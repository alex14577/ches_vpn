-- сервис vpn-bot: создаёт подписки со статусом pending_payment
SELECT format('CREATE ROLE %I LOGIN PASSWORD %L INHERIT', :'vpn_bot_username', :'vpn_bot_password')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'vpn_bot_username')
\gexec
SELECT format('ALTER ROLE %I INHERIT PASSWORD %L', :'vpn_bot_username', :'vpn_bot_password')
WHERE EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'vpn_bot_username')
\gexec

GRANT sub_creator TO :"vpn_bot_username";

-- сервис vpn-pay_verifier: переводит pending_payment в остальные статусы
SELECT format('CREATE ROLE %I LOGIN PASSWORD %L INHERIT', :'vpn_pay_verifier_username', :'vpn_pay_verifier_password')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'vpn_pay_verifier_username')
\gexec
SELECT format('ALTER ROLE %I INHERIT PASSWORD %L', :'vpn_pay_verifier_username', :'vpn_pay_verifier_password')
WHERE EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'vpn_pay_verifier_username')
\gexec

GRANT sub_verifier TO :"vpn_pay_verifier_username";

-- сервис vpn-subscription: полный доступ к subscriptions
SELECT format('CREATE ROLE %I LOGIN PASSWORD %L INHERIT', :'vpn_subscription_username', :'vpn_subscription_password')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'vpn_subscription_username')
\gexec
SELECT format('ALTER ROLE %I INHERIT PASSWORD %L', :'vpn_subscription_username', :'vpn_subscription_password')
WHERE EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'vpn_subscription_username')
\gexec

GRANT sub_reader TO :"vpn_subscription_username";

GRANT USAGE ON SCHEMA public TO :"vpn_bot_username", :"vpn_pay_verifier_username", :"vpn_subscription_username";
GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA public TO :"vpn_bot_username", :"vpn_pay_verifier_username", :"vpn_subscription_username";
GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA public TO :"vpn_bot_username", :"vpn_pay_verifier_username", :"vpn_subscription_username";
