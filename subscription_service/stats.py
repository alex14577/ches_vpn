from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from common.db import db_call
from common.logger import Logger
from common.xui_client.registry import Manager

TZ = ZoneInfo("Europe/Moscow")


def _today_local() -> date:
    return datetime.now(TZ).date()


async def collect_daily_usage(server_manager: Manager, *, snapshot_day: date | None = None) -> None:
    """
    Снимает снапшоты и считает суточное потребление.
    Использует снапшоты на начало дня: delta(snapshot_today - snapshot_yesterday).
    """
    snap_day = snapshot_day or _today_local()
    prev_day = snap_day - timedelta(days=1)

    current_snapshot = await db_call(lambda db: db.stats.user_snapshot_map(snap_day))
    if not current_snapshot:
        current_snapshot = await server_manager.collect_user_traffic()
        await db_call(lambda db: db.stats.upsert_user_snapshots(snap_day, current_snapshot))
        current_snapshot = await db_call(lambda db: db.stats.user_snapshot_map(snap_day))

    total_bytes = 0
    active_users = 0
    for row in current_snapshot.values():
        daily_bytes = getattr(row, "daily_bytes", 0) or 0
        if daily_bytes > 0:
            active_users += 1
            total_bytes += daily_bytes

    await db_call(lambda db: db.stats.upsert_daily_usage(snap_day, active_users, total_bytes))


async def daily_stats_task(server_manager: Manager) -> None:
    while True:
        now = datetime.now(TZ)
        target = now.replace(hour=0, minute=5, second=0, microsecond=0)
        if now >= target:
            target += timedelta(days=1)

        await asyncio.sleep((target - now).total_seconds())

        try:
            await collect_daily_usage(server_manager)
        except Exception:
            Logger.exception("daily_stats_task failed")
            await asyncio.sleep(5)
