# VIP Barber Booking Bot

VIP Barber Booking Bot is a Telegram booking assistant for a barber shop. It
uses Telegram for the conversation and Google Sheets as a simple shared
database, so customers can submit appointments while the administrator manages
requests and the public service list from Telegram.

## What the bot does

### Customer features

- Opens a customer menu with `/start`, `/menu`, or `/reset`.
- Collects a full name, phone number, block number, room number, and optional
  appointment note.
- Accepts a phone number typed by the customer or shared with Telegram's
  contact button.
- Saves every new appointment with `Pending` status.
- Shows the customer's own bookings and their current status.
- Shows the services, prices, and durations stored in the `Services` sheet.
- Provides a support button that opens a direct Telegram chat with the admin.
- Provides a Quick Menu with shortcuts for booking, bookings, services, and
  support.

### Admin features

Only the Telegram chat configured by `ADMIN_CHAT_ID` can open the admin
dashboard. The dashboard provides:

- **All bookings**: paginated list of every booking with customer details,
  address, timestamp, chat ID, and status.
- **Pending bookings**: paginated work queue for requests awaiting a decision.
- **Confirm** and **Reject** buttons directly on each pending booking in the
  list.
- **Manage services**: view the public service catalog, add a service, or edit
  its name, price, and duration.
- Immediate notifications for new bookings, with the same Confirm and Reject
  actions.

Booking decisions update the existing row's `Status` value to `Confirmed` or
`Rejected`; rejected bookings are retained instead of being deleted. The
customer receives a Telegram notification after either decision.

## How it works

The application is a single Python polling process:

1. `bot.py` loads `BOT_TOKEN` and `ADMIN_CHAT_ID` from `.env`.
2. It authenticates to Google Sheets with `credentials.json` and opens the
   `VIP Booking Bot` spreadsheet.
3. Telegram message handlers display menus and collect customer input through
   next-step handlers.
4. A completed booking is appended to the `Bookings` worksheet with a
   `Pending` status.
5. The admin receives the booking and can decide from the notification or from
   the Pending bookings dashboard.
6. Callback handlers update the sheet and notify the customer.
7. The process continues polling Telegram until it is stopped.

The bot keeps short-lived conversation state in memory. Google Sheets remains
the source of truth for bookings and services, so restarting the process does
not lose saved records.

## Booking statuses

| Status | Meaning |
| --- | --- |
| `Pending` | A customer submitted a booking and the admin has not decided. |
| `Confirmed` | The admin accepted the booking. |
| `Rejected` | The admin declined the booking; the row remains available for history. |

## Admin decision workflow

When the admin opens **Pending bookings**, each pending row includes its own
Confirm and Reject buttons. The same buttons are attached to the new-booking
alert sent to the admin. Selecting either action:

1. Verifies that the callback came from the configured admin chat.
2. Updates the row's `Status` cell in Google Sheets.
3. Removes the buttons from the alert that was used.
4. Sends the new status to the customer's Telegram chat.

The list is paginated, and the row number is included in each callback so the
admin can process a request without opening the spreadsheet.

## Google Sheets setup

Create a spreadsheet named **VIP Booking Bot** with these worksheets:

### `Bookings`

The first row must contain the headers used by the bot:

- `Chat ID`
- `Customer Name`
- `Phone`
- `Address`
- `Telegram` or `Username`
- `Timestamp`
- `Status`

The booking writer stores the block and room together in the address value and
stores the optional note in the booking row. Keep the existing booking columns
in the same order used by the current sheet, and make sure a `Status` column
exists for admin decisions. Existing sheets with additional columns are
supported because records are read by header name.

### `Services`

The first row must contain:

- `Service Name`
- `Price (ETB)`
- `Duration`

Customers see these rows in the public services menu. The admin can create or
edit rows from **Manage services**.

## Configuration and installation

1. Install Python 3.10 or newer.
2. Install the dependencies:

   ```powershell
   pip install pyTelegramBotAPI gspread python-dotenv google-auth
   ```

3. Create a `.env` file beside `bot.py`:

   ```dotenv
   BOT_TOKEN=your-telegram-bot-token
   ADMIN_CHAT_ID=your-telegram-chat-id
   ```

4. Create a Google Cloud service account, enable Google Sheets API access, and
   download its JSON key as `credentials.json` beside `bot.py`.
5. Share the **VIP Booking Bot** spreadsheet with the service-account email
   with Editor access.

`.env` and `credentials.json` are ignored by git and must never be committed.

## Running the bot

From the `vip-barber-booking` directory:

```powershell
python bot.py
```

On startup the bot registers its Telegram commands, connects to Google Sheets,
and starts polling. Keep the process running for the bot to respond. Stop it
with `Ctrl+C`.

## Error handling and access control

- Missing environment variables stop startup with an explicit error.
- A failed Google Sheets connection stops startup instead of running with
  incomplete data.
- Google Sheets read/write errors are logged to the process output and shown
  to the affected user as a useful temporary-error message.
- Admin callback actions verify the callback chat against `ADMIN_CHAT_ID`.
- Customer booking views filter by the caller's Telegram chat ID.
- Customer-provided text is HTML-escaped before it is placed in Telegram HTML
  messages.

## Project layout

```text
vip-barber-booking/
├── bot.py             # Telegram handlers, booking flow, and Sheets access
├── README.md          # Setup and behavior documentation
├── credentials.json   # Local Google service-account key (ignored)
└── .env               # Local Telegram configuration (ignored)
```
