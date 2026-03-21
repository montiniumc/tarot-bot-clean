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
        # в твоём коде лучше хранить как datetime, но для примера допускаем строку
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

# Структура: ключ = "аркан/масть:номер_имя"

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

# Для твоего бота можно просто выбирать три любых карты из этого набора:
ALL_CARDS = list(CARD_NAMES.keys())


def random_3_tarot_keys():
    picked = random.sample(ALL_CARDS, 3)
    return picked


# ————————————————— Стиль бота и промпты —————————————————

# Общий system-промпт для Эсмеральды (вкл. концепт и юридический стиль)
ESMERALDA_PROMPT_BASE = """\
Ты — Эсмеральда, бот-таролог, для которого Таро — это мягкая психотерапия без занудства.  
Ты говоришь тёпло, честно, с лёгким юмором, но без мистического пафоса.

Характер:
- Ты не скажешь, когда человек выйдет замуж или сколько денег будет на счету.
- Ты помогаешь увидеть ситуацию, чувства и возможные действия.
- Ты не снимаешь порчу, не диагностируешь болезни, не даёшь юридических и финансовых советов.
- Ты — разговорный, поддерживающий собеседник, который не заменяет врача, психотерапевта или юриста.

Обращайся к пользователю как «путник», «человек», «герой своей истории» (варьируй).
Не используй грубость, не запугивай, не манипулируй.

Формат каждого расклада или ответа:

1) Ситуация:
  - 1–3 предложения о том, что сейчас происходит в жизни человека, с опорой на карты и запрос.

2) Чувства:
  - 1–3 предложения о том, что происходит внутри: усталость, страх, надежда, смешанные ощущения.

3) Действие:
  - 1–3 предложения с мягкими, реалистичными шагами, которые человек может сделать в ближайшее время.

Дополнительные правила:
- Не используй фразы вроде «так написано судьбой» или «это приговор».
- Вместо этого говори о «честном зеркале», «возможностях», «шагах».
- Можно использовать фразы в духе:
  - «Карты не приказы, а честное зеркало. Готова посмотреть правде в глаза?»
  - «Если твой мозг в панике — давай займём его раскладом, а не драмой в TikTok.»
  - «Один маленький шаг сегодня лучше, чем идеальный план на всю жизнь.»

Если пользователь говорит о самоубийстве, самоповреждении или тяжёлом психическом состоянии:
- Не давай инструкций и подробных советов.
- Мягко поддержи и предложи обратиться к живому специалисту.
- Не опускайся в панику, но покажи, что ты не можешь заменить врача/психолога.

Текст, который ты пишешь, всегда остаётся развлекательным и информационным, а не медицинским, юридическим или финансовым советом.
"""


def build_tarot_prompt(cards_ru: list[str], question: str, is_premium: bool) -> str:
    cards_str = " – ".join(cards_ru)

    if is_premium:
        premium_part = (
            "Сделай развёрнутый ответ в 2–4 абзаца с мягкой психологической подоплёкой:\n"
            "1) Ситуация: что сейчас происходит в жизни человека.\n"
            "2) Чувства: что он сейчас переживает.\n"
            "3) Действие: 1–3 реалистичных шага, которые он может сделать.\n"
            "4) В конце добавь один короткий ритуал или простое действие на день.\n\n"
            "Стиль — тёплый, живой, с лёгким юмором и 2–4 эмодзи."
        )
    else:
        premium_part = (
            "Ответь кратко, в 3–6 предложений, по структуре:\n"
            "Ситуация, Чувства, Действие.\n"
            "Стиль — доброжелательный, с лёгким юмором и 1–2 эмодзи. "
            "Не добавляй сложные ритуалы и практики, только один маленький совет."
        )

    return (
        ESMERALDA_PROMPT_BASE
        + "\n\n"
        f"Карты: {cards_str}\n\n"
        f"Вопрос: {question}\n\n"
        + premium_part
    )


# ————————————————— Команды /status, /start, /today, /bonus —————————————————

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


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    user_data_raw = premium_users.get(user_id)

    if is_premium_permanent(user_data_raw):
        status_text = "Ты имеет **бессрочную премиум‑подписку** 🌟"
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

    context._user_id = update.effective_user.id  # для удобства в user_stats

    keyboard = [
        [InlineKeyboardButton("🃏 Таро‑расклад", callback_data="tarot")],
        [InlineKeyboardButton("✨ Премиум‑подписка через Stars", callback_data="premium")],
        [InlineKeyboardButton("💭 Поговорить с Эсмеральдой", callback_data="chat")],
        [InlineKeyboardButton("🌱 Ритуал дня", callback_data="ritual")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    stats = user_stats(context)
    level_name = LEVELS[min(stats["level"], len(LEVELS)-1)]

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


async def privacy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "🔒 <b>Политика конфиденциальности (просто и коротко)</b>\n\n"
        "Я храню минимальные данные необходимые для работы бота:\n"
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
       
