"""إعدادات اختبار محليّة: sqlite بدل Postgres — لا يُستعمل في النشر."""
from .settings import *  # noqa: F401,F403

DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}

# الاختبارات تستعمل روابط وهمية (http://a) — حارس SSRF يُختبر وحده في core/tests
NET_GUARD = False
