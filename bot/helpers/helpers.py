from __future__ import annotations

from typing import Optional

from telegram import CallbackQuery, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.error import BadRequest


_NOT_MODIFIED_PATTERNS = (
    "Message is not modified",
    "message is not modified",
    "MESSAGE_NOT_MODIFIED",
)


async def safe_edit(
    q: CallbackQuery,
    *,
    text: Optional[str] = None,
    reply_markup: Optional[InlineKeyboardMarkup] = None,
    parse_mode: Optional[str] = ParseMode.HTML,
    disable_web_page_preview: bool = False,
) -> None:
    """
    Safely edits a callback query message.

    - If `text` is provided -> edit_message_text (optionally with markup & parse_mode)
    - If `text` is None     -> edit_message_reply_markup (only markup update)

    Ignores "message not modified" errors.
    """
    try:
        if text is not None:
            await q.edit_message_text(
                text=text,
                reply_markup=reply_markup,
                parse_mode=parse_mode,
                disable_web_page_preview=disable_web_page_preview,
            )
        else:
            await q.edit_message_reply_markup(reply_markup=reply_markup)
    except BadRequest as e:
        msg = str(e)
        if any(p in msg for p in _NOT_MODIFIED_PATTERNS):
            return
        raise
