# bot_lp.py — надёжный long polling запуск
import os
import logging
from telegram.ext import Application, CommandHandler

# Ваш токен. Вы просили подставлять заранее.
TOKEN = "8376017439:AAHTSrcMwv9296mbX9rYybhx--azGT79ji4"

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

async def ping(update, context):
    await update.message.reply_text("pong")

def main():
    application = Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler("ping", ping))
    # ВАЖНО: запуск именно polling, без вебхуков
    application.run_polling(
        allowed_updates=None,
        drop_pending_updates=True,  # чтобы не тащить хвост старых апдейтов
        stop_signals=None,          # корректное завершение в Windows
        close_loop=False,
    )

if __name__ == "__main__":
    main()