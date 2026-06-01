"""
Команды для блога и накоплений.
"""
import logging
from aiogram import Dispatcher
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton

from tools.blog_tracker import (
    CONTENT_STRATEGY, SavingsTracker, generate_content_idea, SHOOTING_REMINDERS
)

logger = logging.getLogger(__name__)


def register_blog_commands(dp: Dispatcher):
    dp.message.register(cmd_blog, Command("blog"))
    dp.message.register(cmd_content, Command("content"))
    dp.message.register(cmd_idea, Command("idea"))
    dp.message.register(cmd_savings, Command("savings"))
    dp.message.register(cmd_add_savings, Command("add"))
    dp.callback_query.register(cb_get_idea, lambda c: c.data == "get_idea")
    dp.callback_query.register(cb_content_format, lambda c: c.data and c.data.startswith("format:"))


async def cmd_blog(message: Message, db):
    user_id = message.from_user.id

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💡 Дай идею для рилса", callback_data="get_idea")],
        [InlineKeyboardButton(text="📅 Контент-план на неделю", callback_data="format:weekly")],
        [InlineKeyboardButton(text="🤝 Советы по коллабам", callback_data="format:collab")],
        [InlineKeyboardButton(text="📊 Что снимать под бренды", callback_data="format:brands")],
    ])

    await message.answer(
        "📸 *Твой блог-центр*\n\n"
        "Аккаунт: @n1g1za\n"
        "Цель: коллабы с брендами (косметика, одежда, рестораны)\n"
        "Сейчас: 394 подписчика, 206k просмотров/мес\n\n"
        "Что делаем?",
        parse_mode="Markdown",
        reply_markup=kb
    )


async def cmd_content(message: Message, db):
    """Контент-план на неделю."""
    plan = CONTENT_STRATEGY["weekly_plan"]
    text = "📅 *Контент-план на неделю:*\n\n"

    day_icons = {
        "Понедельник": "1️⃣",
        "Вторник": "2️⃣",
        "Среда": "3️⃣",
        "Четверг": "4️⃣",
        "Пятница": "5️⃣",
        "Суббота": "6️⃣",
        "Воскресенье": "7️⃣"
    }

    for day, info in plan.items():
        icon = day_icons.get(day, "•")
        fmt = CONTENT_STRATEGY["formats"].get(info["type"], {})
        text += f"{icon} *{day}*\n"
        text += f"   {fmt.get('name', '')}: {info['theme']}\n\n"

    text += "💡 Нажми /idea для конкретной идеи на сегодня"
    await message.answer(text, parse_mode="Markdown")


async def cmd_idea(message: Message, db):
    """Генерирует идею для контента."""
    await message.answer("💭 Придумываю идею...")

    # Берём контекст из сообщения если есть
    parts = message.text.split(maxsplit=1)
    context = parts[1] if len(parts) > 1 else ""

    idea = await generate_content_idea(context)

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Другая идея", callback_data="get_idea")],
    ])
    await message.answer(f"💡 *Идея для рилса:*\n\n{idea}", parse_mode="Markdown", reply_markup=kb)


async def cmd_savings(message: Message, db):
    """Показывает статус накоплений."""
    user_id = message.from_user.id
    tracker = SavingsTracker(db)
    data = tracker.get_goal(user_id)

    if data["goal"] == 500000 and data["current"] == 0:
        # Первый раз — инициализируем
        tracker.set_goal(user_id, 500000)
        await message.answer(
            "💰 *Цель: накопить 500 000 ₽ на квартиру*\n\n"
            "Настроила цель! Теперь:\n"
            "• /add 5000 — добавить сумму\n"
            "• /savings — посмотреть прогресс\n\n"
            "Сколько планируешь откладывать в месяц?\n"
            "Напиши: *откладываю X рублей в месяц*",
            parse_mode="Markdown"
        )
    else:
        text = tracker.get_progress_text(user_id)
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="➕ Добавить накопления", callback_data="savings:add")],
        ])
        await message.answer(text, parse_mode="Markdown", reply_markup=kb)


async def cmd_add_savings(message: Message, db):
    """Добавляет сумму к накоплениям. /add 5000"""
    user_id = message.from_user.id
    parts = message.text.split()

    if len(parts) < 2:
        await message.answer(
            "Напиши сумму: */add 5000*",
            parse_mode="Markdown"
        )
        return

    try:
        amount = int(parts[1].replace(" ", "").replace(",", ""))
    except ValueError:
        await message.answer("Не поняла сумму. Пример: /add 5000")
        return

    tracker = SavingsTracker(db)
    new_total = tracker.add_savings(user_id, amount)
    data = tracker.get_goal(user_id)
    goal = data["goal"]
    percent = round(new_total / goal * 100, 1) if goal > 0 else 0

    await message.answer(
        f"✅ Добавила *{amount:,} ₽*!\n\n"
        f"Итого: *{new_total:,} ₽* из {goal:,} ₽ ({percent}%)\n\n"
        f"{'🎉 Ты молодец!' if amount >= 10000 else '💪 Каждая копейка считается!'}",
        parse_mode="Markdown"
    )


# Callbacks
async def cb_get_idea(callback, db):
    await callback.message.edit_text("💭 Придумываю идею...")
    idea = await generate_content_idea()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Другая идея", callback_data="get_idea")],
    ])
    await callback.message.edit_text(f"💡 *Идея для рилса:*\n\n{idea}", parse_mode="Markdown", reply_markup=kb)


async def cb_content_format(callback, db):
    fmt_type = callback.data.split(":")[1]

    if fmt_type == "weekly":
        plan = CONTENT_STRATEGY["weekly_plan"]
        text = "📅 *Контент-план:*\n\n"
        days_short = {"Понедельник": "Пн", "Вторник": "Вт", "Среда": "Ср",
                      "Четверг": "Чт", "Пятница": "Пт", "Суббота": "Сб", "Воскресенье": "Вс"}
        for day, info in plan.items():
            fmt = CONTENT_STRATEGY["formats"].get(info["type"], {})
            text += f"*{days_short[day]}* — {fmt.get('name', '')}\n   {info['theme']}\n\n"

    elif fmt_type == "collab":
        tips = CONTENT_STRATEGY["collab_tips"]
        text = "🤝 *Как получить коллаб с брендом:*\n\n"
        for i, tip in enumerate(tips, 1):
            text += f"{i}. {tip}\n\n"
        text += "\n💡 У тебя 206k просмотров — это уже интересно микро-брендам!"

    elif fmt_type == "brands":
        text = "🏷 *Контент под бренды:*\n\n"
        fmt = CONTENT_STRATEGY["formats"]["brand_bait"]
        text += f"Частота: {fmt['frequency']}\n\n"
        text += "Примеры:\n"
        for ex in fmt["examples"]:
            text += f"• {ex}\n"
        text += f"\n*Почему это работает:* {fmt['why']}\n\n"
        text += "Кафе и рестораны Уфы — особенно охотно делают коллабы с местными!"

    else:
        text = "Неизвестный формат"

    await callback.message.edit_text(text, parse_mode="Markdown")
    await callback.answer()
