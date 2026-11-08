"""Offline conversation tests: no network, Telegram API calls are stubbed.
Run from bot/:  python -m pytest -q tests
"""
import asyncio
import datetime
import io
import os
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["BOT_TOKEN"] = "123:TEST"

import pytest
from telegram import (Bot, CallbackQuery, Chat, Document, Message, MessageEntity,
                      PhotoSize, Update, User)
from telegram.ext import Application

import bot


class _File:
    async def download_to_memory(self, b):
        b.write(b"img")


@pytest.fixture
def harness(monkeypatch):
    out, docs = [], []

    async def reply_text(self, text=None, *a, **k):
        out.append(text)

    async def reply_document(self, *a, document=None, filename=None, **k):
        docs.append((filename, document.getvalue()))

    async def noop(self, *a, **k):
        return None

    async def get_file(self, *a, **k):
        return _File()

    async def bot_init(self):
        self._initialized = True
        self._bot_user = User(99, "bot", True, username="bot")

    monkeypatch.setattr(Message, "reply_text", reply_text)
    monkeypatch.setattr(Message, "reply_document", reply_document)
    for name in ("answer", "edit_message_text", "edit_message_reply_markup"):
        monkeypatch.setattr(CallbackQuery, name, noop)
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

    return type("H", (), dict(out=out, docs=docs, msg=staticmethod(msg), cb=staticmethod(cb),
                              run=staticmethod(lambda u: asyncio.run(run(u)))))


def _to_notes(h, name="Kai"):
    seq = [h.msg("/start"), h.msg(name), h.msg("182 cm"), h.msg("73 kg"), h.cb("tag:body:athletic")]
    seq += [h.cb(f"done:{s}") for s in ("body", "skin", "hair", "face", "style", "vibe")]
    return seq


def test_skip_notes_reaches_photos_and_returns_zip(harness):
    h = harness
    h.run(_to_notes(h) + [h.msg("/skip"), h.msg(photo=[PhotoSize("f", "u", 10, 10)]), h.msg("/done")])
    assert "Send 1–4 photos. /done when finished." in h.out
    assert len(h.docs) == 1
    fname, data = h.docs[0]
    assert fname == "Kai_refsheet.zip"
    names = zipfile.ZipFile(io.BytesIO(data)).namelist()
    assert names == ["prompt.txt", "photos/01.jpg"]


def test_text_notes_also_work(harness):
    h = harness
    h.run(_to_notes(h) + [h.msg("tattoo on left arm")])
    assert h.out[-1] == "Send 1–4 photos. /done when finished."


def test_document_image_keeps_extension_and_size_cap(harness):
    h = harness
    big = Document("b", "ub", file_name="big.png", mime_type="image/png", file_size=bot.MAX_PHOTO_BYTES + 1)
    ok = Document("d", "ud", file_name="pic.PNG", mime_type="image/png", file_size=1000)
    h.run(_to_notes(h) + [h.msg("/skip"), h.msg(document=big), h.msg(document=ok), h.msg("/done")])
    assert any("too large" in (t or "") for t in h.out)
    names = zipfile.ZipFile(io.BytesIO(h.docs[0][1])).namelist()
    assert names == ["prompt.txt", "photos/01.png"]


def test_unsafe_name_is_sanitized_in_filename(harness):
    h = harness
    h.run(_to_notes(h, name='../"Big" Will/..') + [h.msg("/skip"),
          h.msg(photo=[PhotoSize("f", "u", 10, 10)]), h.msg("/done")])
    assert h.docs[0][0] == "Big_Will_refsheet.zip"


def test_message_without_session_gets_hint(harness):
    h = harness
    h.run([h.msg("hello")])
    assert h.out == ["Session expired or not started. Send /start to begin."]


def test_off_step_input_gets_reply(harness):
    h = harness
    h.run([h.msg("/start"), h.msg(photo=[PhotoSize("f", "u", 10, 10)])])
    assert "Didn't catch that" in h.out[-1]


def test_start_mentions_admin_copy_only_when_admin_set(harness, monkeypatch):
    h = harness
    h.run([h.msg("/start")])
    assert "sent to the bot admin" not in h.out[-1]
    monkeypatch.setattr(bot, "ADMIN_ID", 42)
    h.run([h.msg("/start")])
    assert "sent to the bot admin" in h.out[-1]
