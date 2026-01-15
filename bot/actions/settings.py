import os

SBP_PHONE = "+7-967-552-5410"
PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "https://ches-server.mooo.com").strip()

TG_BOT_TOKEN = os.environ.get("TG_BOT_TOKEN", "").strip()

_admin_raw = os.environ.get("ADMIN_TG_ID", "").strip() or os.environ.get("ADMIN_TG_IDS", "").strip()
if _admin_raw:
    parts = [p for p in _admin_raw.replace(";", ",").split(",") if p.strip()]
    ADMIN_TG_ID = [int(p.strip()) for p in parts]
else:
    ADMIN_TG_ID = [572200030]
if not TG_BOT_TOKEN:
    raise RuntimeError("TG_BOT_TOKEN is empty. Export TG_BOT_TOKEN env var.")
