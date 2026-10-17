import os
import asyncio
import logging
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    Message, CallbackQuery, ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardRemove
)

# Load environment variables from .env file
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
BARBER_CHAT_ID = int(os.getenv("BARBER_CHAT_ID", "0"))
TELEBIRR_INFO = os.getenv("TELEBIRR_INFO", "0911XXXXXX")
CBE_INFO = os.getenv("CBE_INFO", "1000XXXXXXXXX")
DEPOSIT_AMOUNT = os.getenv("DEPOSIT_AMOUNT", "200 ETB")

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

class OrderState(StatesGroup):
    waiting_for_time = State()
    waiting_for_phone = State()
    waiting_for_address = State()
    waiting_for_payment = State()
    waiting_for_note = State()

# Step 1: /start -> Select Appointment Time
@dp.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🌅 Morning (9:00 AM - 12:00 PM)", callback_data="time_Morning (9-12)")],
        [InlineKeyboardButton(text="☀️ Afternoon (1:00 PM - 5:00 PM)", callback_data="time_Afternoon (1-5)")],
        [InlineKeyboardButton(text="🌙 Evening (5:00 PM - 8:00 PM)", callback_data="time_Evening (5-8)")]
    ])
    await message.answer(
        "💈 **Welcome to Barber Booking!**\n\nPlease select your preferred appointment time:",
        reply_markup=kb, parse_mode="Markdown"
    )
    await state.set_state(OrderState.waiting_for_time)

# Step 2: Receive Time -> Ask for Phone Number
@dp.callback_query(OrderState.waiting_for_time, F.data.startswith("time_"))
async def process_time(callback: CallbackQuery, state: FSMContext):
    selected_time = callback.data.split("_", 1)[1]
    await state.update_data(time=selected_time)

    phone_kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📱 Share My Phone Number", request_contact=True)]],
        resize_keyboard=True, one_time_keyboard=True
    )
    await callback.message.answer(
        f"🕒 Time selected: **{selected_time}**\n\n"
        "Tap the button below to share your phone number, or type your phone number (e.g., `0911...`):",
        reply_markup=phone_kb, parse_mode="Markdown"
    )
    await state.set_state(OrderState.waiting_for_phone)
    await callback.answer()

# Step 3: Receive Phone -> Ask for GPS or Text Address
@dp.message(OrderState.waiting_for_phone, F.contact | F.text)
async def process_phone(message: Message, state: FSMContext):
    phone = message.contact.phone_number if message.contact else message.text
    await state.update_data(phone=phone)

    loc_kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📍 Send Current GPS Location", request_location=True)]],
        resize_keyboard=True, one_time_keyboard=True
    )
    await message.answer(
        "📍 **Where is the service address?**\n\n"
        "Tap the button below to share your GPS pin, or type your neighborhood/landmark:",
        reply_markup=loc_kb, parse_mode="Markdown"
    )
    await state.set_state(OrderState.waiting_for_address)

# Step 4: Receive Address -> Ask for Payment Screenshot
@dp.message(OrderState.waiting_for_address, F.location | F.text)
async def process_address(message: Message, state: FSMContext):
    if message.location:
        lat, lon = message.location.latitude, message.location.longitude
        address_info = f"https://maps.google.com/?q={lat},{lon}"
    else:
        address_info = message.text

    await state.update_data(address=address_info)
    await message.answer(
        f"💳 **Payment Deposit ({DEPOSIT_AMOUNT})**\n\n"
        f"• **Telebirr:** `{TELEBIRR_INFO}`\n"
        f"• **CBE:** `{CBE_INFO}`\n\n"
        "📸 **Please upload the payment screenshot image here:**",
        reply_markup=ReplyKeyboardRemove(), parse_mode="Markdown"
    )
    await state.set_state(OrderState.waiting_for_payment)

# Step 5: Receive Payment Screenshot -> Ask for Optional Text
@dp.message(OrderState.waiting_for_payment, F.photo)
async def process_payment_photo(message: Message, state: FSMContext):
    photo_file_id = message.photo[-1].file_id
    await state.update_data(payment_photo=photo_file_id)

    skip_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⏭️ Skip Optional Note", callback_data="skip_note")]
    ])
    await message.answer(
        "✍️ **Screenshot received!**\n\nWrite any optional note (haircut style, house number, instructions) or tap **Skip**:",
        reply_markup=skip_kb, parse_mode="Markdown"
    )
    await state.set_state(OrderState.waiting_for_note)

@dp.message(OrderState.waiting_for_payment)
async def reject_non_photo(message: Message):
    await message.answer("⚠️ Please send an **image/photo screenshot** of your payment receipt.", parse_mode="Markdown")

# Step 6: Finalize & Send Order to Barber
async def finalize_order(user_msg: Message, state: FSMContext, note: str, customer_user):
    data = await state.get_data()
    await state.clear()

    username = f"@{customer_user.username}" if customer_user.username else customer_user.full_name
    summary = (
        f"🔔 **NEW BARBER ORDER**\n\n"
        f"👤 **Customer:** {username}\n"
        f"📞 **Phone:** `{data['phone']}`\n"
        f"🕒 **Time:** {data['time']}\n"
        f"📍 **Address:** {data['address']}\n"
        f"📝 **Note:** {note}"
    )

    barber_kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Approve", callback_data=f"approve_{customer_user.id}"),
        InlineKeyboardButton(text="❌ Reject", callback_data=f"reject_{customer_user.id}")
    ]])

    await bot.send_photo(
        chat_id=BARBER_CHAT_ID,
        photo=data['payment_photo'],
        caption=summary,
        reply_markup=barber_kb,
        parse_mode="Markdown"
    )
    await user_msg.answer(
        "✅ **Order submitted!**\nThe barber is reviewing your payment screenshot and will confirm shortly.",
        parse_mode="Markdown"
    )

@dp.callback_query(OrderState.waiting_for_note, F.data == "skip_note")
async def skip_note_handler(callback: CallbackQuery, state: FSMContext):
    await finalize_order(callback.message, state, "None", callback.from_user)
    await callback.answer()

@dp.message(OrderState.waiting_for_note, F.text)
async def text_note_handler(message: Message, state: FSMContext):
    await finalize_order(message, state, message.text, message.from_user)

# Step 7: Barber 1-Tap Approve / Reject
@dp.callback_query(F.data.startswith(("approve_", "reject_")))
async def barber_decision(callback: CallbackQuery):
    action, customer_id = callback.data.split("_")
    if action == "approve":
        await bot.send_message(customer_id, "🎉 **Your barber booking is APPROVED!** See you at your scheduled time.", parse_mode="Markdown")
        await callback.message.edit_caption(caption=callback.message.caption + "\n\n✅ **STATUS: APPROVED**")
    else:
        await bot.send_message(customer_id, "❌ **Booking Rejected:** Your payment screenshot could not be verified.", parse_mode="Markdown")
        await callback.message.edit_caption(caption=callback.message.caption + "\n\n❌ **STATUS: REJECTED**")
    await callback.answer("Customer notified!")

async def main():
    logging.info("Starting Barber Bot...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())