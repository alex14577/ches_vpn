from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from bot.actions import settings

def text() -> str:
    return (
        "VPN готов к работе\n"
        "Доступно до 5 устройств"
    )

def keyboard(tg_user_id) -> InlineKeyboardMarkup:
    rows = [
            [InlineKeyboardButton(            "✅ Подключение", callback_data="connect")],
        ]
    
    if tg_user_id in settings.ADMIN_TG_ID:
        rows.append(
            [InlineKeyboardButton("📣 Сделать рассылку", callback_data="admin_broadcast")]
        )
    else:
        rows.insert(
            2,
            [InlineKeyboardButton("💬 Обратная связь", callback_data="fb_user_reply")],
        )
    return InlineKeyboardMarkup(rows)
