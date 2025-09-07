import asyncio
import nest_asyncio
from db import init_db

async def reset_db():
    await init_db()
    print("✅ Таблицы пересозданы")

if __name__ == "__main__":
    # ✅ Поддержка VSCode / Jupyter
    nest_asyncio.apply()

    try:
        asyncio.run(reset_db())
    except RuntimeError as e:
        if "already running" in str(e):
            print("⚠️ Event loop уже работает — подключаемся к нему...")
            loop = asyncio.get_event_loop()
            loop.create_task(reset_db())
            loop.run_forever()
        else:
            raise