@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist .venv\Scripts\activate.bat (
  echo Сначала запустите install.bat
  pause
  exit /b 1
)
call .venv\Scripts\activate.bat
echo Проверяю библиотеки...
pip install -q -r requirements.txt
python -m assistant.jarvis_web
pause
