import asyncio
import json

import pytest

pytest.importorskip("aiohttp")
pytest.importorskip("psutil")

from aiohttp.test_utils import TestClient, TestServer  # noqa: E402

from assistant.jarvis_web import JarvisServer, build_app, read_notes, read_tasks  # noqa: E402

H = {"X-Jarvis": "1"}


class FakeAssistant:
    def __init__(self):
        self.asked, self.resets = [], 0

    def ask(self, text, out):
        self.asked.append(text)
        return f"Да, сэр: {text}"

    def reset(self):
        self.resets += 1


def run(data_dir, scenario):
    fake = FakeAssistant()
    server = JarvisServer(data_dir, lambda key: fake, "claude-code")

    async def go():
        async with TestClient(TestServer(build_app(server))) as client:
            await scenario(client)

    asyncio.run(go())
    return fake


def test_reads_tasks_and_notes_from_both_formats(tmp_path):
    (tmp_path / "tasks.json").write_text(json.dumps([{"title": "A", "done": False, "due": "2026-10-01"}]), encoding="utf-8")
    (tmp_path / "tasks.md").write_text("# Задачи\n- [ ] Б\n- [x] В\n", encoding="utf-8")
    (tmp_path / "notes.md").write_text("# Заметки\n## Встреча\nтекст\n## Идея\n", encoding="utf-8")
    assert [(t["title"], t["done"]) for t in read_tasks(tmp_path)] == [("A", False), ("Б", False), ("В", True)]
    assert read_notes(tmp_path) == ["Идея", "Встреча"]


def test_api_requires_header_and_local_host(tmp_path):
    async def scenario(client):
        assert (await client.get("/api/status")).status == 403
        assert (await client.get("/api/status", headers={**H, "Host": "evil.example"})).status == 403
        res = await client.get("/api/status", headers=H)
        assert res.status == 200
        data = await res.json()
        assert data["jarvis"] is True and "cpu" in data["system"]

    run(tmp_path, scenario)


def test_ask_reset_and_page(tmp_path):
    async def scenario(client):
        res = await client.post("/api/ask", headers=H, json={"text": "статус"})
        assert (await res.json()) == {"reply": "Да, сэр: статус"}
        assert (await client.post("/api/ask", headers=H, json={"text": " "})).status == 400
        assert (await client.post("/api/reset", headers=H, json={})).status == 200
        page = await (await client.get("/")).text()
        assert page.startswith("<!doctype html>") and "J.A.R.V.I.S." in page

    fake = run(tmp_path, scenario)
    assert fake.asked == ["статус"] and fake.resets == 1


def test_backend_errors_are_returned_to_the_page(tmp_path):
    class Broken(FakeAssistant):
        def ask(self, text, out):
            raise RuntimeError("лимит подписки исчерпан")

    server = JarvisServer(tmp_path, lambda key: Broken(), "claude-code")

    async def go():
        async with TestClient(TestServer(build_app(server))) as client:
            data = await (await client.post("/api/ask", headers=H, json={"text": "привет"})).json()
            assert data == {"error": "лимит подписки исчерпан"}

    asyncio.run(go())
