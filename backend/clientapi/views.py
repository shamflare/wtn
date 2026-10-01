"""
الواجهة الخارجية — كي يرسل متجرٌ خارج منصّتنا طلباته إلينا برمجياً.

**الشكل منسوخ عن ZDK عمداً** (نفس المسارات وأسماء الحقول وترويسة `api-token`)،
لأن كل متجر في هذا السوق مربوطٌ ببركات أو أب‑ستور أصلاً وكوده جاهز: يبدّل
الرابط والتوكن فيعمل. شكلٌ من عندنا كان سيكلّفه مبرمجاً وأسبوعاً — وغالباً
لن يفعل. المرجع: [docs/integrations/ZDK_API.md] ووثيقتنا [docs/integrations/OUR_API.md].

**من هو المتصل:** التوكن يخصّ **وكيلاً** لا متجراً — لأن المحفظة على الوكيل.
فالطلب الوارد يمشي في نفس مسار ضغطة «شراء» في لوحته: نفس التسعير ونفس الخصم
ونفس التوجيه. لا دفتر جديد ولا منطق مالي جديد.

**منع التكرار** بـ `order_uuid` — انظر `Order.client_uuid`.
"""
from decimal import InvalidOperation
from functools import wraps
from uuid import UUID

from django.db import IntegrityError
from rest_framework.decorators import (
    api_view, authentication_classes, permission_classes, throttle_classes,
)
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle

from catalog.models import Product
from core import currency
from orders import services
from orders.models import Order
from orders.views import _maybe_auto_execute

from . import errors
from .auth import ApiTokenAuthentication

# حالاتنا الخمس بلغة ZDK الثلاث. «العالق» = فشل لدى كل المزوّدين وينتظر قرار
# الأدمن، والمال لم يُستَرجع — فهو `wait` لا `reject`. قوله `reject` كان يدفع
# الخارجيَّ إلى إعادة الطلب على شحنةٍ قد تُنفَّذ يدوياً بعد قليل.
STATUS_OUT = {
    Order.Status.SUCCESS: "accept",
    Order.Status.CANCELLED: "reject",
    Order.Status.PENDING: "wait",
    Order.Status.PROCESSING: "wait",
    Order.Status.STUCK: "wait",
}


class ClientThrottle(ScopedRateThrottle):
    """
    حدٌّ تقريبي لكبح حلقة مجنونة عند عميل خارجي — لا حاجز أمني.

    الذاكرة المؤقّتة محليّة لكل عامل gunicorn (عاملان)، فالحدّ الفعلي ضعف
    المكتوب. مقصودٌ أن يبقى بسيطاً بلا Redis؛ الحاجز الحقيقي هو المحفظة والحدّ
    الائتماني.
    """

    scope = "client_api"

    def get_cache_key(self, request, view):
        row = getattr(request, "api_token", None)
        if row is None:
            return None
        return f"throttle_client_api_{row.pk}"


def _api(view):
    """
    مصادقة الترويسة + حدّ نداءات + جسم خطأ واحد.

    صلاحيات DRF مُفرَّغة عمداً: لو تُركت `IsAuthenticated` لردّ DRF بشكله هو
    على التوكن الناقص، وعميلٌ مكتوب لـ ZDK لا يفهمه. فنفحص بأنفسنا ونردّ 120/121.
    """
    @wraps(view)
    def inner(request, *args, **kwargs):
        if not request.user or not request.user.is_authenticated:
            spec = getattr(request, "api_auth_error", errors.TOKEN_REQUIRED)
            return errors.error(spec, http_status=401)
        return view(request, *args, **kwargs)

    return api_view(["GET"])(
        authentication_classes([ApiTokenAuthentication])(
            permission_classes([])(throttle_classes([ClientThrottle])(inner))
        )
    )


def _money(user, amount) -> str:
    """كل مبلغ يخرج بعملة **عرض الوكيل** — نفس ما يراه في لوحته، فلا رقمان."""
    return str(currency.to_display(user, amount))


def _unit_money(user, amount) -> str:
    """سعر الوحدة الواحدة لباقةٍ بالكمية — كسورٌ دقيقة (0.000061) لا تُقرَّب إلى سنت."""
    from decimal import Decimal
    return str((Decimal(str(amount)) * currency.display_rate(user)).quantize(Decimal("0.00000001")).normalize())


# ————————————————————————— الرصيد —————————————————————————

@_api
def profile_view(request):
    """GET /client/api/profile — نظير `profile` لدى ZDK."""
    user = request.user
    wallet = getattr(user, "wallet", None)
    if wallet is None:
        return errors.error(errors.SERVER_ERROR, "No wallet for this account", 500)
    return Response({"status": "OK", "data": {
        "balance": _money(user, wallet.balance),
        "credit_limit": _money(user, wallet.credit_limit),
        # ما يستطيع إنفاقه فعلاً = الرصيد + ما يسمح به حدّه الائتماني
        "available": _money(user, wallet.balance - wallet.credit_limit),
        "currency": currency.display_currency(user),
        "name": user.name,
        "login_id": user.login_id,
    }})


# ———————————————————————— الكتالوج ————————————————————————

@_api
def products_view(request):
    """
    GET /client/api/products[?products_id=1,2][&base=1]

    `price` هو **سعر شراء هذا الوكيل** (سعر مجموعته) لا سعر لائحة عامّاً —
    فوكيلان يريان رقمين مختلفين للمنتج نفسه، وهو الصواب.
    """
    user = request.user
    qs = Product.objects.filter(
        tenant=user.tenant, status=Product.Status.ACTIVE, game__status="active",
    ).select_related("game").order_by("game__sort_order", "sort_order", "id")

    ids = (request.query_params.get("products_id") or "").strip()
    if ids:
        wanted = [int(x) for x in ids.replace(" ", "").split(",") if x.isdigit()]
        qs = qs.filter(id__in=wanted or [0])

    minimal = str(request.query_params.get("base") or "") in ("1", "true")
    rows = []
    for p in qs:
        row = {
            "id": p.id,
            "name": p.name,
            # الباقة «بالكمية»: سعر الوحدة الواحدة (لغة ZDK) — ونحن نسعّر لكل qty_unit
            "price": (_unit_money(user, services.resolve_sell_price(user, p) / p.qty_unit)
                      if p.is_amount else _money(user, services.resolve_sell_price(user, p))),
            "available": True,
            "category_name": p.game.name,
        }
        if not minimal:
            row.update({
                "params": ["playerId"] if p.game.require_player_id else [],
                # «amount» كما يعرضها ZDK: السعر للوحدة الواحدة، والكمية بين الحدّين
                "product_type": "amount" if p.is_amount else "package",
                "qty_values": {"min": p.qty_min, "max": p.qty_max} if p.is_amount else None,
                "category_img": p.game.image_url,
                "currency": currency.display_currency(user),
            })
        rows.append(row)
    return Response({"status": "OK", "data": rows})


# ————————————————————————— الطلب —————————————————————————

def _order_row(order, user) -> dict:
    """صفّ الطلب بلغة ZDK — واحدٌ لـ `newOrder` و`check` فلا يختلفان."""
    return {
        "order_id": order.receipt_no,
        "order_uuid": str(order.client_uuid or ""),
        "status": STATUS_OUT.get(order.status, "wait"),
        "quantity": order.quantity,
        "product_id": order.product_id,
        "product_name": order.product.name,
        "price": _money(user, order.buyer_price),
        "currency": currency.display_currency(user),
        "data": {"playerId": order.player_id},
        "pin": order.pin_result,
        "created_at": order.created_at.strftime("%Y-%m-%d %H:%M:%S"),
        # رسالة المزوّد للزبون — نفس معنى `replay_api` لدى ZDK وبنفس شكلها
        "replay_api": [order.provider_note] if order.provider_note else None,
    }


@_api
def new_order_view(request, product_id):
    """
    GET /client/api/newOrder/{productId}/params?qty=1&order_uuid=…[&playerId=…]

    **الطلب idempotent بالـ uuid:** إعادة النداء بنفس `order_uuid` تعيد الطلب
    الأوّل كما هو ولا تُنشئ ثانياً ولا تخصم مرّتين — وهو ما يحمي من انقطاع
    الشبكة بعد الشحن وقبل وصول الردّ.
    """
    user = request.user

    raw_uuid = (request.query_params.get("order_uuid") or "").strip()
    if not raw_uuid:
        return errors.error(errors.UUID_REQUIRED)
    try:
        client_uuid = UUID(raw_uuid)
    except (ValueError, AttributeError):
        return errors.error(errors.UUID_REQUIRED)

    qty = (request.query_params.get("qty") or "1").strip()

    # نداءٌ مكرّر ⇒ الطلب الأوّل نفسه، وبحالته الحالية لا بحالته وقت الإنشاء
    existing = Order.objects.filter(
        dealer=user, client_uuid=client_uuid,
    ).select_related("product").first()
    if existing is not None:
        return _place_response(existing, user, duplicate=True)

    product = Product.objects.filter(
        pk=product_id, tenant=user.tenant,
    ).select_related("game").first()
    if product is None:
        return errors.error(errors.PRODUCT_NOT_FOUND, http_status=404)
    if product.status != Product.Status.ACTIVE or product.game.status != "active":
        return errors.error(errors.PRODUCT_UNAVAILABLE)

    # الباقة الثابتة كميتها 1 وحدها؛ والكمية للباقة «بالكمية» بين حدّيها
    if not product.is_amount and qty not in ("", "1"):
        return errors.error(errors.QTY_UNSUPPORTED)

    player_id = (request.query_params.get("playerId") or "").strip()
    if product.game.require_player_id and not player_id:
        return errors.error(errors.PLAYER_ID_REQUIRED)

    retail = request.query_params.get("dealer_sell_price")
    if retail not in (None, ""):
        try:
            retail = currency.from_display(user, retail)
        except (InvalidOperation, TypeError):
            retail = None
    else:
        retail = None

    try:
        order = services.create_order(
            user, product,
            player_id=player_id,
            customer_phone=(request.query_params.get("customer_phone") or "").strip(),
            dealer_sell_price=retail,
            client_uuid=client_uuid,
            quantity=qty if product.is_amount else None,
        )
    except IntegrityError:
        # سباق: نداءان بنفس الـ uuid في اللحظة ذاتها. القيد في القاعدة ردّ
        # الثاني، والمعاملة انسحبت بخصمها — فنعيد طلب الأوّل.
        winner = Order.objects.filter(
            tenant=user.tenant, client_uuid=client_uuid,
        ).select_related("product").first()
        if winner is None:
            return errors.error(errors.SERVER_ERROR, http_status=500)
        return _place_response(winner, user, duplicate=True)
    except services.OrderError as e:
        text = str(e)
        spec = errors.INSUFFICIENT_BALANCE if "الحد الائتماني" in text else errors.ORDER_REJECTED
        return errors.error(spec, text)

    # التنفيذ **خارج** معاملة الإنشاء: يخرج إلى مزوّد على الشبكة، وإبقاء
    # المعاملة مفتوحة طواله كان يقفل صف المحفظة ثلاثين ثانية.
    _maybe_auto_execute(order)
    order.refresh_from_db()
    return _place_response(order, user)


def _place_response(order, user, *, duplicate: bool = False) -> Response:
    row = _order_row(order, user)
    body = {"status": row["status"], "data": row}
    if duplicate:
        # ليست خطأً — الطلب موجود وهذه حالته. العلامة لتشخيص العميل لا أكثر.
        body["duplicate"] = True
    return Response(body)


# ———————————————————————— الاستعلام ————————————————————————

@_api
def check_view(request):
    """
    GET /client/api/check?orders=<id1,id2>[&uuid=1]

    `uuid=1` يعني أن `orders` معرّفاتُ العميل (`order_uuid`) لا أرقامنا — وهو
    ما يحتاجه حين ينقطع الردّ فلا يعرف رقم الفيش أصلاً.
    """
    user = request.user
    raw = (request.query_params.get("orders") or "").strip()
    if not raw:
        return Response({"status": "OK", "data": []})

    keys = [x.strip() for x in raw.split(",") if x.strip()][:50]
    qs = Order.objects.filter(tenant=user.tenant, dealer=user).select_related("product")

    if str(request.query_params.get("uuid") or "") in ("1", "true"):
        valid = []
        for k in keys:
            try:
                valid.append(UUID(k))
            except (ValueError, AttributeError):
                continue
        qs = qs.filter(client_uuid__in=valid or [None])
    else:
        qs = qs.filter(receipt_no__in=keys)

    return Response({"status": "OK", "data": [_order_row(o, user) for o in qs]})
