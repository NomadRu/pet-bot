import asyncio
import logging
import os
import sqlite3
import random
from datetime import datetime
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

TOKEN = os.getenv("BOT_TOKEN")

bot = Bot(token=TOKEN)
dp = Dispatcher()

# База
conn = sqlite3.connect('pets.db', check_same_thread=False)
cur = conn.cursor()
cur.execute('''CREATE TABLE IF NOT EXISTS pairs (
    pair_id TEXT PRIMARY KEY, user1_id INTEGER, user2_id INTEGER, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)''')
cur.execute('''CREATE TABLE IF NOT EXISTS pets (
    pair_id TEXT PRIMARY KEY, name TEXT DEFAULT 'Зайка', photo_id TEXT,
    hunger INTEGER DEFAULT 80, happiness INTEGER DEFAULT 50, cleanliness INTEGER DEFAULT 70, 
    level INTEGER DEFAULT 1, last_update TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)''')
conn.commit()

waiting_for_photo = {}

def get_pair(user_id):
    cur.execute("SELECT pair_id, user1_id, user2_id FROM pairs WHERE user1_id=? OR user2_id=?", (user_id, user_id))
    row = cur.fetchone()
    if row:
        pair_id, u1, u2 = row
        other = u2 if u1 == user_id else u1
        return pair_id, other
    return None, None

def get_pet(pair_id):
    cur.execute("SELECT name, photo_id, hunger, happiness, cleanliness, level FROM pets WHERE pair_id=?", (pair_id,))
    row = cur.fetchone()
    return {'name': row[0], 'photo_id': row[1], 'hunger': row[2], 'happiness': row[3], 'cleanliness': row[4], 'level': row[5]} if row else None

def update_pet(pair_id, **kwargs):
    for field, value in kwargs.items():
        cur.execute(f"UPDATE pets SET {field}=?, last_update=CURRENT_TIMESTAMP WHERE pair_id=?", (value, pair_id))
    conn.commit()

def progress_bar(value):
    filled = int(value / 10)
    return "█" * filled + "░" * (10 - filled)

def get_zayka_mood(pet):
    avg = (pet['hunger'] + pet['happiness'] + pet['cleanliness']) // 3
    if avg < 40: return "🥺", "Зайка немного грустит..."
    if avg < 70: return "🐰", "Зайка спокойный и милый"
    if avg < 85: return "🥰", "Зайка очень счастлив!"
    return "✨", "Зайка сияет от любви к вам 💕"

def cute_reaction(action):
    reactions = {
        "feed": ["Ням-ням! 🥕", "Зайка обнимает за вкусняшку 💕"],
        "play": ["Зайка прыгает от радости! 🥰", "Так весело!"],
        "clean": ["Теперь Зайка пушистый и пахнет клубничкой ✨"],
        "pet": ["Муррр~ Зайка тает от ласки 🥹", "Зайка прижимается к тебе ушками 💖"]
    }
    return random.choice(reactions.get(action, ["Зайка очень рад!"]))

def main_menu(name="Зайка"):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🍎 Покормить", callback_data="feed"),
         InlineKeyboardButton(text="🎾 Поиграть", callback_data="play"),
         InlineKeyboardButton(text="🛁 Помыть", callback_data="clean")],
        [InlineKeyboardButton(text="🤗 Погладить", callback_data="pet"),
         InlineKeyboardButton(text="📸 Своё фото", callback_data="change_photo"),
         InlineKeyboardButton(text="👀 Посмотреть", callback_data="show")],
        [InlineKeyboardButton(text="📊 Статус пары", callback_data="info"),
         InlineKeyboardButton(text="✏️ Переименовать", callback_data="rename"),
         InlineKeyboardButton(text="🚪 Выйти", callback_data="leave")]
    ])
    return kb

@dp.message(CommandStart())
async def start(message: Message):
    user_id = message.from_user.id
    pair_id, other = get_pair(user_id)

    if pair_id:
        pet = get_pet(pair_id)
        await message.answer(f"🐰 С возвращением к {pet['name']}!", reply_markup=main_menu(pet['name']))
        return

    text = message.text or ""
    if 'ref_' in text:
        try:
            ref_id = int(text.split('ref_')[1])
            if ref_id == user_id:
                await message.answer("Это твоя ссылка 😉")
                return
            pair_id = f"{min(ref_id, user_id)}_{max(ref_id, user_id)}"
            cur.execute("INSERT INTO pairs (pair_id, user1_id, user2_id) VALUES (?, ?, ?)", (pair_id, ref_id, user_id))
            cur.execute("INSERT INTO pets (pair_id) VALUES (?)", (pair_id,))
            conn.commit()
            await message.answer("✅ Общий Зайка создан! 🐰")
            pet = get_pet(pair_id)
            await message.answer("Выбери действие:", reply_markup=main_menu(pet['name']))
        except:
            await message.answer("Неверная ссылка 😔")
    else:
        bot_info = await bot.get_me()
        ref_link = f"https://t.me/{bot_info.username}?start=ref_{user_id}"
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📋 Поделиться ссылкой", url=ref_link)]])
        await message.answer(f"Привет! Чтобы ухаживать за одним Зайкой вдвоём — поделись этой ссылкой:\n\n{ref_link}", reply_markup=kb)

@dp.callback_query(lambda c: c.data in ["feed", "play", "clean", "pet"])
async def do_action(callback: CallbackQuery):
    user_id = callback.from_user.id
    pair_id, other = get_pair(user_id)
    pet = get_pet(pair_id)
    if not pet: return

    if callback.data == "feed":
        update_pet(pair_id, hunger=min(100, pet['hunger'] + 22))
    elif callback.data == "play":
        update_pet(pair_id, happiness=min(100, pet['happiness'] + 18))
    elif callback.data == "clean":
        update_pet(pair_id, cleanliness=min(100, pet['cleanliness'] + 25))
    elif callback.data == "pet":
        update_pet(pair_id, happiness=min(100, pet['happiness'] + 25))

    pet = get_pet(pair_id)
    emoji, mood = get_zayka_mood(pet)
    reaction = cute_reaction(callback.data)

    text = f"{emoji} {reaction}\n\n" \
           f"{pet['name']}\n" \
           f"Голод: {pet['hunger']}% {progress_bar(pet['hunger'])}\n" \
           f"Счастье: {pet['happiness']}% {progress_bar(pet['happiness'])}\n" \
           f"Чистота: {pet['cleanliness']}% {progress_bar(pet['cleanliness'])}"

    await callback.message.edit_text(text, reply_markup=main_menu(pet['name']))

    try:
        await bot.send_message(other, f"❤️ Твой любимый человек {callback.data.replace('feed','покормил').replace('play','поиграл').replace('clean','помыл').replace('pet','погладил')} нашего {pet['name']}!\n{reaction}")
    except:
        pass

@dp.callback_query(lambda c: c.data == "change_photo")
async def change_photo(callback: CallbackQuery):
    waiting_for_photo[callback.from_user.id] = True
    await callback.message.edit_text("Отправь мне любое фото для нашего Зайки 🐰\nМожно своё селфи ❤️")

@dp.message(lambda m: m.photo)
async def handle_photo(message: Message):
    user_id = message.from_user.id
    if user_id not in waiting_for_photo: return
    del waiting_for_photo[user_id]

    pair_id, _ = get_pair(user_id)
    if not pair_id: return

    photo_id = message.photo[-1].file_id
    cur.execute("UPDATE pets SET photo_id = ? WHERE pair_id = ?", (photo_id, pair_id))
    conn.commit()

    await message.answer("💕 Фото сохранено! Теперь Зайка выглядит именно так 🥰")
    pet = get_pet(pair_id)
    await show_pet(message, pet)

async def show_pet(message, pet):
    emoji, mood = get_zayka_mood(pet)
    if pet.get('photo_id'):
        await message.answer_photo(photo=pet['photo_id'], caption=f"{emoji} {pet['name']}\n{mood}\n\nГолод: {pet['hunger']}% {progress_bar(pet['hunger'])}\nСчастье: {pet['happiness']}% {progress_bar(pet['happiness'])}\nЧистота: {pet['cleanliness']}% {progress_bar(pet['cleanliness'])}", reply_markup=main_menu(pet['name']))
    else:
        await message.answer(f"{emoji} {pet['name']}\n{mood}\n\nГолод: {pet['hunger']}% {progress_bar(pet['hunger'])}\nСчастье: {pet['happiness']}% {progress_bar(pet['happiness'])}\nЧистота: {pet['cleanliness']}% {progress_bar(pet['cleanliness'])}", reply_markup=main_menu(pet['name']))

@dp.callback_query(lambda c: c.data == "show")
async def show_pet_callback(callback: CallbackQuery):
    pair_id, _ = get_pair(callback.from_user.id)
    pet = get_pet(pair_id)
    await show_pet(callback.message, pet)

@dp.callback_query(lambda c: c.data == "info")
async def show_info(callback: CallbackQuery):
    user_id = callback.from_user.id
    pair_id, other = get_pair(user_id)
    if not pair_id: return
    pet = get_pet(pair_id)

    # Получаем @username партнёра
    try:
        other_chat = await bot.get_chat(other)
        partner = f"@{other_chat.username}" if other_chat.username else f"ID {other}"
    except:
        partner = f"ID {other}"

    days = (datetime.now() - datetime.fromisoformat(cur.execute("SELECT created_at FROM pairs WHERE pair_id=?", (pair_id,)).fetchone()[0])).days

    await callback.message.edit_text(
        f"🐰 {pet['name']}\n\n"
        f"Голод: {pet['hunger']}% {progress_bar(pet['hunger'])}\n"
        f"Счастье: {pet['happiness']}% {progress_bar(pet['happiness'])}\n"
        f"Чистота: {pet['cleanliness']}% {progress_bar(pet['cleanliness'])}\n\n"
        f"Ты в паре с {partner} 💕\n"
        f"Вместе уже {days} дней 🥰",
        reply_markup=main_menu(pet['name'])
    )

# rename, leave, confirm_leave, cancel_leave — остались как раньше (с подтверждением 🥺)

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
