
from telegram import (
    CallbackQuery,
    Update,
)
from telegram.error import BadRequest
from telegram.ext import (
    ContextTypes,
)

from bot.helpers import helpers
from bot.actions import settings
from bot.actions import choose_plan, main_menu, return_main_menu
from common.logger import Logger

from telegram.constants import ParseMode

HTML = ParseMode.HTML


async def _render_main_menu(query: CallbackQuery, tg_user_id, username: str | None, full_name: str | None = None) -> None:
    text, reply_markup = await main_menu.build_main_view(tg_user_id, username, full_name)
    if query.message and (
        query.message.photo
        or query.message.document
        or query.message.video
        or query.message.animation
    ):
        await query.message.reply_text(
            text=text,
            reply_markup=reply_markup,
            parse_mode=HTML,
        )
        try:
            await query.message.delete()
        except BadRequest:
            pass
        return

    await helpers.safe_edit(
        query,
        text=text,
        reply_markup=reply_markup,
        parse_mode=HTML,
    )


async def handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query: CallbackQuery | None = update.callback_query
    if query is None or query.from_user is None:
        return

    await query.answer()

    action = (query.data or "").strip()

    tg_user_id = query.from_user.id
    username = query.from_user.username
    full_name = " ".join(filter(None, [query.from_user.first_name, query.from_user.last_name])) or None
    match action:
        case "choose_plan":
            await choose_plan.show_plans(query, context)
            return

        case _ if action.startswith("plan:"):
            plan_code = action.split(":", 1)[1]
            await choose_plan.show_plan_details(query, context, tg_user_id, username, plan_code, full_name)
            return

        case _ if action.startswith("payment_sent:"):
            sub_id = action.split(":", 1)[1]
            await choose_plan.notify_payment_sent(query, context, sub_id)
            return

        case "back_to_main":
            await _render_main_menu(query, tg_user_id, username, full_name)
            return

        case "connect_other_device":
            await main_menu.render_other_device(query, tg_user_id, username, full_name)
            return

        case "copy_connect_link":
            link_text, _ = await main_menu.build_other_device_view(tg_user_id, username, full_name)
            if query.message:
                await query.message.reply_text(
                    text=link_text,
                    disable_web_page_preview=True,
                )
            return

        case "refresh_main_menu":
            await _render_main_menu(query, tg_user_id, username, full_name)
            return

        case "faq_main_menu":
            await main_menu.render_faq(query, tg_user_id, username)
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
            await _render_main_menu(query, tg_user_id, username, full_name)
            return
