"""Выбор «мозга» ассистента по ключам в .env — общий для Telegram-бота и Джарвиса."""

import os
from pathlib import Path
from typing import Callable


def detect_backend() -> str:
    return os.environ.get("ASSISTANT_BACKEND") or (
        "api" if os.environ.get("ANTHROPIC_API_KEY")
        else "gemini" if os.environ.get("GEMINI_API_KEY")
        else "claude-code"
    )


def backend_label(backend: str) -> str:
    return {
        "api": "Claude API",
        "gemini": f"Google Gemini ({os.environ.get('GEMINI_MODEL', 'gemini-flash-latest')})",
        "claude-code": "Claude Code по подписке",
    }.get(backend, backend)


def make_assistant_factory(data_dir: Path, backend: str | None = None) -> Callable[[str], object]:
    """Вернуть функцию chat_key -> ассистент (у каждого чата своя история)."""
    backend = backend or detect_backend()
    if backend == "gemini":
        from google import genai

        from assistant.gemini_backend import GeminiAssistant
        from assistant.tools import Toolbox

        client, toolbox = genai.Client(api_key=os.environ["GEMINI_API_KEY"]), Toolbox(data_dir)
        return lambda chat_key: GeminiAssistant(client, toolbox)
    if backend == "api":
        import anthropic

        from assistant.main import Assistant
        from assistant.tools import Toolbox

        client, toolbox = anthropic.Anthropic(), Toolbox(data_dir)
        return lambda chat_key: Assistant(client, toolbox)

    from assistant.claude_code_backend import ClaudeCodeAssistant

    ClaudeCodeAssistant(data_dir)  # сразу проверить, что Claude Code установлен
    return lambda chat_key: ClaudeCodeAssistant(data_dir, chat_key=str(chat_key))
