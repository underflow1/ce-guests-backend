#!/bin/bash

# Цвета для вывода (определяем ДО set -euo pipefail)
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m' # No Color

set -euo pipefail

# Заголовок
clear
echo -e "${BOLD}${CYAN}"
echo "  ╔═══════════════════════════════════════════════════════════════╗"
echo "  ║     Установка CE Guests Backend                                 ║"
echo "  ╚═══════════════════════════════════════════════════════════════╝"
echo -e "${NC}"

# Функции для вывода
section() {
    # Пустая функция - разделители убраны
    :
}

step() {
    # Показываем спиннер перед операцией
    # После выполнения операции нужно вызвать step_done()
    step_progress "$1"
}

step_done() {
    # Заменяем спиннер на ✓ после выполнения операции
    step_progress_stop
}

STEP_PROGRESS_MSG=""

step_progress() {
    # Показываем шаг с крутящимся спиннером перед текстом
    local msg="$1"
    STEP_PROGRESS_MSG="$msg"
    local pid_file="/tmp/install_progress_$$.pid"
    local spinner_chars="|/-\\"
    local spinner_idx=0
    
    # Запускаем спиннер в фоне
    (
        while [ -f "$pid_file" ]; do
            local spinner_char="${spinner_chars:$spinner_idx:1}"
            # Используем \033[K для очистки до конца строки
            echo -ne "\r\033[K${spinner_char} ${BOLD}${msg}${NC}"
            spinner_idx=$(( (spinner_idx + 1) % 4 ))
            sleep 0.1
        done
    ) &
    echo $! > "$pid_file"
}

step_progress_stop() {
    # Останавливаем спиннер и заменяем на ✓ в той же строке
    local pid_file="/tmp/install_progress_$$.pid"
    if [ -f "$pid_file" ]; then
        local pid=$(cat "$pid_file")
        kill "$pid" 2>/dev/null || true
        wait "$pid" 2>/dev/null || true
        rm -f "$pid_file"
        # Небольшая задержка чтобы убедиться что спиннер остановлен
        sleep 0.15
        local msg="${STEP_PROGRESS_MSG}"
        # Очищаем строку перед выводом ✓
        echo -ne "\r\033[K${GREEN}✓${NC} ${BOLD}${msg}${NC}\n"
        STEP_PROGRESS_MSG=""
    fi
}

success() {
    echo -e "${GREEN}✓${NC} $1"
}

error() {
    echo -e "${RED}✗${NC} ${BOLD}Ошибка:${NC} $1" >&2
}

warn() {
    echo -e "${YELLOW}⚠${NC} $1"
}

info() {
    echo -e "  ${GREEN}→${NC} $1"
}

# ============================================================================
# ПРОВЕРКИ
# ============================================================================

# Проверка окружения

# Проверка запуска через sudo
if [ "$EUID" -ne 0 ]; then
    error "Скрипт должен быть запущен через sudo"
    exit 1
fi

# Определение пользователя, от имени которого запущен sudo
if [ -z "${SUDO_USER:-}" ]; then
    error "Не удалось определить пользователя. Запустите: sudo -u USER $0"
    exit 1
fi

REAL_USER="$SUDO_USER"
REAL_HOME=$(eval echo ~$REAL_USER)

info "Пользователь: $REAL_USER"
info "Домашняя директория: $REAL_HOME"

# Определяем путь к репозиторию - директория где запущен скрипт
REPO_PATH="$(cd "$(dirname "$0")" && pwd)"

# Проверяем что мы в правильной директории (должен быть requirements.txt)
if [ ! -f "$REPO_PATH/requirements.txt" ] || [ ! -f "$REPO_PATH/app/main.py" ]; then
    error "Файлы проекта не найдены. Запустите скрипт из директории проекта."
    exit 1
fi

success "Проверки пройдены"

# ============================================================================
# ИНТЕРАКТИВНЫЙ ВВОД
# ============================================================================

# Настройка параметров

exec 3<&0

# Домен фронтенда для CORS
echo -ne "${BOLD}${YELLOW}Введите домен фронтенда (для CORS): ${NC}" >&2
read -r FRONTEND_DOMAIN <&3
FRONTEND_DOMAIN=${FRONTEND_DOMAIN:-""}
if [ -z "$FRONTEND_DOMAIN" ]; then
    error "Домен не может быть пустым"
    exit 1
fi

# Формируем CORS_ORIGINS с протоколом
if [[ ! "$FRONTEND_DOMAIN" =~ ^https?:// ]]; then
    CORS_ORIGINS="https://$FRONTEND_DOMAIN"
else
    CORS_ORIGINS="$FRONTEND_DOMAIN"
fi

# Порт бэкенда
echo -ne "${BOLD}${YELLOW}Введите порт бэкенда [8000]: ${NC}" >&2
read -r BACKEND_PORT <&3
BACKEND_PORT=${BACKEND_PORT:-8000}

# Хост бэкенда
echo -ne "${BOLD}${YELLOW}Введите хост бэкенда [127.0.0.1]: ${NC}" >&2
read -r BACKEND_HOST <&3
BACKEND_HOST=${BACKEND_HOST:-127.0.0.1}

success "Домен фронтенда: $CORS_ORIGINS"
success "Бэкенд: $BACKEND_HOST:$BACKEND_PORT"

# ============================================================================
# ПРОВЕРКА PYTHON3 И СИСТЕМНЫХ ЗАВИСИМОСТЕЙ
# ============================================================================

step "Проверка Python3"

if ! command -v python3 &> /dev/null; then
    step_progress_stop
    error "Python3 не найден. Установите Python3 перед продолжением."
    exit 1
fi

PYTHON_VERSION=$(python3 --version | cut -d' ' -f2)
PYTHON_MAJOR=$(python3 -c 'import sys; print(sys.version_info.major)')
PYTHON_MINOR=$(python3 -c 'import sys; print(sys.version_info.minor)')

if [ "$PYTHON_MAJOR" -lt 3 ] || ([ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -lt 8 ]); then
    step_progress_stop
    error "Требуется Python 3.8 или выше. Найдена версия: $PYTHON_VERSION"
    exit 1
fi

step_done
info "Найден Python3: $PYTHON_VERSION"

# Проверка и установка python3-venv
step "Проверка python3-venv"

PYTHON_VERSION_SHORT="${PYTHON_MAJOR}.${PYTHON_MINOR}"
VENV_PACKAGE="python${PYTHON_VERSION_SHORT}-venv"

# Проверяем наличие пакета через dpkg
if ! dpkg -l | grep -q "^ii.*${VENV_PACKAGE}"; then
    step_progress_stop
    step_progress "Установка пакета: $VENV_PACKAGE"
    apt-get update -qq > /dev/null 2>&1
    if ! apt-get install -y "$VENV_PACKAGE" > /dev/null 2>&1; then
        step_progress_stop
        error "Не удалось установить $VENV_PACKAGE"
        exit 1
    fi
    step_progress_stop
else
    step_progress_stop
fi

# ============================================================================
# СОЗДАНИЕ ВИРТУАЛЬНОГО ОКРУЖЕНИЯ
# ============================================================================

step "Создание виртуального окружения"

if [ -d "$REPO_PATH/venv" ]; then
    step_progress_stop
    warn "Виртуальное окружение уже существует"
else
    # Временно отключаем set -e для обработки ошибки вручную
    set +e
    sudo -u "$REAL_USER" python3 -m venv "$REPO_PATH/venv" 2>&1
    VENV_EXIT_CODE=$?
    set -e
    
    if [ $VENV_EXIT_CODE -ne 0 ]; then
        step_progress_stop
        error "Не удалось создать виртуальное окружение (код выхода: $VENV_EXIT_CODE)"
        exit 1
    fi
    step_done
fi

# ============================================================================
# УСТАНОВКА ЗАВИСИМОСТЕЙ
# ============================================================================

step_progress "Обновление pip"
if ! sudo -u "$REAL_USER" "$REPO_PATH/venv/bin/pip" install --upgrade pip --quiet 2>&1; then
    step_progress_stop
    error "Не удалось обновить pip"
    exit 1
fi
step_progress_stop

step_progress "Установка зависимостей из requirements.txt"
if ! sudo -u "$REAL_USER" "$REPO_PATH/venv/bin/pip" install -r "$REPO_PATH/requirements.txt" --quiet 2>&1; then
    step_progress_stop
    error "Не удалось установить зависимости"
    exit 1
fi
step_progress_stop

# ============================================================================
# СОЗДАНИЕ .env
# ============================================================================

step "Создание .env файла"

ENV_FILE="$REPO_PATH/.env"
ENV_EXAMPLE="$REPO_PATH/.env.example"

if [ ! -f "$ENV_EXAMPLE" ]; then
    step_progress_stop
    error "Файл .env.example не найден"
    exit 1
fi

# Генерация SECRET_KEY как UUID v4
SECRET_KEY=$(python3 -c "import uuid; print(str(uuid.uuid4()))")

# Создаем .env из примера с подстановкой значений
cat > "$ENV_FILE" <<EOF
# Database
DATABASE_URL=sqlite:///./ce_guests.db

# JWT
SECRET_KEY=$SECRET_KEY
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=1440

# CORS
CORS_ORIGINS=$CORS_ORIGINS

# Timezone
TIMEZONE=Europe/Moscow

# Server
HOST=$BACKEND_HOST
PORT=$BACKEND_PORT
EOF

chown "$REAL_USER:$REAL_USER" "$ENV_FILE"
chmod 600 "$ENV_FILE"
step_done

# ============================================================================
# ПРИМЕНЕНИЕ МИГРАЦИЙ
# ============================================================================

step_progress "Применение миграций БД"
if ! sudo -u "$REAL_USER" bash -c "cd $REPO_PATH && source venv/bin/activate && alembic upgrade head" 2>&1; then
    step_progress_stop
    error "Не удалось применить миграции"
    exit 1
fi
step_progress_stop

# ============================================================================
# СОЗДАНИЕ SYSTEMD СЕРВИСА
# ============================================================================

step "Создание systemd сервиса"

SERVICE_NAME="ce-guests-back"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

# Создание unit файла
cat > "$SERVICE_FILE" <<EOF
[Unit]
Description=CE Guests Backend API Service
After=network.target

[Service]
Type=simple
User=$REAL_USER
Group=$REAL_USER
WorkingDirectory=$REPO_PATH
Environment="PATH=$REPO_PATH/venv/bin:/usr/local/bin:/usr/bin:/bin"
ExecStart=$REPO_PATH/venv/bin/python3 $REPO_PATH/run.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

chmod 644 "$SERVICE_FILE"
step_done

# Перезагрузка systemd
step "Перезагрузка systemd daemon"
systemctl daemon-reload > /dev/null 2>&1
step_done

# Включение автозапуска
step "Включение автозапуска сервиса"
systemctl enable "$SERVICE_NAME.service" > /dev/null 2>&1
step_done

# Запуск сервиса
step "Запуск сервиса"
systemctl start "$SERVICE_NAME.service" > /dev/null 2>&1
sleep 2

if systemctl is-active --quiet "$SERVICE_NAME.service"; then
    step_done
else
    step_progress_stop
    error "Сервис не запустился. Проверьте логи: sudo journalctl -u $SERVICE_NAME"
    exit 1
fi

# ============================================================================
# ЗАВЕРШЕНИЕ
# ============================================================================

echo ""
echo -e "${BOLD}${GREEN}✓ Установка завершена успешно!${NC}"
echo ""
echo -e "  ${BOLD}Домен фронтенда:${NC} $CORS_ORIGINS"
echo -e "  ${BOLD}Бэкенд:${NC} http://$BACKEND_HOST:$BACKEND_PORT"
echo -e "  ${BOLD}Директория проекта:${NC} $REPO_PATH"
echo ""
echo -e "  ${BOLD}Важно:${NC} Создайте первого администратора:"
echo -e "    ${CYAN}cd $REPO_PATH && source venv/bin/activate && python3 scripts/create_admin.py${NC}"
echo ""
echo -e "  ${BOLD}Полезные команды:${NC}"
echo -e "    Статус сервиса:  ${CYAN}sudo systemctl status $SERVICE_NAME${NC}"
echo -e "    Остановка:       ${CYAN}sudo systemctl stop $SERVICE_NAME${NC}"
echo -e "    Перезапуск:      ${CYAN}sudo systemctl restart $SERVICE_NAME${NC}"
echo -e "    Логи:            ${CYAN}sudo journalctl -u $SERVICE_NAME -f${NC}"
echo ""
echo -e "  ${BOLD}API документация:${NC} http://$BACKEND_HOST:$BACKEND_PORT/docs"
echo ""
