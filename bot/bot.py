#!/usr/bin/env python3
"""
RefSheet Telegram Bot
"""
import os
import io
import re
import sys
import time
import zipfile
import logging
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    TypeHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)

BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
_admin_raw = (os.getenv("ADMIN_ID") or "0").strip()
ADMIN_ID = int(_admin_raw) if _admin_raw.lstrip("-").isdigit() else 0

MAX_PHOTOS = 4
MAX_PHOTO_BYTES = 10 * 1024 * 1024  # Bot API downloads cap at 20 MB; keep memory bounded
CONVERSATION_TIMEOUT = 30 * 60  # seconds; frees abandoned sessions (and their photos)
BOT_RUNNING = threading.Event()

(NAME, HEIGHT, WEIGHT, APPEARANCE, STYLE, VIBE, NOTES, PHOTOS) = range(8)

TAGS = {
    "body": ["athletic", "lean muscular", "muscular", "slim", "stocky", "toned", "v-taper", "broad shoulders"],
    "skin": ["medium tan", "fair skin", "olive skin", "dark skin", "sun-kissed", "pale"],
    "hair": ["short hair", "textured hair", "pink hair", "blond hair", "dark hair", "undercut", "buzzed"],
    "face": ["brown eyes", "blue eyes", "beard", "stubble", "strong jawline", "clean shaven"],
    "style": ["edgy", "casual", "streetwear", "minimal", "chain necklace", "sunglasses", "hoodie"],
    "vibe": ["cool", "mysterious", "playful", "chill", "confident", "flirty", "magnetic"],
}

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        ok = BOT_RUNNING.is_set()
        self.send_response(200 if ok else 503)
        self.end_headers()
        self.wfile.write(b"ok" if ok else b"bot not running")
    def log_message(self, format, *args):
        pass

def start_health_server():
    server = HTTPServer(("0.0.0.0", 8080), HealthHandler)
    logger.info("Health server listening on :8080")
    server.serve_forever()

def tag_keyboard(category, selected):
    buttons = []
    row = []
    for tag in TAGS.get(category, []):
        label = f"✓ {tag}" if tag in selected else tag
        row.append(InlineKeyboardButton(label, callback_data=f"tag:{category}:{tag}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton("Done", callback_data=f"done:{category}")])
    return InlineKeyboardMarkup(buttons)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    context.user_data["photos"] = []
    context.user_data["selected"] = {"appearance": [], "style": [], "vibe": []}
    privacy = (
        "\n\nNote: a copy of your finished package (info + photos) is sent to the bot admin."
        if ADMIN_ID else ""
    )
    await update.message.reply_text(
        "RefSheet\n\nI'll ask a few questions, then you can upload photos."
        f"{privacy}\n\nWhat's the character's name?"
    )
    return NAME

async def get_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["name"] = update.message.text.strip()
    await update.message.reply_text("Height? (e.g. 182 cm)")
    return HEIGHT

async def get_height(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["height"] = update.message.text.strip()
    await update.message.reply_text("Weight? (e.g. 73 kg)")
    return WEIGHT

async def get_weight(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["weight"] = update.message.text.strip()
    await update.message.reply_text(
        "Appearance — tap tags, then Done.",
        reply_markup=tag_keyboard("body", [])
    )
    context.user_data["appearance_stage"] = "body"
    return APPEARANCE

async def appearance_tags(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    data = query.data
    stage = context.user_data.get("appearance_stage", "body")
    selected = context.user_data["selected"]["appearance"]
    if data.startswith("tag:"):
        tag = data.split(":", 2)[2]
        if tag in selected:
            selected.remove(tag)
        else:
            selected.append(tag)
        await query.edit_message_reply_markup(tag_keyboard(stage, selected))
        return APPEARANCE
    if data.startswith("done:"):
        stages = ["body", "skin", "hair", "face"]
        idx = stages.index(stage)
        if idx + 1 < len(stages):
            next_stage = stages[idx + 1]
            context.user_data["appearance_stage"] = next_stage
            await query.edit_message_text(f"Appearance — {next_stage.title()}", reply_markup=tag_keyboard(next_stage, selected))
            return APPEARANCE
        context.user_data["appearance"] = ", ".join(selected)
        await query.edit_message_text(f"Appearance: {context.user_data['appearance'] or '—'}")
        await query.message.reply_text("Personal style — tap tags, then Done.", reply_markup=tag_keyboard("style", []))
        return STYLE
    return APPEARANCE

async def style_tags(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    data = query.data
    selected = context.user_data["selected"]["style"]
    if data.startswith("tag:"):
        tag = data.split(":", 2)[2]
        if tag in selected: selected.remove(tag)
        else: selected.append(tag)
        await query.edit_message_reply_markup(tag_keyboard("style", selected))
        return STYLE
    if data.startswith("done:"):
        context.user_data["style"] = ", ".join(selected)
        await query.edit_message_text(f"Style: {context.user_data['style'] or '—'}")
        await query.message.reply_text("Vibe — tap tags, then Done.", reply_markup=tag_keyboard("vibe", []))
        return VIBE
    return STYLE

async def vibe_tags(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    data = query.data
    selected = context.user_data["selected"]["vibe"]
    if data.startswith("tag:"):
        tag = data.split(":", 2)[2]
        if tag in selected: selected.remove(tag)
        else: selected.append(tag)
        await query.edit_message_reply_markup(tag_keyboard("vibe", selected))
        return VIBE
    if data.startswith("done:"):
        context.user_data["vibe"] = ", ".join(selected)
        await query.edit_message_text(f"Vibe: {context.user_data['vibe'] or '—'}")
        await query.message.reply_text("Any extra notes? (or /skip)")
        return NOTES
    return VIBE

async def get_notes(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        text = (update.message.text or "").strip()
        context.user_data["notes"] = "" if text.lower() in ("/skip", "skip", "no", "none") else text
        logger.info(f"Notes received: {context.user_data['notes']!r}")
        await update.message.reply_text("Send 1–4 photos. /done when finished.")
        return PHOTOS
    except Exception as e:
        logger.exception(f"get_notes failed: {e}")
        await update.message.reply_text("Something went wrong. Send /start to try again.")
        return ConversationHandler.END

async def skip_notes(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["notes"] = ""
    logger.info("Notes skipped")
    await update.message.reply_text("Send 1–4 photos. /done when finished.")
    return PHOTOS

async def get_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if len(context.user_data["photos"]) >= MAX_PHOTOS:
        await update.message.reply_text(f"Max {MAX_PHOTOS}. Send /done.")
        return PHOTOS
    if update.message.photo:
        media, ext = update.message.photo[-1], "jpg"
    else:
        media = update.message.document
        ext = (os.path.splitext(media.file_name or "")[1].lstrip(".").lower() or "jpg")[:5]
    if media.file_size and media.file_size > MAX_PHOTO_BYTES:
        await update.message.reply_text("That file is too large (max 10 MB). Try another photo.")
        return PHOTOS
    file = await media.get_file()
    bio = io.BytesIO()
    await file.download_to_memory(bio)
    context.user_data["photos"].append((bio.getvalue(), ext))
    await update.message.reply_text(f"Photo {len(context.user_data['photos'])} saved. More or /done.")
    return PHOTOS

def build_prompt(data):
    return f"""STRICT CHARACTER REFERENCE SHEET LAYOUT. Black background.

Name: {data.get('name','—')}
Height: {data.get('height','—')}
Weight: {data.get('weight','—')}
Appearance: {data.get('appearance','—')}
Style: {data.get('style','—')}
Vibe: {data.get('vibe','—')}
Notes: {data.get('notes','—')}

LEFT SIDEBAR with name, stats, appearance, style, vibe, palettes.
TOP: three reference photos.
BOTTOM: FRONT | LEFT | RIGHT | BACK turnaround.
RIGHT: details + notes.
Same person in every view."""

async def photos_done(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not context.user_data["photos"]:
        await update.message.reply_text("Send at least one photo.")
        return PHOTOS
    data = context.user_data
    prompt = build_prompt(data)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("prompt.txt", prompt)
        for i, (p, ext) in enumerate(data["photos"], 1):
            zf.writestr(f"photos/{i:02d}.{ext}", p)
    buf.seek(0)
    name = re.sub(r"[^A-Za-z0-9_-]+", "_", data.get("name", ""))[:40].strip("_") or "character"
    await update.message.reply_document(document=buf, filename=f"{name}_refsheet.zip", caption="Your RefSheet package")
    if ADMIN_ID:
        try:
            buf.seek(0)
            await context.bot.send_document(chat_id=ADMIN_ID, document=buf, filename=f"{name}_refsheet.zip", caption=f"From @{update.effective_user.username or update.effective_user.id}")
        except Exception as e:
            logger.warning(f"Admin forward failed: {e}")
    context.user_data.clear()
    await update.message.reply_text("Done. /start for another.")
    return ConversationHandler.END

async def lost_session(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Catches messages outside an active conversation (e.g. after a container restart)."""
    if update.effective_message:
        await update.effective_message.reply_text("Session expired or not started. Send /start to begin.")

async def unexpected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Input that doesn't fit the current step."""
    if update.callback_query:
        await update.callback_query.answer("That button is no longer active.")
    elif update.effective_message:
        await update.effective_message.reply_text("Didn't catch that for this step. /cancel to stop, /start to restart.")

async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error("Unhandled error", exc_info=context.error)

async def timed_out(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.clear()
    if update and update.effective_message:
        await update.effective_message.reply_text("Session timed out. Send /start to begin again.")

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    await update.message.reply_text("Cancelled. /start to begin.")
    return ConversationHandler.END

async def _mark_running(app: Application) -> None:
    BOT_RUNNING.set()
    logger.info("Bot polling started")

def run_bot():
    if not BOT_TOKEN or BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        logger.error("BOT_TOKEN not set. Bot will not start.")
        return
    logger.info("Starting Telegram bot...")
    app = Application.builder().token(BOT_TOKEN).post_init(_mark_running).build()
    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_name)],
            HEIGHT: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_height)],
            WEIGHT: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_weight)],
            APPEARANCE: [CallbackQueryHandler(appearance_tags)],
            STYLE: [CallbackQueryHandler(style_tags)],
            VIBE: [CallbackQueryHandler(vibe_tags)],
            NOTES: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, get_notes),
                CommandHandler("skip", skip_notes),
            ],
            PHOTOS: [
                MessageHandler(filters.PHOTO | filters.Document.IMAGE, get_photo),
                CommandHandler("done", photos_done),
            ],
            ConversationHandler.TIMEOUT: [TypeHandler(Update, timed_out)],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            CommandHandler("start", start),
            MessageHandler(filters.ALL, unexpected),
            CallbackQueryHandler(unexpected),
        ],
        allow_reentry=True,
        conversation_timeout=CONVERSATION_TIMEOUT,
    )
    app.add_handler(conv)
    # Anything not inside a live conversation (e.g. state lost on restart)
    app.add_handler(MessageHandler(filters.ALL, lost_session))
    app.add_handler(CallbackQueryHandler(lost_session))
    app.add_error_handler(on_error)
    app.run_polling()
    BOT_RUNNING.clear()

if __name__ == "__main__":
    logger.info(f"BOT_TOKEN present: {bool(BOT_TOKEN and BOT_TOKEN != 'YOUR_BOT_TOKEN_HERE')}")
    logger.info(f"ADMIN_ID: {ADMIN_ID}")
    # Health server keeps the container alive for Cloudflare
    threading.Thread(target=start_health_server, daemon=True).start()
    try:
        run_bot()
    except Exception as e:
        logger.exception(f"Bot crashed: {e}")
    if BOT_TOKEN and BOT_TOKEN != "YOUR_BOT_TOKEN_HERE":
        # Crash/stop with a valid token: exit so the next keep-alive restarts the container.
        time.sleep(30)  # leave time for logs to flush
        sys.exit(1)
    # No token: restarting won't help. Stay up (health returns 503) so logs stay readable.
    while True:
        time.sleep(60)
