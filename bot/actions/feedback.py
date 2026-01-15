import re

from telegram import (
    ForceReply,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
)
from telegram.ext import ContextTypes

from bot.actions import settings
from common.logger import Logger

ADMIN_REPLY_CALLBACK_PREFIX = "fb_admin_reply:"
USER_REPLY_CALLBACK = "fb_user_reply"
PROMPT_PREFIX = "[fb]"
LOG_PREFIX = "[fb]"

USER_TAG_RE = re.compile(r"\[#u(\d+)\]")
USER_HEADER_RE = re.compile(r"\[#u(\d+)\](?:\s+@([A-Za-z0-9_]{1,32}))?")


def _get_admin_ids() -> list[int]:
    admin_ids = settings.ADMIN_TG_ID
    if isinstance(admin_ids, list):
        return [int(admin_id) for admin_id in admin_ids]
    return [int(admin_ids)]


def _user_header(user_id: int, username: str | None) -> str:
    name = f" @{username}" if username else ""
    return f"[#u{user_id}]{name}"


def _admin_reply_keyboard(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("💬 Ответить", callback_data=f"{ADMIN_REPLY_CALLBACK_PREFIX}{user_id}")]]
    )


def _user_reply_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("💬 Ответить", callback_data=USER_REPLY_CALLBACK)]]
    )


def _media_caption(header: str | None, caption: str | None) -> str | None:
    if header and caption:
        return f"{header}\n\n{caption}"
    if header:
        return header
    return caption


def _is_media_message(message) -> bool:
    return any(
        [
            message.photo,
            message.document,
            message.video,
            message.audio,
            message.voice,
            message.animation,
        ]
    )


async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or query.from_user is None:
        return

    data = (query.data or "").strip()
    if not data.startswith("fb_"):
        return

    await query.answer()

    admin_ids = _get_admin_ids()

    if data.startswith(ADMIN_REPLY_CALLBACK_PREFIX):
        if query.from_user.id not in admin_ids:
            return

        user_id_str = data[len(ADMIN_REPLY_CALLBACK_PREFIX):]
        if not user_id_str.isdigit():
            return

        user_id = int(user_id_str)
        username = None
        source_text = ""
        if query.message:
            source_text = query.message.text or query.message.caption or ""
        header_match = USER_HEADER_RE.search(source_text)
        if header_match:
            username = header_match.group(2)
        username_part = f" @{username}" if username else ""
        text = (
            f"{PROMPT_PREFIX} ✍️ Ответ пользователю [#u{user_id}]{username_part}.\n"
            "Напишите сообщение ответом на это сообщение."
        )
        await context.bot.send_message(
            chat_id=query.from_user.id,
            text=text,
            reply_markup=ForceReply(selective=True),
        )
        return

    if data == USER_REPLY_CALLBACK:
        text = (
            f"{PROMPT_PREFIX} ✍️ Ответ поддержке. Напишите сообщение ответом на это сообщение."
        )
        await context.bot.send_message(
            chat_id=query.from_user.id,
            text=text,
            reply_markup=ForceReply(selective=True),
        )


async def _send_with_optional_media(
    context: ContextTypes.DEFAULT_TYPE,
    message,
    chat_id: int,
    header: str | None,
    reply_markup: InlineKeyboardMarkup | None,
) -> None:
    if message.text:
        text = f"{header}\n\n{message.text}" if header else message.text
        try:
            await context.bot.send_message(
                chat_id=chat_id,
                text=text,
                reply_markup=reply_markup,
            )
            Logger.info("%s sent text to chat_id=%s", LOG_PREFIX, chat_id)
        except Exception:
            Logger.exception("%s failed to send text to chat_id=%s", LOG_PREFIX, chat_id)
        return

    if _is_media_message(message):
        caption = _media_caption(header, message.caption)
        if message.photo:
            photo = message.photo[-1].file_id
            try:
                await context.bot.send_photo(
                    chat_id=chat_id,
                    photo=photo,
                    caption=caption,
                    reply_markup=reply_markup,
                )
                Logger.info("%s sent photo to chat_id=%s", LOG_PREFIX, chat_id)
            except Exception:
                Logger.exception("%s failed to send photo to chat_id=%s", LOG_PREFIX, chat_id)
            return
        if message.document:
            try:
                await context.bot.send_document(
                    chat_id=chat_id,
                    document=message.document.file_id,
                    caption=caption,
                    reply_markup=reply_markup,
                )
                Logger.info("%s sent document to chat_id=%s", LOG_PREFIX, chat_id)
            except Exception:
                Logger.exception("%s failed to send document to chat_id=%s", LOG_PREFIX, chat_id)
            return
        if message.video:
            try:
                await context.bot.send_video(
                    chat_id=chat_id,
                    video=message.video.file_id,
                    caption=caption,
                    reply_markup=reply_markup,
                )
                Logger.info("%s sent video to chat_id=%s", LOG_PREFIX, chat_id)
            except Exception:
                Logger.exception("%s failed to send video to chat_id=%s", LOG_PREFIX, chat_id)
            return
        if message.audio:
            try:
                await context.bot.send_audio(
                    chat_id=chat_id,
                    audio=message.audio.file_id,
                    caption=caption,
                    reply_markup=reply_markup,
                )
                Logger.info("%s sent audio to chat_id=%s", LOG_PREFIX, chat_id)
            except Exception:
                Logger.exception("%s failed to send audio to chat_id=%s", LOG_PREFIX, chat_id)
            return
        if message.voice:
            try:
                await context.bot.send_voice(
                    chat_id=chat_id,
                    voice=message.voice.file_id,
                    caption=caption,
                    reply_markup=reply_markup,
                )
                Logger.info("%s sent voice to chat_id=%s", LOG_PREFIX, chat_id)
            except Exception:
                Logger.exception("%s failed to send voice to chat_id=%s", LOG_PREFIX, chat_id)
            return
        if message.animation:
            try:
                await context.bot.send_animation(
                    chat_id=chat_id,
                    animation=message.animation.file_id,
                    caption=caption,
                    reply_markup=reply_markup,
                )
                Logger.info("%s sent animation to chat_id=%s", LOG_PREFIX, chat_id)
            except Exception:
                Logger.exception("%s failed to send animation to chat_id=%s", LOG_PREFIX, chat_id)
            return
        return

    if header:
        try:
            await context.bot.send_message(
                chat_id=chat_id,
                text=header,
                reply_markup=reply_markup,
            )
            Logger.info("%s sent header to chat_id=%s", LOG_PREFIX, chat_id)
        except Exception:
            Logger.exception("%s failed to send header to chat_id=%s", LOG_PREFIX, chat_id)


async def _handle_admin_reply(
    message,
    context: ContextTypes.DEFAULT_TYPE,
    admin_id: int,
) -> None:
    reply_to = message.reply_to_message
    if reply_to is None or reply_to.from_user is None:
        return

    if not reply_to.from_user.is_bot:
        return

    prompt_text = reply_to.text or reply_to.caption or ""
    if PROMPT_PREFIX not in prompt_text:
        return
    match = USER_TAG_RE.search(prompt_text)
    if match is None:
        return

    user_id = int(match.group(1))

    Logger.info("%s admin_reply admin_id=%s user_id=%s", LOG_PREFIX, admin_id, user_id)

    await _send_with_optional_media(
        context=context,
        message=message,
        chat_id=user_id,
        header=None,
        reply_markup=_user_reply_keyboard(),
    )

    await _send_with_optional_media(
        context=context,
        message=message,
        chat_id=admin_id,
        header=f"✅ Отправлено пользователю [#u{user_id}]",
        reply_markup=None,
    )


async def _handle_user_message(
    message,
    context: ContextTypes.DEFAULT_TYPE,
    admin_id: int,
) -> None:
    user = message.from_user
    header = _user_header(user.id, user.username)

    Logger.info(
        "%s user_message user_id=%s username=%s",
        LOG_PREFIX,
        user.id,
        user.username or "",
    )

    await _send_with_optional_media(
        context=context,
        message=message,
        chat_id=admin_id,
        header=header,
        reply_markup=_admin_reply_keyboard(user.id),
    )


async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message
    if message is None or message.from_user is None:
        return

    if message.from_user.is_bot:
        return

    admin_ids = _get_admin_ids()
    if not admin_ids:
        Logger.error("%s no_admin_ids_configured", LOG_PREFIX)
        return

    if message.from_user.id in admin_ids:
        await _handle_admin_reply(message, context, message.from_user.id)
        return

    for admin_id in admin_ids:
        await _handle_user_message(message, context, admin_id)
