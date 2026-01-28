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

LAST_BACKUP_META="${LAST_BACKUP}.meta"
if [ ! -f "$LAST_BACKUP_META" ]; then
    error "Метаданные бэкапа не найдены: $LAST_BACKUP_META"
    error "Не могу определить коммит для отката"
    exit 1
fi

# Читаем метаданные бэкапа
source "$LAST_BACKUP_META"
BACKUP_COMMIT="$COMMIT"

info "Последний бэкап: $(basename "$LAST_BACKUP")"
info "Коммит из бэкапа: $(git rev-parse --short "$BACKUP_COMMIT")"

# Проверка идемпотентности - не откатываемся ли на тот же коммит
if [ "$CURRENT_COMMIT" = "$BACKUP_COMMIT" ]; then
    error "Уже на коммите из бэкапа! Откат не нужен."
    error "Текущий коммит: $(git rev-parse --short "$CURRENT_COMMIT")"
    error "Коммит бэкапа: $(git rev-parse --short "$BACKUP_COMMIT")"
    exit 1
fi

# Проверяем что коммит из бэкапа существует
if ! git rev-parse --verify "$BACKUP_COMMIT" > /dev/null 2>&1; then
    error "Коммит из бэкапа не найден: $BACKUP_COMMIT"
    error "Возможно код был переписан (force push)"
    exit 1
fi

# Показываем что будет откачено
PREVIOUS_COMMIT=$(git rev-parse "$BACKUP_COMMIT~1" 2>/dev/null || echo "")
echo ""
warn "=========================================="
warn "Будет выполнено:"
warn "=========================================="
warn "1. Откат кода на коммит: $(git rev-parse --short "$BACKUP_COMMIT")"
if [ -n "$PREVIOUS_COMMIT" ]; then
    warn "   (предыдущий коммит: $(git rev-parse --short "$PREVIOUS_COMMIT"))"
fi
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

# Откат кода
info "Откат кода на коммит $BACKUP_COMMIT..."
git reset --hard "$BACKUP_COMMIT"
info "Код откачен ✓"

# Восстановление БД
info "Восстановление БД из бэкапа..."
if [ -f "$DB_FILE" ]; then
    # Делаем бэкап текущей БД перед восстановлением
    CURRENT_BACKUP="${DB_FILE}.before_rollback_$(date +%Y%m%d_%H%M%S)"
    cp "$DB_FILE" "$CURRENT_BACKUP"
    info "Текущая БД сохранена в: $CURRENT_BACKUP"
fi

cp "$LAST_BACKUP" "$DB_FILE"
info "БД восстановлена из: $(basename "$LAST_BACKUP") ✓"

# Проверка миграций после отката кода
CURRENT_MIGRATION=$(alembic current 2>/dev/null | grep -o '[a-f0-9]\{12\}' || echo "none")
HEAD_MIGRATION=$(alembic heads | grep -o '[a-f0-9]\{12\}' | head -1)

if [ "$CURRENT_MIGRATION" != "$HEAD_MIGRATION" ] && [ "$CURRENT_MIGRATION" != "none" ]; then
    warn "Версия миграций изменилась после отката кода"
    warn "Текущая: $CURRENT_MIGRATION, Новая: $HEAD_MIGRATION"
    warn "Откатываем миграции на версию $HEAD_MIGRATION..."
    alembic downgrade "$HEAD_MIGRATION" 2>/dev/null || warn "Не удалось откатить миграции автоматически"
fi

# Перезапуск сервиса
info "Перезапуск сервиса ce-guests-back..."
sudo systemctl restart ce-guests-back

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
HEALTH_URL="http://127.0.0.1:8002/health"
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
