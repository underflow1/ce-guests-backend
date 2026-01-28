#!/usr/bin/env python3
"""
Скрипт запуска сервера
Использует настройки HOST и PORT из app.config
"""
import os
import uvicorn
from app.config import settings

if __name__ == "__main__":
    # Отключаем reload в production (когда запускается через systemd)
    # Reload работает только при прямом запуске скрипта
    reload = os.environ.get("RELOAD", "false").lower() == "true"
    
    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=reload,
    )
