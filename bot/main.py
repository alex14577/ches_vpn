# bot/main.py
from __future__ import annotations

import asyncio
import os

from telegram import (
    BotCommand,
    Update,
)
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters
)

from common.db import db_call, init_db_engine
from bot.reports import daily_report_task
from common.logger import Logger, Level
from common.xui_client.registry import Manager
from bot.actions.handler import handler
from bot.actions import main_menu
from bot.actions import broadcast_message
from bot.actions import feedback
from bot.actions.settings import TG_BOT_TOKEN, ADMIN_TG_ID

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    tg_user_id = update.effective_user.id  
    tg_user = update.effective_user
    source = context.args[0] if context.args else None

    if not tg_user or not update.message:
        return

    await db_call(lambda db: db.users.getOrCreate(tg_user.id, tg_user.username, refer_id=source))
    Logger.info("User start: tg_user_id=%s username=%s, source=\"%s\"", tg_user.id, tg_user.username, source or "")
    
    await update.message.reply_text(
        text=main_menu.text(),
        reply_markup=main_menu.keyboard(tg_user_id),
        parse_mode="HTML",
    )

async def cmd_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await cmd_start(update, context)

async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    Logger.exception("Unhandled error: %s", context.error)


def build_app() -> Application:
    Logger.configure("bot", level=Level.DEBUG)
    Logger.silence("telegram", "telegram.ext", "httpx", "httpcore.http11", "httpcore.connection", level=Level.WARNING)

    app = Application.builder().token(TG_BOT_TOKEN).build()
    app.bot_data["servers_manager"] = Manager()

    async def _post_init(application: Application) -> None:
        await application.bot.set_my_commands([
            BotCommand("menu", "Открыть меню"),
        ])
        asyncio.create_task(daily_report_task(application, adminTgId=ADMIN_TG_ID))

    app.post_init = _post_init

    app.add_error_handler(on_error)
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("menu", cmd_menu))
    app.add_handler(CallbackQueryHandler(feedback.callback_handler, pattern="^fb_"))
    app.add_handler(CallbackQueryHandler(handler))
    app.add_handler(CommandHandler("cancel", broadcast_message.cancel))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, broadcast_message.message_handler))
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, feedback.message_handler), group=1)
    return app


def main() -> None:
    init_db_engine(
        os.environ["VPN_BOT_DB_USERNAME"],
        os.environ["VPN_BOT_DB_PASSWORD"],
    )
    app = build_app()
    Logger.info("Bot started")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
