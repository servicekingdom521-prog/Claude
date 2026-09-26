@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist .venv\Scripts\activate.bat (
  echo Сначала выполните установку из README: python -m venv .venv и pip install -r requirements.txt
  pause
  exit /b 1
)
call .venv\Scripts\activate.bat
:loop
python -m assistant.telegram_bot
echo Бот остановился. Перезапуск через 10 секунд, закройте окно, чтобы выключить.
timeout /t 10 >nul
goto loop
