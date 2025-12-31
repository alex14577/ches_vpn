from typing import Optional

from telegram.error import BadRequest

from telegram import InlineKeyboardMarkup, CallbackQuery


async def safe_edit(
    q: CallbackQuery,
    *,
    text: Optional[str] = None,
    reply_markup: Optional[InlineKeyboardMarkup] = None,
) -> None:
    try:
        if text is not None:
            await q.edit_message_text(text=text, reply_markup=reply_markup)
        else:
            await q.edit_message_reply_markup(reply_markup=reply_markup)
    except BadRequest as e:
        if "Message is not modified" in str(e):
            return
        raise
    
    