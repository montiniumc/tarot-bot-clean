import os
import random
import httpx
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
)


TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENROUTER_KEY = os.getenv("OPENROUTER_KEY")

print("TOKEN:", repr(TELEGRAM_TOKEN))
print("OPENROUTER_KEY:", repr(OPENROUTER_KEY))

from openai import OpenAI

client = OpenAI(
    api_key=OPENROUTER_KEY,
    base_url="https://openrouter.ai/api/v1"
)


BASE_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"


def create_stars_invoice_link(title: str, description: str, amount: int) -> str:
    """Создаёт инвойс‑ссылку для Telegram Stars (XTR)."""
    url = f"{BASE_URL}/createInvoiceLink"

    data = {
        "title": title,
        "description": description,
        "payload": "premium_tarot",  # уникальный payload для бота
        "currency": "XTR",  # Stars
        "prices": [{"label": "Премиум‑расшифровка", "amount": amount}],
    }

    resp = httpx.post(url, json=data)
    if resp.status_code != 200:
        raise RuntimeError(f"Telegram API error: {resp.status_code} {resp.text}")

    result = resp.json()
    if not result.get("ok"):
        raise RuntimeError(f"Telegram error: {result}")

    return result["result"]


cards = [
    "Шут", "Маг", "Жрица", "Императрица", "Император",
    "Иерофант", "Влюбленные", "Колесница", "Сила", "Отшельник",
    "Колесо фортуны", "Справедливость", "Повешенный", "Смерть",
    "Умеренность", "Дьявол", "Башня", "Звезда", "Луна", "Солнце", "Суд", "Мир"
]


# Эта функция нужна чуть позже, для реального доступа
PREMIUM_USERS = set()  # словарь/БД потом заменишь на что‑то реальное


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🃏 Таро‑расклад", callback_data="tarot")],
        [InlineKeyboardButton("✨ Премиум‑расшифровка", callback_data="premium")],
        [InlineKeyboardButton("💭 Поговорить с Эсмеральдой", callback_data="chat")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "🔮 Я Эсмеральда. Твой бот‑Таролог и психолог.\n\n"
        "Ты можешь:\n"
        "• сделать расклад на 3 карты,\n"
        "• купить подробную расшифровку,\n"
        "• просто поговорить с ИИ‑психологом.\n\n"
        "Выбери, что хочешь сделать:",
        reply_markup=reply_markup
    )


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "tarot":
        draw = random.sample(cards, 3)
        context.user_data["premium"] = False  # пока не оплачено
        await query.edit_message_text(
            f"🃏 Твои карты:\n{draw[0]} –  {draw[1]} –  {draw[2]}\n\n"
            "Напиши свой вопрос ниже, и Эсмеральда ответит."
        )
    elif query.data == "premium":
        # Создаём Stars‑инвойс‑ссылку
        try:
            link = create_stars_invoice_link(
                title="Премиум‑расшифровка от Эсмеральды",
                description="Подробный разбор твоего расклада, психологический комментарий и рекомендации.",
                amount=100,  # 100 Stars
            )
            keyboard = [
                [
                    InlineKeyboardButton(
                        "💳 Оплатить 100 звёзд",
                        url=link,
                    )
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(
                "✨ Премиум‑расшифровка от Эсмеральды:\n"
                "• подробный разбор твоего расклада,\n"
                "• психологический комментарий,\n"
                "• рекомендации и маленький ритуал.\n\n"
                "Нажми на кнопку ниже, чтобы заплатить 100 звёзд. Твой статус обновится автоматически.",
                reply_markup=reply_markup,
            )
        except Exception as e:
            await query.edit_message_text(
                "🔴 Ошибка при создании оплаты. Попробуй позже."
            )
            print("Stars Invoice Error:", e)
    elif query.data == "chat":
        await query.edit_message_text(
            "💭 Напиши любому Эсмеральде свой вопрос, и я отвечу.\n"
            "Можно спросить о любви, работе, чувствах, будущем."
        )


async def tarot_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    draw = random.sample(cards, 3)
    context.user_data["premium"] = False
    await update.message.reply_text(
        f"🃏 Твои карты:\n{draw[0]} –  {draw[1]} –  {draw[2]}\n\n"
        "Напиши свой вопрос, и Эсмеральда ответит."
    )


async def chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Определяем, премиум‑режим или нет
    is_premium = context.user_data.get("premium", False)

    try:
        # если премиум, даём более длинный, «глубокий» ответ
        if is_premium:
            prompt = (
                "Ты — Эсмеральда, таролог и психолог. Ответь подробно, "
                "как будто консультируешь человека по Таро и психологии, "
                f"на вопрос: {update.message.text}"
            )
        else:
            prompt = update.message.text

        completion = client.chat.completions.create(
            model="openai/gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}]
        )
        reply = completion.choices[0].message.content
    except Exception as e:
        reply = "🔮 Ошибка… попробуй позже"
        print("OpenRouter Error:", e)

    await update.message.reply_text(reply)


app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("tarot", tarot_command))
app.add_handler(CallbackQueryHandler(button_handler))
app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), chat))

print("BOT STARTED")
app.run_polling()
