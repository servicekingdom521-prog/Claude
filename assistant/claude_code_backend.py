"""Ассистент через Claude Code на этом компьютере — работает по подписке Claude, без API-ключа.

Каждое сообщение запускает `claude -p` в папке данных. Диалог продолжается через
`--resume <session_id>`; номера сессий сохраняются в sessions.json, поэтому
контекст переживает перезапуск бота.
"""

import json
import os
import shutil
import subprocess
from pathlib import Path

from assistant.persona import PERSONA

SYSTEM_PROMPT = PERSONA + """Ты помогаешь пользователю с повседневными и бизнес-задачами. Пользователь общается с тобой через Telegram, часто голосом, поэтому отвечай разговорно, коротко и без таблиц; развёрнутые материалы сохраняй в файлы.

Текущая папка — твоя память:
- notes.md — заметки (заголовок, дата, текст). Если просят «запомнить» — допиши сюда.
- tasks.md — список задач в формате «- [ ] задача (срок, приоритет)»; выполненные отмечай «- [x]».
- workspace/ — документы: отчёты, планы, коммерческие предложения, тексты.
- drafts/ — черновики писем (сам ты письма не отправляешь).
Перед ответом о заметках или задачах прочитай соответствующий файл.

Для актуальной информации используй поиск в интернете и указывай источники.
Отвечай на языке пользователя.
"""

TOOLS = "WebSearch,WebFetch,Read,Write,Edit,Glob,Grep"
TIMEOUT_SECONDS = 600


class ClaudeCodeError(Exception):
    pass


def find_claude() -> str | None:
    """Найти claude в PATH, в CLAUDE_BIN или в папке стандартного установщика."""
    if os.environ.get("CLAUDE_BIN"):
        return os.environ["CLAUDE_BIN"]
    found = shutil.which("claude")
    if found:
        return found
    # Установщик кладёт claude в ~/.local/bin, но открытые окна не видят обновлённый PATH.
    for name in ("claude.exe", "claude"):
        candidate = Path.home() / ".local" / "bin" / name
        if candidate.is_file():
            return str(candidate)
    return None


class ClaudeCodeAssistant:
    def __init__(self, data_dir: Path, chat_key: str = "default", claude_bin: str | None = None):
        self.data_dir = Path(data_dir).resolve()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        for sub in ("workspace", "drafts"):
            (self.data_dir / sub).mkdir(exist_ok=True)
        self.prompt_file = self.data_dir / "system_prompt.txt"
        self.prompt_file.write_text(SYSTEM_PROMPT, encoding="utf-8")
        self.sessions_file = self.data_dir / "sessions.json"
        self.chat_key = chat_key
        self.claude_bin = claude_bin or find_claude()
        if not self.claude_bin:
            raise ClaudeCodeError("Не найдена команда claude — установите Claude Code и войдите в аккаунт.")

    def _sessions(self) -> dict[str, str]:
        if self.sessions_file.exists():
            return json.loads(self.sessions_file.read_text(encoding="utf-8"))
        return {}

    def _save_session(self, session_id: str | None) -> None:
        sessions = self._sessions()
        if session_id:
            sessions[self.chat_key] = session_id
        else:
            sessions.pop(self.chat_key, None)
        self.sessions_file.write_text(json.dumps(sessions), encoding="utf-8")

    def reset(self) -> None:
        self._save_session(None)

    def build_command(self, session_id: str | None) -> list[str]:
        cmd = [
            self.claude_bin, "-p",
            "--output-format", "json",
            "--append-system-prompt-file", str(self.prompt_file),
            "--tools", TOOLS,
            "--allowedTools", TOOLS,
        ]
        if session_id:
            cmd += ["--resume", session_id]
        return cmd

    def ask(self, user_text: str, out=None) -> str:
        session_id = self._sessions().get(self.chat_key)
        env = dict(os.environ)
        # Без этого Claude Code взял бы API-ключ вместо подписки.
        env.pop("ANTHROPIC_API_KEY", None)
        try:
            proc = subprocess.run(
                self.build_command(session_id),
                input=user_text,
                capture_output=True,
                text=True,
                encoding="utf-8",
                cwd=self.data_dir,
                env=env,
                timeout=TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired as e:
            raise ClaudeCodeError("Claude думал слишком долго (больше 10 минут).") from e

        try:
            data = json.loads(proc.stdout)
        except json.JSONDecodeError as e:
            detail = (proc.stderr or proc.stdout).strip()[-500:]
            if session_id:
                # Сессия могла пропасть — начнём новую при следующем сообщении.
                self._save_session(None)
            raise ClaudeCodeError(f"Claude Code завершился с ошибкой: {detail}") from e

        self._save_session(data.get("session_id"))
        if data.get("is_error"):
            raise ClaudeCodeError(data.get("result") or f"Ошибка Claude Code ({data.get('subtype')})")
        return data.get("result", "")
