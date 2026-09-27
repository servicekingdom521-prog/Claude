@echo off
chcp 65001 >nul
cd /d "%~dp0"
start "Telegram-bot" "%~dp0start-bot.bat"
start "Jarvis" "%~dp0jarvis.bat"
