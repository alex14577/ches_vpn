import asyncio

from telegram import Update
from telegram.ext import ContextTypes
from telegram.error import RetryAfter

from bot.actions import settings
from common import db
from common.logger import Logger

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return

    if context.user_data.pop("awaiting_broadcast", None):
        await update.message.reply_text("Ок, рассылка отменена.")


async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None or update.message.from_user is None:
        return

    tg_user_id = update.message.from_user.id

    # не админ → игнор
    if tg_user_id not in settings.ADMIN_TG_ID:
        return

    # не ждём рассылку → игнор
    if not context.user_data.get("awaiting_broadcast"):
        return

    # ответы на служебные сообщения бота не считаем рассылкой
    if update.message.reply_to_message:
        return

    text = update.message.text
    if not text:
        await update.message.reply_text("Можно рассылать только текст.")
        return

    context.user_data.pop("awaiting_broadcast", None)

    users = await db.db_call(lambda db: db.users.all())
    user_ids: list[int] = [u.tg_user_id for u in users]
    ok = 0
    fail = 0

    await update.message.reply_text(
        f"Начинаю рассылку по {len(users)} пользователям…"
    )

    SEM_LIMIT = 20  # 10–30 безопасно

    sem = asyncio.Semaphore(SEM_LIMIT)

    ok = 0
    fail = 0
    lock = asyncio.Lock()  # защита счётчиков

    async def send(uid: int):
        nonlocal ok, fail
        async with sem:
            retries = 0
            while True:
                try:
                    await context.bot.send_message(uid, text)
                    async with lock:
                        ok += 1
                    break
                except RetryAfter as e:
                    retries += 1
                    if retries >= 3:
                        async with lock:
                            fail += 1
                        break
                    await asyncio.sleep(e.retry_after + 1)
                    continue
                except Exception as e:
                    Logger.error("Error while sending broadcast message to \"%s\": \"%s\"", uid, e)
                    async with lock:
                        fail += 1
                    break
                finally:
                    await asyncio.sleep(0.03)  # анти-флуд

    tasks = [asyncio.create_task(send(uid)) for uid in user_ids]
    await asyncio.gather(*tasks)

    await update.message.reply_text(
        f"Готово ✅\nУспешно: {ok}\nОшибок: {fail}"
    )
