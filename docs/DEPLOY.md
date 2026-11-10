# Развёртывание и эксплуатация Saul Goodman ⚖️

## 1. Docker (быстрый старт)

```bash
git clone https://github.com/AzizIo/saul-goodman-bot.git
cd saul-goodman-bot
cp .env.example .env
nano .env                     # BOT_TOKEN, ADMIN_ID, CHANNEL_ID
docker compose up -d --build
docker compose logs -f
```

База и QR-файлы лежат в именованном томе `saul-data` — переживают
`docker compose down` и пересборку образа. Служебные команды:

```bash
docker compose restart
docker compose down
docker compose exec bot python -c "print('alive')"

# бэкап тома с базой
docker compose exec bot python - <<'PY'
import sqlite3
with sqlite3.connect('/app/data/saul.db') as s, sqlite3.connect('/app/data/backup.db') as d:
    s.backup(d)
PY
docker compose cp bot:/app/data/backup.db ./saul-backup.db
```

Права: контейнер работает под непривилегированным пользователем `saul`
(uid 10001). Если монтируете каталог с хоста вместо тома — заранее выполните
`chown -R 10001:10001 ./data`.

## 2. systemd на Ubuntu

```bash
sudo adduser --system --group --home /opt/saul-goodman-bot saul
sudo -u saul git clone https://github.com/AzizIo/saul-goodman-bot.git /opt/saul-goodman-bot
cd /opt/saul-goodman-bot

sudo -u saul python3 -m venv .venv
sudo -u saul .venv/bin/pip install -r requirements.txt

sudo -u saul cp .env.example .env
sudo -u saul nano .env
sudo chmod 600 .env

sudo cp deploy/saul-goodman-bot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now saul-goodman-bot
sudo journalctl -u saul-goodman-bot -f
```

Автоперезапуск при сбое — `Restart=always`, `RestartSec=5`.
Логи — `journalctl -u saul-goodman-bot -f`.
Юнит ограничивает запись каталогом `data/` (`ProtectSystem=strict`).

## 3. Бэкапы

```bash
sudo crontab -u saul -e
# 0 3 * * * /opt/saul-goodman-bot/deploy/backup.sh
```

Скрипт делает консистентный снимок через `.backup`/`sqlite3.backup()`
и чистит копии старше 14 дней (`KEEP_DAYS`).

## 4. Гигиена секретов

- `.env` в `.gitignore`; в репозитории только `.env.example`.
- Соединение с Telegram — HTTPS, токен нигде не логируется.
- Персональные данные в логах не пишутся: только ID и технические события.
- QR/eSIM — потенциальный секрет активации. По умолчанию файлы **не**
  скачиваются на диск: бот работает с `file_id` Telegram и через
  `QR_RETENTION_DAYS` (по умолчанию 7 дней) обнуляет его в БД.
  `QR_STORE_FILES=true` включайте только если реально нужен архив файлов —
  тогда закройте права на `data/qr` и определите срок хранения.

## 5. Проверка после запуска

1. `/start` под не-админом → заявка уходит админу с `/approve_ID`.
2. `/approve_ID` → у пользователя появляется меню.
3. «⚖️ Начать сделку» → оператор → фото с номером → заказ `pending`.
4. `/progress_ID` → `/ok_ID` → баланс вырос ровно один раз.
5. `/ok_ID` повторно → «уже завершён», денег не прибавилось.
6. «💳 Вывести» → адрес → `/yes_ID` → списание ровно суммы заявки.
7. `/yes_ID` повторно → повторного списания нет.

## 6. Обновление

```bash
# Docker
docker compose up -d --build

# systemd
cd /opt/saul-goodman-bot && sudo -u saul git pull
sudo -u saul .venv/bin/pip install -r requirements.txt
sudo systemctl restart saul-goodman-bot
```