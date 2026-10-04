"""نقاط الوكيل لشحن الخطوط: كشف الشركة · باقات الفئات · العروض الخاصة الحيّة."""
import re

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core import currency

from . import session_client
from .models import KontorCategory, KontorPackage
from .services import dealer_can_query, dealer_price

_AR_DIGITS = {ord(c): str(i) for i, c in enumerate("٠١٢٣٤٥٦٧٨٩")}
_AR_DIGITS.update({ord(c): str(i) for i, c in enumerate("۰۱۲۳۴۵۶۷۸۹")})


def _clean_gsm(raw: str) -> str:
    """رقم من 10 خانات يبدأ بـ5 — يقبل الأرقام العربية ويزيل الفراغات/الرموز."""
    s = (raw or "").translate(_AR_DIGITS)
    s = re.sub(r"\D", "", s)
    if s.startswith("90"):
        s = s[2:]
    if len(s) == 11 and s.startswith("0"):
        s = s[1:]
    return s


def _valid(gsm: str) -> bool:
    return len(gsm) == 10 and gsm.startswith("5")


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def detect_view(request):
    """كشف شركة الخط (جلسة حيّة). {gsm} ⇐ {operator, operator_label}."""
    gsm = _clean_gsm(request.data.get("gsm", ""))
    if not _valid(gsm):
        return Response({"detail": "رقم غير صحيح — 10 خانات تبدأ بـ5"}, status=400)
    try:
        op = session_client.detect_operator(gsm)
    except session_client.SessionError as e:
        return Response({"detail": str(e)}, status=502)
    if not op:
        return Response({"detail": "تعذّر كشف الشركة لهذا الرقم"}, status=404)
    label = dict(KontorPackage._meta.get_field("operator").choices).get(op, op)
    return Response({"gsm": gsm, "operator": op, "operator_label": label})


def _pkg_row(user, p: KontorPackage) -> dict:
    return {
        "id": p.id, "znet_id": p.znet_id, "name": p.name, "details": p.details,
        "days": p.days, "gb": p.gb, "minutes": p.minutes,
        "kind": p.kind,
        "price": str(currency.to_display(user, dealer_price(user, p))),
    }


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def store_packages_view(request):
    """باقات شركةٍ مجمّعةً بالفئات (الكرات) بأسعار الوكيل. ?operator= مطلوب."""
    user = request.user
    op = request.query_params.get("operator")
    if not op:
        return Response({"detail": "operator مطلوب"}, status=400)
    cats = (KontorCategory.objects.filter(tenant=user.tenant, operator=op,
                                          status=KontorCategory.Status.ACTIVE)
            .order_by("sort_order", "id"))
    pkgs = (KontorPackage.objects.filter(tenant=user.tenant, operator=op,
                                         status=KontorPackage.Status.ACTIVE)
            .select_related("category"))
    by_cat: dict[int, list] = {}
    for p in pkgs:
        by_cat.setdefault(p.category_id, []).append(p)
    result = []
    for c in cats:
        rows = [_pkg_row(user, p) for p in sorted(by_cat.get(c.id, []), key=lambda x: (x.sort_order, x.id))]
        if rows:
            result.append({
                "id": c.id, "line_type": c.line_type, "name": c.name,
                "logo_url": c.logo_url, "packages": rows,
            })
    return Response({
        "operator": op,
        "currency": currency.display_currency(user),
        "categories": result,
    })


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def store_offers_view(request):
    """
    العروض الخاصة الحيّة لرقمٍ: {gsm, operator} ⇐ قائمة باقات مع علم «عرض» (وردي).
    تحتاج إذن استعلام الوكيل لهذه الشركة. تُطابَق بالمعرّف مع الكتالوج للسعر.
    """
    user = request.user
    gsm = _clean_gsm(request.data.get("gsm", ""))
    op = request.data.get("operator", "")
    if not _valid(gsm):
        return Response({"detail": "رقم غير صحيح"}, status=400)
    if not dealer_can_query(user, op):
        return Response({"detail": "استعلام العروض غير مسموح لك لهذه الشركة"}, status=403)
    try:
        offers = session_client.fetch_offers(gsm, op)
    except session_client.SessionError as e:
        return Response({"detail": str(e)}, status=502)

    catalog = {p.znet_id: p for p in KontorPackage.objects.filter(
        tenant=user.tenant, operator=op, status=KontorPackage.Status.ACTIVE)}
    rows = []
    for o in offers:
        p = catalog.get(o["znet_id"])
        if not p:
            continue  # غير موجودة في كتالوجنا (استورِد لتظهر وتُسعَّر)
        rows.append({
            "id": p.id, "znet_id": p.znet_id, "name": p.name,
            "details": o.get("details") or p.details,
            "days": o.get("days") or p.days, "gb": o.get("gb") or p.gb,
            "minutes": o.get("minutes") or p.minutes,
            "is_offer": o.get("is_offer", False),
            "price": str(currency.to_display(user, dealer_price(user, p))),
        })
    return Response({"gsm": gsm, "operator": op,
                     "currency": currency.display_currency(user), "offers": rows})


# ─────────────────────── الشراء والطلبات (المرحلة 5) ───────────────────────
from .execution import KontorOrderError  # noqa: E402
from .execution import create_order as _create_order  # noqa: E402
from .execution import execute as _execute  # noqa: E402
from .models import KontorOrder  # noqa: E402


def _order_row(user, o: KontorOrder) -> dict:
    return {
        "id": o.id, "gsm": o.gsm, "operator": o.operator,
        "package_name": o.package.name, "znet_id": o.package.znet_id,
        "price": str(currency.to_display(user, o.sell_price)),
        "status": o.status, "status_label": o.get_status_display(),
        "note": o.provider_note, "created_at": o.created_at.strftime("%Y-%m-%d %H:%M"),
    }


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def buy_view(request):
    """شراء باقة لرقم: {package, gsm} ⇐ ينشئ الطلب، يخصم، ثم يرسل إلى ZNET."""
    user = request.user
    gsm = _clean_gsm(request.data.get("gsm", ""))
    if not _valid(gsm):
        return Response({"detail": "رقم غير صحيح"}, status=400)
    pkg = KontorPackage.objects.filter(pk=request.data.get("package"), tenant=user.tenant).first()
    if not pkg:
        return Response({"detail": "الباقة غير موجودة"}, status=404)
    try:
        order = _create_order(user, pkg, gsm)
    except KontorOrderError as e:
        return Response({"detail": str(e)}, status=400)
    _execute(order)
    return Response(_order_row(user, order), status=201)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def my_orders_view(request):
    """طلبات شحن الخطوط للوكيل الحالي."""
    qs = (KontorOrder.objects.filter(tenant=request.user.tenant, dealer=request.user)
          .select_related("package")[:100])
    return Response([_order_row(request.user, o) for o in qs])
