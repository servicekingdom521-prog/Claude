"""Универсальный ассистент для повседневных и бизнес-задач на базе Claude."""

from pathlib import Path

from dotenv import load_dotenv

# Загружаем .env до того, как модули прочитают настройки (голос, модель, обращение):
# сначала из папки проекта, затем из текущей папки.
load_dotenv(Path(__file__).resolve().parent.parent / ".env")
load_dotenv(Path.cwd() / ".env")
