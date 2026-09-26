#!/usr/bin/env bash
# Установка Telegram-бота на сервер Debian/Ubuntu (например, Google Cloud e2-micro).
# Запуск:  curl -fsSL https://raw.githubusercontent.com/servicekingdom521-prog/claude/claude/stoic-fermi-14ecz8/deploy/setup.sh | bash
set -euo pipefail

REPO_URL="https://github.com/servicekingdom521-prog/claude.git"
BRANCH="claude/stoic-fermi-14ecz8"
APP_DIR="$HOME/bot"
SERVICE=telegram-bot

echo "==> 1/6 Файл подкачки 2 ГБ (на e2-micro всего 1 ГБ памяти)"
if ! swapon --show | grep -q /swapfile; then
  sudo fallocate -l 2G /swapfile
  sudo chmod 600 /swapfile
  sudo mkswap /swapfile >/dev/null
  sudo swapon /swapfile
  grep -q /swapfile /etc/fstab || echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab >/dev/null
fi

echo "==> 2/6 Системные пакеты"
sudo apt-get update -qq
sudo apt-get install -y -qq git python3-venv python3-pip curl >/dev/null

echo "==> 3/6 Код бота"
if [ -d "$APP_DIR/.git" ]; then
  git -C "$APP_DIR" pull --ff-only
else
  git clone --branch "$BRANCH" "$REPO_URL" "$APP_DIR"
fi
cd "$APP_DIR"

echo "==> 4/6 Библиотеки Python (несколько минут)"
python3 -m venv .venv
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q -r requirements.txt

if [ ! -f .env ]; then
  cat > .env <<'ENV'
ANTHROPIC_API_KEY=
GEMINI_API_KEY=

TELEGRAM_BOT_TOKEN=
TELEGRAM_ALLOWED_USERS=

TTS_VOICE=ru-RU-SvetlanaNeural
# На сервере с 1 ГБ памяти модель small не поместится — используем base
WHISPER_MODEL=base
ENV
fi

echo "==> 5/6 Claude Code"
if [ ! -x "$HOME/.local/bin/claude" ] && ! command -v claude >/dev/null; then
  curl -fsSL https://claude.ai/install.sh | bash
fi

echo "==> 6/6 Автозапуск (systemd)"
sudo tee /etc/systemd/system/$SERVICE.service >/dev/null <<UNIT
[Unit]
Description=Telegram voice assistant bot
After=network-online.target
Wants=network-online.target

[Service]
User=$USER
WorkingDirectory=$APP_DIR
Environment=HOME=$HOME
Environment=PATH=$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin
ExecStart=$APP_DIR/.venv/bin/python -m assistant.telegram_bot
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
UNIT
sudo systemctl daemon-reload
sudo systemctl enable $SERVICE >/dev/null

cat <<DONE

Готово. Осталось три шага:
  1) Войти в Claude:          ~/.local/bin/claude      (выберите вход по подписке, затем /exit)
  2) Вписать токен и ID:      nano $APP_DIR/.env       (Ctrl+O, Enter — сохранить; Ctrl+X — выйти)
  3) Запустить бота:          sudo systemctl restart $SERVICE

Проверить, что работает:      sudo systemctl status $SERVICE
Смотреть журнал:              journalctl -u $SERVICE -f
DONE
