"""Финансовый модуль."""
import logging, os, re, json, httpx
from datetime import datetime
from typing import Optional
logger = logging.getLogger(__name__)
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
EXPENSE_CATEGORIES = {
    "продукты":  {"emoji": "🛒", "keywords": ["пятёрочка","магнит","продукты","вкусвилл","еда","магазин"]},
    "кафе":      {"emoji": "☕", "keywords": ["кафе","ресторан","кофейня","доставка","яндекс еда"]},
    "такси":     {"emoji": "🚕", "keywords": ["такси","яндекс такси","убер","uber"]},
    "косметика": {"emoji": "💄", "keywords": ["косметика","уход","крем","помада","аптека"]},
    "одежда":    {"emoji": "👗", "keywords": ["одежда","zara","вещи","обувь"]},
    "подписки":  {"emoji": "📱", "keywords": ["подписка","spotify","netflix"]},
    "блог":      {"emoji": "📸", "keywords": ["блог","реклама","съёмка"]},
    "здоровье":  {"emoji": "💊", "keywords": ["врач","витамины","спорт","фитнес"]},
    "разное":    {"emoji": "📦", "keywords": []},
}
UNHEALTHY_MAP = {
    "чипсы": "орешки", "газировка": "воду с лимоном",
    "конфеты": "финики", "торт": "творожную запеканку",
    "фастфуд": "куриную грудку", "мороженое": "замороженный банан",
}
DEFAULT_PP_PRODUCTS = [
    ("куриная грудка","белок",5), ("яйца","белок",7), ("творог","белок",5),
    ("гречка","углеводы",14), ("рис","углеводы",14), ("овсянка","углеводы",10),
    ("огурцы","овощи",4), ("помидоры","овощи",4), ("яблоки","фрукты",5),
    ("орехи","жиры",14), ("кефир","молочное",5),
]
def detect_category(text):
    tl = text.lower()
    for cat, info in EXPENSE_CATEGORIES.items():
        for kw in info["keywords"]:
            if kw in tl: return cat
    return "разное"
def detect_unhealthy(text):
    tl = text.lower()
    for kw, alt in UNHEALTHY_MAP.items():
        if kw in tl: return f"⚠️ Заметила *{kw}* — не ПП. Заменить на {alt}?"
    return None
def _parse_simple(text):
    nums = re.findall(r"(\d[\d\s]*)[₽р]", text) or re.findall(r"(\d{3,6})", text)
    if not nums: return None
    return {"amount": int(nums[0].replace(" ","")), "category": detect_category(text), "shop": "", "products": [], "description": text[:100]}
async def parse_expense_with_ai(text): return _parse_simple(text)
def build_budget_report(user_id, db, days=30):
    by_cat = db.get_expenses_by_category(user_id, days)
    total = sum(by_cat.values())
    income = db.get_income_total(user_id, days)
    savings = db.get_savings_total(user_id)
    goal = int(db.get_profile(user_id).get("savings_goal", 500000))
    text = f"💰 *Финансы за {'месяц' if days>=28 else str(days)+' дней'}:*

"
    if income: text += f"📈 Доход: *{income:,} ₽*
"
    text += f"📉 Расходы: *{total:,} ₽*
"
    if income: text += f"{'✅' if income>=total else '❌'} Остаток: *{income-total:,} ₽*
"
    if by_cat:
        text += "
*По категориям:*
"
        for cat, amt in sorted(by_cat.items(), key=lambda x: x[1], reverse=True):
            pct = round(amt/total*100) if total else 0
            text += f"{EXPENSE_CATEGORIES.get(cat,{'emoji':'📦'})['emoji']} {cat}: *{amt:,} ₽* ({pct}%)
"
    text += f"
🏠 Копилка: *{savings:,}* из {goal:,} ₽ ({round(savings/goal*100,1) if goal else 0}%)
"
    return text
def build_pp_report(user_id, db):
    missing = db.get_missing_products(user_id)
    shopping = db.get_shopping_list(user_id)
    text = "🥗 *ПП-статус:*

"
    if missing:
        text += "⚠️ *Нужно купить:*
"
        for p in missing[:8]: text += f"  • {p['name']}
"
        text += "
"
    text += "🛒 *Список:*
" + ("".join(f"  🥗 {i['item']}
" for i in shopping[:10]) if shopping else "  _Пуст_
")
    return text
def savings_projection(user_id, db):
    profile = db.get_profile(user_id)
    savings = db.get_savings_total(user_id)
    goal = int(profile.get("savings_goal", 500000))
    remaining = goal - savings
    if remaining <= 0: return "🎉 Цель достигнута!"
    filled = min(10, int(savings/goal*10)) if goal else 0
    bar = "█"*filled + "░"*(10-filled)
    text = f"🏠 *Копилка:*
{bar} {round(savings/goal*100,1) if goal else 0}%
Накоплено: *{savings:,} ₽* из {goal:,} ₽
Осталось: *{remaining:,} ₽*
"
    monthly_income = int(profile.get("monthly_income", 0))
    monthly_exp = db.get_expenses_total(user_id, 30)
    if monthly_income and monthly_exp:
        free = monthly_income - monthly_exp
        if free > 0:
            months = remaining/free
            years = int(months//12); mons = int(months%12)
            text += f"
При темпе {free:,} ₽/мес: ещё ~"
            text += f"{years} лет {mons} мес.
" if years else f"{mons} мес.
"
    return text
