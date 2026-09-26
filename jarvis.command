#!/bin/bash
# Запуск Джарвиса на macOS: двойной щелчок
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then
  echo "Сначала запустите install.command"
  read -n 1 -s -r -p "Нажмите любую клавишу…"; exit 1
fi
.venv/bin/pip install -q -r requirements.txt
.venv/bin/python -m assistant.jarvis_web
