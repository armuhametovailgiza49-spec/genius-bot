import json
import logging
from datetime import datetime, timedelta
from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler

logger = logging.getLogger(__name__)


async def start_reminder_checker(bot: Bot, db, scheduler: AsyncIOScheduler):
    """Запускает проверку напоминаний каждую минуту."""
    scheduler.add_job(
        _check_reminders,
        "interval",
        minutes=1,
        args=[bot, db],
        id="main_reminder_check",
        replace_existing=True
    )
    logger.info("Планировщик напоминаний запущен")


async def _check_reminders(bot: Bot, db):
    try:
        now = datetime.utcnow()
        from_t = (now - timedelta(seconds=30)).isoformat()
        to_t = (now + timedelta(minutes=1, seconds=30)).isoformat()

        events = db.get_events_to_remind(from_t, to_t)
        for event in events:
            await _send_reminder(bot, db, event)
    except Exception as e:
        logger.error(f"Ошибка проверки напоминаний: {e}")


async def _send_reminder(bot: Bot, db, event: dict):
    try:
        user_id = event["user_id"]
        title = event["title"]
        event_time = datetime.fromisoformat(event["event_time"])

        prep_steps = []
        if event.get("prep_steps"):
            try:
                prep_steps = json.loads(event["prep_steps"])
            except Exception:
                pass

        # Форматируем время
        formatted = event_time.strftime("%d.%m.%Y в %H:%M")

        # Строим текст напоминания
        text = f"🔔 Напоминание!\n\n📌 {title}\n📆 {formatted}\n"

        if prep_steps:
            text += "\n✅ Что нужно сделать:\n"
            for step in prep_steps:
                text += f"  • {step}\n"

        text += "\n⏰ Убедись, что успеешь подготовиться!"

        await bot.send_message(user_id, text)
        db.mark_reminded(event["id"])
        logger.info(f"Отправлено напоминание event_id={event['id']} user_id={user_id}")

    except Exception as e:
        logger.error(f"Ошибка отправки напоминания: {e}")
