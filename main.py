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
    pair_id TEXT PRIMARY KEY, name TEXT DEFAULT 'Зайка', hunger INTEGER DEFAULT 80,
    happiness INTEGER DEFAULT 50, cleanliness INTEGER DEFAULT 70, level INTEGER DEFAULT 1,
    last_update TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)''')
conn.commit()

def get_pair(user_id):
    cur.execute("SELECT pair_id, user1_id, user2_id FROM pairs WHERE user1_id=? OR user2_id=?", (user_id, user_id))
    row = cur.fetchone()
    if row:
        pair_id, u1, u2 = row
        other = u2 if u1 == user_id else u1
        return pair_id, other
    return None, None

def get_pet(pair_id):
    cur.execute("SELECT name, hunger, happiness, cleanliness, level FROM pets WHERE pair_id=?", (pair_id,))
    row = cur.fetchone()
    return {'name': row[0], 'hunger': row[1], 'happiness': row[2], 'cleanliness': row[3], 'level': row[4]} if row else None

def update_pet(pair_id, **kwargs):
    for field, value in kwargs.items():
        cur.execute(f"UPDATE pets SET {field}=?, last_update=CURRENT_TIMESTAMP WHERE pair_id=?", (value, pair_id))
    conn.commit()

def progress_bar(value):
    filled = int(value / 10)
    return "█" * filled + "░" * (10 - filled)

def get_zayka_mood(pet):
    avg = (pet['hunger'] + pet['happiness'] + pet['cleanliness']) // 3
    if avg < 30: return "🥺", "Зайка грустит и прячет ушки..."
    if avg < 50: return "😔", "Зайка немного скучает..."
    if avg < 70: return "🐰", "Зайка спокойный и милый"
    if avg < 85: return "🥰", "Зайка счастлив и мурлычет!"
    return "✨", "Зайка сияет от счастья! 💕"

def cute_reaction(action):
    reactions = {
        "feed": ["Ням-ням! Зайка радостно кушает морковку 🥕", "Зайка обнимает тебя лапками за вкусняшку 💕"],
        "play": ["Зайка прыгает и виляет хвостиком! 🥰", "Так весело! Зайка смеётся ушками!"],
        "clean": ["Теперь Зайка пушистый и пахнет клубничкой ✨", "Зайка доволен и чистенький!"]
    }
    return random.choice(reactions.get(action, ["Зайка очень рад! 💖"]))

def main_menu(name="Зайка"):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"🍎 Покормить {name}", callback_data="feed")],
        [InlineKeyboardButton(text=f"🎾 Поиграть с {name}", callback_data="play")],
        [InlineKeyboardButton(text=f"🛁 Помыть {name}", callback_data="clean")],
        [InlineKeyboardButton(text="📊 Статус пары", callback_data="info")],
        [InlineKeyboardButton(text="✏️ Переименовать", callback_data="rename")],
        [InlineKeyboardButton(text="🚪 Выйти из пары", callback_data="leave")]
    ])
    return kb

@dp.message(CommandStart())
async def start(message: Message):
    user_id = message.from_user.id
    pair_id, other = get_pair(user_id)

    if pair_id:
        pet = get_pet(pair_id)
        await message.answer(f"🐰 Добро пожаловать обратно к {pet['name']}!", reply_markup=main_menu(pet['name']))
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
            await message.answer(f"✅ Общий Зайка создан! 🐰\nВ паре с: {ref_id}")
            try: await bot.send_message(ref_id, f"✅ К тебе присоединились! Теперь общий Зайка 🐰")
            except: pass
            pet = get_pet(pair_id)
            await message.answer("Главное меню:", reply_markup=main_menu(pet['name']))
        except:
            await message.answer("Неверная ссылка 😔")
    else:
        bot_info = await bot.get_me()
        ref_link = f"https://t.me/{bot_info.username}?start=ref_{user_id}"
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📋 Поделиться ссылкой", url=ref_link)]])
        await message.answer(f"Привет! Чтобы ухаживать за одним Зайкой вдвоём — поделись ссылкой с девушкой:\n\n{ref_link}", reply_markup=kb)

@dp.callback_query(lambda c: c.data in ["feed", "play", "clean"])
async def do_action(callback: CallbackQuery):
    user_id = callback.from_user.id
    pair_id, other = get_pair(user_id)
    pet = get_pet(pair_id)
    if not pet: return

    if callback.data == "feed":
        update_pet(pair_id, hunger=min(100, pet['hunger'] + 22))
    elif callback.data == "play":
        update_pet(pair_id, happiness=min(100, pet['happiness'] + 18))
    else:
        update_pet(pair_id, cleanliness=min(100, pet['cleanliness'] + 25))

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
        await bot.send_message(other, f"❤️ Твой любимый человек {callback.data.replace('feed','покормил').replace('play','поиграл').replace('clean','помыл')} нашего {pet['name']}!\n\n{reaction}")
    except:
        pass

@dp.callback_query(lambda c: c.data == "info")
async def show_info(callback: CallbackQuery):
    user_id = callback.from_user.id
    pair_id, other = get_pair(user_id)
    if not pair_id: return
    pet = get_pet(pair_id)
    days = (datetime.now() - datetime.fromisoformat(cur.execute("SELECT created_at FROM pairs WHERE pair_id=?", (pair_id,)).fetchone()[0])).days
    await callback.message.edit_text(
        f"🐰 {pet['name']}\n\n"
        f"Голод: {pet['hunger']}% {progress_bar(pet['hunger'])}\n"
        f"Счастье: {pet['happiness']}% {progress_bar(pet['happiness'])}\n"
        f"Чистота: {pet['cleanliness']}% {progress_bar(pet['cleanliness'])}\n\n"
        f"В паре с: {other}\n"
        f"Вместе уже {days} дней 💕",
        reply_markup=main_menu(pet['name'])
    )

@dp.callback_query(lambda c: c.data == "rename")
async def start_rename(callback: CallbackQuery):
    await callback.message.edit_text("Напиши новое имя для Зайки (до 20 символов):")

@dp.message(lambda m: len(m.text) <= 20 and not m.text.startswith('/'))
async def set_new_name(message: Message):
    user_id = message.from_user.id
    pair_id, _ = get_pair(user_id)
    if pair_id:
        new_name = message.text.strip()
        update_pet(pair_id, name=new_name)
        await message.answer(f"✅ Теперь нашего зайку зовут **{new_name}**! 🐰", reply_markup=main_menu(new_name))

@dp.callback_query(lambda c: c.data == "leave")
async def ask_leave(callback: CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Да, выйти 🥺", callback_data="confirm_leave")],
        [InlineKeyboardButton(text="Нет, я остаюсь 💕", callback_data="cancel")]
    ])
    await callback.message.edit_text("Ты точно хочешь выйти из пары с Зайкой? 🥺\nЭто удалит общий питомец навсегда...", reply_markup=kb)

@dp.callback_query(lambda c: c.data == "confirm_leave")
async def confirm_leave(callback: CallbackQuery):
    user_id = callback.from_user.id
    pair_id, other = get_pair(user_id)
    if pair_id:
        cur.execute("DELETE FROM pairs WHERE pair_id=?", (pair_id,))
        cur.execute("DELETE FROM pets WHERE pair_id=?", (pair_id,))
        conn.commit()
        await callback.message.edit_text("🚪 Ты вышел из пары. Общий Зайка теперь один...")
        try:
            await bot.send_message(other, "😔 Твой партнёр вышел из пары. Общий Зайка больше не существует 🥺")
        except:
            pass

@dp.callback_query(lambda c: c.data == "cancel")
async def cancel_leave(callback: CallbackQuery):
    user_id = callback.from_user.id
    pair_id, _ = get_pair(user_id)
    pet = get_pet(pair_id)
    await callback.message.edit_text(f"Ура! Остаёмся вместе с {pet['name']} 💕", reply_markup=main_menu(pet['name']))

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
