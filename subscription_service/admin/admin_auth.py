import os
import hmac
from pathlib import Path
from typing import Tuple

ADMIN_FILE = Path(
    os.getenv(
        "ADMIN_CREDENTIALS_FILE",
        "/var/lib/ches_vpn/admin.env",
    )
)

def _env(name: str, default: str | None = None) -> str:
    v = os.getenv(name)
    if v is not None and v != "":
        return v
    return default if default is not None else ""

def _read_admin_file() -> dict:
    # формат как .env: KEY=VALUE
    if not ADMIN_FILE.exists():
        return {}
    data = {}
    for line in ADMIN_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        data[k.strip()] = v.strip()
    return data

def get_admin_credentials() -> Tuple[str, str]:
    # приоритет:
    # 1) файл /opt/vpn/.env.admin
    # 2) env ADMIN_USERNAME/ADMIN_PASSWORD
    # 3) дефолт root/root
    f = _read_admin_file()
    u = f.get("ADMIN_USERNAME") or _env("ADMIN_USERNAME", "root")
    p = f.get("ADMIN_PASSWORD") or _env("ADMIN_PASSWORD", "root")
    return u, p

def verify_password(username: str, password: str) -> bool:
    u, p = get_admin_credentials()
    return hmac.compare_digest(username, u) and hmac.compare_digest(password, p)

def save_admin_credentials(username: str, password: str) -> None:
    ADMIN_FILE.parent.mkdir(parents=True, exist_ok=True)
    # минимально безопасно: права 600
    tmp = ADMIN_FILE.with_suffix(".tmp")
    tmp.write_text(f"ADMIN_USERNAME={username}\nADMIN_PASSWORD={password}\n", encoding="utf-8")
    os.chmod(tmp, 0o600)
    tmp.replace(ADMIN_FILE)
