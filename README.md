# CE Guests Backend

Backend API для системы управления записями гостей на основе FastAPI.

## Технологический стек

- **FastAPI** 0.104.1 - веб-фреймворк
- **SQLite** - база данных
- **SQLAlchemy** 2.0.23 - ORM
- **Alembic** 1.12.1 - миграции БД
- **Python 3.11+** - язык программирования
- **JWT** - аутентификация
- **WebSocket** - real-time обновления

## Установка и запуск

### 1. Клонирование репозитория

```bash
git clone https://github.com/underflow1/ce-guests-backend.git
cd ce-guests-backend
```

### 2. Создание виртуального окружения

```bash
python3 -m venv venv
source venv/bin/activate  # Linux/Mac
# или
venv\Scripts\activate  # Windows
```

### 3. Установка зависимостей

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Настройка переменных окружения

Создайте файл `.env` на основе `.env.example`:

```bash
cp .env.example .env
```

Отредактируйте `.env` и укажите необходимые значения:

```env
DATABASE_URL=sqlite:///./ce_guests.db
SECRET_KEY=your-secret-key-change-in-production
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=1440
CORS_ORIGINS=http://localhost:5173
TIMEZONE=Europe/Moscow
HOST=127.0.0.1
PORT=8000
```

### 5. Применение миграций

```bash
alembic upgrade head
```

### 6. Создание первого администратора (обязательно!)

**Важно:** После создания чистой БД необходимо создать первого администратора, иначе невозможно будет войти в систему и управлять ею.

```bash
python3 scripts/create_admin.py
```

Скрипт запросит имя пользователя и пароль интерактивно.

Или с параметрами:

```bash
python3 scripts/create_admin.py --username admin --password secret
```

**Примечание:** После создания первого админа вы сможете войти в систему и создавать других пользователей через API или веб-интерфейс.

### 7. Запуск сервера

**Рекомендуемый способ** (использует настройки из `.env`):

```bash
python3 run.py
```

Или напрямую через uvicorn:

```bash
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Сервер будет доступен по адресу: http://127.0.0.1:8000 (или указанному в `.env`)

**Документация API (Swagger):** http://localhost:8000/docs

## Структура проекта

```
ce-guests-back/
├── alembic/                 # Миграции Alembic
│   ├── versions/
│   └── env.py
├── app/
│   ├── __init__.py
│   ├── main.py              # Точка входа FastAPI
│   ├── config.py            # Конфигурация (переменные окружения)
│   ├── database.py          # Подключение к БД, сессии
│   ├── api/                 # API роуты
│   │   ├── __init__.py
│   │   ├── deps.py          # Общие зависимости (get_current_user и т.д.)
│   │   ├── ws.py            # WebSocket для real-time обновлений
│   │   └── v1/              # Версия API v1
│   │       ├── auth.py      # Авторизация
│   │       ├── entries.py   # Записи гостей
│   │       ├── users.py     # Управление пользователями
│   │       ├── roles.py     # Управление ролями и правами
│   │       └── utils.py     # Утилиты
│   ├── models/              # SQLAlchemy модели
│   │   ├── user.py
│   │   ├── entry.py
│   │   ├── role.py
│   │   ├── permission.py
│   │   └── role_permission.py
│   ├── schemas/             # Pydantic схемы для валидации
│   │   ├── auth.py
│   │   ├── user.py
│   │   ├── entry.py
│   │   ├── role.py
│   │   └── permission.py
│   └── services/            # Бизнес-логика
│       ├── auth.py          # JWT, проверка паролей
│       ├── entry_events.py  # WebSocket события для записей
│       └── workdays.py      # Логика определения рабочих дней
├── scripts/
│   └── create_admin.py      # Создание первого админа
├── alembic.ini
├── requirements.txt
├── install.sh               # Скрипт автоматической установки
├── run.py                   # Скрипт запуска сервера
├── .env.example
├── .gitignore
├── run.py                   # Скрипт запуска сервера
└── README.md
```

## API эндпоинты

Все роуты версионированы через `/api/v1/`

### Авторизация

- `POST /api/v1/auth/login` - логин (username/email + password → JWT access token)
- `GET /api/v1/auth/me` - получить текущего пользователя (требует авторизации)

### Записи (entries)

- `GET /api/v1/entries?today=YYYY-MM-DD` - получить записи за период (от сегодня + 8 дней)
- `POST /api/v1/entries` - создать запись (требует авторизации)
- `PUT /api/v1/entries/{entry_id}` - обновить запись (требует авторизации)
- `PATCH /api/v1/entries/{entry_id}/completed` - изменить статус выполнения (требует авторизации)
- `DELETE /api/v1/entries/{entry_id}` - удалить запись (требует авторизации, мягкое удаление)
- `GET /api/v1/responsible-autocomplete?q=query` - автодополнение ответственных

### Пользователи (только для админов)

- `GET /api/v1/users` - список пользователей (требует авторизации + is_admin)
- `GET /api/v1/users/{user_id}` - получить пользователя по ID
- `POST /api/v1/users` - создать пользователя (требует авторизации + is_admin)
- `PUT /api/v1/users/{user_id}` - обновить пользователя (требует авторизации + is_admin)
- `DELETE /api/v1/users/{user_id}` - деактивировать пользователя (требует авторизации + is_admin)

### Роли и права (только для админов)

- `GET /api/v1/roles` - список всех ролей
- `GET /api/v1/roles/{role_id}` - получить роль по ID
- `POST /api/v1/roles` - создать роль
- `PUT /api/v1/roles/{role_id}` - обновить роль
- `DELETE /api/v1/roles/{role_id}` - удалить роль
- `GET /api/v1/permissions` - список всех доступных прав

### Утилиты

- `GET /api/v1/utils/date-range` - получить диапазон дат для фронта (от сегодня + 8 дней)

### WebSocket

- `WS /ws` - WebSocket соединение для real-time обновлений записей (требует токен авторизации)

### Системные

- `GET /` - информация об API (требует авторизации)
- `GET /health` - проверка здоровья сервиса

## Система прав доступа

Приложение использует систему ролей и прав:

- **Администраторы** (`is_admin=1`) - полный доступ ко всем функциям
- **Пользователи с ролью** - доступ определяется правами роли
- **Права доступа**:
  - `can_view` - просмотр записей
  - `can_add` - создание записей
  - `can_edit_entry` - редактирование записей
  - `can_delete_entry` - удаление записей
  - `can_move_ui` - перемещение записей (UI)
  - `can_delete_ui` - удаление записей (UI)
  - `can_mark_completed` - отметка выполненным
  - `can_unmark_completed` - снятие отметки выполненным
  - и другие...

## Миграции

Создать новую миграцию:

```bash
alembic revision --autogenerate -m "Описание изменений"
```

Применить миграции:

```bash
alembic upgrade head
```

Откатить последнюю миграцию:

```bash
alembic downgrade -1
```

Проверить текущую версию:

```bash
alembic current
```

## Переменные окружения

- `DATABASE_URL` - путь к SQLite файлу (например, `sqlite:///./ce_guests.db`)
- `SECRET_KEY` - секретный ключ для JWT (обязательно изменить в продакшене!)
- `ALGORITHM` - алгоритм JWT (например, `HS256`)
- `ACCESS_TOKEN_EXPIRE_MINUTES` - время жизни токена (например, `1440` = 24 часа)
- `CORS_ORIGINS` - список разрешенных origins через запятую (например, `http://localhost:5173,http://localhost:3000`)
- `TIMEZONE` - часовой пояс (например, `Europe/Moscow`)
- `HOST` - хост для прослушивания (по умолчанию `127.0.0.1`)
- `PORT` - порт для прослушивания (по умолчанию `8000`)
- `AUTOCOMPLETE_LOOKUP_LIMIT` - лимит результатов автодополнения (по умолчанию `100`)

## Управление сервисом (systemd)

Если вы использовали автоматическую установку, сервис будет управляться через systemd:

```bash
# Проверить статус
sudo systemctl status ce-guests-back

# Запустить
sudo systemctl start ce-guests-back

# Остановить
sudo systemctl stop ce-guests-back

# Перезапустить
sudo systemctl restart ce-guests-back

# Просмотр логов
sudo journalctl -u ce-guests-back -f

# Отключить автозапуск
sudo systemctl disable ce-guests-back

# Включить автозапуск
sudo systemctl enable ce-guests-back
```

## Разработка

### Логирование

Все операции с записями (создание, обновление, удаление) и авторизация логируются в консоль.

### Форматы данных

- **UUID**: стандартный UUID v4, хранится как TEXT в БД
- **Datetime**: TEXT в формате ISO 8601 (YYYY-MM-DDTHH:MM:SS) - дата и время записи визита
- **Timestamp**: TEXT в формате ISO 8601 (YYYY-MM-DDTHH:MM:SS) - для created_at, updated_at

### Рабочие дни

Система использует API isdayoff.ru для определения рабочих дней. При недоступности API используется fallback на определение по дню недели (пн-пт = рабочий).

### WebSocket

WebSocket используется для real-time обновлений записей. При создании, обновлении или удалении записи все подключенные клиенты получают уведомление через WebSocket.

## Лицензия

[Указать лицензию если нужно]
