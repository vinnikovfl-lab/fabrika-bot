# bot_lp_ip.py — long polling через фиксированный IP + SNI
import logging
from telegram.ext import Application, CommandHandler
from telegram.request import HTTPXRequest

# Ваш токен
TOKEN = "8376017439:AAHTSrcMwv9296mbX9rYybhx--azGT79ji4"

# IP Telegram, который у вас резолвится (по вашим тестам)
TELEGRAM_IP = "149.154.167.220"
API_HOST = "api.telegram.org"
BASE_URL = f"https://{TELEGRAM_IP}/bot"  # заменим хост на IP

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    level=logging.INFO,
)
log = logging.getLogger(__name__)

# Кастомный HTTPXRequest, который подменяет URL на IP и добавляет заголовок Host
class FixedIPRequest(HTTPXRequest):
    async def do_request(self, *args, **kwargs):
        # Подмена URL: https://api.telegram.org/bot -> https://<IP>/bot
        url = kwargs.get("url")
        if isinstance(url, str) and url.startswith(f"https://{API_HOST}/bot"):
            kwargs["url"] = url.replace(f"https://{API_HOST}/bot", BASE_URL)
        # Устанавливаем Host-заголовок для корректного SNI/сертификата
        headers = kwargs.get("headers") or {}
        if "Host" not in {k.title(): v for k, v in headers.items()}:
            headers["Host"] = API_HOST
        kwargs["headers"] = headers
        return await super().do_request(*args, **kwargs)

async def ping(update, context):
    await update.message.reply_text("pong")

def main():
    request = FixedIPRequest(
        connect_timeout=20.0,
        read_timeout=40.0,
        write_timeout=40.0,
        pool_timeout=20.0,
        # proxy=None  # при необходимости можно подставить http(s) прокси
    )
    app = Application.builder().token(TOKEN).request(request).build()
    app.add_handler(CommandHandler("ping", ping))

    app.run_polling(
        allowed_updates=None,
        drop_pending_updates=True,
        stop_signals=None,
        close_loop=False,
    )

if __name__ == "__main__":
    main()