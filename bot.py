import os
import re
from datetime import datetime

import gspread
import telebot
from dotenv import load_dotenv
from telebot.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID")

if not BOT_TOKEN or not ADMIN_CHAT_ID:
    raise RuntimeError("BOT_TOKEN and ADMIN_CHAT_ID must be set in .env")

ADMIN_CHAT_ID = str(ADMIN_CHAT_ID)
bot = telebot.TeleBot(BOT_TOKEN)
user_data = {}
ACTIVE_ORDER_STATUSES = {"pending", "confirmed", "booked", "in progress"}


def connect_sheets():
    client = gspread.service_account(filename="credentials.json")
    spreadsheet = client.open("VIP Booking Bot")
    return (
        spreadsheet.worksheet("Bookings"),
        spreadsheet.worksheet("Services"),
        spreadsheet.worksheet("Payment_Methods"),
    )


try:
    bookings_sheet, services_sheet, payments_sheet = connect_sheets()
    print("Successfully connected to Google Sheets.")
except gspread.exceptions.SpreadsheetNotFound as exc:
    raise RuntimeError(
        "Could not find the VIP Booking Bot spreadsheet. "
        "Share it with the service account and check its name."
    ) from exc
except Exception as exc:
    raise RuntimeError(f"Could not connect to Google Sheets: {exc}") from exc


def is_admin(message_or_call):
    chat_id = (
        message_or_call.message.chat.id
        if hasattr(message_or_call, "message")
        else message_or_call.chat.id
    )
    return str(chat_id) == ADMIN_CHAT_ID


def remove_keyboard():
    return ReplyKeyboardRemove()


def service_keyboard(services):
    markup = ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
    for service in services:
        name = str(service.get("Service Name", "")).strip()
        price = str(service.get("Price (ETB)", "")).strip()
        if name:
            markup.add(KeyboardButton(f"{name} - {price} ETB"))
    return markup


def admin_keyboard():
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(
        InlineKeyboardButton("All orders", callback_data="admin_orders_all"),
        InlineKeyboardButton("Latest orders", callback_data="admin_orders_latest"),
        InlineKeyboardButton("Orders in progress", callback_data="admin_orders_progress"),
        InlineKeyboardButton("Manage services", callback_data="admin_services"),
    )
    return markup


def get_order_value(order, *keys):
    for key in keys:
        value = order.get(key)
        if value not in (None, ""):
            return str(value).strip()
    return ""


def order_status(order):
    return get_order_value(order, "Status", "status").lower()


def order_summary(order):
    return (
        f"Order {get_order_value(order, 'Row ID', 'Order ID') or 'unknown'}\n"
        f"Customer: {get_order_value(order, 'Customer Name', 'Name') or 'unknown'}\n"
        f"Phone: {get_order_value(order, 'Phone Number', 'Phone') or 'unknown'}\n"
        f"Address: block {get_order_value(order, 'Block Number') or '-'}, "
        f"room {get_order_value(order, 'Room Number') or '-'}\n"
        f"Service: {get_order_value(order, 'Service Chosen', 'Service') or 'unknown'}\n"
        f"Status: {get_order_value(order, 'Status') or 'unknown'}\n"
        f"Created: {get_order_value(order, 'Timestamp', 'Created At') or 'unknown'}"
    )


@bot.message_handler(commands=["start"])
def start_booking(message):
    chat_id = message.chat.id
    username = f"@{message.from_user.username}" if message.from_user.username else "No username"
    user_data[chat_id] = {"username": username}
    bot.send_message(
        chat_id,
        "Welcome to VIP Barber Booking.\n\nPlease enter your full name:",
        reply_markup=remove_keyboard(),
    )
    bot.register_next_step_handler(message, get_name)


def get_name(message):
    if message.chat.id not in user_data:
        return start_booking(message)
    name = (message.text or "").strip()
    if not name:
        bot.send_message(message.chat.id, "Please enter a valid full name.")
        return bot.register_next_step_handler(message, get_name)
    user_data[message.chat.id]["name"] = name
    phone_button = KeyboardButton("Share phone number", request_contact=True)
    markup = ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
    markup.add(phone_button)
    bot.send_message(
        message.chat.id,
        "Please enter your mobile number using digits only, or tap Share phone number.\n"
        "Example: +251912345678",
        reply_markup=markup,
    )
    bot.register_next_step_handler(message, get_phone)


def normalize_phone(message):
    raw_phone = (
        message.contact.phone_number
        if message.content_type == "contact" and message.contact
        else (message.text or "")
    ).strip()
    digits = re.sub(r"[^\d]", "", raw_phone)
    if digits.startswith("251") and len(digits) == 12 and digits[3] in "79":
        return f"+{digits}"
    if digits.startswith("0") and len(digits) == 10 and digits[1] in "79":
        return f"+251{digits[1:]}"
    return None


def get_phone(message):
    if message.chat.id not in user_data:
        return start_booking(message)
    if (
        message.content_type == "contact"
        and message.contact
        and message.contact.user_id
        and message.contact.user_id != message.from_user.id
    ):
        bot.send_message(message.chat.id, "Please share your own mobile number.")
        return bot.register_next_step_handler(message, get_phone)
    phone = normalize_phone(message)
    if not phone:
        bot.send_message(
            message.chat.id,
            "That is not a valid Ethiopian mobile number. Please use 09/07XXXXXXXX "
            "or +2519/+2517XXXXXXXX.",
        )
        return bot.register_next_step_handler(message, get_phone)
    user_data[message.chat.id]["phone"] = phone
    bot.send_message(
        message.chat.id,
        "Enter the block number for your address:",
        reply_markup=remove_keyboard(),
    )
    bot.register_next_step_handler(message, get_block_number)


def get_block_number(message):
    if message.chat.id not in user_data:
        return start_booking(message)
    block = (message.text or "").strip()
    if not re.fullmatch(r"\d{1,10}", block):
        bot.send_message(message.chat.id, "Please enter a valid block number.")
        return bot.register_next_step_handler(message, get_block_number)
    user_data[message.chat.id]["block_number"] = block
    bot.send_message(message.chat.id, "Enter the room number:")
    bot.register_next_step_handler(message, get_room_number)


def get_room_number(message):
    if message.chat.id not in user_data:
        return start_booking(message)
    room = (message.text or "").strip()
    if not re.fullmatch(r"\d{1,10}", room):
        bot.send_message(message.chat.id, "Please enter a valid room number.")
        return bot.register_next_step_handler(message, get_room_number)
    user_data[message.chat.id]["room_number"] = room
    try:
        services = services_sheet.get_all_records()
        if not services:
            raise RuntimeError("The Services sheet has no services.")
        bot.send_message(
            message.chat.id,
            "Choose a service:",
            reply_markup=service_keyboard(services),
        )
        bot.register_next_step_handler(message, get_service)
    except Exception as exc:
        print(f"Error reading services: {exc}")
        bot.send_message(message.chat.id, "Services are temporarily unavailable. Please try later.")


def get_service(message):
    if message.chat.id not in user_data:
        return start_booking(message)
    selected = (message.text or "").strip()
    try:
        services = services_sheet.get_all_records()
        valid_services = {
            f"{s.get('Service Name', '').strip()} - {str(s.get('Price (ETB)', '')).strip()} ETB"
            for s in services
        }
        if selected not in valid_services:
            raise ValueError("invalid service")
    except ValueError:
        bot.send_message(message.chat.id, "Please choose a service using one of the buttons.")
        return bot.register_next_step_handler(message, get_service)
    except Exception as exc:
        print(f"Error validating service: {exc}")
        bot.send_message(message.chat.id, "Services are temporarily unavailable. Please try later.")
        return
    user_data[message.chat.id]["service"] = selected
    try:
        methods = payments_sheet.get_all_records()
        if not methods:
            raise RuntimeError("The Payment_Methods sheet has no methods.")
        markup = ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
        instructions = ["Available payment methods:\n"]
        for method in methods:
            provider = str(method.get("Provider Name", "")).strip()
            instructions.append(
                f"{provider}\nAccount: {method.get('Account Number', '')}\n"
                f"Account name: {method.get('Account Name', '')}\n"
            )
            markup.add(KeyboardButton(provider))
        bot.send_message(message.chat.id, "\n".join(instructions))
        bot.send_message(message.chat.id, "Choose the payment method:", reply_markup=markup)
        bot.register_next_step_handler(message, get_payment_method)
    except Exception as exc:
        print(f"Error reading payment methods: {exc}")
        bot.send_message(message.chat.id, "Payment methods are temporarily unavailable. Please try later.")


def get_payment_method(message):
    if message.chat.id not in user_data:
        return start_booking(message)
    selected = (message.text or "").strip()
    try:
        methods = payments_sheet.get_all_records()
        providers = {str(method.get("Provider Name", "")).strip() for method in methods}
        if selected not in providers:
            raise ValueError("invalid payment method")
    except ValueError:
        bot.send_message(message.chat.id, "Please choose a payment method using the buttons.")
        return bot.register_next_step_handler(message, get_payment_method)
    except Exception as exc:
        print(f"Error validating payment method: {exc}")
        bot.send_message(message.chat.id, "Payment methods are temporarily unavailable. Please try later.")
        return
    user_data[message.chat.id]["payment_method"] = selected
    bot.send_message(
        message.chat.id,
        "Send a payment screenshot, or type the transaction number:",
        reply_markup=remove_keyboard(),
    )
    bot.register_next_step_handler(message, get_payment_proof)


def get_payment_proof(message):
    if message.chat.id not in user_data:
        return start_booking(message)
    data = user_data[message.chat.id]
    if message.content_type == "photo":
        data["proof"] = message.photo[-1].file_id
        data["is_photo"] = True
    else:
        proof = (message.text or "").strip()
        if not proof:
            bot.send_message(message.chat.id, "Please send a screenshot or transaction number.")
            return bot.register_next_step_handler(message, get_payment_proof)
        data["proof"] = proof
        data["is_photo"] = False
    bot.send_message(message.chat.id, "Optional note, or type None:")
    bot.register_next_step_handler(message, finish_booking)


def finish_booking(message):
    chat_id = message.chat.id
    if chat_id not in user_data:
        return start_booking(message)
    data = user_data.pop(chat_id)
    note = (message.text or "").strip()
    note = "" if note.lower() == "none" else note
    try:
        row_id = len(bookings_sheet.get_all_values()) + 1
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        bookings_sheet.append_row(
            [
                row_id,
                data["username"],
                chat_id,
                data["name"],
                data["phone"],
                data["service"],
                data["payment_method"],
                data["proof"] if not data["is_photo"] else "Photo Sent",
                note,
                "Pending",
                timestamp,
                data["block_number"],
                data["room_number"],
            ]
        )
        bot.send_message(
            chat_id,
            f"Your booking was submitted successfully.\nOrder reference: {row_id}\n"
            "We will send an update after review.",
        )
        keyboard = InlineKeyboardMarkup()
        keyboard.row(
            InlineKeyboardButton("Confirm", callback_data=f"approve_{row_id}_{chat_id}"),
            InlineKeyboardButton("Reject", callback_data=f"deny_{row_id}_{chat_id}"),
        )
        admin_text = (
            f"New booking (order {row_id})\n\n"
            f"Name: {data['name']}\nTelegram: {data['username']}\nPhone: {data['phone']}\n"
            f"Address: block {data['block_number']}, room {data['room_number']}\n"
            f"Service: {data['service']}\nPayment: {data['payment_method']}\n"
            f"Note: {note or 'None'}"
        )
        if data["is_photo"]:
            bot.send_photo(ADMIN_CHAT_ID, data["proof"], caption=admin_text, reply_markup=keyboard)
        else:
            bot.send_message(ADMIN_CHAT_ID, f"{admin_text}\nTransaction: {data['proof']}", reply_markup=keyboard)
    except Exception as exc:
        print(f"Error saving booking: {exc}")
        bot.send_message(chat_id, "We could not save your booking. Please try again later.")


@bot.message_handler(commands=["admin"])
def admin_menu(message):
    if not is_admin(message):
        bot.send_message(message.chat.id, "Access denied.")
        return
    bot.send_message(message.chat.id, "Admin order and service management:", reply_markup=admin_keyboard())


@bot.callback_query_handler(func=lambda call: call.data.startswith(("approve_", "deny_")))
def handle_booking_decision(call):
    if not is_admin(call):
        bot.answer_callback_query(call.id, "Access denied.")
        return
    action, row_id, customer_chat_id = call.data.split("_")
    status = "Confirmed" if action == "approve" else "Rejected"
    try:
        bookings_sheet.update_cell(int(row_id), 10, status)
        if status == "Confirmed":
            bot.send_message(customer_chat_id, "Your booking is confirmed.")
        else:
            bot.send_message(customer_chat_id, "Your booking was rejected. Please contact the shop.")
        bot.answer_callback_query(call.id, f"Order {status.lower()}.")
        bot.edit_message_reply_markup(ADMIN_CHAT_ID, call.message.message_id, reply_markup=None)
    except Exception as exc:
        print(f"Error updating booking status: {exc}")
        bot.answer_callback_query(call.id, "Could not update this order.")


@bot.callback_query_handler(func=lambda call: call.data.startswith("admin_"))
def handle_admin_menu(call):
    if not is_admin(call):
        bot.answer_callback_query(call.id, "Access denied.")
        return
    try:
        if call.data == "admin_services":
            services = services_sheet.get_all_records()
            text = "\n".join(
                f"- {s.get('Service Name', 'Unnamed')}: {s.get('Price (ETB)', '-')} ETB"
                for s in services
            ) or "No services configured."
            bot.send_message(ADMIN_CHAT_ID, f"Services\n\n{text}")
        else:
            orders = bookings_sheet.get_all_records()
            if call.data == "admin_orders_latest":
                orders = orders[-5:]
                title = "Latest 5 orders"
            elif call.data == "admin_orders_progress":
                orders = [o for o in orders if order_status(o) in ACTIVE_ORDER_STATUSES]
                title = "Orders in progress"
            else:
                title = "All orders"
            if not orders:
                bot.send_message(ADMIN_CHAT_ID, f"{title}\n\nNo orders found.")
            else:
                bot.send_message(ADMIN_CHAT_ID, f"{title}\n\n" + "\n\n".join(order_summary(o) for o in orders))
        bot.answer_callback_query(call.id)
    except Exception as exc:
        print(f"Error loading admin data: {exc}")
        bot.answer_callback_query(call.id, "Could not load the requested data.")


print("System active.")
bot.infinity_polling()
