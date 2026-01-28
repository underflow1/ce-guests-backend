#!/bin/bash
# Скрипт отката обновления
# Использование: ./scripts/rollback.sh

set -e  # Остановка при ошибке

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

info "Откат обновления CE Guests Backend"
info "Путь к проекту: $REPO_PATH"

# Проверка что мы на ветке main
CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD)
if [ "$CURRENT_BRANCH" != "main" ]; then
    error "Вы не на ветке main! Текущая ветка: $CURRENT_BRANCH"
    exit 1
fi

CURRENT_COMMIT=$(git rev-parse HEAD)
info "Текущий коммит: $(git rev-parse --short HEAD)"

# Проверяем что есть предыдущий коммит
PREVIOUS_COMMIT=$(git rev-parse HEAD~1 2>/dev/null || echo "")
if [ -z "$PREVIOUS_COMMIT" ]; then
    error "Нет предыдущего коммита для отката!"
    exit 1
fi

info "Предыдущий коммит: $(git rev-parse --short "$PREVIOUS_COMMIT")"

# Находим последний бэкап
BACKUP_DIR="$REPO_PATH/backups"
if [ ! -d "$BACKUP_DIR" ]; then
    error "Директория бэкапов не найдена: $BACKUP_DIR"
    exit 1
fi

# Ищем последний бэкап (по времени создания)
LAST_BACKUP=$(ls -t "$BACKUP_DIR"/backup_*.db 2>/dev/null | head -1)

if [ -z "$LAST_BACKUP" ]; then
    error "Бэкапы не найдены в $BACKUP_DIR"
    exit 1
fi

info "Последний бэкап: $(basename "$LAST_BACKUP")"

# Проверка идемпотентности: если уже откатились на один коммит назад, не делать ничего
META_FILE="$REPO_PATH/.update_meta"
if [ -f "$META_FILE" ]; then
    source "$META_FILE"
    LAST_UPDATE_COMMIT="$COMMIT"
    
    # Если текущий HEAD уже на один коммит раньше последнего обновления, значит уже откатились
    LAST_UPDATE_PARENT=$(git rev-parse "$LAST_UPDATE_COMMIT~1" 2>/dev/null || echo "")
    if [ -n "$LAST_UPDATE_PARENT" ] && [ "$CURRENT_COMMIT" = "$LAST_UPDATE_PARENT" ]; then
        info "Уже откачено на один коммит назад от последнего обновления"
        info "Текущий коммит: $(git rev-parse --short "$CURRENT_COMMIT")"
        info "Коммит последнего обновления: $(git rev-parse --short "$LAST_UPDATE_COMMIT")"
        info "Откат не требуется (идемпотентность)"
        exit 0
    fi
fi

# Показываем что будет откачено
echo ""
warn "=========================================="
warn "Будет выполнено:"
warn "=========================================="
warn "1. Откат кода на предыдущий коммит: $(git rev-parse --short "$PREVIOUS_COMMIT")"
warn "2. Восстановление БД из: $(basename "$LAST_BACKUP")"
warn "3. Перезапуск сервиса"
warn "=========================================="
echo ""

# Подтверждение
read -p "Продолжить откат? (yes/no): " CONFIRM
if [ "$CONFIRM" != "yes" ]; then
    info "Откат отменен"
    exit 0
fi

# Проверка что venv существует
if [ ! -d "venv" ]; then
    error "Виртуальное окружение не найдено!"
    exit 1
fi
source venv/bin/activate

# Получаем путь к БД
DB_FILE=$(python3 -c "from app.config import settings; print(settings.DATABASE_URL.replace('sqlite:///', '').replace('sqlite:///./', ''))")

# Откат кода на предыдущий коммит
info "Откат кода на предыдущий коммит $PREVIOUS_COMMIT..."
git reset --hard "$PREVIOUS_COMMIT"
info "Код откачен ✓"

# Остановка сервиса перед восстановлением БД
info "Остановка сервиса ce-guests-back для безопасного восстановления БД..."
if systemctl is-active --quiet ce-guests-back; then
    sudo systemctl stop ce-guests-back
    sleep 2  # Даем время сервису корректно остановиться
    info "Сервис остановлен ✓"
else
    warn "Сервис уже остановлен"
fi

# Восстановление БД (пока сервис остановлен)
info "Восстановление БД из бэкапа..."
if [ -f "$DB_FILE" ]; then
    # Делаем бэкап текущей БД перед восстановлением
    CURRENT_BACKUP="${DB_FILE}.before_rollback_$(date +%Y%m%d_%H%M%S)"
    cp "$DB_FILE" "$CURRENT_BACKUP"
    info "Текущая БД сохранена в: $CURRENT_BACKUP"
fi

cp "$LAST_BACKUP" "$DB_FILE"
info "БД восстановлена из: $(basename "$LAST_BACKUP") ✓"

# Применение миграций после отката кода
info "Применение миграций после отката кода..."
if ! alembic upgrade head; then
    warn "Не удалось применить миграции автоматически"
fi

# Запуск сервиса после восстановления
info "Запуск сервиса ce-guests-back..."
sudo systemctl start ce-guests-back

# Ждем немного
sleep 3

# Проверка статуса сервиса
if systemctl is-active --quiet ce-guests-back; then
    info "Сервис запущен ✓"
else
    error "Сервис не запущен!"
    error "Проверьте логи: sudo journalctl -u ce-guests-back -n 50"
    exit 1
fi

# Проверка здоровья
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
if curl -s -f "$HEALTH_URL" > /dev/null 2>&1; then
    HEALTH_RESPONSE=$(curl -s "$HEALTH_URL")
    if echo "$HEALTH_RESPONSE" | grep -q '"status":"ok"'; then
        info "Сервис здоров ✓"
    else
        warn "Сервис отвечает, но статус не OK: $HEALTH_RESPONSE"
    fi
else
    error "Сервис не отвечает на health check!"
    error "Проверьте логи: sudo journalctl -u ce-guests-back -n 50"
fi

# Финальная информация
echo ""
info "=========================================="
info "✅ Откат завершен"
info "=========================================="
info "Коммит: $(git rev-parse --short HEAD)"
info "Версия миграций: $(alembic current | grep -o '[a-f0-9]\{12\}' || echo 'none')"
info "Статус сервиса: $(systemctl is-active ce-guests-back)"
info "БД восстановлена из: $(basename "$LAST_BACKUP")"
info "=========================================="
