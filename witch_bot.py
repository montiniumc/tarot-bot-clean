import os
import json
import random
from pathlib import Path
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENROUTER_KEY = os.getenv("OPENROUTER_KEY")

from openai import OpenAI
client = OpenAI(api_key=OPENROUTER_KEY, base_url="https://openrouter.ai/api/v1")

PREMIUM_FILE = Path("premium_users.json")

def load_premium_users():
    if PREMIUM_FILE.exists():
        with open(PREMIUM_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_premium_users(data):
    with open(PREMIUM_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

premium_users = load_premium_users()

LEVELS = ["Новичок", "Искатель", "Посвященный", "Маг", "Верховный маг"]
STEPS_PER_LEVEL = 5
FREE_READING_COOLDOWN_HOURS = 24

# Полная колода Таро 78 карт
MAJORS = {
    "0": "Шут", "1": "Маг", "2": "Жрица", "3": "Императрица", "4": "Император",
    "5": "Иерофант", "6": "Влюбленные", "7": "Колесница", "8": "Сила", "9": "Отшельник",
    "10": "Колесо Фортуны", "11": "Справедливость", "12": "Повешенный", "13": "Смерть",
    "14": "Умеренность", "15": "Дьявол", "16": "Башня", "17": "Звезда", "18": "Луна",
    "19": "Солнце", "20": "Суд", "21": "Мир"
}

MINOR_RANKS = ["Туз", "2", "3", "4", "5", "6", "7", "8", "9", "10", "Паж", "Рыцарь", "Королева", "Король"]
CARD_NAMES = {**MAJORS}

for suit_name, suit_rus in [("wands", "Жезлы"), ("cups", "Чаш"), ("swords", "Мечей"), ("pentacles", "Пентакли")]:
    for rank in MINOR_RANKS:
        CARD_NAMES[f"{suit_name}:{rank.lower().replace('ё','е')}"] = f"{rank} {suit_rus}"

ALL_CARDS = list(CARD_NAMES.values())

# ТОЧНЫЙ ХАРАКТЕР Эсмеральды из твоего описания
ESMERALDA_FULL_PROMPT = """Ты — Эсмеральда, бот-таролог, для которого Таро — это мягкая психотерапия без занудства.
Ты говоришь тепло, честно, с легким юмором, но без мистического пафоса.

Ты не диагност, не врач, не юрист и не «снимаешь порчу».
Ты помогаешь человеку честно посмотреть на ситуацию, чувства и возможные действия.

Формат ответа:
1) Ситуация: 1–3 предложения про то, что сейчас происходит
2) Чувства: 1–3 предложения про внутреннее состояние, страхи, надежды
3) Действие: 1–3 предложения про мягкие, реалистичные шаги

Ты не угрожаешь, не запугиваешь, не создаешь ощущение «приговора судьбы».
Можешь использовать: «Карты не приказы, а честное зеркало», «Один маленький шаг сегодня лучше идеального плана»."""

def build_tarot_prompt(cards, question, is_premium=False):
    cards_str = " – ".join(cards)
    if is_premium:
        extra = "Сделай развернутый ответ в 2-4 абзаца + короткий ритуал на день. Стиль — теплый, живой."
    else:
        extra = "Ответь кратко в 3-6 предложений. Стиль — доброжелательный с юмором."
    return ESMERALDA_FULL_PROMPT + "\n\nКарты: " + cards_str + "\nВопрос: " + question + "\n\n" + extra

def user_stats(context):
    data = context.user_data
    if "level" not in 
        data.update({"level": 0, "steps": 0, "last_reading": None, "bonus_readings": 0})
    return data

def can_do_reading(context):
    stats = user_stats(context)
    user_id = str(context.effective_user.id)
    is_premium = premium_users.get(user_id, {}).get("premium", False)
    
    if is_premium:
        return True, ""
    
    last = stats.get("last_reading")
    if not last:
        return True, ""
    
    if isinstance(last, str):
        return True, ""
    
    now = datetime.now()
    if now - last >= timedelta(hours=FREE_READING_COOLDOWN_HOURS):
        return True, ""
    
    remaining = timedelta(hours=FREE_READING_COOLDOWN_HOURS) - (now - last)
    hours = int(remaining.total_seconds() // 3600)
    mins = int((remaining.total_seconds() % 3600) // 60)
    return False, f"Бесплатный расклад 1 раз в сутки. Осталось {hours}ч {mins}м"

def add_step(stats):
    stats["steps"] += 1
    if stats["steps"] >= STEPS_PER_LEVEL:
        stats["steps"] = 0
        stats["level"] += 1
        stats["bonus_readings"] = max(stats["bonus_readings"] + 1, 1)
        lvl_name = LEVELS[min(stats["level"], len(LEVELS)-1)]
        return f"\n🎉 Поздравляю! Ты стал {lvl_name}! +1 бонусный расклад (/bonus)"
    return f"\nПуть Мага: шаг {stats['steps']}/{STEPS_PER_LEVEL}"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    stats = user_stats(context)
    level_name = LEVELS[min(stats["level"], len(LEVELS)-1)]
    is_premium = premium_users.get(user_id, {}).get("premium", False)
    
    keyboard = [
        [InlineKeyboardButton("🃏 Таро-расклад", callback_data="tarot")],
        [InlineKeyboardButton("🌟 Мой путь", callback_data="status")],
        [InlineKeyboardButton("🔒 Конфиденциальность", callback_data="privacy")],
        [InlineKeyboardButton("✨ Премиум", callback_data="premium")]
    ]
    
    status = "🌟 Ты в премиум!" if is_premium else "🔓 Бесплатно (1/сутки)"
    
    await update.message.reply_text(
        f"🔮 <b>Привет, путник! Я Эсмеральда ✨</b>\n\n"
        f"<i>Таро — твое честное зеркало, а не приказы судьбы.</i>\n\n"
        f"Твой путь: <b>{level_name}</b> ({stats['steps']}/{STEPS_PER_LEVEL})\n"
        f"Статус: {status}\n\n"
        f"<b>Что умею:</b>\n"
        f"• Расклады на 78 карт Таро\n"
        f"• Система уровней Мага\n"
        f"• Теплая поддержка\n\n"
        f"Выбери действие:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML"
    )

async def privacy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🔒 <b>Политика конфиденциальности</b>\n\n"
        "Храню только:\n"
        "• Твой Telegram ID\n" 
        "• Уровень и шаги по пути Мага\n"
        "• Время последнего бесплатного расклада\n\n"
        "<b>НЕ храню:</b>\n"
        "• Сообщения и личные данные\n"
        "• Не передаю данные третьим лицам\n\n"
        "<b>/delete_me</b> — удалить ВСЕ данные\n\n"
        "Это развлекательный контент 18+",
        parse_mode="HTML"
    )

async def delete_me_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if user_id in premium_users:
        del premium_users[user_id]
        save_premium_users(premium_users)
    context.user_data.clear()
    await update.message.reply_text(
        "✅ <b>Все твои данные удалены!</b>\n\n"
        "При следующем /start начнем путь Мага с нуля ✨",
        parse_mode="HTML"
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "tarot":
        await do_tarot_reading(query, context)
    elif query.data == "status":
        stats = user_stats(context)
        user_id = str(query.from_user.id)
        is_premium = premium_users.get(user_id, {}).get("premium", False)
        level_name = LEVELS[min(stats["level"], len(LEVELS)-1)]
        status_text = "🟢 Бессрочный премиум" if is_premium else "🔓 Бесплатно (1/сутки)"
        
        await query.edit_message_text(
            f"🌟 <b>Твой путь Мага:</b>\n\n"
            f"Уровень: <b>{level_name}</b>\n"
            f"Шаги: {stats['steps']}/{STEPS_PER_LEVEL}\n"
            f"Бонусов: {stats.get('bonus_readings', 0)}\n\n"
            f"Подписка: <b>{status_text}</b>",
            parse_mode="HTML"
        )
    elif query.data == "privacy":
        await privacy_command(update, context)
    elif query.data == "premium":
        await query.edit_message_text(
            "✨ <b>Премиум-подписка</b>\n\n"
            "Скоро через Telegram Stars!\n"
            "Бессрочный доступ ко всем функциям 🌟"
        )

async def do_tarot_reading(query_or_update, context):
    can_use, msg = can_do_reading(context)
    if not can_use:
        if hasattr(query_or_update, 'edit_message_text'):
            await query_or_update.edit_message_text(msg, parse_mode="HTML")
        else:
            await query_or_update.message.reply_text(msg, parse_mode="HTML")
        return
    
    cards = random.sample(ALL_CARDS, 3)
    question = "Как дела сегодня в жизни человека?"
    
    try:
        response = client.chat.completions.create(
            model="openai/gpt-4o-mini",
            messages=[{"role": "user", "content": build_tarot_prompt(cards, question)}]
        )
        reply = response.choices[0].message.content
    except Exception as e:
        reply = "Карты не приказы, а честное зеркало. Сделай маленький шаг сегодня."
    
    stats = user_stats(context)
    stats["last_reading"] = datetime.now()
    
    text = f"""🃏 <b>Расклад на сегодня:</b>

{cards[0]} – {cards[1]} – {cards[2]}

{reply}

{add_step(stats)}"""
    
    if hasattr(query_or_update, 'edit_message_text'):
        await query_or_update.edit_message_text(text, parse_mode="HTML")
    else:
        await query_or_update.message.reply_text(text, parse_mode="HTML")

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await button_handler(Update(callback_query=type('obj', (), {'data': 'status', 'from_user': update.effective_user})(), context)

async def chat_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "💭 <b>Эсмеральда слушает! ✨</b>\n\n"
        "Расскажи, что волнует, или сделай расклад:\n"
        "<b>/start</b> — главное меню\n"
        "<b>/status</b> — твой путь",
        parse_mode="HTML"
    )

if __name__ == "__main__":
    print("🤖 Эсмеральда с полным характером готова!")
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("privacy", privacy_command))
    app.add_handler(CommandHandler("delete_me", delete_me_command))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chat_handler))
    
    print("✅ Бот запущен с полным характером Эсмеральды!")
    app.run_polling()
