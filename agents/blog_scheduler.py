"""
Планировщик блог-напоминаний: каждый день напоминает о съёмке.
"""
import logging
from datetime import datetime
import pytz
from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from tools.blog_tracker import CONTENT_STRATEGY, generate_content_idea

logger = logging.getLogger(__name__)

# Время напоминаний (локальное время пользователя)
BLOG_REMINDERS = [
    {"hour": 9,  "minute": 0,  "days": "mon-fri", "type": "morning"},
    {"hour": 13, "minute": 0,  "days": "mon,wed,fri", "type": "midday"},
    {"hour": 19, "minute": 0,  "days": "tue,thu,sat", "type": "evening"},
    {"hour": 21, "minute": 0,  "days": "mon-sun", "type": "post_reminder"},
]

MESSAGES = {
    "morning": [
        "☀️ Доброе утро, Иля! Утренний свет — лучший для съёмки. Есть идея на сегодня?",
        "🌅 Утро! Напомню: регулярность = рост. Что снимем сегодня?",
        "☕ Доброе утро! Пока пьёшь кофе — подумай что снять сегодня для @n1g1za",
    ],
    "midday": [
        "📸 Середина дня — идеальное время для съёмки на улице! Ты уже что-то сняла?",
        "🌤 Дневной свет на улице сейчас самый красивый. Выйди на 15 минут — снимешь материал!",
        "🎬 Напоминаю про контент! Даже 1 короткое видео в день делает разницу.",
    ],
    "evening": [
        "💄 Вечернее время — отлично для образа дня или макияжа! Снимешь что-нибудь?",
        "🌆 Вечерний контент хорошо заходит. Покажи как ты выглядишь сегодня!",
        "✨ Напоминаю про блог! Вечерний образ или лайф — отличный контент.",
    ],
    "post_reminder": [
        "📱 Уже вечер! Ты сегодня выложила что-нибудь? Регулярность — главный секрет роста 🔑",
        "🌙 Не забудь про блог сегодня! Даже сторис считается.",
        "📊 Алгоритм любит регулярность. Выложи хотя бы сторис перед сном!",
    ]
}

import random


async def schedule_blog_reminders(bot: Bot, db, scheduler: AsyncIOScheduler):
    """Находит всех пользователей с включёнными блог-напоминаниями и планирует их."""

    # Ищем пользователей у которых включены блог-напоминания
    # Для простоты — планируем для всех у кого есть blog_reminders=on в профиле
    scheduler.add_job(
        _send_blog_reminders,
        "cron",
        hour=9, minute=0,
        args=[bot, db, "morning"],
        id="blog_morning",
        replace_existing=True
    )
    scheduler.add_job(
        _send_blog_reminders,
        "cron",
        hour=13, minute=0,
        args=[bot, db, "midday"],
        id="blog_midday",
        replace_existing=True
    )
    scheduler.add_job(
        _send_blog_reminders,
        "cron",
        hour=19, minute=0,
        args=[bot, db, "evening"],
        id="blog_evening",
        replace_existing=True
    )
    scheduler.add_job(
        _send_blog_reminders,
        "cron",
        hour=21, minute=0,
        args=[bot, db, "post_reminder"],
        id="blog_post_reminder",
        replace_existing=True
    )

    # Еженедельный контент-план (в воскресенье вечером на следующую неделю)
    scheduler.add_job(
        _send_weekly_plan,
        "cron",
        day_of_week="sun",
        hour=20, minute=0,
        args=[bot, db],
        id="blog_weekly_plan",
        replace_existing=True
    )

    # Ежемесячное напоминание про накопления
    scheduler.add_job(
        _send_savings_reminder,
        "cron",
        day=1, hour=10, minute=0,
        args=[bot, db],
        id="savings_monthly",
        replace_existing=True
    )

    logger.info("Блог-напоминания запланированы")


async def _send_blog_reminders(bot: Bot, db, reminder_type: str):
    """Отправляет напоминание всем пользователям с активными блог-напоминаниями."""
    try:
        # Получаем всех пользователей с blog_reminders=on
        with db.conn() as c:
            rows = c.execute(
                "SELECT DISTINCT user_id FROM profile WHERE key='blog_reminders' AND value='on'"
            ).fetchall()

        messages = MESSAGES.get(reminder_type, MESSAGES["morning"])
        text = random.choice(messages)

        # Раз в неделю добавляем идею для контента
        now = datetime.now()
        if reminder_type == "morning" and now.weekday() in [0, 3]:  # пн, чт
            idea = await generate_content_idea()
            text += f"\n\n💡 *Идея на сегодня:*\n{idea}"

        for row in rows:
            try:
                await bot.send_message(row["user_id"], text, parse_mode="Markdown")
            except Exception as e:
                logger.warning(f"Не удалось отправить блог-напоминание user {row['user_id']}: {e}")

    except Exception as e:
        logger.error(f"Blog reminder error: {e}")


async def _send_weekly_plan(bot: Bot, db):
    """Отправляет контент-план на следующую неделю."""
    try:
        with db.conn() as c:
            rows = c.execute(
                "SELECT DISTINCT user_id FROM profile WHERE key='blog_reminders' AND value='on'"
            ).fetchall()

        plan = CONTENT_STRATEGY["weekly_plan"]
        text = "📅 *Твой план на следующую неделю:*\n\n"
        days_short = {"Понедельник": "Пн", "Вторник": "Вт", "Среда": "Ср",
                      "Четверг": "Чт", "Пятница": "Пт", "Суббота": "Сб", "Воскресенье": "Вс"}
        for day, info in plan.items():
            fmt = CONTENT_STRATEGY["formats"].get(info["type"], {})
            text += f"*{days_short[day]}* — {info['theme']}\n"

        text += "\n/idea — получить конкретную идею\n/blog — открыть блог-центр"

        for row in rows:
            try:
                await bot.send_message(row["user_id"], text, parse_mode="Markdown")
            except Exception as e:
                logger.warning(f"Weekly plan error user {row['user_id']}: {e}")

    except Exception as e:
        logger.error(f"Weekly plan error: {e}")


async def _send_savings_reminder(bot: Bot, db):
    """Ежемесячное напоминание обновить накопления."""
    try:
        from tools.blog_tracker import SavingsTracker

        with db.conn() as c:
            rows = c.execute(
                "SELECT DISTINCT user_id FROM profile WHERE key='savings_goal'"
            ).fetchall()

        for row in rows:
            try:
                tracker = SavingsTracker(db)
                text = tracker.get_progress_text(row["user_id"])
                text = "🗓 *Начало месяца — время обновить накопления!*\n\n" + text
                text += "\n\n/add [сумма] — добавить что накопила за месяц"
                await bot.send_message(row["user_id"], text, parse_mode="Markdown")
            except Exception as e:
                logger.warning(f"Savings reminder error user {row['user_id']}: {e}")

    except Exception as e:
        logger.error(f"Savings monthly reminder error: {e}")
