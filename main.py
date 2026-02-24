import asyncio
import logging
import os
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton

TOKEN = os.getenv("BOT_TOKEN")  # ← будет брать из настроек Railway

logging.basicConfig(level=logging.INFO)

bot = Bot(token=TOKEN)
dp = Dispatcher()

# Хранилище в памяти (для теста)
pairs = {}
pets = {}

@dp.message(CommandStart(deep_link=True))
async def start_with_ref(message: Message, command: types.CommandObject):
    user_id = message.from_user.id
    payload = command.args or ""
    
    if payload.startswith("ref_"):
        try:
            ref_id = int(payload[4:])
        except:
            await message.answer("Неверная ссылка 😔")
            return

        if ref_id == user_id:
            await message.answer("Это твоя ссылка! Поделись с девушкой 😉")
            return

        pair_key = f"{min(ref_id, user_id)}_{max(ref_id, user_id)}"
        if pair_key not in pets:
            pairs[ref_id] = user_id
            pets[pair_key] = {'hunger': 80, 'happiness': 50, 'clean': 70}
            await message.answer(f"✅ Пара создана! Общий питомец 🦊\nГолод: 80%\nСчастье: 50%\nЧистота: 70%")
            try: await bot.send_message(ref_id, "К тебе присоединились! Теперь общий питомец 🐾")
            except: pass
        else:
            await message.answer("Пара уже есть!")
    else:
        await message.answer("Привет! Поделись ссылкой с девушкой ❤️")

@dp.message(CommandStart())
async def start_no_ref(message: Message):
    user_id = message.from_user.id
    bot_info = await bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start=ref_{user_id}"

    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📋 Скопировать ссылку", url=ref_link)]])
    
    await message.answer(f"🐶 Чтобы создать общего питомца:\n\nПоделись этой ссылкой с девушкой:\n{ref_link}", reply_markup=kb)

@dp.message(lambda m: m.text in ["Покормить", "Поиграть", "Помыть"])
async def action(message: Message):
    user_id = message.from_user.id
    pair_key = None
    for k, v in pairs.items():
        if user_id in (k, v):
            pair_key = f"{min(k,v)}_{max(k,v)}"
            break

    if not pair_key or pair_key not in pets:
        await message.answer("Сначала создай пару через реф-ссылку!")
        return

    pet = pets[pair_key]
    if message.text == "Покормить": pet['hunger'] = min(100, pet['hunger'] + 30)
    elif message.text == "Поиграть": pet['happiness'] = min(100, pet['happiness'] + 25)
    elif message.text == "Помыть": pet['clean'] = min(100, pet['clean'] + 40)

    await message.answer(f"✅ Готово!\nГолод: {pet['hunger']}%\nСчастье: {pet['happiness']}%\nЧистота: {pet['clean']}%")

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
