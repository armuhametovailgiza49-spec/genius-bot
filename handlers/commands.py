import json
import logging
from aiogram import Dispatcher, types
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton

logger = logging.getLogger(__name__)


def register_commands(dp: Dispatcher):
    dp.message.register(cmd_start, Command("start"))
    dp.message.register(cmd_help, Command("help"))
    dp.message.register(cmd_profile, Command("profile"))
    dp.message.register(cmd_list, Command("list"))
    dp.message.register(cmd_roadmap, Command("roadmap"))
    dp.message.register(cmd_forget, Command("forget"))
    dp.message.register(cmd_files, Command("files"))
    dp.callback_query.register(cb_roadmap_done, lambda c: c.data and c.data.startswith("rm_done:"))
    dp.callback_query.register(cb_roadmap_undone, lambda c: c.data and c.data.startswith("rm_undone:"))
    dp.callback_query.register(cb_delete_event, lambda c: c.data and c.data.startswith("del_event:"))


async def cmd_start(message: Message, db):
    user_id = message.from_user.id
    settings = db.get_settings(user_id)
    name = message.from_user.first_name or "друг"

    if not settings.get("onboarded"):
        await message.answer(
            f"Привет, {name}! 👋 Я твой личный гений-помощник.\n\n"
            "Я помню всё о тебе и никогда не забываю. Могу:\n"
            "• 📅 Создавать напоминания с учётом подготовки\n"
            "• 🗺 Строить план к любой мечте\n"
            "• 📚 Читать и понимать файлы (PDF, DOCX, фото)\n"
            "• 🧠 Учиться о тебе с каждым диалогом\n\n"
            "Для начала: в каком ты часовом поясе?\n"
            "Напиши, например: *Europe/Moscow* или *Asia/Almaty* или просто *Москва*"
        )
        db.add_memory(user_id, "fact", f"Имя пользователя: {name}", "system")
    else:
        await message.answer(
            f"Привет снова, {name}! 👋\n\n"
            "Что делаем? Можешь написать в свободной форме:\n"
            "• О событии: «Встреча в пятницу в 18:00»\n"
            "• О мечте: «Хочу научиться рисовать»\n"
            "• Прислать файл для разбора\n\n"
            "/profile — что я знаю о тебе\n"
            "/list — предстоящие события\n"
            "/roadmap — твои планы к мечтам"
        )


async def cmd_help(message: Message):
    await message.answer(
        "📖 *Как со мной работать:*\n\n"
        "*Напоминания:*\n"
        "Просто напиши: «Свидание в субботу в 19:00» — я сам заложу время на подготовку\n\n"
        "*Мечты и планы:*\n"
        "«Хочу открыть кофейню» — получишь детальный roadmap\n\n"
        "*Файлы:*\n"
        "Пришли PDF/DOCX/фото — я прочту и отвечу на вопросы\n\n"
        "*Команды:*\n"
        "/profile — мои знания о тебе\n"
        "/list — предстоящие события\n"
        "/roadmap — планы к мечтам\n"
        "/files — загруженные файлы\n"
        "/forget — удалить что-то из памяти",
        parse_mode="Markdown"
    )


async def cmd_profile(message: Message, db):
    user_id = message.from_user.id
    profile = db.get_profile(user_id)
    memories = db.get_memories(user_id, limit=20)
    settings = db.get_settings(user_id)

    text = f"🧠 *Что я знаю о тебе:*\n\n"
    text += f"🌍 Часовой пояс: {settings.get('timezone', 'не задан')}\n\n"

    if profile:
        text += "*Профиль:*\n"
        for k, v in profile.items():
            text += f"  • {k}: {v}\n"
        text += "\n"

    by_category = {}
    for m in memories:
        cat = m["category"]
        by_category.setdefault(cat, []).append(m["content"])

    category_names = {
        "habit": "Привычки",
        "goal": "Цели и мечты",
        "preference": "Предпочтения",
        "fact": "Факты",
        "file": "Из файлов"
    }

    for cat, items in by_category.items():
        cat_name = category_names.get(cat, cat)
        text += f"*{cat_name}:*\n"
        for item in items[:5]:
            text += f"  • {item}\n"
        text += "\n"

    if not profile and not memories:
        text += "_Пока пусто. Расскажи мне о себе в диалоге — я всё запомню._"

    text += "\n/forget — удалить что-то из памяти"
    await message.answer(text, parse_mode="Markdown")


async def cmd_list(message: Message, db):
    user_id = message.from_user.id
    events = db.get_upcoming_events(user_id)

    if not events:
        await message.answer(
            "📭 Предстоящих событий нет.\n\n"
            "Напиши о событии в свободной форме, например:\n"
            "«Встреча с подругой в субботу в 15:00»"
        )
        return

    from datetime import datetime
    text = "📅 *Предстоящие события:*\n\n"
    buttons = []

    for i, ev in enumerate(events[:10], 1):
        dt = datetime.fromisoformat(ev["event_time"])
        formatted = dt.strftime("%d.%m в %H:%M")
        text += f"{i}. *{ev['title']}* — {formatted}\n"

        prep = json.loads(ev.get("prep_steps") or "[]")
        if prep:
            text += f"   Подготовка: {', '.join(prep[:3])}\n"

        buttons.append([InlineKeyboardButton(
            text=f"🗑 Удалить: {ev['title'][:25]}",
            callback_data=f"del_event:{ev['id']}"
        )])

    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await message.answer(text, parse_mode="Markdown", reply_markup=kb)


async def cmd_roadmap(message: Message, db):
    user_id = message.from_user.id
    roadmaps = db.get_roadmaps(user_id)

    if not roadmaps:
        await message.answer(
            "🗺 У тебя пока нет roadmap.\n\n"
            "Напиши свою мечту, например:\n"
            "«Хочу научиться играть на гитаре»\n"
            "«Хочу открыть своё дело»"
        )
        return

    for rm in roadmaps[:3]:
        steps = rm["steps"]
        done = sum(1 for s in steps if s.get("done"))
        total = len(steps)

        text = f"🗺 *{rm['dream']}*\n"
        text += f"Прогресс: {done}/{total} шагов\n\n"

        buttons = []
        for i, step in enumerate(steps[:15]):
            icon = "✅" if step.get("done") else "⬜"
            step_text = step.get("step", step.get("title", f"Шаг {i+1}"))
            days = step.get("days", "")
            resource = step.get("resource", "")

            text += f"{icon} {i+1}. {step_text}"
            if days:
                text += f" _{days} д._"
            text += "\n"
            if resource and not step.get("done"):
                text += f"   🔗 {resource}\n"

            action = "rm_undone" if step.get("done") else "rm_done"
            buttons.append([InlineKeyboardButton(
                text=f"{'✅ Готово' if not step.get('done') else '↩️ Вернуть'}: {step_text[:30]}",
                callback_data=f"{action}:{rm['id']}:{i}"
            )])

        kb = InlineKeyboardMarkup(inline_keyboard=buttons[:10])
        await message.answer(text, parse_mode="Markdown", reply_markup=kb)


async def cmd_forget(message: Message, db):
    await message.answer(
        "🗑 *Что удалить из памяти?*\n\n"
        "Напиши, что именно хочешь забыть, например:\n"
        "«Забудь что я не люблю рыбу»\n"
        "«Удали цель про гитару»\n\n"
        "Или используй /profile чтобы увидеть всё."
    )


async def cmd_files(message: Message, db):
    user_id = message.from_user.id
    files = db.get_files(user_id)

    if not files:
        await message.answer(
            "📂 Файлов нет.\n\n"
            "Пришли мне любой файл (PDF, DOCX, изображение) — я его прочту и отвечу на вопросы."
        )
        return

    text = "📂 *Загруженные файлы:*\n\n"
    for f in files[:10]:
        text += f"📄 *{f['filename']}*\n"
        if f.get("summary"):
            text += f"   {f['summary'][:100]}...\n"
        text += "\n"

    text += "\nЧтобы задать вопрос по файлу — просто напиши его."
    await message.answer(text, parse_mode="Markdown")


# Callbacks
async def cb_roadmap_done(callback: types.CallbackQuery, db):
    _, rm_id, step_idx = callback.data.split(":")
    db.update_roadmap_step(int(rm_id), int(step_idx), True)
    await callback.answer("✅ Отмечено как выполнено!")
    await callback.message.edit_reply_markup(reply_markup=None)


async def cb_roadmap_undone(callback: types.CallbackQuery, db):
    _, rm_id, step_idx = callback.data.split(":")
    db.update_roadmap_step(int(rm_id), int(step_idx), False)
    await callback.answer("↩️ Возвращено в список")
    await callback.message.edit_reply_markup(reply_markup=None)


async def cb_delete_event(callback: types.CallbackQuery, db):
    _, event_id = callback.data.split(":")
    event = db.get_event(int(event_id))
    if event:
        db.delete_event(int(event_id))
        await callback.answer(f"🗑 Удалено: {event['title']}")
        await callback.message.edit_text(f"🗑 Удалено: *{event['title']}*", parse_mode="Markdown")
    else:
        await callback.answer("Событие не найдено")
