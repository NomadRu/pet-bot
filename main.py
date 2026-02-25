import asyncio
import os
import sqlite3
import random
from datetime import datetime, date

from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

TOKEN = os.getenv("BOT_TOKEN")
bot = Bot(token=TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# ====================== БАЗА ДАННЫХ ======================
conn = sqlite3.connect('pets.db', check_same_thread=False)
cur = conn.cursor()

cur.execute('''CREATE TABLE IF NOT EXISTS pairs (
    pair_id TEXT PRIMARY KEY,
    user1_id INTEGER,
    user2_id INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)''')

cur.execute('''CREATE TABLE IF NOT EXISTS pets (
    pair_id TEXT PRIMARY KEY,
    name TEXT DEFAULT 'Зайка',
    hunger INTEGER DEFAULT 80,
    happiness INTEGER DEFAULT 50,
    cleanliness INTEGER DEFAULT 70,
    level INTEGER DEFAULT 1,
    xp INTEGER DEFAULT 0,
    daily_score INTEGER DEFAULT 0,
    last_reset DATE DEFAULT CURRENT_DATE,
    last_decay TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)''')
conn.commit()


# ====================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ======================
def get_pair(user_id):
    cur.execute("SELECT pair_id, user1_id, user2_id FROM pairs WHERE user1_id=? OR user2_id=?", (user_id, user_id))
    row = cur.fetchone()
    if row:
        pair_id, u1, u2 = row
        other = u2 if u1 == user_id else u1
        return pair_id, other
    return None, None


def get_pet(pair_id):
    cur.execute("SELECT name, hunger, happiness, cleanliness, level, xp, daily_score, last_decay FROM pets WHERE pair_id=?", (pair_id,))
    row = cur.fetchone()
    if row:
        return {
            'name': row[0], 'hunger': row[1], 'happiness': row[2], 'cleanliness': row[3],
            'level': row[4], 'xp': row[5], 'daily_score': row[6], 'last_decay': row[7]
        }
    return None


def update_pet(pair_id, **kwargs):
    for field, value in kwargs.items():
        cur.execute(f"UPDATE pets SET {field}=? WHERE pair_id=?", (value, pair_id))
    conn.commit()


def reset_daily_if_needed(pair_id):
    cur.execute("SELECT last_reset FROM pets WHERE pair_id=?", (pair_id,))
    last = cur.fetchone()[0]
    today = date.today().isoformat()
    if last != today:
        cur.execute("UPDATE pets SET daily_score=0, last_reset=? WHERE pair_id=?", (today, pair_id))
        conn.commit()


def progress_bar(value):
    filled = int(value / 10)
    return "█" * filled + "░" * (10 - filled)


def get_zayka_mood(pet):
    avg = (pet['hunger'] + pet['happiness'] + pet['cleanliness']) // 3
    if avg < 30: return "🥺💔", "Зайка очень грустит... 😢"
    if avg < 50: return "🥺", "Зайка немного грустит..."
    if avg < 70: return "🐰", "Зайка спокойный и милый"
    if avg < 85: return "🥰", "Зайка очень счастлив!"
    return "✨", "Зайка сияет от любви к вам 💕"


def cute_reaction(action):
    reactions = {
        "feed": ["Ням-ням! 🥕", "Зайка обнимает за вкусняшку 💕"],
        "play": ["Зайка прыгает от радости! 🥰", "Так весело!"],
        "clean": ["Теперь Зайка пушистый и пахнет клубничкой ✨"],
        "pet": ["Муррр~ Зайка тает от ласки 🥹"],
        "miss": ["Зайка тоже скучает и прижимается к вам обоим 🥺💕"]
    }
    return random.choice(reactions.get(action, ["Зайка очень рад!"]))


def main_menu(name="Зайка"):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🍎 Покормить", callback_data="feed"),
         InlineKeyboardButton(text="🎾 Поиграть", callback_data="play"),
         InlineKeyboardButton(text="🛁 Помыть", callback_data="clean")],
        [InlineKeyboardButton(text="🤗 Погладить", callback_data="pet"),
         InlineKeyboardButton(text="💌 Я скучаю", callback_data="miss"),
         InlineKeyboardButton(text="📊 Статус", callback_data="info")],
        [InlineKeyboardButton(text="✏️ Переименовать", callback_data="rename"),
         InlineKeyboardButton(text="🚪 Выйти из пары", callback_data="leave")]
    ])
    return kb


# ====================== FSM ======================
class RenameState(StatesGroup):
    waiting_name = State()


# ====================== ФОНОВЫЕ ЗАДАЧИ ======================
async def decay_task():
    while True:
        await asyncio.sleep(300)  # каждые 5 минут проверяем
        now = datetime.now()
        cur.execute("SELECT pair_id, last_decay, hunger, happiness, cleanliness FROM pets")
        pets = cur.fetchall()

        for pair_id, last_decay_str, h, ha, c in pets:
            last_decay = datetime.fromisoformat(last_decay_str)
            minutes_passed = (now - last_decay).total_seconds() / 60

            if minutes_passed >= 30:
                hours = minutes_passed / 60

                new_hunger = max(0, h - int(hours * 6))      # -6 за час голода
                new_happiness = max(0, ha - int(hours * 4))  # -4 за час
                new_clean = max(0, c - int(hours * 3.5))     # -3.5 за час

                update_pet(pair_id,
                           hunger=new_hunger,
                           happiness=new_happiness,
                           cleanliness=new_clean,
                           last_decay=now.isoformat())

                # уведомление, если совсем плохо
                if (new_hunger + new_happiness + new_clean) / 3 < 25:
                    pair_id, other = get_pair(list(cur.execute("SELECT user1_id FROM pairs WHERE pair_id=?", (pair_id,)).fetchone())[0])  # упрощённо
                    try:
                        await bot.send_message(other, f"🥺 Наш {get_pet(pair_id)['name']} очень грустит... Приходи скорее! 💔")
                    except:
                        pass


# ====================== ХЭНДЛЕРЫ ======================
@dp.message(CommandStart())
async def start(message: Message):
    user_id = message.from_user.id
    pair_id, other = get_pair(user_id)

    if pair_id:
        reset_daily_if_needed(pair_id)
        pet = get_pet(pair_id)
        await message.answer(f"🐰 С возвращением к {pet['name']} (уровень {pet['level']})!", reply_markup=main_menu(pet['name']))
        return

    text = message.text or ""
    if 'ref_' in text:
        try:
            ref_id = int(text.split('ref_')[1])
            if ref_id == user_id:
                await message.answer("Это твоя ссылка 😉")
                return
            pair_id = f"{min(ref_id, user_id)}_{max(ref_id, user_id)}"
            cur.execute("INSERT OR IGNORE INTO pairs (pair_id, user1_id, user2_id) VALUES (?, ?, ?)", (pair_id, ref_id, user_id))
            cur.execute("INSERT OR IGNORE INTO pets (pair_id, last_decay) VALUES (?, ?)", (pair_id, datetime.now().isoformat()))
            conn.commit()

            await message.answer("✅ Общий Зайка создан! 🐰 Теперь вы вместе за ним ухаживаете!")
            pet = get_pet(pair_id)
            await message.answer(f"Выбери действие для {pet['name']}:", reply_markup=main_menu(pet['name']))

            # уведомление первому человеку
            try:
                await bot.send_message(ref_id, f"❤️ {message.from_user.first_name} присоединился! У нас теперь общий Зайка! 🐰")
            except:
                pass
        except:
            await message.answer("Неверная ссылка 😔")
    else:
        bot_info = await bot.get_me()
        ref_link = f"https://t.me/{bot_info.username}?start=ref_{user_id}"
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📋 Поделиться ссылкой", url=ref_link)]])
        await message.answer(
            f"Привет! 💕\nЧтобы ухаживать за одним Зайкой вдвоём — поделись этой ссылкой со своим человеком:\n\n{ref_link}",
            reply_markup=kb
        )


@dp.callback_query(lambda c: c.data in ["feed", "play", "clean", "pet", "miss"])
async def do_action(callback: CallbackQuery):
    user_id = callback.from_user.id
    pair_id, other = get_pair(user_id)
    if not pair_id:
        return

    reset_daily_if_needed(pair_id)
    pet = get_pet(pair_id)

    # Cooldown 8 сек
    if (datetime.now() - datetime.fromisoformat(pet['last_decay'])).total_seconds() < 8:
        await callback.answer("Подожди немного 🐰", show_alert=True)
        return

    xp_gain = 0
    if callback.data == "feed":
        update_pet(pair_id, hunger=min(100, pet['hunger'] + 22))
        xp_gain = 15
        action_text = "покормил"
    elif callback.data == "play":
        update_pet(pair_id, happiness=min(100, pet['happiness'] + 18))
        xp_gain = 12
        action_text = "поиграл"
    elif callback.data == "clean":
        update_pet(pair_id, cleanliness=min(100, pet['cleanliness'] + 25))
        xp_gain = 14
        action_text = "помыл"
    elif callback.data == "pet":
        update_pet(pair_id, happiness=min(100, pet['happiness'] + 25))
        xp_gain = 10
        action_text = "погладил"
    elif callback.data == "miss":
        update_pet(pair_id, daily_score=pet['daily_score'] + 1)
        xp_gain = 5
        action_text = "сказал, что скучает"
        try:
            await bot.send_message(other, f"❤️ {callback.from_user.first_name} скучает по тебе... 🥺\nПриходи скорее к нашему Зайке 💕")
        except:
            pass

    # Добавляем опыт и проверяем левел-ап
    new_xp = pet['xp'] + xp_gain
    new_level = pet['level']
    while new_xp >= 100:
        new_xp -= 100
        new_level += 1
        # бонус при левел-апе
        update_pet(pair_id, hunger=min(100, pet['hunger'] + 10), happiness=min(100, pet['happiness'] + 10))

    update_pet(pair_id, xp=new_xp, level=new_level, last_decay=datetime.now().isoformat())

    pet = get_pet(pair_id)
    emoji, mood = get_zayka_mood(pet)
    reaction = cute_reaction(callback.data)

    await callback.message.edit_text(
        f"{emoji} {reaction}\n\n"
        f"🐰 {pet['name']} (уровень {pet['level']})\n"
        f"Голод: {pet['hunger']}% {progress_bar(pet['hunger'])}\n"
        f"Счастье: {pet['happiness']}% {progress_bar(pet['happiness'])}\n"
        f"Чистота: {pet['cleanliness']}% {progress_bar(pet['cleanliness'])}\n"
        f"XP: {pet['xp']}/100",
        reply_markup=main_menu(pet['name'])
    )

    if callback.data != "miss":
        try:
            await bot.send_message(other, f"❤️ {callback.from_user.first_name} {action_text} нашего {pet['name']}!\n{reaction}")
        except:
            pass


@dp.callback_query(lambda c: c.data == "info")
async def show_info(callback: CallbackQuery):
    user_id = callback.from_user.id
    pair_id, other = get_pair(user_id)
    if not pair_id:
        return
    reset_daily_if_needed(pair_id)
    pet = get_pet(pair_id)

    try:
        other_chat = await bot.get_chat(other)
        partner = f"@{other_chat.username}" if other_chat.username else f"ID {other}"
    except:
        partner = f"ID {other}"

    days = (datetime.now() - datetime.fromisoformat(
        cur.execute("SELECT created_at FROM pairs WHERE pair_id=?", (pair_id,)).fetchone()[0]
    )).days

    await callback.message.edit_text(
        f"🐰 {pet['name']} (уровень {pet['level']})\n\n"
        f"Голод: {pet['hunger']}% {progress_bar(pet['hunger'])}\n"
        f"Счастье: {pet['happiness']}% {progress_bar(pet['happiness'])}\n"
        f"Чистота: {pet['cleanliness']}% {progress_bar(pet['cleanliness'])}\n"
        f"XP: {pet['xp']}/100\n\n"
        f"Ты в паре с {partner} 💕\n"
        f"Вместе уже {days} дней\n"
        f"Сегодня вместе: {pet['daily_score']} раз ❤️",
        reply_markup=main_menu(pet['name'])
    )


@dp.callback_query(lambda c: c.data == "rename")
async def start_rename(callback: CallbackQuery, state: FSMContext):
    await state.set_state(RenameState.waiting_name)
    await callback.message.edit_text(
        "✏️ Введи новое имя для нашего Зайки (до 20 символов):",
        reply_markup=None
    )


@dp.message(RenameState.waiting_name)
async def process_new_name(message: Message, state: FSMContext):
    name = message.text.strip()[:20]
    if len(name) < 2:
        await message.answer("Имя слишком короткое 😔 Попробуй ещё раз:")
        return

    user_id = message.from_user.id
    pair_id, _ = get_pair(user_id)
    if not pair_id:
        await state.clear()
        return

    update_pet(pair_id, name=name)
    pet = get_pet(pair_id)

    await message.answer(f"✅ Зайка теперь зовётся **{name}**! 🐰", reply_markup=main_menu(name))
    await state.clear()


@dp.callback_query(lambda c: c.data == "leave")
async def start_leave(callback: CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Да, выйти ❌", callback_data="leave_confirm")],
        [InlineKeyboardButton(text="Нет, остаться ❤️", callback_data="cancel")]
    ])
    await callback.message.edit_text(
        "🚪 Ты точно хочешь выйти из пары?\nЗайка останется у второго человека.",
        reply_markup=kb
    )


@dp.callback_query(lambda c: c.data == "leave_confirm")
async def confirm_leave(callback: CallbackQuery):
    user_id = callback.from_user.id
    pair_id, other = get_pair(user_id)
    if not pair_id:
        return

    cur.execute("DELETE FROM pairs WHERE pair_id=?", (pair_id,))
    cur.execute("DELETE FROM pets WHERE pair_id=?", (pair_id,))
    conn.commit()

    await callback.message.edit_text("😢 Ты вышел из пары. Зайка теперь только у второго человека.")
    try:
        await bot.send_message(other, "💔 Твой человек вышел из пары... Зайка теперь только твой.")
    except:
        pass


@dp.callback_query(lambda c: c.data == "cancel")
async def cancel_action(callback: CallbackQuery):
    pair_id, _ = get_pair(callback.from_user.id)
    pet = get_pet(pair_id)
    await callback.message.edit_text("Хорошо, остаёмся вместе! ❤️", reply_markup=main_menu(pet['name']))


# ====================== ЗАПУСК ======================
async def main():
    asyncio.create_task(decay_task())   # запуск decay
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
