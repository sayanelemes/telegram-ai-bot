# 🚀 Руководство по деплою на сервер (Production Deployment)

Это полное пошаговое руководство по развертыванию **NutriTracker AI** (Telegram-бот + Telegram Mini App + FastAPI + Gemini AI) на любом Linux-сервере (VPS / VDS: Ubuntu, Debian, AlmaLinux, CentOS).

---

## 📋 Оглавление
1. [Требования](#-требования)
2. [Подготовка ключей и настроек](#-1-подготовка-ключей-и-настроек)
3. [Способ 1: Быстрый деплой через Docker Compose (Рекомендуется)](#-способ-1-быстрый-деплой-через-docker-compose-рекомендуется)
4. [Способ 2: Деплой с автоматическим SSL через Caddy](#-способ-2-деплой-с-автоматическим-ssl-через-caddy)
5. [Способ 3: Деплой через классический Nginx + Certbot](#-способ-3-деплой-через-классический-nginx--certbot)
6. [Способ 4: Бесплатный HTTPS через Cloudflare Tunnel (без белого IP)](#-способ-4-бесплатный-https-через-cloudflare-tunnel-без-белого-ip)
7. [Способ 5: Деплой без Docker через systemd](#-способ-5-деплой-без-docker-через-systemd)
8. [Настройка кнопки Mini App в @BotFather](#-настройка-кнопки-mini-app-в-botfather)
9. [Обновление приложения и бэкапы](#-обновление-приложения-и-бэкапы)
10. [Безопасность и Git](#-безопасность-и-git)

---

## 💻 Требования

* Любой VPS / VDS сервер (минимум **1 vCPU, 1 GB RAM, 10 GB SSD**).
* Установленный **Docker** и **Docker Compose** (либо Python 3.12+ и Node.js 20+).
* Токен бота Telegram от [@BotFather](https://t.me/BotFather).
* API-ключ Google Gemini от [Google AI Studio](https://aistudio.google.com/).
* **Обязательно HTTPS**: Telegram Mini App и PWA для iPhone требуют защищенный протокол `https://`!

---

## 🔑 1. Подготовка ключей и настроек

### 1.1. Получение токена Telegram-бота
1. Напишите [@BotFather](https://t.me/BotFather) команду `/newbot`.
2. Задайте имя и юзернейм бота (например, `MyNutriTrackerBot`).
3. Скопируйте выданный `BOT_TOKEN` вида `1234567890:ABCdefGHIjklMNO...`.

### 1.2. Получение ключа Google Gemini
1. Перейдите в [Google AI Studio](https://aistudio.google.com/).
2. Нажмите **«Get API key»** -> **«Create API key»**.
3. Скопируйте ключ `GEMINI_API_KEY`.

### 1.3. Подготовка файла `.env`
На сервере скопируйте шаблон:
```bash
cp .env.example .env
nano .env
```

Заполните переменные:
```env
BOT_TOKEN=ваш_токен_бота
GEMINI_API_KEY=ваш_ключ_gemini
WEB_APP_URL=https://bot.yourdomain.com
GEMINI_MODEL=gemini-3.5-flash
DEFAULT_TIMEZONE=Asia/Almaty
DATABASE_PATH=data/bot.db
API_HOST=0.0.0.0
API_PORT=8000
LOG_LEVEL=INFO
```

---

## 🐳 Способ 1: Быстрый деплой через Docker Compose (Рекомендуется)

Проект использует **multi-stage Dockerfile**: автоматически собирается React frontend на Node.js и упаковывается в легковесный контейнер Python 3.12-slim.

### Шаг 1: Клонирование репозитория
```bash
git clone https://github.com/ВАШ_АККАУНТ/ВАШ_РЕПОЗИТОРИЙ.git
cd telegram-ai-bot
```

### Шаг 2: Настройка .env
```bash
cp .env.example .env
nano .env # вставьте свои ключи
```

### Шаг 3: Запуск в 1 команду
```bash
chmod +x deploy/deploy.sh
./deploy/deploy.sh
```

Либо вручную:
```bash
docker compose up -d --build
```

### Шаг 4: Проверка статуса и логов
```bash
docker compose ps
docker compose logs -f
```

---

## 🔒 Способ 2: Деплой с автоматическим SSL через Caddy

Если у вас есть домен (например, `bot.mydomain.com`), направьте его DNS `A`-запись на IP вашего сервера. Caddy сам автоматически получит и будет продлевать бесплатный SSL-сертификат Let's Encrypt!

В `.env` укажите:
```env
DOMAIN=bot.mydomain.com
WEB_APP_URL=https://bot.mydomain.com
```

Запустите прод-компоуз:
```bash
docker compose -f docker-compose.prod.yml up -d --build
```
Caddy поднимет HTTPS на портах 80 и 443 за несколько секунд без дополнительных настроек!

---

## 🌐 Способ 3: Деплой через классический Nginx + Certbot

Если на сервере уже работает Nginx:

1. Запустите приложение в Docker:
   ```bash
   docker compose up -d --build
   ```
   (Оно слушает `http://127.0.0.1:8000`).

2. Скопируйте конфигурационный файл Nginx:
   ```bash
   sudo cp deploy/nginx.conf /etc/nginx/sites-available/nutritracker.conf
   sudo nano /etc/nginx/sites-available/nutritracker.conf # укажите ваш домен
   sudo ln -s /etc/nginx/sites-available/nutritracker.conf /etc/nginx/sites-enabled/
   sudo nginx -t
   sudo systemctl reload nginx
   ```

3. Получите бесплатный SSL-сертификат Let's Encrypt через Certbot:
   ```bash
   sudo apt install -y certbot python3-certbot-nginx
   sudo certbot --nginx -d bot.yourdomain.com
   ```

---

## 🚇 Способ 4: Бесплатный HTTPS через Cloudflare Tunnel (без белого IP)

Если у сервера нет белого IP или домена, можно использовать бесплатный туннель Cloudflare:

1. Скачайте `cloudflared`:
   ```bash
   curl -L --output cloudflared https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64
   chmod +x cloudflared
   ```
2. Запустите туннель:
   ```bash
   ./cloudflared tunnel --url http://127.0.0.1:8000
   ```
3. Cloudflare выдаст адрес вида `https://xxx-yyy-zzz.trycloudflare.com`. Укажите его в `WEB_APP_URL` в `.env` и перезапустите контейнер!

---

## ⚙️ Способ 5: Деплой без Docker через systemd

Если вы не хотите использовать Docker:

1. Установите зависимости на Ubuntu/Debian:
   ```bash
   sudo apt update && sudo apt install -y python3-venv python3-pip nodejs npm
   ```

2. Соберите фронтенд:
   ```bash
   cd webapp
   npm install
   npm run build
   cd ..
   ```

3. Настройте Python окружение:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install --upgrade pip
   pip install -r requirements.txt
   ```

4. Настройте systemd сервис:
   ```bash
   sudo cp deploy/nutritracker.service /etc/systemd/system/
   sudo nano /etc/systemd/system/nutritracker.service # проверьте пути
   sudo systemctl daemon-reload
   sudo systemctl enable --now nutritracker
   ```

---

## 📱 Настройка кнопки Mini App в @BotFather

Чтобы пользователи открывали приложение по удобной кнопке в Telegram:

1. Откройте [@BotFather](https://t.me/BotFather).
2. Отправьте команду:
   ```text
   /setmenubutton
   ```
3. Выберите вашего бота.
4. Отправьте ссылку на ваш Web App:
   ```text
   https://bot.yourdomain.com
   ```
5. Введите текст кнопки:
   ```text
   🍎 Открыть приложение
   ```

Теперь в левом нижнем углу чата с ботом всегда будет отображаться стильная кнопка для открытия Mini App!

---

## 💾 Обновление приложения и бэкапы

### Обновление на сервере:
```bash
git pull origin main
docker compose up -d --build
```
База данных `data/bot.db` сохраняется на хосте в папке `./data/` и **не стирается** при обновлениях контейнера.

### Резервное копирование базы данных:
База данных находится в одном файле `data/bot.db`:
```bash
# Создать резервную копию
sqlite3 data/bot.db ".backup 'data/backup_$(date +%Y%m%d).db'"
```

---

## 🛡 Безопасность и Git

Перед отправкой кода на GitHub проект уже полностью защищен:

* Файл `.env` **добавлен в `.gitignore`** и никогда не попадет в репозиторий.
* Папка базы данных `data/*.db` **исключена из Git**.
* Виртуальное окружение `.venv` и зависимости `node_modules` **исключены из Git**.
* Секретные ключи передаются исключительно через переменные окружения.
