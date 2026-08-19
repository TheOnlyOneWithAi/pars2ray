# Pars2Ray Enterprise

[English](README.md) | [فارسی](README.fa.md) | [Русский](README.ru.md)

Pars2Ray یک کنترل‌پلین حرفه‌ای برای مدیریت و بهینه‌سازی شبکه است که از یک سرور Master، چند Node Agent سبک، PostgreSQL، Redis، workerهای پس‌زمینه و رابط React/TypeScript تشکیل شده است.

## ساختار مخزن

```text
master/       API اصلی، منطق کنترل‌پلین، دیتابیس و worker
agent/        عامل سبک نود؛ بدون رابط کاربری و دیتابیس
frontend/     پنل سازمانی React + TypeScript
migrations/   migrationهای Alembic
installer/    نصب اولیه Master و Node از طریق SSH
deploy/       Docker Compose، اسکریپت اجرا و پشتیبان‌گیری
tests/        تست‌های قطعی backend
```

## شروع سریع

```bash
cp .env.example .env
# تمام مقادیر replace-with-* را تغییر دهید
docker compose --env-file .env -f deploy/docker-compose.yml up -d --build
```

پس از اجرا، پنل در `http://localhost:8000/` در دسترس است. مستندات OpenAPI 3.1 نیز از مسیرهای `/docs`، `/redoc` و `/openapi.json` ارائه می‌شوند. حساب Super Admin اولیه از متغیرهای `ADMIN_USER`، `ADMIN_PASSWORD` و `ADMIN_EMAIL` ساخته می‌شود.

## قابلیت‌های اصلی

- احراز هویت JWT، چرخش Refresh Token، API Key و RBAC
- نقش‌های Super Admin، Admin، Operator، Reseller و User
- مدیریت پویا و نامحدود نودها از طریق متغیرهای محیطی مانند `DE1`، `DE2` و `NL1`
- Heartbeat، جمع‌آوری Metrics، Benchmark، همگام‌سازی تنظیمات، Rollback و گزارش نسخه
- پشتیبانی از Xray و sing-box با فرمان‌های از پیش تعریف‌شده
- ذخیره تاریخچه آزمایش‌ها در سطوح `GOLDEN`، `VERIFIED` و `EXPERIMENTAL`
- بهینه‌ساز مبتنی بر Rule Engine، حافظه آزمایش‌ها، Validator و Canary
- مدیریت کاربران، پلن‌ها، اشتراک‌ها، ترافیک، API Key و Audit Log
- Docker Compose، PostgreSQL، Redis، Alembic، backup و GitHub Actions CI

## امنیت

- رمزهای عبور با Argon2id هش می‌شوند.
- Refresh Tokenها و API Keyها به‌صورت هش‌شده ذخیره می‌شوند.
- توکن نود و تنظیمات حساس Route به‌صورت رمزنگاری‌شده نگهداری می‌شوند.
- Agent هیچ endpoint برای اجرای shell دلخواه، آپلود فایل یا نمایش Swagger ندارد.
- اطلاعات حساس نودها و Routeها در API، رابط کاربری یا لاگ خام نمایش داده نمی‌شوند.

## بهینه‌ساز هوشمند

مدل هوش مصنوعی مستقیماً تولید را کنترل نمی‌کند. مسیر تصمیم‌گیری شامل Telemetry، Rule Engine، حافظه، تصمیم AI، Validator، Canary و سپس Production است. درخواست‌های عادی و تغییرات جزئی بدون فراخوانی مدل با نتیجه `KEEP` مدیریت می‌شوند.

یکپارچه‌سازی OpenAI از Responses API، خروجی ساختاریافته JSON Schema، `store=false`، reasoning کم‌هزینه و prompt caching استفاده می‌کند.

## حالت National Mode

اگر سرویس‌های خارجی یا API هوش مصنوعی در دسترس نباشند، Pars2Ray با حافظه آزمایش‌ها، تنظیمات Golden، قوانین محلی و موتور Benchmark به کار ادامه می‌دهد. سیستم ابتدا روش‌های موفق قبلی را آزمایش می‌کند و سپس فقط از templateهای داخلی و محدود استفاده می‌کند.

## حمایت از پروژه

اگر Pars2Ray برای شما مفید بوده یا در مدیریت زیرساخت صرفه‌جویی ایجاد کرده است، می‌توانید از ادامه توسعه آن حمایت کنید. کمک‌ها صرف نگهداری، تست و هزینه‌های زیرساخت می‌شوند.

```text
UQCWzDFlNgoLT55ZvtGC13W5zxwkJzwdBnh8Zv-IeYvX5pFc
```

استفاده، ستاره‌دادن و معرفی پروژه نیز کمک بزرگی به ادامه مسیر آن است.

## بررسی و تست

```bash
PYTHONPATH=master pytest -q tests
python -m compileall -q master/app agent/app installer
cd frontend && npm install && npm run typecheck && npm run build
```

برای جزئیات بیشتر، فایل‌های [معماری](ARCHITECTURE.md)، [API](API.md)، [استقرار](DEPLOYMENT.md) و [امنیت](SECURITY.md) را ببینید.
