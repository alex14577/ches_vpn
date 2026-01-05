from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅️ Назад", callback_data="back_to_main")]
    ])