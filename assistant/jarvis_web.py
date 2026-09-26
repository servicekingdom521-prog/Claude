"""Джарвис — голосовой HUD-интерфейс в браузере: python -m assistant.jarvis_web

Открывает http://localhost:8765. Сервер доступен только с этого компьютера.
Распознавание речи делает браузер (Chrome или Edge), озвучку — Edge TTS.
"""

import asyncio
import json
import logging
import os
import re
import tempfile
import time
import webbrowser
from datetime import datetime
from pathlib import Path

import psutil
from aiohttp import web
from dotenv import load_dotenv

from assistant import voice
from assistant.backends import backend_label, detect_backend, make_assistant_factory
from assistant.persona import USER_TITLE

log = logging.getLogger("assistant.jarvis")
WEB_DIR = Path(__file__).parent / "web"
JARVIS_VOICE = os.environ.get("JARVIS_VOICE", "ru-RU-DmitryNeural")
ALLOWED_HOSTS = {"localhost", "127.0.0.1"}
STARTED_AT = time.time()

PAGE_HEAD = (
    '<!doctype html><html lang="ru"><head><meta charset="utf-8">'
    '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">'
    "</head><body>"
)


def read_tasks(data_dir: Path) -> list[dict]:
    """Задачи из tasks.json (режимы API/Gemini) или tasks.md (режим подписки)."""
    tasks: list[dict] = []
    json_file, md_file = data_dir / "tasks.json", data_dir / "tasks.md"
    if json_file.exists():
        for t in json.loads(json_file.read_text(encoding="utf-8")):
            tasks.append({"title": t["title"], "done": t.get("done", False), "due": t.get("due")})
    if md_file.exists():
        for line in md_file.read_text(encoding="utf-8").splitlines():
            m = re.match(r"\s*[-*]\s*\[([ xX])\]\s*(.+)", line)
            if m:
                tasks.append({"title": m.group(2).strip(), "done": m.group(1).lower() == "x", "due": None})
    return tasks


def read_notes(data_dir: Path, limit: int = 6) -> list[str]:
    notes: list[str] = []
    json_file, md_file = data_dir / "notes.json", data_dir / "notes.md"
    if json_file.exists():
        notes += [n["title"] for n in json.loads(json_file.read_text(encoding="utf-8"))]
    if md_file.exists():
        notes += [
            line.lstrip("#").strip()
            for line in md_file.read_text(encoding="utf-8").splitlines()
            if re.match(r"#{1,3}\s", line) and not line.startswith("# Заметки")
        ]
    return notes[-limit:][::-1]


def system_stats() -> dict:
    battery = psutil.sensors_battery()
    return {
        "cpu": round(psutil.cpu_percent(interval=None)),
        "ram": round(psutil.virtual_memory().percent),
        "disk": round(psutil.disk_usage(str(Path.home().anchor or "/")).percent),
        "battery": None if battery is None else {"percent": round(battery.percent), "plugged": battery.power_plugged},
        "uptime_s": int(time.time() - STARTED_AT),
    }


@web.middleware
async def guard(request: web.Request, handler):
    # Защита от DNS-rebinding и запросов со сторонних сайтов к localhost.
    host = (request.host or "").rsplit(":", 1)[0].strip("[]")
    if host not in ALLOWED_HOSTS:
        return web.Response(status=403, text="forbidden host")
    if request.path.startswith("/api/") and request.headers.get("X-Jarvis") != "1":
        return web.Response(status=403, text="missing header")
    return await handler(request)


class JarvisServer:
    def __init__(self, data_dir: Path, make_assistant, backend: str):
        self.data_dir = data_dir
        self.assistant = make_assistant("jarvis-web")
        self.backend = backend
        self.lock = asyncio.Lock()

    async def index(self, request: web.Request) -> web.Response:
        page = (WEB_DIR / "jarvis.html").read_text(encoding="utf-8")
        return web.Response(text=PAGE_HEAD + page + "</body></html>", content_type="text/html")

    async def status(self, request: web.Request) -> web.Response:
        return web.json_response({
            "jarvis": True,
            "backend": backend_label(self.backend),
            "title": USER_TITLE,
            "time": datetime.now().astimezone().isoformat(timespec="seconds"),
            "system": system_stats(),
            "tasks": read_tasks(self.data_dir),
            "notes": read_notes(self.data_dir),
        })

    async def ask(self, request: web.Request) -> web.Response:
        body = await request.json()
        text = str(body.get("text", "")).strip()
        if not text:
            return web.json_response({"error": "Пустой запрос"}, status=400)
        async with self.lock:
            try:
                reply = await asyncio.to_thread(self.assistant.ask, text, _NullOut())
            except Exception as e:  # ошибки бэкенда показываем в интерфейсе
                log.exception("Сбой при ответе")
                return web.json_response({"error": str(e) or e.__class__.__name__})
        return web.json_response({"reply": reply.strip() or "Готово, " + USER_TITLE + "."})

    async def reset(self, request: web.Request) -> web.Response:
        self.assistant.reset()
        return web.json_response({"ok": True})

    async def tts(self, request: web.Request) -> web.Response:
        body = await request.json()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "reply.mp3"
            try:
                ok = await voice.synthesize(str(body.get("text", "")), path, voice=JARVIS_VOICE)
            except Exception:
                log.exception("Не удалось озвучить")
                return web.Response(status=502, text="tts failed")
            if not ok:
                return web.Response(status=204)
            return web.Response(body=path.read_bytes(), content_type="audio/mpeg")


class _NullOut:
    def write(self, _text):
        pass

    def flush(self):
        pass


def build_app(server: JarvisServer) -> web.Application:
    app = web.Application(middlewares=[guard])
    app.router.add_get("/", server.index)
    app.router.add_get("/api/status", server.status)
    app.router.add_post("/api/ask", server.ask)
    app.router.add_post("/api/reset", server.reset)
    app.router.add_post("/api/tts", server.tts)
    return app


def main() -> None:
    load_dotenv()
    logging.basicConfig(format="%(asctime)s %(levelname)s %(message)s", level=logging.INFO)
    data_dir = Path(os.environ.get("ASSISTANT_DATA_DIR", "data")).resolve()
    data_dir.mkdir(parents=True, exist_ok=True)
    backend = detect_backend()
    server = JarvisServer(data_dir, make_assistant_factory(data_dir, backend), backend)
    port = int(os.environ.get("JARVIS_PORT", "8765"))
    url = f"http://localhost:{port}"
    log.info("Джарвис запущен (%s): %s  — остановить: Ctrl+C", backend_label(backend), url)
    if os.environ.get("JARVIS_NO_BROWSER") != "1":
        webbrowser.open(url)
    web.run_app(build_app(server), host="127.0.0.1", port=port, print=None)


if __name__ == "__main__":
    main()
