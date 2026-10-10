"""
أمن الدخول: القفل المتدرّج · التحقق بخطوتين (2FA) · إسقاط الجلسات.

القفل المتدرّج (قرار المالك 2026-10-10):
  محاولةٌ خاطئة ⇐ تنبيه · الثانية ⇐ انتظار ربع ساعة · الثالثة ⇐ ساعة ·
  الرابعة ⇐ يُقفل الحساب حتى يغيّر كلمةَ سرّه الدورُ الأعلى منه.
  ومالك المنصّة لا يُقفل دائماً (لا أحد فوقه) — يبقى انتظار الساعة، وحسابه محميٌّ
  بالتحقق بخطوتين **الإلزامي**. فلا يستطيع أحدٌ أن يُغلق المنصّة على صاحبها.

والتحقق بخطوتين اختياريٌّ لكل الأدوار، إلزاميٌّ لمالك المنصّة: أوّل دخولٍ له بلا 2FA
يعرض رمز QR ولا يُصدر جلسةً حتى يؤكّد الرمز. ورمزٌ خاطئ يُعدّ محاولةً خاطئة،
والرمز نفسه لا يُقبل مرّتين.

والجلسة (JWT) تحمل بصمةً من كلمة السر ونسخة الجلسات (`User.session_stamp`):
تغيير كلمة السر أو «الخروج من كل الأجهزة» يُسقط كل الجلسات القديمة فوراً.
"""
from datetime import timedelta

import pyotp
from django.core.cache import cache
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken

from .models import Tenant, User

GENERIC = "بيانات الدخول غير صحيحة"
LOCKED = "أُوقف الحساب بعد محاولات دخول خاطئة متكرّرة. راجع من أنشأ حسابك ليمنحك كلمة سرّ جديدة."
STEPS = {2: 15, 3: 60}          # المحاولة الخاطئة رقم ⇐ دقائق الانتظار
PERMANENT_AT = 4                # الرابعة ⇐ قفلٌ دائم (لغير مالك المنصّة)
IP_LIMIT, IP_WINDOW = 20, 15 * 60   # محاولاتٌ خاطئة من عنوانٍ واحد خلال ربع ساعة
ISSUER = "ahlacard"


# ─────────────────────────── الجلسات ───────────────────────────

def tokens_for(user: User) -> dict:
    refresh = RefreshToken.for_user(user)
    refresh["sv"] = user.session_stamp()        # يُنسخ إلى توكن الوصول
    return {"access": str(refresh.access_token), "refresh": str(refresh)}


def session_valid(user: User, token) -> bool:
    """يقبل التوكن إن طابقت بصمتُه بصمةَ الحساب الآن."""
    return token.get("sv") == user.session_stamp()


def tenant_suspended(user: User) -> bool:
    t = getattr(user, "tenant", None)
    return bool(t and user.role != User.Role.PLATFORM_OWNER and t.status == Tenant.Status.SUSPENDED)


# ─────────────────────────── التحقق بخطوتين ───────────────────────────

def verify_totp(user: User, code: str) -> bool:
    """
    يتحقق من الرمز (± 30 ثانية) ويرفض إعادة استعمال رمزٍ قُبل من قبل. يحفظ خطوته.
    """
    code = "".join(ch for ch in str(code or "") if ch.isdigit())
    if len(code) != 6 or not user.totp_secret:
        return False
    totp = pyotp.TOTP(user.totp_secret)
    now = timezone.now()
    current = totp.timecode(now)
    for step in (current - 1, current, current + 1):
        if step > user.totp_last_step and totp.generate_otp(step) == code:
            User.objects.filter(pk=user.pk).update(totp_last_step=step)
            user.totp_last_step = step
            return True
    return False


def _qr_svg(uri: str) -> str:
    import segno
    return segno.make(uri, error="m").svg_data_uri(scale=5, border=2)


def setup_payload(user: User) -> dict:
    """سرٌّ معلّق (يُنشأ مرّةً ويبقى حتى يُؤكَّد) مع رمز QR لتطبيق المصادقة."""
    if not user.totp_secret:
        user.totp_secret = pyotp.random_base32()
        user.save(update_fields=["totp_secret"])
    uri = pyotp.TOTP(user.totp_secret).provisioning_uri(name=user.login_id, issuer_name=ISSUER)
    return {"secret": user.totp_secret, "otpauth": uri, "qr": _qr_svg(uri)}


# ─────────────────────────── الدخول ───────────────────────────

def _client_ip(request) -> str:
    # خلف Caddy: يستبدل X-Forwarded-For بعنوان الزائر الحقيقي، فأوّله هو العميل
    fwd = request.META.get("HTTP_X_FORWARDED_FOR", "")
    return (fwd.split(",")[0].strip() if fwd else request.META.get("REMOTE_ADDR", "")) or "?"


def _wait_text(minutes: int) -> str:
    return "ربع ساعة" if minutes == 15 else "ساعة" if minutes == 60 else f"{minutes} دقيقة"


def _fail(user: User, request) -> Response:
    """محاولةٌ خاطئة: يرفع العدّاد ويطبّق الانتظار أو القفل، ويعيد الرسالة المناسبة."""
    from django.db.models import F
    ip_key = f"login-fail:{_client_ip(request)}"
    cache.set(ip_key, cache.get(ip_key, 0) + 1, IP_WINDOW)

    User.objects.filter(pk=user.pk).update(failed_login_count=F("failed_login_count") + 1)
    user.refresh_from_db(fields=["failed_login_count"])
    n = user.failed_login_count
    fields = []
    if n >= PERMANENT_AT and user.role != User.Role.PLATFORM_OWNER:
        user.locked_at = timezone.now()
        fields.append("locked_at")
        msg, code = LOCKED, status.HTTP_403_FORBIDDEN
    elif n in STEPS or n >= PERMANENT_AT:
        minutes = STEPS.get(n, 60)
        user.lock_until = timezone.now() + timedelta(minutes=minutes)
        fields.append("lock_until")
        tail = " — المحاولة الخاطئة التالية توقف الحساب" if n == 3 and user.role != User.Role.PLATFORM_OWNER else ""
        msg = f"{GENERIC}. حاول بعد {_wait_text(minutes)}{tail}"
        code = status.HTTP_429_TOO_MANY_REQUESTS
    else:
        msg, code = f"{GENERIC} — بعد محاولةٍ خاطئةٍ أخرى ستنتظر ربع ساعة", status.HTTP_401_UNAUTHORIZED
    if fields:
        user.save(update_fields=fields)
    return Response({"detail": msg}, status=code)


def login(request, data) -> Response:
    if cache.get(f"login-fail:{_client_ip(request)}", 0) >= IP_LIMIT:
        return Response({"detail": "محاولاتٌ خاطئة كثيرة من هذا الجهاز — حاول بعد ربع ساعة"},
                        status=status.HTTP_429_TOO_MANY_REQUESTS)
    user = User.objects.filter(login_id=data["login_id"]).select_related("tenant").first()
    if user is None:
        User().set_password(data["password"])    # نفس زمن الحساب الموجود — لا يُعرف بالتوقيت
        ip_key = f"login-fail:{_client_ip(request)}"
        cache.set(ip_key, cache.get(ip_key, 0) + 1, IP_WINDOW)
        return Response({"detail": GENERIC}, status=status.HTTP_401_UNAUTHORIZED)

    # على عنوان متجرٍ بعينه لا يدخل إلا أهلُه (قبل كلمة السر: لا يُقفل بلا ذنب)
    store = getattr(request, "store", None)
    if store is not None and user.tenant_id != store.id:
        return Response({"detail": f"هذا الحساب ليس من متجر «{store.name}» — ادخل من عنوان متجرك."},
                        status=status.HTTP_403_FORBIDDEN)

    # القفل والانتظار قبل كلمة السر: لا تُختبر كلمةٌ على حسابٍ ينتظر
    if user.is_locked:
        return Response({"detail": LOCKED}, status=status.HTTP_403_FORBIDDEN)
    if user.lock_until and user.lock_until > timezone.now():
        left = max(1, int((user.lock_until - timezone.now()).total_seconds() // 60) + 1)
        return Response({"detail": f"الحساب ينتظر بعد محاولاتٍ خاطئة — حاول بعد {left} دقيقة"},
                        status=status.HTTP_429_TOO_MANY_REQUESTS)

    if not user.check_password(data["password"]):
        return _fail(user, request)

    if user.status == User.Status.PENDING:
        return Response({"detail": "طلب تسجيلك قيد المراجعة لدى إدارة المتجر — تستطيع الدخول فور قبوله"},
                        status=status.HTTP_403_FORBIDDEN)
    if user.status != User.Status.ACTIVE:
        return Response({"detail": "الحساب معطّل"}, status=status.HTTP_403_FORBIDDEN)
    if tenant_suspended(user):
        return Response({"detail": "المتجر موقوف — تواصل مع إدارة المنصّة"}, status=status.HTTP_403_FORBIDDEN)

    code = data.get("totp", "")
    # مالك المنصّة: التحقق بخطوتين إلزامي — أوّل دخولٍ بلا 2FA يُعدّه هنا
    if user.role == User.Role.PLATFORM_OWNER and not user.totp_enabled:
        if not code:
            return Response({"require_totp_setup": True, **setup_payload(user)})
        if not verify_totp(user, code):
            return _fail(user, request)
        user.totp_enabled = True
        user.save(update_fields=["totp_enabled"])
    elif user.totp_enabled:
        if not code:
            return Response({"require_totp": True})
        if not verify_totp(user, code):
            return _fail(user, request)

    user.failed_login_count = 0
    user.lock_until = None
    user.save(update_fields=["failed_login_count", "lock_until"])
    from .serializers import UserSerializer
    return Response({"user": UserSerializer(user).data, "tokens": tokens_for(user)})


# ─────────────────────────── إعداد 2FA من الحساب ───────────────────────────

@api_view(["GET", "POST", "DELETE"])
@permission_classes([IsAuthenticated])
def two_factor_view(request):
    """
    GET    ⇐ {enabled, required}
    POST   {} ⇐ بدء التفعيل: سرٌّ معلّق + QR · POST {code} ⇐ تأكيد وتفعيل
    DELETE {password, code} ⇐ إيقاف (لغير مالك المنصّة — عليه إلزامي)
    """
    user = request.user
    required = user.role == User.Role.PLATFORM_OWNER
    if request.method == "GET":
        return Response({"enabled": user.totp_enabled, "required": required})
    if request.method == "POST":
        if user.totp_enabled:
            return Response({"detail": "التحقق بخطوتين مفعّل أصلاً"}, status=400)
        if not request.data.get("code"):
            return Response(setup_payload(user))
        if not verify_totp(user, request.data["code"]):
            return Response({"detail": "الرمز غير صحيح — تأكّد من وقت الجهاز وأعد المحاولة"}, status=400)
        user.totp_enabled = True
        user.save(update_fields=["totp_enabled"])
        return Response({"enabled": True})
    # DELETE
    if required:
        return Response({"detail": "التحقق بخطوتين إلزامي لمالك المنصّة"}, status=400)
    if not user.totp_enabled:
        return Response({"enabled": False})
    if not user.check_password(str(request.data.get("password") or "")) or \
            not verify_totp(user, request.data.get("code")):
        return Response({"detail": "كلمة السر أو الرمز غير صحيح"}, status=400)
    user.totp_enabled = False
    user.totp_secret = ""
    user.save(update_fields=["totp_enabled", "totp_secret"])
    return Response({"enabled": False})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def logout_all_view(request):
    """الخروج من كل الأجهزة: يرفع نسخة الجلسات فتسقط كل التوكنات القائمة."""
    from django.db.models import F
    User.objects.filter(pk=request.user.pk).update(token_version=F("token_version") + 1)
    return Response({"ok": True})
