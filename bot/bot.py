#!/usr/bin/env python3
"""
RefSheet Telegram Bot

Flow: name → height → weight → tag picker (8 categories, custom tags allowed)
      → notes → review card → photos → zip package (prompt.txt + photos/).
"""
import html
import io
import logging
import math
import os
import re
import sys
import threading
import time
import zipfile
from http.server import BaseHTTPRequestHandler, HTTPServer

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.error import BadRequest
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    TypeHandler,
    filters,
)

BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
_admin_raw = (os.getenv("ADMIN_ID") or "0").strip()
ADMIN_ID = int(_admin_raw) if _admin_raw.lstrip("-").isdigit() else 0

MAX_PHOTOS = 4
MAX_PHOTO_BYTES = 10 * 1024 * 1024  # Bot API downloads cap at 20 MB; keep memory bounded
CONVERSATION_TIMEOUT = 30 * 60  # seconds; frees abandoned sessions (and their photos)
BOT_RUNNING = threading.Event()

(NAME, HEIGHT, WEIGHT, TAGS, CUSTOM, NOTES, REVIEW, PHOTOS) = range(8)

# ---------------------------------------------------------------------------
# Tags (kept in sync with TAGS in ../index.html, plus extras)
# ---------------------------------------------------------------------------
# (key, title, section) — section decides which prompt field the tags land in.
STAGES = [
    ("body", "Body type", "appearance"),
    ("skin", "Skin", "appearance"),
    ("hair", "Hair", "appearance"),
    ("eyes", "Eyes", "appearance"),
    ("face", "Face & facial hair", "appearance"),
    ("style", "Style", "style"),
    ("wardrobe", "Wardrobe & accessories", "style"),
    ("vibe", "Vibe", "vibe"),
]
SECTIONS = [("appearance", "🧍", "Appearance"), ("style", "👕", "Style"), ("vibe", "✨", "Vibe")]
STAGE_ICON = {"body": "💪", "skin": "🎨", "hair": "💇", "eyes": "👁", "face": "🧔",
              "style": "🕶", "wardrobe": "🧥", "vibe": "✨"}

TAG_OPTIONS = {
    "body": ["athletic", "lean muscular", "muscular", "slim", "stocky", "toned", "broad shoulders",
             "narrow waist", "defined abs", "thick thighs", "long legs", "compact", "tall frame",
             "short frame", "v-taper", "soft", "cut", "bulk", "swimmer build", "runner build"],
    "skin": ["medium tan", "fair skin", "olive skin", "dark skin", "light skin", "sun-kissed", "pale",
             "freckles", "warm undertone", "cool undertone", "neutral undertone", "golden", "porcelain",
             "deep", "medium", "light medium", "tattoos", "birthmark", "scar"],
    "hair": ["short hair", "textured hair", "messy hair", "styled hair", "undercut", "buzzed",
             "long hair", "curly hair", "wavy hair", "straight hair", "slicked back", "pink hair",
             "blond hair", "dark hair", "brown hair", "black hair", "dyed hair", "bleached hair",
             "silver hair", "red hair", "blue hair", "platinum", "ash blond", "crew cut", "fade",
             "man bun", "middle part", "side part", "mullet", "braids", "dreadlocks", "ponytail",
             "bald"],
    "eyes": ["brown eyes", "blue eyes", "green eyes", "hazel eyes", "dark eyes", "light eyes",
             "grey eyes", "amber eyes", "hooded eyes", "almond eyes", "glasses", "eyeliner"],
    "face": ["beard", "full beard", "stubble", "clean shaven", "mustache", "goatee", "trimmed beard",
             "strong jawline", "soft features", "sharp features", "high cheekbones", "full lips",
             "defined brows", "thick brows", "intense gaze", "friendly face", "smirk",
             "serious expression", "boyish face", "mature face", "dimples", "nose piercing",
             "lip piercing", "eyebrow slit"],
    "style": ["edgy", "confident", "stylish", "casual", "refined", "laid-back", "streetwear",
              "minimal", "summer casual", "clean lines", "layered", "monochrome", "bold colors",
              "neutral tones", "oversized", "fitted", "athleisure", "smart casual", "nightlife",
              "daytime casual", "workwear", "preppy", "grunge", "techwear", "y2k", "old money",
              "gorpcore", "punk", "skater"],
    "wardrobe": ["chain necklace", "sunglasses", "hoodie", "leather jacket", "denim", "tank top",
                 "button-up", "t-shirt", "jewelry", "rings", "earring", "bracelet", "cap", "beanie",
                 "boots", "sneakers", "loafers", "silver jewelry", "gold jewelry", "cross necklace",
                 "choker", "watch", "bag", "backpack", "bomber jacket", "cargo pants", "suit",
                 "turtleneck", "tracksuit", "bucket hat"],
    "vibe": ["cool", "versatile", "approachable", "mysterious", "playful", "intense", "chill",
             "confident", "flirty", "aloof", "warm", "magnetic", "charismatic", "calm", "energetic",
             "laid-back", "bold", "subtle", "teasing", "serious", "friendly", "distant", "inviting",
             "guarded", "night owl", "party energy", "low-key", "high-energy", "smooth",
             "rough around the edges", "sweet", "dominant", "submissive energy", "bratty", "soft",
             "stoic", "expressive", "shy", "outgoing", "dry humor", "chaotic", "grounded", "dreamy"],
}

PAGE_SIZE = 12          # 2 columns x 6 rows
MAX_CUSTOM_PER_STAGE = 10
MAX_CUSTOM_LEN = 40
TOTAL_STEPS = 3 + len(STAGES) + 2  # name, height, weight, tag stages, notes, photos

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Health server (Cloudflare keep-alive)
# ---------------------------------------------------------------------------
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


# ---------------------------------------------------------------------------
# Rendering helpers
# ---------------------------------------------------------------------------
def esc(v) -> str:
    return html.escape(str(v or ""), quote=False)


def progress(step: int) -> str:
    filled = round(step / TOTAL_STEPS * 10)
    return f"<code>{'▰' * filled}{'▱' * (10 - filled)}</code>  {step}/{TOTAL_STEPS}"


def header(ud, step: int, title: str) -> str:
    name = ud.get("name")
    top = f"🎨 <b>{esc(name)}</b>" if name else "🎨 <b>New character</b>"
    return f"{top}\n{progress(step)}\n\n<b>{title}</b>"


def section_tags(ud, section: str) -> list:
    out = []
    for key, _, sec in STAGES:
        if sec == section:
            out += ud["sel"][key]
    return out


def profile_card(ud) -> str:
    lines = [f"🎨 <b>{esc(ud.get('name'))}</b>",
             f"📏 {esc(ud.get('height')) or '—'}  ·  ⚖️ {esc(ud.get('weight')) or '—'}",
             "━━━━━━━━━━━━━━"]
    for section, icon, title in SECTIONS:
        tags = section_tags(ud, section)
        lines.append(f"{icon} <b>{title}</b>\n{esc(', '.join(tags)) or '<i>—</i>'}")
    notes = ud.get("notes")
    lines.append(f"📝 <b>Notes</b>\n{esc(notes) if notes else '<i>—</i>'}")
    return "\n".join(lines)


def tag_card_text(ud) -> str:
    i = ud["stage"]
    key, title, _ = STAGES[i]
    sel = ud["sel"][key]
    picked = esc(", ".join(sel)) if sel else "<i>nothing yet</i>"
    return (f"{header(ud, 4 + i, f'{STAGE_ICON[key]} {title}')}\n"
            f"Tap everything that fits — pick as many as you like.\n\n"
            f"<b>Selected:</b> {picked}")


def tag_card_keyboard(ud) -> InlineKeyboardMarkup:
    i = ud["stage"]
    key = STAGES[i][0]
    opts, sel = ud["opts"][key], ud["sel"][key]
    pages = max(1, math.ceil(len(opts) / PAGE_SIZE))
    page = ud["page"] % pages
    rows, row = [], []
    for idx in range(page * PAGE_SIZE, min(len(opts), (page + 1) * PAGE_SIZE)):
        tag = opts[idx]
        row.append(InlineKeyboardButton(("✅ " if tag in sel else "") + tag, callback_data=f"t:{i}:{idx}"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    if pages > 1:
        rows.append([
            InlineKeyboardButton("◀", callback_data=f"p:{i}:-1"),
            InlineKeyboardButton(f"page {page + 1}/{pages}", callback_data="noop"),
            InlineKeyboardButton("▶", callback_data=f"p:{i}:1"),
        ])
    rows.append([InlineKeyboardButton("➕ Add your own", callback_data=f"c:{i}")])
    nav = []
    if i > 0:
        nav.append(InlineKeyboardButton("⬅ Back", callback_data=f"b:{i}"))
    last = i == len(STAGES) - 1
    nav.append(InlineKeyboardButton("Finish tags ✓" if last else "Next ➜", callback_data=f"n:{i}"))
    rows.append(nav)
    return InlineKeyboardMarkup(rows)


REVIEW_KB = InlineKeyboardMarkup([
    [InlineKeyboardButton("📸 Looks good — add photos", callback_data="r:ok")],
    [InlineKeyboardButton("✏️ Edit tags", callback_data="r:edit"),
     InlineKeyboardButton("🔁 Start over", callback_data="r:restart")],
])
NOTES_KB = InlineKeyboardMarkup([[InlineKeyboardButton("Skip ➜", callback_data="notes:skip")]])
DONE_KB = InlineKeyboardMarkup([[InlineKeyboardButton("✅ Done — build my package", callback_data="ph:done")]])


async def safe_edit(query, text, reply_markup=None):
    try:
        await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=reply_markup,
                                      disable_web_page_preview=True)
    except BadRequest as e:
        if "not modified" not in str(e).lower():
            raise


async def try_delete(context, chat_id, message_id):
    if not message_id:
        return
    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
    except Exception:
        pass


def clip(text: str, n: int) -> str:
    return (text or "").strip()[:n]


# ---------------------------------------------------------------------------
# Conversation
# ---------------------------------------------------------------------------
def _fresh(ud):
    ud.clear()
    ud["photos"] = []
    ud["sel"] = {key: [] for key, _, _ in STAGES}
    ud["opts"] = {key: list(TAG_OPTIONS[key]) for key, _, _ in STAGES}
    ud["stage"] = 0
    ud["page"] = 0


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    _fresh(context.user_data)
    privacy = (
        "\n\nNote: a copy of your finished package (info + photos) is sent to the bot admin."
        if ADMIN_ID else ""
    )
    await update.effective_message.reply_text(
        "🎨 <b>RefSheet</b>\n"
        "Build a character reference sheet in about two minutes.\n\n"
        "① Basics  →  ② Tags  →  ③ Notes  →  ④ Photos"
        f"{privacy}\n\n"
        f"{progress(1)}\n<b>What's the character's name?</b>",
        parse_mode=ParseMode.HTML,
    )
    return NAME


async def get_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["name"] = clip(update.message.text, 60)
    await update.message.reply_text(
        f"{header(context.user_data, 2, '📏 Height')}\ne.g. <code>182 cm</code> or <code>6\'0\"</code>",
        parse_mode=ParseMode.HTML,
    )
    return HEIGHT


async def get_height(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["height"] = clip(update.message.text, 30)
    await update.message.reply_text(
        f"{header(context.user_data, 3, '⚖️ Weight')}\ne.g. <code>73 kg</code> or <code>160 lbs</code>",
        parse_mode=ParseMode.HTML,
    )
    return WEIGHT


async def get_weight(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    ud = context.user_data
    ud["weight"] = clip(update.message.text, 30)
    ud["stage"], ud["page"] = 0, 0
    await update.message.reply_text(tag_card_text(ud), parse_mode=ParseMode.HTML,
                                    reply_markup=tag_card_keyboard(ud))
    return TAGS


async def tags_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    ud = context.user_data
    kind, *rest = q.data.split(":")
    if kind == "noop":
        await q.answer()
        return TAGS
    i = int(rest[0])
    if i != ud.get("stage"):
        await q.answer("That menu is out of date — use the latest one.")
        return TAGS
    key, title, _ = STAGES[i]

    if kind == "t":
        idx = int(rest[1])
        if idx >= len(ud["opts"][key]):
            await q.answer()
            return TAGS
        tag = ud["opts"][key][idx]
        sel = ud["sel"][key]
        if tag in sel:
            sel.remove(tag)
            await q.answer(f"Removed {tag}")
        else:
            sel.append(tag)
            await q.answer(f"Added {tag}")
    elif kind == "p":
        await q.answer()
        pages = max(1, math.ceil(len(ud["opts"][key]) / PAGE_SIZE))
        ud["page"] = (ud["page"] + int(rest[1])) % pages
    elif kind == "b":
        await q.answer()
        ud["stage"], ud["page"] = i - 1, 0
    elif kind == "c":
        if len(ud["opts"][key]) - len(TAG_OPTIONS[key]) >= MAX_CUSTOM_PER_STAGE:
            await q.answer(f"Max {MAX_CUSTOM_PER_STAGE} custom tags here.", show_alert=True)
            return TAGS
        await q.answer()
        ud["card_id"] = q.message.message_id
        await safe_edit(
            q,
            f"{header(ud, 4 + i, f'✏️ Your own {title.lower()} tags')}\n"
            "Type one or more, separated by commas.\n"
            "<i>e.g. septum piercing, scar over left eyebrow</i>",
            InlineKeyboardMarkup([[InlineKeyboardButton("✖ Cancel", callback_data=f"x:{i}")]]),
        )
        return CUSTOM
    elif kind == "n":
        await q.answer()
        if i == len(STAGES) - 1:
            return await finish_tags(update, context)
        ud["stage"], ud["page"] = i + 1, 0

    await safe_edit(q, tag_card_text(ud), tag_card_keyboard(ud))
    return TAGS


async def custom_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    ud = context.user_data
    key = STAGES[ud["stage"]][0]
    opts, sel = ud["opts"][key], ud["sel"][key]
    added = []
    for raw in re.split(r"[,\n]", update.message.text or ""):
        tag = re.sub(r"\s+", " ", raw).strip()[:MAX_CUSTOM_LEN]
        if not tag:
            continue
        existing = next((o for o in opts if o.lower() == tag.lower()), None)
        if existing:
            if existing not in sel:
                sel.append(existing)
                added.append(existing)
            continue
        if len(opts) - len(TAG_OPTIONS[key]) >= MAX_CUSTOM_PER_STAGE:
            break
        opts.insert(len(opts) - len(TAG_OPTIONS[key]), tag)  # customs first, after earlier customs
        sel.append(tag)
        added.append(tag)
    ud["page"] = 0
    chat_id = update.effective_chat.id
    # Keep the chat tidy: drop the typed message and the old card, post a fresh card at the bottom.
    await try_delete(context, chat_id, update.message.message_id)
    await try_delete(context, chat_id, ud.pop("card_id", None))
    msg = await update.message.reply_text(tag_card_text(ud), parse_mode=ParseMode.HTML,
                                          reply_markup=tag_card_keyboard(ud))
    if msg is not None:
        ud["card_id"] = getattr(msg, "message_id", None)
    return TAGS


async def cancel_custom(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    await safe_edit(q, tag_card_text(context.user_data), tag_card_keyboard(context.user_data))
    return TAGS


async def finish_tags(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    ud = context.user_data
    for section, _, _ in SECTIONS:
        ud[section] = ", ".join(section_tags(ud, section))
    q = update.callback_query
    summary = "\n".join(f"{icon} <b>{t}:</b> {esc(ud[s]) or '—'}" for s, icon, t in SECTIONS)
    await safe_edit(q, f"✅ <b>Tags saved</b>\n\n{summary}")
    if ud.get("reviewed"):
        await q.message.reply_text(profile_card(ud), parse_mode=ParseMode.HTML, reply_markup=REVIEW_KB)
        return REVIEW
    await q.message.reply_text(
        f"{header(ud, 4 + len(STAGES), '📝 Extra notes')}\n"
        "Anything the tags missed? Tattoos, scars, poses, props, colors…\n"
        "Type it, or tap Skip.",
        parse_mode=ParseMode.HTML, reply_markup=NOTES_KB,
    )
    return NOTES


async def show_review(message, ud) -> int:
    ud["reviewed"] = True
    await message.reply_text(
        f"{profile_card(ud)}\n\n<b>Look right?</b>",
        parse_mode=ParseMode.HTML, reply_markup=REVIEW_KB,
    )
    return REVIEW


async def get_notes(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = clip(update.message.text, 1000)
    context.user_data["notes"] = "" if text.lower() in ("skip", "no", "none", "-") else text
    logger.info("Notes received")
    return await show_review(update.message, context.user_data)


async def skip_notes(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["notes"] = ""
    if update.callback_query:
        q = update.callback_query
        await q.answer()
        await safe_edit(q, "📝 <b>Notes:</b> <i>skipped</i>")
        return await show_review(q.message, context.user_data)
    return await show_review(update.message, context.user_data)


async def review_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    ud = context.user_data
    action = q.data.split(":")[1]
    if action == "edit":
        ud["stage"], ud["page"] = 0, 0
        await safe_edit(q, tag_card_text(ud), tag_card_keyboard(ud))
        return TAGS
    if action == "restart":
        await safe_edit(q, "🔁 <i>Starting over…</i>")
        return await start(update, context)
    # ok
    await safe_edit(q, profile_card(ud))
    await q.message.reply_text(
        f"{header(ud, TOTAL_STEPS, '📸 Photos')}\n"
        f"Send 1–{MAX_PHOTOS} photos:\n"
        "• a clear face close-up (front, good light)\n"
        "• a full-body or torso shot\n"
        "• optional: outfit or lifestyle shots\n\n"
        "Send them as photos or files.",
        parse_mode=ParseMode.HTML,
    )
    return PHOTOS


async def get_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    ud = context.user_data
    if len(ud["photos"]) >= MAX_PHOTOS:
        await update.message.reply_text(f"That's the max of {MAX_PHOTOS}.", reply_markup=DONE_KB)
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
    ud["photos"].append((bio.getvalue(), ext))
    n = len(ud["photos"])
    dots = "●" * n + "○" * (MAX_PHOTOS - n)
    more = " Send more, or tap Done." if n < MAX_PHOTOS else ""
    await try_delete(context, update.effective_chat.id, ud.pop("done_msg_id", None))
    msg = await update.message.reply_text(f"📸 {dots}  Photo {n}/{MAX_PHOTOS} saved.{more}",
                                          reply_markup=DONE_KB)
    if msg is not None:
        ud["done_msg_id"] = getattr(msg, "message_id", None)
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


def handoff_prompt(zip_name):
    """Prompt to paste alongside the uploaded zip — has given the best sheets in ChatGPT."""
    return (f"generate the professional character reference sheet from the uploaded package "
            f"({zip_name}), using the character info in prompt.txt and the reference photos.")


async def photos_done(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    ud = context.user_data
    msg = update.effective_message
    if update.callback_query:
        await update.callback_query.answer()
    if not ud["photos"]:
        await msg.reply_text("Send at least one photo first.")
        return PHOTOS
    if update.callback_query:
        try:
            await update.callback_query.edit_message_reply_markup(None)
        except BadRequest:
            pass
    prompt = build_prompt(ud)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("prompt.txt", prompt)
        for i, (p, ext) in enumerate(ud["photos"], 1):
            zf.writestr(f"photos/{i:02d}.{ext}", p)
    buf.seek(0)
    name = re.sub(r"[^A-Za-z0-9_-]+", "_", ud.get("name", ""))[:40].strip("_") or "character"
    card = profile_card(ud)
    caption = card if len(card) <= 1000 else f"📦 <b>{esc(ud.get('name'))}</b> — RefSheet package"
    await msg.reply_document(document=buf, filename=f"{name}_refsheet.zip",
                             caption=caption, parse_mode=ParseMode.HTML)
    if ADMIN_ID:
        try:
            buf.seek(0)
            user = update.effective_user
            await context.bot.send_document(
                chat_id=ADMIN_ID, document=buf, filename=f"{name}_refsheet.zip",
                caption=f"From @{user.username or user.id}")
        except Exception as e:
            logger.warning(f"Admin forward failed: {e}")
    ud.clear()
    await msg.reply_text(
        "🎉 <b>Your package is ready!</b>\n\n"
        "<b>Next:</b> upload the zip as-is to <b>ChatGPT</b> (recommended) or your AI of choice, "
        "then paste this prompt (tap it to copy):\n\n"
        f"<code>{esc(handoff_prompt(f'{name}_refsheet.zip'))}</code>\n\n"
        "/start to build another.",
        parse_mode=ParseMode.HTML,
    )
    return ConversationHandler.END


# ---------------------------------------------------------------------------
# Fallbacks / errors
# ---------------------------------------------------------------------------
async def lost_session(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Catches input outside an active conversation (e.g. after a container restart)."""
    if update.callback_query:
        await update.callback_query.answer("This session has expired. Send /start to begin.", show_alert=True)
    elif update.effective_message:
        await update.effective_message.reply_text("Session expired or not started. Send /start to begin.")


async def unexpected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Input that doesn't fit the current step."""
    if update.callback_query:
        await update.callback_query.answer("That button is no longer active.")
    elif update.effective_message:
        await update.effective_message.reply_text(
            "Didn't catch that for this step — use the buttons above. /cancel to stop, /start to restart.")


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error("Unhandled error", exc_info=context.error)


async def timed_out(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.clear()
    if update and update.effective_message:
        await update.effective_message.reply_text("⏰ Session timed out. Send /start to begin again.")


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
    text = filters.TEXT & ~filters.COMMAND
    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            NAME: [MessageHandler(text, get_name)],
            HEIGHT: [MessageHandler(text, get_height)],
            WEIGHT: [MessageHandler(text, get_weight)],
            TAGS: [CallbackQueryHandler(tags_cb, pattern=r"^(t|p|b|c|n|noop)(:|$)")],
            CUSTOM: [
                MessageHandler(text, custom_text),
                CallbackQueryHandler(cancel_custom, pattern=r"^x:"),
            ],
            NOTES: [
                MessageHandler(text, get_notes),
                CommandHandler("skip", skip_notes),
                CallbackQueryHandler(skip_notes, pattern=r"^notes:skip$"),
            ],
            REVIEW: [CallbackQueryHandler(review_cb, pattern=r"^r:")],
            PHOTOS: [
                MessageHandler(filters.PHOTO | filters.Document.IMAGE, get_photo),
                CommandHandler("done", photos_done),
                CallbackQueryHandler(photos_done, pattern=r"^ph:done$"),
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
