import json
import os
import stat
import sys

import pytest

from assistant.claude_code_backend import ClaudeCodeAssistant, ClaudeCodeError

FAKE_CLAUDE = """#!{python}
import json, os, sys
args = sys.argv[1:]
text = sys.stdin.read()
log = os.path.join(os.getcwd(), "calls.jsonl")
with open(log, "a", encoding="utf-8") as f:
    f.write(json.dumps({{"args": args, "stdin": text, "has_key": "ANTHROPIC_API_KEY" in os.environ}}) + "\\n")
if text == "сломайся":
    print("boom", file=sys.stderr); sys.exit(1)
if text == "ошибка":
    print(json.dumps({{"is_error": True, "result": "лимит исчерпан", "session_id": "s1"}})); sys.exit(0)
sid = args[args.index("--resume") + 1] if "--resume" in args else "s1"
print(json.dumps({{"is_error": False, "result": "ответ: " + text, "session_id": sid}}))
"""


@pytest.fixture
def fake_bin(tmp_path):
    path = tmp_path / "claude"
    path.write_text(FAKE_CLAUDE.format(python=sys.executable), encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return str(path)


def calls(data_dir):
    return [json.loads(line) for line in (data_dir / "calls.jsonl").read_text(encoding="utf-8").splitlines()]


def test_conversation_resumes_and_hides_api_key(tmp_path, fake_bin, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    data = tmp_path / "data"
    a = ClaudeCodeAssistant(data, chat_key="7", claude_bin=fake_bin)

    assert a.ask("привет") == "ответ: привет"
    assert a.ask("ещё") == "ответ: ещё"
    first, second = calls(data)
    assert "--resume" not in first["args"]
    assert second["args"][second["args"].index("--resume") + 1] == "s1"
    assert first["stdin"] == "привет"
    assert not first["has_key"]
    assert "Bash" not in first["args"][first["args"].index("--tools") + 1]


def test_session_survives_restart_and_reset(tmp_path, fake_bin):
    data = tmp_path / "data"
    ClaudeCodeAssistant(data, chat_key="7", claude_bin=fake_bin).ask("привет")
    restarted = ClaudeCodeAssistant(data, chat_key="7", claude_bin=fake_bin)
    restarted.ask("снова")
    assert "--resume" in calls(data)[-1]["args"]
    restarted.reset()
    restarted.ask("заново")
    assert "--resume" not in calls(data)[-1]["args"]


def test_errors_are_reported(tmp_path, fake_bin):
    a = ClaudeCodeAssistant(tmp_path / "data", claude_bin=fake_bin)
    with pytest.raises(ClaudeCodeError, match="лимит"):
        a.ask("ошибка")
    with pytest.raises(ClaudeCodeError, match="boom"):
        a.ask("сломайся")
    # после сбоя сессия сброшена, следующее сообщение начнёт новый диалог
    a.ask("привет")
    assert "--resume" not in calls(tmp_path / "data")[-1]["args"]


def test_claude_found_in_installer_folder(tmp_path, monkeypatch):
    monkeypatch.delenv("CLAUDE_BIN", raising=False)
    monkeypatch.setattr("shutil.which", lambda name: None)
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    exe = tmp_path / ".local" / "bin" / "claude.exe"
    exe.parent.mkdir(parents=True)
    exe.write_text("")
    assert ClaudeCodeAssistant(tmp_path / "data").claude_bin == str(exe)


def test_missing_claude_is_explained(tmp_path, monkeypatch):
    monkeypatch.delenv("CLAUDE_BIN", raising=False)
    monkeypatch.setattr("shutil.which", lambda name: None)
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    with pytest.raises(ClaudeCodeError, match="Claude Code"):
        ClaudeCodeAssistant(tmp_path)
