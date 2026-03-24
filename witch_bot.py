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
PROVIDER_TOKEN = os.getenv("390540012:LIVE:92480")

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
            "history": [],
            "refs": [],
            "ref_by": None,
            "bonus": 0
        }
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
    if user["premium"] or user["bonus"] > 0:
        return True, None

    if not user["last_free"]:
        return True, None

    diff = datetime.now() - datetime.fromisoformat(user["last_free"])
    if diff >= timedelta(hours=24):
        return True, None

    return False, "⏳ Бесплатный расклад уже был.\nОткрой премиум ✨"

def mark_free(user):
    if user["bonus"] > 0:
        user["bonus"] -= 1
    else:
        user["last_free"] = datetime.now().isoformat()

# === GPT ===
def build_prompt(cards, question, history):
    hist = "\n".join(history[-6:])
    return f"""
Ты — таролог Эсмеральда.

История:
{hist}

Карты: {", ".join(cards)}
Вопрос: {question}

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
        return "Карты молчат…"

# === UI ===
def main_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🃏 Бесплатный расклад", callback_data="free")],
        [InlineKeyboardButton("💭 Анализ чувств", callback_data="thoughts")],
        [InlineKeyboardButton("💔 Анализ отношений", callback_data="return")],
        [InlineKeyboardButton("⭐ Премиум", callback_data="premium")],
        [InlineKeyboardButton("🔗 Пригласить (+1 расклад)", callback_data="ref")],
        [InlineKeyboardButton("🔒 Конфиденциальность", callback_data="privacy")]
    ])

def buy_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💎 Купить Премиум — 10 ₽ (тест)", callback_data="premium_pay")]
    ])

# === START ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = get_uid(update)
    user = get_user(uid)

    args = update.message.text.split()
    if len(args) > 1:
        ref = args[1]
        if ref != uid and not user["ref_by"]:
            user["ref_by"] = ref
            get_user(ref)["bonus"] += 1

    save_db(db)

    await update.message.reply_text(
        "🔮 Я Эсмеральда.\n"
        "Задай вопрос — посмотрим глубже.\n\n"
        "✨ Помогу разобраться в ситуации и увидеть скрытые моменты.\n\n"
        "❗️Услуга носит развлекательный и консультативный характер.\n\n"
        + PRIVACY_TEXT,
        reply_markup=main_kb()
    )

# === BUTTONS ===
async def buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    if q.data in ["free","thoughts","return"]:
        context.user_data["mode"] = "ask"
        context.user_data["type"] = q.data
        await q.message.reply_text("❓ Напиши свой вопрос")

    elif q.data == "premium":
        await q.message.reply_text(
            "💎 Премиум доступ\n\n"
            "— Все расклады без ограничений\n"
            "— Глубокий анализ\n\n"
            "💰 1000 ₽",
            reply_markup=buy_kb()
        )

    elif q.data == "premium_pay":
        await context.bot.send_invoice(
            chat_id=q.from_user.id,
            title="Таро-консультация (Тест)",
            description="Тестовый платёж 10 ₽",
            payload="premium_test",
            provider_token="390540012:LIVE:92480"
            currency="RUB",
            prices=[LabeledPrice("Тестовый платёж", 10_00)],  # 10 ₽
            need_email=True
        )

    elif q.data == "ref":
        link = f"https://t.me/{(await context.bot.get_me()).username}?start={get_uid(update)}"
        await q.message.reply_text(f"🔗 Твоя ссылка:\n{link}")

    elif q.data == "privacy":
        await q.message.reply_text(PRIVACY_TEXT)

# === CHAT ===
async def chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = get_uid(update)
    user = get_user(uid)
    text = update.message.text

    if context.user_data.get("mode") == "ask":
        t = context.user_data["type"]

        if t=="free":
            ok,msg = can_free(user)
            if not ok:
                await update.message.reply_text(msg, reply_markup=buy_kb())
                return

        if t in ["thoughts","return"] and not user["premium"]:
            await update.message.reply_text("🔒 Только премиум", reply_markup=buy_kb())
            return

        await update.message.reply_text("🔮 Смотрю карты...")

        cards = pick_cards()
        answer = ask_gpt(build_prompt(cards, text, user["history"]))

        user["history"] += [text, answer]

        if t=="free":
            mark_free(user)

        save_db(db)
        context.user_data["mode"]=None

        msg = f"🃏 {' – '.join(cards)}\n\n{answer}"
        msg += "\n\n💭 Интерпретация носит вероятностный характер"

        await update.message.reply_text(msg, reply_markup=buy_kb())
        return

    answer = ask_gpt(build_prompt(["интуиция"], text, user["history"]))
    await update.message.reply_text(answer)

# === PAY ===
async def pre_checkout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.pre_checkout_query.answer(ok=True)

async def successful_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = get_user(get_uid(update))
    user["premium"] = True
    save_db(db)

    await update.message.reply_text(
        "🌟 Премиум активирован!\n\n"
        "Теперь доступны все функции.\n"
        "Напиши свой вопрос 💭"
    )

# === DELETE ===
async def delete_me(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = get_uid(update)
    if uid in db:
        del db[uid]
        save_db(db)
    await update.message.reply_text("✅ Данные удалены")

# === RUN ===
if __name__ == "__main__":
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("delete_me", delete_me))
    app.add_handler(CallbackQueryHandler(buttons))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chat))
    app.add_handler(PreCheckoutQueryHandler(pre_checkout))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment))

    print("🔥 BOT RUNNING")
    app.run_polling()
