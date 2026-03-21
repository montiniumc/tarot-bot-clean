import os
import json
import random
from pathlib import Path
from datetime import datetime, timedelta

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice
)
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

def save_db(data):
    DB_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

db = load_db()

def get_uid(update):
    return str(update.effective_user.id)

def get_user(uid):
    if uid not in db:
        db[uid] = {
            "premium": False,
            "last_free": None,
            "history": []
        }
    return db[uid]

# === PRIVACY ===
PRIVACY_TEXT = """
🔒 Политика конфиденциальности

Я храню:
• Telegram ID
• историю диалога
• действия внутри бота

Используется только для работы бота.

❗ Данные не передаются третьим лицам

Удаление: /delete_me

Соответствие ФЗ-152 РФ
18+
"""

# === TAROT ===
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
    cards = random.sample(ALL_CARDS, 3)
    result = []
    for c in cards:
        if random.choice([True, False]):
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

    return False, "⏳ Бесплатный расклад уже был.\nХочешь глубже — открой премиум ✨"

def mark_free(user):
    user["last_free"] = datetime.now().isoformat()

# === GPT ===
def build_prompt(cards, question, history):
    hist = "\n".join(history[-6:])
    return f"""
Ты — Эсмеральда, живой таролог.

История:
{hist}

Карты: {", ".join(cards)}
Вопрос: {question}

Учитывай перевёрнутые карты.

Формат:
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
        return "Карты молчат… попробуй позже"

# === UI ===
def main_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🃏 Бесплатный расклад", callback_data="free")],
        [InlineKeyboardButton("💭 Его мысли", callback_data="thoughts")],
        [InlineKeyboardButton("💔 Вернётся ли он", callback_data="return")],
        [InlineKeyboardButton("⭐ Премиум", callback_data="premium")],
        [InlineKeyboardButton("🔒 Конфиденциальность", callback_data="privacy")]
    ])

# === COMMANDS ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🔮 Я Эсмеральда. Задай вопрос — и посмотрим, что скрыто.",
        reply_markup=main_kb()
    )

async def delete_me(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = get_uid(update)
    if uid in db:
        del db[uid]
        save_db(db)
    await update.message.reply_text("✅ Данные удалены")

# === BUTTONS ===
async def buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    if q.data == "free":
        context.user_data["mode"] = "ask"
        context.user_data["type"] = "free"

        await q.edit_message_text(
            "✨ Напиши свой вопрос.\n\nПример:\nЧто он чувствует ко мне?"
        )

    elif q.data == "thoughts":
        context.user_data["mode"] = "ask"
        context.user_data["type"] = "thoughts"

        await q.edit_message_text("💭 Напиши имя или ситуацию")

    elif q.data == "return":
        context.user_data["mode"] = "ask"
        context.user_data["type"] = "return"

        await q.edit_message_text("💔 Напиши про кого вопрос")

    elif q.data == "premium":
        await update.effective_chat.send_invoice(
            title="Премиум доступ",
            description="Безлимитные расклады",
            payload="premium",
            provider_token=PROVIDER_TOKEN,
            currency="XTR",
            prices=[LabeledPrice("Premium", 100)]
        )

    elif q.data == "privacy":
        await q.edit_message_text(PRIVACY_TEXT)

# === CHAT ===
async def chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = get_uid(update)
    user = get_user(uid)
    text = update.message.text

    if context.user_data.get("mode") == "ask":

        spread_type = context.user_data.get("type")

        if spread_type == "free":
            ok, msg = can_free(user)
            if not ok:
                await update.message.reply_text(msg)
                return

        if spread_type in ["thoughts", "return"] and not user["premium"]:
            await update.message.reply_text(
                "🔒 Этот расклад доступен только в премиум ✨",
                reply_markup=main_kb()
            )
            return

        await update.message.reply_text("🔮 Смотрю на карты...")

        cards = pick_cards()
        answer = ask_gpt(build_prompt(cards, text, user["history"]))

        user["history"].append(text)
        user["history"].append(answer)

        if spread_type == "free":
            mark_free(user)

        save_db(db)
        context.user_data["mode"] = None

        # 🔥 ПРОДАЮЩИЙ АПСЕЛЛ
        upsell = "\n\n💫 Хочешь узнать, что он думает прямо сейчас — это уже глубже...\nОткрой премиум ⭐"

        await update.message.reply_text(
            f"🃏 {' – '.join(cards)}\n\n{answer}{upsell}",
            reply_markup=main_kb()
        )
        return

    # обычный чат
    answer = ask_gpt(build_prompt(["интуиция"], text, user["history"]))
    user["history"].append(text)
    user["history"].append(answer)
    save_db(db)

    await update.message.reply_text(answer)

# === PAYMENT ===
async def pre_checkout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.pre_checkout_query.answer(ok=True)

async def successful_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = get_uid(update)
    user = get_user(uid)

    user["premium"] = True
    save_db(db)

    await update.message.reply_text("🌟 Премиум активирован!")

# === RUN ===
if __name__ == "__main__":
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("delete_me", delete_me))
    app.add_handler(CallbackQueryHandler(buttons))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chat))

    app.add_handler(PreCheckoutQueryHandler(pre_checkout))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment))

    print("🔥 BOT STARTED")
    app.run_polling()
