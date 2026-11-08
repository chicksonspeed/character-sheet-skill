"""Offline conversation tests: no network, Telegram API calls are stubbed.
Run from bot/:  python -m pytest -q tests
"""
import asyncio
import datetime
import io
import os
import sys
import types
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["BOT_TOKEN"] = "123:TEST"

import pytest
from telegram import (Bot, CallbackQuery, Chat, Document, Message, MessageEntity,
                      PhotoSize, Update, User)
from telegram.ext import Application

import bot

N_STAGES = len(bot.STAGES)


class _File:
    async def download_to_memory(self, b):
        b.write(b"img")


@pytest.fixture
def harness(monkeypatch):
    out, edits, docs, alerts, deleted = [], [], [], [], []

    async def reply_text(self, text=None, *a, reply_markup=None, **k):
        out.append(text)
        return types.SimpleNamespace(message_id=1000 + len(out), reply_markup=reply_markup)

    async def reply_document(self, *a, document=None, filename=None, caption=None, **k):
        docs.append((filename, document.getvalue(), caption))

    async def edit_text(self, text, *a, reply_markup=None, **k):
        edits.append((text, reply_markup))

    async def answer(self, text=None, *a, **k):
        if text:
            alerts.append(text)

    async def noop(self, *a, **k):
        return None

    async def delete_message(self, chat_id=None, message_id=None, **k):
        deleted.append(message_id)

    async def get_file(self, *a, **k):
        return _File()

    async def bot_init(self):
        self._initialized = True
        self._bot_user = User(99, "bot", True, username="bot")

    monkeypatch.setattr(Message, "reply_text", reply_text)
    monkeypatch.setattr(Message, "reply_document", reply_document)
    monkeypatch.setattr(CallbackQuery, "answer", answer)
    monkeypatch.setattr(CallbackQuery, "edit_message_text", edit_text)
    monkeypatch.setattr(CallbackQuery, "edit_message_reply_markup", noop)
    monkeypatch.setattr(Bot, "delete_message", delete_message)
    monkeypatch.setattr(PhotoSize, "get_file", get_file)
    monkeypatch.setattr(Document, "get_file", get_file)
    monkeypatch.setattr(Bot, "initialize", bot_init)
    captured = {}
    monkeypatch.setattr(Application, "run_polling", lambda self, **k: captured.setdefault("app", self))
    monkeypatch.setattr(bot, "BOT_TOKEN", "123:TEST")
    monkeypatch.setattr(bot, "ADMIN_ID", 0)
    bot.run_bot()
    app = captured["app"]
    user, chat, n = User(1, "h", False, username="h"), Chat(1, "private"), [0]

    def msg(text=None, photo=None, document=None):
        n[0] += 1
        ents = [MessageEntity("bot_command", 0, len(text.split()[0]))] if text and text.startswith("/") else None
        m = Message(n[0], datetime.datetime.now(), chat, from_user=user, text=text,
                    entities=ents, photo=photo, document=document)
        return Update(n[0], message=m)

    def cb(data):
        n[0] += 1
        m = Message(999, datetime.datetime.now(), chat, from_user=user)
        return Update(n[0], callback_query=CallbackQuery(str(n[0]), user, "x", data=data, message=m))

    async def run(updates):
        await app.initialize()
        for up in updates:
            up.set_bot(app.bot)
            for obj in (up.message, up.callback_query, up.callback_query and up.callback_query.message):
                if obj:
                    obj.set_bot(app.bot)
            await app.process_update(up)

    h = types.SimpleNamespace(out=out, edits=edits, docs=docs, alerts=alerts, deleted=deleted,
                              msg=msg, cb=cb, run=lambda u: asyncio.run(run(u)), app=app)
    h.ud = lambda: app.user_data[1]
    return h


def basics(h, name="Kai"):
    return [h.msg("/start"), h.msg(name), h.msg("182 cm"), h.msg("73 kg")]


def all_next(h, start=0):
    return [h.cb(f"n:{i}") for i in range(start, N_STAGES)]


def photo(h):
    return h.msg(photo=[PhotoSize("f", "u", 10, 10)])


def zip_names(h):
    return zipfile.ZipFile(io.BytesIO(h.docs[0][1])).namelist()


def prompt_txt(h):
    return zipfile.ZipFile(io.BytesIO(h.docs[0][1])).read("prompt.txt").decode()


def test_full_flow_with_buttons(harness):
    h = harness
    h.run(basics(h) + [h.cb("t:0:0")] + all_next(h) + [h.cb("notes:skip"), h.cb("r:ok"),
          photo(h), h.cb("ph:done")])
    assert len(h.docs) == 1
    fname, _, caption = h.docs[0]
    assert fname == "Kai_refsheet.zip"
    assert zip_names(h) == ["prompt.txt", "photos/01.jpg"]
    assert "Appearance: athletic" in prompt_txt(h)
    assert "<b>Kai</b>" in caption
    assert "package is ready" in h.out[-1]


def test_legacy_commands_still_work(harness):
    h = harness
    h.run(basics(h) + all_next(h) + [h.msg("/skip"), h.cb("r:ok"), photo(h), h.msg("/done")])
    assert len(h.docs) == 1


def test_tags_map_to_sections(harness):
    h = harness
    keys = [k for k, _, _ in bot.STAGES]
    picks = [h.cb(f"t:{keys.index('hair')}:0"), h.cb(f"t:{keys.index('wardrobe')}:0"),
             h.cb(f"t:{keys.index('vibe')}:0")]
    seq = basics(h)
    for i in range(N_STAGES):
        seq += [p for p in picks if p.callback_query.data.startswith(f"t:{i}:")]
        seq.append(h.cb(f"n:{i}"))
    h.run(seq + [h.msg("has a tattoo"), h.cb("r:ok"), photo(h), h.cb("ph:done")])
    p = prompt_txt(h)
    assert f"Appearance: {bot.TAG_OPTIONS['hair'][0]}" in p
    assert f"Style: {bot.TAG_OPTIONS['wardrobe'][0]}" in p
    assert f"Vibe: {bot.TAG_OPTIONS['vibe'][0]}" in p
    assert "Notes: has a tattoo" in p


def test_custom_tags(harness):
    h = harness
    h.run(basics(h) + [h.cb("c:0"), h.msg("Septum piercing, athletic,  scar over left eyebrow ,")])
    ud = h.ud()
    assert ud["sel"]["body"] == ["Septum piercing", "athletic", "scar over left eyebrow"]
    assert ud["opts"]["body"][:2] == ["Septum piercing", "scar over left eyebrow"]  # customs first, no dup
    assert h.deleted, "typed message / old card should be cleaned up"
    assert "Septum piercing" in h.out[-1]  # fresh card shows the selection
    # custom tags are real buttons: toggling index 0 removes it
    h.run([h.cb("t:0:0")])
    assert "Septum piercing" not in h.ud()["sel"]["body"]


def test_custom_cancel_returns_to_card(harness):
    h = harness
    h.run(basics(h) + [h.cb("c:0"), h.cb("x:0"), h.cb("t:0:0")])
    assert h.ud()["sel"]["body"] == [bot.TAG_OPTIONS["body"][0]]


def test_custom_limit(harness):
    h = harness
    many = ", ".join(f"custom{i}" for i in range(15))
    h.run(basics(h) + [h.cb("c:0"), h.msg(many), h.cb("c:0")])
    assert len(h.ud()["opts"]["body"]) - len(bot.TAG_OPTIONS["body"]) == bot.MAX_CUSTOM_PER_STAGE
    assert any("Max" in a for a in h.alerts)


def test_pagination_and_back(harness):
    h = harness
    hair = [k for k, _, _ in bot.STAGES].index("hair")
    seq = basics(h) + all_next(h)[:hair] + [h.cb(f"p:{hair}:1")]
    h.run(seq)
    text, kb = h.edits[-1]
    labels = [b.text for row in kb.inline_keyboard for b in row]
    assert bot.TAG_OPTIONS["hair"][bot.PAGE_SIZE] in labels      # page 2 shown
    assert "page 2/3" in labels
    h.run([h.cb(f"b:{hair}")])
    assert h.ud()["stage"] == hair - 1


def test_stale_menu_is_ignored(harness):
    h = harness
    h.run(basics(h) + [h.cb("n:0"), h.cb("t:0:0")])
    assert h.ud()["sel"]["body"] == []
    assert any("out of date" in a for a in h.alerts)


def test_review_edit_goes_back_to_review(harness):
    h = harness
    h.run(basics(h) + all_next(h) + [h.cb("notes:skip"), h.cb("r:edit"), h.cb("t:0:1")]
          + all_next(h) + [h.cb("r:ok"), photo(h), h.cb("ph:done")])
    assert f"Appearance: {bot.TAG_OPTIONS['body'][1]}" in prompt_txt(h)
    assert sum("Look right?" in (t or "") for t in h.out) == 1  # second pass re-shows card without notes step


def test_done_without_photo(harness):
    h = harness
    h.run(basics(h) + all_next(h) + [h.cb("notes:skip"), h.cb("r:ok"), h.msg("/done")])
    assert h.out[-1] == "Send at least one photo first."
    assert not h.docs


def test_document_image_keeps_extension_and_size_cap(harness):
    h = harness
    big = Document("b", "ub", file_name="big.png", mime_type="image/png", file_size=bot.MAX_PHOTO_BYTES + 1)
    ok = Document("d", "ud", file_name="pic.PNG", mime_type="image/png", file_size=1000)
    h.run(basics(h) + all_next(h) + [h.cb("notes:skip"), h.cb("r:ok"), h.msg(document=big),
          h.msg(document=ok), h.cb("ph:done")])
    assert any("too large" in (t or "") for t in h.out)
    assert zip_names(h) == ["prompt.txt", "photos/01.png"]


def test_unsafe_name_is_sanitized_and_escaped(harness):
    h = harness
    h.run(basics(h, name='../"Big" <Will>/..') + all_next(h) + [h.cb("notes:skip"), h.cb("r:ok"),
          photo(h), h.cb("ph:done")])
    assert h.docs[0][0] == "Big_Will_refsheet.zip"
    assert "&lt;Will&gt;" in h.docs[0][2]


def test_message_without_session_gets_hint(harness):
    h = harness
    h.run([h.msg("hello")])
    assert h.out == ["Session expired or not started. Send /start to begin."]


def test_off_step_input_gets_reply(harness):
    h = harness
    h.run([h.msg("/start"), photo(h)])
    assert "Didn't catch that" in h.out[-1]


def test_start_mentions_admin_copy_only_when_admin_set(harness, monkeypatch):
    h = harness
    h.run([h.msg("/start")])
    assert "sent to the bot admin" not in h.out[-1]
    monkeypatch.setattr(bot, "ADMIN_ID", 42)
    h.run([h.msg("/start")])
    assert "sent to the bot admin" in h.out[-1]
