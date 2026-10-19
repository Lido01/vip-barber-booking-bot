import os
from html import escape
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
import gspread
from datetime import datetime
from dotenv import load_dotenv

# Load environment configuration variables
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID") 

if not BOT_TOKEN or not ADMIN_CHAT_ID:
    print("ERROR: BOT_TOKEN or ADMIN_CHAT_ID is missing from your .env file!", flush=True)
    exit(1)

bot = telebot.TeleBot(BOT_TOKEN)

try:
    client = gspread.service_account(filename=os.path.join(BASE_DIR, "credentials.json"))
    spreadsheet = client.open("VIP Booking Bot")
    bookings_sheet = spreadsheet.worksheet("Bookings")
    services_sheet = spreadsheet.worksheet("Services")
    print("Successfully connected to Google Sheets!", flush=True)
except Exception as e:
    print(f"DATABASE ERROR: Could not connect. Reason: {e}", flush=True)
    exit(1)

# Active state configuration store session dictionaries
user_data = {}

def html_text(value):
    return escape(str(value or ""))

# ==========================================
# INTERACTIVE MAIN MENU KEYBOARD SYSTEM
# ==========================================

def send_main_menu(chat_id, text="🏠 <b>VIP Barber Shop Main Menu</b>\nSelect an option below to proceed:"):
    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row(KeyboardButton("💇‍♂️ Book a Haircut Now"))
    markup.row(KeyboardButton("📅 View My Bookings"), KeyboardButton("💈 Our Services & Prices"))
    bot.send_message(chat_id, text, reply_markup=markup, parse_mode="HTML")

@bot.message_handler(commands=['start', 'menu'])
def handle_start_or_menu(message):
    chat_id = message.chat.id
    first_name = html_text(message.from_user.first_name)
    send_main_menu(chat_id, f"👋 Hello {first_name}! Welcome to the <b>VIP Barber Shop</b>.")

@bot.message_handler(commands=['admin'])
def handle_admin_panel(message):
    chat_id = str(message.chat.id)
    if chat_id != str(ADMIN_CHAT_ID):
        bot.send_message(chat_id, "❌ Restricted entry portal.")
        return

    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        InlineKeyboardButton("⏳ View Pending Bookings", callback_data="adm_list_pending"),
        InlineKeyboardButton("📋 View All Bookings (Latest)", callback_data="adm_list_all")
    )
    bot.send_message(chat_id, "⚡ <b>VIP Barber Shop Manager Dashboard</b>\nSelect a tool path below:", reply_markup=keyboard, parse_mode="HTML")

@bot.message_handler(func=lambda msg: True)
def handle_menu_navigation(message):
    chat_id = message.chat.id
    text = message.text

    if text == "💇‍♂️ Book a Haircut Now":
        username = f"@{message.from_user.username}" if message.from_user.username else "No Username"
        user_data[chat_id] = {'username': username}
        
        bot.send_message(chat_id, "✍️ Please enter your <b>Full Name</b>:", reply_markup=ReplyKeyboardRemove(), parse_mode="HTML")
        bot.register_next_step_handler(message, get_name)
        
    elif text == "💈 Our Services & Prices":
        try:
            services = services_sheet.get_all_records()
            msg = "⚡ <b>What We Do (Pay in Person After Service):</b>\n\n"
            for s in services:
                service_name = html_text(s.get('Service Name'))
                price = html_text(s.get('Price (ETB)'))
                duration = html_text(s.get('Duration'))
                msg += f"🔹 <b>{service_name}</b>\n💰 Price: <code>{price} ETB</code> | ⏳ Duration: {duration}\n\n"
            bot.send_message(chat_id, msg, parse_mode="HTML")
        except Exception as e:
            bot.send_message(chat_id, "⚠️ Could not pull services matrix. Please try again.")
            print(f"Error reading menu: {e}")
            
    elif text == "📅 View My Bookings":
        try:
            all_rows = bookings_sheet.get_all_values()
            if len(all_rows) <= 1:
                bot.send_message(chat_id, "ℹ️ You have no active bookings on file yet!")
                return
                
            headers = all_rows[0]
            records = [dict(zip(headers, row)) for row in all_rows[1:]]
            my_records = [r for r in records if str(r.get('Chat ID')) == str(chat_id)]
            
            if not my_records:
                bot.send_message(chat_id, "ℹ️ You have no active bookings on file yet!")
                return
                
            report = "📅 <b>Your Registered Appointments:</b>\n\n"
            for idx, r in enumerate(my_records, 1):
                name = html_text(r.get('Customer Name'))
                address = html_text(r.get('Address'))
                status = html_text(r.get('Status'))
                timestamp = html_text(r.get('Timestamp'))
                
                status_icon = "🟡" if status == "Pending" else "🟢" if status == "Confirmed" else "🔴"
                report += f"{idx}. 👤 <b>Name:</b> {name}\n📍 <b>Address:</b> {address}\n{status_icon} <b>Status:</b> {status}\n🕒 Booked on: <i>{timestamp}</i>\n\n"
            bot.send_message(chat_id, report, parse_mode="HTML")
        except Exception as e:
            bot.send_message(chat_id, "⚠️ Failed to look up your booking information.")
            print(f"User database lookup failure: {e}")

# ==========================================
# CUSTOMER DATA COLLECTION PROCESS
# ==========================================

def get_name(message):
    chat_id = message.chat.id
    if chat_id not in user_data: return handle_start_or_menu(message)
    
    user_data[chat_id]['name'] = message.text.strip()
    
    # Create Native Share Contact button layout along with clear manual entry options
    phone_markup = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    phone_markup.add(KeyboardButton("📱 Share My Phone Number", request_contact=True))
    
    bot.send_message(chat_id, "📞 Please share your phone using the button below or type it manually (digits only):", reply_markup=phone_markup, parse_mode="HTML")
    bot.register_next_step_handler(message, get_phone)

def get_phone(message):
    chat_id = message.chat.id
    if chat_id not in user_data: return handle_start_or_menu(message)
    
    # Detect if user clicked the native contact share button or typed text manually
    if message.contact is not None:
        raw_phone = message.contact.phone_number.strip().replace(" ", "").replace("+", "")
    else:
        raw_phone = message.text.strip().replace(" ", "").replace("+", "")
    
    if not raw_phone.isdigit() or len(raw_phone) < 9 or len(raw_phone) > 15:
        bot.send_message(chat_id, "⚠️ <b>Invalid phone entry!</b> Please type only digits or press the Share Contact button:", parse_mode="HTML")
        bot.register_next_step_handler(message, get_phone)
        return
        
    user_data[chat_id]['phone'] = raw_phone
    bot.send_message(chat_id, "🏢 Enter your <b>Block Number / Building Name</b>:", reply_markup=ReplyKeyboardRemove(), parse_mode="HTML")
    bot.register_next_step_handler(message, get_block)

def get_block(message):
    chat_id = message.chat.id
    if chat_id not in user_data: return handle_start_or_menu(message)
    
    user_data[chat_id]['block'] = message.text.strip()
    bot.send_message(chat_id, "🚪 Enter your <b>Room Number / Office Number</b>:", parse_mode="HTML")
    bot.register_next_step_handler(message, get_room)

def get_room(message):
    chat_id = message.chat.id
    if chat_id not in user_data: return handle_start_or_menu(message)
    
    user_data[chat_id]['room'] = message.text.strip()
    bot.send_message(chat_id, "✍️ Enter any <b>Optional Notes</b> (Preferred date/time) or type 'None':", parse_mode="HTML")
    bot.register_next_step_handler(message, get_optional_note)

def get_optional_note(message):
    chat_id = message.chat.id
    if chat_id not in user_data: return handle_start_or_menu(message)
    
    data = user_data[chat_id]
    data['note'] = message.text.strip() if message.text.lower() != 'none' else ""
    
    try:
        full_address = f"Block {data['block']}, Room {data['room']}"
        all_rows = bookings_sheet.get_all_values()
        next_row = len(all_rows) + 1
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        row_data = [
            next_row, data['username'], chat_id, data['name'], 
            data['phone'], full_address, data['note'], "Pending", timestamp
        ]
        bookings_sheet.append_row(row_data)
        
        del user_data[chat_id]
        
        bot.send_message(chat_id, "✅ <b>Booking Submitted Successfully!</b>\nYour appointment is logged. Please pay in person at the shop after your cut.", parse_mode="HTML")
        send_main_menu(chat_id)
        
        # Build interactive actions panel for real-time manager handling
        keyboard = InlineKeyboardMarkup()
        keyboard.row(
            InlineKeyboardButton("Confirm ✅", callback_data=f"approve_{next_row}_{chat_id}"),
            InlineKeyboardButton("Reject ❌", callback_data=f"deny_{next_row}_{chat_id}")
        )
        
        admin_msg = (
            f"🔔 <b>New Appointment Booked!</b> (Row {next_row})\n\n"
            f"👤 <b>Name:</b> {html_text(data['name'])}\n"
            f"💬 <b>Telegram:</b> {html_text(data['username'])}\n"
            f"📞 <b>Phone:</b> <code>{html_text(data['phone'])}</code>\n"
            f"📍 <b>Location:</b> {html_text(full_address)}\n"
            f"📝 <b>Notes:</b> {html_text(data['note'] if data['note'] else 'None')}\n"
            f"🕒 <b>Time:</b> {html_text(timestamp)}"
        )
        bot.send_message(ADMIN_CHAT_ID, admin_msg, reply_markup=keyboard, parse_mode="HTML")
        
    except Exception as e:
        bot.send_message(chat_id, "⚠️ Database write error occurred. Please try again.")
        print(f"Error logging line: {e}")
        send_main_menu(chat_id)

# ==========================================
# CALLBACK ROUTINES (ADMIN CONTROLS)
# ==========================================

@bot.callback_query_handler(func=lambda call: call.data.startswith(("approve_", "deny_")))
def handle_booking_decision(call):
    if str(call.message.chat.id) != str(ADMIN_CHAT_ID):
        bot.answer_callback_query(call.id, "Restricted action.", show_alert=True)
        return

    action, row_number, customer_chat_id = call.data.split("_", 2)
    status = "Confirmed" if action == "approve" else "Rejected"

    try:
        headers = bookings_sheet.row_values(1)
        if "Status" not in headers:
            raise ValueError("The Bookings sheet must contain a 'Status' column.")

        status_column = headers.index("Status") + 1
        bookings_sheet.update_cell(int(row_number), status_column, status)

        bot.answer_callback_query(call.id, f"Booking {status.lower()}.")
        bot.edit_message_reply_markup(
            call.message.chat.id,
            call.message.message_id,
            reply_markup=None,
        )
        bot.send_message(
            customer_chat_id,
            f"📣 Your booking status is now: <b>{status}</b>.",
            parse_mode="HTML",
        )
    except Exception as e:
        bot.answer_callback_query(call.id, "Could not update booking.", show_alert=True)
        print(f"Error updating booking status: {e}", flush=True)


if __name__ == "__main__":
    print("System Active. Press Ctrl+C to terminate the polling loop.", flush=True)
    bot.infinity_polling()
