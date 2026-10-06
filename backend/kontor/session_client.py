"""
عميل خدمة جلسة ZNET من جهة Django: ينادي الخدمة المستقلّة ويحلّل ردّها.

عنوان الخدمة من `KONTOR_SESSION_URL` (افتراضاً http://kontor-session:8700).
يُبقي المتصفّح خارج عمّال gunicorn — هنا طلب HTTP داخليّ خفيف فقط.
"""
import os
from datetime import timedelta

import requests

from .panel_parse import parse_offers, parse_operator

# رمزنا ⇐ صيغة ZNET في رابط العروض
_TO_ZNET = {"Turkcell": "TURKCELL", "Vodafone": "VODAFONE",
            "Avea": "AVEA", "Callback": "CALLBACK"}


def _base() -> str:
    return os.environ.get("KONTOR_SESSION_URL", "http://kontor-session:8700").rstrip("/")


class SessionError(Exception):
    """تعذّر الوصول إلى خدمة الجلسة أو فشلها."""


def _account_headers(ignore_switch: bool = False) -> dict:
    """
    حساب لوحة الكشف من إعداد المنصّة (/sorgula) — يُمرَّر إلى الخدمة في ترويسات.
    غير مضبوط ⇐ لا ترويسات فتستعمل الخدمة متغيّرات البيئة القديمة. معطَّل ⇐ خطأ صريح.
    """
    from .models import KontorSessionConfig
    cfg = KontorSessionConfig.objects.first()
    if cfg is None or not cfg.configured:
        return {}
    if not cfg.enabled and not ignore_switch:
        raise SessionError("كشف الشركة والعروض موقوف من إدارة المنصّة")
    return {"X-Kontor-Base": cfg.base_url.rstrip("/"), "X-Kontor-User": cfg.username,
            "X-Kontor-Pass": cfg.password, "X-Kontor-Image": (cfg.security_image or "D").strip()}


def _record(ok: bool, error: str = ""):
    """آخر نجاح/خطأ — يراه مالك المنصّة في /sorgula فيعرف حال الخدمة بنظرة."""
    from django.utils import timezone

    from .models import KontorSessionConfig
    cfg = KontorSessionConfig.objects.first()
    if cfg is None:
        return
    if ok:
        KontorSessionConfig.objects.filter(pk=cfg.pk).update(last_ok_at=timezone.now(), last_error="")
    else:
        KontorSessionConfig.objects.filter(pk=cfg.pk).update(last_error=error[:300])


def _get(path: str, params: dict, ignore_switch: bool = False) -> dict:
    headers = _account_headers(ignore_switch)
    try:
        r = requests.get(f"{_base()}{path}", params=params, headers=headers, timeout=(5, 90))
    except requests.RequestException as e:
        _record(False, f"تعذّر الاتصال بخدمة الجلسة: {e}")
        raise SessionError(f"تعذّر الاتصال بخدمة الجلسة: {e}")
    if r.status_code != 200:
        detail = (r.json().get("detail") if r.headers.get("content-type", "").startswith("application/json") else r.text)
        _record(False, detail or f"HTTP {r.status_code}")
        raise SessionError(detail or f"HTTP {r.status_code}")
    if path != "/health":
        _record(True)
    return r.json()


def check_login() -> bool:
    """
    اختبار حساب الكشف: تدخل الخدمة باللوحة وتتأكّد أن صفحة Kontor جاهزة.
    يتجاهل مفتاح الإيقاف عمداً — المالك يختبر الحساب قبل أن يفعّله للمتاجر.
    """
    return bool(_get("/login", {}, ignore_switch=True).get("ok"))


# مدّة الكاش: شركة الرقم نادراً ما تتغيّر (نقل الرقم)، والعروض تتبدّل يومياً
OPERATOR_TTL = timedelta(days=30)
OFFERS_TTL = timedelta(hours=24)


def _cached(kind: str, gsm: str, operator: str = ""):
    from django.utils import timezone

    from .models import KontorLookupCache
    row = KontorLookupCache.objects.filter(
        kind=kind, gsm=gsm, operator=operator, expires_at__gt=timezone.now()).first()
    return row.data.get("v") if row else None


def _store(kind: str, gsm: str, value, ttl: timedelta, operator: str = ""):
    from django.utils import timezone

    from .models import KontorLookupCache
    now = timezone.now()
    KontorLookupCache.objects.filter(expires_at__lte=now).delete()  # المنتهي يُمسح تلقائياً
    KontorLookupCache.objects.update_or_create(
        kind=kind, gsm=gsm, operator=operator,
        defaults={"data": {"v": value}, "expires_at": now + ttl})


def forget_offers(gsm: str):
    """بعد شحن الرقم تتغيّر عروضه — يُنسى كاشها فيُجلب جديداً عند الكشف التالي."""
    from .models import KontorLookupCache
    KontorLookupCache.objects.filter(kind=KontorLookupCache.Kind.OFFERS, gsm=gsm).delete()


def detect_operator(gsm: str, ignore_switch: bool = False) -> str | None:
    """
    الشركة المكتشفة ⇐ رمزنا (Turkcell/Vodafone/Avea/Callback) أو None.
    من الكاش إن كُشف خلال شهر. ignore_switch (اختبار /sorgula) يتجاوز الكاش فيختبر الحساب فعلاً.
    """
    if not ignore_switch:
        hit = _cached("operator", gsm)
        if hit:
            return hit
    html = _get("/detect", {"gsm": gsm}, ignore_switch).get("html", "")
    op = parse_operator(html)
    if op:  # الفشل لا يُحفظ — يُعاد الكشف في المرّة التالية
        _store("operator", gsm, op, OPERATOR_TTL)
    return op


def fetch_offers(gsm: str, operator: str, ignore_switch: bool = False) -> list[dict]:
    """عروض الرقم الخاصة (بصيغة panel_parse). operator برمزنا. من الكاش إن جُلبت خلال 24 ساعة."""
    if not ignore_switch:
        hit = _cached("offers", gsm, operator)
        if hit is not None:
            return hit
    znet_op = _TO_ZNET.get(operator, operator.upper())
    html = _get("/offers", {"gsm": gsm, "operator": znet_op}, ignore_switch).get("html", "")
    offers = parse_offers(html)
    if offers:  # ردٌّ فارغ قد يكون عطلاً عابراً — لا يُحفظ يوماً كاملاً
        _store("offers", gsm, offers, OFFERS_TTL, operator)
    return offers


def health() -> bool:
    try:
        return bool(_get("/health", {}).get("ok"))
    except SessionError:
        return False
