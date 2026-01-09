
from telegram import (
    CallbackQuery,
    Update,
)
from telegram.ext import (
    ContextTypes,
)

from bot.helpers import helpers
from bot.actions import settings 
from bot.actions import try_free, main_menu, instructions, say_thanks, return_main_menu
from common.xui_client.registry import Manager
from common.logger import Logger

from telegram.constants import ParseMode

HTML = ParseMode.HTML


async def _render_main_menu(query: CallbackQuery, tg_user_id) -> None:
    await helpers.safe_edit(
        query,
        text=main_menu.text(),
        reply_markup=main_menu.keyboard(tg_user_id),
        parse_mode=HTML,
    )


async def handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or query.from_user is None:
        return

    await query.answer()

    action = (query.data or "").strip()

    tg_user_id = query.from_user.id
    username = query.from_user.username
    servers_manager: Manager = context.bot_data["servers_manager"]

    match action:
        case "instruction":
            await helpers.safe_edit(
                query,
                text=instructions.text(),
                reply_markup=return_main_menu.keyboard(),
                parse_mode=HTML,
            )
            return

        case "say_thanks":
            await helpers.safe_edit(
                query,
                text=say_thanks.text(),
                reply_markup=return_main_menu.keyboard(),
                parse_mode=HTML,
            )
            return

        case "try_free":
            sub_url = await try_free.try_free(
                tg_user_id, username, servers_manager
            )
            text = (
                "📋 <b>Ваша ссылка для подписки</b>\n\n"
                f"<code>{sub_url}</code>\n\n"
                "Нажмите на строку, чтобы скопировать ссылку."
            )

            await helpers.safe_edit(
                query,
                text=text,
                reply_markup=return_main_menu.keyboard(),
                parse_mode=HTML,
                disable_web_page_preview=True,
            )
            return

        case "back_to_main":
            await _render_main_menu(query, tg_user_id)
            return
        
        case "admin_broadcast":
            if tg_user_id not in settings.ADMIN_TG_ID:
                Logger.error("User \"%s\" tried to get admin rights", username or tg_user_id)
                return

            context.user_data["awaiting_broadcast"] = True

            await helpers.safe_edit(
                query,
                text=(
                    "📣 <b>Рассылка</b>\n\n"
                    "Отправьте текст сообщения, которое нужно разослать.\n"
                    "Или напишите /cancel для отмены."
                ),
                reply_markup=return_main_menu.keyboard(),
                parse_mode=HTML,
            )
            return


        case _:
            await _render_main_menu(query, tg_user_id)
            return
