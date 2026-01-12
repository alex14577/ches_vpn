-- сервис vpn-bot: создаёт подписки со статусом pending_payment
SELECT format('CREATE ROLE %I LOGIN PASSWORD %L', :'vpn_bot_username', :'vpn_bot_password')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'vpn_bot_username')
\gexec
SELECT format('ALTER ROLE %I PASSWORD %L', :'vpn_bot_username', :'vpn_bot_password')
WHERE EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'vpn_bot_username')
\gexec

GRANT sub_creator TO :"vpn_bot_username";

-- сервис vpn-worker: переводит pending_payment в остальные статусы
SELECT format('CREATE ROLE %I LOGIN PASSWORD %L', :'vpn_worker_username', :'vpn_worker_password')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'vpn_worker_username')
\gexec
SELECT format('ALTER ROLE %I PASSWORD %L', :'vpn_worker_username', :'vpn_worker_password')
WHERE EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'vpn_worker_username')
\gexec

GRANT sub_verifier TO :"vpn_worker_username";

-- сервис vpn-subscription: только читает подписки (статус менять не может)
SELECT format('CREATE ROLE %I LOGIN PASSWORD %L', :'vpn_subscription_username', :'vpn_subscription_password')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'vpn_subscription_username')
\gexec
SELECT format('ALTER ROLE %I PASSWORD %L', :'vpn_subscription_username', :'vpn_subscription_password')
WHERE EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'vpn_subscription_username')
\gexec

GRANT sub_reader TO :"vpn_subscription_username";
