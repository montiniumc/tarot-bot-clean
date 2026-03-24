import os
import json
import random
from pathlib import Path
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import LabeledPrice
from aiogram.utils.keyboard import InlineKeyboardBuilder
import asyncio

# === CONFIG ===
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
PROVIDER_TOKEN = os.getenv("PROVIDER_TOKEN")  # токен ЮKassa для Telegram
bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()

# === DB ===
DB_FILE = Path("db.json")
def load_db():
    if DB_FILE.exists():
        return json.loads(DB_FILE.read_text(encoding="utf-8"))
    return {}
def save_db(data):
    DB_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
db = load_db()
def get_uid(update):
    return str(update.from_user.id if hasattr(update, "from_user") else update.effective_user.id)
def get_user(uid):
    if uid not in db:
        db[uid] = {"premium": False,"last_free": None,"history":[],"refs":[],"ref_by":None,"bonus":0}
    return db[uid]

# === PRIVACY ===
PRIVACY_TEXT = """
🔒 Политика конфиденциальности
• Хранится только ID и история
• Данные не передаются третьим лицам
• Можно удалить: /delete_me
• 18+
"""

# === TAROT ===
MAJORS = ["Шут","Маг","Жрица","Императрица","Император","Иерофант","Влюбленные","Колесница",
          "Сила","Отшельник","Колесо Фортуны","Справедливость","Повешенный","Смерть",
          "Умеренность","Дьявол","Башня","Звезда","Луна","Солнце","Суд","Мир"]

SUITS = {
    "Жезлы": ["Туз","2","3","4","5","6","7","8","9","10","Паж","Рыцарь","Королева","Король"],
    "Чаш": ["Туз","2","3","4","5","6","7","8","9","10","Паж","Рыцарь","Королева","Король"],
    "Мечей": ["Туз","2","3","4","5","6","7","8","9","10","Паж","Рыцарь","Королева","Король"],
    "Пентакли": ["Туз","2","3","4","5","6","7","8","9","10","Паж","Рыцарь","Королева","Король"],
}
ALL_CARDS = MAJORS + [f"{r} {s}" for s in SUITS for r in SUITS[s]]
def pick_cards():
    return [f"{c} (перевернутая)" if random.random()<0.5 else c for c in random.sample(ALL_CARDS,3)]

# === LIMIT ===
def can_free(user):
    if user["premium"] or user["bonus"] > 0: return True, None
    if not user["last_free"]: return True, None
    diff = datetime.now() - datetime.fromisoformat(user["last_free"])
    if diff >= timedelta(hours=24): return True, None
    return False, "⏳ Бесплатный расклад уже был.\nОткрой премиум ✨"
def mark_free(user):
    if user["bonus"] > 0: user["bonus"] -= 1
    else: user["last_free"] = datetime.now().isoformat()

# === UI ===
def main_kb():
    builder = InlineKeyboardBuilder()
    builder.add(types.InlineKeyboardButton("🃏 Бесплатный расклад", callback_data="free"))
    builder.add(types.InlineKeyboardButton("💭 Анализ чувств", callback_data="thoughts"))
    builder.add(types.InlineKeyboardButton("💔 Анализ отношений", callback_data="return"))
    builder.add(types.InlineKeyboardButton("⭐ Премиум", callback_data="premium"))
    builder.add(types.InlineKeyboardButton("🔗 Пригласить (+1 расклад)", callback_data="ref"))
    builder.add(types.InlineKeyboardButton("🔒 Конфиденциальность", callback_data="privacy"))
    return builder.as_markup()

def buy_kb():
    builder = InlineKeyboardBuilder()
    builder.add(types.InlineKeyboardButton("💎 Купить Премиум — 10 ₽ (тест)", callback_data="premium_pay"))
    return builder.as_markup()

# provider_data для ЮKassa
PROVIDER_DATA = {
    "receipt": {
        "items": [{
            "description": "Тестовый расклад Таро",
            "quantity": 1,
            "amount": {"value":"10.00","currency":"RUB"},
            "vat_code":1,
            "payment_mode":"full_payment",
            "payment_subject":"service"
        }]
    }
}

# === START ===
@dp.message(Command("start"))
async def start(update: types.Message):
    uid = get_uid(update)
    user = get_user(uid)
    await update.answer(
        "🔮 Я Эсмеральда.\n"
        "Задай вопрос — посмотрим глубже.\n\n✨ Помогу разобраться.\n\n❗️Развлекательный характер.\n\n" + PRIVACY_TEXT,
        reply_markup=main_kb()
    )

# === BUTTONS ===
@dp.callback_query()
async def buttons(callback: types.CallbackQuery):
    q = callback
    await q.answer()
    uid = get_uid(q)
    user = get_user(uid)

    if q.data in ["free","thoughts","return"]:
        q.message.reply_text("❓ Напиши свой вопрос")
        return

    elif q.data == "premium":
        await q.message.answer(
            "💎 Премиум доступ\n— Все расклады без ограничений\n— Глубокий анализ\n💰 1000 ₽",
            reply_markup=buy_kb()
        )

    elif q.data == "premium_pay":
        await bot.send_invoice(
            chat_id=uid,
            title="Тестовый Таро-платёж",
            description="Тестовая оплата 10 ₽",
            payload="premium_test",
            provider_token=PROVIDER_TOKEN,
            currency="RUB",
            prices=[LabeledPrice(label="Тестовый расклад", amount=10_00)],
            provider_data=json.dumps(PROVIDER_DATA),
            need_email=True,
            send_email_to_provider=True
        )

    elif q.data == "ref":
        await q.message.answer("🔗 Ссылка для приглашения: https://t.me/ВАШ_BOT_USERNAME?start=" + uid)

    elif q.data == "privacy":
        await q.message.answer(PRIVACY_TEXT)

# === PRECHECKOUT ===
@dp.pre_checkout_query()
async def pre_checkout_handler(pre_checkout: types.PreCheckoutQuery):
    await bot.answer_pre_checkout_query(pre_checkout.id, ok=True)

# === SUCCESSFUL PAYMENT ===
@dp.message(lambda m: m.successful_payment is not None)
async def successful_payment_handler(message: types.Message):
    user = get_user(get_uid(message))
    user["premium"] = True
    save_db(db)
    await message.answer("🌟 Премиум активирован!\nТеперь доступны все функции.")

# === DELETE ===
@dp.message(Command("delete_me"))
async def delete_me(message: types.Message):
    uid = get_uid(message)
    if uid in db: del db[uid]; save_db(db)
    await message.answer("✅ Данные удалены")

# === RUN ===
async def main():
    print("🔥 BOT RUNNING")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
