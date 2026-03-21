import os
import json
import random
from pathlib import Path
from datetime import datetime, timedelta

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes, PreCheckoutQueryHandler
)

from openai import OpenAI

# === CONFIG ===
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENROUTER_KEY = os.getenv("OPENROUTER_KEY")

client = OpenAI(api_key=OPENROUTER_KEY, base_url="https://openrouter.ai/api/v1")

# === DB ===
DB_FILE = Path("db.json")

def load_db():
    if DB_FILE.exists():
        return json.loads(DB_FILE.read_text(encoding="utf-8"))
    return {}

def save_db(db):
    DB_FILE.write_text(json.dumps(db, ensure_ascii=False, indent=2), encoding="utf-8")

db = load_db()

def get_user(update):
    return str(update.effective_user.id)

def get_user_data(uid):
    if uid not in db:
        db[uid] = {
            "premium": False,
            "last_free": None,
            "history": []
        }
    return db[uid]

# === SAFE REPLY ===
async def safe_reply(update, text, kb=None):
    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=kb)
    else:
        await update.message.reply_text(text, reply_markup=kb)

# === TAROT (78 + reversed) ===
MAJORS = [
    "Шут","Маг","Жрица","Императрица","Император","Иерофант",
    "Влюбленные","Колесница","Сила","Отшельник","Колесо Фортуны",
    "Справедливость","Повешенный","Смерть","Умеренность","Дьявол",
    "Башня","Звезда","Луна","Солнце","Суд","Мир"
]

SUITS = {
    "Жезлы": ["Туз","2","3","4","5","6","7","8","9","10","Паж","Рыцарь","Королева","Король"],
    "Чаш": ["Туз","2","3","4","5","6","7","8","9","10","Паж","Рыцарь","Королева","Король"],
    "Мечей": ["Туз","2","3","4","5","6","7","8","9","10","Паж","Рыцарь","Королева","Король"],
    "Пентакли": ["Туз","2","3","4","5","6","7","8","9","10","Паж","Рыцарь","Королева","Король"],
}

ALL_CARDS = MAJORS.copy()
for suit, ranks in SUITS.items():
    for r in ranks:
        ALL_CARDS.append(f"{r} {suit}")

def pick_cards():
    result = []
    cards = random.sample(ALL_CARDS, 3)
    for c in cards:
        reversed_flag = random.choice([True, False])
        if reversed_flag:
            result.append(f"{c} (перевернутая)")
        else:
            result.append(c)
    return result

# === LIMIT ===
def can_free(user):
    if user["premium"]:
        return True, None

    if not user["last_free"]:
        return True, None

    last = datetime.fromisoformat(user["last_free"])
    diff = datetime.now() - last

    if diff >= timedelta(hours=24):
        return True, None

    return False, "⏳ Бесплатный расклад уже был. Хочешь глубже — открой премиум ✨"

def mark_free(user):
    user["last_free"] = datetime.now().isoformat()

# === GPT ===
def build_prompt(cards, question, history):
    hist = "\n".join(history[-6:])
    return f"""
Ты Эсмеральда — живой таролог с психологическим подходом.

История:
{hist}

Карты: {", ".join(cards)}
Вопрос: {question}

ВАЖНО:
- учитывай перевёрнутые карты
- не пугай
- говори как живой человек

Ответ:
✨ Ситуация:
💔 Чувства:
🚀 Действие:
"""

def ask_gpt(prompt):
    try:
        r = client.chat.completions.create(
            model="openai/gpt-4o-mini",
            messages=[{"role":"user","content":prompt}]
        )
        return r.choices[0].message.content
    except:
        return "Карты молчат... попробуй позже 😢"

# === UI ===
def main_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🃏 Бесплатный расклад", callback_data="free")],
        [InlineKeyboardButton("💭 Его мысли", callback_data="thoughts")],
        [InlineKeyboardButton("💔 Вернётся ли он", callback_data="return")],
        [InlineKeyboardButton("⭐ Премиум", callback_data="premium")]
    ])

# === LOGIC ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await safe_reply(update, "🔮 Я Эсмеральда. Смотрю глубже, чем кажется.", main_kb())

async def free_reading(update, context):
    uid = get_user(update)
    user = get_user_data(uid)

    ok, msg = can_free(user)
    if not ok:
        await safe_reply(update, msg, main_kb())
        return

    cards = pick_cards()
    ans = ask_gpt(build_prompt(cards, "Что важно сейчас?", user["history"]))

    user["history"].append(ans)
    mark_free(user)
    save_db(db)

    await safe_reply(update, f"🃏 {' – '.join(cards)}\n\n{ans}", main_kb())

async def paid_reading(update, context, question):
    uid = get_user(update)
    user = get_user_data(uid)

    if not user["premium"]:
        await safe_reply(update, "🔒 Только для премиум ✨", main_kb())
        return

    cards = pick_cards()
    ans = ask_gpt(build_prompt(cards, question, user["history"]))

    user["history"].append(ans)
    save_db(db)

    await safe_reply(update, f"🃏 {' – '.join(cards)}\n\n{ans}", main_kb())

# === BUTTONS ===
async def buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    if q.data == "free":
        await free_reading(update, context)
    elif q.data == "thoughts":
        await paid_reading(update, context, "Что он думает обо мне?")
    elif q.data == "return":
        await paid_reading(update, context, "Вернётся ли он?")
    elif q.data == "premium":
        await update.effective_chat.send_invoice(
            title="Премиум Эсмеральда",
            description="Все расклады без ограничений",
            payload="premium",
            provider_token=PROVIDER_TOKEN,
            currency="XTR",
            prices=[LabeledPrice("Premium", 100)]
        )

# === PAYMENT ===
async def pre_checkout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.pre_checkout_query.answer(ok=True)

async def successful_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = get_user(update)
    user = get_user_data(uid)

    user["premium"] = True
    save_db(db)

    await update.message.reply_text("🌟 Премиум активирован!")

# === CHAT ===
async def chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = get_user(update)
    user = get_user_data(uid)

    text = update.message.text
    ans = ask_gpt(build_prompt(["интуиция"], text, user["history"]))

    user["history"].append(text)
    user["history"].append(ans)
    save_db(db)

    await update.message.reply_text(ans)

# === RUN ===
if __name__ == "__main__":
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(buttons))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chat))

    app.add_handler(PreCheckoutQueryHandler(pre_checkout))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment))

    print("🔥 PRO TAROT BOT STARTED")
    app.run_polling()
