import logging
import os
import httpx
from aiogram import Dispatcher
from aiogram.types import Message

from tools.file_parser import extract_text
from agents.brain import process_message, call_claude, build_system_prompt
from tools.event_processor import process_agent_result

logger = logging.getLogger(__name__)

MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 MB


def register_files(dp: Dispatcher):
    dp.message.register(handle_document, lambda m: m.document is not None)
    dp.message.register(handle_photo, lambda m: m.photo is not None)


async def handle_document(message: Message, db):
    user_id = message.from_user.id
    doc = message.document

    if doc.file_size and doc.file_size > MAX_FILE_SIZE:
        await message.answer("⚠️ Файл слишком большой (максимум 20 МБ).")
        return

    await message.answer(f"📄 Читаю файл *{doc.file_name}*...", parse_mode="Markdown")
    await message.bot.send_chat_action(message.chat.id, "typing")

    try:
        file = await message.bot.get_file(doc.file_id)
        file_bytes = await download_file(message.bot, file.file_path)

        if not file_bytes:
            await message.answer("❌ Не удалось скачать файл.")
            return

        text, file_type = await extract_text(file_bytes, doc.file_name or "file")

        if not text or len(text) < 10:
            await message.answer("⚠️ Не удалось извлечь текст из файла.")
            return

        # Генерируем саммари через Claude
        summary = await summarize_file(text, doc.file_name, user_id, db)

        # Сохраняем в БД
        file_id = db.save_file(user_id, doc.file_name, file_type, summary, text[:50000])
        db.add_memory(user_id, "file", f"Загружен файл '{doc.file_name}': {summary[:150]}", f"file:{doc.file_name}")

        # Отвечаем пользователю
        caption = message.caption or ""
        if caption:
            # Есть вопрос — отвечаем сразу
            result = await process_message(user_id, caption, db, extra_context=text[:4000])
            notifications = await process_agent_result(user_id, result, db)
            response = f"📚 *{doc.file_name}* — прочитала!\n\n{summary}\n\n---\n{result['text']}"
            if notifications:
                response += "\n" + "\n".join(notifications)
        else:
            response = (
                f"📚 *{doc.file_name}* — прочитала!\n\n"
                f"*Краткое содержание:*\n{summary}\n\n"
                f"Теперь можешь спрашивать меня по содержанию этого файла."
            )

        await message.answer(response[:4000], parse_mode="Markdown")

    except Exception as e:
        logger.error(f"File handling error: {e}")
        await message.answer(f"❌ Ошибка при обработке файла: {e}")


async def handle_photo(message: Message, db):
    user_id = message.from_user.id

    await message.answer("🖼 Читаю изображение...")
    await message.bot.send_chat_action(message.chat.id, "typing")

    try:
        # Берём самое большое фото
        photo = message.photo[-1]
        file = await message.bot.get_file(photo.file_id)
        file_bytes = await download_file(message.bot, file.file_path)

        if not file_bytes:
            await message.answer("❌ Не удалось скачать изображение.")
            return

        text, _ = await extract_text(file_bytes, "image.jpg")

        if text and len(text) > 10:
            summary = await summarize_file(text, "изображение", user_id, db)
            db.save_file(user_id, "photo.jpg", "image", summary, text[:10000])

            caption = message.caption or ""
            if caption:
                result = await process_message(user_id, caption, db, extra_context=text[:3000])
                await message.answer(result["text"][:4000])
            else:
                await message.answer(
                    f"🖼 Распознала текст на изображении:\n\n{text[:500]}\n\n"
                    "Можешь задать вопросы по содержанию."
                )
        else:
            # Нет текста — просто описываем изображение
            await message.answer(
                "🖼 На изображении не обнаружен текст.\n"
                "Пришли PDF или DOCX для полноценного анализа."
            )

    except Exception as e:
        logger.error(f"Photo handling error: {e}")
        await message.answer(f"❌ Ошибка: {e}")


async def download_file(bot, file_path: str) -> bytes:
    token = bot.token
    url = f"https://api.telegram.org/file/bot{token}/{file_path}"
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(url)
            if resp.status_code == 200:
                return resp.content
    except Exception as e:
        logger.error(f"File download error: {e}")
    return b""


async def summarize_file(text: str, filename: str, user_id: int, db) -> str:
    """Генерирует краткое саммари файла через Claude."""
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        return f"Файл прочитан ({len(text)} символов). Задай вопросы по содержанию."

    try:
        profile = db.get_profile(user_id)
        memories = db.get_memories(user_id, limit=10)
        settings = db.get_settings(user_id)
        system = build_system_prompt(profile, memories, settings)

        messages = [{
            "role": "user",
            "content": f"Файл: {filename}\n\nСодержание:\n{text[:6000]}\n\n---\nСоставь краткое саммари (3-5 предложений): главные идеи, ключевые факты, практические выводы. Если есть список шагов/задач — перечисли их."
        }]
        result = await call_claude(messages, system)
        return result or "Файл прочитан."
    except Exception as e:
        logger.error(f"Summarize error: {e}")
        return f"Файл прочитан ({len(text)} символов)."
