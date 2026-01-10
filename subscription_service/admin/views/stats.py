from __future__ import annotations

from datetime import timedelta
import uuid

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from common.db import db_call

router = APIRouter()
templates = Jinja2Templates(directory="subscription_service/admin/templates")

GB = 1024 * 1024 * 1024


@router.get("/stats", response_class=HTMLResponse)
async def stats_page(request: Request):
    return await stats_users_page(request)


@router.get("/stats/users", response_class=HTMLResponse)
async def stats_users_page(request: Request):
    latest_day = await db_call(lambda db: db.stats.latest_snapshot_day())
    if latest_day is None:
        server_manager = request.app.state.serverManager
        live = await server_manager.collect_user_traffic()
        label_map = await server_manager.collect_user_labels()
        users = await db_call(lambda db: db.users.all())
        user_labels = {u.id: (u.username or str(u.tg_user_id)) for u in users}
        for user_id, label in label_map.items():
            if user_id not in user_labels and label:
                user_labels[user_id] = f"{label} NOT-DB"

        rows = []
        for user_id, (total_bytes, daily_bytes) in live.items():
            user_label = user_labels.get(user_id)
            if not user_label:
                continue
            rows.append(
                {
                    "user_label": user_label,
                    "daily_gb": daily_bytes / GB if daily_bytes else 0,
                    "three_gb": daily_bytes / GB if daily_bytes else 0,
                    "month_gb": daily_bytes / GB if daily_bytes else 0,
                    "total_gb": total_bytes / GB if total_bytes else 0,
                }
            )

        rows.sort(key=lambda r: (r["daily_gb"], r["total_gb"]), reverse=True)
        return templates.TemplateResponse(
            "stats_users.html",
            {"request": request, "rows": rows, "day": None},
        )

    start_day = latest_day - timedelta(days=30)

    current_map = await db_call(lambda db: db.stats.user_snapshot_map(latest_day))
    snapshots = await db_call(lambda db: db.stats.user_snapshots_range(start_day, latest_day))
    users = await db_call(lambda db: db.users.all())

    user_labels = {u.id: (u.username or str(u.tg_user_id)) for u in users}
    label_map = await request.app.state.serverManager.collect_user_labels()
    for user_id, label in label_map.items():
        if user_id not in user_labels and label:
            user_labels[user_id] = f"{label} NOT-DB"

    daily_by_user: dict[uuid.UUID, int] = {}
    three_by_user: dict[uuid.UUID, int] = {}
    month_by_user: dict[uuid.UUID, int] = {}

    last3_start = latest_day - timedelta(days=2)
    last30_start = latest_day - timedelta(days=29)

    for row in snapshots:
        uid = row.user_id
        daily = row.daily_bytes or 0
        if row.day == latest_day:
            daily_by_user[uid] = daily
        if row.day >= last3_start:
            three_by_user[uid] = three_by_user.get(uid, 0) + daily
        if row.day >= last30_start:
            month_by_user[uid] = month_by_user.get(uid, 0) + daily

    rows = []
    for user_id, current_row in current_map.items():
        user_label = user_labels.get(user_id)
        if not user_label:
            continue
        total_bytes = current_row.total_bytes or 0
        daily_bytes = daily_by_user.get(user_id, 0)
        three_bytes = three_by_user.get(user_id, 0)
        month_bytes = month_by_user.get(user_id, 0)
        rows.append(
            {
                "user_label": user_label,
                "daily_gb": daily_bytes / GB if daily_bytes else 0,
                "three_gb": three_bytes / GB if three_bytes else 0,
                "month_gb": month_bytes / GB if month_bytes else 0,
                "total_gb": total_bytes / GB if total_bytes else 0,
            }
        )

    rows.sort(key=lambda r: (r["daily_gb"], r["total_gb"]), reverse=True)

    return templates.TemplateResponse(
        "stats_users.html",
        {"request": request, "rows": rows, "day": latest_day},
    )
