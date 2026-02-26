# nailsBot — Telegram-бот записи (aiogram + SQLite)

Бот для мастера по маникюру: запись на свободные слоты, админ-панель, проверка подписки, напоминания за 24 часа.

## Установка

1) Установите Python **3.11+**

2) Установите зависимости:

```bash
python -m pip install -r requirements.txt
```

3) Создайте файл `.env` в корне проекта:

```env
BOT_TOKEN=123456:ABCDEF
ADMIN_ID=123456789

# Канал для обязательной подписки (требование)
CHANNEL_ID=
CHANNEL_LINK=

# Канал, куда бот будет публиковать расписание (отдельный канал)
SCHEDULE_CHANNEL_ID=

# Часовой пояс
TIMEZONE=Europe/Moscow

# Путь к SQLite
DB_PATH=./data/bot.db
```

Шаблон переменных без секретов: `env.example`

## Запуск

```bash
python bot.py
```

## Деплой на Railway.com (SQLite + напоминания)

Важно: **SQLite-файл должен лежать на постоянном диске**, иначе при редеплое/перезапуске база (и задачи напоминаний) пропадут.

### 1) Залей проект на GitHub

- Создай репозиторий
- Запушь текущую папку проекта

### 2) Создай проект в Railway

- Railway → **New Project** → **Deploy from GitHub repo**
- Выбери репозиторий

### 3) Start Command

В Railway (Settings/Deploy) укажи команду запуска:
- **`python bot.py`**

`Procfile` уже добавлен, но самый надёжный вариант — явно задать Start Command в UI.

### 4) Variables (переменные окружения)

Railway → Service → **Variables** → добавь:

- `BOT_TOKEN`
- `ADMIN_ID`
- `CHANNEL_ID`
- `CHANNEL_LINK`
- `SCHEDULE_CHANNEL_ID`
- `TIMEZONE` (пример: `Europe/Moscow`)
- `DB_PATH` (для Railway лучше так): **`/data/bot.db`**

### 5) Подключи Volume (постоянный диск) под SQLite

- Railway → Service → Storage/Volumes → **Add Volume**
- Mount path: **`/data`**

После этого `DB_PATH=/data/bot.db` будет сохраняться между перезапусками.

## Как продавать и хостить “на своём аккаунте” (много клиентов)

Самый простой способ с текущим SQLite:
- **1 клиент = 1 отдельный Railway service/project**
- у каждого клиента: свой `BOT_TOKEN`, свой `ADMIN_ID`, свои каналы, свой Volume `/data`

### Чеклист “добавить нового клиента” (на твоём Railway)

- Клиент создаёт бота у `@BotFather` → даёт тебе **BOT_TOKEN**
- Ты создаёшь (или клиент создаёт и даёт доступ) 1–2 канала:
  - канал подписки (для `CHANNEL_ID/CHANNEL_LINK`)
  - канал расписания (для `SCHEDULE_CHANNEL_ID`)
- Добавь бота **админом** в оба канала
- Railway: **Duplicate service/project** → проставь Variables конкретного клиента → подключи Volume `/data`

Обновления бота: меняешь код в GitHub → Railway сам задеплоит, база не потеряется (Volume).

## Первичная настройка (через админ-панель)

- Откройте у бота меню **Админ-панель**
- Добавьте рабочие дни и временные слоты

