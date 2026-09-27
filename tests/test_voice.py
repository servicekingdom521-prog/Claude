import asyncio

import pytest

pytest.importorskip("edge_tts")

from aiohttp import web  # noqa: E402
from aiohttp.test_utils import TestServer  # noqa: E402

from assistant import voice  # noqa: E402


class FakeEdge:
    calls = []

    def __init__(self, text, voice_name):
        FakeEdge.calls.append((text, voice_name))

    async def save(self, path):
        with open(path, "wb") as f:
            f.write(b"edge-mp3")


def run_with_fake_elevenlabs(status, tmp_path, monkeypatch):
    seen = {}

    async def handler(request):
        seen["key"] = request.headers.get("xi-api-key")
        seen["path"] = request.path
        seen["body"] = await request.json()
        if status != 200:
            return web.Response(status=status, text='{"detail":"quota_exceeded"}')
        return web.Response(body=b"eleven-mp3", content_type="audio/mpeg")

    async def go():
        app = web.Application()
        app.router.add_post("/v1/text-to-speech/{voice}", handler)
        async with TestServer(app) as server:
            monkeypatch.setenv("ELEVENLABS_BASE_URL", str(server.make_url("")).rstrip("/"))
            out = tmp_path / "reply.mp3"
            assert await voice.synthesize("**Добрый вечер**, сэр.", out)
            return out.read_bytes()

    FakeEdge.calls = []
    monkeypatch.setattr(voice.edge_tts, "Communicate", FakeEdge)
    monkeypatch.setenv("ELEVENLABS_API_KEY", "test-key")
    monkeypatch.setenv("ELEVENLABS_VOICE_ID", "voice123")
    return asyncio.run(go()), seen


def test_elevenlabs_used_when_key_set(tmp_path, monkeypatch):
    audio, seen = run_with_fake_elevenlabs(200, tmp_path, monkeypatch)
    assert audio == b"eleven-mp3"
    assert seen["key"] == "test-key" and seen["path"] == "/v1/text-to-speech/voice123"
    assert seen["body"]["text"] == "Добрый вечер, сэр."
    assert FakeEdge.calls == []


def test_falls_back_to_edge_when_quota_exceeded(tmp_path, monkeypatch):
    monkeypatch.setenv("TTS_VOICE", "ru-RU-DmitryNeural")
    audio, _ = run_with_fake_elevenlabs(401, tmp_path, monkeypatch)
    assert audio == b"edge-mp3"
    assert FakeEdge.calls == [("Добрый вечер, сэр.", "ru-RU-DmitryNeural")]


def test_edge_used_without_key(tmp_path, monkeypatch):
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    monkeypatch.setattr(voice.edge_tts, "Communicate", FakeEdge)
    FakeEdge.calls = []
    out = tmp_path / "r.mp3"
    assert asyncio.run(voice.synthesize("Привет", out, voice="uk-UA-OstapNeural"))
    assert FakeEdge.calls == [("Привет", "uk-UA-OstapNeural")]
