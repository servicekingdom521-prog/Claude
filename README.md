# Универсальный ассистент на Claude

Консольный AI-агент для повседневных и бизнес-задач. Работает на Claude API (модель `claude-opus-5`).

## Что умеет

| Возможность | Инструмент |
|---|---|
| Поиск актуальной информации в интернете, чтение страниц | `web_search`, `web_fetch` (выполняются на серверах Anthropic) |
| Заметки, которые сохраняются между запусками | `save_note`, `search_notes` |
| Список задач со сроками и приоритетами | `add_task`, `list_tasks`, `complete_task` |
| Чтение и создание документов (отчёты, планы, КП, CSV) | `list_files`, `read_file`, `write_file` |
| Черновики деловых писем (не отправляет) | `save_email_draft` |
| Текущая дата для планирования | `get_current_datetime` |

Все данные хранятся локально в папке `data/`: `notes.json`, `tasks.json`, `workspace/` и `drafts/`. Доступ к файлам ограничен папкой `workspace/`.

## Запуск

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # впишите ANTHROPIC_API_KEY
python -m assistant
```

Ключ API можно получить на https://platform.claude.com/settings/keys.

Команды в чате: `/new` начинает новый диалог, `/exit` завершает работу.

## Telegram-бот с голосом

Бот работает у вас на компьютере, пока открыто окно с ним. Голосовые сообщения он распознаёт локально (Whisper), а отвечает голосом через бесплатный Microsoft Edge TTS. На текст отвечает текстом, на голосовое — текстом и голосом.

**Два режима работы:**
- **По подписке Claude, без API-ключа** (если `ANTHROPIC_API_KEY` пуст). Бот передаёт сообщения в Claude Code на этом компьютере. Нужен установленный Claude Code (`claude` в командной строке), в котором вы вошли в свой аккаунт. Расходуются лимиты подписки. Заметки и задачи хранятся в `data/notes.md` и `data/tasks.md`.
- **Через Claude API** (если `ANTHROPIC_API_KEY` заполнен). Оплата по факту использования, лимиты подписки не тратятся.

**Первый запуск (Windows):**

1. Установите Python 3.11+ с https://www.python.org/downloads/ и отметьте галочку **Add Python to PATH**.
2. Скачайте проект: зелёная кнопка **Code → Download ZIP** на GitHub, распакуйте.
3. Откройте папку проекта, в адресной строке проводника наберите `cmd` и нажмите Enter.
4. Выполните:
   ```bat
   python -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt
   copy .env.example .env
   notepad .env
   ```
5. В блокноте впишите `TELEGRAM_BOT_TOKEN` (и `ANTHROPIC_API_KEY`, если работаете через API), сохраните.
6. Запустите бота: `python -m assistant.telegram_bot`
7. Напишите боту в Telegram `/start`. Он ответит «Доступ закрыт» и покажет ваш ID.
8. Впишите этот ID в `TELEGRAM_ALLOWED_USERS` в `.env`, остановите бота (Ctrl+C) и запустите снова.

Готово: теперь бот отвечает только вам. Первое голосовое обработается дольше обычного, потому что скачивается модель распознавания (~500 МБ, один раз).

**macOS / Linux:** то же самое, но `source .venv/bin/activate`, `cp .env.example .env` и `nano .env`.

**Дальнейшие запуски:** открыть папку → `cmd` → `.venv\Scripts\activate` → `python -m assistant.telegram_bot`.

Команды бота: `/start` — приветствие, `/new` — новый диалог. Голос меняется в `.env` (`TTS_VOICE`).

## Примеры запросов

- «Найди трёх главных конкурентов для кофейни в Киеве и сохрани сравнение в файл»
- «Запомни: встреча с поставщиком в пятницу, обсудить скидку 10%»
- «Какие у меня задачи? Отметь первую выполненной»
- «Напиши клиенту письмо с напоминанием об оплате счёта №45»
- «Составь бизнес-план на месяц и разбей его на задачи»

## Как устроено

- `assistant/main.py`: агентный цикл. Потоковый вывод, adaptive thinking, кэширование промпта, автоматический переход на запасную модель при отказе (`fallbacks: "default"`), обработка `pause_turn` и ошибок API.
- `assistant/telegram_bot.py`, `assistant/voice.py`: Telegram-бот, распознавание речи и озвучка.
- `assistant/claude_code_backend.py`: режим «по подписке» — ответы через `claude -p` с продолжением диалога (`--resume`).
- `assistant/tools.py`: описания и реализация локальных инструментов. Новый инструмент добавляется двумя шагами: метод в `Toolbox` и схема в `LOCAL_TOOLS`.

## Тесты

```bash
pip install pytest
python -m pytest
```
