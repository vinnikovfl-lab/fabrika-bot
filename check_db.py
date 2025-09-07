import asyncio
import nest_asyncio
from db import init_db

async def main():
    print("🔧 Проверка/инициализация базы...")
    await init_db()
    print("✅ База готова!")

if __name__ == "__main__":
    # ✅ Поддержка VSCode / Jupyter
    nest_asyncio.apply()

    try:
        asyncio.run(main())
    except RuntimeError as e:
        if "already running" in str(e):
            print("⚠️ Event loop уже работает — подключаемся к нему...")
            loop = asyncio.get_event_loop()
            loop.create_task(main())
            loop.run_forever()
        else:
            raise