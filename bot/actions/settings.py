import os

SBP_PHONE = "+7-967-552-5410"
PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "https://ches-server.mooo.com").strip()

TG_BOT_TOKEN = os.environ.get("TG_BOT_TOKEN", "").strip()
ADMIN_TG_ID = [ 572200030 ]
if not TG_BOT_TOKEN:
    raise RuntimeError("TG_BOT_TOKEN is empty. Export TG_BOT_TOKEN env var.")
