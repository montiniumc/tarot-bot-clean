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
PROVIDER_TOKEN = os.getenv("PROVIDER_TOKEN")  # ВАЖНО!

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

# === UI ===
def main_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🃏 Бесплатный расклад", callback_data="free")],
        [InlineKeyboardButton("⭐ Премиум", callback_data="premium")]
    ])

def buy_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💳 Купить за 10 ₽ (тест)", callback_data="pay")]
    ])

# === START ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🔮 Я Эсмеральда\n\n"
        "❗️Развлекательный сервис\n\n"
        "Задай вопрос или выбери расклад",
        reply_markup=main_kb()
    )

# === BUTTONS ===
async def buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    if q.data == "free":
        await q.message.reply_text("❓ Напиши вопрос")

    elif q.data == "premium":
        await q.message.reply_text(
            "💎 Премиум доступ\n\n"
            "Без ограничений\n\n"
            "Нажми ниже для оплаты",
            reply_markup=buy_kb()
        )

    elif q.data == "pay":
        await context.bot.send_invoice(
            chat_id=q.from_user.id,
            title="Премиум доступ",
            description="Тестовый платеж 10 ₽",
            payload="premium",
            provider_token=PROVIDER_TOKEN,  # ← ВОТ ТУТ ВСЁ ГЛАВНОЕ
            currency="RUB",
            prices=[LabeledPrice("Премиум", 1000)],  # 10 ₽
            need_email=True
        )

# === CHAT ===
async def chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔮 Карты говорят: всё будет хорошо 😉")

# === PAY ===
async def pre_checkout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.pre_checkout_query.answer(ok=True)

async def successful_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("💎 Платёж прошёл! Премиум активирован")

# === RUN ===
if __name__ == "__main__":
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(buttons))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chat))
    app.add_handler(PreCheckoutQueryHandler(pre_checkout))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment))

    print("🔥 BOT STARTED")
    app.run_polling()
