import logging, os, re, json
from datetime import datetime
from typing import Optional
logger = logging.getLogger(__name__)
EXPENSE_CATEGORIES = {
    "продукты":  {"emoji": "🛒", "keywords": ["пятёрочка","магнит","продукты","вкусвилл","еда","магазин"]},
    "кафе":      {"emoji": "☕", "keywords": ["кафе","ресторан","кофейня","доставка"]},
    "такси":     {"emoji": "🚕", "keywords": ["такси","убер","uber"]},
    "косметика": {"emoji": "💄", "keywords": ["косметика","уход","крем","помада","аптека"]},
    "одежда":    {"emoji": "👗", "keywords": ["одежда","вещи","обувь"]},
    "подписки":  {"emoji": "📱", "keywords": ["подписка","spotify","netflix"]},
    "блог":      {"emoji": "📸", "keywords": ["блог","реклама"]},
    "здоровье":  {"emoji": "💊", "keywords": ["врач","витамины","спорт"]},
    "разное":    {"emoji": "📦", "keywords": []},
}
UNHEALTHY_MAP = {"чипсы": "орешки", "газировка": "воду с лимоном", "конфеты": "финики", "торт": "творожную запеканку", "фастфуд": "куриную грудку", "мороженое": "замороженный банан"}
DEFAULT_PP_PRODUCTS = [("куриная грудка","белок",5),("яйца","белок",7),("творог","белок",5),("гречка","углеводы",14),("рис","углеводы",14),("овсянка","углеводы",10),("огурцы","овощи",4),("помидоры","овощи",4),("яблоки","фрукты",5),("орехи","жиры",14),("кефир","молочное",5)]
def detect_category(text):
    tl = text.lower()
    for cat, info in EXPENSE_CATEGORIES.items():
        for kw in info["keywords"]:
            if kw in tl: return cat
    return "разное"
def detect_unhealthy(text):
    tl = text.lower()
    for kw, alt in UNHEALTHY_MAP.items():
        if kw in tl: return "⚠️ Заметила *" + kw + "* — не ПП. Заменить на " + alt + "?"
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
    period = "месяц" if days >= 28 else str(days) + " дней"
    text = "💰 *Финансы за " + period + ":*" + chr(10) + chr(10)
    if income: text += "📈 Доход: *" + str(income) + " ₽*" + chr(10)
    text += "📉 Расходы: *" + str(total) + " ₽*" + chr(10)
    if income:
        bal = income - total
        text += ("✅" if bal >= 0 else "❌") + " Остаток: *" + str(bal) + " ₽*" + chr(10)
    if by_cat:
        text += chr(10) + "*По категориям:*" + chr(10)
        for cat, amt in sorted(by_cat.items(), key=lambda x: x[1], reverse=True):
            pct = round(amt/total*100) if total else 0
            emoji = EXPENSE_CATEGORIES.get(cat, {"emoji":"📦"})["emoji"]
            text += emoji + " " + cat + ": *" + str(amt) + " ₽* (" + str(pct) + "%)" + chr(10)
    pct_s = round(savings/goal*100, 1) if goal else 0
    text += chr(10) + "🏠 Копилка: *" + str(savings) + "* из " + str(goal) + " ₽ (" + str(pct_s) + "%)" + chr(10)
    return text
def build_pp_report(user_id, db):
    missing = db.get_missing_products(user_id)
    shopping = db.get_shopping_list(user_id)
    text = "🥗 *ПП-статус:*" + chr(10) + chr(10)
    if missing:
        text += "⚠️ *Нужно купить:*" + chr(10)
        for p in missing[:8]: text += "  • " + p["name"] + chr(10)
        text += chr(10)
    text += "🛒 *Список:*" + chr(10)
    if shopping:
        for item in shopping[:10]: text += "  🥗 " + item["item"] + chr(10)
    else: text += "  Пуст" + chr(10)
    return text
def savings_projection(user_id, db):
    profile = db.get_profile(user_id)
    savings = db.get_savings_total(user_id)
    goal = int(profile.get("savings_goal", 500000))
    remaining = goal - savings
    if remaining <= 0: return "🎉 Цель достигнута!"
    filled = min(10, int(savings/goal*10)) if goal else 0
    bar = "█"*filled + "░"*(10-filled)
    pct = round(savings/goal*100, 1) if goal else 0
    text = "🏠 *Копилка:*" + chr(10) + bar + " " + str(pct) + "%" + chr(10)
    text += "Накоплено: *" + str(savings) + " ₽* из " + str(goal) + " ₽" + chr(10)
    text += "Осталось: *" + str(remaining) + " ₽*" + chr(10)
    monthly_income = int(profile.get("monthly_income", 0))
    monthly_exp = db.get_expenses_total(user_id, 30)
    if monthly_income and monthly_exp:
        free = monthly_income - monthly_exp
        if free > 0:
            months = remaining/free
            years = int(months//12); mons = int(months%12)
            text += chr(10) + "При темпе " + str(free) + " ₽/мес: ещё ~"
            text += (str(years) + " лет " + str(mons) + " мес." if years else str(mons) + " мес.") + chr(10)
    return text
