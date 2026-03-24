import os
import json
import random
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler, MessageHandler,
    PreCheckoutQueryHandler, ContextTypes, filters
)

# ==== CONFIG ====
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
PROVIDER_TOKEN = os.getenv("390540012:LIVE:92480")  # ЮKassa токен для Telegram
DB_FILE = "db.json"

# ==== DB ====
def load_db():
    try:
        with open(DB_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}

def save_db(db):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)

db = load_db()

def get_user(uid):
    if uid not in db:
        db[uid] = {"premium": False, "last_free": None, "history": []}
    return db[uid]

# ==== TAROT CARDS ====
MAJORS = ["Шут","Маг","Жрица","Императрица","Император","Иерофант","Влюбленные","Колесница",
          "Сила","Отшельник","Колесо Фортуны","Справедливость","Повешенный","Смерть",
          "Умеренность","Дьявол","Башня","Звезда","Луна","Солнце","Суд","Мир"]

SUITS = {
    "Жезлы": ["Туз","2","3","4","5","6","7","8","9","10","Паж","Рыцарь","Королева","Король"],
    "Чаш": ["Туз","2","3","4","5","6","7","8","9","10","Паж","Рыцарь","Королева","Король"],
    "Мечей": ["Туз","2","3","4","5","6","7","8","9","10","Паж","Рыцарь","Королева","Король"],
    "Пентакли": ["Туз","2","3","4","5","6","7","8","9","10","Паж","Рыцарь","Королева","Король"]
}

ALL_CARDS = MAJORS + [f"{r} {s}" for s in SUITS for r in SUITS[s]]

def pick_cards():
    return [f"{c} (перевернутая)" if random.random()<0.5 else c for c in random.sample(ALL_CARDS,3)]

# ==== FREE / PREMIUM LIMIT ====
def can_free(user):
    if user["premium"]:
        return True, None
    if not user["last_free"]:
        return True, None
    diff = datetime.now() - datetime.fromisoformat(user["last_free"])
    if diff >= timedelta(hours=24):
        return True, None
    return False, "⏳ Бесплатный расклад уже был. Купи премиум ✨"

def mark_free(user):
    user["last_free"] = datetime.now().isoformat()

# ==== KEYBOARDS ====
def main_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🃏 Бесплатный расклад", callback_data="free")],
        [InlineKeyboardButton("💭 Анализ чувств", callback_data="thoughts")],
        [InlineKeyboardButton("💔 Анализ отношений", callback_data="return")],
        [InlineKeyboardButton("⭐ Премиум", callback_data="premium")]
    ])

def buy_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💎 Купить Премиум — 10 ₽ (тест)", callback_data="premium_pay")]
    ])

# ==== START ====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    get_user(uid)
    await update.message.reply_text(
        "🔮 Я Эсмеральда, твой таролог.\n"
        "Выбери расклад или нажми /premium для тестового платежа.",
        reply_markup=main_kb()
    )

# ==== BUTTONS ====
async def buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = str(q.from_user.id)
    user = get_user(uid)

    if q.data in ["free","thoughts","return"]:
        ok,msg = can_free(user) if q.data=="free" else (user["premium"], "🔒 Только премиум доступ")
        if not ok:
            await q.message.reply_text(msg, reply_markup=buy_kb())
            return

        if q.data=="free":
            mark_free(user)

        cards = pick_cards()
        result_text = f"🃏 {' – '.join(cards)}\n\n💭 Интерпретация носит вероятностный характер."
        user["history"] += [result_text]
        save_db(db)
        await q.message.reply_text(result_text, reply_markup=main_kb())

    elif q.data=="premium":
        await q.message.reply_text("💎 Премиум доступ — тест 10 ₽", reply_markup=buy_kb())

    elif q.data=="premium_pay":
        await context.bot.send_invoice(
            chat_id=uid,
            title="Таро-консультация (Тест)",
            description="Тестовый платёж 10 ₽",
            payload="premium_test",
            provider_token="390540012:LIVE:92480",
            currency="RUB",
            prices=[LabeledPrice("Тестовый расклад", 10_00)],
            need_email=True,
            send_email_to_provider=True,
            provider_data=json.dumps({
                "receipt": {
                    "items": [{
                        "description": "Тестовый расклад Таро",
                        "quantity": 1,
                        "amount": {"value": "10.00", "currency": "RUB"},
                        "vat_code": 1,
                        "payment_mode": "full_payment",
                        "payment_subject": "service"
                    }]
                }
            })
        )

# ==== PRECHECKOUT ====
async def pre_checkout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.pre_checkout_query.answer(ok=True)

# ==== SUCCESSFUL PAYMENT ====
async def successful_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    user = get_user(uid)
    user["premium"] = True
    save_db(db)
    await update.message.reply_text("✅ Премиум активирован! Оплата прошла успешно.", reply_markup=main_kb())

# ==== RUN ====
if __name__ == "__main__":
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(buttons))
    app.add_handler(PreCheckoutQueryHandler(pre_checkout))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment))
    print("Бот запущен!")
    app.run_polling()
