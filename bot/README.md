# RefSheet Bot

RefSheet bot. Collects info + photos and returns a zip package.

## Setup

1. Create a bot with [@BotFather](https://t.me/BotFather) and copy the token.
2. Get your Telegram user ID (message [@userinfobot](https://t.me/userinfobot)).
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Run:
   ```bash
   export BOT_TOKEN="your-token-here"
   export ADMIN_ID="your-telegram-id"
   python bot.py
   ```

## Flow

- `/start` — begin
- Answer name, height, weight
- Tap appearance / style / vibe tags
- Upload 1–4 photos
- `/done` — receive the zip

The zip contains `prompt.txt` + `photos/`. If `ADMIN_ID` is set, a copy is also forwarded to the admin.
