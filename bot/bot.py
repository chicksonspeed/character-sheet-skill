#!/usr/bin/env python3
"""
Character Sheet Telegram Bot
Collects character info + photos and builds a zip package
that can be used in any image model (or forwarded to an admin).
"""

import os
import io
import zipfile
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)

# ---------- Config ----------
BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))  # Your Telegram user ID

# Conversation states
(
    NAME, HEIGHT, WEIGHT,
    APPEARANCE, STYLE, VIBE, NOTES,
    PHOTOS, CONFIRM
) = range(10)

# Tag sets
TAGS = {
    "body": ["athletic", "lean muscular", "muscular", "slim", "stocky", "toned", "v-taper", "broad shoulders"],
    "skin": ["medium tan", "fair skin", "olive skin", "dark skin", "sun-kissed", "pale"],
    "hair": ["short hair", "textured hair", "pink hair", "blond hair", "dark hair", "undercut", "buzzed"],
    "face": ["brown eyes", "blue eyes", "beard", "stubble", "strong jawline", "clean shaven"],
    "style": ["edgy", "casual", "streetwear", "minimal", "chain necklace", "sunglasses", "hoodie"],
    "vibe": ["cool", "mysterious", "playful", "chill", "confident", "flirty", "magnetic"],
}

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def tag_keyboard(category: str, selected: list) -> InlineKeyboardMarkup:
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
    await update.message.reply_text(
        "RefSheet\n\n"
        "I'll ask a few questions, then you can upload photos.\n"
        "At the end you'll get a zip you can drop into any image model.\n\n"
        "What's the character's name?"
    )
    return NAME


async def get_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["name"] = update.message.text.strip()
    await update.message.reply_text("Height? (e.g. 182 cm or 6'0\")")
    return HEIGHT


async def get_height(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["height"] = update.message.text.strip()
    await update.message.reply_text("Weight? (e.g. 73 kg or 161 lbs)")
    return WEIGHT


async def get_weight(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["weight"] = update.message.text.strip()
    await update.message.reply_text(
        "Appearance — tap tags to add them, then press Done.",
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
        _, cat, tag = data.split(":", 2)
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
            await query.edit_message_text(
                f"Appearance — {next_stage.title()}",
                reply_markup=tag_keyboard(next_stage, selected)
            )
            return APPEARANCE
        else:
            context.user_data["appearance"] = ", ".join(selected)
            await query.edit_message_text(f"Appearance: {context.user_data['appearance'] or '—'}")
            await query.message.reply_text(
                "Personal style — tap tags, then Done.",
                reply_markup=tag_keyboard("style", context.user_data["selected"]["style"])
            )
            return STYLE
    return APPEARANCE


async def style_tags(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    data = query.data
    selected = context.user_data["selected"]["style"]

    if data.startswith("tag:"):
        tag = data.split(":", 2)[2]
        if tag in selected:
            selected.remove(tag)
        else:
            selected.append(tag)
        await query.edit_message_reply_markup(tag_keyboard("style", selected))
        return STYLE

    if data.startswith("done:"):
        context.user_data["style"] = ", ".join(selected)
        await query.edit_message_text(f"Style: {context.user_data['style'] or '—'}")
        await query.message.reply_text(
            "Vibe — tap tags, then Done.",
            reply_markup=tag_keyboard("vibe", context.user_data["selected"]["vibe"])
        )
        return VIBE
    return STYLE


async def vibe_tags(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    data = query.data
    selected = context.user_data["selected"]["vibe"]

    if data.startswith("tag:"):
        tag = data.split(":", 2)[2]
        if tag in selected:
            selected.remove(tag)
        else:
            selected.append(tag)
        await query.edit_message_reply_markup(tag_keyboard("vibe", selected))
        return VIBE

    if data.startswith("done:"):
        context.user_data["vibe"] = ", ".join(selected)
        await query.edit_message_text(f"Vibe: {context.user_data['vibe'] or '—'}")
        await query.message.reply_text("Any extra notes? (or send /skip)")
        return NOTES
    return VIBE


async def get_notes(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    context.user_data["notes"] = "" if text == "/skip" else text
    await update.message.reply_text(
        "Now send 1–4 reference photos (face close-up + body shots work best).\n"
        "Send /done when finished."
    )
    return PHOTOS


async def get_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if len(context.user_data["photos"]) >= 4:
        await update.message.reply_text("Max 4 photos. Send /done to continue.")
        return PHOTOS
    photo = update.message.photo[-1]
    file = await photo.get_file()
    bio = io.BytesIO()
    await file.download_to_memory(bio)
    bio.seek(0)
    context.user_data["photos"].append(bio.getvalue())
    await update.message.reply_text(f"Photo {len(context.user_data['photos'])} saved. Send more or /done.")
    return PHOTOS


async def photos_done(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not context.user_data["photos"]:
        await update.message.reply_text("Please send at least one photo.")
        return PHOTOS
    await send_package(update, context)
    return ConversationHandler.END


def build_prompt(data: dict) -> str:
    return f"""STRICT CHARACTER REFERENCE SHEET LAYOUT. Black background. Do not deviate from this structure.

LEFT SIDEBAR:
- Large bold white text: "{data.get('name', 'CHARACTER')}"
- "CHARACTER SHEET"
- STATS (height, weight)
- APPEARANCE bullets
- PERSONAL STYLE bullets
- VIBE paragraph
- COLOR PALETTE + STYLE PALETTE

TOP: three reference photos labeled 01 02 03
BOTTOM: FRONT | LEFT PROFILE | RIGHT PROFILE | BACK turnaround (shirtless, black pants)
RIGHT: DETAILS close-ups + NOTES

Consistency: exact same person in every view. Lock face, hair, body from references.

Character information:
Name: {data.get('name', '—')}
Height: {data.get('height', '—')}
Weight: {data.get('weight', '—')}
Appearance: {data.get('appearance', '—')}
Style: {data.get('style', '—')}
Vibe: {data.get('vibe', '—')}
Notes: {data.get('notes', '—')}
"""


async def send_package(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = context.user_data
    prompt = build_prompt(data)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("prompt.txt", prompt)
        zf.writestr("INSTRUCTIONS.txt", "Upload the photos and paste prompt.txt into Grok, Flux, Midjourney, etc.")
        for i, photo_bytes in enumerate(data["photos"], 1):
            zf.writestr(f"photos/0{i}.jpg", photo_bytes)
    buf.seek(0)

    name = data.get("name", "character").replace(" ", "_")
    caption = f"Character sheet package for {data.get('name')}\n\nDrop the photos + prompt.txt into any image model."

    await update.message.reply_document(
        document=buf,
        filename=f"{name}_character_sheet.zip",
        caption=caption
    )

    # Forward to admin if configured
    if ADMIN_ID:
        try:
            buf.seek(0)
            await context.bot.send_document(
                chat_id=ADMIN_ID,
                document=buf,
                filename=f"{name}_character_sheet.zip",
                caption=f"New request from @{update.effective_user.username or update.effective_user.id}\n{caption}"
            )
        except Exception as e:
            logger.warning(f"Could not forward to admin: {e}")

    await update.message.reply_text("Done. Send /start to make another.")


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Cancelled. /start to begin again.")
    return ConversationHandler.END


def main():
    if BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        print("Set BOT_TOKEN environment variable")
        return

    app = Application.builder().token(BOT_TOKEN).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_name)],
            HEIGHT: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_height)],
            WEIGHT: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_weight)],
            APPEARANCE: [CallbackQueryHandler(appearance_tags)],
            STYLE: [CallbackQueryHandler(style_tags)],
            VIBE: [CallbackQueryHandler(vibe_tags)],
            NOTES: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_notes)],
            PHOTOS: [
                MessageHandler(filters.PHOTO, get_photo),
                CommandHandler("done", photos_done),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(conv)
    app.add_handler(CommandHandler("start", start))
    print("Bot running…")
    app.run_polling()


if __name__ == "__main__":
    main()
