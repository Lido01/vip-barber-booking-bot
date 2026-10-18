
# VIP Barber Booking Bot

## Customer flow

Customers start a booking with `/start` and are guided through one clean flow:

1. Full name.
2. Ethiopian mobile number (`09...`, `07...`, `+2519...`, or `+2517...`), entered as
   digits or shared from Telegram.
3. Numeric block number and room number.
4. A service loaded from the `Services` sheet.
5. A payment method and payment screenshot or transaction number.
6. An optional note.

The customer receives confirmation after the request is saved and a status message
after an admin approves or rejects it.

## Admin flow

The admin sends `/admin` from the chat configured by `ADMIN_CHAT_ID`. The menu
provides buttons for:

- **All orders**: review every saved booking.
- **Latest orders**: review the five newest bookings.
- **Orders in progress**: review pending, confirmed, booked, and in-progress bookings.
- **Manage services**: view the current service names and prices from the `Services` sheet.

New orders also arrive directly in the admin chat with **Confirm** and **Reject**
buttons. There is one callback handler and one polling loop, so old duplicate
buttons and shortcuts are not shown.

## Google Sheets columns

The existing booking columns are preserved. New bookings append:

- `Block Number`
- `Room Number`

Add those two headers to the `Bookings` sheet if they are not already present.

## Configuration

Create a local `.env` containing `BOT_TOKEN` and `ADMIN_CHAT_ID`, and keep the
Google service-account file as the local `credentials.json`. Both files are
ignored by Git.