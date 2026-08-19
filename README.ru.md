# Pars2Ray Enterprise

[English](README.md) | [فارسی](README.fa.md) | [Русский](README.ru.md)

Pars2Ray — производственная платформа управления и оптимизации сети. Она состоит из одного Master-сервера, нескольких лёгких Node Agent, PostgreSQL, Redis, фоновых workers и панели управления на React/TypeScript.

## Структура репозитория

```text
master/       основной API, логика control plane, база данных и worker
agent/        лёгкий агент узла без UI и базы данных
frontend/     корпоративная панель React + TypeScript
migrations/   миграции Alembic
installer/    начальная установка Master и Node по SSH
deploy/       Docker Compose, запуск и резервное копирование
tests/        детерминированные backend-тесты
```

## Быстрый запуск

Установка одной командой на Ubuntu/Debian (перед production-запуском проверьте `deploy/install.sh`):

```bash
curl -fsSL https://raw.githubusercontent.com/parsahoseini549-star/pars2ray/main/deploy/install.sh | sudo bash
```

Скрипт при необходимости устанавливает Docker/Compose, создаёт отсутствующие секреты, сохраняет существующий `.env`, запускает Master и Worker и ждёт успешного ответа `/health`. Для настройки используйте `PARS2RAY_ADMIN_PASSWORD` или `PARS2RAY_INSTALL_DIR` перед командой.

```bash
cp .env.example .env
# замените все значения replace-with-*
docker compose --env-file .env -f deploy/docker-compose.yml up -d --build
```

После запуска панель доступна по адресу `http://localhost:8000/`. Документация OpenAPI 3.1 находится в `/docs`, `/redoc` и `/openapi.json`. Начальный Super Admin создаётся из `ADMIN_USER`, `ADMIN_PASSWORD` и `ADMIN_EMAIL`.

Панель включает телеметрию трафика, операции с узлами, активацию маршрутов, обзор протоколов, повышение экспериментов, защищённый запуск Optimizer, управление пользователями RBAC, подписками, тарифами, API Key, настройками среды и Audit Log. В интерфейсе доступны английский, персидский с RTL и русский языки. Все таблицы, графики и действия используют реальные API Master; интерфейс не создаёт демонстрационные записи.

## Основные возможности

- JWT-аутентификация, ротация Refresh Token, API Key и RBAC
- Роли Super Admin, Admin, Operator, Reseller и User
- Динамическое управление неограниченным числом узлов через переменные `DE1`, `DE2`, `NL1` и другие
- Heartbeat, Metrics, Benchmark, синхронизация конфигурации, Rollback и отчёт о версии
- Адаптеры Xray и sing-box с фиксированным набором разрешённых команд
- Память экспериментов уровней `GOLDEN`, `VERIFIED` и `EXPERIMENTAL`
- Оптимизатор с Rule Engine, памятью, Validator и Canary
- Управление пользователями, тарифами, подписками, трафиком, API Key и Audit Log
- Docker Compose, PostgreSQL, Redis, Alembic, резервные копии и GitHub Actions CI

## Безопасность

- Пароли хешируются с помощью Argon2id.
- Refresh Token и API Key хранятся только в хешированном виде.
- Токены узлов и чувствительные настройки Route шифруются при хранении.
- Agent не предоставляет произвольное выполнение shell-команд, загрузку файлов или Swagger UI.
- Чувствительные данные узлов и маршрутов не возвращаются в API, UI или необработанных логах.

## AI-оптимизатор

Модель AI не управляет production напрямую. Решение проходит через Telemetry, Rule Engine, память экспериментов, AI, Validator, Canary и только затем может попасть в Production. Обычные проверки и небольшие изменения обрабатываются локально с результатом `KEEP`, без вызова модели.

Интеграция OpenAI использует Responses API, строгий JSON Schema, `store=false`, низкий reasoning effort и кэширование промпта.

## National Mode

Если внешние сервисы или AI API недоступны, Pars2Ray продолжает работать на основе памяти экспериментов, Golden-конфигураций, локальных правил и Benchmark Engine. Сначала повторно тестируются ранее успешные методы, затем используются только встроенные ограниченные шаблоны.

## Поддержать проект

Если Pars2Ray экономит ваше время или помогает управлять инфраструктурой, вы можете поддержать дальнейшую разработку. Взносы помогают покрывать обслуживание, тестирование и инфраструктурные расходы.

```text
UQCWzDFlNgoLT55ZvtGC13W5zxwkJzwdBnh8Zv-IeYvX5pFc
```

Использование проекта, звезда на GitHub и рекомендация другим также очень помогают.

## Проверка

```bash
PYTHONPATH=master pytest -q tests
python -m compileall -q master/app agent/app installer
cd frontend && npm ci && npm run typecheck && npm run build
```

Дополнительная информация находится в документах [Architecture](ARCHITECTURE.md), [API](API.md), [Deployment](DEPLOYMENT.md) и [Security](SECURITY.md).
