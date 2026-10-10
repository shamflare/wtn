"""
حدودٌ بسيطة لمنع الإغراق — كم مرّةً يفعل المستخدم شيئاً في فترة.

ليست حاجزاً أمنياً صلباً (الذاكرة المؤقّتة محليّة لكل عامل gunicorn فالحدّ الفعلي
مضاعف) — بل كبحٌ لحلقةٍ مجنونة أو لمن يملأ القاعدة صوراً أو يُثقل جلسة ZNET.
"""
from django.core.cache import cache


def hit(key: str, limit: int, window: int) -> bool:
    """يعدّ مرّةً ويعيد True إن تجاوز `limit` خلال `window` ثانية."""
    k = f"rl:{key}"
    if cache.add(k, 1, window):          # أوّل مرّةٍ في النافذة — تبدأ مدّتها الآن
        return 1 > limit
    try:
        return cache.incr(k) > limit
    except ValueError:                   # انتهت النافذة بين السطرين
        cache.add(k, 1, window)
        return False
