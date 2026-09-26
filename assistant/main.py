"""Консольный чат с ассистентом: python -m assistant"""

import os
import sys
from pathlib import Path

import anthropic
from dotenv import load_dotenv

from assistant.tools import ALL_TOOLS, Toolbox, ToolError

SYSTEM_PROMPT = """Ты — личный ассистент пользователя для повседневных и бизнес-задач.

Что ты умеешь:
- отвечать на вопросы и искать актуальную информацию в интернете (web_search, web_fetch) — при поиске указывай источники;
- вести заметки и список задач пользователя — они сохраняются между сессиями;
- читать и создавать файлы в рабочей папке: отчёты, планы, коммерческие предложения, тексты, CSV;
- писать деловые письма и сохранять их черновиками (сам ты письма не отправляешь);
- помогать с планированием, анализом, расчётами и идеями для бизнеса.

Как работать:
- Отвечай на языке пользователя, по делу и без воды.
- Для сроков и относительных дат сначала узнай текущую дату через get_current_datetime.
- Если пользователь просит «запомнить» или «записать» — сохрани заметку или задачу.
- Длинные документы сохраняй в файл и коротко пересказывай содержание в ответе.
- Если запрос неоднозначен и ошибка дорого обойдётся — задай один уточняющий вопрос.
"""

MODEL = os.environ.get("ASSISTANT_MODEL", "claude-opus-5")
MAX_TOOL_ROUNDS = 25


class Assistant:
    def __init__(self, client: anthropic.Anthropic, toolbox: Toolbox, model: str = MODEL):
        self.client = client
        self.toolbox = toolbox
        self.model = model
        self.messages: list[dict] = []

    def _request(self):
        return self.client.beta.messages.stream(
            model=self.model,
            max_tokens=64000,
            system=SYSTEM_PROMPT,
            tools=ALL_TOOLS,
            messages=self.messages,
            thinking={"type": "adaptive"},
            cache_control={"type": "ephemeral"},
            # При отказе классификатора запрос автоматически повторится на запасной модели.
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )

    def ask(self, user_text: str, out=sys.stdout) -> str:
        """Отправить сообщение, выполнить все нужные инструменты и вернуть итоговый текст."""
        checkpoint = len(self.messages)
        try:
            return self._run_turn(user_text, out)
        except Exception:
            # Откатываем незавершённый ход, чтобы история осталась корректной.
            del self.messages[checkpoint:]
            raise

    def _run_turn(self, user_text: str, out) -> str:
        self.messages.append({"role": "user", "content": user_text})
        final_text = ""

        for _ in range(MAX_TOOL_ROUNDS):
            with self._request() as stream:
                for text in stream.text_stream:
                    out.write(text)
                    out.flush()
                response = stream.get_final_message()

            # Сохраняем весь content (включая thinking-блоки), а не только текст.
            self.messages.append({"role": "assistant", "content": response.content})
            final_text = "".join(b.text for b in response.content if b.type == "text")

            if response.stop_reason == "refusal":
                out.write("\n[Запрос отклонён по соображениям безопасности.]\n")
                return final_text
            if response.stop_reason == "max_tokens":
                out.write("\n[Ответ обрезан: достигнут лимит длины.]\n")
                return final_text
            if response.stop_reason == "pause_turn":
                # Серверный инструмент (поиск) взял паузу — просто продолжаем.
                continue
            if response.stop_reason != "tool_use":
                return final_text

            results = []
            for block in response.content:
                if block.type != "tool_use":
                    continue
                out.write(f"\n  ⚙ {block.name}\n")
                try:
                    content, is_error = self.toolbox.run(block.name, block.input), False
                except ToolError as e:
                    content, is_error = str(e), True
                results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": content,
                    "is_error": is_error,
                })
            # Все результаты — одним сообщением.
            self.messages.append({"role": "user", "content": results})

        out.write("\n[Остановлено: слишком много шагов подряд.]\n")
        return final_text


def main() -> None:
    load_dotenv()
    data_dir = Path(os.environ.get("ASSISTANT_DATA_DIR", "data"))
    assistant = Assistant(anthropic.Anthropic(), Toolbox(data_dir))

    print(f"Ассистент готов (модель {assistant.model}, данные в {data_dir.resolve()}).")
    print("Пишите запрос. Команды: /new — новый диалог, /exit — выход.\n")
    while True:
        try:
            user_text = input("Вы: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not user_text:
            continue
        if user_text in ("/exit", "/quit"):
            break
        if user_text == "/new":
            assistant.messages.clear()
            print("Начат новый диалог.\n")
            continue

        print("\nАссистент: ", end="")
        try:
            assistant.ask(user_text)
        except anthropic.AuthenticationError:
            print("\n[Неверный или отсутствующий ANTHROPIC_API_KEY — проверьте файл .env]")
        except anthropic.RateLimitError:
            print("\n[Превышен лимит запросов — подождите немного и повторите.]")
        except anthropic.APIStatusError as e:
            print(f"\n[Ошибка API {e.status_code}: {e.message}]")
        except anthropic.APIConnectionError:
            print("\n[Нет соединения с API — проверьте интернет.]")
        print("\n")
