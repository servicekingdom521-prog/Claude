"""Telegram-бот с голосом: python -m assistant.telegram_bot"""

import asyncio
import io
import logging
import os
import tempfile
from pathlib import Path
from typing import Callable

import anthropic
from dotenv import load_dotenv
from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from assistant import voice
from assistant.claude_code_backend import ClaudeCodeAssistant, ClaudeCodeError
from assistant.main import Assistant
from assistant.tools import Toolbox

log = logging.getLogger("assistant.bot")
TELEGRAM_LIMIT = 4000


def parse_allowed_users(raw: str) -> set[int]:
    return {int(x) for x in raw.replace(" ", "").split(",") if x}


def split_message(text: str, limit: int = TELEGRAM_LIMIT) -> list[str]:
    chunks = []
    while len(text) > limit:
        cut = text.rfind("\n", 0, limit)
        if cut <= 0:
            cut = limit
        chunks.append(text[:cut])
        text = text[cut:].lstrip("\n")
    if text:
        chunks.append(text)
    return chunks


class Bot:
    def __init__(self, allowed_users: set[int], make_assistant: Callable[[int], object]):
        self.allowed_users = allowed_users
        self.make_assistant = make_assistant
        self.assistants: dict[int, object] = {}
        self.locks: dict[int, asyncio.Lock] = {}

    def _assistant(self, chat_id: int):
        if chat_id not in self.assistants:
            self.assistants[chat_id] = self.make_assistant(chat_id)
            self.locks[chat_id] = asyncio.Lock()
        return self.assistants[chat_id]

    async def _check_access(self, update: Update) -> bool:
        user = update.effective_user
        if user and user.id in self.allowed_users:
            return True
        uid = user.id if user else "неизвестен"
        await update.effective_message.reply_text(
            f"Доступ закрыт. Ваш Telegram ID: {uid}\n"
            "Если это ваш бот — впишите этот ID в TELEGRAM_ALLOWED_USERS в файле .env и перезапустите бота."
        )
        log.warning("Отклонён пользователь %s", uid)
        return False

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._check_access(update):
            return
        await update.effective_message.reply_text(
            "Привет! Я ваш ассистент. Пишите или отправляйте голосовые — на голосовые отвечу голосом.\n"
            "Умею искать в интернете, вести заметки и задачи, писать письма и документы.\n"
            "/new — начать новый диалог"
        )

    async def new_dialog(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._check_access(update):
            return
        self._assistant(update.effective_chat.id).reset()
        await update.effective_message.reply_text("Начат новый диалог.")

    async def on_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._check_access(update):
            return
        await self._answer(update, context, update.effective_message.text, speak=False)

    async def on_voice(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._check_access(update):
            return
        msg = update.effective_message
        media = msg.voice or msg.audio
        await context.bot.send_chat_action(msg.chat_id, ChatAction.TYPING)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "input.ogg"
            tg_file = await media.get_file()
            await tg_file.download_to_drive(path)
            text = await asyncio.to_thread(voice.transcribe, path)
        if not text:
            await msg.reply_text("Не расслышал, повторите, пожалуйста.")
            return
        await msg.reply_text(f"🎙 {text}")
        await self._answer(update, context, text, speak=True)

    async def _answer(self, update: Update, context: ContextTypes.DEFAULT_TYPE, text: str, speak: bool) -> None:
        msg = update.effective_message
        assistant = self._assistant(msg.chat_id)
        async with self.locks[msg.chat_id]:
            typing = asyncio.create_task(self._keep_typing(context, msg.chat_id))
            try:
                reply = await asyncio.to_thread(assistant.ask, text, io.StringIO())
            except ClaudeCodeError as e:
                reply = f"Ошибка: {e}"
            except anthropic.AuthenticationError:
                reply = "Ошибка: неверный ANTHROPIC_API_KEY в файле .env."
            except anthropic.RateLimitError:
                reply = "Слишком много запросов — подождите минуту и повторите."
            except anthropic.APIConnectionError:
                reply = "Нет соединения с Claude API — проверьте интернет."
            except anthropic.APIStatusError as e:
                reply = f"Ошибка API {e.status_code}: {e.message}"
            except Exception as e:
                log.exception("Сбой при ответе")
                reply = f"Не получилось ответить: {e}"
            finally:
                typing.cancel()

        reply = reply.strip() or "Готово."
        for chunk in split_message(reply):
            await msg.reply_text(chunk)

        if speak:
            await context.bot.send_chat_action(msg.chat_id, ChatAction.RECORD_VOICE)
            with tempfile.TemporaryDirectory() as tmp:
                audio = Path(tmp) / "reply.mp3"
                try:
                    if await voice.synthesize(reply, audio):
                        with audio.open("rb") as f:
                            await msg.reply_voice(f)
                except Exception:
                    log.exception("Не удалось озвучить ответ")
                    await msg.reply_text("(Озвучка не удалась — ответ выше текстом.)")

    @staticmethod
    async def _keep_typing(context: ContextTypes.DEFAULT_TYPE, chat_id: int) -> None:
        while True:
            await context.bot.send_chat_action(chat_id, ChatAction.TYPING)
            await asyncio.sleep(4)


def main() -> None:
    load_dotenv()
    logging.basicConfig(format="%(asctime)s %(levelname)s %(message)s", level=logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)

    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise SystemExit("Не задан TELEGRAM_BOT_TOKEN в файле .env")
    allowed = parse_allowed_users(os.environ.get("TELEGRAM_ALLOWED_USERS", ""))
    if not allowed:
        log.warning("TELEGRAM_ALLOWED_USERS пуст — бот никому не ответит, но сообщит ваш ID. Напишите ему /start.")

    data_dir = Path(os.environ.get("ASSISTANT_DATA_DIR", "data"))
    backend = os.environ.get("ASSISTANT_BACKEND") or ("api" if os.environ.get("ANTHROPIC_API_KEY") else "claude-code")
    if backend == "api":
        client, toolbox = anthropic.Anthropic(), Toolbox(data_dir)
        make_assistant = lambda chat_id: Assistant(client, toolbox)  # noqa: E731
        log.info("Режим: Claude API")
    else:
        make_assistant = lambda chat_id: ClaudeCodeAssistant(data_dir, chat_key=str(chat_id))  # noqa: E731
        make_assistant(0)  # сразу проверить, что Claude Code установлен
        log.info("Режим: Claude Code по подписке (без API-ключа)")
    bot = Bot(allowed, make_assistant)

    app = Application.builder().token(token).concurrent_updates(True).build()
    app.add_handler(CommandHandler("start", bot.start))
    app.add_handler(CommandHandler("new", bot.new_dialog))
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, bot.on_voice))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, bot.on_text))

    log.info("Бот запущен. Остановить: Ctrl+C")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
