import io
from types import SimpleNamespace

import pytest

from assistant.main import Assistant
from assistant.tools import LOCAL_TOOLS, Toolbox, ToolError


@pytest.fixture
def toolbox(tmp_path):
    return Toolbox(tmp_path)


def test_every_local_tool_has_handler(toolbox):
    for tool in LOCAL_TOOLS:
        assert tool["name"] in toolbox._handlers


def test_notes_roundtrip(toolbox):
    toolbox.run("save_note", {"title": "Встреча", "content": "Обсудили бюджет", "tags": ["финансы"]})
    assert "бюджет" in toolbox.run("search_notes", {"query": "бюджет"})
    assert "Встреча" in toolbox.run("search_notes", {"query": "финансы"})
    assert toolbox.run("search_notes", {"query": "нет такого"}) == "Заметок не найдено."


def test_tasks_lifecycle(toolbox):
    toolbox.run("add_task", {"title": "Позвонить клиенту", "priority": "high"})
    assert "Позвонить" in toolbox.run("list_tasks", {})
    toolbox.run("complete_task", {"task_id": 1})
    assert toolbox.run("list_tasks", {}) == "Задач нет."
    assert "Позвонить" in toolbox.run("list_tasks", {"include_done": True})
    with pytest.raises(ToolError):
        toolbox.run("complete_task", {"task_id": 99})


def test_files_stay_inside_workspace(toolbox):
    toolbox.run("write_file", {"path": "reports/q3.md", "content": "# Отчёт"})
    assert toolbox.run("read_file", {"path": "reports/q3.md"}) == "# Отчёт"
    assert "reports/q3.md" in toolbox.run("list_files", {})
    with pytest.raises(ToolError):
        toolbox.run("read_file", {"path": "../tasks.json"})
    with pytest.raises(ToolError):
        toolbox.run("write_file", {"path": "/etc/passwd", "content": "x"})


def test_email_draft_saved(toolbox):
    msg = toolbox.run("save_email_draft", {"to": "a@b.c", "subject": "Счёт", "body": "Добрый день"})
    assert "НЕ отправлено" in msg
    assert len(list(toolbox.drafts.iterdir())) == 1


def test_bad_arguments_become_tool_error(toolbox):
    with pytest.raises(ToolError):
        toolbox.run("save_note", {"wrong": 1})
    with pytest.raises(ToolError):
        toolbox.run("unknown_tool", {})


# --- агентный цикл с поддельным API ------------------------------------------


class FakeStream:
    def __init__(self, message):
        self.message = message

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    @property
    def text_stream(self):
        return (b.text for b in self.message.content if b.type == "text")

    def get_final_message(self):
        return self.message


class FakeClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(stream=self._stream))

    def _stream(self, **kwargs):
        self.calls.append({**kwargs, "messages": list(kwargs["messages"])})
        return FakeStream(self.responses.pop(0))


def text(t):
    return SimpleNamespace(type="text", text=t)


def tool_use(id_, name, input_):
    return SimpleNamespace(type="tool_use", id=id_, name=name, input=input_)


def test_agent_runs_tools_then_answers(toolbox):
    client = FakeClient([
        SimpleNamespace(stop_reason="tool_use", content=[
            text("Добавляю. "),
            tool_use("t1", "add_task", {"title": "Отчёт"}),
            tool_use("t2", "complete_task", {"task_id": 42}),
        ]),
        SimpleNamespace(stop_reason="end_turn", content=[text("Готово!")]),
    ])
    agent = Assistant(client, toolbox)
    out = io.StringIO()

    assert agent.ask("Добавь задачу", out=out) == "Готово!"
    assert "Отчёт" in toolbox.run("list_tasks", {})

    # Оба результата отправлены одним сообщением, ошибка помечена is_error.
    results = client.calls[1]["messages"][-1]["content"]
    assert [r["tool_use_id"] for r in results] == ["t1", "t2"]
    assert results[0]["is_error"] is False
    assert results[1]["is_error"] is True
    assert client.calls[0]["fallbacks"] == "default"


def test_agent_continues_after_pause_turn(toolbox):
    client = FakeClient([
        SimpleNamespace(stop_reason="pause_turn", content=[text("Ищу…")]),
        SimpleNamespace(stop_reason="end_turn", content=[text("Нашёл.")]),
    ])
    agent = Assistant(client, toolbox)
    assert agent.ask("Найди новости", out=io.StringIO()) == "Нашёл."
    assert len(client.calls) == 2


def test_history_rolled_back_on_error(toolbox):
    class Boom(Exception):
        pass

    client = FakeClient([
        SimpleNamespace(stop_reason="tool_use", content=[tool_use("t1", "list_tasks", {})]),
    ])
    agent = Assistant(client, toolbox)
    agent.messages.append({"role": "user", "content": "старое"})
    original = client._stream

    def failing(**kw):
        if len(client.calls) >= 1:
            raise Boom()
        return original(**kw)

    client.beta.messages.stream = failing
    with pytest.raises(Boom):
        agent.ask("новое", out=io.StringIO())
    assert agent.messages == [{"role": "user", "content": "старое"}]
