from types import SimpleNamespace

import pytest

pytest.importorskip("google.genai")

from google.genai import errors, types  # noqa: E402

from assistant.gemini_backend import GeminiAssistant, GeminiError, build_function_declarations  # noqa: E402
from assistant.tools import LOCAL_TOOLS, Toolbox  # noqa: E402


def reply(text=None, calls=None):
    return SimpleNamespace(text=text, function_calls=calls or None)


def call(name, **args):
    return types.FunctionCall(name=name, args=args)


class FakeChat:
    def __init__(self, script, history):
        self.script = script
        self.history = history
        self.sent = []

    def get_history(self):
        return list(self.history)

    def send_message(self, message):
        self.sent.append(message)
        step = self.script.pop(0)
        if isinstance(step, Exception):
            raise step
        self.history.append(message)
        return step


class FakeClient:
    def __init__(self, script, search_text="Курс 41.5"):
        self.script = script
        self.chats_created = []
        self.search_queries = []
        self.chats = SimpleNamespace(create=self._create)
        self.models = SimpleNamespace(generate_content=self._search)
        self.search_text = search_text

    def _create(self, model, config, history=None):
        chat = FakeChat(self.script, list(history or []))
        self.chats_created.append(chat)
        return chat

    def _search(self, model, contents, config):
        self.search_queries.append(contents)
        return SimpleNamespace(text=self.search_text, candidates=[])


def test_declarations_cover_all_tools_without_additional_properties():
    decls = build_function_declarations()
    assert {d.name for d in decls} == {"web_search", *(t["name"] for t in LOCAL_TOOLS)}
    assert all("additionalProperties" not in (d.parameters_json_schema or {}) for d in decls)


def test_tool_loop_runs_local_tools_and_search(tmp_path):
    client = FakeClient([
        reply(calls=[call("add_task", title="Позвонить"), call("web_search", query="курс доллара")]),
        reply(calls=[call("complete_task", task_id=99)]),
        reply(text="Готово"),
    ])
    toolbox = Toolbox(tmp_path)
    agent = GeminiAssistant(client, toolbox)

    assert agent.ask("сделай") == "Готово"
    assert "Позвонить" in toolbox.run("list_tasks", {})
    assert client.search_queries == ["курс доллара"]
    chat = client.chats_created[-1]
    first = [p.function_response for p in chat.sent[1]]
    assert first[0].response == {"result": "Задача #1 «Позвонить» добавлена."}
    assert first[1].response == {"result": "Курс 41.5"}
    assert "error" in chat.sent[2][0].function_response.response


def test_rate_limit_is_explained_and_history_rolled_back(tmp_path):
    rate_limited = errors.ClientError(429, {"error": {"code": 429, "message": "quota", "status": "RESOURCE_EXHAUSTED"}})
    client = FakeClient([
        reply(text="привет"),
        reply(calls=[call("list_tasks")]),
        rate_limited,
    ])
    agent = GeminiAssistant(client, Toolbox(tmp_path))
    agent.ask("привет")
    history_before = agent.chat.get_history()

    with pytest.raises(GeminiError, match="Лимит"):
        agent.ask("задачи?")
    assert agent.chat.get_history() == history_before


def test_reset_starts_new_chat(tmp_path):
    client = FakeClient([])
    agent = GeminiAssistant(client, Toolbox(tmp_path))
    agent.reset()
    assert len(client.chats_created) == 2
