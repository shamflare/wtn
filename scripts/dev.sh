#!/usr/bin/env bash
# تشغيل النظام محلياً (Backend + Frontend) بأمر واحد.
# المتطلّبات: Python 3.11+ · Node 18+ · PostgreSQL 14+ يعمل محلياً.
set -e
# التطوير المحلي يطلب وضع التطوير صراحةً — الإنتاج آمنٌ افتراضياً (DEBUG=0)
export DEBUG=1
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo "==> [1/5] إعداد قاعدة البيانات (إن لم تكن موجودة)"
psql -U postgres -tc "SELECT 1 FROM pg_roles WHERE rolname='wtn'" | grep -q 1 || \
  psql -U postgres -c "CREATE USER wtn WITH PASSWORD 'wtn_dev_pass' CREATEDB;"
psql -U postgres -tc "SELECT 1 FROM pg_database WHERE datname='wtn_db'" | grep -q 1 || \
  psql -U postgres -c "CREATE DATABASE wtn_db OWNER wtn;"

echo "==> [2/5] الخلفية: البيئة والحزم"
cd "$ROOT/backend"
[ -d venv ] || python3 -m venv venv
venv/bin/pip install -q -r requirements.txt

echo "==> [3/5] الجداول والبيانات التجريبية"
venv/bin/python manage.py migrate
venv/bin/python manage.py seed_demo

echo "==> [4/5] تشغيل الخلفية على :8000"
venv/bin/python manage.py runserver 127.0.0.1:8000 &

echo "==> [5/5] الواجهة على :5173"
cd "$ROOT/frontend"
npm install
npm run dev -- --host 0.0.0.0 --port 5173

# افتح المتصفح على: http://localhost:5173
# دخول:  5550000007 / admin123
