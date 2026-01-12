#!/usr/bin/env bash
set -euo pipefail

# --- constants ---
TARGET_DIR="/opt/vpn"
SERVICE_USER="alex"
SERVICE_GROUP="alex"
ENV_FILE="$TARGET_DIR/.env.systemd"
UNIT_DST_DIR="/etc/systemd/system"
ADMIN_CREDENTIALS_FILE="/var/lib/ches_vpn"

SERVICES=(
  vpn-bot.service
  vpn-subscription.service
)

# --- helpers ---
require_root() {
  if [[ "$EUID" -ne 0 ]]; then
    echo "ERROR: run as root (use sudo)"
    exit 1
  fi
}

ensure_packages() {
  echo "Installing base packages"
  apt-get update -y
  apt-get install -y rsync python3 python3-venv python3-pip ca-certificates curl
}

ensure_postgres() {
  echo "Installing PostgreSQL (local)"
  apt-get install -y postgresql postgresql-contrib
  systemctl enable --now postgresql
  systemctl is-active --quiet postgresql || {
    echo "ERROR: postgresql service is not active"
    exit 1
  }
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

  rsync -a --delete \
    --exclude ".env.systemd" \
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
  echo "Ensuring venv and dependencies in $TARGET_DIR/.venv"

  sudo -u "$SERVICE_USER" -H bash -lc "
    set -e
    cd '$TARGET_DIR'
    if [ ! -d .venv ]; then
      python3 -m venv .venv
    fi
    . .venv/bin/activate
    python -m pip install -U pip wheel setuptools

    if [ -f requirements.txt ]; then
      pip install -r requirements.txt
    else
      echo 'ERROR: requirements.txt not found. Add it or adapt installer for poetry/uv.'
      exit 1
    fi
  "
}

load_env_if_exists() {
  if [[ -f "$ENV_FILE" ]]; then
    echo "[INFO] Found existing env file: $ENV_FILE"
    set -a
    source "$ENV_FILE"
    set +a
    return 0
  fi
  return 1
}

read_and_export_env() {
  if load_env_if_exists; then
    echo "[INFO] Using credentials from $ENV_FILE"
  fi

  : "${VPN_SUBSCRIPTION_DB_USERNAME:=subscription}"
  : "${VPN_SUBSCRIPTION_DB_PASSWORD:=1234}"
  : "${VPN_BOT_DB_USERNAME:=bot}"
  : "${VPN_BOT_DB_PASSWORD:=1234}"
  : "${VPN_WORKER_DB_USERNAME:=woker}"
  : "${VPN_WORKER_DB_PASSWORD:=1234}"
  : "${DB_NAME:=app}"

  if [[ -z "${TG_BOT_TOKEN:-}" ]]; then
    read -rp "Telegram bot token: " TG_BOT_TOKEN
  fi

  if [[ -z "${VPN_SUBSCRIPTION_DB_USERNAME:-}" ]]; then
    read -rp "VPN_SUBSCRIPTION_DB_USERNAME: " VPN_SUBSCRIPTION_DB_USERNAME
  fi
  if [[ -z "${VPN_SUBSCRIPTION_DB_PASSWORD:-}" ]]; then
    VPN_SUBSCRIPTION_DB_PASSWORD="$(prompt_secret VPN_SUBSCRIPTION_DB_PASSWORD)"
  fi

  if [[ -z "${VPN_BOT_DB_USERNAME:-}" ]]; then
    read -rp "VPN_BOT_DB_USERNAME: " VPN_BOT_DB_USERNAME
  fi
  if [[ -z "${VPN_BOT_DB_PASSWORD:-}" ]]; then
    VPN_BOT_DB_PASSWORD="$(prompt_secret VPN_BOT_DB_PASSWORD)"
  fi

  if [[ -z "${VPN_WORKER_DB_USERNAME:-}" ]]; then
    read -rp "VPN_WORKER_DB_USERNAME: " VPN_WORKER_DB_USERNAME
  fi
  if [[ -z "${VPN_WORKER_DB_PASSWORD:-}" ]]; then
    VPN_WORKER_DB_PASSWORD="$(prompt_secret VPN_WORKER_DB_PASSWORD)"
  fi

  if [[ -z "${DB_NAME:-}" ]]; then
    read -rp "Postgres DB name: " DB_NAME
  fi

  export TG_BOT_TOKEN
  export VPN_SUBSCRIPTION_DB_USERNAME
  export VPN_SUBSCRIPTION_DB_PASSWORD
  export VPN_BOT_DB_USERNAME
  export VPN_BOT_DB_PASSWORD
  export VPN_WORKER_DB_USERNAME
  export VPN_WORKER_DB_PASSWORD
  export DB_NAME
  
  : "${DB_HOST:=127.0.0.1}"
  : "${DB_PORT:=5432}"
  export DB_HOST DB_PORT
}


write_env_file() {
  if [[ -f "$ENV_FILE" ]]; then
    echo "[INFO] Env file already exists, ensuring required vars"
    if ! grep -q "^VPN_SUBSCRIPTION_DB_USERNAME=" "$ENV_FILE"; then
      echo "VPN_SUBSCRIPTION_DB_USERNAME=$VPN_SUBSCRIPTION_DB_USERNAME" >>"$ENV_FILE"
    fi
    if ! grep -q "^VPN_SUBSCRIPTION_DB_PASSWORD=" "$ENV_FILE"; then
      echo "VPN_SUBSCRIPTION_DB_PASSWORD=$VPN_SUBSCRIPTION_DB_PASSWORD" >>"$ENV_FILE"
    fi
    if ! grep -q "^VPN_BOT_DB_USERNAME=" "$ENV_FILE"; then
      echo "VPN_BOT_DB_USERNAME=$VPN_BOT_DB_USERNAME" >>"$ENV_FILE"
    fi
    if ! grep -q "^VPN_BOT_DB_PASSWORD=" "$ENV_FILE"; then
      echo "VPN_BOT_DB_PASSWORD=$VPN_BOT_DB_PASSWORD" >>"$ENV_FILE"
    fi
    if ! grep -q "^VPN_WORKER_DB_USERNAME=" "$ENV_FILE"; then
      echo "VPN_WORKER_DB_USERNAME=$VPN_WORKER_DB_USERNAME" >>"$ENV_FILE"
    fi
    if ! grep -q "^VPN_WORKER_DB_PASSWORD=" "$ENV_FILE"; then
      echo "VPN_WORKER_DB_PASSWORD=$VPN_WORKER_DB_PASSWORD" >>"$ENV_FILE"
    fi
    return
  fi

  echo "[INFO] Writing env file to $ENV_FILE"

  install -d -m 700 "$TARGET_DIR"

  cat >"$ENV_FILE" <<EOF
TG_BOT_TOKEN=$TG_BOT_TOKEN
VPN_SUBSCRIPTION_DB_USERNAME=$VPN_SUBSCRIPTION_DB_USERNAME
VPN_SUBSCRIPTION_DB_PASSWORD=$VPN_SUBSCRIPTION_DB_PASSWORD
VPN_BOT_DB_USERNAME=$VPN_BOT_DB_USERNAME
VPN_BOT_DB_PASSWORD=$VPN_BOT_DB_PASSWORD
VPN_WORKER_DB_USERNAME=$VPN_WORKER_DB_USERNAME
VPN_WORKER_DB_PASSWORD=$VPN_WORKER_DB_PASSWORD
DB_NAME=$DB_NAME
DB_HOST=$DB_HOST
DB_PORT=$DB_PORT
EOF

  chown "$SERVICE_USER:$SERVICE_GROUP" "$ENV_FILE"
  chmod 600 "$ENV_FILE"
}


ensure_postgres_role_and_db() {
  if [[ -z "${DB_NAME:-}" || -z "${VPN_SUBSCRIPTION_DB_USERNAME:-}" || -z "${VPN_SUBSCRIPTION_DB_PASSWORD:-}" ]]; then
    echo "ERROR: DB_NAME/VPN_SUBSCRIPTION_DB_USERNAME/VPN_SUBSCRIPTION_DB_PASSWORD must be set"
    exit 1
  fi

  : "${DB_HOST:=127.0.0.1}"
  : "${DB_PORT:=5432}"

  if [[ "$DB_HOST" != "localhost" && "$DB_HOST" != "127.0.0.1" ]]; then
    echo "Remote PostgreSQL detected ($DB_HOST), skipping role/db creation"
    return 0
  fi

  local pg_user="$VPN_SUBSCRIPTION_DB_USERNAME"
  local pg_password="$VPN_SUBSCRIPTION_DB_PASSWORD"
  local pg_db="$DB_NAME"

  echo "Postgres user: $pg_user"
  echo "Postgres db:   $pg_db"
  echo "Postgres port: $DB_PORT"

  # 1) Ensure role (OK to do in DO)
  sudo -u postgres psql -v ON_ERROR_STOP=1 <<SQL
DO \$\$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '$pg_user') THEN
    CREATE ROLE $pg_user LOGIN PASSWORD '$pg_password';
  ELSE
    ALTER ROLE $pg_user PASSWORD '$pg_password';
  END IF;
END
\$\$;
SQL

  # 2) Ensure database (MUST be outside transaction/DO)
  if sudo -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname = '$pg_db'" | grep -q 1; then
    echo "Database '$pg_db' already exists"
  else
    echo "Creating database '$pg_db' owned by '$pg_user'"
    sudo -u postgres psql -v ON_ERROR_STOP=1 -c "CREATE DATABASE $pg_db OWNER $pg_user;"
  fi
}


run_migrations() {
  echo "Running migrations: python migrate.py"
  # ✅ Передаём env явно в процесс python (на всякий случай)
  sudo -u "$SERVICE_USER" -H bash -lc "
    set -e
    cd '$TARGET_DIR'
    . .venv/bin/activate
    DB_HOST='$DB_HOST' \
    DB_PORT='$DB_PORT' \
    DB_NAME='$DB_NAME' \
    VPN_SUBSCRIPTION_DB_USERNAME='$VPN_SUBSCRIPTION_DB_USERNAME' \
    VPN_SUBSCRIPTION_DB_PASSWORD='$VPN_SUBSCRIPTION_DB_PASSWORD' \
      python migrate.py
  "
}

run_init_sql() {
  echo "Running init SQL scripts"

  if [[ -z "${DB_NAME:-}" ]]; then
    echo "ERROR: DB_NAME is empty"
    exit 1
  fi
  local db_name="$DB_NAME"
  local roles_sql="$TARGET_DIR/init_scripts/init_roles.sql"
  local users_sql="$TARGET_DIR/init_scripts/create_users_db.sql"

  if [[ ! -f "$roles_sql" || ! -f "$users_sql" ]]; then
    echo "ERROR: init SQL scripts not found in $TARGET_DIR/init_scripts"
    exit 1
  fi

  sudo -u postgres psql -v ON_ERROR_STOP=1 -d "$db_name" -f "$roles_sql"
  sudo -u postgres psql -v ON_ERROR_STOP=1 \
    -v vpn_bot_username="$VPN_BOT_DB_USERNAME" \
    -v vpn_bot_password="$VPN_BOT_DB_PASSWORD" \
    -v vpn_worker_username="$VPN_WORKER_DB_USERNAME" \
    -v vpn_worker_password="$VPN_WORKER_DB_PASSWORD" \
    -v vpn_subscription_username="$VPN_SUBSCRIPTION_DB_USERNAME" \
    -v vpn_subscription_password="$VPN_SUBSCRIPTION_DB_PASSWORD" \
    -d "$db_name" -f "$users_sql"
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

create_creds_file() {
  touch "$ADMIN_CREDENTIALS_FILE"
  chown "$SERVICE_USER":"$SERVICE_GROUP" "$ADMIN_CREDENTIALS_FILE"
  chmod 700 "$ADMIN_CREDENTIALS_FILE"
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

restart_services() {

  echo "==== $(date -Is) Starting soft restart ===="

  for svc in "${SERVICES[@]}"; do
    if systemctl is-active --quiet "$svc"; then
      echo "[$(date -Is)] Restarting $svc"

      if systemctl restart "$svc"; then
        echo "[$(date -Is)] $svc restarted successfully"
      else
        echo "[$(date -Is)] ERROR: failed to restart $svc"
        systemctl --no-pager --full status "$svc"
        exit 1
      fi
    else
      echo "[$(date -Is)] $svc is not active — skipping"
    fi
  done

  echo "==== $(date -Is) Soft restart finished ===="
}

# --- main ---
require_root

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
UNIT_SRC_DIR="$SCRIPT_DIR"

echo "Repo root: $REPO_ROOT"
echo "Target dir: $TARGET_DIR"
echo "Service user: $SERVICE_USER"
echo

ensure_packages
ensure_postgres
ensure_user
copy_repo_to_opt "$REPO_ROOT"
ensure_venv_and_deps
read_and_export_env
write_env_file
ensure_postgres_role_and_db
run_migrations
run_init_sql

create_creds_file
install_units "$UNIT_SRC_DIR"
enable_and_start
restart_services
