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

# SQLite база
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
    last_update TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)''')
conn.commit()

def get_pair(user_id):
    cur.execute("SELECT pair_id, user1_id, user2_id FROM pairs WHERE user1_id = ? OR user2_id = ?", (user_id, user_id))
    row = cur.fetchone()
    if row:
        pair_id, u1, u2 = row
        other = u2 if u1 == user_id else u1
        return pair_id, other
    return None, None

def get_pet(pair_id):
    cur.execute("SELECT name, hunger, happiness, cleanliness FROM pets WHERE pair_id = ?", (pair_id,))
    row = cur.fetchone()
    if row:
        return {'name': row[0], 'hunger': row[1], 'happiness': row[2], 'cleanliness': row[3]}
    return None

def update_pet(pair_id, field, value):
    cur.execute(f"UPDATE pets SET {field} = ?, last_update = CURRENT_TIMESTAMP WHERE pair_id = ?", (value, pair_id))
    conn.commit()

def get_days_together(pair_id):
    cur.execute("SELECT created_at FROM pairs WHERE pair_id = ?", (pair_id,))
    created = cur.fetchone()[0]
    days = (datetime.now() - datetime.fromisoformat(created)).days
    return days

def main_menu():
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🐰 Действия с Зайкой", callback_data="actions")],
        [InlineKeyboardButton(text="📊 Статус пары", callback_data="info")],
        [InlineKeyboardButton(text="✏️ Переименовать Зайку", callback_data="rename")],
        [InlineKeyboardButton(text="🚪 Выйти из пары", callback_data="leave")]
    ])
    return kb

@dp.message(CommandStart())
async def start(message: Message):
    user_id = message.from_user.id
    pair_id, other = get_pair(user_id)

    if pair_id:
        await message.answer("Ты уже в паре с общим Зайкой 🐰\nВыбери действие ниже:", reply_markup=main_menu())
        return

    text = message.text or ""
    if 'ref_' in text:
        try:
            ref_id = int(text.split('ref_')[1])
            if ref_id == user_id:
                await message.answer("Это твоя ссылка 😉 Поделись ей с девушкой!")
                return
            pair_id = f"{min(ref_id, user_id)}_{max(ref_id, user_id)}"
            cur.execute("INSERT INTO pairs (pair_id, user1_id, user2_id) VALUES (?, ?, ?)", (pair_id, ref_id, user_id))
            cur.execute("INSERT INTO pets (pair_id) VALUES (?)", (pair_id,))
            conn.commit()
            await message.answer(f"✅ Общий Зайка создан! 🐰\nВ паре с: {ref_id}")
            try:
                await bot.send_message(ref_id, f"✅ К тебе присоединились! Теперь общий Зайка 🐰")
            except:
                pass
            await message.answer("Главное меню:", reply_markup=main_menu())
        except:
            await message.answer("Неверная ссылка 😔")
    else:
        bot_info = await bot.get_me()
        ref_link = f"https://t.me/{bot_info.username}?start=ref_{user_id}"
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📋 Поделиться ссылкой", url=ref_link)]])
        await message.answer(f"Привет! Чтобы ухаживать за одним Зайкой вдвоём — поделись ссылкой с девушкой:\n\n{ref_link}", reply_markup=kb)

@dp.callback_query(lambda c: c.data == "actions")
async def actions_menu(callback: CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🍎 Покормить Зайку", callback_data="feed")],
        [InlineKeyboardButton(text="🎾 Поиграть с Зайкой", callback_data="play")],
        [InlineKeyboardButton(text="🛁 Помыть Зайку", callback_data="clean")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="main")]
    ])
    await callback.message.edit_text("Что делаем с нашим Зайкой? 🐰", reply_markup=kb)

@dp.callback_query(lambda c: c.data in ["feed", "play", "clean"])
async def do_action(callback: CallbackQuery):
    user_id = callback.from_user.id
    pair_id, other = get_pair(user_id)
    if not pair_id:
        await callback.answer("Ты не в паре!")
        return

    pet = get_pet(pair_id)
    action_name = ""
    if callback.data == "feed":
        new_val = min(100, pet['hunger'] + 25)
        update_pet(pair_id, "hunger", new_val)
        action_name = "покормил Зайку 🍎"
    elif callback.data == "play":
        new_val = min(100, pet['happiness'] + 20)
        update_pet(pair_id, "happiness", new_val)
        action_name = "поиграл с Зайкой 🎾"
    elif callback.data == "clean":
        new_val = min(100, pet['cleanliness'] + 30)
        update_pet(pair_id, "cleanliness", new_val)
        action_name = "помыл Зайку 🛁"

    pet = get_pet(pair_id)
    await callback.message.edit_text(
        f"✅ Ты {action_name}!\n\n"
        f"🐰 **{pet['name']}**\n"
        f"Голод: {pet['hunger']}%\n"
        f"Счастье: {pet['happiness']}%\n"
        f"Чистота: {pet['cleanliness']}%",
        reply_markup=main_menu()
    )

    # Реал-тайм уведомление второму человеку
    try:
        await bot.send_message(other, f"❤️ Твой партнёр {action_name}!\n\n"
                                     f"🐰 **{pet['name']}**\n"
                                     f"Голод: {pet['hunger']}%\n"
                                     f"Счастье: {pet['happiness']}%\n"
                                     f"Чистота: {pet['cleanliness']}%")
    except:
        pass

@dp.callback_query(lambda c: c.data == "info")
async def show_info(callback: CallbackQuery):
    user_id = callback.from_user.id
    pair_id, other = get_pair(user_id)
    if not pair_id:
        await callback.answer("Ты не в паре!")
        return

    pet = get_pet(pair_id)
    days = get_days_together(pair_id)
    await callback.message.edit_text(
        f"🐰 **{pet['name']}**\n\n"
        f"Голод: {pet['hunger']}%\n"
        f"Счастье: {pet['happiness']}%\n"
        f"Чистота: {pet['cleanliness']}%\n\n"
        f"В паре с: {other}\n"
        f"Вместе растите Зайку уже {days} дней ❤️",
        reply_markup=main_menu()
    )

@dp.callback_query(lambda c: c.data == "rename")
async def start_rename(callback: CallbackQuery):
    await callback.message.edit_text("Напиши новое имя для Зайки (до 20 символов):")

@dp.message(lambda m: len(m.text) <= 20 and not m.text.startswith('/'))
async def set_new_name(message: Message):
    user_id = message.from_user.id
    pair_id, _ = get_pair(user_id)
    if pair_id:
        cur.execute("UPDATE pets SET name = ? WHERE pair_id = ?", (message.text.strip(), pair_id))
        conn.commit()
        await message.answer(f"✅ Зайка теперь зовётся **{message.text}**! 🐰", reply_markup=main_menu())

@dp.callback_query(lambda c: c.data == "leave")
async def leave_pair(callback: CallbackQuery):
    user_id = callback.from_user.id
    pair_id, other = get_pair(user_id)
    if not pair_id:
        await callback.answer("Ты не в паре!")
        return

    cur.execute("DELETE FROM pairs WHERE pair_id = ?", (pair_id,))
    cur.execute("DELETE FROM pets WHERE pair_id = ?", (pair_id,))
    conn.commit()
    await callback.message.edit_text("🚪 Ты вышел из пары. Общий Зайка удалён.")
    try:
        await bot.send_message(other, "😔 Твой партнёр вышел из пары. Общий Зайка больше не существует.")
    except:
        pass

@dp.callback_query(lambda c: c.data == "main")
async def back_main(callback: CallbackQuery):
    await callback.message.edit_text("Главное меню Зайки 🐰", reply_markup=main_menu())

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
