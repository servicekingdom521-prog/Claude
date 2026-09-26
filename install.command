#!/bin/bash
# Установка ассистента на macOS: двойной щелчок (или bash install.command в Терминале)
set -e
cd "$(dirname "$0")"
echo "=== Установка Джарвиса и Telegram-бота ==="

if ! command -v python3 >/dev/null || ! python3 -c 'import sys; sys.exit(sys.version_info < (3, 11))'; then
  echo "Нужен Python 3.11+. Скачайте его с https://www.python.org/downloads/macos/ , установите и запустите этот файл снова."
  open "https://www.python.org/downloads/macos/"
  read -n 1 -s -r -p "Нажмите любую клавишу, чтобы закрыть…"; exit 1
fi
echo "[1/4] Python: $(python3 --version)"

if ! command -v claude >/dev/null && [ ! -x "$HOME/.local/bin/claude" ]; then
  echo "[2/4] Устанавливаю Claude Code…"
  curl -fsSL https://claude.ai/install.sh | bash
fi
CLAUDE="$(command -v claude || echo "$HOME/.local/bin/claude")"
echo "[2/4] Claude Code готов."
read -r -p "Войти в аккаунт Claude сейчас? Нужно при первой установке [y/N] " ans
if [[ "$ans" =~ ^[YyДд] ]]; then
  echo "Выберите вход по подписке, войдите в браузере, затем введите /exit"
  "$CLAUDE" || true
fi

echo "[3/4] Устанавливаю библиотеки (несколько минут)…"
[ -d .venv ] || python3 -m venv .venv
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q -r requirements.txt

if [ ! -f .env ]; then
  cp .env.example .env
  echo "[4/4] Откроется файл .env. Для Telegram-бота впишите токен и ID, сохраните (Cmd+S) и закройте."
  open -e .env
else
  echo "[4/4] Файл .env уже есть."
fi
chmod +x jarvis.command 2>/dev/null || true
echo
echo "Готово! Джарвис запускается двойным щелчком по jarvis.command"
