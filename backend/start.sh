#!/usr/bin/env bash
# سكربت الإقلاع في الإنتاج (Render): ترحيلات + بذور أوّلية (مرة واحدة) + gunicorn.
set -e

python manage.py migrate --noinput

# البذور: seed_demo متسامح (get_or_create) فيُشغَّل دائماً ليُنشئ أي حسابات ناقصة
# (مثل الوكيل الكبير)؛ أما بذور الكتالوج الثقيلة فتُزرع مرّة واحدة فقط (قاعدة فارغة).
python - <<'PY'
import os, django, subprocess
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()
from catalog.models import Product

# نسخة عميل (SEED_DEMO=0): لا حسابات تجريبية بكلمات سرٍّ معروفة ولا كتالوج وهميّ.
# حساباتها يصنعها `provision_instance` مرّةً بكلمات سرٍّ عشوائية.
demo = os.environ.get("SEED_DEMO", "1") != "0"

if demo:
    subprocess.run(["python", "manage.py", "seed_demo"], check=False)
else:
    print("SEED_DEMO=0 — نسخة عميل: البذور التجريبية متروكة")

if demo and not Product.objects.exists():
    for cmd in ["seed_catalog", "seed_providers",
                "seed_pools", "seed_payments", "seed_platform"]:
        print(f"seeding: {cmd}")
        subprocess.run(["python", "manage.py", cmd], check=False)
else:
    print("catalog seeds skipped (data already present)")

# المكتبة التجريبية + عرض التنفيذ التلقائي — للنسخة التجريبية وحدها. في نسخة
# العميل كانت seed_library تُعيد مع كل إقلاعٍ أيَّ لعبةٍ تجريبية حذفها المالك
# من مكتبته (get_or_create بالاسم) — والمكتبة الآن تُملأ من «مصادر المكتبة».
if demo:
    subprocess.run(["python", "manage.py", "seed_library"], check=False)
    subprocess.run(["python", "manage.py", "seed_auto"], check=False)
# طرق الدفع وسعر الصرف العام — متسامحة، تُنشئ الناقص وتترك تعديلات المالك
subprocess.run(["python", "manage.py", "seed_payment_methods"], check=False)
# seed_routing_test لا يُشغَّل في النشر: كان يزرع «بنك فارغ (للاختبار)» ومتجر
# مورّد وهميّاً في بيئة الإنتاج، ويظهران للمالك كمزوّدَين حقيقيَّين. يبقى
# الأمر متاحاً يدوياً للتجارب المحلية.
PY

exec gunicorn config.wsgi:application \
  --bind "0.0.0.0:${PORT:-8000}" \
  --workers 2 --timeout 180
