"""
الباب العام للمتجر: واجهةٌ يراها الزائر قبل أي حساب، وتسجيلٌ ذاتي يُراجعه صاحب المتجر.

- `public_games_view` — الألعاب المعروضة (الاسم والصورة فقط): لا أسعار ولا باقات،
  فالأسعار تخصّ كل وكيلٍ بمجموعته، ولا تُكشف لمن لم يدخل.
- `register_view` — طلب فتح حساب وكيل: تُحفظ بياناته «بانتظار الموافقة»، فلا يدخل
  ولا يشتري حتى يقبله صاحب المتجر من قائمة الوكلاء.
- `registration_review_view` — قبولٌ (مع عملته وحدّه ومجموعة أسعاره) أو رفض.

الحقول إجبارية كلّها — ومنها صورة الهوية: صاحب المتجر يُقرض وكلاءه رصيداً، فلا
يُفتح حسابٌ لمجهول.
"""
from decimal import Decimal, InvalidOperation

from django.core.cache import cache
from django.db import transaction
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from . import currency
from .models import Tenant, User, Wallet
from .text import clean_login_id

MAX_IMAGE_CHARS = 3_000_000          # ≈ 2.2 ميغابايت بعد base64 — الصور تُصغَّر في المتصفّح
REGISTER_PER_HOUR = 5                # من عنوانٍ واحد — حاجزٌ أمام الإغراق الآلي
COUNTRIES = {"SY", "TR", "SA", "IQ", "LB", "JO", "EG", "AE", "KW", "QA", "BH", "OM", "YE", "PS", "LY", "DZ", "MA", "TN", "SD", "DE", "OTHER"}


def public_tenant(request):
    """متجر هذا العنوان — ونسخة العميل (متجرٌ واحد على دومينه) بابها العام بابه."""
    store = getattr(request, "store", None)
    if store is not None:
        return store
    only = list(Tenant.objects.all()[:2])
    return only[0] if len(only) == 1 else None


@api_view(["GET"])
@permission_classes([AllowAny])
def public_games_view(request):
    """الألعاب النشطة التي فيها باقةٌ تُباع — للعرض قبل الدخول، بلا أسعار."""
    from catalog.models import Game, Product

    tenant = public_tenant(request)
    if tenant is None:
        return Response({"games": []})
    games = (Game.objects.filter(tenant=tenant, status=Game.Status.ACTIVE,
                                 products__status=Product.Status.ACTIVE)
             .distinct().order_by("sort_order", "id"))
    return Response({"games": [
        {"id": g.id, "name": g.name, "image_url": g.image_url, "description": g.description}
        for g in games
    ]})


def _client_ip(request) -> str:
    fwd = request.META.get("HTTP_X_FORWARDED_FOR", "")
    return (fwd.split(",")[0].strip() if fwd else request.META.get("REMOTE_ADDR", "")) or "?"


def _image(value, label, required):
    img = str(value or "")
    if not img:
        return ("", f"{label} مطلوبة") if required else ("", "")
    if not img.startswith("data:image/"):
        return "", f"{label}: الملف المرفوع ليس صورة"
    if len(img) > MAX_IMAGE_CHARS:
        return "", f"{label} كبيرة جداً — اختر صورة أصغر"
    return img, ""


@api_view(["POST"])
@permission_classes([AllowAny])
def register_view(request):
    """طلب فتح حساب وكيل — يُحفظ «بانتظار الموافقة» ولا يُدخل به حتى يُقبل."""
    from whatsapp.phone import normalize

    tenant = public_tenant(request)
    if tenant is None:
        return Response({"detail": "التسجيل متاحٌ من عنوان المتجر نفسه"}, status=400)

    key = f"register:{tenant.id}:{_client_ip(request)}"
    if cache.get(key, 0) >= REGISTER_PER_HOUR:
        return Response({"detail": "محاولاتٌ كثيرة من هذا الجهاز — حاول بعد ساعة"}, status=429)

    d = request.data
    name = str(d.get("name") or "").strip()[:120]
    login_id = clean_login_id(d.get("login_id"))
    password = str(d.get("password") or "")
    country = str(d.get("country") or "").strip().upper()[:5]
    province = str(d.get("province") or "").strip()[:80]
    raw_wa = str(d.get("whatsapp") or "").strip()

    errors = {}
    if len(name) < 3:
        errors["name"] = "اكتب الاسم الكامل"
    if not login_id or not login_id.isdigit() or not 6 <= len(login_id) <= 15:
        errors["login_id"] = "رقم الدخول أرقامٌ فقط (من 6 إلى 15)"
    elif User.objects.filter(login_id=login_id).exists():
        errors["login_id"] = "رقم الدخول مستعمل — اختر رقماً آخر"
    if len(password) < 6:
        errors["password"] = "كلمة السر 6 أحرف على الأقل"
    if country not in COUNTRIES:
        errors["country"] = "اختر الدولة"
    if len(province) < 2:
        errors["province"] = "اكتب المدينة / المحافظة"
    wa = normalize(raw_wa, country) if raw_wa else ""
    if not raw_wa:
        errors["whatsapp"] = "رقم واتساب مطلوب"
    elif not wa:
        errors["whatsapp"] = "اكتب رقم واتساب مع رمز الدولة، مثل +905551234567"
    id_image, err = _image(d.get("id_image"), "صورة الهوية", required=True)
    if err:
        errors["id_image"] = err
    shop_image, err = _image(d.get("shop_image"), "صورة المحل", required=False)
    if err:
        errors["shop_image"] = err
    if errors:
        return Response({"detail": next(iter(errors.values())), "errors": errors}, status=400)

    from .views import _next_dealer_no

    with transaction.atomic():
        u = User(
            tenant=tenant, role=User.Role.BAYI, login_id=login_id, name=name,
            dealer_no=_next_dealer_no(tenant), status=User.Status.PENDING,
            country=country if country != "OTHER" else "", province=province,
            whatsapp=wa, phone=wa, id_image=id_image, shop_image=shop_image,
            modules={"oyun": True, "shopping": True, "group": "", "self_registered": True},
        )
        u.set_password(password)
        u.save()
        Wallet.objects.create(tenant=tenant, user=u, balance=Decimal("0"), credit_limit=Decimal("0"))

    cache.set(key, cache.get(key, 0) + 1, 3600)
    return Response({"ok": True, "login_id": u.login_id}, status=201)


def pending_row(u) -> dict:
    """طلب التسجيل كما يراه صاحب المتجر في «معاينة»."""
    return {
        "id": u.id, "login_id": u.login_id, "name": u.name, "country": u.country,
        "province": u.province, "whatsapp": f"+{u.whatsapp}" if u.whatsapp else "",
        "id_image": u.id_image, "shop_image": u.shop_image,
        "created_at": u.created_at.strftime("%Y-%m-%d %H:%M") if u.created_at else "",
    }


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def registration_review_view(request, dealer_id):
    """
    قرار صاحب المتجر في طلب تسجيل: {action: approve|reject, display_currency?,
    credit_limit? (بعملة الوكيل), price_group?}. والإلغاء لا يصل هنا — يبقى الطلب معلّقاً.
    """
    from catalog.models import PriceGroup

    if request.user.role != User.Role.TENANT_ADMIN:
        return Response({"detail": "غير مصرّح"}, status=403)
    u = User.objects.filter(pk=dealer_id, tenant=request.user.tenant,
                            status=User.Status.PENDING).select_related("wallet").first()
    if u is None:
        return Response({"detail": "لا طلب تسجيل بهذا الرقم"}, status=404)

    action = request.data.get("action")
    if action == "reject":
        name = u.name
        u.delete()   # لم يدخل قطّ ولا حركات له — ويتحرّر رقم دخوله
        return Response({"rejected": True, "name": name})
    if action != "approve":
        return Response({"detail": "إجراء غير معروف"}, status=400)

    tenant = request.user.tenant
    cur = str(request.data.get("display_currency") or "").strip().upper()
    if cur == currency.base_currency(tenant):
        cur = ""
    if cur and not currency.rate_of(tenant, cur):
        return Response({"detail": f"لا سعر صرف مضبوط للعملة {cur}"}, status=400)
    try:
        limit = Decimal(str(request.data.get("credit_limit") or "0"))
    except (InvalidOperation, TypeError):
        return Response({"detail": "حد ائتماني غير صحيح"}, status=400)
    if limit > 0:
        return Response({"detail": "الحد الائتماني صفرٌ أو رقمٌ سالب"}, status=400)
    group = None
    gid = request.data.get("price_group")
    if gid not in (None, ""):
        group = PriceGroup.objects.filter(pk=gid, tenant=tenant).first()
        if group is None:
            return Response({"detail": "مجموعة الأسعار غير موجودة"}, status=404)

    with transaction.atomic():
        u.status = User.Status.ACTIVE
        u.display_currency = cur
        u.price_group = group
        u.save(update_fields=["status", "display_currency", "price_group"])
        u.wallet.credit_limit = currency.from_display(u, limit)
        u.wallet.save(update_fields=["credit_limit"])
    return Response({"approved": True, "name": u.name, "login_id": u.login_id})
