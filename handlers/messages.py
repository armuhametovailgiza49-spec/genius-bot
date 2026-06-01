import logging
import pytz
from aiogram import Dispatcher
from aiogram.types import Message

from agents.brain import process_message
from tools.event_processor import process_agent_result

logger = logging.getLogger(__name__)

TIMEZONE_ALIASES = {
    "москва": "Europe/Moscow",
    "питер": "Europe/Moscow",
    "санкт-петербург": "Europe/Moscow",
    "киев": "Europe/Kiev",
    "минск": "Europe/Minsk",
    "алматы": "Asia/Almaty",
    "астана": "Asia/Almaty",
    "ташкент": "Asia/Tashkent",
    "amsterdam": "Europe/Amsterdam",
    "амстердам": "Europe/Amsterdam",
    "берлин": "Europe/Berlin",
    "лондон": "Europe/London",
    "нью-йорк": "America/New_York",
}


def register_messages(dp: Dispatcher):
    dp.message.register(handle_text)


async def handle_text(message: Message, db):
    if not message.text:
        return

    user_id = message.from_user.id
    text = message.text.strip()

    # Проверяем онбординг (установка часового пояса)
    settings = db.get_settings(user_id)
    if not settings.get("onboarded"):
        await handle_timezone_setup(message, db, text)
        return

    # Автораспознавание расходов
    expense_triggers = ["потратила", "потратил", "купила", "купил", "заплатила",
                        "заплатил", "расход", "трата", "списалось", "₽", "рублей", "руб"]
    if any(t in text.lower() for t in expense_triggers):
        from tools.finance import parse_expense, check_not_pp, PP_ESSENTIALS
        parsed = await parse_expense(text)
        if parsed and "error" not in parsed and parsed.get("amount", 0) > 0:
            from handlers.finance import _process_expense_text
            await _process_expense_text(message, db, text)
            return

    # Обычная обработка через агента
    await message.bot.send_chat_action(message.chat.id, "typing")

    result = await process_message(user_id, text, db)

    # Обрабатываем команды агента (создаём события, сохраняем память)
    notifications = await process_agent_result(user_id, result, db)

    # Отправляем ответ
    response_text = result["text"]
    if notifications:
        response_text += "\n" + "\n".join(notifications)

    # Telegram ограничение 4096 символов
    if len(response_text) > 4000:
        parts = [response_text[i:i+4000] for i in range(0, len(response_text), 4000)]
        for part in parts:
            await message.answer(part)
    else:
        await message.answer(response_text)


async def handle_timezone_setup(message: Message, db, text: str):
    user_id = message.from_user.id
    text_lower = text.lower().strip()

    # Пробуем распознать часовой пояс
    tz = None

    # Проверяем псевдонимы
    for alias, tz_name in TIMEZONE_ALIASES.items():
        if alias in text_lower:
            tz = tz_name
            break

    # Пробуем напрямую как pytz timezone
    if not tz:
        try:
            pytz.timezone(text)
            tz = text
        except Exception:
            pass

    # Пробуем Europe/City формат
    if not tz and "/" in text:
        try:
            pytz.timezone(text)
            tz = text
        except Exception:
            pass

    if tz:
        db.set_timezone(user_id, tz)
        db.set_onboarded(user_id)
        name = message.from_user.first_name or "друг"
        await message.answer(
            f"✅ Отлично, {name}! Твой часовой пояс: *{tz}*\n\n"
            f"Теперь расскажи мне о себе — я всё запомню:\n"
            f"• Как добираешься до центра?\n"
            f"• Есть ли у тебя привычки перед важными событиями?\n"
            f"• Какие цели или мечты сейчас актуальны?\n\n"
            f"Или просто напиши что хочешь сделать — я помогу!",
            parse_mode="Markdown"
        )
    else:
        await message.answer(
            "Не смогла распознать часовой пояс 😕\n\n"
            "Напиши, например:\n"
            "• *Москва*\n"
            "• *Europe/Moscow*\n"
            "• *Europe/Amsterdam*\n"
            "• *Asia/Almaty*",
            parse_mode="Markdown"
        )
