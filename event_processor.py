"""Обрабатывает все команды агента: события, память, профиль, финансы, бартер."""
import json, logging
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)


async def process_agent_result(user_id: int, result: dict, db) -> list:
    notifications = []

    for mem in result.get("memories", []):
        if mem.get("category") and mem.get("content"):
            db.add_memory(user_id, mem["category"], mem["content"])

    for prof in result.get("profiles", []):
        if prof.get("key") and prof.get("value"):
            db.set_profile(user_id, prof["key"], prof["value"])

    for event_data in result.get("events", []):
        notif = await _create_event(user_id, event_data, db)
        if notif: notifications.append(notif)

    for rm in result.get("roadmaps", []):
        if rm.get("dream") and rm.get("steps"):
            rm_id = db.save_roadmap(user_id, rm["dream"], rm["steps"])
            notifications.append(f"\n📍 Roadmap сохранён! /roadmap — посмотреть")

    for exp in result.get("expenses", []):
        if exp.get("amount"):
            amount = int(exp["amount"])
            cat = exp.get("category", "разное")
            desc = exp.get("description", "")
            shop = exp.get("shop", "")
            db.add_expense(user_id, amount, cat, desc, shop=shop)
            # Обновляем pp_products если это продукты
            products = exp.get("products", [])
            if isinstance(products, list):
                for p in products:
                    if p: db.update_product_bought(user_id, str(p))
            notifications.append(f"\n💾 Расход *{amount:,} ₽* ({cat}) записан")

            # Предупреждение про большие траты
            savings = db.get_savings_total(user_id)
            goal = int(db.get_profile(user_id).get("savings_goal", 500000))
            if amount >= 3000 and goal > savings:
                notifications.append(f"⚠️ Это *{amount:,} ₽* меньше в копилку на квартиру")

    for inc in result.get("income", []):
        if inc.get("amount"):
            db.add_income(user_id, int(inc["amount"]), inc.get("source", ""))

    for sav in result.get("savings", []):
        if sav.get("amount"):
            db.add_savings(user_id, int(sav["amount"]), sav.get("note", ""))

    for b in result.get("barters", []):
        if b.get("brand"):
            db.add_barter(user_id, b["brand"], b.get("category",""), int(b.get("value_rub",0)),
                         b.get("status","wishlist"), int(b.get("followers_needed",0)))

    for item in result.get("shop_items", []):
        if item.get("item"):
            db.add_to_shopping(user_id, item["item"], is_pp=int(item.get("is_pp", 1)))

    if result.get("followers"):
        db.add_blog_stat(user_id, result["followers"])

    return notifications


async def _create_event(user_id: int, event_data: dict, db) -> Optional[str]:
    try:
        title = event_data.get("title", "Событие")
        dt_str = event_data.get("datetime", "")
        if not dt_str: return None

        try: event_dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M")
        except: 
            try: event_dt = datetime.fromisoformat(dt_str)
            except: return None

        import pytz
        settings = db.get_settings(user_id)
        tz_name = settings.get("timezone", "Asia/Yekaterinburg")
        try:
            local_tz = pytz.timezone(tz_name)
            event_dt_utc = local_tz.localize(event_dt).astimezone(pytz.utc).replace(tzinfo=None)
        except: event_dt_utc = event_dt

        profile = db.get_profile(user_id)
        total_prep = int(event_data.get("prep_minutes", 0))
        if total_prep == 0:
            total_prep = int(profile.get("travel_minutes", 0)) + int(profile.get("grooming_minutes", 0)) + 15
        if total_prep < 20: total_prep = 30

        remind_dt_utc = event_dt_utc - timedelta(minutes=total_prep)
        prep_steps = event_data.get("prep_steps", [])
        if isinstance(prep_steps, str):
            try: prep_steps = json.loads(prep_steps)
            except: prep_steps = [prep_steps]

        db.add_event(user_id, title, event_dt_utc.isoformat(), remind_dt_utc.isoformat(), prep_steps)

        try:
            remind_local = pytz.utc.localize(remind_dt_utc).astimezone(pytz.timezone(tz_name)).replace(tzinfo=None)
        except: remind_local = remind_dt_utc

        msg = (f"\n\n✅ *Событие создано!*\n📌 {title}\n"
               f"📆 {event_dt.strftime('%d.%m.%Y в %H:%M')}\n"
               f"🔔 Напомню в {remind_local.strftime('%H:%M')} (за {total_prep} мин.)")
        if prep_steps:
            msg += "\n📋 " + " → ".join(str(s) for s in prep_steps[:4])
        return msg
    except Exception as e:
        logger.error(f"Event creation error: {e}")
        return None
