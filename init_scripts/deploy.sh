#!/usr/bin/env bash
set -euo pipefail

SERVER="firstbyte-msc"
REMOTE_DIR="/opt/vpn"
LOCAL_DIR="$(cd "$(dirname "$0")/.." && pwd)"

SERVICES=(
  vpn-bot.service
  vpn-subscription.service
  vpn-pay_verifier.service
  vpn-access-sync.service
)

echo "==> Syncing code to $SERVER:$REMOTE_DIR"
rsync -a --delete \
  --exclude ".git/" \
  --exclude ".venv/" \
  --exclude "__pycache__/" \
  --exclude "*.pyc" \
  --exclude ".env" \
  --exclude ".env.systemd" \
  --exclude "temp/" \
  "$LOCAL_DIR/" "$SERVER:$REMOTE_DIR/"

echo "==> Restarting services"
ssh "$SERVER" "sudo systemctl restart ${SERVICES[*]}"

echo "==> Done. Status:"
ssh "$SERVER" "sudo systemctl --no-pager status ${SERVICES[*]}"
