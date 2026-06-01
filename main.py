import asyncio, logging, os
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from memory.database import Database
from handlers.commands import register_commands
from handlers.messages import register_messages
from handlers.files import register_files
from handlers.blog import register_blog_commands
from handlers.finance import register_finance_commands
from agents.reminder_checker import start_reminder_checker
from agents.blog_scheduler import schedule_blog_reminders

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s — %(message)s")
logger = logging.getLogger(__name__)
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")


async def main():
    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN не задан!")
    db = Database()
    db.init()
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())
    scheduler = AsyncIOScheduler(timezone="UTC")
    dp["db"] = db
    dp["scheduler"] = scheduler

    # Порядок важен: сначала специфичные команды, потом общий обработчик текста
    register_commands(dp)
    register_blog_commands(dp)
    register_finance_commands(dp)
    register_messages(dp)   # ПОСЛЕДНИМ — ловит всё остальное
    register_files(dp)

    scheduler.start()
    await start_reminder_checker(bot, db, scheduler)
    await schedule_blog_reminders(bot, db, scheduler)

    logger.info("🤖 Гений-бот запущен!")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
