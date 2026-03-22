from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler,
    ConversationHandler, ContextTypes, filters
)
import random, json, os
from pathlib import Path
from datetime import datetime, timedelta
from urllib.parse import parse_qs

# ——————————————————— ПЕРЕМЕННЫЕ ———————————————————
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
FREE_READING_COOLDOWN_HOURS = 24
STEPS_PER_LEVEL = 5
LEVELS = ["Новичок", "Искатель", "Посвящённый", "Маг", "Верховный маг"]

PREMIUM_FILE = Path("premium_users.json")
CHAT_MEMORY_FILE = Path("chat_memory.json")
REFERRAL_FILE = Path("referrals.json")

premium_users = json.loads(PREMIUM_FILE.read_text(encoding="utf-8")) if PREMIUM_FILE.exists() else {}
chat_memory = json.loads(CHAT_MEMORY_FILE.read_text(encoding="utf-8")) if CHAT_MEMORY_FILE.exists() else {}
referrals = json.loads(REFERRAL_FILE.read_text(encoding="utf-8")) if REFERRAL_FILE.exists() else {}

# ——————————————————— КОЛОДА ТАРО ———————————————————
ALL_CARDS = ["9 Пентакли","Отшельник","Паж Мечи","Королева Пентакли","Перевернутая Умеренность","4 Чаш"]
def random_3_tarot():
    return random.sample(ALL_CARDS, 3)
def format_card(card):
    return f"{card} (перевернутая)" if random.random() < 0.5 else card

# ——————————————————— ФУНКЦИИ ———————————————————
def save_json(path: Path, data: dict):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def user_stats(context):
    data = context.user_data
    if "level" not in data:
        data.update({"level":0,"steps":0,"last_free_reading_at":None,"referrer":None})
    return data

def can_do_free_reading(context):
    stats = user_stats(context)
    last = stats.get("last_free_reading_at")
    if not last:
        return True, None
    if isinstance(last, str):
        last = datetime.fromisoformat(last)
    diff = datetime.now() - last
    if diff >= timedelta(hours=FREE_READING_COOLDOWN_HOURS):
        return True, None
    remaining = timedelta(hours=FREE_READING_COOLDOWN_HOURS) - diff
    h, m = divmod(int(remaining.total_seconds() // 60), 60)
    return False, f"Бесплатный расклад доступен раз в день. Следующий через {h} ч {m} мин."

def mark_free_done(stats):
    stats["last_free_reading_at"] = datetime.now().isoformat()

# ——————————————————— СОСТОЯНИЯ ———————————————————
ASK_QUESTION = 1

# ——————————————————— СТАРТ + РЕФЕРАЛКА ———————————————————
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    stats = user_stats(context)
    lvl_name = LEVELS[min(stats["level"], len(LEVELS)-1)]
    
    # Обработка реферала: /start ref=USERID
    args = context.args
    if args:
        ref = args[0]
        if ref.isdigit() and ref != str(update.effective_user.id):
            stats["referrer"] = ref
            referrals.setdefault(ref, []).append(str(update.effective_user.id))
            save_json(REFERRAL_FILE, referrals)
    
    keyboard = [[InlineKeyboardButton("🃏 Бесплатный расклад", callback_data="tarot")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        f"Привет! Твой уровень: {lvl_name} ({stats['steps']}/{STEPS_PER_LEVEL})\n\n🔒 Конфиденциальность соблюдается.\nЕсли тебя пригласил кто-то — он получит бонус при твоем раскладе.",
        reply_markup=reply_markup
    )

# ——————————————————— КНОПКИ ———————————————————
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    stats = user_stats(context)
    if query.data == "tarot":
        can_use, err = can_do_free_reading(context)
        if not can_use:
            kb = [[InlineKeyboardButton("💰 Купить премиум", callback_data="buy_premium")]]
            await query.edit_message_text(f"{err}", reply_markup=InlineKeyboardMarkup(kb))
            return ConversationHandler.END
        await query.edit_message_text("Напиши свой вопрос для расклада:")
        return ASK_QUESTION
    elif query.data == "buy_premium":
        kb = [[InlineKeyboardButton("Купить Stars", url="https://t.me/store")]]
        await query.edit_message_text("💰 Оплата через Stars доступна прямо в Telegram:", reply_markup=InlineKeyboardMarkup(kb))
    return ConversationHandler.END

# ——————————————————— ПОЛУЧЕНИЕ ВОПРОСА ———————————————————
async def receive_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    question = update.message.text
    stats = user_stats(context)
    cards = [format_card(c) for c in random_3_tarot()]
    reply = "1) Ситуация: ...\n2) Чувства: ...\n3) Действие: ..."  # Можно подключить GPT
    msg = f"🃏 {' – '.join(cards)}\n\n{reply}\nТы продвинулся на 1 шаг."
    
    # Триггер ревности
    if any(kw in question.lower() for kw in ["третье лицо","он с кем-то","она с кем-то","третий","третья"]):
        msg += "\n💔 Есть скрытый фактор — возможное третье лицо в ситуации."
    
    # Автоворонка
    can_use, _ = can_do_free_reading(context)
    if not can_use:
        kb = [[InlineKeyboardButton("💰 Купить премиум", callback_data="buy_premium")]]
        await update.message.reply_text(msg, reply_markup=InlineKeyboardMarkup(kb))
    else:
        await update.message.reply_text(msg)
    mark_free_done(stats)

    # Начисление бонуса рефереру
    ref = stats.get("referrer")
    if ref:
        premium_users.setdefault(ref, {}).update({"bonus_readings": premium_users.get(ref, {}).get("bonus_readings",0)+1})
        save_json(PREMIUM_FILE, premium_users)
    
    return ConversationHandler.END

# ——————————————————— RUN ———————————————————
if __name__ == "__main__":
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    
    conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(button_handler)],
        states={ASK_QUESTION: [MessageHandler(filters.TEXT & (~filters.COMMAND), receive_question)]},
        fallbacks=[],
        per_message=True
    )
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(conv_handler)
    
    print("🤖 BOT ESMERALDA STARTED!")
    app.run_polling()
