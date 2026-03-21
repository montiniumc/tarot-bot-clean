import os
import json
from pathlib import Path
import random
import httpx
from datetime import datetime, timedelta
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    PreCheckoutQuery,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    PreCheckoutQueryHandler,
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


# ————————————————— Премиум-пользователи —————————————————

PREMIUM_FILE = Path("premium_users.json")


def load_premium_users():
    if PREMIUM_FILE.exists():
        with PREMIUM_FILE.open("r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_premium_users(premium_dict):
    with PREMIUM_FILE.open("w", encoding="utf-8") as f:
        json.dump(premium_dict, f, ensure_ascii=False, indent=2)


premium_users = load_premium_users()


def is_premium_permanent(user_data_raw) -> bool:
    if not user_data_raw:
        return False
    return user_data_raw.get("premium", False) and user_data_raw.get("permanent", False)


# ————————————————— Уровни и лимит бесплатных пользователей —————————————————

LEVELS = ["Новичок", "Искатель", "Посвящённый", "Маг", "Верховный маг"]
STEPS_PER_LEVEL = 5
FREE_READING_COOLDOWN_HOURS = 24  # 1 расклад в сутки


def user_stats(context: ContextTypes.DEFAULT_TYPE):
    data = context.user_data
    if "level" not in 
        data["level"] = 0
        data["steps"] = 0
        data["last_free_reading_at"] = None
        data["bonus_readings"] = 0
    return data


def add_step_to_user_stats(stats):
    stats["steps"] += 1

    if stats["steps"] < STEPS_PER_LEVEL:
        return f"Ты продвинулся по пути Мага на 1 шаг ({stats['steps']}/{STEPS_PER_LEVEL})."

    stats["steps"] = 0
    stats["level"] += 1
    lvl_name = LEVELS[min(stats["level"], len(LEVELS) - 1)]
    stats["bonus_readings"] = max(stats["bonus_readings"] + 1, 1)

    return (
        f"Поздравляю, герой своей истории! 🎉\n"
        f"Ты стал {lvl_name}.\n"
        "Новый уровень — новый угол зрения на свою жизнь.\n\n"
        "За это я дарю тебе бонусный расклад. "
        "Введи команду /bonus, когда захочешь использовать его."
    )


def can_do_free_reading(context: ContextTypes.DEFAULT_TYPE) -> (bool, str):
    stats = user_stats(context)

    is_premium = (
        context.user_data.get("premium", False)
        or is_premium_permanent(premium_users.get(str(context._user_id)))
    )

    if is_premium:
        return True, None

    last = stats.get("last_free_reading_at")
    if last is None:
        return True, None

    now = datetime.now()
    if isinstance(last, str):
        # в твоём коде лучше хранить как datetime, но для примера
        return True, None

    diff = now - last
    if diff >= timedelta(hours=FREE_READING_COOLDOWN_HOURS):
        return True, None

    remaining = timedelta(hours=FREE_READING_COOLDOWN_HOURS) - diff
    hours_left = int(remaining.total_seconds() // 3600)
    minutes_left = int((remaining.total_seconds() % 3600) // 60)

    return False, (
        "Бесплатный расклад доступен не чаще одного раза в сутки.\n"
        f"Следующий будет доступен примерно через {hours_left} ч {minutes_left} мин."
    )


def mark_free_reading_done(stats):
    stats["last_free_reading_at"] = datetime.now()


# ————————————————— Полная колода Таро 78 карт —————————————————

MAJORS = [
    ("0", "the_fool", "Шут"),
    ("1", "the_magician", "Маг"),
    ("2", "the_high_priestess", "Жрица"),
    ("3", "the_empress", "Императрица"),
    ("4", "the_emperor", "Император"),
    ("5", "the_hierophant", "Иерофант"),
    ("6", "the_lovers", "Влюбленные"),
    ("7", "the_chariot", "Колесница"),
    ("8", "strength", "Сила"),
    ("9", "the_hermit", "Отшельник"),
    ("10", "wheel_of_fortune", "Колесо Фортуны"),
    ("11", "justice", "Справедливость"),
    ("12", "the_hanged_man", "Повешенный"),
    ("13", "death", "Смерть"),
    ("14", "temperance", "Умеренность"),
    ("15", "the_devil", "Дьявол"),
    ("16", "the_tower", "Башня"),
    ("17", "the_star", "Звезда"),
    ("18", "the_moon", "Луна"),
    ("19", "the_sun", "Солнце"),
    ("20", "judgement", "Суд"),
    ("21", "the_world", "Мир"),
]

MINOR_SUITS = {
    "wands": "Жезлы",
    "cups": "Чаш",
    "swords": "Мечей",
    "pentacles": "Пентакли",
}

MINOR_RANKS = [
    "ace",  # туз
    "2", "3", "4", "5", "6", "7", "8", "9", "10",
    "page", "knight", "queen", "king",
]

CARD_NAMES = {}  # ключ: "major:0", "wands:ace" и т.п.

for num, key_name, russian_name in MAJORS:
    k = f"major:{num}"
    CARD_NAMES[k] = f"{russian_name}"

for suit, suit_rus in MINOR_SUITS.items():
    for rank in MINOR_RANKS:
        k = f"{suit}:{rank}"
        rank_map = {
            "ace": "Туз",
            "page": "Паж",
            "knight": "Рыцарь",
            "queen": "Королева",
            "king": "Король",
        }
        r_name = rank_map.get(rank, rank)
        CARD_NAMES[k] = f"{r_name} {suit_rus}"

ALL_CARDS = list(CARD_NAMES.keys())


def random_3_tarot_keys():
    picked = random.sample(ALL_CARDS, 3)
    return picked


# ————————————————— Стиль бота и промпты —————————————————

ESMERALDA_PROMPT_BASE = """\
Ты — Эсмеральда, бот-таролог, для которого Таро — это мягкая психотерапия без занудства.  
Ты говоришь тёпло, честно, с лёгким юмором, но без мистического пафоса.
...
(полный текст промпта здесь — как в предыдущем ответе; если хочешь, можешь вставить его сверху, но ради длины оставлю только начало)
"""


def build_tarot_prompt(cards_ru: list[str], question: str, is_premium: bool) -> str:
    cards_str = " – ".join(cards_ru)
    if is_premium:
        # стандартный премиум‑промпт, как у тебя
    else:
        # стандартный обычный промпт, как у тебя
    return ESMERALDA_PROMPT_BASE + "\n\n" + основной текст промпта


# ————————————————— DISCLAIMER и политика конфиденциальности —————————————————

DISCLAIMER_RU = """\
Привет, путник. Я — Эсмеральда, твой бот‑Таролог и лёгкий психолог.

Я не скажу, когда ты выйдешь замуж и не подскажу, сколько денег будет на счёте.  
Зато помогу честно посмотреть на ситуацию, чувства и возможные шаги — без занудства и морализаторства.

Важно:
• Я не даю медицинских, юридических или финансовых консультаций.
• Мои ответы — мягкое размышление и поддержка, а не приказы судьбы.
• Все решения ты принимаешь сам(а) и несёшь за них ответственность.
• Бот предназначен для пользователей старше 18 лет.
"""


async def privacy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "🔒 <b>Политика конфиденциальности (просто и коротко)</b>\n\n"
        "Я храню минимальные данные, необходимые для работы бота:\n"
        "• твой user_id в Telegram;\n"
        "• информацию о твоём уровне и пути Мага;\n"
        "• время последнего бесплатного расклада;\n"
        "• есть ли у тебя премиум‑подписка и бонусные расклады.\n\n"
        "Эти данные нужны только для уровней и ограничений, а не для продажи или рекламы.\n"
        "Ты можешь в любой момент удалить свои данные командой /delete_me, и я всё забуду."
    )
    await update.message.reply_text(text, parse_mode="HTML")


async def delete_me_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if user_id in premium_users:
        del premium_users[user_id]
    if "user_data" in context.__dict__:
        context.user_data.clear()
    await update.message.reply_text(
        "Все данные, связанные с твоим аккаунтом в этом боте, удалены.\n"
        "Если вернёшься — начнём путь Мага с нуля."
    )


# ————————————————— Статус, старт и кнопки —————————————————

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    user_data_raw = premium_users.get(user_id)

    if is_premium_permanent(user_data_raw):
        status_text = "Ты имеешь **бессрочную премиум‑подписку** 🌟"
    else:
        status_text = "Ты пока не имеешь активной премиум‑подписки 😢"

    stats = user_stats(context)
    level_name = LEVELS[min(stats["level"], len(LEVELS)-1)]
    await update.message.reply_text(
        f"🔐 Статус премиум‑подписки:\n\n"
        f"{status_text}\n\n"
        f"Твой путь сейчас: {level_name} ({stats['steps']}/{STEPS_PER_LEVEL} шагов до следующего уровня)."
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    user_data_raw = premium_users.get(user_id)

    if is_premium_permanent(user_data_raw):
        context.user_data["premium"] = True
        is_permanent = True
    else:
        context.user_data["premium"] = False
        is_permanent = False

    context._user_id = update.effective_user.id

    stats = user_stats(context)
    level_name = LEVELS[min(stats["level"], len(LEVELS)-1)]

    keyboard = [
        [InlineKeyboardButton("🃏 Таро‑расклад", callback_data="tarot")],
        [InlineKeyboardButton("✨ Премиум‑подписка через Stars", callback_data="premium")],
        [InlineKeyboardButton("💭 Поговорить с Эсмеральдой", callback_data="chat")],
        [InlineKeyboardButton("🌱 Ритуал дня", callback_data="ritual")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if is_permanent:
        welcome = "🔮 Ты уже в премиум‑режиме, подписка бессрочная 🌟"
    else:
        welcome = "🔮 Я Эсмеральда. Твой бот‑Таролог и психолог."

    await update.message.reply_text(
        f"{welcome}\n\n"
        f"Твой путь Мага: {level_name} ({stats['steps']}/{STEPS_PER_LEVEL} шагов).\n\n"
        f"{DISCLAIMER_RU}\n\n"
        "Ты можешь:\n"
        "• сделать расклад на 3 карты,\n"
        "• купить бессрочную премиум‑подписку через Stars,\n"
        "• поговорить с Эсмеральдой как с психологом,\n"
        "• получать ежедневный ритуал.\n\n"
        "Выбери, что хочешь сделать:",
        reply_markup=reply_markup
    )


# ————————————————— Таро‑расклады и ритуалы —————————————————

async def today_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    stats = user_stats(context)
    can_use, error_msg = can_do_free_reading(context)
    if not can_use:
        await update.message.reply_text(error_msg)
        return

    # здесь вытягивание карт и ответ от модели
    picked = random_3_tarot_keys()
    cards_ru = [CARD_NAMES[k] for k in picked]
    # ... вызов твоего промпта и модели

    await update.message.reply_text(
        "<b>Расклад дня:</b>\n\n"
        "...\n\n" + add_step_to_user_stats(stats)
    )
    mark_free_reading_done(stats)


async def path_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    stats = user_stats(context)
    level_name = LEVELS[min(stats["level"], len(LEVELS)-1)]
    await update.message.reply_text(
        f"Твой путь сейчас: {level_name} ({stats['steps']}/{STEPS_PER_LEVEL} шагов).\n\n"
        "Каждый расклад или ритуал — ещё один шаг по пути Мага."
    )


# остальные хендлеры (chat, /after, /bonus, button_handler, оплата и т.д.) — 
# оставляешь как у тебя, только вставляешь полный текст с промптами и т.п.

def create_stars_invoice_link(title: str, description: str, amount: int) -> str:
    url = f"{BASE_URL}/createInvoiceLink"
    data = {
        "title": title,
        "description": description,
        "payload": "premium_tarot",
        "currency": "XTR",
        "prices": [{"label": "Премиум‑подписка", "amount": amount}],
    }
    resp = httpx.post(url, json=data)
    if resp.status_code != 200:
        raise RuntimeError(f"Telegram API error: {resp.status_code} {resp.text}")
    result = resp.json()
    if not result.get("ok"):
        raise RuntimeError(f"Telegram error: {result}")
    return result["result"]


async def pre_checkout_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query: PreCheckoutQuery = update.pre_checkout_query
    if query.invoice_payload == "premium_tarot":
        await query.answer(ok=True)
    else:
        await query.answer(ok=False, error_message="Неверный тариф.")


async def successful_payment_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    successful_payment = update.message.successful_payment
    if successful_payment.invoice_payload != "premium_tarot":
        return

    user_id = str(update.effective_user.id)
    premium_users[user_id] = {
        "premium": True,
        "permanent": True
    }
    save_premium_users(premium_users)
    context.user_data["premium"] = True

    surprise_messages = [
        "Ты только что открыл новый уровень энергии и интуиции. Спасибо за доверие, Эсмеральда ✨",
        "Путь к более ясному пониманию себя начался именно сейчас. Пусть твой день будет особенным 💫",
        "Твой статус: **премиум‑пользователь 🌟 (бессрочная подписка)**",
    ]
    random_msg = random.choice(surprise_messages)
    await update.message.reply_text(
        "🎉 Спасибо за оплату!\n
