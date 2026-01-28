#!/usr/bin/env python3
"""
Скрипт для переноса данных (users и entries) между хостами
Использование:
    python3 scripts/transfer_data.py [output_file.sql]
    
Если output_file не указан, создастся файл data_dump_YYYYMMDD_HHMMSS.sql
"""
import sys
import os
from datetime import datetime
from pathlib import Path

# Добавляем корневую директорию в путь
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.database import SessionLocal
from app.models.user import User
from app.models.entry import Entry


def escape_sql_string(value):
    """Экранирование строк для SQL"""
    if value is None:
        return 'NULL'
    # Заменяем одинарные кавычки на двойные для SQL
    return "'" + str(value).replace("'", "''") + "'"


def dump_users(db):
    """Дамп пользователей"""
    users = db.query(User).order_by(User.created_at).all()
    
    if not users:
        return "-- Нет пользователей для дампа\n"
    
    sql = "-- Дамп пользователей\n"
    sql += f"-- Всего пользователей: {len(users)}\n\n"
    
    for user in users:
        sql += f"INSERT OR IGNORE INTO users (id, username, email, full_name, password_hash, is_admin, is_active, role_id, created_at) VALUES (\n"
        sql += f"  {escape_sql_string(user.id)},\n"
        sql += f"  {escape_sql_string(user.username)},\n"
        sql += f"  {escape_sql_string(user.email)},\n"
        sql += f"  {escape_sql_string(user.full_name)},\n"
        sql += f"  {escape_sql_string(user.password_hash)},\n"
        sql += f"  {user.is_admin},\n"
        sql += f"  {user.is_active},\n"
        sql += f"  {escape_sql_string(user.role_id)},\n"
        sql += f"  {escape_sql_string(user.created_at)}\n"
        sql += ");\n\n"
    
    return sql


def dump_entries(db):
    """Дамп записей"""
    entries = db.query(Entry).order_by(Entry.created_at).all()
    
    if not entries:
        return "-- Нет записей для дампа\n"
    
    sql = "-- Дамп записей (entries)\n"
    sql += f"-- Всего записей: {len(entries)}\n\n"
    
    for entry in entries:
        sql += f"INSERT OR IGNORE INTO entries (id, name, responsible, datetime, created_by, created_at, updated_at, updated_by, deleted_at, deleted_by, is_completed) VALUES (\n"
        sql += f"  {escape_sql_string(entry.id)},\n"
        sql += f"  {escape_sql_string(entry.name)},\n"
        sql += f"  {escape_sql_string(entry.responsible)},\n"
        sql += f"  {escape_sql_string(entry.datetime)},\n"
        sql += f"  {escape_sql_string(entry.created_by)},\n"
        sql += f"  {escape_sql_string(entry.created_at)},\n"
        sql += f"  {escape_sql_string(entry.updated_at)},\n"
        sql += f"  {escape_sql_string(entry.updated_by)},\n"
        sql += f"  {escape_sql_string(entry.deleted_at)},\n"
        sql += f"  {escape_sql_string(entry.deleted_by)},\n"
        sql += f"  {entry.is_completed}\n"
        sql += ");\n\n"
    
    return sql


def main():
    """Основная функция"""
    db = SessionLocal()
    
    try:
        # Определяем имя выходного файла
        if len(sys.argv) > 1:
            output_file = sys.argv[1]
        else:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_file = f"data_transfer_{timestamp}.sql"
        
        # Проверяем что файл не существует
        if os.path.exists(output_file):
            response = input(f"Файл {output_file} уже существует. Перезаписать? (y/N): ")
            if response.lower() != 'y':
                print("Отменено")
                return
        
        print(f"Создание дампа данных...")
        print(f"Источник БД: {os.getenv('DATABASE_URL', 'sqlite:///./ce_guests.db')}")
        
        # Формируем SQL дамп
        sql_dump = "-- Перенос данных CE Guests Backend\n"
        sql_dump += f"-- Создан: {datetime.now().isoformat()}\n"
        sql_dump += "-- ВНИМАНИЕ: Этот файл содержит только данные (users и entries)\n"
        sql_dump += "-- Структура таблиц должна быть создана через миграции!\n"
        sql_dump += "-- Использование: sqlite3 ce_guests.db < data_transfer.sql\n\n"
        sql_dump += "BEGIN TRANSACTION;\n\n"
        
        # Дамп пользователей
        print("Дамп пользователей...")
        users_sql = dump_users(db)
        sql_dump += users_sql
        
        # Дамп записей
        print("Дамп записей...")
        entries_sql = dump_entries(db)
        sql_dump += entries_sql
        
        sql_dump += "COMMIT;\n"
        
        # Сохраняем в файл
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(sql_dump)
        
        # Статистика
        users_count = len(db.query(User).all())
        entries_count = len(db.query(Entry).all())
        
        print("\n" + "=" * 60)
        print("✅ Дамп создан успешно!")
        print("=" * 60)
        print(f"Файл: {output_file}")
        print(f"Пользователей: {users_count}")
        print(f"Записей: {entries_count}")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n❌ Ошибка при создании дампа: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
