-- init_roles.sql
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
      CHECK (status IN ('pending_payment','active','payment_failed','canceled','expired'));
  END IF;
END
$$;

-- 2) RLS
ALTER TABLE subscriptions ENABLE ROW LEVEL SECURITY;

-- 3) Политики (создаём/пересоздаём идемпотентно)
DROP POLICY IF EXISTS subs_creator_insert_pending ON subscriptions;
CREATE POLICY subs_creator_insert_pending
ON subscriptions
FOR INSERT
TO sub_creator
WITH CHECK (
  status = 'pending_payment'
  AND expected_amount_minor > 0
  AND matched_event_id IS NULL
);

DROP POLICY IF EXISTS subs_verifier_update_pending ON subscriptions;
CREATE POLICY subs_verifier_update_pending
ON subscriptions
FOR UPDATE
TO sub_verifier
USING (status = 'pending_payment')
WITH CHECK (status IN ('active','payment_failed','canceled','expired'));

DROP POLICY IF EXISTS subs_reader_select ON subscriptions;
CREATE POLICY subs_reader_select
ON subscriptions
FOR SELECT
TO sub_reader
USING (true);

-- 4) Права
REVOKE ALL ON subscriptions FROM sub_creator;
REVOKE ALL ON subscriptions FROM sub_verifier;
REVOKE ALL ON subscriptions FROM sub_reader;

GRANT SELECT, INSERT ON subscriptions TO sub_creator;

GRANT SELECT ON subscriptions TO sub_verifier;
GRANT UPDATE(status, updated_at) ON subscriptions TO sub_verifier;

GRANT SELECT ON subscriptions TO sub_reader;
