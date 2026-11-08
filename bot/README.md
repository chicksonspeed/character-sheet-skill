# RefSheet Bot

RefSheet bot. Collects info + photos and returns a zip package.

## Setup

1. Create a bot with [@BotFather](https://t.me/BotFather) and copy the token.
2. Get your Telegram user ID (message [@userinfobot](https://t.me/userinfobot)).
3. Install dependencies:
   ```zsh
   pip install -r requirements.txt
   ```
4. Run:
   ```zsh
   export BOT_TOKEN="your-token-here"
   export ADMIN_ID="your-telegram-id"
   python bot.py
   ```

## Flow

- `/start` — begin
- Answer name, height, weight
- Pick tags on one updating card: body, skin, hair, eyes, face, style, wardrobe, vibe
  (paged, ⬅ Back / Next ➜, and **➕ Add your own** for custom tags in any category)
- Add notes, or tap Skip
- Review the profile card — add photos, edit tags, or start over
- Upload 1–4 photos (compressed or as image files, max 10 MB each), then tap ✅ Done
- `/cancel` stops; `/start` restarts at any point. Sessions expire after 30 min of inactivity.

The zip contains `prompt.txt` + `photos/`. If `ADMIN_ID` is set, a copy is also forwarded to the admin.

## Tests

```zsh
pip install -r requirements.txt pytest
python -m pytest -q tests
```
