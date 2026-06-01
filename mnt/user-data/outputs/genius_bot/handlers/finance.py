"""Хендлеры для финансов: /money, /pp, /shop, /barter, /add, /income"""
import logging
from aiogram import Dispatcher
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from tools.finance import (parse_expense_with_ai, detect_unhealthy, build_budget_report,
    build_pp_report, savings_projection, DEFAULT_PP_PRODUCTS, detect_category)

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
    user_id = message.from_user.id
    total_month = db.get_expenses_total(user_id, 30)
    savings = db.get_savings_total(user_id)
    goal = int(db.get_profile(user_id).get("savings_goal", 500000))
    pct = round(savings / goal * 100, 1) if goal else 0
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Отчёт за месяц", callback_data="money:month")],
        [InlineKeyboardButton(text="📊 Отчёт за неделю", callback_data="money:week")],
        [InlineKeyboardButton(text="🏠 Прогноз накоплений", callback_data="money:savings")],
        [InlineKeyboardButton(text="🥗 ПП и закупки", callback_data="money:pp")],
    ])
    await message.answer(
        f"💰 *Финансовый центр*\n\nЗа месяц потрачено: *{total_month:,} ₽*\nКопилка: *{savings:,} ₽* ({pct}%)\n\nЧто посмотреть?",
        parse_mode="Markdown", reply_markup=kb)


async def handle_money_callback(callback, db):
    action = callback.data.split(":")[1]
    user_id = callback.from_user.id
    if action == "month": text = build_budget_report(user_id, db, 30)
    elif action == "week": text = build_budget_report(user_id, db, 7)
    elif action == "savings": text = savings_projection(user_id, db)
    elif action == "pp": text = build_pp_report(user_id, db)
    else: text = "Неизвестное действие"
    await callback.message.edit_text(text, parse_mode="Markdown")
    await callback.answer()


async def cmd_pp(message: Message, db):
    user_id = message.from_user.id
    if not db.get_pp_products(user_id):
        for name, cat, days in DEFAULT_PP_PRODUCTS:
            db.add_pp_product(user_id, name, cat, days)
        await message.answer("🥗 Настроила твой ПП-список!\n\n" + build_pp_report(user_id, db), parse_mode="Markdown")
    else:
        await message.answer(build_pp_report(user_id, db), parse_mode="Markdown")


async def cmd_shop(message: Message, db):
    user_id = message.from_user.id
    parts = message.text.split(maxsplit=1)
    if len(parts) > 1:
        item = parts[1].strip()
        unhealthy = detect_unhealthy(item)
        if unhealthy:
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Всё равно добавить", callback_data=f"shop:add:{item[:50]}")],
                [InlineKeyboardButton(text="Отмена", callback_data="shop:cancel")],
            ])
            await message.answer(unhealthy, parse_mode="Markdown", reply_markup=kb)
            return
        db.add_to_shopping(user_id, item)
        await message.answer(f"✅ Добавила: *{item}*", parse_mode="Markdown")
        return
    shopping = db.get_shopping_list(user_id)
    missing = db.get_missing_products(user_id)
    text = "🛒 *Список покупок:*\n\n"
    if shopping:
        for item in shopping:
            text += f"  {'🥗' if item['is_pp'] else '⚠️'} {item['item']}\n"
    else:
        text += "_Список пуст_\n"
    if missing:
        text += f"\n⚠️ *Заканчивается:*\n" + "".join(f"  • {p['name']}\n" for p in missing[:5])
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ Всё куплено", callback_data="shop:clear")]]) if shopping else None
    await message.answer(text, parse_mode="Markdown", reply_markup=kb)


async def cmd_barter(message: Message, db):
    user_id = message.from_user.id
    received = db.get_barters(user_id, "received")
    wishlist = db.get_barters(user_id, "wishlist")
    total_saved = db.get_barter_saved_total(user_id)
    followers = db.get_latest_followers(user_id)
    text = "🤝 *Трекер бартеров:*\n\n"
    if received:
        text += f"✅ *Получено:*\n"
        for b in received:
            text += f"  • {b['brand']} — *{b['value_rub']:,} ₽*\n"
        text += f"\nСэкономлено: *{total_saved:,} ₽* → прямо в копилку!\n\n"
    if wishlist:
        text += "🎯 *Хочу:*\n"
        for b in wishlist:
            need = b.get("followers_needed", 0)
            if need and need > followers:
                status = f" (нужно ещё +{need-followers} подп.)"
            elif need and need <= followers:
                status = " ← *МОЖНО ПИСАТЬ!* 🔥"
            else:
                status = ""
            text += f"  • {b['brand']} ({b['category']}){status}\n"
    else:
        text += "_Список пуст. Напиши «Хочу бартер с [бренд]»_\n"
    text += f"\n📊 Подписчики: *{followers}*"
    await message.answer(text, parse_mode="Markdown")


async def cmd_savings_full(message: Message, db):
    user_id = message.from_user.id
    if not db.get_profile(user_id).get("monthly_income"):
        await message.answer("🏠 Скажи свой доход в месяц:\n*Мой доход X рублей в месяц*", parse_mode="Markdown")
        return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏠 Прогноз", callback_data="money:savings")],
    ])
    await message.answer(savings_projection(user_id, db), parse_mode="Markdown", reply_markup=kb)


async def cmd_add_savings_cmd(message: Message, db):
    user_id = message.from_user.id
    parts = message.text.split()
    if len(parts) < 2:
        await message.answer("Напиши: */add 5000*", parse_mode="Markdown")
        return
    try:
        amount = int(parts[1].replace(",","").replace(" ",""))
    except ValueError:
        await message.answer("Не поняла сумму."); return
    db.add_savings(user_id, amount)
    total = db.get_savings_total(user_id)
    goal = int(db.get_profile(user_id).get("savings_goal", 500000))
    pct = round(total/goal*100,1) if goal else 0
    await message.answer(
        f"✅ *{amount:,} ₽* в копилку!\n🏠 Итого: *{total:,} ₽* ({pct}%) — осталось *{goal-total:,} ₽*",
        parse_mode="Markdown")


async def cmd_income(message: Message, db):
    user_id = message.from_user.id
    parts = message.text.split(maxsplit=2)
    if len(parts) < 2:
        await message.answer("Напиши: */income 50000 зарплата*", parse_mode="Markdown"); return
    try:
        amount = int(parts[1].replace(",",""))
    except ValueError:
        await message.answer("Не поняла сумму."); return
    source = parts[2] if len(parts) > 2 else "доход"
    db.add_income(user_id, amount, source)
    save_20 = amount // 5
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"🏠 Отложить {save_20:,} ₽ (20%)", callback_data=f"save20:{save_20}")],
        [InlineKeyboardButton(text="Пропустить", callback_data="save20:skip")],
    ])
    await message.answer(f"✅ Доход *{amount:,} ₽* записан!\nОтложить 20% в копилку?", parse_mode="Markdown", reply_markup=kb)


async def cb_save_20pct(callback, db):
    user_id = callback.from_user.id
    val = callback.data.split(":")[1]
    if val == "skip":
        await callback.answer("Хорошо!")
        await callback.message.edit_reply_markup(reply_markup=None); return
    amount = int(val)
    db.add_savings(user_id, amount)
    total = db.get_savings_total(user_id)
    goal = int(db.get_profile(user_id).get("savings_goal", 500000))
    pct = round(total/goal*100,1) if goal else 0
    await callback.message.edit_text(f"🏠 *{amount:,} ₽ отложены!*\nИтого: *{total:,} ₽* ({pct}%)", parse_mode="Markdown")
    await callback.answer("✅")


async def cb_shop_clear(callback, db):
    db.clear_shopping_list(callback.from_user.id)
    await callback.message.edit_text("✅ Список очищен — всё куплено!")
    await callback.answer()
