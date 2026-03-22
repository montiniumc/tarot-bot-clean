import os
import json
import random
from pathlib import Path
from datetime import datetime, timedelta
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    LabeledPrice
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)
from openai import OpenAI

# ——————————————————— ПЕРЕМЕННЫЕ СРЕДЫ ———————————————————
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENROUTER_KEY = os.getenv("OPENROUTER_KEY")
STARS_TOKEN = os.getenv("STARS_PROVIDER_TOKEN")  # для Telegram оплаты Stars

client = OpenAI(api_key=OPENROUTER_KEY, base_url="https://openrouter.ai/api/v1")

# ——————————————————— ФАЙЛЫ ДАННЫХ ———————————————————
PREMIUM_FILE = Path("premium_users.json")
CHAT_MEMORY_FILE = Path("chat_memory.json")
REFERRAL_FILE = Path("referrals.json")

premium_users = json.loads(PREMIUM_FILE.read_text(encoding="utf-8")) if PREMIUM_FILE.exists() else {}
chat_memory = json.loads(CHAT_MEMORY_FILE.read_text(encoding="utf-8")) if CHAT_MEMORY_FILE.exists() else {}
referrals = json.loads(REFERRAL_FILE.read_text(encoding="utf-8")) if REFERRAL_FILE.exists() else {}

def save_json(path: Path, data: dict):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

# ——————————————————— ПРЕМИУМ ———————————————————
def is_premium_permanent(user_data) -> bool:
    return user_data and user_data.get("premium") and user_data.get("permanent", False)

# ——————————————————— УРОВНИ И ЛИМИТЫ ———————————————————
LEVELS = ["Новичок", "Искатель", "Посвящённый", "Маг", "Верховный маг"]
STEPS_PER_LEVEL = 5
FREE_READING_COOLDOWN_HOURS = 24

def user_stats(context: ContextTypes.DEFAULT_TYPE):
    data = context.user_data
    if "level" not in data:
        data.update({
            "level": 0,
            "steps": 0,
            "last_free_reading_at": None,
            "bonus_readings": 0,
        })
    return data

def add_step(stats):
    stats["steps"] += 1
    if stats["steps"] < STEPS_PER_LEVEL:
        return f"Ты продвинулся по пути Мага на 1 шаг ({stats['steps']}/{STEPS_PER_LEVEL})."
    stats["steps"] = 0
    stats["level"] += 1
    lvl_name = LEVELS[min(stats["level"], len(LEVELS) - 1)]
    stats["bonus_readings"] = max(stats["bonus_readings"] + 1, 1)
    return f"Поздравляю! Ты стал {lvl_name}. Новый уровень — новый угол зрения на жизнь. Введи /bonus для бонусного расклада."

def can_do_free_reading(context: ContextTypes.DEFAULT_TYPE):
    stats = user_stats(context)
    user_id = str(context.user_data.get("id", context._user_id))
    is_prem = context.user_data.get("premium") or is_premium_permanent(premium_users.get(user_id))
    if is_prem:
        return True, None

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

# ——————————————————— КОЛОДА ТАРО 78 КАРТ ———————————————————
MAJORS = [
    ("0", "Шут"), ("1", "Маг"), ("2", "Жрица"), ("3", "Императрица"),
    ("4", "Император"), ("5", "Иерофант"), ("6", "Влюбленные"),
    ("7", "Колесница"), ("8", "Сила"), ("9", "Отшельник"), ("10", "Колесо Фортуны"),
    ("11", "Справедливость"), ("12", "Повешенный"), ("13", "Смерть"), ("14", "Умеренность"),
    ("15", "Дьявол"), ("16", "Башня"), ("17", "Звезда"), ("18", "Луна"), ("19", "Солнце"),
    ("20", "Суд"), ("21", "Мир"),
]
MINOR_SUITS = {"wands": "Жезлы", "cups": "Чаши", "swords": "Мечи", "pentacles": "Пентакли"}
MINOR_RANKS = ["Туз","2","3","4","5","6","7","8","9","10","Паж","Рыцарь","Королева","Король"]

CARD_NAMES = {}
for num, name in MAJORS:
    CARD_NAMES[f"major:{num}"] = name
for suit, suit_rus in MINOR_SUITS.items():
    for rank in MINOR_RANKS:
        CARD_NAMES[f"{suit}:{rank}"] = f"{rank} {suit_rus}"

ALL_CARDS = list(CARD_NAMES.keys())

def random_3_tarot():
    return random.sample(ALL_CARDS, 3)

def format_card(key):
    base = CARD_NAMES[key]
    if random.random() < 0.5:
        return f"{base} (перевернутая)"
    return base

# ——————————————————— PROMPTS ———————————————————
ESM_PROMPT_BASE = """Ты — Эсмеральда, бот-таролог, мягкая психотерапия без мистического пафоса.
Формат ответа:
1) Ситуация 2) Чувства 3) Действие
Не даешь медицинские, юридические или финансовые советы."""

def build_prompt(cards, question, is_premium):
    cards_str = " – ".join(cards)
    extra = "Дай развернутый ответ" if is_premium else "Дай краткий ответ в 3-6 предложений"
    return f"{ESM_PROMPT_BASE}\nКарты: {cards_str}\nВопрос: {question}\n{extra}"

# ——————————————————— КОНФИДЕНЦИАЛЬНОСТЬ ———————————————————
CONF_TEXT = """🔒 Политика конфиденциальности:
• Храним только user_id, уровень, премиум и бонусы
• Данные не продаются и не используются для рекламы
• Можно удалить /delete_me
• Пользователи старше 18 лет"""

# ——————————————————— КОМАНДЫ ———————————————————
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    context.user_data["id"] = user_id
    context.user_data["premium"] = is_premium_permanent(premium_users.get(user_id))
    stats = user_stats(context)
    lvl_name = LEVELS[min(stats["level"], len(LEVELS)-1)]

    keyboard = [
        [InlineKeyboardButton("🃏 Бесплатный расклад", callback_data="tarot")],
        [InlineKeyboardButton("💰 Премиум Stars", callback_data="buy_premium")],
        [InlineKeyboardButton("💬 Память диалога", callback_data="chat")],
        [InlineKeyboardButton("🌱 Ритуал дня", callback_data="ritual")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    welcome = "🌟 Премиум активен!" if context.user_data["premium"] else "🔮 Я Эсмеральда, бот-таролог"
    await update.message.reply_text(
        f"{welcome}\nТвой уровень: {lvl_name} ({stats['steps']}/{STEPS_PER_LEVEL})\n\n{CONF_TEXT}",
        reply_markup=reply_markup
    )

# ——————————————————— ТАРО РАСКЛАД С ВОПРОСОМ И ЛИМИТОМ ———————————————————
async def today_command(update: Update, context: ContextTypes.DEFAULT_TYPE, question=None):
    stats = user_stats(context)
    can_use, err = can_do_free_reading(context)

    if isinstance(update, Update) and update.callback_query:
        send = update.callback_query.message.reply_text
        uid = str(update.callback_query.from_user.id)
    else:
        send = update.message.reply_text
        uid = str(update.effective_user.id)

    if not can_use and not context.user_data.get("premium"):
        kb = [[InlineKeyboardButton("💰 Купить премиум", callback_data="buy_premium")]]
        await send(f"{err}\nДля расширенного расклада с подробным ответом и бонусами:",
                   reply_markup=InlineKeyboardMarkup(kb))
        return

    # Если вопрос не передан, спрашиваем его
    if not question:
        await send("❓ Какой вопрос ты хочешь задать таро? Напиши ответ в течение 2 минут.")

        def check(m):
            return m.from_user.id == int(uid) and m.text

        try:
            response = await context.application.wait_for(
                filters.TEXT & (~filters.COMMAND),
                timeout=120,
                check=check
            )
            question = response.text
        except TimeoutError:
            await send("⏰ Время ожидания вопроса истекло. Попробуй снова.")
            return

    # Генерация расклада
    cards_keys = random_3_tarot()
    cards = [format_card(k) for k in cards_keys]

    prompt = build_prompt(cards, question, context.user_data.get("premium"))
    try:
        resp = client.chat.completions.create(
            model="openai/gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}]
        )
        reply = resp.choices[0].message.content
    except Exception:
        reply = "🔮 Ошибка генерации…"

    msg = f"🃏 {' – '.join(cards)}\n\n{reply}\n\n{add_step(stats)}"

    # ———————————— Триггер ревности ————————————
    lower_text = question.lower()
    if any(kw in lower_text for kw in ["третье лицо","он с кем-то","она с кем-то","третий","третья"]):
        msg += "\n\n💔 Есть скрытый фактор — возможное третье лицо в ситуации."

    # ———————————— Автоворонка на премиум ————————————
    if not context.user_data.get("premium"):
        kb = [[InlineKeyboardButton("💰 Купить премиум", callback_data="buy_premium")]]
        await send(msg, reply_markup=InlineKeyboardMarkup(kb))
    else:
        await send(msg)

    mark_free_done(stats)

    # сохраняем диалог
    chat_memory.setdefault(uid, []).append({"time": datetime.now().isoformat(), "text": question})
    save_json(CHAT_MEMORY_FILE, chat_memory)

# ——————————————————— BUTTONS ———————————————————
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "tarot":
        await today_command(update, context)
    elif query.data == "buy_premium":
        if STARS_TOKEN:
            prices = [LabeledPrice(label="Премиум доступ 1 месяц", amount=50000)]
            await context.bot.send_invoice(
                chat_id=query.from_user.id,
                title="Премиум Stars",
                description="Доступ ко всем раскладам и бонусам",
                payload="premium_month",
                provider_token=STARS_TOKEN,
                currency="RUB",
                prices=prices,
                need_email=True,
                is_flexible=False
            )
        else:
            await query.edit_message_text(
                "💰 Оплата через Stars доступна прямо в Telegram. Ссылка на оплату: [оплатить](https://example.com)",
                parse_mode="Markdown"
            )
    elif query.data == "chat":
        await query.edit_message_text("💬 Пиши сюда, я буду помнить твой диалог ✨")
    elif query.data == "ritual":
        await query.edit_message_text("🌱 Ритуал дня: 5 минут без телефона")

# ——————————————————— ПАМЯТЬ ДИАЛОГА ———————————————————
async def chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    chat_memory.setdefault(uid, []).append({"time": datetime.now().isoformat(), "text": update.message.text})
    save_json(CHAT_MEMORY_FILE, chat_memory)
    await update.message.reply_text("💬 Я помню твой диалог. Продолжай…")

# ——————————————————— RUN ———————————————————
if __name__ == "__main__":
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), chat))

    print("🤖 BOT ESMERALDA STARTED!")
    app.run_polling()
