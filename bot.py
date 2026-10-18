import os
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
import gspread
from datetime import datetime
from dotenv import load_dotenv

# Load variables safely from local configuration system
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID") 

if not BOT_TOKEN or not ADMIN_CHAT_ID:
    print("❌ ERROR: BOT_TOKEN or ADMIN_CHAT_ID is missing from your .env file!")
    exit(1)

bot = telebot.TeleBot(BOT_TOKEN)

print("⏳ Attempting to bridge secure tunnel to Google API servers...")

try:
    # Modern direct verification interface bypasses library caching structures
    client = gspread.service_account(filename="credentials.json")
    
    # Open the database structures mapped cleanly inside Google Sheets
    spreadsheet = client.open("VIP Booking Bot")
    bookings_sheet = spreadsheet.worksheet("Bookings")
    services_sheet = spreadsheet.worksheet("Services")
    payments_sheet = spreadsheet.worksheet("Payment_Methods")
    print("✅ Successfully connected to Google Sheets!")
except gspread.exceptions.SpreadsheetNotFound:
    print("❌ DATABASE ERROR: Could not find a sheet named precisely 'Barbershop_System'.")
    print("👉 Make sure you shared the sheet with your service account email as an Editor!")
    exit(1)
except Exception as e:
    print(f"❌ CONNECTION INTERCEPTED: Your local internet router or firewall blocked the connection.")
    print(f"📋 Technical Reason: {e}")
    print("💡 FIX: Turn off your VPN or connect your PC to your phone's mobile hotspot, then run it again!")
    exit(1)

# Active state configuration store mapping dictionary
user_data = {}

@bot.message_handler(commands=['start'])
def start_booking(message):
    chat_id = message.chat.id
    username = f"@{message.from_user.username}" if message.from_user.username else "No Username"
    
    user_data[chat_id] = {'username': username}
    bot.send_message(chat_id, "✂️ Welcome to the Barbershop! Please enter your **Full Name**:")
    bot.register_next_step_handler(message, get_name)

def get_name(message):
    chat_id = message.chat.id
    if chat_id not in user_data: 
        return start_booking(message)
    user_data[chat_id]['name'] = message.text
    bot.send_message(chat_id, "📞 Please enter your **Phone Number**:")
    bot.register_next_step_handler(message, get_phone)

def get_phone(message):
    chat_id = message.chat.id
    if chat_id not in user_data: 
        return start_booking(message)
    user_data[chat_id]['phone'] = message.text
    
    try:
        services = services_sheet.get_all_records()
        markup = ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
        for s in services:
            markup.add(KeyboardButton(f"{s['Service Name']} - {s['Price (ETB)']} ETB"))
            
        bot.send_message(chat_id, "💈 Select the **Service** you want:", reply_markup=markup)
        bot.register_next_step_handler(message, get_service)
    except Exception as e:
        bot.send_message(chat_id, "⚠️ Error pulling services menu. Please try again later.")
        print(f"Error reading services: {e}")

def get_service(message):
    chat_id = message.chat.id
    if chat_id not in user_data: 
        return start_booking(message)
    user_data[chat_id]['service'] = message.text
    
    try:
        methods = payments_sheet.get_all_records()
        pay_instructions = "💵 **Available Payment Methods:**\n\n"
        markup = ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
        
        for m in methods:
            pay_instructions += f"🔹 **{m['Provider Name']}**\nAcc: `{m['Account Number']}`\nName: {m['Account Name']}\n\n"
            markup.add(KeyboardButton(m['Provider Name']))
            
        bot.send_message(chat_id, pay_instructions, parse_mode="Markdown")
        bot.send_message(chat_id, "Please select the **Payment Method** you used:", reply_markup=markup)
        bot.register_next_step_handler(message, get_payment_method)
    except Exception as e:
        bot.send_message(chat_id, "⚠️ Error pulling payment methods. Please try again.")
        print(f"Error reading payment methods: {e}")

def get_payment_method(message):
    chat_id = message.chat.id
    if chat_id not in user_data: 
        return start_booking(message)
    user_data[chat_id]['payment_method'] = message.text
    
    markup = telebot.types.ReplyKeyboardRemove()
    bot.send_message(chat_id, "📸 Please send a **Screenshot** of the payment OR type the **Transaction Number**:", reply_markup=markup)
    bot.register_next_step_handler(message, get_payment_proof)

def get_payment_proof(message):
    chat_id = message.chat.id
    if chat_id not in user_data: 
        return start_booking(message)
    data = user_data[chat_id]
    
    if message.content_type == 'photo':
        data['proof'] = message.photo[-1].file_id
        data['is_photo'] = True
    else:
        data['proof'] = message.text
        data['is_photo'] = False
        
    bot.send_message(chat_id, "✍️ Add any **Optional Notes** (e.g., preferred barber, specific time) or type 'None':")
    bot.register_next_step_handler(message, get_optional_note)

def get_optional_note(message):
    chat_id = message.chat.id
    if chat_id not in user_data: 
        return start_booking(message)
    data = user_data[chat_id]
    data['note'] = message.text if message.text.lower() != 'none' else ""
    
    try:
        all_rows = bookings_sheet.get_all_values()
        next_row = len(all_rows) + 1
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        row_data = [
            next_row, data['username'], chat_id, data['name'], data['phone'], 
            data['service'], data['payment_method'], data['proof'] if not data['is_photo'] else "Photo Sent", 
            data['note'], "Pending", timestamp
        ]
        bookings_sheet.append_row(row_data)
        
        bot.send_message(chat_id, "🙌 Thank you! Your booking details have been submitted. Waiting for admin confirmation.")
        
        keyboard = InlineKeyboardMarkup()
        keyboard.row(
            InlineKeyboardButton("Confirm ✅", callback_data=f"approve_{next_row}_{chat_id}"),
            InlineKeyboardButton("Reject ❌", callback_data=f"deny_{next_row}_{chat_id}")
        )
        
        admin_msg = (
            f"🔔 **New Booking Request!** (Row {next_row})\n\n"
            f"👤 **Name:** {data['name']}\n"
            f"💬 **Telegram:** {data['username']}\n"
            f"📞 **Phone:** {data['phone']}\n"
            f"💈 **Service:** {data['service']}\n"
            f"💳 **Method:** {data['payment_method']}\n"
            f"📝 **Note:** {data['note'] if data['note'] else 'None'}"
        )
        
        if data['is_photo']:
            bot.send_photo(ADMIN_CHAT_ID, data['proof'], caption=admin_msg, reply_markup=keyboard, parse_mode="Markdown")
        else:
            admin_msg += f"\n🔢 **Txn Details:** {data['proof']}"
            bot.send_message(ADMIN_CHAT_ID, admin_msg, reply_markup=keyboard, parse_mode="Markdown")
            
    except Exception as e:
        bot.send_message(chat_id, "⚠️ System experienced a database write error. Please message us directly.")
        print(f"Error appending booking row data: {e}")

@bot.callback_query_handler(func=lambda call: call.data.startswith(('approve_', 'deny_')))
def handle_admin_action(call):
    action, row_id, customer_chat_id = call.data.split('_')
    row_id = int(row_id)
    
    try:
        if action == "approve":
            bookings_sheet.update_cell(row_id, 10, "Confirmed")
            status_text = "\n\n🟢 **Status: Confirmed & Approved**"
            bot.send_message(customer_chat_id, "🎉 Your booking has been **Confirmed**! See you at the shop.")
        else:
            bookings_sheet.update_cell(row_id, 10, "Rejected")
            status_text = "\n\n🔴 **Status: Rejected / Denied**"
            bot.send_message(customer_chat_id, "❌ Your booking payment could not be verified. Please contact us.")

        if call.message.photo:
            bot.edit_message_caption(chat_id=ADMIN_CHAT_ID, message_id=call.message.message_id, caption=call.message.caption + status_text, parse_mode="Markdown")
        else:
            bot.edit_message_text(chat_id=ADMIN_CHAT_ID, message_id=call.message.message_id, text=call.message.text + status_text, parse_mode="Markdown")
    except Exception as e:
        print(f"Error executing callback status alteration mapping: {e}")



# ==========================================
# ADMIN / MANAGER COMMANDS & INTERFACES
# ==========================================

@bot.message_handler(commands=['admin'])
def admin_menu(message):
    chat_id = str(message.chat.id)
    
    # Verify that the person texting the bot is the actual manager
    if chat_id != str(ADMIN_CHAT_ID):
        bot.send_message(chat_id, "❌ Access Denied. This command is restricted to the shop manager.")
        return

    # Build the Manager control console
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        InlineKeyboardButton("📋 View Pending Bookings", callback_data="mgr_view_pending"),
        InlineKeyboardButton("💰 Today's Revenue Summary", callback_data="mgr_revenue"),
        InlineKeyboardButton("🔄 Refresh DB Connection", callback_data="mgr_refresh")
    )
    
    bot.send_message(chat_id, "⚙️ **VIP Barber Manager Console**\nSelect a management action below:", reply_markup=keyboard, parse_mode="Markdown")

# Handle All Interactive Buttons (Admin & Manager Actions)
@bot.callback_query_handler(func=lambda call: call.data.startswith(('approve_', 'deny_', 'mgr_')))
def handle_callback_actions(call):
    # 1. Handle Booking Approvals
    if call.data.startswith(('approve_', 'deny_')):
        action, row_id, customer_chat_id = call.data.split('_')
        row_id = int(row_id)
        
        try:
            if action == "approve":
                bookings_sheet.update_cell(row_id, 10, "Confirmed") # Column 10 (J) is Status
                status_text = "\n\n🟢 **Status: Confirmed & Approved**"
                bot.send_message(customer_chat_id, "🎉 Your booking has been **Confirmed**! See you at the shop.")
            else:
                bookings_sheet.update_cell(row_id, 10, "Rejected")
                status_text = "\n\n🔴 **Status: Rejected / Denied**"
                bot.send_message(customer_chat_id, "❌ Your booking payment could not be verified. Please contact us.")

            # Formats the visual card clean layout
            if call.message.photo:
                bot.edit_message_caption(chat_id=ADMIN_CHAT_ID, message_id=call.message.message_id, caption=call.message.caption + status_text, parse_mode="Markdown")
            else:
                bot.edit_message_text(chat_id=ADMIN_CHAT_ID, message_id=call.message.message_id, text=call.message.text + status_text, parse_mode="Markdown")
        except Exception as e:
            print(f"Callback process failure mapping data: {e}")

    # 2. Manager Function: View All Pending Orders
    elif call.data == "mgr_view_pending":
        try:
            all_records = bookings_sheet.get_all_records()
            pending_lists = [r for r in all_records if str(r.get('Status')).strip() == "Pending"]
            
            if not pending_lists:
                bot.send_message(ADMIN_CHAT_ID, "✅ **No pending bookings found!** Everything is up to date.")
                return
                
            for p in pending_lists:
                summary = (
                    f"📄 **Pending Row ID:** {p.get('Row ID')}\n"
                    f"👤 **Customer:** {p.get('Customer Name')}\n"
                    f"📞 **Phone:** {p.get('Phone Number')}\n"
                    f"💈 **Service:** {p.get('Service Chosen')}\n"
                    f"💳 **Method:** {p.get('Payment Method')}\n"
                    f"🕒 **Time:** {p.get('Timestamp')}"
                )
                # Add unique control triggers for individual customer rows
                kb = InlineKeyboardMarkup()
                kb.row(
                    InlineKeyboardButton("Approve ✅", callback_data=f"approve_{p.get('Row ID')}_{p.get('Chat ID')}"),
                    InlineKeyboardButton("Reject ❌", callback_data=f"deny_{p.get('Row ID')}_{p.get('Chat ID')}")
                )
                bot.send_message(ADMIN_CHAT_ID, summary, reply_markup=kb, parse_mode="Markdown")
        except Exception as e:
            bot.send_message(ADMIN_CHAT_ID, f"⚠️ Failed to scan spreadsheet: {e}")

    # 3. Manager Function: View Revenue Metrics Summary
    elif call.data == "mgr_revenue":
        try:
            all_records = bookings_sheet.get_all_records()
            confirmed_bookings = [r for r in all_records if str(r.get('Status')).strip() == "Confirmed"]
            
            total_revenue = 0
            for b in confirmed_bookings:
                # Extract number from format string like "Standard Haircut - 300 ETB"
                service_string = str(b.get('Service Chosen', '0'))
                try:
                    price = int(''.join(filter(str.isdigit, service_string)))
                    total_revenue += price
                except:
                    continue
            
            report = (
                f"📊 **Shop Performance Overview**\n\n"
                f"🟢 Total Confirmed Bookings: `{len(confirmed_bookings)}` users\n"
                f"💰 Total Collected Revenue: `{total_revenue} ETB`"
            )
            bot.send_message(ADMIN_CHAT_ID, report, parse_mode="Markdown")
        except Exception as e:
            bot.send_message(ADMIN_CHAT_ID, f"⚠️ Failed to compute metrics data: {e}")

    # 4. Manager Function: Re-connect client pipelines
    elif call.data == "mgr_refresh":
        bot.answer_callback_query(call.id, "🔄 Re-indexing spreadsheet structures...")
        bot.send_message(ADMIN_CHAT_ID, "✅ Connection pipelines healthy.")

print("🚀 System Active... Press Ctrl+C to terminate terminal script listening loop.")
bot.infinity_polling()


print("🚀 System Active... Press Ctrl+C to terminate terminal script listening loop.")
bot.infinity_polling()
