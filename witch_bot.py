import os
import json
from pathlib import Path
import random
import httpx
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, PreCheckoutQuery
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


# ————————————————— Файл с премиум‑пользователями —————————————————

PREMIUM_FILE = Path("premium_users.json")


def load_premium_users():
    """Загружает список премиум‑пользователей из JSON."""
    if PREMIUM_FILE.exists():
        with PREMIUM_FILE.open("r", encoding="utf‑8") as f:
            return json.load(f)
    return {}


def save_premium_users(premium_dict):
    """Сохраняет список премиум‑пользователей в JSON."""
    with PREMIUM_FILE.open("w", encoding="utf‑8") as f:
        json.dump(premium_dict, f, ensure_ascii=False, indent=2)


# Глобальный словарь премиум‑пользователей
premium_users = load_premium_users()


# ————————————————— Проверка, есть ли вечный премиум —————————————————

def is_premium_permanent(user_data_raw) -> bool:
    """Проверяет, есть ли у пользователя бессрочная премиум‑подписка."""
    if not user_data_raw:
        return False
    return user_data_raw.get("premium", False) and user_data_raw.get("permanent", False)


# ————————————————— Команда /status —————————————————

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    user_data_raw = premium_users.get(user_id)

    if is_premium_permanent(user_data_raw):
        status_text = "Ты имеешь **бессрочную премиум‑подписку** 🌟"
    else:
        status_text = "Ты пока не имеешь активной премиум‑подписки 😢"

    await update.message.reply_text(
        f"🔐 Статус премиум‑подписки:\n\n"
        f"{status_text}"
    )


# ————————————————— Создание Stars‑инвойс‑ссылки (~1000 ₽) —————————————————

def create_stars_invoice_link(title: str, description: str, amount: int) -> str:
    """Создаёт инвойс‑ссылку для Telegram Stars (XTR)."""
    url = f"{BASE_URL}/createInvoiceLink"

    data = {
        "title": title,
        "description": description,
        "payload": "premium_tarot",        # уникальный payload для бота
        "currency": "XTR",               # Stars
        "prices": [{"label": "Премиум‑подписка", "amount": amount}],
    }

    resp = httpx.post(url, json=data)
    if resp.status_code != 200:
        raise RuntimeError(f"Telegram API error: {resp.status_code} {resp.text}")

    result = resp.json()
    if not result.get("ok"):
        raise RuntimeError(f"Telegram error: {result}")

    return result["result"]


# ————————————————— Карты и хранение статуса —————————————————

cards = [
    "Шут", "Маг", "Жрица", "Императрица", "Император",
    "Иерофант", "Влюбленные", "Колесница", "Сила", "Отшельник",
    "Колесо фортуны", "Справедливость", "Повешенный", "Смерть",
    "Умеренность", "Дьявол", "Башня", "Звезда", "Луна", "Солнце", "Суд", "Мир"
]


# ————————————————— Обработчики команд —————————————————

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    user_data_raw = premium_users.get(user_id)

    if is_premium_permanent(user_data_raw):
        context.user_data["premium"] = True
        is_permanent = True
    else:
        context.user_data["premium"] = False
        is_permanent = False

    keyboard = [
        [InlineKeyboardButton("🃏 Таро‑расклад", callback_data="tarot")],
        [InlineKeyboardButton("✨ Премиум‑подписка (1000 ₽)", callback_data="premium")],
        [InlineKeyboardButton("💭 Поговорить с Эсмеральдой", callback_data="chat")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if is_permanent:
        welcome = "🔮 Ты уже в премиум‑режиме, подписка бессрочная 🌟"
    else:
        welcome = "🔮 Я Эсмеральда. Твой бот‑Таролог и психолог."

    await update.message.reply_text(
        f"{welcome}\n\n"
        "Ты можешь:\n"
        "• сделать расклад на 3 карты,\n"
        "• купить бессрочную премиум‑подписку за 1000 ₽,\n"
        "• просто поговорить с ИИ‑психологом.\n\n"
        "Выбери, что хочешь сделать:",
        reply_markup=reply_markup
    )


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "tarot":
        draw = random.sample(cards, 3)
        await query.edit_message_text(
            f"🃏 Твои карты:\n{draw[0]} –  {draw[1]} –  {draw[2]}\n\n"
            "Напиши свой вопрос, и Эсмеральда ответит."
        )
    elif query.data == "premium":
        # Покупка бессрочной премиум‑подписки за ~1000 ₽
        try:
            link = create_stars_invoice_link(
                title="Бессрочный премиум от Эсмеральды",
                description="Покупаешь бессрочную премиум‑подписку за 1000 ₽. Наслаждайся ею всегда.",
                amount=550,  # примерно 1000 ₽ по текущему курсу Telegram Stars
            )
            keyboard = [
                [
                    InlineKeyboardButton(
                        "💳 Купить бессрочную подписку (1000 ₽)",
                        url=link,
                    )
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(
                "✨ Бессрочная премиум‑подписка:\n"
                "• подробный разбор твоего расклада,\n"
                "• психологический комментарий,\n"
                "• рекомендации и маленький ритуал.\n\n"
                "Нажми на кнопку ниже, чтобы заплатить примерно 1000 ₽ и получить **бессрочную подписку**.",
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
    # Восстановим премиум‑статус
    user_id = str(update.effective_user.id)
    user_data_raw = premium_users.get(user_id)

    if is_premium_permanent(user_data_raw):
        context.user_data["premium"] = True
    else:
        context.user_data["premium"] = False

    draw = random.sample(cards, 3)
    await update.message.reply_text(
        f"🃏 Твои карты:\n{draw[0]} –  {draw[1]} –  {draw[2]}\n\n"
        "Напиши свой вопрос, и Эсмеральда ответит."
    )


async def chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Восстановим премиум‑статус
    user_id = str(update.effective_user.id)
    user_data_raw = premium_users.get(user_id)

    if is_premium_permanent(user_data_raw):
        context.user_data["premium"] = True
        is_premium = True
    else:
        context.user_data["premium"] = False
        is_premium = False

    try:
        if is_premium:
    prompt = (
        "Ты — Эсмеральда, игривая тарологиня и лёгкая психологиня. "
        "Ответь на вопрос человека доброжелательно, с юмором, но без фамильярности, "
        "используя одну‑две метафоры, 2–4 эмодзи и разговорный тон. "
        "Добавь в ответ короткий ритуал или простое действие, "
        "которое человек может сделать уже сегодня. "
        f"Вот вопрос: {update.message.text}"
    )
else:
    prompt = (
        "Ты — Эсмеральда, таролог и психолог. Ответь на вопрос человека доброжелательно, "
        "доступно и немного с юмором, используя 1–3 эмодзи. "
        f"Вот вопрос: {update.message.text}"
    )

        completion = client.chat.completions.create(
            model="openai/gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}]
        )
        reply = completion.choices[0].message.content
    except Exception as e:
        reply = "🔮 Ошибка… попробуй позже"
        print("OpenRouter Error:", e)

    await update.message.reply_text(reply)


# ————————————————— Обработчики оплаты (Stars) —————————————————

async def pre_checkout_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query: PreCheckoutQuery = update.pre_checkout_query
    if query.invoice_payload == "premium_tarot":
        await query.answer(ok=True)
    else:
        await query.answer(ok=False, error_message="Неверный тариф.")


async def successful_payment_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    successful_payment = update.message.successful_payment

    # Проверяем именно наш payload
    if successful_payment.invoice_payload != "premium_tarot":
        return

    user_id = str(update.effective_user.id)

    # Бессрочная премиум‑подписка
    premium_users[user_id] = {
        "premium": True,
        "permanent": True
    }
    save_premium_users(premium_users)

    context.user_data["premium"] = True

    # Приветствие
    surprise_messages = [
        "Ты только что открыл новый уровень энергии и интуиции. Спасибо за доверие, Эсмеральда ✨",
        "Путь к более ясному пониманию себя начался именно сейчас. Пусть твой день будет особенным 💫",
        "Твой статус: **премиум‑пользователь 🌟 (бессрочная подписка)**",
    ]
    random_msg = random.choice(surprise_messages)

    await update.message.reply_text(
        "🎉 Спасибо за оплату!\n\n"
        + random_msg
        + "\n\n"
        "Теперь ты можешь получать более подробные расклады и анализ. Напиши свой вопрос, и Эсмеральда ответит!"
    )


# ————————————————— Настройка и запуск бота —————————————————

app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("tarot", tarot_command))
app.add_handler(CommandHandler("status", status_command))         # команда /status
app.add_handler(CallbackQueryHandler(button_handler))
app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), chat))

# Добавляем обработчики платежей Stars
app.add_handler(PreCheckoutQueryHandler(pre_checkout_handler))
app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment_handler))

print("BOT STARTED")
app.run_polling()
