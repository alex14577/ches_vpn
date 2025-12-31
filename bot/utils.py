from datetime import datetime, timezone
from html import escape as html_escape
from typing import Optional


import base64, hmac, hashlib

REF_SECRET = b"morgan"  # возьми из env

def _b64url(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")

def make_ref_payload(referrer_tg_id: int) -> str:
    msg = str(referrer_tg_id).encode()
    sig = hmac.new(REF_SECRET, msg, hashlib.sha256).digest()[:10]  # 10 байт хватит
    return _b64url(msg + b"." + sig)

def make_ref_link(bot_username: str, referrer_tg_id: int) -> str:
    return f"https://t.me/{bot_username}?start={make_ref_payload(referrer_tg_id)}"

def _b64url_decode(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)

def parse_ref_payload(payload: str) -> Optional[int]:
    try:
        raw = _b64url_decode(payload)
        msg, sig = raw.split(b".", 1)
        expected = hmac.new(REF_SECRET, msg, hashlib.sha256).digest()[:10]
        if not hmac.compare_digest(sig, expected):
            return None
        return int(msg.decode())
    except Exception:
        return None

def idem_key(prefix: str, tg_user_id: int) -> str:
    # идемпотентность на день
    day = datetime.now(timezone.utc).strftime("%Y%m%d")
    return f"{prefix}:{tg_user_id}:{day}"

def html_pre(text: str) -> str:
    return f"<pre>{html_escape(text or '')}</pre>"