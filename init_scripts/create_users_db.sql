-- сервис vpn-bot: создаёт подписки со статусом pending_payment
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'vpn_bot_username') THEN
    EXECUTE format('CREATE ROLE %I LOGIN PASSWORD %L', :'vpn_bot_username', :'vpn_bot_password');
  ELSE
    EXECUTE format('ALTER ROLE %I PASSWORD %L', :'vpn_bot_username', :'vpn_bot_password');
  END IF;
END $$;

GRANT sub_creator TO :"vpn_bot_username";

-- сервис vpn-worker: переводит pending_payment в остальные статусы
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'vpn_worker_username') THEN
    EXECUTE format('CREATE ROLE %I LOGIN PASSWORD %L', :'vpn_worker_username', :'vpn_worker_password');
  ELSE
    EXECUTE format('ALTER ROLE %I PASSWORD %L', :'vpn_worker_username', :'vpn_worker_password');
  END IF;
END $$;

GRANT sub_verifier TO :"vpn_worker_username";

-- сервис vpn-subscription: только читает подписки (статус менять не может)
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'vpn_subscription_username') THEN
    EXECUTE format('CREATE ROLE %I LOGIN PASSWORD %L', :'vpn_subscription_username', :'vpn_subscription_password');
  ELSE
    EXECUTE format('ALTER ROLE %I PASSWORD %L', :'vpn_subscription_username', :'vpn_subscription_password');
  END IF;
END $$;

GRANT sub_reader TO :"vpn_subscription_username";
