"""Ассистент на Google Gemini API — бесплатный тариф, ключ на aistudio.google.com.

Использует те же локальные инструменты, что и Claude-версия (заметки, задачи,
файлы, черновики писем), плюс поиск в Google через отдельный запрос с grounding.
"""

import copy
import os

from google import genai
from google.genai import errors, types

from assistant.persona import PERSONA
from assistant.tools import LOCAL_TOOLS, Toolbox, ToolError

GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-flash-latest")
MAX_TOOL_ROUNDS = 15

SYSTEM_PROMPT = PERSONA + """Ты помогаешь пользователю с повседневными и бизнес-задачами. Пользователь часто общается голосом через Telegram, поэтому отвечай разговорно, по делу и без таблиц; развёрнутые материалы сохраняй в файлы через write_file.

Ты умеешь: искать актуальную информацию (web_search), вести заметки и задачи (они сохраняются между сессиями), читать и создавать документы, писать черновики деловых писем (сам ты их не отправляешь), помогать с планированием и идеями для бизнеса.

Для сроков и относительных дат сначала вызови get_current_datetime. Если просят «запомнить» или «записать» — сохрани заметку или задачу. Отвечай на языке пользователя.
"""

WEB_SEARCH_DECLARATION = {
    "name": "web_search",
    "description": "Найти актуальную информацию в интернете через Google: новости, цены, факты, контакты компаний, курсы валют, погоду.",
    "input_schema": {
        "type": "object",
        "properties": {"query": {"type": "string", "description": "Поисковый запрос"}},
        "required": ["query"],
    },
}


class GeminiError(Exception):
    pass


def _strip_additional_properties(schema):
    # Gemini принимает подмножество JSON Schema — убираем то, что ему не нужно.
    schema = copy.deepcopy(schema)
    schema.pop("additionalProperties", None)
    for prop in schema.get("properties", {}).values():
        prop.pop("additionalProperties", None)
    return schema


def build_function_declarations() -> list[types.FunctionDeclaration]:
    return [
        types.FunctionDeclaration(
            name=tool["name"],
            description=tool["description"],
            parameters_json_schema=_strip_additional_properties(tool["input_schema"]),
        )
        for tool in [WEB_SEARCH_DECLARATION, *LOCAL_TOOLS]
    ]


class GeminiAssistant:
    def __init__(self, client: genai.Client, toolbox: Toolbox, model: str = GEMINI_MODEL):
        self.client = client
        self.toolbox = toolbox
        self.model = model
        self.config = types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            tools=[types.Tool(function_declarations=build_function_declarations())],
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        )
        self.reset()

    def reset(self) -> None:
        self.chat = self.client.chats.create(model=self.model, config=self.config)

    def web_search(self, query: str) -> str:
        response = self.client.models.generate_content(
            model=self.model,
            contents=query,
            config=types.GenerateContentConfig(tools=[types.Tool(google_search=types.GoogleSearch())]),
        )
        text = response.text or "Ничего не найдено."
        sources = []
        for candidate in response.candidates or []:
            metadata = candidate.grounding_metadata
            for chunk in (metadata.grounding_chunks or []) if metadata else []:
                if chunk.web and chunk.web.uri:
                    sources.append(f"- {chunk.web.title or ''} {chunk.web.uri}".strip())
        if sources:
            text += "\n\nИсточники:\n" + "\n".join(sources[:5])
        return text

    def _run_tool(self, call: types.FunctionCall) -> dict:
        args = dict(call.args or {})
        try:
            if call.name == "web_search":
                return {"result": self.web_search(**args)}
            return {"result": self.toolbox.run(call.name, args)}
        except ToolError as e:
            return {"error": str(e)}
        except TypeError as e:
            return {"error": f"Неверные аргументы: {e}"}

    def ask(self, user_text: str, out=None) -> str:
        history = self.chat.get_history()
        try:
            return self._run_turn(user_text)
        except Exception:
            # Откатываем незавершённый ход, чтобы следующий запрос не сломался.
            self.chat = self.client.chats.create(model=self.model, config=self.config, history=history)
            raise

    def _run_turn(self, user_text: str) -> str:
        try:
            response = self.chat.send_message(user_text)
            for _ in range(MAX_TOOL_ROUNDS):
                calls = response.function_calls
                if not calls:
                    return response.text or ""
                parts = [
                    types.Part.from_function_response(name=call.name, response=self._run_tool(call))
                    for call in calls
                ]
                response = self.chat.send_message(parts)
            return (response.text or "") + "\n[Остановлено: слишком много шагов подряд.]"
        except errors.APIError as e:
            if e.code == 429:
                raise GeminiError("Лимит бесплатного тарифа Gemini исчерпан — попробуйте позже.") from e
            if e.code in (400, 401, 403) and "API key" in (e.message or ""):
                raise GeminiError("Неверный GEMINI_API_KEY в файле .env.") from e
            raise GeminiError(f"Ошибка Gemini {e.code}: {e.message}") from e
