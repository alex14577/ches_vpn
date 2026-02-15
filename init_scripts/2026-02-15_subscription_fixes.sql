-- Subscription/payment fixes rollout
-- Run under migration/DBA role.

ALTER TABLE subscriptions
  ADD COLUMN IF NOT EXISTS notified_overdue BOOLEAN NOT NULL DEFAULT FALSE;

ALTER TABLE subscriptions
  ADD COLUMN IF NOT EXISTS reminded_at TIMESTAMPTZ;

ALTER TABLE subscriptions
  ADD COLUMN IF NOT EXISTS notified_expired BOOLEAN NOT NULL DEFAULT FALSE;

CREATE UNIQUE INDEX IF NOT EXISTS idx_payment_events_vk_msg_id
ON payment_events ((payload->>'id'))
WHERE source = 'vk' AND payload->>'id' IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS idx_pending_amount
ON subscriptions (expected_amount_minor)
WHERE status = 'pending_payment';
