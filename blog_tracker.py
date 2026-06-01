"""
Блог-модуль: напоминания о съёмке, контент-план, трекер накоплений.
"""
import json
import logging
import os
from datetime import datetime, timedelta
import pytz
import httpx

logger = logging.getLogger(__name__)
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")


# ─── КОНТЕНТ-ПЛАН ДЛЯ НАБОРА ПОДПИСЧИКОВ ─────────────────────
# Основан на анализе аккаунта: лайф-блог, визаж, путешествия, юмор
# Цель: бартер с брендами (косметика, одежда, рестораны)

CONTENT_STRATEGY = {
    "formats": {
        "reels_hook": {
            "name": "Рилс с цепляющим текстом",
            "description": "Текст на первом кадре — вопрос или провокация",
            "examples": [
                "Что ты делаешь когда...",
                "Никто не говорит что...",
                "Я наконец поняла почему..."
            ],
            "frequency": "4-5 раз в неделю",
            "why": "Твои лучшие рилсы — именно такие (10.7k просмотров)"
        },
        "makeup_comparison": {
            "name": "Сравнение макияжа",
            "description": "До/после, разный свет, разные техники",
            "examples": [
                "Макияж при мягком свете vs на солнце",
                "Макияж за 5 минут vs за час",
                "Дневной vs вечерний образ"
            ],
            "frequency": "2-3 раза в неделю",
            "why": "Прямо в интересах брендов косметики"
        },
        "brand_bait": {
            "name": "Контент под бренды",
            "description": "Явно показываешь продукт/место — бренд видит и пишет",
            "examples": [
                "Обзор продукта который купила сама",
                "Любимое кафе в Уфе (отметить заведение)",
                "Образ дня (отметить бренд одежды)"
            ],
            "frequency": "1-2 раза в неделю",
            "why": "Бренды мониторят упоминания"
        },
        "lifestyle_vlog": {
            "name": "Лайф-влог",
            "description": "Будни, прогулки, кофейни — твой стиль жизни",
            "examples": [
                "Утро в Уфе",
                "День визажиста",
                "Вечер с подругами"
            ],
            "frequency": "2-3 раза в неделю",
            "why": "Строит личный бренд и лояльность аудитории"
        }
    },

    "weekly_plan": {
        "Понедельник": {"type": "reels_hook", "theme": "Начало недели / мотивация / юмор"},
        "Вторник": {"type": "makeup_comparison", "theme": "Макияж или образ дня"},
        "Среда": {"type": "lifestyle_vlog", "theme": "Середина недели / кофейня / прогулка"},
        "Четверг": {"type": "brand_bait", "theme": "Продукт или место с отметкой"},
        "Пятница": {"type": "reels_hook", "theme": "Пятничное настроение"},
        "Суббота": {"type": "lifestyle_vlog", "theme": "Выходной день / активности"},
        "Воскресенье": {"type": "makeup_comparison", "theme": "Вечерний образ / подготовка к неделе"},
    },

    "collab_tips": [
        "Добавь в bio: 'По сотрудничеству: @makeupilgiza' или email",
        "Отмечай бренды в постах — многие сами напишут",
        "Создай папку highlights 'Бренды' когда начнутся коллабы",
        "Пиши брендам сама: 500-700 подписчиков уже норм для микро-блогера",
        "Покажи статистику (206k просмотров) — это сильный аргумент"
    ]
}


SHOOTING_REMINDERS = [
    {"time": "09:00", "days": [0, 1, 2, 3, 4], "text": "📸 Доброе утро! Сними что-нибудь сегодня — утренний свет самый красивый"},
    {"time": "13:00", "days": [0, 2, 4], "text": "🎬 Середина дня — идеально для контента на улице. Есть что снять?"},
    {"time": "19:00", "days": [1, 3, 5], "text": "💄 Вечернее время — снимай образ дня или вечерний макияж!"},
    {"time": "21:00", "days": [0, 1, 2, 3, 4, 5, 6], "text": "📱 Не забудь выложить что-нибудь сегодня! Регулярность = рост"},
]


# ─── ТРЕКЕР НАКОПЛЕНИЙ ────────────────────────────────────────

class SavingsTracker:
    def __init__(self, db):
        self.db = db

    def get_goal(self, user_id: int) -> dict:
        profile = self.db.get_profile(user_id)
        return {
            "goal": int(profile.get("savings_goal", 500000)),
            "current": int(profile.get("savings_current", 0)),
            "monthly": int(profile.get("savings_monthly", 0)),
            "currency": profile.get("savings_currency", "₽")
        }

    def add_savings(self, user_id: int, amount: int):
        profile = self.db.get_profile(user_id)
        current = int(profile.get("savings_current", 0))
        new_amount = current + amount
        self.db.set_profile(user_id, "savings_current", str(new_amount))
        return new_amount

    def set_goal(self, user_id: int, goal: int):
        self.db.set_profile(user_id, "savings_goal", str(goal))

    def set_monthly_plan(self, user_id: int, monthly: int):
        self.db.set_profile(user_id, "savings_monthly", str(monthly))

    def get_progress_text(self, user_id: int) -> str:
        data = self.get_goal(user_id)
        goal = data["goal"]
        current = data["current"]
        monthly = data["monthly"]
        currency = data["currency"]

        if goal == 0:
            return "Цель накоплений не задана."

        percent = round(current / goal * 100, 1) if goal > 0 else 0
        remaining = goal - current

        # Прогресс-бар
        filled = int(percent / 10)
        bar = "█" * filled + "░" * (10 - filled)

        text = f"💰 *Накопления на квартиру:*\n\n"
        text += f"{bar} {percent}%\n"
        text += f"Накоплено: *{current:,} {currency}*\n"
        text += f"Осталось: *{remaining:,} {currency}*\n"
        text += f"Цель: {goal:,} {currency}\n"

        if monthly > 0:
            months_left = remaining / monthly
            years = int(months_left // 12)
            months = int(months_left % 12)
            text += f"\nПри откладывании {monthly:,} {currency}/мес:\n"
            if years > 0:
                text += f"⏱ Ещё ~{years} лет {months} мес.\n"
            else:
                text += f"⏱ Ещё ~{months} мес.\n"

            # Мотивационный совет
            if percent < 10:
                text += "\n💪 Только начинаем! Главное — система."
            elif percent < 30:
                text += "\n🔥 Хороший старт! Продолжай в том же духе."
            elif percent < 60:
                text += "\n⚡ Больше половины пути впереди, но темп хороший!"
            elif percent < 90:
                text += "\n🎯 Почти у цели! Не сбавляй обороты."
            else:
                text += "\n🏠 Финишная прямая! Уже видно квартиру!"

        return text


# ─── ГЕНЕРАТОР ИДЕЙ ДЛЯ КОНТЕНТА ─────────────────────────────

async def generate_content_idea(user_context: str = "") -> str:
    """Генерирует идею для рилса через Claude."""
    if not ANTHROPIC_API_KEY:
        return _fallback_idea()

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": ANTHROPIC_API_KEY,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json"
                },
                json={
                    "model": "claude-haiku-4-5-20251001",
                    "max_tokens": 400,
                    "messages": [{
                        "role": "user",
                        "content": f"""Придумай 1 конкретную идею для рилса Instagram для девушки-блогера.
Профиль: Иля из Уфы, лайф-блог + визаж (@makeupilgiza), 394 подписчика, хочет коллабы с брендами косметики, одежды, ресторанов.
Лучший контент: юмористические тексты на экране, путешествия, макияж-сравнения.
Контекст: {user_context or 'случайная идея'}

Формат ответа:
🎬 Название: [короткое название]
📱 Хук (первые 2 секунды): [что видит зритель и текст на экране]
🎵 Атмосфера: [настроение/музыка]
🏷 Отметить: [какой бренд отметить если уместно]
⚡ Почему зайдёт: [1 причина]"""
                    }]
                }
            )
        if resp.status_code == 200:
            return resp.json()["content"][0]["text"]
    except Exception as e:
        logger.error(f"Content idea error: {e}")

    return _fallback_idea()


def _fallback_idea() -> str:
    import random
    ideas = [
        "🎬 *День визажиста*\nСними утро до первого клиента — кофе, кисти, зеркало. Текст: 'Мой день начинается раньше чем ваш'. Отметь кофейню где сидишь.",
        "🎬 *Образ за Х рублей*\nПокажи полный образ и скажи цену. Отметь бренды одежды — они часто репостят.",
        "🎬 *Уфа которую не показывают*\nКрасивое или необычное место в городе. Людям нравится когда про свой город.",
        "🎬 *Ошибка в макияже*\nПокажи распространённую ошибку и как исправить. Образовательный контент отлично сохраняют.",
        "🎬 *Готовлюсь к выходу*\nТаймлапс сборов с музыкой. Текст: 'Они думают я просто встала и вышла'",
    ]
    return random.choice(ideas)
