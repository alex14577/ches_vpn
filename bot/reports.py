import asyncio
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from telegram.ext import Application

from common.adapters import DbAdapters
from common.db import db_call
from common.logger import Logger

TZ = ZoneInfo("Europe/Moscow")

async def daily_report_task(app: Application, adminTgId) -> None:
    while True:
        now = datetime.now(TZ)

        # ближайшие 21:00
        target = now.replace(hour=21, minute=0, second=0, microsecond=0)
        if now >= target:
            target += timedelta(days=1)

        await asyncio.sleep((target - now).total_seconds())

        try:
            async def work(db: DbAdapters):
                # ожидается, что адаптер вернёт список/итерируемое пользователей
                # (если у тебя там select -> execute, пусть возвращает list[User])
                return await db.users.new_users_last_24h()

            users = await db_call(work)

            names: list[str] = []
            for u in users:
                if getattr(u, "username", None):
                    uname = u.username
                    names.append(f"@{uname}" if not uname.startswith("@") else uname)
                else:
                    names.append(f"(no_username:{u.tg_user_id})")

            text = "Новые пользователи за последние 24 часа:\n" + ("\n".join(names) if names else "(нет)")
            await app.bot.send_message(
                chat_id=adminTgId,
                text=text,
                disable_web_page_preview=True,
            )
        except Exception:
            Logger.exception("daily_report_task failed")
            await asyncio.sleep(5)