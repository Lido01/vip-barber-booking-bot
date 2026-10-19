
# VIP Barber Booking Bot

## Customer flow

Customers start a booking with `/start` and are guided through one clean flow:

1. Full name.
2. Ethiopian mobile number (`09...`, `07...`, `+2519...`, or `+2517...`), entered as
   digits or shared from Telegram.
3. Numeric block number and numeric room number.
4. A service loaded from the `Services` sheet.
5. A payment method and payment screenshot or transaction number.
6. An optional note.

The customer receives confirmation after the request is saved and a status message
after an admin approves or rejects it.

## Admin flow

The admin sends `/admin` from the chat configured by `ADMIN_CHAT_ID`. The menu
provides buttons for:

- **All bookings**: review every saved booking, including customer name, phone,
  Telegram chat ID, address, status, and timestamp. Results are paginated.
- **Pending bookings**: review only bookings that still need action.
- **Manage services**: view services and add or edit service name, price, and duration.

New orders also arrive directly in the admin chat with **Confirm** and **Reject**
buttons. Confirmed bookings remain in the sheet. Rejected bookings are removed
from the sheet and the customer receives a rejection notification. There is one
callback handler and one polling loop, so old duplicate buttons and shortcuts
are not shown.

Customers can use `/start` or `/menu` to book, view only their own bookings,
and view available services. The admin dashboard is restricted to
`ADMIN_CHAT_ID`; customers cannot access the all-bookings or service-management
views.
The customer menu also includes **Help / Contact Support**, which opens a direct
Telegram chat with the configured administrator. `/help` opens the same support
option.

The configured admin also sees an **Admin Dashboard** button in the normal menu.
It opens the all-bookings and pending-bookings lists, while regular customers
only see their own bookings. The **Quick Menu** button provides shortcuts to
booking, private bookings, services, support, and (for the admin) the dashboard.

## Google Sheets columns

The existing booking columns are preserved. New bookings append:

- `Block Number`
- `Room Number`

Add those two headers to the `Bookings` sheet if they are not already present.
The booking row also expects a `Status` column for Pending, Confirmed, and
Rejected updates. The `Services` sheet must have these headers:

- `Service Name`
- `Price (ETB)`
- `Duration`

## Configuration

Create a local `.env` containing `BOT_TOKEN` and `ADMIN_CHAT_ID`, and keep the
Google service-account file as the local `credentials.json`. Both files are
ignored by Git.