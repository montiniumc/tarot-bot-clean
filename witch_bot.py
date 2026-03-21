import os
import json
import random
import asyncio
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

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENROUTER_KEY = os.getenv("OPENROUTER_KEY")
PROVIDER_TOKEN = os.getenv("PROVIDER_TOKEN", "")

client = OpenAI(api_key=OPENROUTER_KEY, base_url="https://openrouter.ai/api/v1")

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
            "history": [],
            "referrals": 0,
            "invited_by": None
        }
    return db[uid]

# === TAROT ===
MAJORS = ["Шут","Маг","Жрица","Императрица","Император","Иерофант","Влюбленные","Колесница","Сила","Отшельник","Колесо Фортуны","Справедливость","Повешенный","Смерть","Умеренность","Дьявол","Башня","Звезда","Луна","Солнце","Суд","Мир"]

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
    return [c + (" (перевернутая)" if random.choice([True, False]) else "") for c in cards]

# === GPT ===
def build_prompt(cards, question, history):
    hist = "\n".join(history[-6:])
    return f"""
Ты — живой таролог.

История:
{hist}

Карты: {", ".join(cards)}
Вопрос: {question}

Добавь лёгкое ощущение, что есть скрытый фактор (но без прямых обвинений).

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
        return "Ошибка..."

# === LIMIT ===
def can_free(user):
    if user["premium"]:
        return True, None

    if not user["last_free"]:
        return True, None

    last = datetime.fromisoformat(user["last_free"])
    if datetime.now() - last >= timedelta(hours=24):
        return True, None

    return False, "⏳ Бесплатный расклад уже был"

def mark_free(user):
    user["last_free"] = datetime.now().isoformat()

# === UI ===
def main_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🃏 Бесплатный расклад", callback_data="free")],
        [InlineKeyboardButton("💭 Его мысли", callback_data="thoughts")],
        [InlineKeyboardButton("💔 Вернётся ли он", callback_data="return")],
        [InlineKeyboardButton("👥 Пригласить друзей", callback_data="ref")]
    ])

# === START (рефералка) ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = get_uid(update)
    user = get_user(uid)

    # реферал
    if context.args:
        ref = context.args[0]
        if ref != uid and not user["invited_by"]:
            user["invited_by"] = ref
            ref_user = get_user(ref)
            ref_user["referrals"] += 1

            # бонус
            ref_user["last_free"] = None

    save_db(db)

    bot_username = (await context.bot.get_me()).username
    ref_link = f"https://t.me/{bot_username}?start={uid}"

    await update.message.reply_text(
        f"🔮 Добро пожаловать\n\n"
        f"Твоя ссылка:\n{ref_link}\n\n"
        f"Приглашено: {user['referrals']}\n\n"
        f"За каждого — бонусный расклад 🔥",
        reply_markup=main_kb()
    )

# === BUTTONS ===
async def buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    if q.data == "free":
        context.user_data["mode"] = "ask"
        context.user_data["type"] = "free"
        await q.edit_message_text("Напиши вопрос")

    elif q.data == "thoughts":
        context.user_data["mode"] = "ask"
        context.user_data["type"] = "thoughts"
        await q.edit_message_text("Напиши имя")

    elif q.data == "return":
        context.user_data["mode"] = "ask"
        context.user_data["type"] = "return"
        await q.edit_message_text("Напиши ситуацию")

    elif q.data == "ref":
        uid = get_uid(update)
        bot_username = (await context.bot.get_me()).username
        link = f"https://t.me/{bot_username}?start={uid}"

        await q.edit_message_text(
            f"👥 Твоя ссылка:\n{link}\n\n"
            "За каждого друга — бонус"
        )

# === CHAT ===
async def chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = get_uid(update)
    user = get_user(uid)
    text = update.message.text

    if context.user_data.get("mode") == "ask":
        spread = context.user_data.get("type")

        if spread == "free":
            ok, msg = can_free(user)
            if not ok:
                await update.message.reply_text(msg)
                return

        if spread in ["thoughts","return"] and not user["premium"]:
            await update.message.reply_text("🔒 Только премиум")
            return

        await update.message.reply_text("🔮 Смотрю карты...")

        cards = pick_cards()
        answer = ask_gpt(build_prompt(cards, text, user["history"]))

        # 💔 триггер ревности
        jealousy = "\n\n💔 Есть ощущение, что в его поле сейчас есть влияние извне..."

        user["history"].append(text)
        user["history"].append(answer)

        if spread == "free":
            mark_free(user)

        save_db(db)
        context.user_data["mode"] = None

        await update.message.reply_text(
            f"🃏 {' – '.join(cards)}\n\n{answer}{jealousy}",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("💭 Узнать его мысли", callback_data="thoughts")]
            ])
        )
        return

    await update.message.reply_text("Задай вопрос через кнопку 🃏")

# === RUN ===
if __name__ == "__main__":
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(buttons))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chat))

    print("🔥 BOT STARTED")
    app.run_polling()
