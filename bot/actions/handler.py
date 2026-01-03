
from telegram import (
    MaybeInaccessibleMessage,
    CallbackQuery,
    Update,
)
from telegram.ext import (
    ContextTypes,
)

from bot.helpers import helpers
from bot.actions import try_free, main_menu, instructions, say_thanks
from common.xui_client.registry import Manager

async def handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query: CallbackQuery | None = update.callback_query
    if query is None or query.from_user is None:
        return
    
    serversManager: Manager = context.bot_data["servers_manager"]

    await query.answer()

    message: MaybeInaccessibleMessage | None = query.message
    tg_user_id = query.from_user.id
    username = query.from_user.username
    chat_id = message.chat.id if message is not None else tg_user_id
    action = query.data or ""

    if action == "instruction":
        await instructions.common(chat_id=chat_id, context=context)
    if action == "say_thanks":
        await say_thanks.common(chat_id=chat_id, context=context)

    elif action == "try_free":
        sub_url = await try_free.try_free(tg_user_id, username, serversManager)
        text = ("📋 <b>Ваша ссылка для подписки</b>\n\n"
                f"<code>{sub_url}</code>\n\n"
                "Нажмите на строку, чтобы скопировать.")
        if message is not None:
            await message.reply_text(text=text,
                                     parse_mode="HTML")
        else:
            await context.bot.send_message(chat_id=chat_id, text=text, parse_mode="HTML")

    await helpers.safe_edit(query, reply_markup=main_menu.show())
