import os
import asyncio
from aiohttp import web

from aiogram import Bot, Dispatcher
from aiogram.types import Message
from aiogram.filters import CommandStart


BOT_TOKEN = os.getenv("BOT_TOKEN")
PORT = int(os.getenv("PORT", 10000))

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN не найден")


bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


@dp.message(CommandStart())
async def start_handler(message: Message):
    await message.answer(
        "🔥 Добро пожаловать в PaltoPay!\n\n"
        "💼 Ваш криптовалютный кошелёк скоро будет здесь."
    )


async def health_check(request):
    return web.Response(text="PaltoPay is running!")


async def start_web_server():
    app = web.Application()
    app.router.add_get("/", health_check)

    runner = web.AppRunner(app)
    await runner.setup()

    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()

    print(f"HTTP сервер запущен на порту {PORT}")


async def main():
    print("PaltoPay запускается...")

    await start_web_server()

    print("PaltoPay запущен!")

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
