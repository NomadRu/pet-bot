import asyncio
import logging
import os
import sqlite3
from datetime import datetime
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

TOKEN = os.getenv("BOT_TOKEN")

logging.basicConfig(level=logging.INFO)

bot = Bot(token=TOKEN)
dp = Dispatcher()

# ====================== БАЗА ======================
conn = sqlite3.connect('pets.db', check_same_thread=False)
cur = conn.cursor()

cur.execute('''CREATE TABLE IF NOT EXISTS pairs (
    pair_id TEXT PRIMARY KEY,
    user1_id INTEGER,
    user2_id INTEGER,
    user1_username TEXT,
    user2_username TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)''')

cur.execute('''CREATE TABLE IF NOT EXISTS pets (
    pair_id TEXT PRIMARY KEY,
    name TEXT DEFAULT 'Зайка',
    hunger INTEGER DEFAULT 80,
    happiness INTEGER DEFAULT 50,
    cleanliness INTEGER DEFAULT 70,
    health INTEGER DEFAULT 100,
    level INTEGER DEFAULT 1,
    exp INTEGER DEFAULT 0,
    last_update TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)''')
conn.commit()

# ====================== ФОНОВЫЙ ТАЙМЕР ======================
async def decrease_stats_task():
    while True:
        await asyncio.sleep(180)  # каждые 3 минуты
        cur.execute("SELECT pair_id, hunger, happiness, cleanliness, health FROM pets")
        for row in cur.fetchall():
            pair_id = row[0]
            hunger = max(0, row[1] - 1)
            happiness = max(0, row[2] - 1)
            cleanliness = max(0, row[3] - 1)
            health = max(0, row[4] - 1 if hunger < 25 or happiness < 25 or cleanliness < 25 else row[4])

            cur.execute("""UPDATE pets SET hunger=?, happiness=?, cleanliness=?, health=?, last_update=CURRENT_TIMESTAMP 
                           WHERE pair_id=?""", (hunger, happiness, cleanliness, health, pair_id))
            conn.commit()

            if hunger < 30 or happiness < 30 or cleanliness < 30:
                try:
                    cur.execute("SELECT user1_id, user2_id FROM pairs WHERE pair_id = ?", (pair_id,))
                    u1, u2 = cur.fetchone()
                    msg = f"😢 **{get_pet(pair_id)['name']}** грустит! Параметры падают..."
                    await bot.send_message(u1, msg)
                    await bot.send_message(u2, msg)
                except:
                    pass

# ====================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ======================
def get_pair(user_id):
    cur.execute("SELECT * FROM pairs WHERE user1_id = ? OR user2_id = ?", (user_id, user_id))
    row = cur.fetchone()
    if row:
        return row[0], row[2] if row[1] == user_id else row[1], row[4] if row[1] == user_id else row[3]
    return None, None, None

def get_pet(pair_id):
    cur.execute("SELECT name, hunger, happiness, cleanliness, health, level, exp FROM pets WHERE pair_id = ?", (pair_id,))
    row = cur.fetchone()
    if row:
        return {'name': row[0], 'hunger': row[1], 'happiness': row[2], 'cleanliness': row[3],
                'health': row[4], 'level': row[5], 'exp': row[6]}
    return None

def update_pet(pair_id, field, value):
    cur.execute(f"UPDATE pets SET {field}=?, last_update=CURRENT_TIMESTAMP WHERE pair_id=?", (value, pair_id))
    conn.commit()

def add_exp(pair_id, amount):
    pet = get_pet(pair_id)
    new_exp = pet['exp'] + amount
    new_level = pet['level']
    if new_exp >= pet['level'] * 80:
        new_level += 1
        new_exp = 0
        update_pet(pair_id, "health", min(100, pet['health'] + 20))
        # Милое сообщение при левел-апе
        asyncio.create_task(send_level_up(pair_id, new_level))
    cur.execute("UPDATE pets SET exp=?, level=? WHERE pair_id=?", (new_exp, new_level, pair_id))
    conn.commit()

async def send_level_up(pair_id, new_level):
    pet = get_pet(pair_id)
    cur.execute("SELECT user1_id, user2_id FROM pairs WHERE pair_id=?", (pair_id,))
    u1, u2 = cur.fetchone()
    msg = f"🎉 **{pet['name']}** вырос до уровня {new_level}! ❤️"
    await bot.send_message(u1, msg)
    await bot.send_message(u2, msg)

def dynamic_menu(pet_name):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"🍎 Покормить {pet_name}", callback_data="feed")],
        [InlineKeyboardButton(text=f"🎾 Поиграть с {pet_name}", callback_data="play")],
        [InlineKeyboardButton(text=f"🛁 Помыть {pet_name}", callback_data="clean")],
        [InlineKeyboardButton(text="📊 Статус пары", callback_data="info")],
        [InlineKeyboardButton(text="✏️ Переименовать", callback_data="rename")],
        [InlineKeyboardButton(text="🚪 Выйти из пары", callback_data="leave")]
    ])

# ====================== ХЭНДЛЕРЫ ======================
@dp.message(CommandStart())
async def start(message: Message):
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name
    pair_id, other_id, other_username = get_pair(user_id)

    if pair_id:
        pet = get_pet(pair_id)
        await message.answer(f"🐰 С возвращением! Твой общий питомец — **{pet['name']}**", 
                           reply_markup=dynamic_menu(pet['name']))
        return

    text = message.text or ""
    if 'ref_' in text:
        try:
            ref_id = int(text.split('ref_')[1])
            if ref_id == user_id:
                await message.answer("Это твоя ссылка 😉")
                return
            pair_id = f"{min(ref_id, user_id)}_{max(ref_id, user_id)}"
            cur.execute("INSERT INTO pairs (pair_id, user1_id, user2_id, user1_username, user2_username) VALUES (?, ?, ?, ?, ?)",
                        (pair_id, ref_id, user_id, "User"+str(ref_id), username))
            cur.execute("INSERT INTO pets (pair_id) VALUES (?)", (pair_id,))
            conn.commit()

            await message.answer(f"❤️ Общий питомец создан!\nТеперь вы вместе ухаживаете за **Зайкой**")
            try: await bot.send_message(ref_id, f"❤️ @{username} присоединился! Теперь общий питомец!")
            except: pass

            pet = get_pet(pair_id)
            await message.answer("Главное меню:", reply_markup=dynamic_menu(pet['name']))
        except:
            await message.answer("Неверная ссылка 😔")
    else:
        bot_info = await bot.get_me()
        ref_link = f"https://t.me/{bot_info.username}?start=ref_{user_id}"
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📋 Поделиться ссылкой", url=ref_link)]])
        await message.answer(f"🐰 Привет! Создай пару с девушкой:\n\n{ref_link}", reply_markup=kb)

@dp.callback_query()
async def callback_handler(callback: CallbackQuery):
    data = callback.data
    user_id = callback.from_user.id
    pair_id, other_id, other_username = get_pair(user_id)
    if not pair_id:
        await callback.answer("Ты не в паре!")
        return

    pet = get_pet(pair_id)

    if data in ["feed", "play", "clean"]:
        if data == "feed":
            update_pet(pair_id, "hunger", min(100, pet['hunger'] + 28))
            action = f"покормил {pet['name']} 🍎"
            add_exp(pair_id, 12)
        elif data == "play":
            update_pet(pair_id, "happiness", min(100, pet['happiness'] + 22))
            action = f"поиграл с {pet['name']} 🎾"
            add_exp(pair_id, 15)
        else:
            update_pet(pair_id, "cleanliness", min(100, pet['cleanliness'] + 35))
            action = f"помыл {pet['name']} 🛁"
            add_exp(pair_id, 10)

        pet = get_pet(pair_id)
        await callback.message.edit_text(
            f"✅ Ты {action}!\n\n"
            f"🐰 **{pet['name']}** (Ур. {pet['level']})\n"
            f"Голод: {pet['hunger']}%\nСчастье: {pet['happiness']}%\nЧистота: {pet['cleanliness']}%\nЗдоровье: {pet['health']}%",
            reply_markup=dynamic_menu(pet['name'])
        )
        try:
            await bot.send_message(other_id, f"❤️ Партнёр {action}!\n\n"
                                            f"🐰 **{pet['name']}** (Ур. {pet['level']})\n"
                                            f"Голод: {pet['hunger']}%\nСчастье: {pet['happiness']}%\nЧистота: {pet['cleanliness']}%\nЗдоровье: {pet['health']}%")
        except:
            pass

    elif data == "info":
        days = (datetime.now() - datetime.fromisoformat(cur.execute("SELECT created_at FROM pairs WHERE pair_id = ?", (pair_id,)).fetchone()[0])).days
        await callback.message.edit_text(
            f"🐰 **{pet['name']}** (Уровень {pet['level']})\n\n"
            f"Голод: {pet['hunger']}%\nСчастье: {pet['happiness']}%\nЧистота: {pet['cleanliness']}%\nЗдоровье: {pet['health']}%\nОпыт: {pet['exp']}/{pet['level']*80}\n\n"
            f"В паре с: @{other_username or other_id}\nВместе уже {days} дней ❤️",
            reply_markup=dynamic_menu(pet['name'])
        )

    elif data == "rename":
        await callback.message.edit_text(f"Напиши новое имя для **{pet['name']}** (до 20 символов):")
    elif data == "leave":
        cur.execute("DELETE FROM pairs WHERE pair_id = ?", (pair_id,))
        cur.execute("DELETE FROM pets WHERE pair_id = ?", (pair_id,))
        conn.commit()
        await callback.message.edit_text("🚪 Ты вышел из пары. Общий питомец удалён.")
        try: await bot.send_message(other_id, "😔 Партнёр вышел из пары.")
        except: pass

@dp.message()
async def handle_rename(message: Message):
    user_id = message.from_user.id
    pair_id, _, _ = get_pair(user_id)
    if pair_id and 1 < len(message.text.strip()) <= 20:
        new_name = message.text.strip()
        cur.execute("UPDATE pets SET name = ? WHERE pair_id = ?", (new_name, pair_id))
        conn.commit()
        pet = get_pet(pair_id)
        await message.answer(f"✅ Теперь питомца зовут **{new_name}**! 🐰", reply_markup=dynamic_menu(new_name))

async def main():
    asyncio.create_task(decrease_stats_task())   # Запуск таймера
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
