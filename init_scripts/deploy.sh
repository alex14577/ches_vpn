#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
REMOTE_DIR="/opt/vpn"

SERVICES=(
  vpn-bot.service
  vpn-subscription.service
  vpn-pay_verifier.service
  vpn-access-sync.service
)

echo "==> Pulling latest code"
git -C "$REPO_DIR" pull

echo "==> Syncing code to $REMOTE_DIR"
sudo rsync -a --delete \
  --exclude ".git/" \
  --exclude ".venv/" \
  --exclude "__pycache__/" \
  --exclude "*.pyc" \
  --exclude ".env" \
  --exclude ".env.systemd" \
  --exclude "temp/" \
  "$REPO_DIR/" "$REMOTE_DIR/"

echo "==> Restarting services"
sudo systemctl restart "${SERVICES[@]}"

echo "==> Done. Status:"
sudo systemctl --no-pager status "${SERVICES[@]}"
