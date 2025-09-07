import asyncio
from telegram import Bot
from telegram.request import HTTPXRequest

TOKEN = "8376017439:AAHTSrcMwv9296mbX9rYybhx--azGT79ji4"

async def main():
    # Совместимо с PTB 20.7 — без http2/trust_env
    request = HTTPXRequest(
        connect_timeout=20.0,
        read_timeout=40.0,
        write_timeout=40.0,
        pool_timeout=20.0,
        # proxy=None  # при необходимости сюда можно подставить http(s) прокси
    )
    bot = Bot(TOKEN, request=request)
    await bot.delete_webhook(drop_pending_updates=True)
    me = await bot.get_me()
    print("Webhook удалён. Бот:", me.username)

if __name__ == "__main__":
    asyncio.run(main())