# Запуск бота на Google Cloud (e2-micro) — работает без вашего ПК

Бот работает в режиме «по подписке Claude» через Claude Code на сервере.

## 1. Аккаунт Google Cloud
1. Откройте https://console.cloud.google.com и войдите через Google.
2. Примите условия и привяжите карту (**Billing**). Google требует карту даже для бесплатного тарифа; новым аккаунтам дают пробные кредиты.
3. Сразу настройте оповещение о расходах: **Billing → Budgets & alerts → Create budget**, сумма $1.

## 2. Создайте сервер
1. Меню ☰ → **Compute Engine → VM instances**. Если попросит, нажмите **Enable** (включить API) и подождите минуту.
2. **Create instance** и заполните:
   - **Name:** `bot`
   - **Region:** `us-central1` (или `us-west1`, `us-east1`). Бесплатно **только** в этих регионах.
   - **Machine type:** серия **E2**, тип **e2-micro**
   - **Boot disk → Change:** система **Debian 12**, тип диска **Standard persistent disk**, размер **30 GB**, затем **Select**. Тип «Balanced» не бесплатный.
3. **Create**. Через минуту сервер появится в списке с зелёной галочкой.

Бесплатный лимит: один e2-micro в указанных регионах, 30 ГБ стандартного диска. Условия и возможная плата за внешний IP-адрес могут меняться, поэтому проверьте https://cloud.google.com/free и следите за бюджетом.

## 3. Установка бота
1. В строке сервера нажмите **SSH**. Откроется окно с терминалом в браузере.
2. Вставьте команду (правой кнопкой → Paste) и нажмите Enter:
   ```
   curl -fsSL https://raw.githubusercontent.com/servicekingdom521-prog/claude/claude/stoic-fermi-14ecz8/deploy/setup.sh | bash
   ```
3. Подождите 5–10 минут, пока не появится надпись **«Готово»**.

## 4. Вход в Claude
```
~/.local/bin/claude
```
Выберите вход по подписке (**Claude account with subscription**). Появится ссылка: откройте её в браузере, войдите, скопируйте код и вставьте его в окно SSH. Когда Claude Code запустится, введите `/exit`.

## 5. Токен и ID
```
nano ~/bot/.env
```
Впишите значения:
```
TELEGRAM_BOT_TOKEN=ваш_токен
TELEGRAM_ALLOWED_USERS=ваш_ID
```
Сохраните: **Ctrl+O**, **Enter**, затем выйдите: **Ctrl+X**.

## 6. Запуск
⚠️ Сначала **остановите бота на ПК** (Ctrl+C в чёрном окне), иначе будет ошибка `Conflict`.
```
sudo systemctl restart telegram-bot
sudo systemctl status telegram-bot
```
Строка `active (running)` значит, что бот работает. Теперь ПК можно выключить: бот сам запускается после перезагрузки сервера и перезапускается при сбоях.

## Полезные команды
| Что | Команда |
|---|---|
| Журнал в реальном времени (выход: Ctrl+C) | `journalctl -u telegram-bot -f` |
| Перезапустить | `sudo systemctl restart telegram-bot` |
| Остановить | `sudo systemctl stop telegram-bot` |
| Обновить бота до новой версии | `curl -fsSL https://raw.githubusercontent.com/servicekingdom521-prog/claude/claude/stoic-fermi-14ecz8/deploy/setup.sh \| bash` и `sudo systemctl restart telegram-bot` |

## Ограничения
- На сервере 1 ГБ памяти, поэтому распознавание речи работает на модели `base`: быстрее, но чуть менее точно, чем `small` на ПК.
- Лимиты подписки Claude общие для бота, приложения Claude и Claude Code.
