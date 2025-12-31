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

read_and_export_env() {
  echo

  BOT_TOKEN="$(prompt_secret BOT_TOKEN | tr -d '\r\n')"
  DATABASE_URL="$(prompt_secret DATABASE_URL | tr -d '\r\n')"
  PUBLIC_BASE_URL="$(prompt_value PUBLIC_BASE_URL | tr -d '\r\n')"

  # ✅ критично: экспортируем, чтобы видел Python/psql, запускаемые из этого скрипта
  export BOT_TOKEN DATABASE_URL PUBLIC_BASE_URL
}

write_env_file() {
  echo "Writing env file: $ENV_FILE"
  umask 077
  cat > "$ENV_FILE" <<EOF
BOT_TOKEN=${BOT_TOKEN}
DATABASE_URL=${DATABASE_URL}
PUBLIC_BASE_URL=${PUBLIC_BASE_URL}
EOF

  chown "${SERVICE_USER}:${SERVICE_GROUP}" "$ENV_FILE"
  chmod 0600 "$ENV_FILE"
}

ensure_postgres_role_and_db() {
  echo "Ensuring PostgreSQL role and database from DATABASE_URL"

  # Парсим URL надёжно через Python (читает DATABASE_URL из env)
  local parsed
  parsed="$(python3 - <<'PY'
import os, sys
from urllib.parse import urlparse

url = os.environ.get("DATABASE_URL", "")
if not url:
    print("ERROR: DATABASE_URL is empty", file=sys.stderr)
    sys.exit(1)

url2 = url.replace("postgresql+psycopg://", "postgresql://", 1)\
          .replace("postgresql+psycopg2://", "postgresql://", 1)\
          .replace("postgresql+asyncpg://", "postgresql://", 1)

u = urlparse(url2)

user = u.username or ""
password = u.password or ""
host = u.hostname or "localhost"
port = u.port or 5432
db = (u.path or "/")[1:]

print(f"{user}\n{password}\n{host}\n{port}\n{db}")
PY
)"

  local pg_user pg_password pg_host pg_port pg_db
  pg_user="$(echo "$parsed" | sed -n '1p')"
  pg_password="$(echo "$parsed" | sed -n '2p')"
  pg_host="$(echo "$parsed" | sed -n '3p')"
  pg_port="$(echo "$parsed" | sed -n '4p')"
  pg_db="$(echo "$parsed" | sed -n '5p')"

  if [[ -z "$pg_user" || -z "$pg_db" ]]; then
    echo "ERROR: failed to parse DATABASE_URL (user or db is empty)"
    exit 1
  fi

  if [[ "$pg_host" != "localhost" && "$pg_host" != "127.0.0.1" ]]; then
    echo "Remote PostgreSQL detected ($pg_host), skipping role/db creation"
    return 0
  fi

  echo "Postgres user: $pg_user"
  echo "Postgres db:   $pg_db"
  echo "Postgres port: $pg_port"

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

  sudo -u postgres psql -v ON_ERROR_STOP=1 <<SQL
DO \$\$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = '$pg_db') THEN
    CREATE DATABASE $pg_db OWNER $pg_user;
  END IF;
END
\$\$;
SQL
}

run_migrations() {
  echo "Running migrations: python migrate.py"
  # ✅ Передаём env явно в процесс python (на всякий случай)
  sudo -u "$SERVICE_USER" -H bash -lc "
    set -e
    cd '$TARGET_DIR'
    . .venv/bin/activate
    BOT_TOKEN='$BOT_TOKEN' DATABASE_URL='$DATABASE_URL' PUBLIC_BASE_URL='$PUBLIC_BASE_URL' \
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

install_units "$UNIT_SRC_DIR"
enable_and_start
