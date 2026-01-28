#!/usr/bin/env python3
"""
Скрипт для создания первого администратора
Использование:
    python3 scripts/create_admin.py
    python3 scripts/create_admin.py --username admin --password secret
"""
import sys
import os
import termios
import tty

# Добавляем корневую директорию в путь
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.orm import Session
from app.database import SessionLocal, engine
from app.models.user import User
from app.services.auth import get_password_hash, get_current_timestamp
import argparse


def getpass_with_stars(prompt="Password: "):
    """Ввод пароля с отображением звездочек"""
    print(prompt, end='', flush=True)
    password = []
    
    # Сохраняем настройки терминала
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    
    try:
        # Переключаемся в raw mode
        tty.setraw(sys.stdin.fileno())
        
        while True:
            char = sys.stdin.read(1)
            
            # Enter - завершаем ввод
            if char == '\n' or char == '\r':
                break
            # Backspace или Delete
            elif char == '\x7f' or char == '\b':
                if password:
                    password.pop()
                    sys.stdout.write('\b \b')
                    sys.stdout.flush()
            # Ctrl+C
            elif char == '\x03':
                raise KeyboardInterrupt
            else:
                password.append(char)
                sys.stdout.write('*')
                sys.stdout.flush()
    
    finally:
        # Восстанавливаем настройки терминала
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        print()  # Новая строка после ввода
    
    return ''.join(password)


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
        password = getpass_with_stars("Введите пароль: ").strip()
        if not password:
            print("Ошибка: Пароль не может быть пустым")
            return
    else:
        password = args.password
    
    create_admin(username, password)


if __name__ == "__main__":
    main()
