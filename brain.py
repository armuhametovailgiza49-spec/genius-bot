"""Главный агент — мозг бота. Умеет про финансы, ПП, блог, накопления."""
import os, json, logging, httpx, re
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
MODEL = "claude-sonnet-4-20250514"


def build_system_prompt(profile: dict, memories: list, settings: dict, db=None, user_id=None) -> str:
    tz = settings.get("timezone", "Asia/Yekaterinburg")
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

    profile_text = "\n".join(f"  • {k}: {v}" for k, v in profile.items()) or "  (пока пусто)"
    memory_text = "".join(f"  [{m['category']}] {m['content']}\n" for m in memories[-30:]) or "  (пусто)\n"

    # Финансовый контекст
    finance_ctx = ""
    if db and user_id:
        try:
            total_month = db.get_expenses_total(user_id, 30)
            savings = db.get_savings_total(user_id)
            goal = int(profile.get("savings_goal", 500000))
            followers = db.get_latest_followers(user_id)
            missing = db.get_missing_products(user_id)
            barter_saved = db.get_barter_saved_total(user_id)
            finance_ctx = f"""
═══ ТЕКУЩЕЕ СОСТОЯНИЕ ═══
  💰 Расходы за месяц: {total_month:,} ₽
  🏠 Накоплено: {savings:,} ₽ из {goal:,} ₽ ({round(savings/goal*100,1) if goal else 0}%)
  📸 Подписчики: {followers}
  🤝 Сэкономлено бартером: {barter_saved:,} ₽
  🥗 Заканчивается продуктов: {len(missing)} позиций ({', '.join(p['name'] for p in missing[:3])})"""
        except Exception:
            pass

    return f"""Ты личный гений-помощник Или (Ильгизы) из Уфы. Знаешь её лучше, чем она сама себя помнит.

ТЕКУЩЕЕ ВРЕМЯ: {now} (часовой пояс: {tz})
{finance_ctx}

═══ ПРОФИЛЬ ═══
{profile_text}

═══ ЧТО Я ЗНАЮ ═══
{memory_text}

═══ СУПЕРСПОСОБНОСТИ ═══
1. РАСХОДЫ: Когда пишет «потратила X на Y» — запомни и проверь ПП (если продукты). Если не-ПП продукт — предложи замену.
2. НАПОМИНАНИЯ: Всегда закладывай время на подготовку (мытьё головы — 20 мин, дорога — смотри профиль).
3. БЛОГ: Знаешь что @n1g1za цель — коллабы с брендами. Предлагай идеи контента и напоминай снимать.
4. НАКОПЛЕНИЯ: При любом доходе — предложи отложить 20%. Если трата большая — предупреди про влияние на копилку.
5. БАРТЕР = ЭКОНОМИЯ: Помни что каждый бартер ускоряет накопления. Связывай блог с финансами.
6. ПП: Если упоминает еду — проверяй ПП-статус и список продуктов.
7. ПАМЯТЬ: Запоминай новые факты тегом [REMEMBER].
8. ПРОТИВОРЕЧИЯ: Если новый факт противоречит старому — спрашивай.

═══ КОМАНДЫ В ОТВЕТЕ ═══
[EVENT: title="...", datetime="YYYY-MM-DD HH:MM", prep_minutes=N, prep_steps=["шаг1","шаг2"]]
[REMEMBER: category="habit|goal|preference|fact|finance", content="..."]
[EXPENSE: amount=N, category="...", description="...", products=[".."], shop="..."]
[INCOME: amount=N, source="..."]
[SAVINGS: amount=N, note="..."]
[PROFILE: key="...", value="..."]
[BARTER: brand="...", category="косметика|одежда|ресторан", value_rub=N, status="wishlist|received"]
[SHOP: item="...", is_pp=1]
[FOLLOWERS: count=N]
[ROADMAP: dream="...", steps=[{{"step":"...","days":N,"resource":"..."}}]]

═══ ПРАВИЛА ═══
- Отвечай на РУССКОМ
- Будь конкретной: не «скоро», а «в субботу, 21 июня в 18:00»
- НЕ требуй объяснять одно и то же дважды
- Один уточняющий вопрос за раз
- При каждом упоминании траты > 5000₽ — напомни про влияние на копилку
- Связывай всё: блог → подписчики → бартер → экономия → быстрее квартира"""


async def call_claude(messages: list, system: str) -> Optional[str]:
    if not ANTHROPIC_API_KEY:
        return "⚠️ ANTHROPIC_API_KEY не задан. Добавь его в Variables на Railway."
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={"x-api-key": ANTHROPIC_API_KEY, "anthropic-version": "2023-06-01", "content-type": "application/json"},
                json={"model": MODEL, "max_tokens": 2000, "system": system, "messages": messages}
            )
        if resp.status_code != 200:
            logger.error(f"Claude API {resp.status_code}: {resp.text[:200]}")
            return f"Ошибка API: {resp.status_code}. Попробуй снова."
        return resp.json()["content"][0]["text"]
    except Exception as e:
        logger.error(f"Claude call error: {e}")
        return "Ошибка при обращении к ИИ. Попробуй снова."


async def process_message(user_id: int, user_text: str, db, extra_context: str = "") -> dict:
    profile = db.get_profile(user_id)
    memories = db.get_memories(user_id, limit=40)
    dialog = db.get_dialog(user_id, limit=16)
    settings = db.get_settings(user_id)

    system = build_system_prompt(profile, memories, settings, db, user_id)
    messages = list(dialog)
    full_text = user_text
    if extra_context:
        full_text = f"{user_text}\n\n[Контекст из файла]:\n{extra_context[:3000]}"
    messages.append({"role": "user", "content": full_text})

    raw_response = await call_claude(messages, system)
    if not raw_response:
        return {"text": "Не удалось получить ответ.", "events": [], "memories": [], "profiles": [], "roadmaps": [], "expenses": [], "income": [], "savings": [], "barters": [], "shop_items": [], "followers": None}

    result = parse_agent_response(raw_response)
    db.add_dialog(user_id, "user", user_text)
    db.add_dialog(user_id, "assistant", result["clean_text"])
    return result


def parse_agent_response(raw: str) -> dict:
    events, memories, profiles, roadmaps, expenses, income_items, savings_items, barters, shop_items = [], [], [], [], [], [], [], [], []
    followers = None

    patterns = {
        "event": r'\[EVENT:\s*(.*?)\]',
        "remember": r'\[REMEMBER:\s*(.*?)\]',
        "profile": r'\[PROFILE:\s*(.*?)\]',
        "expense": r'\[EXPENSE:\s*(.*?)\]',
        "income": r'\[INCOME:\s*(.*?)\]',
        "savings": r'\[SAVINGS:\s*(.*?)\]',
        "barter": r'\[BARTER:\s*(.*?)\]',
        "shop": r'\[SHOP:\s*(.*?)\]',
        "followers": r'\[FOLLOWERS:\s*count=(\d+)\]',
        "roadmap": r'\[ROADMAP:\s*([\s\S]*?)\]',
    }

    for m in re.finditer(patterns["event"], raw, re.DOTALL):
        try: events.append(parse_kv(m.group(1)))
        except: pass
    for m in re.finditer(patterns["remember"], raw, re.DOTALL):
        try: memories.append(parse_kv(m.group(1)))
        except: pass
    for m in re.finditer(patterns["profile"], raw, re.DOTALL):
        try: profiles.append(parse_kv(m.group(1)))
        except: pass
    for m in re.finditer(patterns["expense"], raw, re.DOTALL):
        try: expenses.append(parse_kv(m.group(1)))
        except: pass
    for m in re.finditer(patterns["income"], raw, re.DOTALL):
        try: income_items.append(parse_kv(m.group(1)))
        except: pass
    for m in re.finditer(patterns["savings"], raw, re.DOTALL):
        try: savings_items.append(parse_kv(m.group(1)))
        except: pass
    for m in re.finditer(patterns["barter"], raw, re.DOTALL):
        try: barters.append(parse_kv(m.group(1)))
        except: pass
    for m in re.finditer(patterns["shop"], raw, re.DOTALL):
        try: shop_items.append(parse_kv(m.group(1)))
        except: pass
    for m in re.finditer(patterns["followers"], raw):
        try: followers = int(m.group(1))
        except: pass
    for m in re.finditer(patterns["roadmap"], raw, re.DOTALL):
        try:
            content = m.group(1).strip()
            dream_m = re.search(r'dream="([^"]+)"', content)
            steps_m = re.search(r'steps=(\[[\s\S]+\])', content)
            if dream_m and steps_m:
                roadmaps.append({"dream": dream_m.group(1), "steps": json.loads(steps_m.group(1).replace("'", '"'))})
        except: pass

    clean = raw
    for pat in patterns.values():
        clean = re.sub(pat, '', clean, flags=re.DOTALL)
    clean = clean.strip()

    return {"text": clean, "clean_text": clean, "events": events, "memories": memories,
            "profiles": profiles, "roadmaps": roadmaps, "expenses": expenses,
            "income": income_items, "savings": savings_items, "barters": barters,
            "shop_items": shop_items, "followers": followers, "raw": raw}


def parse_kv(s: str) -> dict:
    result = {}
    for m in re.finditer(r'(\w+)="([^"]*)"', s):
        result[m.group(1)] = m.group(2)
    for m in re.finditer(r'(\w+)=(\d+)', s):
        if m.group(1) not in result:
            result[m.group(1)] = int(m.group(2))
    return result
