#!/usr/bin/env bash
set -euo pipefail

# --- constants ---
TARGET_DIR="/opt/vpn"
SERVICE_USER="alex"
SERVICE_GROUP="alex"
ENV_FILE="$TARGET_DIR/.env.systemd"
UNIT_DST_DIR="/etc/systemd/system"

SERVICES=(
  vpn-bot.service
  vpn-worker.service
  vpn-subscription.service
)

# --- helpers ---
require_root() {
  if [[ "$EUID" -ne 0 ]]; then
    echo "ERROR: run as root (use sudo)"
    exit 1
  fi
}

ensure_user() {
  if id -u "$SERVICE_USER" >/dev/null 2>&1; then
    echo "User '$SERVICE_USER' exists"
  else
    echo "Creating user '$SERVICE_USER'"
    useradd --create-home --shell /bin/bash "$SERVICE_USER"
  fi
}

prompt_secret() {
  local var_name="$1"
  local value
  while true; do
    read -r -s -p "Enter ${var_name}: " value
    echo
    if [[ -n "${value}" ]]; then
      printf '%s' "$value"
      return 0
    fi
    echo "Value cannot be empty."
  done
}

prompt_value() {
  local var_name="$1"
  local value
  while true; do
    read -r -p "Enter ${var_name}: " value
    if [[ -n "${value}" ]]; then
      printf '%s' "$value"
      return 0
    fi
    echo "Value cannot be empty."
  done
}

copy_repo_to_opt() {
  local src_repo_root="$1"

  echo "Copying repository to $TARGET_DIR"
  mkdir -p "$TARGET_DIR"

  # чистое копирование, без .git и мусора
  rsync -a --delete \
    --exclude ".git/" \
    --exclude ".venv/" \
    --exclude "__pycache__/" \
    --exclude "*.pyc" \
    --exclude ".pytest_cache/" \
    --exclude ".mypy_cache/" \
    --exclude ".ruff_cache/" \
    --exclude ".idea/" \
    --exclude ".vscode/" \
    "$src_repo_root/" "$TARGET_DIR/"

  chown -R "${SERVICE_USER}:${SERVICE_GROUP}" "$TARGET_DIR"
}

ensure_venv_and_deps() {
  # Этот блок делает best-effort установку зависимостей.
  echo "Ensuring venv and dependencies in $TARGET_DIR/.venv"

  sudo -u "$SERVICE_USER" -H bash -lc "
    set -e
    cd '$TARGET_DIR'
      python3 -m venv .venv
    . .venv/bin/activate
    python -m pip install -U pip wheel setuptools

    if [ -f requirements.txt ]; then
      pip install -r requirements.txt
    elif [ -f pyproject.toml ]; then
      echo 'WARNING: pyproject.toml found, but installer supports requirements.txt by default.'
      echo '         Add requirements.txt or adapt install.sh for poetry/uv.'
    else
      echo 'WARNING: No requirements.txt/pyproject.toml found; skipping deps install.'
    fi
  "
}

write_env_file() {
  echo

  BOT_TOKEN="$(prompt_secret BOT_TOKEN)"
  DATABASE_URL="$(prompt_secret DATABASE_URL)"
  PUBLIC_BASE_URL="$(prompt_value PUBLIC_BASE_URL)"

  echo "Writing env file: $ENV_FILE"
  umask 077

  cat > "$ENV_FILE" <<EOF
BOT_TOKEN="${BOT_TOKEN}"
DATABASE_URL="${DATABASE_URL}"
PUBLIC_BASE_URL="${PUBLIC_BASE_URL}"
EOF

  chown "${SERVICE_USER}:${SERVICE_GROUP}" "$ENV_FILE"
  chmod 0600 "$ENV_FILE"
}


run_migrations() {
  echo "Running migrations: python migrate.py"
  sudo -u "$SERVICE_USER" -H bash -lc "
    set -e
    cd '$TARGET_DIR'
    . .venv/bin/activate
    export \$(grep -v '^#' '$ENV_FILE' | xargs)
    python migrate.py
  "
}

install_units() {
  local unit_src_dir="$1"

  echo "Installing systemd unit files into $UNIT_DST_DIR"
  for service in "${SERVICES[@]}"; do
    local src="$unit_src_dir/$service"
    local dst="$UNIT_DST_DIR/$service"

    if [[ ! -f "$src" ]]; then
      echo "ERROR: unit file not found: $src"
      exit 1
    fi

    echo "→ $service"
    install -m 0644 "$src" "$dst"
  done

  systemctl daemon-reload
}

enable_and_start() {
  echo "Enabling and starting services"
  for service in "${SERVICES[@]}"; do
    systemctl enable --now "$service"
  done

  echo
  echo "Done. Status:"
  systemctl --no-pager status "${SERVICES[@]}"
}

install_deps() {
    apt install rsync python3.12-venv
}

# --- main ---
require_root

# определить корень репо как директорию на уровень выше init_scripts
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
UNIT_SRC_DIR="$SCRIPT_DIR"

echo "Repo root: $REPO_ROOT"
echo "Target dir: $TARGET_DIR"
echo "Service user: $SERVICE_USER"
echo


install_deps
ensure_user
copy_repo_to_opt "$REPO_ROOT"
ensure_venv_and_deps
write_env_file
run_migrations
install_units "$UNIT_SRC_DIR"
enable_and_start
