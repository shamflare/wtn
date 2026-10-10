"""
الواجهة الخارجية لشحن الخطوط التركية (موبايل).

نفس عقد الألعاب حرفاً حيث أمكن: ترويسة `api-token`، جسم الخطأ نفسه، `order_uuid`
لمنع الشحن المزدوج، والحالات الثلاث accept/wait/reject — فمن ربط الألعاب يربط
الخطوط بنفس كوده تقريباً. لا ZDK هنا (ZDK لا يبيع خطوطاً)، فالمسارات تحت
`/client/api/mobile/` كي لا تختلط بمسارات المنتجات.

**المال:** نفس مسار ضغطة «شحن» في لوحة الوكيل — `kontor.execution` يخصم ويرسل
إلى ZNET ويُرجع عند الرفض. لا منطق مالي جديد هنا.
"""
from decimal import InvalidOperation
from uuid import UUID

from django.db import IntegrityError
from rest_framework.response import Response

from core import currency
from kontor import session_client
from kontor.execution import KontorOrderError, create_order, execute
from kontor.models import KontorCategory, KontorOrder, KontorPackage, Operator
from kontor.services import dealer_can_query, dealer_price
from kontor.views_store import _clean_gsm, _valid, live_offers

from . import errors
from .views import _api, _money

STATUS_OUT = {
    KontorOrder.Status.SUCCESS: "accept",
    KontorOrder.Status.FAILED: "reject",
    KontorOrder.Status.REFUNDED: "reject",
    KontorOrder.Status.PENDING: "wait",
    KontorOrder.Status.PROCESSING: "wait",
}
OPERATORS = [c.value for c in Operator]
OP_LABEL = dict(Operator.choices)


def _gsm(request):
    """الرقم من ?gsm= — يقبل 05… و905… والأرقام العربية، ويعيد 10 خانات أو None."""
    g = _clean_gsm(request.query_params.get("gsm", ""))
    return g if _valid(g) else None


# ———————————————————————— الكتالوج ————————————————————————

@_api
def packages_view(request):
    """
    GET /client/api/mobile/packages[?operator=Turkcell][&packages_id=1,2][&base=1]

    `price` سعر شراء **هذا الوكيل** (مجموعته)، و`recommended_price` السعر المقترح
    لبيعه لزبونه. `id` هو **رقم الربط** (link_code — افتراضه رقم ZNET) الذي يُرسَل في newOrder.
    """
    user = request.user
    qs = (KontorPackage.objects
          .filter(tenant=user.tenant, status=KontorPackage.Status.ACTIVE,
                  category__status=KontorCategory.Status.ACTIVE)
          .select_related("category"))
    op = (request.query_params.get("operator") or "").strip()
    if op:
        if op not in OPERATORS:
            return errors.error(errors.OPERATOR_INVALID)
        qs = qs.filter(operator=op)
    ids = (request.query_params.get("packages_id") or "").strip()
    if ids:
        wanted = [x for x in ids.replace(" ", "").split(",") if x]
        qs = qs.filter(link_code__in=wanted or [""])

    minimal = str(request.query_params.get("base") or "") in ("1", "true")
    order = {o: i for i, o in enumerate(OPERATORS)}
    from orders.pricebook import MobilePrices
    book = MobilePrices(user)
    rows = []
    for p in qs:
        price = book.price(p)
        offer = p.kind == KontorPackage.Kind.OFFER
        row = {
            "id": p.link_code,
            "name": p.name,
            "operator": p.operator,
            "price": _money(user, price),
            "available": True,
            # العروض في فئة بنجمة (Ses*) — كما يراها الوكيل في لوحته
            "category_name": f"{p.category.name}*" if offer else p.category.name,
        }
        if not minimal:
            row.update({
                "operator_label": OP_LABEL.get(p.operator, p.operator),
                "line_type": p.category.line_type,
                "is_offer": offer,
                "details": p.details,
                "days": p.days, "gb": p.gb, "minutes": p.minutes,
                "recommended_price": _money(user, p.recommended_price),
                "params": ["gsm"],
                "currency": currency.display_currency(user),
            })
        rows.append((order.get(p.operator, 9), not offer, p.category.sort_order, price, row))
    # الشركات بترتيبها، والعروض أوّلاً داخل كلٍّ منها، ثم الأرخص — كلوحة الوكيل
    rows.sort(key=lambda r: r[:4])
    return Response({"status": "OK", "data": [r[-1] for r in rows]})


# ———————————————————— كشف الشركة والعروض الحيّة ————————————————————

@_api
def detect_view(request):
    """GET /client/api/mobile/detect?gsm=5XXXXXXXXX — شركة الخط (استعلام حيّ، ثوانٍ)."""
    gsm = _gsm(request)
    if not gsm:
        return errors.error(errors.GSM_INVALID)
    try:
        op = session_client.detect_operator(gsm)
    except session_client.SessionError as e:
        return errors.error(errors.LIVE_UNAVAILABLE, str(e), http_status=502)
    if not op:
        return errors.error(errors.OPERATOR_UNKNOWN, http_status=404)
    return Response({"status": "OK", "data": {
        "gsm": gsm, "operator": op, "operator_label": OP_LABEL.get(op, op),
    }})


@_api
def offers_view(request):
    """
    GET /client/api/mobile/offers?gsm=5XXXXXXXXX&operator=Turkcell

    الباقات المتاحة لهذا الرقم تحديداً الآن (منها العروض الخاصة is_offer=true)،
    بأسعار هذا الوكيل. يحتاج إذن الاستعلام من صاحب المتجر.
    """
    user = request.user
    gsm = _gsm(request)
    if not gsm:
        return errors.error(errors.GSM_INVALID)
    op = (request.query_params.get("operator") or "").strip()
    if op not in OPERATORS:
        return errors.error(errors.OPERATOR_INVALID)
    if not dealer_can_query(user, op):
        return errors.error(errors.QUERY_NOT_ALLOWED, http_status=403)
    try:
        rows = live_offers(user, gsm, op)
    except session_client.SessionError as e:
        return errors.error(errors.LIVE_UNAVAILABLE, str(e), http_status=502)
    cur = currency.display_currency(user)
    for r in rows:
        r.pop("znet_id", None)  # معرّف المزوّد شأنٌ داخلي
        r["id"] = r.pop("link_code")  # رقم الربط — نفس ما في packages وnewOrder
        r["currency"] = cur
    return Response({"status": "OK", "data": rows})


# ————————————————————————— الطلب —————————————————————————

def _order_row(o: KontorOrder, user) -> dict:
    return {
        "order_id": str(o.id),
        "order_uuid": str(o.client_uuid or ""),
        "status": STATUS_OUT.get(o.status, "wait"),
        "package_id": o.link_code,
        "package_name": o.package_name,
        "operator": o.operator,
        "gsm": o.gsm,
        "price": _money(user, o.buyer_price),
        "dealer_sell_price": _money(user, o.dealer_sell_price),
        "currency": currency.display_currency(user),
        "created_at": o.created_at.strftime("%Y-%m-%d %H:%M:%S"),
        "replay_api": [o.provider_note] if o.provider_note else None,
    }


def _place(o: KontorOrder, user, *, duplicate=False) -> Response:
    row = _order_row(o, user)
    body = {"status": row["status"], "data": row}
    if duplicate:
        body["duplicate"] = True
    return Response(body)


@_api
def new_order_view(request, package_id):
    """
    GET /client/api/mobile/newOrder/{packageId}/params?gsm=5XXXXXXXXX&order_uuid={UUID}
        [&dealer_sell_price=…]

    idempotent بالـ uuid كطلبات الألعاب: نفس المعرّف يعيد الطلب الأوّل ولا يخصم مرّتين.
    """
    user = request.user
    try:
        client_uuid = UUID((request.query_params.get("order_uuid") or "").strip())
    except (ValueError, AttributeError):
        return errors.error(errors.UUID_REQUIRED)

    existing = (KontorOrder.objects.filter(dealer=user, client_uuid=client_uuid)
                .select_related("package").first())
    if existing is not None:
        return _place(existing, user, duplicate=True)

    gsm = _gsm(request)
    if not gsm:
        return errors.error(errors.GSM_INVALID)

    pkg = (KontorPackage.objects.filter(link_code=str(package_id).strip(), tenant=user.tenant)
           .select_related("category").first() if str(package_id).strip() else None)
    if pkg is None:
        return errors.error(errors.PRODUCT_NOT_FOUND, http_status=404)
    if pkg.status != KontorPackage.Status.ACTIVE or (
            pkg.category and pkg.category.status != KontorCategory.Status.ACTIVE):
        return errors.error(errors.PRODUCT_UNAVAILABLE)

    retail = request.query_params.get("dealer_sell_price")
    if retail not in (None, ""):
        try:
            retail = currency.from_display(user, str(retail).replace(",", "."))
        except (InvalidOperation, TypeError, ValueError):
            retail = None
    else:
        retail = None

    try:
        order = create_order(user, pkg, gsm, dealer_sell_price=retail, client_uuid=client_uuid)
    except IntegrityError:
        # سباق نداءين بنفس الـ uuid — القيد ردّ الثاني وانسحب خصمه؛ نعيد الأوّل
        winner = (KontorOrder.objects.filter(dealer=user, client_uuid=client_uuid)
                  .select_related("package").first())
        if winner is None:
            return errors.error(errors.SERVER_ERROR, http_status=500)
        return _place(winner, user, duplicate=True)
    except KontorOrderError as e:
        text = str(e)
        spec = errors.INSUFFICIENT_BALANCE if "الحد الائتماني" in text else errors.ORDER_REJECTED
        return errors.error(spec, text)

    # الإرسال إلى ZNET خارج معاملة الإنشاء — كي لا يُقفل صفّ المحفظة طوال الاتصال
    execute(order)
    order.refresh_from_db()
    return _place(order, user)


@_api
def check_view(request):
    """GET /client/api/mobile/check?orders=<id1,id2>[&uuid=1] — حتى 50 طلباً."""
    user = request.user
    raw = (request.query_params.get("orders") or "").strip()
    if not raw:
        return Response({"status": "OK", "data": []})
    keys = [x.strip() for x in raw.split(",") if x.strip()][:50]
    qs = KontorOrder.objects.filter(tenant=user.tenant, dealer=user).select_related("package")
    if str(request.query_params.get("uuid") or "") in ("1", "true"):
        valid = []
        for k in keys:
            try:
                valid.append(UUID(k))
            except (ValueError, AttributeError):
                continue
        qs = qs.filter(client_uuid__in=valid or [None])
    else:
        qs = qs.filter(id__in=[int(k) for k in keys if k.isdigit()] or [0])
    return Response({"status": "OK", "data": [_order_row(o, user) for o in qs]})
