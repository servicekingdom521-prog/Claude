"""Локальные инструменты ассистента: заметки, задачи, файлы, черновики писем.

Всё хранится в папке данных (по умолчанию ./data) в виде JSON и обычных файлов,
поэтому ассистент помнит заметки и задачи между запусками.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Callable


class ToolError(Exception):
    """Ошибка, которую нужно вернуть модели как is_error tool_result."""


class Toolbox:
    def __init__(self, data_dir: Path):
        self.data_dir = Path(data_dir).resolve()
        self.workspace = self.data_dir / "workspace"
        self.drafts = self.data_dir / "drafts"
        for d in (self.data_dir, self.workspace, self.drafts):
            d.mkdir(parents=True, exist_ok=True)
        self._handlers: dict[str, Callable[..., str]] = {
            "get_current_datetime": self.get_current_datetime,
            "save_note": self.save_note,
            "search_notes": self.search_notes,
            "add_task": self.add_task,
            "list_tasks": self.list_tasks,
            "complete_task": self.complete_task,
            "list_files": self.list_files,
            "read_file": self.read_file,
            "write_file": self.write_file,
            "save_email_draft": self.save_email_draft,
        }

    # --- инфраструктура -------------------------------------------------

    def run(self, name: str, tool_input: dict[str, Any]) -> str:
        handler = self._handlers.get(name)
        if handler is None:
            raise ToolError(f"Неизвестный инструмент: {name}")
        try:
            return handler(**tool_input)
        except TypeError as e:
            raise ToolError(f"Неверные аргументы для {name}: {e}") from e

    def _load(self, name: str) -> list[dict]:
        path = self.data_dir / f"{name}.json"
        if not path.exists():
            return []
        return json.loads(path.read_text(encoding="utf-8"))

    def _save(self, name: str, items: list[dict]) -> None:
        path = self.data_dir / f"{name}.json"
        path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")

    def _safe_path(self, base: Path, relative: str) -> Path:
        path = (base / relative).resolve()
        if not path.is_relative_to(base):
            raise ToolError(f"Путь вне разрешённой папки: {relative}")
        return path

    @staticmethod
    def _now() -> str:
        return datetime.now().astimezone().isoformat(timespec="seconds")

    # --- общие ----------------------------------------------------------

    def get_current_datetime(self) -> str:
        now = datetime.now().astimezone()
        return now.strftime("%Y-%m-%d %H:%M:%S %Z, %A")

    # --- заметки --------------------------------------------------------

    def save_note(self, title: str, content: str, tags: list[str] | None = None) -> str:
        notes = self._load("notes")
        note_id = max((n["id"] for n in notes), default=0) + 1
        notes.append({
            "id": note_id,
            "title": title,
            "content": content,
            "tags": tags or [],
            "created_at": self._now(),
        })
        self._save("notes", notes)
        return f"Заметка #{note_id} «{title}» сохранена."

    def search_notes(self, query: str = "") -> str:
        notes = self._load("notes")
        q = query.lower().strip()
        found = [
            n for n in notes
            if not q
            or q in n["title"].lower()
            or q in n["content"].lower()
            or any(q in t.lower() for t in n["tags"])
        ]
        if not found:
            return "Заметок не найдено."
        return json.dumps(found, ensure_ascii=False, indent=2)

    # --- задачи ---------------------------------------------------------

    def add_task(self, title: str, due: str | None = None, priority: str = "normal") -> str:
        if priority not in ("low", "normal", "high"):
            raise ToolError("priority должен быть low, normal или high")
        tasks = self._load("tasks")
        task_id = max((t["id"] for t in tasks), default=0) + 1
        tasks.append({
            "id": task_id,
            "title": title,
            "due": due,
            "priority": priority,
            "done": False,
            "created_at": self._now(),
        })
        self._save("tasks", tasks)
        return f"Задача #{task_id} «{title}» добавлена."

    def list_tasks(self, include_done: bool = False) -> str:
        tasks = [t for t in self._load("tasks") if include_done or not t["done"]]
        if not tasks:
            return "Задач нет."
        return json.dumps(tasks, ensure_ascii=False, indent=2)

    def complete_task(self, task_id: int) -> str:
        tasks = self._load("tasks")
        for t in tasks:
            if t["id"] == task_id:
                t["done"] = True
                t["completed_at"] = self._now()
                self._save("tasks", tasks)
                return f"Задача #{task_id} отмечена выполненной."
        raise ToolError(f"Задача #{task_id} не найдена")

    # --- файлы ----------------------------------------------------------

    def list_files(self) -> str:
        files = sorted(
            str(p.relative_to(self.workspace))
            for p in self.workspace.rglob("*") if p.is_file()
        )
        return "\n".join(files) if files else "Папка workspace пуста."

    def read_file(self, path: str) -> str:
        file = self._safe_path(self.workspace, path)
        if not file.is_file():
            raise ToolError(f"Файл не найден: {path}")
        return file.read_text(encoding="utf-8", errors="replace")

    def write_file(self, path: str, content: str) -> str:
        file = self._safe_path(self.workspace, path)
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(content, encoding="utf-8")
        return f"Файл сохранён: workspace/{file.relative_to(self.workspace)}"

    # --- бизнес ---------------------------------------------------------

    def save_email_draft(self, to: str, subject: str, body: str) -> str:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        file = self.drafts / f"{stamp}.md"
        file.write_text(f"**Кому:** {to}\n**Тема:** {subject}\n\n{body}\n", encoding="utf-8")
        return f"Черновик письма сохранён: drafts/{file.name} (письмо НЕ отправлено)."


def _schema(properties: dict, required: list[str]) -> dict:
    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


# Серверные инструменты выполняются на стороне Anthropic — реализовывать их не нужно.
SERVER_TOOLS: list[dict] = [
    {"type": "web_search_20260209", "name": "web_search", "max_uses": 8},
    {"type": "web_fetch_20260209", "name": "web_fetch", "max_uses": 8},
]

LOCAL_TOOLS: list[dict] = [
    {
        "name": "get_current_datetime",
        "description": "Текущие дата, время и день недели пользователя. Используй для сроков, планирования и относительных дат («завтра», «в пятницу»).",
        "input_schema": _schema({}, []),
    },
    {
        "name": "save_note",
        "description": "Сохранить заметку в постоянную память пользователя (идеи, итоги встреч, контакты, факты, которые пригодятся позже).",
        "input_schema": _schema({
            "title": {"type": "string", "description": "Короткий заголовок"},
            "content": {"type": "string", "description": "Текст заметки"},
            "tags": {"type": "array", "items": {"type": "string"}, "description": "Теги для поиска"},
        }, ["title", "content"]),
    },
    {
        "name": "search_notes",
        "description": "Найти сохранённые заметки по слову в заголовке, тексте или тегах. Пустой запрос возвращает все заметки.",
        "input_schema": _schema({
            "query": {"type": "string", "description": "Строка поиска"},
        }, []),
    },
    {
        "name": "add_task",
        "description": "Добавить задачу в список дел пользователя.",
        "input_schema": _schema({
            "title": {"type": "string", "description": "Что нужно сделать"},
            "due": {"type": "string", "description": "Срок в формате YYYY-MM-DD, если известен"},
            "priority": {"type": "string", "enum": ["low", "normal", "high"]},
        }, ["title"]),
    },
    {
        "name": "list_tasks",
        "description": "Показать список задач пользователя.",
        "input_schema": _schema({
            "include_done": {"type": "boolean", "description": "Включить выполненные задачи"},
        }, []),
    },
    {
        "name": "complete_task",
        "description": "Отметить задачу выполненной по её номеру.",
        "input_schema": _schema({
            "task_id": {"type": "integer"},
        }, ["task_id"]),
    },
    {
        "name": "list_files",
        "description": "Список файлов в рабочей папке пользователя (workspace).",
        "input_schema": _schema({}, []),
    },
    {
        "name": "read_file",
        "description": "Прочитать текстовый файл из рабочей папки (workspace). Путь относительный.",
        "input_schema": _schema({
            "path": {"type": "string"},
        }, ["path"]),
    },
    {
        "name": "write_file",
        "description": "Создать или перезаписать текстовый файл в рабочей папке (workspace): отчёты, тексты, планы, таблицы CSV, Markdown-документы.",
        "input_schema": _schema({
            "path": {"type": "string", "description": "Относительный путь, например reports/q3.md"},
            "content": {"type": "string"},
        }, ["path", "content"]),
    },
    {
        "name": "save_email_draft",
        "description": "Сохранить черновик делового письма в папку drafts. Письмо не отправляется — пользователь отправит его сам.",
        "input_schema": _schema({
            "to": {"type": "string", "description": "Получатель (имя или email)"},
            "subject": {"type": "string"},
            "body": {"type": "string"},
        }, ["to", "subject", "body"]),
    },
]

ALL_TOOLS = SERVER_TOOLS + LOCAL_TOOLS
