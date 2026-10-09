#!/usr/bin/env bash
set -e

# ==============================================================================
# Telegram Nutrition & Expense AI — One-Click Production Deploy Script
# ==============================================================================

GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${BLUE}======================================================${NC}"
echo -e "${BLUE}  🚀 Развертывание NutriTracker AI на сервере        ${NC}"
echo -e "${BLUE}======================================================${NC}"

# 1. Проверка наличия Docker
if ! command -v docker &> /dev/null; then
    echo -e "${RED}❌ Ошибка: Docker не установлен! Установите Docker: https://docs.docker.com/engine/install/${NC}"
    exit 1
fi

# 2. Проверка наличия docker compose
if docker compose version &> /dev/null; then
    DOCKER_COMPOSE="docker compose"
elif command -v docker-compose &> /dev/null; then
    DOCKER_COMPOSE="docker-compose"
else
    echo -e "${RED}❌ Ошибка: docker compose не найден!${NC}"
    exit 1
fi

# 3. Проверка .env файла
if [ ! -f .env ]; then
    echo -e "${YELLOW}⚠️ Файл .env не найден! Создаю из .env.example...${NC}"
    cp .env.example .env
    echo -e "${RED}❗ Заполните ваши реальные ключи в файле .env (BOT_TOKEN, GEMINI_API_KEY, WEB_APP_URL)!${NC}"
    echo -e "После заполнения запустите ./deploy/deploy.sh снова."
    exit 1
fi

# 4. Проверка обязательных переменных
if grep -q "YOUR_GEMINI_API_KEY_HERE" .env || grep -q "1234567890:ABCdef" .env; then
    echo -e "${RED}❌ В .env остались значения по умолчанию! Укажите ваши реальные BOT_TOKEN и GEMINI_API_KEY.${NC}"
    exit 1
fi

# 5. Создание директории данных
mkdir -p data

# 6. Сборка и запуск контейнеров
echo -e "${GREEN}📦 Сборка и запуск контейнеров через Docker Compose...${NC}"
$DOCKER_COMPOSE up -d --build

# 7. Проверка статуса
echo -e "${BLUE}⏳ Ожидание запуска сервиса...${NC}"
sleep 5

if $DOCKER_COMPOSE ps | grep -q "Up"; then
    echo -e "${GREEN}======================================================${NC}"
    echo -e "${GREEN}✅ Сервис успешно запущен и работает в фоновом режиме!${NC}"
    echo -e "${GREEN}======================================================${NC}"
    echo -e "Команды для управления:"
    echo -e "  • Просмотр логов:       $DOCKER_COMPOSE logs -f"
    echo -e "  • Перезапуск:           $DOCKER_COMPOSE restart"
    echo -e "  • Остановка:            $DOCKER_COMPOSE down"
    echo -e "  • Статус:               $DOCKER_COMPOSE ps"
else
    echo -e "${RED}❌ Сервис не запустился. Проверьте логи командой:${NC}"
    echo -e "  $DOCKER_COMPOSE logs"
    exit 1
fi
