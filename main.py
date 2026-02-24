import asyncio
import logging
import os
import sqlite3
import random
from datetime import datetime, date
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
    pair_id TEXT PRIMARY KEY, 
    name TEXT DEFAULT 'Зайка', 
    hunger INTEGER DEFAULT 80,
    happiness INTEGER DEFAULT 50, 
    cleanliness INTEGER DEFAULT 70, 
    level INTEGER DEFAULT 1,
    daily_score INTEGER DEFAULT 0,
    last_reset DATE DEFAULT CURRENT_DATE,
    last_sad_message TIMESTAMP
)''')
conn.commit()

waiting_for_photo = {}  # если вдруг вернёшь фото позже

def get_pair(user_id):
    cur.execute("SELECT pair_id, user1_id, user2_id FROM pairs WHERE user1_id=? OR user2_id=?", (user_id, user_id))
    row = cur.fetchone()
    if row:
        pair_id, u1, u2 = row
        other = u2 if u1 == user_id else u1
        return pair_id, other
    return None, None

def get_pet(pair_id):
    cur.execute("SELECT name, hunger, happiness, cleanliness, level, daily_score FROM pets WHERE pair_id=?", (pair_id,))
    row = cur.fetchone()
    return {'name': row[0], 'hunger': row[1], 'happiness': row[2], 'cleanliness': row[3], 'level': row[4], 'daily_score': row[5]} if row else None

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

def get_zayka_face_and_mood(pet):
    avg = (pet['hunger'] + pet['happiness'] + pet['cleanliness']) // 3
    if avg < 30: return "🥺", "Зайка очень грустит и прячет ушки..."
    if avg < 40: return "😔", "Зайка грустит и скучает по вам..."
    if avg < 60: return "🐰", "Зайка спокойный"
    if avg < 80: return "🥰", "Зайка счастлив!"
    return "✨", "Зайка сияет от счастья и любви к вам 💕"

def cute_reaction(action):
    reactions = {
        "feed": ["Ням-ням! 🥕", "Зайка обнимает за вкусняшку 💕"],
        "play": ["Зайка прыгает от радости! 🥰", "Так весело!"],
        "clean": ["Теперь Зайка пушистый и пахнет клубничкой ✨"],
        "pet": ["Муррр~ Зайка тает от ласки 🥹"],
        "miss": ["Зайка тоже скучает по вам обоим 🥺💕"]
    }
    return random.choice(reactions.get(action, ["Зайка очень рад!"]))

def main_menu(name="Зайка"):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🍎 Покормить", callback_data="feed"),
         InlineKeyboardButton(text="🎾 Поиграть", callback_data="play"),
         InlineKeyboardButton(text="🛁 Помыть", callback_data="clean")],
        [InlineKeyboardButton(text="🤗 Погладить", callback_data="pet"),
         InlineKeyboardButton(text="💌 Я скучаю по тебе", callback_data="miss"),
         InlineKeyboardButton(text="📊 Статус", callback_data="info")],
        [InlineKeyboardButton(text="✏️ Переименовать", callback_data="rename"),
         InlineKeyboardButton(text="🚪 Выйти", callback_data="leave")]
    ])
    return kb

# Фоновая задача — грустные сообщения Зайки
async def sad_zayka_task():
    while True:
        await asyncio.sleep(3600)  # каждые 60 минут
        cur.execute("SELECT pair_id FROM pets")
        for (pair_id,) in cur.fetchall():
            pet = get_pet(pair_id)
            if not pet: continue
            avg = (pet['hunger'] + pet['happiness'] + pet['cleanliness']) // 3
            if avg >= 40: continue

            # проверяем, что не писали в последний час
            cur.execute("SELECT last_sad_message FROM pets WHERE pair_id=?", (pair_id,))
            last = cur.fetchone()[0]
            if last and (datetime.now() - datetime.fromisoformat(last)).total_seconds() < 3600:
                continue

            emoji, mood = get_zayka_face_and_mood(pet)
            sad_text = random.choice([
                f"{emoji} Зайка грустит... Приходите скорее, мне одиноко 🥺",
                f"{emoji} Зайка ждёт вас... Скучаю по вашим ручкам 💕",
                f"{emoji} Зайка совсем грустный сегодня... Пожалуйста, поиграйте со мной 🥹"
            ])

            pair_id, other = get_pair(0)  # костыль, чтобы получить обоих
            # лучше получить user1 и user2
            cur.execute("SELECT user1_id, user2_id FROM pairs WHERE pair_id=?", (pair_id,))
            u1, u2 = cur.fetchone()
            for uid in (u1, u2):
                try:
                    await bot.send_message(uid, sad_text)
                except:
                    pass

            # обновляем время последнего грустного сообщения
            cur.execute("UPDATE pets SET last_sad_message=CURRENT_TIMESTAMP WHERE pair_id=?", (pair_id,))
            conn.commit()

# ... (остальной код start, do_action, info, rename, leave — тот же, что в прошлом сообщении, но с новым get_zayka_face_and_mood)

async def main():
    asyncio.create_task(sad_zayka_task())  # запускаем грустного Зайку
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
