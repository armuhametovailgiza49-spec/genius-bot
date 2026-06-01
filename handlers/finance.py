from aiogram import Dispatcher
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from tools.finance import build_budget_report, build_pp_report, savings_projection, DEFAULT_PP_PRODUCTS, detect_unhealthy
import logging
logger = logging.getLogger(__name__)

def register_finance_commands(dp: Dispatcher):
    dp.message.register(cmd_money, Command("money"))
    dp.message.register(cmd_pp, Command("pp"))
    dp.message.register(cmd_shop, Command("shop"))
    dp.message.register(cmd_barter, Command("barter"))
    dp.message.register(cmd_savings_full, Command("savings"))
    dp.message.register(cmd_add_savings_cmd, Command("add"))
    dp.message.register(cmd_income, Command("income"))
    dp.callback_query.register(handle_money_callback, lambda c: c.data and c.data.startswith("money:"))
    dp.callback_query.register(cb_save_20pct, lambda c: c.data and c.data.startswith("save20:"))
    dp.callback_query.register(cb_shop_clear, lambda c: c.data == "shop:clear")

async def cmd_money(message: Message, db):
    uid = message.from_user.id
    total = db.get_expenses_total(uid, 30)
    savings = db.get_savings_total(uid)
    goal = int(db.get_profile(uid).get("savings_goal", 500000))
    pct = round(savings/goal*100,1) if goal else 0
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 За месяц", callback_data="money:month")],
        [InlineKeyboardButton(text="🏠 Накопления", callback_data="money:savings")],
        [InlineKeyboardButton(text="🥗 ПП", callback_data="money:pp")],
    ])
    await message.answer(f"💰 *Финансы*\nЗа месяц: *{total:,} ₽*\nКопилка: *{savings:,} ₽* ({pct}%)", parse_mode="Markdown", reply_markup=kb)

async def handle_money_callback(callback, db):
    action = callback.data.split(":")[1]
    uid = callback.from_user.id
    if action == "month": text = build_budget_report(uid, db, 30)
    elif action == "week": text = build_budget_report(uid, db, 7)
    elif action == "savings": text = savings_projection(uid, db)
    elif action == "pp": text = build_pp_report(uid, db)
    else: text = "Неизвестное действие"
    await callback.message.edit_text(text, parse_mode="Markdown")
    await callback.answer()

async def cmd_pp(message: Message, db):
    uid = message.from_user.id
    if not db.get_pp_products(uid):
        for name, cat, days in DEFAULT_PP_PRODUCTS:
            db.add_pp_product(uid, name, cat, days)
    await message.answer(build_pp_report(uid, db), parse_mode="Markdown")

async def cmd_shop(message: Message, db):
    uid = message.from_user.id
    parts = message.text.split(maxsplit=1)
    if len(parts) > 1:
        item = parts[1].strip()
        warn = detect_unhealthy(item)
        if warn:
            await message.answer(warn, parse_mode="Markdown"); return
        db.add_to_shopping(uid, item)
        await message.answer(f"✅ Добавила: *{item}*", parse_mode="Markdown"); return
    shopping = db.get_shopping_list(uid)
    text = "🛒 *Список покупок:*\n\n" + ("".join(f"  🥗 {i['item']}\n" for i in shopping) if shopping else "_Пусто_\n")
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ Всё куплено", callback_data="shop:clear")]]) if shopping else None
    await message.answer(text, parse_mode="Markdown", reply_markup=kb)

async def cmd_barter(message: Message, db):
    uid = message.from_user.id
    received = db.get_barters(uid, "received")
    total = db.get_barter_saved_total(uid)
    wishlist = db.get_barters(uid, "wishlist")
    followers = db.get_latest_followers(uid)
    text = "🤝 *Бартеры:*\n\n"
    if received: text += f"✅ Сэкономлено: *{total:,} ₽*\n\n"
    if wishlist:
        text += "🎯 *Хочу:*\n"
        for b in wishlist:
            need = b.get("followers_needed", 0)
            status = " ← *ПИШИ!* 🔥" if need and need <= followers else (f" (нужно +{need-followers})" if need else "")
            text += f"  • {b['brand']}{status}\n"
    else: text += "_Список пуст_\n"
    text += f"\n📊 Подписчики: *{followers}*"
    await message.answer(text, parse_mode="Markdown")

async def cmd_savings_full(message: Message, db):
    uid = message.from_user.id
    await message.answer(savings_projection(uid, db), parse_mode="Markdown")

async def cmd_add_savings_cmd(message: Message, db):
    uid = message.from_user.id
    parts = message.text.split()
    if len(parts) < 2:
        await message.answer("Напиши: */add 5000*", parse_mode="Markdown"); return
    try: amount = int(parts[1].replace(",",""))
    except: await message.answer("Не поняла сумму."); return
    db.add_savings(uid, amount)
    total = db.get_savings_total(uid)
    goal = int(db.get_profile(uid).get("savings_goal", 500000))
    pct = round(total/goal*100,1) if goal else 0
    await message.answer(f"✅ *{amount:,} ₽* в копилку!\n🏠 Итого: *{total:,} ₽* ({pct}%)", parse_mode="Markdown")

async def cmd_income(message: Message, db):
    uid = message.from_user.id
    parts = message.text.split(maxsplit=2)
    if len(parts) < 2:
        await message.answer("Напиши: */income 50000*", parse_mode="Markdown"); return
    try: amount = int(parts[1].replace(",",""))
    except: await message.answer("Не поняла."); return
    source = parts[2] if len(parts) > 2 else "доход"
    db.add_income(uid, amount, source)
    save20 = amount // 5
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"🏠 Отложить {save20:,} ₽", callback_data=f"save20:{save20}")],
        [InlineKeyboardButton(text="Пропустить", callback_data="save20:skip")],
    ])
    await message.answer(f"✅ Доход *{amount:,} ₽* записан!\nОтложить 20% в копилку?", parse_mode="Markdown", reply_markup=kb)

async def cb_save_20pct(callback, db):
    uid = callback.from_user.id
    val = callback.data.split(":")[1]
    if val == "skip":
        await callback.answer("Хорошо!"); await callback.message.edit_reply_markup(reply_markup=None); return
    amount = int(val)
    db.add_savings(uid, amount)
    total = db.get_savings_total(uid)
    goal = int(db.get_profile(uid).get("savings_goal", 500000))
    pct = round(total/goal*100,1) if goal else 0
    await callback.message.edit_text(f"🏠 *{amount:,} ₽ отложены!*\nИтого: *{total:,} ₽* ({pct}%)", parse_mode="Markdown")
    await callback.answer("✅")

async def cb_shop_clear(callback, db):
    db.clear_shopping_list(callback.from_user.id)
    await callback.message.edit_text("✅ Список очищен!")
    await callback.answer()
