#!/usr/bin/env python3
"""
Скрипт для создания первого администратора
Использование:
    python3 scripts/create_admin.py
    python3 scripts/create_admin.py --username admin --password secret
"""
import sys
import os

# Добавляем корневую директорию в путь
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.orm import Session
from app.database import SessionLocal, engine
from app.models.user import User
from app.services.auth import get_password_hash, get_current_timestamp
import argparse


def create_admin(username: str, password: str):
    """Создать администратора"""
    db: Session = SessionLocal()
    
    try:
        # Проверяем что пользователь с таким username не существует
        existing_user = db.query(User).filter(User.username == username).first()
        if existing_user:
            print(f"Ошибка: Пользователь '{username}' уже существует")
            return False
        
        password_hash = get_password_hash(password)
        timestamp = get_current_timestamp()
        
        admin = User(
            username=username,
            password_hash=password_hash,
            is_admin=1,
            is_active=1,
            created_at=timestamp,
        )
        
        db.add(admin)
        db.commit()
        db.refresh(admin)
        
        print(f"✓ Администратор '{username}' успешно создан!")
        print(f"  ID: {admin.id}")
        return True
        
    except Exception as e:
        db.rollback()
        print(f"Ошибка при создании администратора: {e}")
        return False
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(description="Создать первого администратора")
    parser.add_argument("--username", help="Имя пользователя", default=None)
    parser.add_argument("--password", help="Пароль", default=None)
    
    args = parser.parse_args()
    
    # Если аргументы не переданы, запрашиваем интерактивно
    if not args.username:
        username = input("Введите имя пользователя: ").strip()
        if not username:
            print("Ошибка: Имя пользователя не может быть пустым")
            return
    else:
        username = args.username
    
    if not args.password:
        import getpass
        password = getpass.getpass("Введите пароль: ").strip()
        if not password:
            print("Ошибка: Пароль не может быть пустым")
            return
    else:
        password = args.password
    
    create_admin(username, password)


if __name__ == "__main__":
    main()
