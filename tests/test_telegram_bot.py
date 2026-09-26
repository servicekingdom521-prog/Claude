import asyncio
from types import SimpleNamespace

import pytest

pytest.importorskip("telegram")
pytest.importorskip("edge_tts")

from assistant import telegram_bot, voice  # noqa: E402
from assistant.telegram_bot import Bot, parse_allowed_users, split_message  # noqa: E402


def test_parse_allowed_users():
    assert parse_allowed_users("") == set()
    assert parse_allowed_users("123, 456") == {123, 456}


def test_split_message_respects_limit():
    text = "\n".join(f"строка {i}" for i in range(2000))
    chunks = split_message(text, limit=500)
    assert all(len(c) <= 500 for c in chunks)
    assert "".join(c.replace("\n", "") for c in chunks) == text.replace("\n", "")
    assert split_message("коротко") == ["коротко"]


def test_speech_text_strips_markdown():
    spoken = voice.to_speech_text("## План\n- **Первое** [сайт](https://a.b)\n| a | b |\n`код`")
    assert "*" not in spoken and "#" not in spoken and "http" not in spoken and "|" not in spoken
    assert "Первое" in spoken and "сайт" in spoken and "код" in spoken


def test_speech_text_truncates_long_answers():
    spoken = voice.to_speech_text("слово " * 2000)
    assert len(spoken) < voice.MAX_SPOKEN_CHARS + 50
    assert spoken.endswith("Полный ответ — в тексте.")


class FakeMessage:
    def __init__(self, text="", chat_id=1):
        self.text = text
        self.chat_id = chat_id
        self.replies = []
        self.voices = 0

    async def reply_text(self, text):
        self.replies.append(text)

    async def reply_voice(self, f):
        self.voices += 1


def make_update(user_id, text=""):
    msg = FakeMessage(text)
    return SimpleNamespace(
        effective_user=SimpleNamespace(id=user_id),
        effective_message=msg,
        effective_chat=SimpleNamespace(id=msg.chat_id),
    ), msg


def make_context():
    async def send_chat_action(*a, **k):
        pass
    return SimpleNamespace(bot=SimpleNamespace(send_chat_action=send_chat_action))


class FakeAssistant:
    def __init__(self, *a, **k):
        self.messages = []

    def ask(self, text, out):
        self.messages.append(text)
        return f"Ответ на: {text}"


@pytest.fixture
def bot(monkeypatch, tmp_path):
    monkeypatch.setattr(telegram_bot, "Assistant", FakeAssistant)
    return Bot({42}, toolbox=None, client=None)


def test_stranger_is_rejected_and_told_id(bot):
    update, msg = make_update(7, "привет")
    asyncio.run(bot.on_text(update, make_context()))
    assert "Доступ закрыт" in msg.replies[0] and "7" in msg.replies[0]
    assert bot.assistants == {}


def test_owner_gets_text_answer(bot):
    update, msg = make_update(42, "привет")
    asyncio.run(bot.on_text(update, make_context()))
    assert msg.replies == ["Ответ на: привет"]
    assert msg.voices == 0


def test_voice_input_gets_voice_answer(bot, monkeypatch):
    monkeypatch.setattr(voice, "transcribe", lambda path: "какие задачи")

    async def fake_synth(text, path):
        path.write_bytes(b"mp3")
        return True
    monkeypatch.setattr(voice, "synthesize", fake_synth)

    async def download_to_drive(path):
        path.write_bytes(b"ogg")

    async def get_file():
        return SimpleNamespace(download_to_drive=download_to_drive)

    update, msg = make_update(42)
    msg.voice = SimpleNamespace(get_file=get_file)
    msg.audio = None
    asyncio.run(bot.on_voice(update, make_context()))
    assert msg.replies == ["🎙 какие задачи", "Ответ на: какие задачи"]
    assert msg.voices == 1
