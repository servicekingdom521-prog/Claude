@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Установка Telegram-бота
echo ============================================
echo   Установка Telegram-бота с голосом
echo ============================================
echo.

rem --- 1. Python ---
python --version >nul 2>&1
if errorlevel 1 (
  echo [1/5] Python не найден. Устанавливаю...
  winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements
  echo.
  echo Python установлен. ЗАКРОЙТЕ это окно и снова запустите install.bat
  pause
  exit /b 0
)
echo [1/5] Python найден.

rem --- 2. Claude Code ---
set "CLAUDE_EXE=%USERPROFILE%\.local\bin\claude.exe"
where claude >nul 2>&1
if errorlevel 1 if not exist "%CLAUDE_EXE%" (
  echo [2/5] Устанавливаю Claude Code...
  powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://claude.ai/install.ps1 | iex"
)
if not exist "%CLAUDE_EXE%" set "CLAUDE_EXE=claude"
echo [2/5] Claude Code готов.
echo.
choice /c YN /m "Войти в аккаунт Claude сейчас? (нужно при первой установке)"
if errorlevel 2 goto skip_login
echo.
echo Откроется Claude. Выберите вход по подписке, войдите в браузере,
echo затем введите /exit и нажмите Enter, чтобы продолжить установку.
echo.
"%CLAUDE_EXE%"
:skip_login

rem --- 3. Библиотеки ---
echo.
echo [3/5] Устанавливаю библиотеки (несколько минут)...
if not exist .venv\Scripts\activate.bat python -m venv .venv
call .venv\Scripts\activate.bat
python -m pip install -q --upgrade pip
pip install -q -r requirements.txt
if errorlevel 1 (
  echo Ошибка установки библиотек. Сделайте скриншот этого окна.
  pause
  exit /b 1
)
echo [3/5] Библиотеки установлены.

rem --- 4. Настройки ---
if not exist .env (
  copy .env.example .env >nul
  echo.
  echo [4/5] Сейчас откроется блокнот. Впишите TELEGRAM_BOT_TOKEN и TELEGRAM_ALLOWED_USERS,
  echo       сохраните Ctrl+S и закройте блокнот.
  notepad .env
) else (
  echo [4/5] Файл .env уже есть.
)

rem --- 5. Автозапуск ---
echo.
choice /c YN /m "Запускать бота автоматически при включении компьютера?"
if errorlevel 2 goto start
powershell -NoProfile -Command "$s=(New-Object -ComObject WScript.Shell).CreateShortcut([Environment]::GetFolderPath('Startup')+'\Telegram-bot.lnk'); $s.TargetPath='%~dp0start-bot.bat'; $s.WorkingDirectory='%~dp0'; $s.Save()"
echo [5/5] Автозапуск включён.

:start
echo.
echo Готово! Запускаю бота...
start "Telegram-бот" "%~dp0start-bot.bat"
timeout /t 3 >nul
