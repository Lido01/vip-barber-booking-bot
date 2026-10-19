import os
import re
from html import escape
import telebot
from telebot.types import (
    BotCommand,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardRemove,
)
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

def configure_bot_commands():
    bot.set_my_commands([
        BotCommand("start", "Open the customer menu"),
        BotCommand("menu", "Show the customer menu"),
        BotCommand("help", "Get help and contact support"),
        BotCommand("reset", "Clear the old menu and start again"),
        BotCommand("admin", "Open the admin dashboard"),
    ])

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
admin_data = {}
ADMIN_PAGE_SIZE = 8

def html_text(value):
    return escape(str(value or ""))

def is_admin(chat_id):
    return str(chat_id) == str(ADMIN_CHAT_ID)

def admin_dashboard_markup():
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        InlineKeyboardButton("📋 All bookings", callback_data="adm_bookings_all_0"),
        InlineKeyboardButton("⏳ Pending bookings", callback_data="adm_bookings_pending_0"),
        InlineKeyboardButton("💈 Manage services", callback_data="adm_services"),
    )
    return keyboard

def send_admin_dashboard(chat_id):
    bot.send_message(
        chat_id,
        "⚡ <b>VIP Barber Shop Manager Dashboard</b>\nChoose an action:",
        reply_markup=admin_dashboard_markup(),
        parse_mode="HTML",
    )

def booking_status_icon(status):
    return {"Pending": "🟡", "Confirmed": "🟢", "Rejected": "🔴"}.get(status, "⚪")

def booking_action_markup(row_number, customer_chat_id):
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton(
            "Confirm ✅",
            callback_data=f"approve_{row_number}_{customer_chat_id}",
        ),
        InlineKeyboardButton(
            "Reject ❌",
            callback_data=f"deny_{row_number}_{customer_chat_id}",
        ),
    )
    return keyboard

def get_booking_records():
    rows = bookings_sheet.get_all_values()
    if not rows:
        return []
    headers = rows[0]
    records = []
    for row_number, row in enumerate(rows[1:], 2):
        record = dict(zip(headers, row))
        record["_row_number"] = row_number
        records.append(record)
    return records

def send_admin_bookings(chat_id, status_filter=None, page=0):
    records = get_booking_records()
    if status_filter:
        records = [r for r in records if r.get("Status", "Pending") == status_filter]
    records.reverse()

    start = page * ADMIN_PAGE_SIZE
    page_records = records[start:start + ADMIN_PAGE_SIZE]
    title = "All bookings" if not status_filter else f"{status_filter} bookings"
    if not page_records:
        bot.send_message(chat_id, f"ℹ️ No {title.lower()} found.", reply_markup=admin_dashboard_markup())
        return

    lines = [f"📋 <b>{title}</b> ({len(records)} total)\n"]
    for record in page_records:
        row_number = record["_row_number"]
        status = record.get("Status", "Pending")
        lines.append(
            f"<b>#{row_number}</b> {booking_status_icon(status)} <b>{html_text(record.get('Customer Name'))}</b>\n"
            f"📞 {html_text(record.get('Phone'))} | 💬 {html_text(record.get('Telegram') or record.get('Username'))}\n"
            f"📍 {html_text(record.get('Address'))}\n"
            f"🕒 {html_text(record.get('Timestamp'))}\n"
            f"🆔 Customer chat: <code>{html_text(record.get('Chat ID'))}</code>\n"
        )

    keyboard = InlineKeyboardMarkup(row_width=2)
    for record in page_records:
        if record.get("Status", "Pending") == "Pending":
            keyboard.add(
                InlineKeyboardButton(
                    f"Confirm #{record['_row_number']} ✅",
                    callback_data=f"approve_{record['_row_number']}_{record.get('Chat ID', '')}",
                ),
                InlineKeyboardButton(
                    f"Reject #{record['_row_number']} ❌",
                    callback_data=f"deny_{record['_row_number']}_{record.get('Chat ID', '')}",
                ),
            )
    navigation = []
    if page > 0:
        navigation.append(InlineKeyboardButton("⬅️ Previous", callback_data=f"adm_bookings_{status_filter or 'all'}_{page - 1}"))
    if start + ADMIN_PAGE_SIZE < len(records):
        navigation.append(InlineKeyboardButton("Next ➡️", callback_data=f"adm_bookings_{status_filter or 'all'}_{page + 1}"))
    if navigation:
        keyboard.row(*navigation)
    keyboard.add(InlineKeyboardButton("⬅️ Dashboard", callback_data="adm_dashboard"))
    bot.send_message(chat_id, "\n".join(lines), reply_markup=keyboard, parse_mode="HTML")

def service_headers():
    headers = services_sheet.row_values(1)
    required = ["Service Name", "Price (ETB)", "Duration"]
    if not headers:
        services_sheet.append_row(required)
        return required
    missing = [header for header in required if header not in headers]
    if missing:
        raise ValueError(f"Services sheet is missing columns: {', '.join(missing)}")
    return headers

def send_services_admin(chat_id):
    headers = service_headers()
    rows = services_sheet.get_all_records()
    keyboard = InlineKeyboardMarkup(row_width=1)
    for offset, service in enumerate(rows, 2):
        name = service.get("Service Name", "Unnamed service")
        price = service.get("Price (ETB)", "")
        duration = service.get("Duration", "")
        keyboard.add(InlineKeyboardButton(
            f"✏️ {str(name)[:30]} ({price} ETB)",
            callback_data=f"svc_edit_{offset}",
        ))
    keyboard.add(InlineKeyboardButton("➕ Add service", callback_data="svc_add"))
    keyboard.add(InlineKeyboardButton("⬅️ Dashboard", callback_data="adm_dashboard"))
    text = "💈 <b>Service management</b>\n\n"
    if rows:
        for service in rows:
            text += f"🔹 <b>{html_text(service.get('Service Name'))}</b> — {html_text(service.get('Price (ETB)'))} ETB, {html_text(service.get('Duration'))}\n"
    else:
        text += "No services have been added yet.\n"
    bot.send_message(chat_id, text, reply_markup=keyboard, parse_mode="HTML")

# ==========================================
# INTERACTIVE MAIN MENU KEYBOARD SYSTEM
# ==========================================

def send_main_menu(chat_id, text="🏠 <b>VIP Barber Shop Main Menu</b>\nSelect an option below to proceed:"):
    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row(KeyboardButton("💇‍♂️ Book a Haircut Now"))
    markup.row(KeyboardButton("📅 View My Bookings"), KeyboardButton("💈 Our Services & Prices"))
    markup.row(KeyboardButton("⚡ Quick Menu"), KeyboardButton("🆘 Help / Contact Support"))
    if is_admin(chat_id):
        markup.row(KeyboardButton("🛠️ Admin Dashboard"))
    bot.send_message(chat_id, text, reply_markup=markup, parse_mode="HTML")

def send_quick_menu(chat_id):
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("💇‍♂️ Book", callback_data="quick_book"),
        InlineKeyboardButton("📅 My bookings", callback_data="quick_my_bookings"),
        InlineKeyboardButton("💈 Services", callback_data="quick_services"),
        InlineKeyboardButton("🆘 Support", callback_data="quick_support"),
    )
    if is_admin(chat_id):
        keyboard.add(InlineKeyboardButton("🛠️ Admin dashboard", callback_data="adm_dashboard"))
    bot.send_message(chat_id, "⚡ <b>Quick Menu</b>\nChoose an option:", reply_markup=keyboard, parse_mode="HTML")

def clear_old_menu(chat_id):
    bot.send_message(chat_id, "Menu refreshed.", reply_markup=ReplyKeyboardRemove())

@bot.message_handler(commands=['start', 'menu'])
def handle_start_or_menu(message):
    chat_id = message.chat.id
    first_name = html_text(message.from_user.first_name)
    clear_old_menu(chat_id)
    send_main_menu(chat_id, f"👋 Hello {first_name}! Welcome to the <b>VIP Barber Shop</b>.")

@bot.message_handler(commands=['reset'])
def handle_reset(message):
    clear_old_menu(message.chat.id)
    first_name = html_text(message.from_user.first_name)
    send_main_menu(message.chat.id, f"👋 Hello {first_name}! Welcome to the <b>VIP Barber Shop</b>.")

@bot.message_handler(commands=['help'])
def handle_help(message):
    send_support_menu(message.chat.id)

def send_support_menu(chat_id):
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton("💬 Contact the administrator", url=f"tg://user?id={ADMIN_CHAT_ID}"))
    bot.send_message(
        chat_id,
        "🆘 <b>Support</b>\n\nFor help with a booking, contact the administrator directly.",
        reply_markup=keyboard,
        parse_mode="HTML",
    )

@bot.message_handler(commands=['admin'])
def handle_admin_panel(message):
    chat_id = str(message.chat.id)
    if not is_admin(chat_id):
        bot.send_message(chat_id, "❌ Restricted entry portal.")
        return
    send_admin_dashboard(chat_id)

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
                status = r.get('Status', 'Pending')
                timestamp = html_text(r.get('Timestamp'))
                
                status_icon = "🟡" if status == "Pending" else "🟢" if status == "Confirmed" else "🔴"
                report += f"{idx}. 👤 <b>Name:</b> {name}\n📍 <b>Address:</b> {address}\n{status_icon} <b>Status:</b> {status}\n🕒 Booked on: <i>{timestamp}</i>\n\n"
            bot.send_message(chat_id, report, parse_mode="HTML")
        except Exception as e:
            bot.send_message(chat_id, "⚠️ Failed to look up your booking information.")
            print(f"User database lookup failure: {e}")

    elif text == "🆘 Help / Contact Support":
        send_support_menu(chat_id)

    elif text == "⚡ Quick Menu":
        send_quick_menu(chat_id)

    elif text == "🛠️ Admin Dashboard":
        if is_admin(chat_id):
            send_admin_dashboard(chat_id)
        else:
            bot.send_message(chat_id, "This option is available only to the administrator.")

    else:
        bot.send_message(
            chat_id,
            "I did not recognize that option. Please choose one of the menu buttons below.",
            reply_markup=None,
        )
        send_main_menu(chat_id)

# ==========================================
# CUSTOMER DATA COLLECTION PROCESS
# ==========================================

def get_name(message):
    chat_id = message.chat.id
    if chat_id not in user_data: return handle_start_or_menu(message)
    
    if not message.text or not message.text.strip():
        bot.send_message(chat_id, "Please enter your full name as text.")
        bot.register_next_step_handler(message, get_name)
        return

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
        raw_phone = (message.text or "").strip().replace(" ", "").replace("+", "")
    
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
    
    block = (message.text or "").strip()
    if not re.fullmatch(r"[0-9]+", block):
        bot.send_message(chat_id, "Please enter the block number using whole digits only, for example: 12.")
        bot.register_next_step_handler(message, get_block)
        return

    user_data[chat_id]['block'] = int(block)
    bot.send_message(chat_id, "🚪 Enter your <b>Room Number / Office Number</b>:", parse_mode="HTML")
    bot.register_next_step_handler(message, get_room)

def get_room(message):
    chat_id = message.chat.id
    if chat_id not in user_data: return handle_start_or_menu(message)
    
    room = (message.text or "").strip()
    if not re.fullmatch(r"[0-9]+", room):
        bot.send_message(chat_id, "Please enter the room number using whole digits only, for example: 204.")
        bot.register_next_step_handler(message, get_room)
        return

    user_data[chat_id]['room'] = int(room)
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
        
        bot.send_message(chat_id, "✅ <b>Booking Submitted Successfully!</b>\nYour appointment is logged. We will contact you shortly.", parse_mode="HTML")
        send_main_menu(chat_id)
        
        # Build interactive actions panel for real-time manager handling
        keyboard = booking_action_markup(next_row, chat_id)
        
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

    try:
        headers = bookings_sheet.row_values(1)
        if "Status" not in headers:
            raise ValueError("The Bookings sheet must contain a 'Status' column.")

        row_number = int(row_number)
        status_column = headers.index("Status") + 1
        new_status = "Rejected" if action == "deny" else "Confirmed"
        bookings_sheet.update_cell(row_number, status_column, new_status)
        customer_message = f"📣 Your booking status is now: <b>{new_status}</b>."
        callback_message = f"Booking {new_status.lower()}."

        bot.answer_callback_query(call.id, callback_message)
        bot.edit_message_reply_markup(
            call.message.chat.id,
            call.message.message_id,
            reply_markup=None,
        )
        bot.send_message(
            customer_chat_id,
            customer_message,
            parse_mode="HTML",
        )
    except Exception as e:
        bot.answer_callback_query(call.id, "Could not update booking.", show_alert=True)
        print(f"Error updating booking status: {e}", flush=True)

@bot.callback_query_handler(func=lambda call: call.data.startswith(("adm_", "svc_")))
def handle_admin_navigation(call):
    if not is_admin(call.message.chat.id):
        bot.answer_callback_query(call.id, "Restricted action.", show_alert=True)
        return

    try:
        parts = call.data.split("_")
        if call.data == "adm_dashboard":
            bot.answer_callback_query(call.id)
            send_admin_dashboard(call.message.chat.id)
        elif parts[0:2] == ["adm", "bookings"]:
            status_filter = None if parts[2] == "all" else parts[2].title()
            bot.answer_callback_query(call.id)
            send_admin_bookings(call.message.chat.id, status_filter, int(parts[3]))
        elif call.data == "adm_services":
            bot.answer_callback_query(call.id)
            send_services_admin(call.message.chat.id)
        elif call.data == "svc_add":
            admin_data[call.message.chat.id] = {"mode": "add"}
            bot.answer_callback_query(call.id)
            bot.send_message(call.message.chat.id, "Enter the new service name:")
            bot.register_next_step_handler(call.message, get_service_name)
        elif parts[0:2] == ["svc", "edit"]:
            admin_data[call.message.chat.id] = {"mode": "edit", "row": int(parts[2])}
            bot.answer_callback_query(call.id)
            bot.send_message(call.message.chat.id, "Enter the new service name:")
            bot.register_next_step_handler(call.message, get_service_name)
    except Exception as e:
        bot.answer_callback_query(call.id, "Could not open that admin action.", show_alert=True)
        print(f"Admin navigation error: {e}", flush=True)

@bot.callback_query_handler(func=lambda call: call.data.startswith("quick_"))
def handle_quick_menu(call):
    if call.data == "quick_book":
        bot.answer_callback_query(call.id)
        username = f"@{call.from_user.username}" if call.from_user.username else "No Username"
        user_data[call.message.chat.id] = {"username": username}
        bot.send_message(
            call.message.chat.id,
            "✍️ Please enter your <b>Full Name</b>:",
            reply_markup=ReplyKeyboardRemove(),
            parse_mode="HTML",
        )
        bot.register_next_step_handler(call.message, get_name)
    elif call.data == "quick_my_bookings":
        bot.answer_callback_query(call.id)
        show_customer_bookings(call.message.chat.id)
    elif call.data == "quick_services":
        bot.answer_callback_query(call.id)
        show_services(call.message.chat.id)
    elif call.data == "quick_support":
        bot.answer_callback_query(call.id)
        send_support_menu(call.message.chat.id)

def show_services(chat_id):
    try:
        services = services_sheet.get_all_records()
        msg = "⚡ <b>What We Do (Pay in Person After Service):</b>\n\n"
        for service in services:
            msg += (
                f"🔹 <b>{html_text(service.get('Service Name'))}</b>\n"
                f"💰 Price: <code>{html_text(service.get('Price (ETB)'))} ETB</code> | "
                f"⏳ Duration: {html_text(service.get('Duration'))}\n\n"
            )
        bot.send_message(chat_id, msg, parse_mode="HTML")
    except Exception as e:
        bot.send_message(chat_id, "⚠️ Services are temporarily unavailable.")
        print(f"Error reading services: {e}", flush=True)

def show_customer_bookings(chat_id):
    try:
        records = [r for r in get_booking_records() if str(r.get("Chat ID")) == str(chat_id)]
        if not records:
            bot.send_message(chat_id, "ℹ️ You have no bookings yet.")
            return
        report = "📅 <b>Your bookings</b>\n\n"
        for record in records:
            status = record.get("Status", "Pending")
            report += (
                f"👤 <b>{html_text(record.get('Customer Name'))}</b>\n"
                f"📍 {html_text(record.get('Address'))}\n"
                f"{booking_status_icon(status)} <b>{html_text(status)}</b>\n"
                f"🕒 {html_text(record.get('Timestamp'))}\n\n"
            )
        bot.send_message(chat_id, report, parse_mode="HTML")
    except Exception as e:
        bot.send_message(chat_id, "⚠️ Your bookings are temporarily unavailable.")
        print(f"Customer booking lookup error: {e}", flush=True)

def get_service_name(message):
    if not is_admin(message.chat.id) or message.chat.id not in admin_data:
        return
    admin_data[message.chat.id]["name"] = message.text.strip()
    bot.send_message(message.chat.id, "Enter the price (numbers or text such as 250 ETB):")
    bot.register_next_step_handler(message, get_service_price)

def get_service_price(message):
    if not is_admin(message.chat.id) or message.chat.id not in admin_data:
        return
    admin_data[message.chat.id]["price"] = message.text.strip()
    bot.send_message(message.chat.id, "Enter the duration (for example, 30 minutes):")
    bot.register_next_step_handler(message, get_service_duration)

def get_service_duration(message):
    if not is_admin(message.chat.id) or message.chat.id not in admin_data:
        return
    data = admin_data.pop(message.chat.id)
    try:
        headers = service_headers()
        values = [data["name"], data["price"], message.text.strip()]
        if data["mode"] == "add":
            services_sheet.append_row(values)
            result = "Service added successfully."
        else:
            row_number = data["row"]
            for header, value in zip(("Service Name", "Price (ETB)", "Duration"), values):
                services_sheet.update_cell(row_number, headers.index(header) + 1, value)
            result = "Service updated successfully."
        bot.send_message(message.chat.id, f"✅ {result}", reply_markup=admin_dashboard_markup())
    except Exception as e:
        bot.send_message(message.chat.id, "⚠️ Could not save the service. Check the Services sheet headers.")
        print(f"Service management error: {e}", flush=True)


if __name__ == "__main__":
    try:
        configure_bot_commands()
    except Exception as e:
        print(f"WARNING: Could not update Telegram command menu: {e}", flush=True)
    print("System Active. Press Ctrl+C to terminate the polling loop.", flush=True)
    bot.infinity_polling()
