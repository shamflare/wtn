"""API views للقلب: تسجيل الدخول (JWT + 2FA)، المستخدم، الوكلاء، المحفظة."""
import re
from decimal import Decimal, InvalidOperation

import pyotp
from django.db import models
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken

from . import currency, services
from .text import clean_login_id
from .models import (
    LOGIN_ATTEMPTS_BEFORE_LOCK, Invoice, Tenant, User, Wallet, WalletTransaction,
)
from .serializers import (
    LoginSerializer, SiteSettingsSerializer, SmsSettingsSerializer, UserSerializer,
)

# رسالة واحدة للقفل — لا تكشف سبباً ولا تلوم، وتقول لمن يُراجَع
LOCKED_MESSAGE = (
    "قُفل الحساب بعد محاولات دخول فاشلة. "
    "راجع صاحب المتجر ليمنحك كلمة سرّ جديدة."
)


def _tokens_for(user: User) -> dict:
    refresh = RefreshToken.for_user(user)
    return {"access": str(refresh.access_token), "refresh": str(refresh)}


@api_view(["POST"])
@permission_classes([AllowAny])
def login_view(request):
    """تسجيل الدخول: login_id + كلمة السر (+ رمز 2FA إن كان مفعّلاً)."""
    serializer = LoginSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data

    try:
        user = User.objects.get(login_id=data["login_id"])
    except User.DoesNotExist:
        return Response(
            {"detail": "بيانات الدخول غير صحيحة"}, status=status.HTTP_401_UNAUTHORIZED
        )

    # على عنوان متجرٍ بعينه لا يدخل إلا أهلُه. ويُقال صراحةً ولا يُخلط بخطأ
    # كلمة السرّ: من دخل عنواناً خاطئاً يجرّب كلمته حتى يُقفل حسابه بلا ذنب.
    # (`wtn4.com` يبقى مفتوحاً للجميع — قرار المالك 2026-08-16.)
    store = getattr(request, "store", None)
    if store is not None and user.tenant_id != store.id:
        return Response(
            {"detail": f"هذا الحساب ليس من متجر «{store.name}» — ادخل من عنوان متجرك."},
            status=status.HTTP_403_FORBIDDEN,
        )

    # القفل يُفحص **قبل** كلمة السرّ: بعده كانت المحاولة تُختبَر فعلياً على
    # حسابٍ مقفل، فيبقى التخمين ممكناً وإن لم يُفتح الباب.
    if user.is_locked:
        return Response({"detail": LOCKED_MESSAGE}, status=status.HTTP_403_FORBIDDEN)

    if not user.check_password(data["password"]):
        user.failed_login_count += 1
        fields = ["failed_login_count"]
        if user.failed_login_count >= LOGIN_ATTEMPTS_BEFORE_LOCK:
            user.locked_at = timezone.now()
            fields.append("locked_at")
        user.save(update_fields=fields)
        if user.is_locked:
            return Response({"detail": LOCKED_MESSAGE}, status=status.HTTP_403_FORBIDDEN)
        left = LOGIN_ATTEMPTS_BEFORE_LOCK - user.failed_login_count
        return Response(
            # لا نقول أيّ الحقلين خطأ — لكن نقول كم بقي، وإلّا فوجئ صاحب الحساب
            # بالقفل بلا إنذار وهو يظنّ أنه يخطئ الكتابة.
            {"detail": f"بيانات الدخول غير صحيحة — تبقّت {left} محاولة قبل قفل الحساب"},
            status=status.HTTP_401_UNAUTHORIZED,
        )

    if user.status == User.Status.PENDING:
        return Response(
            {"detail": "طلب تسجيلك قيد المراجعة لدى إدارة المتجر — تستطيع الدخول فور قبوله"},
            status=status.HTTP_403_FORBIDDEN,
        )
    if user.status != User.Status.ACTIVE:
        return Response({"detail": "الحساب معطّل"}, status=status.HTTP_403_FORBIDDEN)

    # التحقق الثنائي (2FA) — بديل حديث لآلة حاسبة المرجع
    if user.totp_enabled:
        code = data.get("totp", "")
        if not code:
            return Response({"require_totp": True}, status=status.HTTP_200_OK)
        if not pyotp.TOTP(user.totp_secret).verify(code, valid_window=1):
            return Response(
                {"detail": "رمز التحقق غير صحيح"}, status=status.HTTP_401_UNAUTHORIZED
            )

    user.failed_login_count = 0
    user.save(update_fields=["failed_login_count"])

    return Response({"user": UserSerializer(user).data, "tokens": _tokens_for(user)})


@api_view(["GET"])
@permission_classes([AllowAny])
def storefront_view(request):
    """
    هويّة المتجر صاحبِ هذا العنوان — تقرأها صفحة الدخول **قبل** أي حساب.

    على الباب العام (`wtn4.com`) تعود `null`، فتظهر الصفحة العامّة كما هي.
    ولا تُعاد من الحقول إلا ما يُرسم: لا اشتراك ولا أسرار — هي نقطةٌ مفتوحة
    بلا توكن، يقرؤها كل من كتب العنوان.
    """
    store = getattr(request, "store", None)
    if store is None:
        # نسخة عميل (متجرٌ واحد على دومينه): الباب العام **هو** بابُ متجره، فتلبس
        # صفحةُ الدخول اسمَه وشعاره. للعرض وحده — لا يمسّ من يُقبل دخوله.
        only = list(Tenant.objects.all()[:2])
        store = only[0] if len(only) == 1 else None
    if store is None:
        return Response({"store": None})
    return Response({
        "store": {
            "name": store.name,
            "short_name": store.short_name or store.name,
            "subdomain": store.subdomain,
            "logo_url": store.logo_url,
            "theme": store.theme,
            "theme_color": store.theme_color,
            "font": store.font,
            # صفحة الدخول تُرسم قبل أي حساب، فلو غاب الحجم هنا لظهرت بمقاسٍ
            # ثم قفزت إلى مقاسٍ آخر بعد الدخول.
            "ui_scale": store.ui_scale,
            # هويّة المتجر كما يراها الزائر قبل الدخول
            "tagline": store.tagline,
            "login_footer": store.login_footer,
            "social_links": store.social_links or {},
            # ألوان واجهة الوكلاء — الباب العام (الواجهة والدخول والتسجيل) يلبسها هو أيضاً
            "agent_theme": store.agent_theme or {},
            # العملات التي يختار منها من يسجّل نفسه: عملة الموقع + ما له سعر صرف مضبوط
            "currencies": [currency.base_currency(store)] + sorted(
                c for c, v in (store.exchange_rates or {}).items()
                if c != currency.base_currency(store) and currency.rate_of(store, c) > 0),
        }
    })


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def me_view(request):
    """معلومات المستخدم الحالي (للواجهة بعد الدخول)."""
    return Response(UserSerializer(request.user).data)


@api_view(["GET", "PUT"])
@permission_classes([IsAuthenticated])
def site_settings_view(request):
    """قراءة/تحديث إعدادات موقع المستأجر الحالي (Web Site Ayarları)."""
    tenant = request.user.tenant
    if tenant is None:
        return Response({"detail": "لا يوجد مستأجر"}, status=400)

    if request.method == "PUT":
        serializer = SiteSettingsSerializer(tenant, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    return Response(SiteSettingsSerializer(tenant).data)


@api_view(["GET", "PUT"])
@permission_classes([IsAuthenticated])
def exchange_rates_view(request):
    """
    سعر الصرف العام للمتجر: عملة الأساس + كم وحدةً منها تساوي وحدةً
    من كل عملة أخرى. تعتمد عليه طرق الدفع في حساب المبلغ المُضاف للمحفظة.
    """
    tenant = request.user.tenant
    if tenant is None:
        return Response({"detail": "لا يوجد مستأجر"}, status=400)

    if request.method == "PUT":
        if request.user.role != User.Role.TENANT_ADMIN:
            return Response({"detail": "غير مصرّح"}, status=403)
        base = str(request.data.get("base_currency") or tenant.base_currency or "TRY")
        rates = request.data.get("exchange_rates")
        if isinstance(rates, dict):
            clean = {}
            for cur, val in rates.items():
                try:
                    d = Decimal(str(val))
                except (InvalidOperation, TypeError):
                    return Response({"detail": f"سعر صرف غير صحيح للعملة {cur}"}, status=400)
                if d <= 0:
                    return Response({"detail": f"سعر صرف {cur} يجب أن يكون أكبر من صفر"}, status=400)
                clean[cur] = str(d)
            clean.pop(base, None)  # عملة الأساس لا سعر صرف لها
            tenant.exchange_rates = clean
        tenant.base_currency = base
        tenant.save(update_fields=["base_currency", "exchange_rates"])
        # كلفة باقات الخطوط مشتقّة من كلفة ZNET بالليرة ⇐ تتبع سعر الصرف الجديد
        from kontor.services import reprice_costs
        reprice_costs(tenant)

    return Response({
        "base_currency": tenant.base_currency or "TRY",
        "exchange_rates": tenant.exchange_rates or {},
    })


@api_view(["GET", "PUT"])
@permission_classes([IsAuthenticated])
def sms_settings_view(request):
    """قراءة/تحديث إعدادات SMS للمستأجر الحالي."""
    tenant = request.user.tenant
    if tenant is None:
        return Response({"detail": "لا يوجد مستأجر"}, status=400)
    if request.method == "PUT":
        s = SmsSettingsSerializer(tenant, data=request.data, partial=True)
        s.is_valid(raise_exception=True)
        s.save()
        return Response(s.data)
    return Response(SmsSettingsSerializer(tenant).data)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def ledger_view(request):
    """حركات الحسابات (Hesap Hareketleri): كل حركات المحافظ في المستأجر."""
    qs = WalletTransaction.objects.filter(tenant=request.user.tenant).select_related(
        "wallet__user"
    )
    dealer = request.query_params.get("dealer")
    if dealer:
        qs = qs.filter(wallet__user_id=dealer)
    txn_type = request.query_params.get("type")
    if txn_type and txn_type != "all":
        qs = qs.filter(type=txn_type)
    rows = [{
        "id": t.id,
        "dealer_name": t.wallet.user.name,
        "type": t.type,
        "type_label": t.get_type_display(),
        "amount": str(t.amount),
        "balance_before": str(t.balance_before),
        "balance_after": str(t.balance_after),
        "note": t.note,
        "created_at": t.created_at.strftime("%Y-%m-%d %H:%M"),
    } for t in qs[:300]]
    return Response({"count": qs.count(), "results": rows})


def _next_dealer_no(tenant) -> int:
    """الرقم التسلسلي التالي داخل هذا المتجر — لا يعيد استعمال رقم وكيل محذوف."""
    last = (
        User.objects.filter(tenant=tenant, role__in=[User.Role.BAYI, User.Role.ANA_BAYI])
        .aggregate(models.Max("dealer_no"))["dealer_no__max"]
    )
    return (last or 0) + 1


def _create_dealer(request):
    """إنشاء وكيل (Bayi) جديد تحت المستأجر الحالي — يقابل زر "Bayi Ekle"."""
    tenant = request.user.tenant
    if tenant is None:
        return Response({"detail": "لا يوجد مستأجر"}, status=400)

    data = request.data
    login_id = clean_login_id(data.get("login_id"))
    name = (data.get("name") or "").strip()
    password = data.get("password") or ""
    if not login_id or not name or not password:
        return Response(
            {"detail": "الاسم ورقم الدخول وكلمة السر مطلوبة"}, status=400
        )
    if User.objects.filter(login_id=login_id).exists():
        return Response({"detail": "رقم الدخول مستخدم مسبقاً"}, status=400)

    try:
        credit_limit = Decimal(str(data.get("credit_limit") or "0"))
    except (InvalidOperation, TypeError):
        return Response({"detail": "الحد الائتماني غير صحيح"}, status=400)

    country = (data.get("country") or "SY").strip()[:2] or "SY"
    group = (data.get("group") or "").strip()

    # عملة الوكيل: يرى بها لوحته، ويكتب صاحب المتجر أرقامه بها (الحد الائتماني هنا)
    cur = str(data.get("display_currency") or "").strip().upper()
    if cur == currency.base_currency(tenant):
        cur = ""
    if cur and not currency.rate_of(tenant, cur):
        return Response({"detail": f"لا سعر صرف مضبوط للعملة {cur} — اضبطه في «أسعار الصرف» أولاً"},
                        status=400)

    # وكيل كبير أم وكيل عادي؟ والعادي قد يتبع وكيلاً كبيراً
    role = data.get("role") or User.Role.BAYI
    if role not in (User.Role.BAYI, User.Role.ANA_BAYI):
        return Response({"detail": "نوع وكيل غير معروف"}, status=400)

    parent = None
    if role == User.Role.BAYI and data.get("parent"):
        parent = User.objects.filter(
            pk=data["parent"], tenant=tenant, role=User.Role.ANA_BAYI
        ).first()
        if parent is None:
            return Response({"detail": "الوكيل الكبير المحدّد غير موجود"}, status=404)

    from django.db import transaction as db_transaction

    with db_transaction.atomic():
        u = User(
            tenant=tenant,
            role=role,
            parent=parent,
            login_id=login_id,
            dealer_no=_next_dealer_no(tenant),
            name=name,
            country=country,
            status=User.Status.ACTIVE,
            modules={"oyun": True, "shopping": True, "group": group},
            display_currency=cur,
        )
        u.set_password(password)
        u.save()
        # الحد مكتوبٌ بعملة الوكيل ⇐ يُحفظ بعملة الدفتر كبقيّة الأرقام
        Wallet.objects.create(
            tenant=tenant, user=u, balance=Decimal("0"),
            credit_limit=currency.from_display(u, credit_limit),
        )

    return Response(
        {"id": u.id, "login_id": u.login_id, "name": u.name,
         "role": u.role, "parent": u.parent_id},
        status=status.HTTP_201_CREATED,
    )


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def dealers_view(request):
    """قائمة الوكلاء (Bayi Listesi) للمستأجر الحالي + إنشاء وكيل جديد (Bayi Ekle)."""
    if request.method == "POST":
        return _create_dealer(request)

    tenant = request.user.tenant
    everyone = list(
        User.objects.filter(
            tenant=tenant, role__in=[User.Role.BAYI, User.Role.ANA_BAYI]
        ).select_related("wallet", "parent").order_by("dealer_no", "name")
    )
    big_ids = {u.id for u in everyone if u.role == User.Role.ANA_BAYI}

    search = request.query_params.get("q", "").strip()

    def row(u):
        wallet = getattr(u, "wallet", None)
        mods = u.modules or {}
        return {
            "id": u.id,
            "login_id": u.login_id,
            "dealer_no": u.dealer_no,
            "name": u.name,
            "balance": str(wallet.balance) if wallet else "0.00",
            "credit_limit": str(wallet.credit_limit) if wallet else "0.00",
            # الرصيد بعملة دفتر المتجر — لا بحقل المحفظة القديم
            "currency": currency.base_currency(u.tenant),
            # وبعملة الوكيل نفسه (ما يراه في لوحته، وما يكتبه صاحب المتجر له)
            "own_currency": currency.display_currency(u),
            "balance_own": str(currency.to_display(u, wallet.balance)) if wallet else "0.00",
            "credit_limit_own": str(currency.to_display(u, wallet.credit_limit)) if wallet else "0.00",
            # عملة عرض الوكيل — فارغة تعني عملة الموقع
            "display_currency": u.display_currency or "",
            "status": u.status,
            "country": u.country,
            # مجموعة الأسعار الفعلية (ما تحدّده نافذة الإعدادات) — وإلا وسمُ الإنشاء القديم
            "group": u.price_group.name if u.price_group_id else mods.get("group", ""),
            "shopping": mods.get("shopping", True),   # Alışveriş
            "oyun": mods.get("oyun", True),           # لعبة OyunPin
            "active": u.status == User.Status.ACTIVE,  # Aktif
            # قفلُ المحاولات — كان يُعرف بفتح إعدادات كل وكيل واحداً واحداً،
            # فمن قُفل حسابه ينتظر أن يتّصل ليُعرف. صار يُرى في الصفّ.
            "is_locked": u.is_locked,
            # وكيل كبير: تحته دكاكين، ويُميَّز بنجمة وصفوف تتفرّع منه
            "is_big": u.role == User.Role.ANA_BAYI,
            "role": u.role,
            "parent": u.parent_id,
            "parent_name": u.parent.name if u.parent_id else "",
            # واتساب: الرقم وموافقة التحصيل — يقرأهما زرّا الإرسال في الجدول
            "whatsapp": u.whatsapp,
            "auto_debt_collection": u.auto_debt_collection,
        }

    # الدكان التابع لوكيل كبير لا يقف صفّاً مستقلاً: مكانه داخل جدول وكيله.
    children_of = {}
    for u in everyone:
        if u.parent_id in big_ids:
            children_of.setdefault(u.parent_id, []).append(u)

    # طلبات التسجيل الذاتي: لا تُعدّ وكلاء بعد — تُعرض أعلى القائمة للمعاينة
    from .registration import pending_row
    pending = [pending_row(u) for u in everyone if u.status == User.Status.PENDING]

    rows = []
    for u in everyone:
        if u.status == User.Status.PENDING:
            continue
        if u.parent_id in big_ids:
            continue
        if search and search not in u.name and search not in u.login_id:
            continue
        r = row(u)
        kids = children_of.get(u.id, [])
        r["children"] = [row(c) for c in kids]
        r["children_count"] = len(kids)
        rows.append(r)

    return Response({"count": len(rows), "results": rows, "pending": pending})


def _get_dealer_wallet(request, dealer_id):
    """يجلب محفظة وكيل ضمن نفس المستأجر (عزل)."""
    return Wallet.objects.select_related("user").get(
        user_id=dealer_id, tenant=request.user.tenant
    )


# أقصى حجم لصورة محفوظة كـ data URL — الصور تُصغَّر في المتصفّح قبل الإرسال
MAX_IMAGE_CHARS = 3_000_000  # ≈ 2.2 ميغابايت بعد ترميز base64


def _dealer_settings_row(u):
    from catalog.models import PriceGroup

    wallet = getattr(u, "wallet", None)
    tenant = u.tenant
    return {
        "id": u.id,
        "login_id": u.login_id,
        "dealer_no": u.dealer_no,
        "name": u.name,
        "role": u.role,
        "role_label": u.get_role_display(),
        # الشجرة: وكيل كبير أم دكان يتبع أحدهم
        "parent": u.parent_id,
        "parent_name": u.parent.name if u.parent_id else "",
        "children_count": u.children.count(),
        "big_agents": [
            {"id": b.id, "name": b.name}
            for b in User.objects.filter(
                tenant=tenant, role=User.Role.ANA_BAYI
            ).exclude(pk=u.pk).order_by("name")
        ],
        # إعدادات انتقلت من صفحة «أسعار الوكلاء» المحذوفة
        "oyun_load_limit": str(u.oyun_load_limit),
        "price_group": u.price_group_id,
        "price_groups": [
            {"id": g.id, "name": g.name}
            for g in PriceGroup.objects.filter(tenant=tenant).order_by("id")
        ],
        # التبويب الأول
        "display_currency": u.display_currency or "",
        # بعملة الوكيل — وتُحوَّل عند الحفظ إلى عملة الدفتر
        "credit_limit": str(currency.to_display(u, wallet.credit_limit)) if wallet else "0.00",
        "balance": str(currency.to_display(u, wallet.balance)) if wallet else "0.00",
        "own_currency": currency.display_currency(u),
        "status": u.status,
        # التبويب الثاني
        "phone": u.phone,
        "whatsapp": u.whatsapp,
        "whatsapp_pretty": f"+{u.whatsapp}" if u.whatsapp else "",
        "country": u.country,
        "province": u.province,
        "id_image": u.id_image,
        "shop_image": u.shop_image,
        "auto_debt_collection": u.auto_debt_collection,
        "internal_supply_allowed": u.internal_supply_allowed,
        "api_access_allowed": u.api_access_allowed,
        "is_locked": u.is_locked,
        "locked_at": u.locked_at.strftime("%Y-%m-%d %H:%M") if u.locked_at else "",
        "failed_login_count": u.failed_login_count,
        # مرجع العملات
        "base_currency": currency.base_currency(tenant),
        "available_currencies": sorted(
            c for c, v in (tenant.exchange_rates or {}).items() if str(v).strip()
        ),
        # لتحويل الحد في النافذة لحظة تبديل العملة — قبل الحفظ
        "rates": {c: str(v) for c, v in (tenant.exchange_rates or {}).items() if str(v).strip()},
    }


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def dealer_settings_view(request, dealer_id):
    """
    إعدادات وكيل واحد من «قائمة الوكلاء» — نافذة بتبويبين:
    الحساب (العملة · الحد الائتماني · كلمة السر · الحالة) وبيانات الوكيل
    (الجوال · البلد والمحافظة · الوثائق · موافقة التحصيل الآلي).
    """
    if request.user.role != User.Role.TENANT_ADMIN:
        return Response({"detail": "غير مصرّح"}, status=403)
    try:
        u = User.objects.select_related("wallet", "tenant").get(
            pk=dealer_id, tenant=request.user.tenant,
            role__in=[User.Role.BAYI, User.Role.ANA_BAYI],
        )
    except User.DoesNotExist:
        return Response({"detail": "الوكيل غير موجود"}, status=404)

    if request.method == "GET":
        return Response(_dealer_settings_row(u))

    data = request.data
    tenant = request.user.tenant
    fields = []

    if "display_currency" in data:
        cur = str(data["display_currency"] or "")
        if cur and cur != currency.base_currency(tenant) and not currency.rate_of(tenant, cur):
            return Response(
                {"detail": f"لا سعر صرف مضبوط للعملة {cur} — اضبطه في «أسعار الصرف» أولاً"},
                status=400,
            )
        u.display_currency = "" if cur == currency.base_currency(tenant) else cur
        fields.append("display_currency")

    if "status" in data:
        if data["status"] not in User.Status.values:
            return Response({"detail": "حالة غير معروفة"}, status=400)
        u.status = data["status"]
        fields.append("status")

    # النوع والتبعية: ترقية وكيل إلى كبير، أو ضمّ دكان تحت كبير
    if "role" in data:
        new_role = data["role"]
        if new_role not in (User.Role.BAYI, User.Role.ANA_BAYI):
            return Response({"detail": "نوع وكيل غير معروف"}, status=400)
        if new_role == User.Role.BAYI and u.children.exists():
            return Response(
                {"detail": "لا يمكن تحويله إلى وكيل عادي وتحته دكاكين — انقلها أولاً"},
                status=400,
            )
        if new_role == User.Role.ANA_BAYI and u.parent_id:
            u.parent = None            # الكبير لا يتبع أحداً
            fields.append("parent")
        u.role = new_role
        fields.append("role")

    if "parent" in data:
        pid = data["parent"]
        if pid in (None, ""):
            u.parent = None
        else:
            if int(pid) == u.id:
                return Response({"detail": "لا يتبع الوكيل نفسه"}, status=400)
            parent = User.objects.filter(
                pk=pid, tenant=tenant, role=User.Role.ANA_BAYI
            ).first()
            if parent is None:
                return Response({"detail": "الوكيل الكبير المحدّد غير موجود"}, status=404)
            if u.role == User.Role.ANA_BAYI:
                return Response({"detail": "الوكيل الكبير لا يتبع وكيلاً آخر"}, status=400)
            u.parent = parent
        if "parent" not in fields:
            fields.append("parent")

    # حدّ تحميل الألعاب ومجموعة الأسعار — كانا في صفحة «أسعار الوكلاء» قبل حذفها
    if "oyun_load_limit" in data:
        try:
            limit = Decimal(str(data["oyun_load_limit"]))
        except (InvalidOperation, TypeError):
            return Response({"detail": "حدّ تحميل غير صحيح"}, status=400)
        if limit < 0:
            return Response({"detail": "حدّ التحميل لا يكون سالباً"}, status=400)
        u.oyun_load_limit = limit
        fields.append("oyun_load_limit")

    if "price_group" in data:
        from catalog.models import PriceGroup

        gid = data["price_group"]
        if gid in (None, ""):
            u.price_group = None
        else:
            group = PriceGroup.objects.filter(pk=gid, tenant=tenant).first()
            if group is None:
                return Response({"detail": "مجموعة الأسعار غير موجودة"}, status=404)
            u.price_group = group
        fields.append("price_group")

    for key in ("phone", "province", "country"):
        if key in data:
            setattr(u, key, str(data[key] or "").strip()[:80])
            fields.append(key)

    # رقم واتساب: يُطبَّع هنا مرّةً — فلا يبقى تخمين صيغته إلى لحظة الإرسال.
    # البلد يُقرأ من الحقل المُرسَل معه إن وُجد، وإلّا من المحفوظ.
    if "whatsapp" in data:
        from whatsapp.phone import normalize

        raw = str(data["whatsapp"] or "").strip()
        if raw:
            country = str(data.get("country") or u.country or "")
            normalized = normalize(raw, country)
            if not normalized:
                return Response(
                    {"detail": "رقم واتساب غير صالح — اكتبه برمز الدولة مثل +905551234567"},
                    status=400,
                )
            u.whatsapp = normalized
        else:
            u.whatsapp = ""
        fields.append("whatsapp")

    for key in ("id_image", "shop_image"):
        if key in data:
            img = str(data[key] or "")
            if len(img) > MAX_IMAGE_CHARS:
                return Response({"detail": "الصورة كبيرة جداً — اختر صورة أصغر"}, status=400)
            if img and not img.startswith("data:image/"):
                return Response({"detail": "الملف المرفوع ليس صورة"}, status=400)
            setattr(u, key, img)
            fields.append(key)

    if "auto_debt_collection" in data:
        u.auto_debt_collection = bool(data["auto_debt_collection"])
        fields.append("auto_debt_collection")

    if "internal_supply_allowed" in data:
        u.internal_supply_allowed = bool(data["internal_supply_allowed"])
        fields.append("internal_supply_allowed")

    if "api_access_allowed" in data:
        u.api_access_allowed = bool(data["api_access_allowed"])
        fields.append("api_access_allowed")

    new_password = str(data.get("new_password") or "")
    if new_password:
        if len(new_password) < 5:
            return Response({"detail": "كلمة السر قصيرة (5 أحرف على الأقل)"}, status=400)
        u.set_password(new_password)
        fields.append("password")
        # كلمة سرّ جديدة تفتح القفل دائماً — وهو المخرج الوحيد منه عمداً:
        # زرُّ فتحٍ بلا تبديل كان يعيد الحساب بكلمة سرٍّ ثبت أن أحدهم يخمّنها.
        if u.is_locked or u.failed_login_count:
            u.locked_at = None
            u.failed_login_count = 0
            fields += ["locked_at", "failed_login_count"]

    if fields:
        u.save(update_fields=fields)

    # الحد الائتماني على المحفظة لا على المستخدم
    if "credit_limit" in data:
        wallet = getattr(u, "wallet", None)
        if wallet is None:
            return Response({"detail": "لا توجد محفظة لهذا الوكيل"}, status=400)
        try:
            limit = Decimal(str(data["credit_limit"]))
        except (InvalidOperation, TypeError):
            return Response({"detail": "حد ائتماني غير صحيح"}, status=400)
        if limit > 0:
            return Response(
                {"detail": "الحد الائتماني أقصى دَين مسموح — اكتبه صفراً أو رقماً سالباً"},
                status=400,
            )
        # مكتوبٌ بعملة الوكيل (المحدَّثة أعلاه إن تبدّلت) ⇐ يُحفظ بعملة الدفتر
        wallet.credit_limit = currency.from_display(u, limit)
        wallet.save(update_fields=["credit_limit"])

    u.refresh_from_db()
    # إقرارٌ صريح بأن السرّ تبدّل فعلاً — الواجهة تعرضه، فلا يظنّ المالك أنه
    # غيّره وهو لم يُرسَل أصلاً (حقل التأكيد الفارغ كان يُسقطه بصمت).
    return Response(_dealer_settings_row(u) | {"password_changed": bool(new_password)})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def wallet_operation_view(request, dealer_id, action):
    """شحن/خصم رصيد وكيل (Finans İşlem +/−)."""
    if action not in ("topup", "deduct"):
        return Response({"detail": "عملية غير معروفة"}, status=400)
    try:
        wallet = _get_dealer_wallet(request, dealer_id)
    except Wallet.DoesNotExist:
        return Response({"detail": "الوكيل غير موجود"}, status=404)

    try:
        amount = Decimal(str(request.data.get("amount", "")))
    except (InvalidOperation, TypeError):
        return Response({"detail": "مبلغ غير صحيح"}, status=400)

    note = request.data.get("note", "")
    # المبلغ بعملة الوكيل: صاحب المتجر يقبض منه ليراتٍ فيكتب ليرات — يُحفظ بعملة الدفتر.
    # ويُذكر المكتوب في الملاحظة: الدفتر بالدولار، ولا يُنسى أنه كان «1000 ل.ت».
    dealer = wallet.user
    own = currency.display_currency(dealer)
    base_amount = currency.from_display(dealer, amount)
    if own != currency.base_currency(dealer.tenant):
        note = (f"{amount:,.2f} {own}" + (f" — {note}" if note else ""))[:255]
    fn = services.topup if action == "topup" else services.deduct
    try:
        txn = fn(wallet.id, base_amount, created_by=request.user, note=note)
    except services.WalletError as e:
        return Response({"detail": str(e)}, status=400)

    wallet.refresh_from_db()
    return Response({
        "balance_own": str(currency.to_display(dealer, wallet.balance)),
        "own_currency": own,
        "balance": str(wallet.balance),
        "transaction": {
            "id": txn.id, "type": txn.type, "amount": str(txn.amount),
            "balance_after": str(txn.balance_after),
        },
    })


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def wallet_transactions_view(request, dealer_id):
    """كشف حركات محفظة وكيل (Hesap Hareketleri)."""
    try:
        wallet = _get_dealer_wallet(request, dealer_id)
    except Wallet.DoesNotExist:
        return Response({"detail": "الوكيل غير موجود"}, status=404)

    txns = wallet.transactions.all()[:100]
    return Response({
        "dealer": {"id": wallet.user_id, "name": wallet.user.name,
                   "balance": str(wallet.balance), "currency": currency.base_currency(wallet.tenant)},
        "results": [{
            "id": t.id,
            "type": t.type,
            "type_label": t.get_type_display(),
            "amount": str(t.amount),
            "balance_after": str(t.balance_after),
            "note": t.note,
            "created_at": t.created_at.strftime("%Y-%m-%d %H:%M"),
        } for t in txns],
    })


def _invoice_row(inv):
    return {
        "id": inv.id,
        "tenant_name": inv.tenant.name,
        "plan": inv.plan,
        "plan_label": "سنوي" if inv.plan == "yearly" else "شهري",
        "amount": str(inv.amount),
        "period_start": inv.period_start.strftime("%Y-%m-%d"),
        "period_end": inv.period_end.strftime("%Y-%m-%d"),
        "status": inv.status,
        "status_label": inv.get_status_display(),
        "created_at": inv.created_at.strftime("%Y-%m-%d"),
    }


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def my_invoices_view(request):
    """فواتير اشتراك المستأجر الحالي (يراها صاحب المتجر)."""
    if request.user.tenant_id is None:
        return Response({"count": 0, "results": []})
    qs = Invoice.objects.filter(tenant=request.user.tenant).select_related("tenant")
    return Response({"count": qs.count(), "results": [_invoice_row(i) for i in qs]})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def announcement_view(request):
    """إعلان المنصّة الحالي — يظهر فوق هيدر لوحات أصحاب المتاجر."""
    from .models import PlatformAnnouncement
    a = PlatformAnnouncement.get()
    return Response({"message": a.message, "ticker": a.ticker})


@api_view(["GET", "PUT"])
@permission_classes([IsAuthenticated])
def theme_config_view(request):
    """تخصيص مظهر المتجر: أي مستخدم بالمستأجر يقرأه؛ صاحب المتجر فقط يعدّله."""
    tenant = request.user.tenant
    if tenant is None:
        return Response({"config": {}})
    if request.method == "PUT":
        if request.user.role != User.Role.TENANT_ADMIN:
            return Response({"detail": "التخصيص لصاحب المتجر فقط"}, status=403)
        cfg = request.data.get("config")
        if not isinstance(cfg, dict) or len(str(cfg)) > 4000:
            return Response({"detail": "إعدادات غير صالحة"}, status=400)
        tenant.theme_config = cfg
        tenant.save(update_fields=["theme_config"])
    return Response({"config": tenant.theme_config or {}})


_HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")
_THEME_KEY = re.compile(r"^[a-z][a-z0-9_]{0,31}$")


@api_view(["GET", "PUT"])
@permission_classes([IsAuthenticated])
def agent_theme_view(request):
    """
    ألوان واجهة الوكلاء: يقرؤها كل من في المتجر، ويضبطها صاحبه وحده.

    القيم ألوانٌ سداسية فقط (`#rrggbb`) — تُكتب في وسم <style> على صفحة الوكيل،
    فأيّ نصٍّ آخر هنا بابٌ لحقن CSS. والمفاتيح يعرفها الواجهة (agentTheme.ts)؛
    مفتاحٌ لا تعرفه يُهمَل هناك، فلا داعي لقائمةٍ ثانية تُنسى عند الإضافة.
    """
    tenant = request.user.tenant
    if tenant is None:
        return Response({"theme": {}})
    if request.method == "PUT":
        if request.user.role != User.Role.TENANT_ADMIN:
            return Response({"detail": "تصميم واجهة الوكلاء لصاحب المتجر فقط"}, status=403)
        theme = request.data.get("theme")
        if not isinstance(theme, dict) or len(theme) > 60:
            return Response({"detail": "إعدادات غير صالحة"}, status=400)
        for k, v in theme.items():
            if not _THEME_KEY.match(str(k)) or not isinstance(v, str) or not _HEX_COLOR.match(v):
                return Response({"detail": f"لونٌ غير صالح: {k}"}, status=400)
        tenant.agent_theme = {k: v.lower() for k, v in theme.items()}
        tenant.save(update_fields=["agent_theme"])
    return Response({"theme": tenant.agent_theme or {}})
