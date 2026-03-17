import os
import random
import asyncio
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from openai import OpenAI

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENROUTER_KEY = os.getenv("OPENROUTER_KEY")

print("TOKEN:", repr(TELEGRAM_TOKEN))
client = OpenAI(
    api_key=OPENROUTER_KEY,
    base_url="https://openrouter.ai/api/v1"
)

cards = [
    "Шут","Маг","Жрица","Императрица","Император",
    "Иерофант","Влюбленные","Колесница","Сила","Отшельник",
    "Колесо фортуны","Справедливость","Повешенный","Смерть",
    "Умеренность","Дьявол","Башня","Звезда","Луна","Солнце","Суд","Мир"
]

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔮 Я Эсмеральда. Напиши /tarot")

async def tarot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    draw = random.sample(cards, 3)
    await update.message.reply_text(f"🔮 Твои карты:\n{draw[0]}, {draw[1]}, {draw[2]}")

async def chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        completion = client.chat.completions.create(
            model="openai/gpt-4o-mini",
            messages=[{"role": "user", "content": update.message.text}]
        )
        reply = completion.choices[0].message.content
    except Exception as e:
        reply = "🔮 Ошибка... попробуй позже"
        print(e)

    await update.message.reply_text(reply)

app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("tarot", tarot))
app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), chat))

print("BOT STARTED")
async def main():
    await app.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
