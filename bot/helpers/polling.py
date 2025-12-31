import asyncio, time

from common.logger import Logger
from common.adapters import DbAdapters
from common.db import db_call
from telegram.ext import (
    Application,
)

from bot.utils import html_pre


POLL_INTERVAL_SEC = 2
POLL_TIMEOUT_SEC = 120


async def _poll_task_until_done(app: Application, chat_id: int, task_id: str, kind: str) -> None:
    deadline = time.monotonic() + POLL_TIMEOUT_SEC

    while True:
        if time.monotonic() >= deadline:
            Logger.error("Task poll timeout: task_id=%s kind=%s chat_id=%s", task_id, kind, chat_id)
            await app.bot.send_message(chat_id=chat_id, text="❌ Таймаут. Попробуй ещё раз.")
            return

        async def work(db: DbAdapters):
            t = await db.tasks.get(task_id)
            if not t:
                return ("FAILED", {"error": "task_not_found"}, "task_not_found")
            payload = t.payload or {}
            return (t.status, payload.get("result"), t.last_error)

        status, result, last_error = await db_call(work)

        if status in ("NEW", "RESERVED", "RUNNING"):
            await asyncio.sleep(POLL_INTERVAL_SEC)
            continue

        if status == "DONE":
            if kind == "PROVISION":
                cfg = None
                if isinstance(result, dict):
                    cfg = result.get("config") or result.get("config_uri") or result.get("uri")

                if not cfg:
                    Logger.error("DONE without config: task_id=%s kind=%s result=%r", task_id, kind, result)
                    await app.bot.send_message(chat_id=chat_id, text="✅ Готово, но конфиг не найден.")
                    return

                await app.bot.send_message(
                    chat_id=chat_id,
                    text=html_pre(cfg),
                    parse_mode="HTML",
                    disable_web_page_preview=True,
                )
                return

            await app.bot.send_message(chat_id=chat_id, text="✅ Готово.")
            return

        # FAILED / other terminal states
        err = None
        if isinstance(result, dict):
            err = result.get("error")
        if not err and last_error:
            err = last_error

        msg = "❌ Не удалось выполнить операцию."
        if err:
            msg += f"\nПричина: {err}"
        await app.bot.send_message(chat_id=chat_id, text=msg)
        return

def start_polling_async(app: Application, chat_id: int, task_id: str, kind: str) -> None:
    asyncio.create_task(_poll_task_until_done(app, chat_id, str(task_id), kind))
