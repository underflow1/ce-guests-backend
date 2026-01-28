#!/bin/bash
# Скрипт обновления на проде
# Использование: ./scripts/update.sh

# Не используем set -e, чтобы можно было обработать ошибки и перезапустить сервис

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Функции для вывода
info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Определяем путь к проекту
REPO_PATH="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_PATH"

info "Обновление CE Guests Backend"
info "Путь к проекту: $REPO_PATH"

# Проверка что мы на ветке main
CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD)
if [ "$CURRENT_BRANCH" != "main" ]; then
    error "Вы не на ветке main! Текущая ветка: $CURRENT_BRANCH"
    error "Переключитесь на main: git checkout main"
    exit 1
fi
info "Текущая ветка: $CURRENT_BRANCH ✓"

# Проверка что нет незакоммиченных изменений
if ! git diff-index --quiet HEAD --; then
    error "Есть незакоммиченные изменения!"
    error "Закоммитьте или отмените изменения перед деплоем"
    exit 1
fi
info "Нет незакоммиченных изменений ✓"

# Проверка что venv существует
if [ ! -d "venv" ]; then
    error "Виртуальное окружение не найдено!"
    exit 1
fi
info "Виртуальное окружение найдено ✓"

# Активация venv
source venv/bin/activate

# Проверка текущей версии миграций
CURRENT_MIGRATION=$(alembic current 2>/dev/null | grep -o '[a-f0-9]\{12\}' || echo "none")
info "Текущая версия миграций: $CURRENT_MIGRATION"

# Сохраняем текущий коммит ДО обновления (для отката)
COMMIT_BEFORE_UPDATE=$(git rev-parse HEAD)

# Флаг что сервис был остановлен (для восстановления при ошибке)
SERVICE_WAS_RUNNING=false

# Остановка сервиса перед бэкапом
info "Остановка сервиса ce-guests-back для безопасного бэкапа..."
if systemctl is-active --quiet ce-guests-back; then
    SERVICE_WAS_RUNNING=true
    sudo systemctl stop ce-guests-back
    sleep 2  # Даем время сервису корректно остановиться
    info "Сервис остановлен ✓"
else
    warn "Сервис уже остановлен"
fi

# Функция восстановления сервиса при ошибке
restore_service_on_error() {
    if [ "$SERVICE_WAS_RUNNING" = true ]; then
        warn "Восстановление сервиса после ошибки..."
        sudo systemctl start ce-guests-back || true
    fi
}

# Обработка ошибок
trap 'restore_service_on_error; exit 1' ERR

# Бэкап БД (пока сервис остановлен)
DB_FILE=$(python3 -c "from app.config import settings; print(settings.DATABASE_URL.replace('sqlite:///', '').replace('sqlite:///./', ''))")
if [ -f "$DB_FILE" ]; then
    BACKUP_DIR="$REPO_PATH/backups"
    mkdir -p "$BACKUP_DIR"
    TIMESTAMP=$(date +%Y%m%d_%H%M%S)
    BACKUP_FILE="$BACKUP_DIR/backup_${TIMESTAMP}.db"
    cp "$DB_FILE" "$BACKUP_FILE"
    
    # Сохраняем метаданные обновления в один файл (перезаписывается при каждом обновлении)
    # COMMIT - это коммит ДО обновления, на который нужно откатиться
    META_FILE="$REPO_PATH/.update_meta"
    echo "COMMIT=$COMMIT_BEFORE_UPDATE" > "$META_FILE"
    echo "TIMESTAMP=$TIMESTAMP" >> "$META_FILE"
    echo "BRANCH=$CURRENT_BRANCH" >> "$META_FILE"
    echo "BACKUP_FILE=$(basename "$BACKUP_FILE")" >> "$META_FILE"
    
    info "Бэкап БД создан: $BACKUP_FILE"
    info "Метаданные сохранены: $META_FILE"
    
    # Выводим команды для отката
    echo ""
    warn "=========================================="
    warn "Команды для отката (если что-то пойдет не так):"
    warn "=========================================="
    warn "./scripts/rollback.sh"
    warn "Или вручную:"
    warn "  git reset --hard $COMMIT_BEFORE_UPDATE"
    warn "  cp $BACKUP_FILE $DB_FILE"
    warn "  sudo systemctl restart ce-guests-back"
    warn "=========================================="
    echo ""
else
    warn "Файл БД не найден, пропускаем бэкап"
fi

# Обновление кода
info "Обновление кода из репозитория..."
git fetch origin
LOCAL_COMMIT=$(git rev-parse HEAD)
REMOTE_COMMIT=$(git rev-parse origin/main)

if [ "$LOCAL_COMMIT" = "$REMOTE_COMMIT" ]; then
    warn "Локальный код уже актуален (нет новых коммитов)"
else
    info "Найдены новые коммиты, обновляем..."
    git pull origin main
    info "Код обновлен ✓"
fi

# Проверка новых миграций
HEAD_MIGRATION=$(alembic heads | grep -o '[a-f0-9]\{12\}' | head -1)
if [ "$CURRENT_MIGRATION" != "$HEAD_MIGRATION" ] && [ "$CURRENT_MIGRATION" != "none" ]; then
    info "Найдены новые миграции: $CURRENT_MIGRATION -> $HEAD_MIGRATION"
    info "Применение миграций..."
    if ! alembic upgrade head; then
        error "Ошибка при применении миграций!"
        restore_service_on_error
        exit 1
    fi
    info "Миграции применены ✓"
elif [ "$CURRENT_MIGRATION" = "none" ]; then
    warn "Миграции не применены, применяем все..."
    if ! alembic upgrade head; then
        error "Ошибка при применении миграций!"
        restore_service_on_error
        exit 1
    fi
    info "Миграции применены ✓"
else
    info "Нет новых миграций ✓"
fi

# Запуск сервиса после обновления
info "Запуск сервиса ce-guests-back..."
if ! sudo systemctl start ce-guests-back; then
    error "Не удалось запустить сервис!"
    exit 1
fi

# Отключаем trap после успешного запуска
trap - ERR

# Ждем немного чтобы сервис запустился
sleep 3

# Проверка статуса сервиса
if systemctl is-active --quiet ce-guests-back; then
    info "Сервис запущен ✓"
else
    error "Сервис не запущен!"
    error "Проверьте логи: sudo journalctl -u ce-guests-back -n 50"
    exit 1
fi

# Проверка здоровья через health endpoint
info "Проверка здоровья сервиса..."

# Читаем HOST и PORT из .env файла
if [ -f "$REPO_PATH/.env" ]; then
    # Безопасное чтение переменных из .env (игнорируем комментарии и пустые строки)
    ENV_HOST=$(grep -E "^HOST=" "$REPO_PATH/.env" | cut -d'=' -f2 | tr -d '"' | tr -d "'" || echo "127.0.0.1")
    ENV_PORT=$(grep -E "^PORT=" "$REPO_PATH/.env" | cut -d'=' -f2 | tr -d '"' | tr -d "'" || echo "8000")
else
    warn ".env файл не найден, используем значения по умолчанию"
    ENV_HOST="127.0.0.1"
    ENV_PORT="8000"
fi

HEALTH_URL="http://${ENV_HOST}:${ENV_PORT}/health"
MAX_RETRIES=5
RETRY_COUNT=0

while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
    if curl -s -f "$HEALTH_URL" > /dev/null 2>&1; then
        HEALTH_RESPONSE=$(curl -s "$HEALTH_URL")
        if echo "$HEALTH_RESPONSE" | grep -q '"status":"ok"'; then
            info "Сервис здоров ✓"
            info "Ответ: $HEALTH_RESPONSE"
            break
        fi
    fi
    
    RETRY_COUNT=$((RETRY_COUNT + 1))
    if [ $RETRY_COUNT -lt $MAX_RETRIES ]; then
        warn "Попытка $RETRY_COUNT/$MAX_RETRIES не удалась, ждем..."
        sleep 2
    else
        error "Сервис не отвечает на health check!"
        error "URL: $HEALTH_URL"
        error "Проверьте логи: sudo journalctl -u ce-guests-back -n 50"
        exit 1
    fi
done

# Финальная информация
echo ""
info "=========================================="
info "✅ Обновление завершено успешно!"
info "=========================================="
info "Версия миграций: $(alembic current | grep -o '[a-f0-9]\{12\}' || echo 'none')"
info "Последний коммит: $(git rev-parse --short HEAD)"
info "Статус сервиса: $(systemctl is-active ce-guests-back)"
if [ -f "$BACKUP_FILE" ]; then
    info "Бэкап БД: $BACKUP_FILE"
fi
info "=========================================="
