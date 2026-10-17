import os
import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    Message, CallbackQuery, ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardRemove,
    BotCommand, BotCommandScopeDefault
)

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
BARBER_CHAT_ID = int(os.getenv("BARBER_CHAT_ID", "0"))
TELEBIRR_INFO = os.getenv("TELEBIRR_INFO", "0911XXXXXX (Name: Abebe)")
CBE_INFO = os.getenv("CBE_INFO", "1000XXXXXXXXX (Name: Abebe)")
DATA_FILE = Path(__file__).with_name("barber_data.json")

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Clean Service Catalog (Easy to customize prices & names)
SERVICES = {
    "svc_regular": {"name": "✂️ Regular Haircut", "price": "300 ETB", "deposit": "150 ETB"},
    "svc_combo":   {"name": "🧔 Haircut + Beard Styling", "price": "450 ETB", "deposit": "200 ETB"},
    "svc_vip":     {"name": "👑 Full VIP Package (Cut + Facial + Wash)", "price": "700 ETB", "deposit": "300 ETB"},
    "svc_home":    {"name": "🏠 Home-to-Home VIP Service", "price": "1,200 ETB", "deposit": "500 ETB"},
}

ORDER_STATUSES = {
    "booked": "📅 Booked",
    "checked": "🔎 Checked",
    "complete": "✅ Complete",
    "cancel": "🚫 Cancelled",
    "reject": "❌ Rejected",
}

def load_data():
    if not DATA_FILE.exists():
        return {}, SERVICES.copy()
    try:
        saved = json.loads(DATA_FILE.read_text(encoding="utf-8"))
        return saved.get("orders", {}), saved.get("services", SERVICES.copy())
    except (OSError, json.JSONDecodeError) as exc:
        logging.warning("Could not load saved barber data: %s", exc)
        return {}, SERVICES.copy()


ORDERS_DB, SERVICES = load_data()


def save_data():
    try:
        DATA_FILE.write_text(
            json.dumps({"orders": ORDERS_DB, "services": SERVICES}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError as exc:
        logging.error("Could not save barber data: %s", exc)


def is_admin(user_id: int) -> bool:
    return user_id == BARBER_CHAT_ID


def status_label(status: str) -> str:
    return ORDER_STATUSES.get(status, status)

class OrderFlow(StatesGroup):
    choosing_service = State()
    choosing_shift = State()
    sending_phone = State()
    sending_address = State()
    sending_screenshot = State()
    sending_special_note = State()


class AdminFlow(StatesGroup):
    adding_service = State()
    editing_service = State()

# Automatically create the persistent blue "Menu" button in Telegram
async def setup_bot_menu(bot: Bot):
    commands = [
        BotCommand(command="start", description="💈 View Services & Book Appointment"),
        BotCommand(command="myorders", description="📋 Check My Booking Status"),
        BotCommand(command="allorders", description="🔐 Barber Admin: View Today's Bookings"),
        BotCommand(command="services", description="🔐 Barber Admin: Manage Services"),
        BotCommand(command="adminhelp", description="🔐 Barber Admin: Show Management Help"),
    ]
    await bot.set_my_commands(commands, scope=BotCommandScopeDefault())

# 1. Main Screen: Read Services & Tap to Order
@dp.message(CommandStart())
async def show_services_menu(message: Message, state: FSMContext):
    await state.clear()
    service_lines = []
    service_buttons = []
    for number, (service_id, service) in enumerate(SERVICES.items(), start=1):
        service_lines.append(
            f"{number}. **{service['name']}** — `{service['price']}`\n"
            f"   • Deposit: `{service['deposit']}`"
        )
        service_buttons.append([
            InlineKeyboardButton(
                text=f"{service['name']} ({service['price']})",
                callback_data=service_id,
            )
        ])

    menu_text = (
        "💈 **WELCOME TO VIP BARBER BOOKING** 💈\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "📋 **OUR SERVICES & PRICES:**\n\n"
        + "\n\n".join(service_lines)
        + "\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "👇 **Tap a service button below to start your order:**"
    )
    service_buttons.append([
        InlineKeyboardButton(text="📋 Check My Booking Status", callback_data="check_my_order")
    ])

    await message.answer(
        menu_text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=service_buttons),
        parse_mode="Markdown",
    )
    await state.set_state(OrderFlow.choosing_service)

# 2. Choose Time Shift (Updates same message card for high speed)
@dp.callback_query(F.data.in_(SERVICES.keys()))
async def select_shift(callback: CallbackQuery, state: FSMContext):
    svc = SERVICES.get(callback.data)
    if not svc:
        await callback.answer("That service is no longer available.", show_alert=True)
        return
    await state.update_data(
        service_id=callback.data,
        service_name=svc["name"],
        price=svc["price"],
        deposit=svc["deposit"],
    )

    shift_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🌅 Morning Shift (9:00 AM - 12:00 PM)", callback_data="shift_Morning (9:00 AM - 12:00 PM)")],
        [InlineKeyboardButton(text="☀️ Afternoon Shift (12:00 PM - 4:00 PM)", callback_data="shift_Afternoon (12:00 PM - 4:00 PM)")],
        [InlineKeyboardButton(text="🌆 Evening Shift (4:00 PM - 8:30 PM)", callback_data="shift_Evening (4:00 PM - 8:30 PM)")],
        [InlineKeyboardButton(text="⬅️ Back to Services", callback_data="back_to_services")]
    ])

    await callback.message.edit_text(
        f"✅ **Selected:** {svc['name']} (`{svc['price']}`)\n\n"
        "🕒 **Step 1 of 4: Choose your preferred Time Shift:**",
        reply_markup=shift_kb, parse_mode="Markdown"
    )
    await state.set_state(OrderFlow.choosing_shift)
    await callback.answer()

@dp.callback_query(F.data == "back_to_services")
async def back_to_services_handler(callback: CallbackQuery, state: FSMContext):
    await callback.message.delete()
    await show_services_menu(callback.message, state)
    await callback.answer()

# 3. Choose Shift -> Ask for Phone Number
@dp.callback_query(OrderFlow.choosing_shift, F.data.startswith("shift_"))
async def ask_phone(callback: CallbackQuery, state: FSMContext):
    shift = callback.data.split("_", 1)[1]
    await state.update_data(shift=shift)

    phone_kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📱 Tap to Share My Phone Number", request_contact=True)]],
        resize_keyboard=True, one_time_keyboard=True
    )

    await callback.message.edit_text(
        f"🕒 **Shift:** {shift}\n\n"
        "📞 **Step 2 of 4:** Tap the bottom button to share your phone number, or type it below (e.g., `0911...`):",
        parse_mode="Markdown"
    )
    await callback.message.answer("👇 Use the button below or type your number:", reply_markup=phone_kb)
    await state.set_state(OrderFlow.sending_phone)
    await callback.answer()

# 4. Receive Phone -> Ask for GPS or Text Address
@dp.message(OrderFlow.sending_phone, F.contact | F.text)
async def ask_address(message: Message, state: FSMContext):
    phone = message.contact.phone_number if message.contact else message.text
    await state.update_data(phone=phone)

    loc_kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📍 Send Current GPS Location", request_location=True)]],
        resize_keyboard=True, one_time_keyboard=True
    )
    await message.answer(
        "📍 **Step 3 of 4: Send Location / Address**\n\n"
        "Tap **Send Current GPS Location** below, or type your neighborhood/landmark (or type `At Barber Shop` if coming in person):",
        reply_markup=loc_kb, parse_mode="Markdown"
    )
    await state.set_state(OrderFlow.sending_address)

# 5. Receive Address -> Ask for Payment Screenshot
@dp.message(OrderFlow.sending_address, F.location | F.text)
async def ask_payment_screenshot(message: Message, state: FSMContext):
    if message.location:
        lat, lon = message.location.latitude, message.location.longitude
        address = f"https://maps.google.com/?q={lat},{lon}"
    else:
        address = message.text

    await state.update_data(address=address)
    data = await state.get_data()

    await message.answer(
        f"💳 **Step 4 of 4: Booking Deposit ({data['deposit']})**\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"• **Service:** {data['service_name']} ({data['price']})\n"
        f"• **Required Deposit:** `{data['deposit']}`\n\n"
        f"🏦 **Telebirr:** `{TELEBIRR_INFO}`\n"
        f"🏦 **CBE Account:** `{CBE_INFO}`\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "📸 **Upload the payment screenshot image here to continue:**",
        reply_markup=ReplyKeyboardRemove(), parse_mode="Markdown"
    )
    await state.set_state(OrderFlow.sending_screenshot)

# 6. Receive Screenshot -> Ask for Optional Special Need Text
@dp.message(OrderFlow.sending_screenshot, F.photo)
async def ask_special_note(message: Message, state: FSMContext):
    photo_id = message.photo[-1].file_id
    await state.update_data(payment_photo=photo_id)

    skip_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⏭️ No Special Need — Submit Order Now", callback_data="skip_special_note")]
    ])
    await message.answer(
        "✍️ **Optional: Any Special Needs or Instructions?**\n\n"
        "Type your message now (e.g., *sensitive skin, kid's haircut, specific fade style, exact arrival time*) OR tap the button below to skip:",
        reply_markup=skip_kb, parse_mode="Markdown"
    )
    await state.set_state(OrderFlow.sending_special_note)

@dp.message(OrderFlow.sending_screenshot)
async def invalid_screenshot(message: Message):
    await message.answer("⚠️ Please upload a **Photo / Screenshot image** of your payment receipt.", parse_mode="Markdown")

# 7. Finalize Order -> Save & Notify Barber with 1-Tap Buttons
async def submit_booking(msg_obj: Message, state: FSMContext, special_note: str, user):
    data = await state.get_data()
    await state.clear()

    order_id = f"ORD-{uuid4().hex[:8].upper()}"
    customer_tag = f"@{user.username}" if user.username else user.full_name

    order = {
        "user_id": user.id,
        "order_id": order_id,
        "customer": customer_tag,
        "username": user.username or "",
        "service": data["service_name"],
        "service_id": data.get("service_id", ""),
        "price": data["price"],
        "shift": data["shift"],
        "phone": data["phone"],
        "address": data["address"],
        "note": special_note,
        "payment_photo": data["payment_photo"],
        "status": "booked",
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    ORDERS_DB[order_id] = order
    save_data()

    barber_caption = (
        f"🔔 **NEW BOOKING ({order_id})**\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 **Customer:** {customer_tag}\n"
        f"📞 **Phone:** `{data['phone']}`\n"
        f"✂️ **Service:** {data['service_name']} ({data['price']})\n"
        f"🕒 **Shift:** {data['shift']}\n"
        f"📍 **Address:** {data['address']}\n"
        f"📝 **Special Need:** {special_note}\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━"
    )

    barber_kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🔎 Check booking", callback_data=f"status_checked_{order_id}"),
        InlineKeyboardButton(text="❌ Reject", callback_data=f"status_reject_{order_id}")
    ]])

    await bot.send_photo(
        chat_id=BARBER_CHAT_ID,
        photo=data["payment_photo"],
        caption=barber_caption,
        reply_markup=barber_kb,
        parse_mode="Markdown"
    )

    customer_receipt = (
        f"🎉 **ORDER SUBMITTED ({order_id})**\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"• **Service:** {data['service_name']}\n"
        f"• **Shift:** {data['shift']}\n"
        f"• **Special Need:** {special_note}\n"
        f"• **Status:** ⏳ *Pending Verification*\n\n"
        "You will receive an instant notification here as soon as the barber approves your payment screenshot.\n"
        "👉 Tap `/myorders` anytime to check your status!"
    )
    await msg_obj.answer(customer_receipt, parse_mode="Markdown")

@dp.callback_query(OrderFlow.sending_special_note, F.data == "skip_special_note")
async def skip_note_callback(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text("⏳ Submitting your order...")
    await submit_booking(callback.message, state, "None", callback.from_user)
    await callback.answer()

@dp.message(OrderFlow.sending_special_note, F.text)
async def receive_note_text(message: Message, state: FSMContext):
    await submit_booking(message, state, message.text, message.from_user)

# 8. Customer Checks Order Status (/myorders or button)
@dp.message(Command("myorders"))
async def check_order_cmd(message: Message):
    order = next(
        (item for item in ORDERS_DB.values() if item.get("user_id") == message.from_user.id),
        None,
    )
    if not order:
        await message.answer("📭 You have no active bookings yet. Tap `/start` to view services and book!")
        return
    await message.answer(
        f"📋 **YOUR BOOKING ({order['order_id']})**\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"✂️ **Service:** {order['service']} ({order['price']})\n"
        f"🕒 **Shift:** {order['shift']}\n"
        f"📝 **Special Note:** {order['note']}\n"
        f"📌 **Status:** **{status_label(order['status'])}**",
        parse_mode="Markdown"
    )

@dp.callback_query(F.data == "check_my_order")
async def check_order_btn(callback: CallbackQuery):
    order = next(
        (item for item in ORDERS_DB.values()
         if item.get("user_id") == callback.from_user.id
         and item["status"] not in {"complete", "cancel", "reject"}),
        None,
    )
    if not order:
        await callback.answer("You have no active bookings yet!", show_alert=True)
        return
    await callback.message.answer(
        f"📋 **YOUR BOOKING ({order['order_id']})**\n"
        f"• **Service:** {order['service']}\n"
        f"• **Shift:** {order['shift']}\n"
        f"• **Status:** **{status_label(order['status'])}**",
        parse_mode="Markdown"
    )
    await callback.answer()

# 9. Barber Admin Checks All Bookings (/allorders) & Updates Status
@dp.message(Command("allorders"))
async def barber_view_all(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Only the Barber Admin can use this command.")
        return
    if not ORDERS_DB:
        await message.answer("📭 No bookings received yet today.")
        return

    await message.answer("💈 **ALL CUSTOMER BOOKINGS** 💈", parse_mode="Markdown")
    for order in ORDERS_DB.values():
        await send_admin_order(message.chat.id, order)


def admin_order_keyboard(order_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🔎 Checked", callback_data=f"status_checked_{order_id}"),
            InlineKeyboardButton(text="✅ Complete", callback_data=f"status_complete_{order_id}"),
        ],
        [
            InlineKeyboardButton(text="🚫 Cancel", callback_data=f"status_cancel_{order_id}"),
            InlineKeyboardButton(text="❌ Reject", callback_data=f"status_reject_{order_id}"),
        ],
    ])


def order_details(order: dict) -> str:
    return (
        f"🔹 **{order['order_id']}** — {order['customer']}\n"
        f"🗓 **Created:** {order.get('created_at', 'Unknown')}\n"
        f"✂️ **Service:** {order['service']} ({order['price']})\n"
        f"🕒 **Shift:** {order['shift']}\n"
        f"📞 **Phone:** `{order['phone']}`\n"
        f"📍 **Address:** {order['address']}\n"
        f"📝 **Note:** {order['note']}\n"
        f"📌 **Status:** {status_label(order['status'])}"
    )


async def send_admin_order(chat_id: int, order: dict):
    await bot.send_photo(
        chat_id=chat_id,
        photo=order["payment_photo"],
        caption=order_details(order) + "\n\n📸 Payment screenshot attached.",
        reply_markup=admin_order_keyboard(order["order_id"]),
        parse_mode="Markdown",
    )


@dp.callback_query(F.data.startswith("status_"))
async def update_order_status(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Only the Barber Admin can change booking status.", show_alert=True)
        return
    _, new_status, order_id = callback.data.split("_", 2)
    order = ORDERS_DB.get(order_id)
    if not order or new_status not in ORDER_STATUSES:
        await callback.answer("Booking not found.", show_alert=True)
        return
    order["status"] = new_status
    save_data()
    await bot.send_message(
        order["user_id"],
        f"📌 **Booking {order_id} updated**\nYour booking status is now: **{status_label(new_status)}**.",
        parse_mode="Markdown",
    )
    await callback.message.edit_caption(
        caption=order_details(order) + "\n\n📸 Payment screenshot attached.",
        reply_markup=admin_order_keyboard(order_id),
        parse_mode="Markdown",
    )
    await callback.answer("Customer notified and booking updated.")


@dp.message(Command("services"))
async def admin_services(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Only the Barber Admin can manage services.")
        return
    lines = ["🛠 **SERVICE MANAGEMENT**", "Use `/addservice` or `/editservice <id>`."]
    for service_id, service in SERVICES.items():
        lines.append(
            f"`{service_id}` — {service['name']} | {service['price']} | deposit {service['deposit']}"
        )
    await message.answer("\n".join(lines), parse_mode="Markdown")


@dp.message(Command("adminhelp"))
async def admin_help(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Only the Barber Admin can use this command.")
        return
    await message.answer(
        "🔐 **ADMIN CONTROLS**\n"
        "• `/allorders` — view every booking and payment screenshot\n"
        "• `/services` — list services and prices\n"
        "• `/addservice` — add a service\n"
        "• `/editservice <id>` — update a service\n"
        "Use the buttons under each booking to notify the customer of status changes.",
        parse_mode="Markdown",
    )


@dp.message(Command("addservice"))
async def add_service_start(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Only the Barber Admin can manage services.")
        return
    await state.set_state(AdminFlow.adding_service)
    await message.answer(
        "Send the new service as:\n`service_id | service name | total price | deposit`\n"
        "Example: `svc_kids | 👦 Kids Cut | 250 ETB | 100 ETB`",
        parse_mode="Markdown",
    )


@dp.message(AdminFlow.adding_service, F.text)
async def add_service(message: Message, state: FSMContext):
    parts = [part.strip() for part in message.text.split("|")]
    if len(parts) != 4 or not parts[0] or parts[0] in SERVICES:
        await message.answer("Invalid format or service ID already exists. Please try again.")
        return
    service_id, name, price, deposit = parts
    SERVICES[service_id] = {"name": name, "price": price, "deposit": deposit}
    save_data()
    await state.clear()
    await message.answer(f"✅ Service `{service_id}` added. Customers can book it now.", parse_mode="Markdown")


@dp.message(Command("editservice"))
async def edit_service_start(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Only the Barber Admin can manage services.")
        return
    parts = message.text.split(maxsplit=1)
    if len(parts) != 2 or parts[1].strip() not in SERVICES:
        await message.answer("Usage: `/editservice <service_id>`", parse_mode="Markdown")
        return
    service_id = parts[1].strip()
    await state.update_data(service_id=service_id)
    await state.set_state(AdminFlow.editing_service)
    await message.answer(
        f"Send updated values for `{service_id}` as:\n`service name | total price | deposit`",
        parse_mode="Markdown",
    )


@dp.message(AdminFlow.editing_service, F.text)
async def edit_service(message: Message, state: FSMContext):
    parts = [part.strip() for part in message.text.split("|")]
    if len(parts) != 3:
        await message.answer("Invalid format. Use: `service name | total price | deposit`", parse_mode="Markdown")
        return
    data = await state.get_data()
    SERVICES[data["service_id"]] = {"name": parts[0], "price": parts[1], "deposit": parts[2]}
    save_data()
    await state.clear()
    await message.answer(f"✅ Service `{data['service_id']}` updated.", parse_mode="Markdown")

async def main():
    await setup_bot_menu(bot)
    logging.info("High-speed Barber Bot is live!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())