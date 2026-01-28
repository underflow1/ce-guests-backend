# Инструкция по переносу данных

## Создать дамп для переноса

```bash
cd /path/to/ce-guests-back
source venv/bin/activate  # если используется venv
python3 scripts/transfer_data.py
```

Скрипт создаст файл `data_transfer_YYYYMMDD_HHMMSS.sql` с данными пользователей и записей.

## Восстановить данные

```bash
# 1. Применить миграции (если еще не применены)
alembic upgrade head

# 2. Восстановить данные
sqlite3 ce_guests.db < data_transfer_YYYYMMDD_HHMMSS.sql
```

Готово! Данные перенесены.
