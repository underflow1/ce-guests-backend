#!/usr/bin/env python3
"""
Скрипт запуска сервера
Использует настройки HOST и PORT из app.config
"""
import uvicorn
from app.config import settings

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=True,
    )
