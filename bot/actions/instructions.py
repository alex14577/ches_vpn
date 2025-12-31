from telegram.ext import (
    ContextTypes,
)

 
ANDROID_URL = "https://play.google.com/store/apps/details?id=dev.hexasoftware.v2box&hl=ru"
IOS_URL = "https://apps.apple.com/ru/app/v2box-v2ray-client/id6446814690"

INSTRUCTION_HTML = (
    "📖 <b>Инструкция по подключению</b>\n\n"
    "1) Установи приложение <b>V2Box</b>:\n"
    f"• Android: <a href=\"{ANDROID_URL}\">Google Play</a>\n"
    f"• iOS: <a href=\"{IOS_URL}\">App Store</a>\n\n"
    "2) В этом боте нажми кнопку <b>«Получить конфиг»</b>.\n"
    "3) Скопируй конфиг в буфер обмена.\n"
    "4) Открой V2Box и перейди во вкладку <b>«Конфигурации»</b>.\n"
    "5) Нажми <b>«+»</b>.\n"
    "6) Выбери <b>«Импортировать V2Ray URI из буфера обмена»</b>.\n\n"
)

async def common(chat_id, context: ContextTypes.DEFAULT_TYPE):
    await context.application.bot.send_message(
        chat_id=chat_id,
        text=INSTRUCTION_HTML,
        parse_mode="HTML",
        disable_web_page_preview=True,
    )
    return
    