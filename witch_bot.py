import os
import json
import random
import asyncio
from pathlib import Path
from datetime import datetime, timedelta

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes, PreCheckoutQueryHandler
)

from openai import OpenAI

# ===== ENV =====
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENROUTER_KEY = os.getenv("OPENROUTER_KEY")

client = OpenAI(api_key=OPENROUTER_KEY, base_url="https://openrouter.ai/api/v1")

# ===== DB =====
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
            "summary": "",
            "referrals": 0,
            "invited_by": None
        }
    return db[uid]

# ===== TAROT 78 =====
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

# ===== GPT =====
def build_prompt(cards, question, user):
    history = "\n".join(user["history"][-6:])
    summary = user.get("summary", "")

    return f"""
Ты — тёплый таролог.

Контекст пользователя:
{summary}

Последний диалог:
{history}

Карты: {", ".join(cards)}
Вопрос: {question}

Добавь лёгкое ощущение скрытого фактора (третье лицо), но мягко.

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
        return "🔮 Ошибка генерации..."

# ===== MEMORY =====
def update_memory(user, text, answer):
    user["history"].append(text)
    user["history"].append(answer)
    user["history"] = user["history"][-10:]

    try:
        summary_prompt = f"Сократи до сути:\n{user['history']}"
        r = client.chat.completions.create(
            model="openai/gpt-4o-mini",
            messages=[{"role":"user","content":summary_prompt}]
        )
        user["summary"] = r.choices[0].message.content
    except:
        pass

# ===== LIMIT =====
def can_free(user):
    if user["premium"]:
        return True, None
    if not user["last_free"]:
        return True, None

    last = datetime.fromisoformat(user["last_free"])
    if datetime.now() - last >= timedelta(hours=24):
        return True, None

    return False, "⏳ Уже был расклад сегодня"

def mark_free(user):
    user["last_free"] = datetime.now().isoformat()

# ===== UI =====
def main_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🃏 Бесплатный расклад", callback_data="free")],
        [InlineKeyboardButton("💭 Его мысли", callback_data="thoughts")],
        [InlineKeyboardButton("💔 Вернётся ли он", callback_data="return")],
        [InlineKeyboardButton("💎 Купить премиум", callback_data="premium")],
        [InlineKeyboardButton("👥 Пригласить друзей", callback_data="ref")],
        [InlineKeyboardButton("🔒 Конфиденциальность", callback_data="privacy")]
    ])

# ===== START =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = get_uid(update)
    user = get_user(uid)

    if context.args:
        ref = context.args[0]
        if ref != uid and not user["invited_by"]:
            user["invited_by"] = ref
            get_user(ref)["referrals"] += 1

    save_db(db)

    bot_username = (await context.bot.get_me()).username

    await update.message.reply_text(
        f"🔮 Я Эсмеральда\n\n"
        f"Приглашено: {user['referrals']}\n\n"
        f"Ссылка:\nhttps://t.me/{bot_username}?start={uid}",
        reply_markup=main_kb()
    )

# ===== BUTTONS =====
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
        await q.edit_message_text("Имя человека")

    elif q.data == "return":
        context.user_data["mode"] = "ask"
        context.user_data["type"] = "return"
        await q.edit_message_text("Опиши ситуацию")

    elif q.data == "premium":
        await context.bot.send_invoice(
            chat_id=q.message.chat_id,
            title="🔮 Премиум",
            description="Безлимит + скрытые расклады",
            payload="premium",
            provider_token="",
            currency="XTR",
            prices=[LabeledPrice("Премиум", 100)]
        )

    elif q.data == "privacy":
        await q.edit_message_text(
            "🔒 Конфиденциальность:\n\n"
            "Храню:\n• Telegram ID\n• историю\n• статус\n\n"
            "Соответствует 152-ФЗ РФ\n"
            "Данные не передаются третьим лицам\n\n"
            "/delete_me — удалить всё"
        )

# ===== FUNNEL =====
async def sales_funnel(chat_id, context):
    await asyncio.sleep(30)
    await context.bot.send_message(chat_id, "💭 Я не всё сказала...")

    await asyncio.sleep(40)
    await context.bot.send_message(chat_id, "💔 Есть влияние третьего лица...")

    await asyncio.sleep(40)
    await context.bot.send_message(
        chat_id,
        "Хочешь узнать его мысли?",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("💭 Его мысли", callback_data="thoughts")]
        ])
    )

# ===== CHAT =====
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
        answer = ask_gpt(build_prompt(cards, text, user))

        update_memory(user, text, answer)

        if spread == "free":
            mark_free(user)

        save_db(db)
        context.user_data["mode"] = None

        await update.message.reply_text(
            f"🃏 {' – '.join(cards)}\n\n{answer}\n\n💔 Есть скрытый фактор..."
        )

        asyncio.create_task(sales_funnel(update.effective_chat.id, context))
        return

    await update.message.reply_text("Нажми кнопку 🃏")

# ===== PAYMENT =====
async def pre_checkout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.pre_checkout_query.answer(ok=True)

async def successful_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = get_uid(update)
    user = get_user(uid)

    user["premium"] = True
    save_db(db)

    await update.message.reply_text("🌟 Премиум активирован!")

# ===== DELETE =====
async def delete_me(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = get_uid(update)
    if uid in db:
        del db[uid]
        save_db(db)
    await update.message.reply_text("✅ Данные удалены")

# ===== RUN =====
if __name__ == "__main__":
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("delete_me", delete_me))
    app.add_handler(CallbackQueryHandler(buttons))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chat))
    app.add_handler(PreCheckoutQueryHandler(pre_checkout))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment))

    print("🚀 BOT STARTED")
    app.run_polling()
