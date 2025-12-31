# bot/main.py
from __future__ import annotations

import asyncio
import os
import time

from telegram import (
    BotCommand,
    Update,
)
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)

from common.db import db_call
from common.adapters import DbAdapters
from bot.reports import daily_report_task
from common.logger import Logger, Level
from bot.utils import parse_ref_payload
from bot.actions.handler import handler
from bot.actions import main_menu

BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
ADMIN_TG_ID = 572200030
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is empty. Export BOT_TOKEN env var.")


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    tg_user_id = update.effective_user.id  
    tg_user = update.effective_user
    if not tg_user or not update.message:
        return

    args = context.args
    payload = args[0] if args else None

    referrer_tg_id = parse_ref_payload(payload) if payload else None

    if referrer_tg_id == tg_user_id:
        referrer_tg_id = None

    async def work(db: DbAdapters):
        return await db.users.getOrCreate(tg_user.id, tg_user.username, refer_id=referrer_tg_id)

    await db_call(work)
    Logger.info("User start: tg_user_id=%s username=%s", tg_user.id, tg_user.username)
    
    await update.message.reply_text(
        "👋 Добро пожаловать в Ches VPN\n\n"
        "В данный момент проект только начинает развиваться, поэтому предоставляем бесплатный ддоступ за рекомендации друзьям и знакомым.\n\n"
        "Нажмите \"Получить бесплатно\", чтобы получить ссылку, а  инструкции Вы найдёте всю нужную информацию, как установить приложения на все устройства\n\n"
        "Выбери действие ниже 👇",
        reply_markup=main_menu.show(),
    )

async def cmd_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await cmd_start(update, context)



async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    Logger.exception("Unhandled error: %s", context.error)


def build_app() -> Application:
    Logger.configure("bot", level=Level.DEBUG)
    Logger.silence("telegram", "telegram.ext", "httpx", level=Level.WARNING)

    app = Application.builder().token(BOT_TOKEN).build()

    async def _post_init(application: Application) -> None:
        await application.bot.set_my_commands([
            BotCommand("menu", "Открыть меню"),
        ])
        asyncio.create_task(daily_report_task(application, adminTgId=ADMIN_TG_ID))

    app.post_init = _post_init

    app.add_error_handler(on_error)
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("menu", cmd_menu))
    app.add_handler(CallbackQueryHandler(handler))
    return app


def main() -> None:
    app = build_app()
    Logger.info("Bot started")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
