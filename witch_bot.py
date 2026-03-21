import os
import json
import random
from datetime import datetime, timedelta
from pathlib import Path
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler,
    PreCheckoutQueryHandler, ContextTypes, filters
)
from openai import OpenAI

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENROUTER_KEY = os.getenv("OPENROUTER_KEY")

client = OpenAI(api_key=OPENROUTER_KEY, base_url="https://openrouter.ai/api/v1")

# ————————————————— Премиум-пользователи —————————————————
PREMIUM_FILE = Path("premium_users.json")
def load_premium_users():
    if PREMIUM_FILE.exists():
        with PREMIUM_FILE.open("r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_premium_users(data):
    with PREMIUM_FILE.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

premium_users = load_premium_users()
def is_premium_permanent(data):
    return data.get("premium", False) and data.get("permanent", False)

# ————————————————— Уровни и лимит бесплатных пользователей —————————————————
LEVELS = ["Новичок", "Искатель", "Посвящённый", "Маг", "Верховный маг"]
STEPS_PER_LEVEL = 5
FREE_READING_COOLDOWN_HOURS = 24

def user_stats(context: ContextTypes.DEFAULT_TYPE):
    data = context.user_data
    if "level" not in data:
        data.update({"level":0, "steps":0, "last_free":None, "bonus":0, "dialog":[]})
    return data

def add_step(stats):
    stats["steps"] +=1
    if stats["steps"]<STEPS_PER_LEVEL:
        return f"Ты продвинулся на 1 шаг ({stats['steps']}/{STEPS_PER_LEVEL})."
    stats["steps"]=0
    stats["level"]+=1
    stats["bonus"]=max(stats["bonus"]+1,1)
    lvl_name = LEVELS[min(stats["level"], len(LEVELS)-1)]
    return f"Поздравляю! 🎉 Ты стал {lvl_name}. Введи /bonus для бонусного расклада."

def can_free(context):
    stats=user_stats(context)
    is_premium = context.user_data.get("premium",False) or is_premium_permanent(premium_users.get(str(context.user.id)))
    if is_premium: return True, None
    last=stats.get("last_free")
    now=datetime.now()
    if last is None: return True,None
    if isinstance(last,str): return True,None
    diff = now-last
    if diff >= timedelta(hours=FREE_READING_COOLDOWN_HOURS): return True,None
    rem = timedelta(hours=FREE_READING_COOLDOWN_HOURS)-diff
    return False,f"Бесплатный расклад через {int(rem.total_seconds()//3600)} ч {int((rem.total_seconds()%3600)//60)} мин."

def mark_free_done(stats):
    stats["last_free"]=datetime.now()

# ————————————————— Карты Таро (78) + перевернутые —————————————————
MAJORS=[("0","the_fool","Шут"),("1","the_magician","Маг"),("2","the_high_priestess","Жрица"),
        ("3","the_empress","Императрица"),("4","the_emperor","Император"),("5","the_hierophant","Иерофант"),
        ("6","the_lovers","Влюбленные"),("7","the_chariot","Колесница"),("8","strength","Сила"),
        ("9","the_hermit","Отшельник"),("10","wheel_of_fortune","Колесо Фортуны"),("11","justice","Справедливость"),
        ("12","the_hanged_man","Повешенный"),("13","death","Смерть"),("14","temperance","Умеренность"),
        ("15","the_devil","Дьявол"),("16","the_tower","Башня"),("17","the_star","Звезда"),
        ("18","the_moon","Луна"),("19","the_sun","Солнце"),("20","judgement","Суд"),("21","the_world","Мир")]
MINOR_SUITS={"wands":"Жезлы","cups":"Чаш","swords":"Мечей","pentacles":"Пентакли"}
MINOR_RANKS=["ace","2","3","4","5","6","7","8","9","10","page","knight","queen","king"]

CARD_NAMES={}
for num,key,rus in MAJORS: CARD_NAMES[f"major:{num}"]=rus
for suit,rus in MINOR_SUITS.items():
    for rank in MINOR_RANKS:
        rank_map={"ace":"Туз","page":"Паж","knight":"Рыцарь","queen":"Королева","king":"Король"}
        name=rank_map.get(rank,rank)
        CARD_NAMES[f"{suit}:{rank}"]=name+" "+rus

ALL_CARDS=list(CARD_NAMES.keys())
def random_3_tarot(): return [random.choice(ALL_CARDS)+(" (перевернутая)" if random.random()<0.5 else "") for _ in range(3)]
def format_card(k): return k

# ————————————————— Промпты и стиль —————————————————
ESM_PROMPT_BASE="""Ты — Эсмеральда, бот-таролог, мягкая психотерапия, честно и с юмором. Формат: Ситуация, Чувства, Действие. Не медицинская/юридическая/финансовая консультация."""

def build_prompt(cards:list, question:str, premium:bool):
    cards_str=" – ".join(cards)
    if premium:
        extra="Развёрнуто 2-4 абзаца, добавь простой ритуал, стиль тёплый, юмор."
    else:
        extra="Кратко 3-6 предложений, стиль доброжелательный."
    return f"{ESM_PROMPT_BASE}\n\nКарты: {cards_str}\nВопрос: {question}\n{extra}"

# ————————————————— Конфиденциальность —————————————————
PRIVACY="""Я храню минимальные данные: user_id, уровень, бонусы, премиум, время последнего бесплатного. 
Данные нужны только для работы бота. Можно удалить через /delete_me. Всё согласно нормам РФ."""

# ————————————————— Команды —————————————————
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id=str(update.effective_user.id)
    if is_premium_permanent(premium_users.get(user_id)):
        context.user_data["premium"]=True
    else:
        context.user_data["premium"]=False
    stats=user_stats(context)
    lvl_name=LEVELS[min(stats["level"],len(LEVELS)-1)]
    kb=[[InlineKeyboardButton("🃏 Бесплатный расклад",callback_data="tarot")],
        [InlineKeyboardButton("💰 Купить премиум",callback_data="buy_premium")]]
    await update.message.reply_text(f"Привет! Твой путь: {lvl_name} ({stats['steps']}/{STEPS_PER_LEVEL})\n\n{PRIVACY}", reply_markup=InlineKeyboardMarkup(kb))

async def delete_me(update,context):
    uid=str(update.effective_user.id)
    if uid in premium_users: del premium_users[uid]; save_premium_users(premium_users)
    context.user_data.clear()
    await update.message.reply_text("Данные удалены.")

async def status(update,context):
    stats=user_stats(context)
    lvl=LEVELS[min(stats["level"],len(LEVELS)-1)]
    premium="🌟 Бессрочная премиум" if context.user_data.get("premium") else "😢 Нет премиум"
    await update.message.reply_text(f"{premium}\nПуть: {lvl} ({stats['steps']}/{STEPS_PER_LEVEL})")

# ————————————————— Расклады —————————————————
async def today_command(update,context,question="Как дела?"):
    stats=user_stats(context)
    can,err=can_free(context)
    send=update.message.reply_text if update.message else update.callback_query.message.reply_text
    if not can:
        kb=[[InlineKeyboardButton("💰 Купить премиум",callback_data="buy_premium")]]
        await send(f"{err}", reply_markup=InlineKeyboardMarkup(kb))
        return
    cards=random_3_tarot()
    prompt=build_prompt(cards,question,context.user_data.get("premium",False))
    try:
        resp=client.chat.completions.create(model="openai/gpt-4o-mini", messages=[{"role":"user","content":prompt}])
        reply=resp.choices[0].message.content
    except Exception: reply="🔮 Ошибка генерации"
    await send(f"🃏 {' – '.join(cards)}\n\n{reply}\n\n{add_step(stats)}")
    mark_free_done(stats)

# ————————————————— Кнопки —————————————————
async def button(update,context):
    q=update.callback_query
    await q.answer()
    if q.data=="tarot": await today_command(update,context)
    elif q.data=="buy_premium":
        prices=[LabeledPrice("Премиум",1000)]
        await q.message.reply_invoice(title="Премиум", description="Бессрочная подписка", payload="premium", provider_token=os.getenv("STARS_TOKEN"), currency="RUB", prices=prices)

# ————————————————— Платёж —————————————————
async def pre_checkout(update,context):
    await update.pre_checkout_query.answer(ok=True)

async def successful(update,context):
    uid=str(update.effective_user.id)
    premium_users[uid]={"premium":True,"permanent":True}
    save_premium_users(premium_users)
    await update.message.reply_text("🌟 Премиум активирован!")

# ————————————————— Сообщения —————————————————
async def chat(update,context):
    context.user_data.setdefault("dialog",[]).append(update.message.text)
    await update.message.reply_text("💭 Я тебя слушаю…")

# ————————————————— Запуск —————————————————
if __name__=="__main__":
    app=ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start",start))
    app.add_handler(CommandHandler("status",status))
    app.add_handler(CommandHandler("delete_me",delete_me))
    app.add_handler(CallbackQueryHandler(button))
    app.add_handler(MessageHandler(filters.TEXT&(~filters.COMMAND),chat))
    app.add_handler(PreCheckoutQueryHandler(pre_checkout))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT,successful))
    print("🤖 BOT ESMERALDA STARTED!")
    app.run_polling()
