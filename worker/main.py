# worker/main.py
from __future__ import annotations

import time
import asyncio
from datetime import datetime, timezone

from common.adapters import DbAdapters
from common.models import User, Task
from common.xui_client.registry import Manager
from common.db import db_call
from common.logger import Logger, Level

SLEEP_NO_TASK_SEC = 1.0


async def provision_inbound_user(user: User):
    manager: Manager = Manager()
    await manager.syncUser(user)

    return 
 
async def main_loop():
    Logger.info("Worker started at %s", datetime.now(timezone.utc).isoformat())
    while True:
        nextTask: Task = None
        try:
            nextTask = await db_call(lambda db: db.tasks.get_and_mark_running())

            if not nextTask:
                time.sleep(SLEEP_NO_TASK_SEC)
                continue

            Logger.info("Picked task: type=\"%s\" paiload=%s",
                     nextTask.type,
                     nextTask.payload)

            if nextTask.type != "add":
                raise RuntimeError(f"unsupported task type: {nextTask.type}")
            
            userTgId = nextTask.payload.get("user_tg_id")

            user = await db_call(lambda db: db.users.byTgId(userTgId))

            await provision_inbound_user(user=user)

            await db_call(lambda db: db.tasks.mark_done(nextTask.id))
            Logger.info("Task DONE: id=%s", nextTask.id)

        except Exception as e:
            Logger.exception("Worker error: %s", e)
            if nextTask:
                try:
                    async def mark_failed(db: DbAdapters):
                        await db.tasks.mark_failed(nextTask.id, error=str(e))
                    await db_call(mark_failed)
                except Exception:
                    Logger.exception("Failed to mark task FAILED: id=%s", nextTask.id)

            time.sleep(0.5)


if __name__ == "__main__":
    Logger.configure("worker", Level.DEBUG)
    Logger.silence(("httpcore.http11"), level=Level.WARNING)
    asyncio.run(main_loop())
