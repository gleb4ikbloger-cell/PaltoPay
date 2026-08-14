import os
import asyncio

from aiogram import Bot, Dispatcher
from aiogram.types import Message
from aiogram.filters import CommandStart


BOT_TOKEN = os.getenv("BOT_TOKEN")

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


async def main():
    print("PaltoPay запущен!")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
