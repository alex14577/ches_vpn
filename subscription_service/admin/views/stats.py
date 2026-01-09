from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from common.db import db_call

router = APIRouter()
templates = Jinja2Templates(directory="subscription_service/admin/templates")

GB = 1024 * 1024 * 1024


@router.get("/stats", response_class=HTMLResponse)
async def stats_page(request: Request):
    stats = await db_call(lambda db: db.stats.list_daily_usage(limit=30))

    stats_asc = list(reversed(stats))
    total_bytes = 0
    rows_asc = []
    for s in stats_asc:
        total_bytes += s.total_bytes or 0
        rows_asc.append(
            {
                "day": s.day,
                "active_users": s.active_users,
                "daily_bytes": s.total_bytes,
                "daily_gb": (s.total_bytes / GB) if s.total_bytes else 0,
                "total_bytes": total_bytes,
                "total_gb": total_bytes / GB if total_bytes else 0,
            }
        )

    rows = list(reversed(rows_asc))

    return templates.TemplateResponse(
        "stats.html",
        {"request": request, "rows": rows},
    )
