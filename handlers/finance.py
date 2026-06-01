"""Финансовый модуль: расходы, доходы, бюджет, ПП-продукты."""
import logging, os, re, json, httpx
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

EXPENSE_CATEGORIES = {
    "продукты":  {"emoji": "🛒", "keywords": ["пятёрочка","магнит","продукты","вкусвилл","еда","магазин","супермаркет"]},
    "кафе":      {"emoji": "☕", "keywords": ["кафе","ресторан","кофейня","доставка","яндекс еда","самокат"]},
    "такси":     {"emoji": "🚕", "keywords": ["такси","яндекс такси","убер","uber","каршеринг"]},
    "косметика": {"emoji": "💄", "keywords": ["косметика","уход","крем","тональный","помада","аптека","сефора"]},
    "одежда":    {"emoji": "👗", "keywords": ["одежда","zara","h&m","вещи","обувь"]},
    "подписки":  {"emoji": "📱", "keywords": ["подписка","spotify","netflix","яндекс плюс","apple"]},
    "блог":      {"emoji": "📸", "keywords": ["блог","реклама","съёмка","реквизит"]},
    "здоровье":  {"emoji": "💊", "keywords": ["врач","больница","витамины","спорт","фитнес"]},
    "транспорт": {"emoji": "🚇", "keywords": ["метро","автобус","проездной"]},
    "разное":    {"emoji": "📦", "keywords": []},
}

UNHEALTHY_MAP = {
    "чипсы": "орешки", "сухарики": "хлебцы", "газировка": "воду с лимоном",
    "конфеты": "финики или горький шоколад", "торт": "творожную запеканку",
    "фастфуд": "куриную грудку с овощами", "мороженое": "замороженный банан",
    "печенье": "протеиновый батончик",
}

DEFAULT_PP_PRODUCTS = [
    ("куриная грудка","белок",5), ("яйца","белок",7), ("творог","белок",5),
    ("гречка","углеводы",14), ("рис","углеводы",14), ("овсянка","углеводы",10),
    ("огурцы","овощи",4), ("помидоры","овощи",4), ("брокколи","овощи",5),
    ("яблоки","фрукты",5), ("бананы","фрукты",5),
    ("оливковое масло","жиры",30), ("орехи","жиры",14), ("кефир","молочное",5),
]


def detect_category(text: str) -> str:
    tl = text.lower()
    for cat, info in EXPENSE_CATEGORIES.items():
        for kw in info["keywords"]:
            if kw in tl:
                return cat
    return "разное"


def detect_unhealthy(text: str) -> Optional[str]:
    tl = text.lower()
    for kw, alt in UNHEALTHY_MAP.items():
        if kw in tl:
            return f"⚠️ Заметила *{kw}* в списке — это не ПП. Заменить на {alt}?"
    return None


async def parse_expense_with_ai(text: str) -> Optional[dict]:
    if not ANTHROPIC_API_KEY:
        return _parse_simple(text)
    try:
        async with httpx.AsyncClient(timeout=12.0) as client:
            resp = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={"x-api-key": ANTHROPIC_API_KEY, "anthropic-version": "2023-06-01", "content-type": "application/json"},
                json={"model": "claude-haiku-4-5-20251001", "max_tokens": 250,
                      "messages": [{"role": "user", "content":
                          f'Извлеки расход. Верни ТОЛЬКО JSON без markdown:\n{{"amount":число,"category":"продукты|кафе|такси|косметика|одежда|подписки|блог|здоровье|транспорт|разное","shop":"магазин или пусто","products":["список"],"description":"описание"}}\n\nТекст: {text}'}]}
            )
        if resp.status_code == 200:
            raw = resp.json()["content"][0]["text"].strip().replace("```json","").replace("```","")
            return json.loads(raw)
    except Exception as e:
        logger.error(f"AI expense: {e}")
    return _parse_simple(text)


def _parse_simple(text: str) -> Optional[dict]:
    nums = re.findall(r'(\d[\d\s]*)[₽р]', text) or re.findall(r'\b(\d{3,6})\b', text)
    if not nums:
        return None
    return {"amount": int(nums[0].replace(" ","")), "category": detect_category(text),
            "shop": "", "products": [], "description": text[:100]}


def build_budget_report(user_id: int, db, days: int = 30) -> str:
    by_cat = db.get_expenses_by_category(user_id, days)
    total = sum(by_cat.values())
    limits = db.get_budget_limits(user_id)
    income = db.get_income_total(user_id, days)
    savings = db.get_savings_total(user_id)
    goal = int(db.get_profile(user_id).get("savings_goal", 500000))
    barter_saved = db.get_barter_saved_total(user_id)
    period = "месяц" if days >= 28 else f"{days} дней"
    text = f"💰 *Финансы за {period}:*\n\n"
    if income:
        text += f"📈 Доход: *{income:,} ₽*\n"
    text += f"📉 Расходы: *{total:,} ₽*\n"
    if income:
        bal = income - total
        text += f"{'✅' if bal >= 0 else '❌'} Остаток: *{bal:,} ₽*\n"
    if by_cat:
        text += "\n*По категориям:*\n"
        for cat, amt in sorted(by_cat.items(), key=lambda x: x[1], reverse=True):
            emoji = EXPENSE_CATEGORIES.get(cat, {"emoji":"📦"})["emoji"]
            pct = round(amt/total*100) if total else 0
            text += f"{emoji} {cat}: *{amt:,} ₽* ({pct}%)\n"
            if cat in limits and amt > limits[cat]:
                text += f"  ⚠️ Лимит превышен на {amt-limits[cat]:,} ₽!\n"
    if total and by_cat:
        max_cat = max(by_cat, key=by_cat.get)
        if by_cat[max_cat] > total * 0.3:
            text += f"\n💡 {max_cat.capitalize()} — {round(by_cat[max_cat]/total*100)}% расходов, здесь можно сэкономить\n"
    text += f"\n🏠 Копилка: *{savings:,}* из {goal:,} ₽ ({round(savings/goal*100,1) if goal else 0}%)\n"
    if barter_saved:
        text += f"🤝 Бартер сэкономил: *+{barter_saved:,} ₽*\n"
    return text


def build_pp_report(user_id: int, db) -> str:
    missing = db.get_missing_products(user_id)
    shopping = db.get_shopping_list(user_id)
    text = "🥗 *ПП-статус:*\n\n"
    if missing:
        text += "⚠️ *Нужно купить:*\n"
        for p in missing[:8]:
            days_ago = ""
            if p.get("last_bought"):
                try:
                    d = (datetime.utcnow() - datetime.fromisoformat(p["last_bought"])).days
                    days_ago = f" (куплено {d} дн. назад)"
                except Exception:
                    pass
            text += f"  • {p['name']}{days_ago}\n"
        text += "\n"
    if shopping:
        text += "🛒 *Список покупок:*\n"
        for item in shopping[:10]:
            text += f"  {'🥗' if item['is_pp'] else '⚠️'} {item['item']}"
            if item.get("amount"):
                text += f" ({item['amount']})"
            text += "\n"
    else:
        text += "✅ Список покупок пуст\n"
    return text


def savings_projection(user_id: int, db) -> str:
    profile = db.get_profile(user_id)
    savings = db.get_savings_total(user_id)
    goal = int(profile.get("savings_goal", 500000))
    remaining = goal - savings
    if remaining <= 0:
        return "🎉 *Цель достигнута!* Ты накопила 500 000 ₽!"
    monthly_income = int(profile.get("monthly_income", 0))
    monthly_exp = db.get_expenses_total(user_id, 30)
    barter_saved = db.get_barter_saved_total(user_id)
    filled = min(10, int(savings/goal*10)) if goal else 0
    bar = "█"*filled + "░"*(10-filled)
    text = f"🏠 *Копилка на квартиру:*\n{bar} {round(savings/goal*100,1) if goal else 0}%\n"
    text += f"Накоплено: *{savings:,} ₽* из {goal:,} ₽\n"
    text += f"Осталось: *{remaining:,} ₽*\n"
    if barter_saved:
        text += f"🤝 Бартер сэкономил: *{barter_saved:,} ₽*\n"
    if monthly_income and monthly_exp:
        free = monthly_income - monthly_exp
        if free > 0:
            months = remaining / free
            years = int(months // 12); mons = int(months % 12)
            text += f"\nПри темпе {free:,} ₽/мес: ещё ~"
            text += f"{years} лет {mons} мес.\n" if years else f"{mons} мес.\n"
            by_cat = db.get_expenses_by_category(user_id, 30)
            text += "\n*Как ускорить:*\n"
            if by_cat.get("кафе",0) > 3000:
                save = by_cat["кафе"]//2
                text += f"☕ Кафе -50% → +{save:,} ₽/мес\n"
            if by_cat.get("такси",0) > 2000:
                save = by_cat["такси"]//2
                text += f"🚕 Такси -50% → +{save:,} ₽/мес\n"
            text += "🤝 Бартер = прямая экономия → ускоряет цель\n"
    return text
