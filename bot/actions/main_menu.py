
from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)

def show() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("📦 Попробовать бесплатно", callback_data="try_free")],
            [InlineKeyboardButton(           "📖 Инструкция", callback_data="instruction")],
        ]
    )

