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

MAJORS = {
    "0": "Шут", "1": "Маг", "2": "Жрица", "3": "Императрица", "4": "Император",
    "5": "Иерофант", "6": "Влюбленные", "7": "Колесница", "8": "Сила", "9": "Отшельник",
    "10": "Колесо Фортуны", "11": "Справедливость", "12": "Повешенный", "13": "Смерть",
    "14": "Умеренность", "15": "Дьявол", "16": "Башня", "17": "Звезда", "18": "Луна",
    "19": "Солнце", "20": "Суд", "21": "Мир"
}

MINOR_RANKS = ["Туз", "2", "3", "4", "5", "6", "7", "8", "9", "10", "Паж", "Рыцарь", "Королева", "Король"]
CARD_NAMES = MAJORS.copy()

for suit_name, suit_rus in [("Жезлы", "wands"), ("Чаш", "cups"), ("Мечей", "swords"), ("Пентакли", "pentacles")]:
    for rank in MINOR_RANKS:
        CARD_NAMES[f"{suit_name.lower()}:{rank.lower().replace('ё','е')}"] = f"{rank} {suit_name}"

ALL_CARDS = list(CARD_NAMES.values())

ESMERALDA_FULL_PROMPT = (
    "Ты — Эсмеральда, бот-таролог, для которого Таро — это мягкая психотерапия без занудства. "
    "Ты говоришь тепло, честно, с легким юмором, но без мистического пафоса. "
    "Формат ответа: 1) Ситуация 2) Чувства 3) Действие. "
    "Не угрожаешь, не запугиваешь. Карты — честное зеркало."
)

def build_tarot_prompt(cards, question, is_premium=False):
    cards_str = " – ".join(cards)
    if is_premium:
        extra = "Подробный ответ в 4 абзаца + ритуал. Стиль — теплый, живой."
    else:
        extra = "Короткий ответ в 3-6 предложений. Стиль — доброжелательный."
    return ESMERALDA_FULL_PROMPT + " Карты: " + cards_str + ". Вопрос: " + question + ". " + extra

def user_stats(context):
    data = context.user_data
    if "level" not in 
        data["level"] = 0
        data["steps"] = 0
        data["last_reading"] = None
        data["bonus_readings"] = 0
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
    return False, f"Подожди {hours}ч {mins}м до следующего бесплатного расклада"

def add_step(stats):
    stats["steps"] += 1
    if stats["steps"] >= STEPS_PER_LEVEL:
        stats["steps"] = 0
        stats["level"] += 1
        stats["bonus_readings"] += 1
        lvl_name = LEVELS[min(stats["level"], len(LEVELS)-1)]
        return f"\n🎉 Ты {lvl_name}! +1 бонус (/bonus)"
    return f"\nШаг {stats['steps']}/{STEPS_PER_LEVEL}"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    stats = user_stats(context)
    level_name = LEVELS[min(stats["level"], len(LEVELS)-1)]
    
    keyboard = [
        [InlineKeyboardButton("🃏 Таро-расклад", callback_data="tarot")],
        [InlineKeyboardButton("🌟 Мой путь", callback_data="status")],
        [InlineKeyboardButton("🔒 Конфиденциальность", callback_data="privacy")]
    ]
    
    await update.message.reply_text(
        f"🔮 Эсмеральда приветствует!\n\n"
        f"Путь Мага: {level_name} ({stats['steps']}/{STEPS_PER_LEVEL})\n\n"
        f"🃏 Расклад на 78 карт Таро\n"
        f"💫 Теплая психологическая поддержка\n"
        f"✨ Без мистики и пафоса\n\n"
        f"Выбери:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML"
    )

async def privacy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🔒 Конфиденциальность:\n\n"
        "Сохраняю только:\n"
        "• Telegram ID\n"
        "• Уровень/шаги\n"
        "• Время раскладов\n\n"
        "/delete_me — удалить всё\n\n"
        "Не передаю данные. 18+",
        parse_mode="HTML"
    )

async def delete_me_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if user_id in premium_users:
        del premium_users[user_id]
        save_premium_users(premium_users)
    context.user_data.clear()
    await update.message.reply_text("✅ Данные удалены!")

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
        
        await query.edit_message_text(
            f"Твой путь: {level_name}\n"
            f"Шаги: {stats['steps']}/{STEPS_PER_LEVEL}\n"
            f"Бонусы: {stats.get('bonus_readings', 0)}\n"
            f"Статус: {'Премиум' if is_premium else 'Бесплатно'}",
            parse_mode="HTML"
        )
    elif query.data == "privacy":
        await privacy_command(update, context)

async def do_tarot_reading(query_or_update, context):
    can_use, msg = can_do_reading(context)
    if not can_use:
        if hasattr(query_or_update, 'edit_message_text'):
            await query_or_update.edit_message_text(msg)
        else:
            await query_or_update.message.reply_text(msg)
        return
    
    cards = random.sample(ALL_CARDS, 3)
    question = "Что важно знать человеку сегодня?"
    
    try:
        response = client.chat.completions.create(
            model="openai/gpt-4o-mini",
            messages=[{"role": "user", "content": build_tarot_prompt(cards, question)}]
        )
        reply = response.choices[0].message.content
    except:
        reply = "Ситуация: сейчас важный момент. Чувства: есть неуверенность. Действие: сделай маленький шаг."
    
    stats = user_stats(context)
    stats["last_reading"] = datetime.now()
    
    text = f"🃏 {cards[0]} – {cards[1]} – {cards[2]}\n\n{reply}{add_step(stats)}"
    
    if hasattr(query_or_update, 'edit_message_text'):
        await query_or_update.edit_message_text(text, parse_mode="HTML")
    else:
        await query_or_update.message.reply_text(text, parse_mode="HTML")

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await button_handler(update, context)

async def chat_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("💭 Расскажи или /start для меню")

if __name__ == "__main__":
    print("🤖 Эсмеральда готова!")
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("privacy", privacy_command))
    app.add_handler(CommandHandler("delete_me", delete_me_command))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chat_handler))
    
    print("✅ Запуск!")
    app.run_polling()
