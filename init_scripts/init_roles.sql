-- .
-- Выполнять под DBA/миграционной ролью (не под сервисными ролями).
-- Создаёт роли sub_creator / sub_verifier / sub_reader если их нет, включает RLS/политики,
-- и настраивает права на subscriptions.

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'sub_creator') THEN
    CREATE ROLE sub_creator NOINHERIT;
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'sub_verifier') THEN
    CREATE ROLE sub_verifier NOINHERIT;
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'sub_reader') THEN
    CREATE ROLE sub_reader NOINHERIT;
  END IF;
END
$$;

-- 1) Обязательные поля/ограничения (если ты добавлял expected_amount_minor ранее — пропусти этот блок)
-- ВНИМАНИЕ: IF NOT EXISTS для ADD COLUMN есть, для CONSTRAINT — нет во всех версиях одинаково,
-- поэтому constraint проверяем через pg_constraint.

ALTER TABLE users
  ADD COLUMN IF NOT EXISTS used_trial BOOLEAN NOT NULL DEFAULT FALSE;

ALTER TABLE subscriptions
  ADD COLUMN IF NOT EXISTS expected_amount_minor INTEGER NOT NULL DEFAULT 0;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'subscriptions_status_chk'
  ) THEN
    ALTER TABLE subscriptions
      ADD CONSTRAINT subscriptions_status_chk
      CHECK (status IN ('pending_payment','active','payment_failed','payment_overdue','canceled','expired'));
  END IF;
END
$$;

-- matched_event_id (может появиться позже; добавляем безопасно)
ALTER TABLE subscriptions
  ADD COLUMN IF NOT EXISTS matched_event_id UUID;

DO $$
BEGIN
  IF EXISTS (
    SELECT 1
    FROM information_schema.tables
    WHERE table_name = 'payment_events'
  ) AND NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'subscriptions_matched_event_id_fkey'
  ) THEN
    ALTER TABLE subscriptions
      ADD CONSTRAINT subscriptions_matched_event_id_fkey
      FOREIGN KEY (matched_event_id)
      REFERENCES payment_events(id)
      ON DELETE SET NULL;
  END IF;
END
$$;

-- 2) RLS
ALTER TABLE subscriptions ENABLE ROW LEVEL SECURITY;
ALTER TABLE subscriptions FORCE ROW LEVEL SECURITY;

-- 3) Политики (создаём/пересоздаём идемпотентно)
DROP POLICY IF EXISTS subs_select_all ON subscriptions;
CREATE POLICY subs_select_all
ON subscriptions
FOR SELECT
TO sub_creator, sub_verifier, sub_reader
USING (true);

DROP POLICY IF EXISTS subs_creator_insert_pending ON subscriptions;
DO $$
BEGIN
  IF EXISTS (
    SELECT 1
    FROM information_schema.columns
    WHERE table_name = 'subscriptions'
      AND column_name = 'matched_event_id'
  ) THEN
    EXECUTE $sql$
      CREATE POLICY subs_creator_insert_pending
      ON subscriptions
      FOR INSERT
      TO sub_creator
      WITH CHECK (
        (
          status = 'pending_payment'
          AND expected_amount_minor >= 0
          AND matched_event_id IS NULL
        )
        OR (
          status = 'active'
          AND expected_amount_minor = 0
          AND matched_event_id IS NULL
          AND EXISTS (
            SELECT 1
            FROM plans p
            WHERE p.id = plan_id
              AND p.code IN ('free','trial')
          )
        )
      )
    $sql$;
  ELSE
    EXECUTE $sql$
      CREATE POLICY subs_creator_insert_pending
      ON subscriptions
      FOR INSERT
      TO sub_creator
      WITH CHECK (
        (
          status = 'pending_payment'
          AND expected_amount_minor >= 0
        )
        OR (
          status = 'active'
          AND expected_amount_minor = 0
          AND EXISTS (
            SELECT 1
            FROM plans p
            WHERE p.id = plan_id
              AND p.code IN ('free','trial')
          )
        )
      )
    $sql$;
  END IF;
END
$$;

DROP POLICY IF EXISTS subs_update_no_status_change ON subscriptions;
CREATE POLICY subs_update_no_status_change
ON subscriptions
FOR UPDATE
TO sub_creator
USING (true)
WITH CHECK (
  status = (
    SELECT s.status
    FROM subscriptions AS s
    WHERE s.id = subscriptions.id
  )
);

DROP POLICY IF EXISTS subs_creator_cancel_pending ON subscriptions;
CREATE POLICY subs_creator_cancel_pending
ON subscriptions
FOR UPDATE
TO sub_creator
USING (status = 'pending_payment')
WITH CHECK (status = 'canceled');

DROP POLICY IF EXISTS subs_verifier_update_pending ON subscriptions;
CREATE POLICY subs_verifier_update_pending
ON subscriptions
FOR UPDATE
TO sub_verifier
USING (status = 'pending_payment')
WITH CHECK (status IN ('active','payment_failed','payment_overdue','canceled','expired'));

DROP POLICY IF EXISTS subs_reader_insert_all ON subscriptions;
CREATE POLICY subs_reader_insert_all
ON subscriptions
FOR INSERT
TO sub_reader
WITH CHECK (true);

DROP POLICY IF EXISTS subs_reader_update_all ON subscriptions;
CREATE POLICY subs_reader_update_all
ON subscriptions
FOR UPDATE
TO sub_reader
USING (true)
WITH CHECK (true);

-- 4) Права
REVOKE ALL ON subscriptions FROM sub_creator;
REVOKE ALL ON subscriptions FROM sub_verifier;
REVOKE ALL ON subscriptions FROM sub_reader;

GRANT SELECT, INSERT, UPDATE ON subscriptions TO sub_creator;
GRANT SELECT, UPDATE(status, updated_at) ON subscriptions TO sub_verifier;
GRANT SELECT, INSERT, UPDATE ON subscriptions TO sub_reader;

REVOKE UPDATE(status) ON subscriptions FROM sub_creator;

GRANT USAGE ON SCHEMA public TO sub_creator, sub_verifier, sub_reader;
GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA public TO sub_creator, sub_verifier, sub_reader;
GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA public TO sub_creator, sub_verifier, sub_reader;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE ON TABLES TO sub_creator, sub_verifier, sub_reader;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO sub_creator, sub_verifier, sub_reader;
ALTER DEFAULT PRIVILEGES FOR ROLE :"db_owner" IN SCHEMA public GRANT SELECT, INSERT, UPDATE ON TABLES TO sub_creator, sub_verifier, sub_reader;
ALTER DEFAULT PRIVILEGES FOR ROLE :"db_owner" IN SCHEMA public GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO sub_creator, sub_verifier, sub_reader;

-- 5) Notify on subscription changes (access_sync listener)
CREATE OR REPLACE FUNCTION subscriptions_notify_change()
RETURNS trigger AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    PERFORM pg_notify(
      'subscriptions_changed',
      json_build_object('user_id', OLD.user_id)::text
    );
    RETURN OLD;
  END IF;

  PERFORM pg_notify(
    'subscriptions_changed',
    json_build_object('user_id', NEW.user_id)::text
  );
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS subscriptions_notify_change ON subscriptions;
CREATE TRIGGER subscriptions_notify_change
AFTER INSERT OR UPDATE OR DELETE ON subscriptions
FOR EACH ROW
EXECUTE FUNCTION subscriptions_notify_change();
