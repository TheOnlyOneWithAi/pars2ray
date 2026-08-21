# Pars2Ray Enterprise

[English](README.md) | [فارسی](README.fa.md) | [Русский](README.ru.md)

Pars2Ray یک کنترل‌پلین حرفه‌ای برای مدیریت شبکه است که از Master، Node Agent، PostgreSQL، Redis، worker و پنل React/TypeScript تشکیل شده است.

## نصب در حد یک پنل

ساختار نصب Pars2Ray را عمداً مثل پنل‌های آماده ساده کرده‌ایم: **یک دستور، بدون ساختن یا ویرایش دستی `.env`**.

```bash
curl -fsSL https://raw.githubusercontent.com/TheOnlyOneWithAi/pars2ray/main/install.sh | sudo bash
```

نصاب به‌صورت خودکار Docker/Compose را در صورت نیاز نصب می‌کند، نسخه فعلی پروژه را دریافت می‌کند، secretهای امنیتی را می‌سازد، یک subnet مناسب برای Docker انتخاب می‌کند، اطلاعات پنل را می‌پرسد، PostgreSQL و Redis و Master و Worker را بالا می‌آورد، migrationها را اجرا می‌کند، سلامت پنل را بررسی می‌کند و در پایان آدرس پنل را نمایش می‌دهد.

اگر نصب قبلی وجود داشته باشد، اطلاعات `.env` و داده‌های Docker حفظ می‌شوند.

### فقط این ۴ مورد پرسیده می‌شود

در اولین نصب:

1. نام کاربری پنل
2. ایمیل پنل
3. رمز عبور پنل
4. پورت پنل

رمز PostgreSQL، JWT secret، Master secret و تنظیمات شبکه به‌صورت خودکار ساخته می‌شوند. **لازم نیست `.env` را دستی بسازید یا تغییر دهید.**

پس از پایان نصب، پنل با آدرسی شبیه زیر آماده است:

```text
http://SERVER_IP:8000/
```

### بعد از نصب

دیگر لازم نیست با Docker Compose و مسیرهای طولانی کار کنید:

```bash
pars2ray status
pars2ray restart
pars2ray logs
pars2ray update
```

دستورهای موجود شامل `start`، `stop`، `restart`، `status`، `logs`، `master-logs`، `worker-logs`، `update`، `config`، `install` و `uninstall` هستند.

### نصب مستقیم نسخه قدیمی‌تر

در صورت نیاز، اسکریپت اصلی هم مستقیماً قابل اجراست:

```bash
curl -fsSL https://raw.githubusercontent.com/TheOnlyOneWithAi/pars2ray/main/deploy/install.sh | sudo bash
```

## نصب دستی برای توسعه

برای توسعه‌دهندگان، روش دستی همچنان وجود دارد:

```bash
cp .env.example .env
docker compose --env-file .env -f deploy/docker-compose.yml up -d --build
```

## قابلیت‌های اصلی

پنل شامل telemetry زنده، مدیریت نودها، route activation، inventory پروتکل‌ها، experimentها، optimizer کنترل‌شده، RBAC، اشتراک‌ها، پلن‌ها، API Key، تنظیمات runtime، AI اختیاری و Audit Log است. زبان‌های فارسی RTL، انگلیسی و روسی از داخل پنل قابل انتخاب هستند.

## تست

```bash
PYTHONPATH=master pytest -q tests
python -m compileall -q master/app agent/app installer
cd frontend && npm ci && npm run typecheck && npm run build
```

برای جزئیات معماری، استقرار و امنیت، فایل‌های `ARCHITECTURE.md`، `DEPLOYMENT.md` و `SECURITY.md` را ببینید.
