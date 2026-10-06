"""نقاط الوكيل لشحن الخطوط: كشف الشركة · باقات الفئات · العروض الخاصة الحيّة."""
import re
from decimal import Decimal

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
        "id": p.id, "link_code": p.link_code, "znet_id": p.znet_id, "name": p.name, "details": p.details,
        "days": p.days, "gb": p.gb, "minutes": p.minutes,
        "kind": p.kind,
        "price": str(currency.to_display(user, dealer_price(user, p))),
        "recommended_price": str(currency.to_display(user, p.recommended_price)),
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
    # شعار الشركة: أول شعار رفعه المالك لأيّ فئة منها — يظهر على كراتها كلّها
    op_logo = next((c.logo_url for c in cats if c.logo_url), "")
    # الباقات داخل كل كرة من الأرخص (بسعر هذا الوكيل)، وكرات العروض أوّلاً
    price_of = {p.id: dealer_price(user, p) for p in pkgs}
    by_price = lambda x: (price_of[x.id], x.sort_order, x.id)  # noqa: E731
    offer_chips, general_chips = [], []
    for c in cats:
        pkgs_c = by_cat.get(c.id, [])
        # العروض تنفصل في كرة بنجمة (Ses ⇐ Ses*) كما في ZNET
        general = sorted((p for p in pkgs_c if p.kind != KontorPackage.Kind.OFFER), key=by_price)
        offers = sorted((p for p in pkgs_c if p.kind == KontorPackage.Kind.OFFER), key=by_price)
        for key, name, rows, bucket in ((f"{c.id}*", f"{c.name}*", offers, offer_chips),
                                        (str(c.id), c.name, general, general_chips)):
            if rows:
                bucket.append({
                    "id": key, "line_type": c.line_type, "name": name, "is_offer": key.endswith("*"),
                    "logo_url": c.logo_url or op_logo, "packages": [_pkg_row(user, p) for p in rows],
                })
    result = offer_chips + general_chips
    return Response({
        "operator": op, "operator_logo": op_logo,
        "currency": currency.display_currency(user),
        "categories": result,
    })


def _learn_specs(p: KontorPackage, o: dict) -> None:
    """
    تفاصيل الباقة (الوصف · GB · الدقائق · الأيام) لا يعطيها paket_listesi بل صفحة
    العروض وحدها — فنحفظها في الكتالوج أوّل ما تظهر، فتبدو للوكلاء قبل أي كشف.
    تملأ الفارغ فقط: ما كتبه المالك بيده لا يُمسّ.
    """
    changed = []
    if not p.details and o.get("details"):
        p.details = str(o["details"])[:300]; changed.append("details")
    for f in ("gb", "minutes", "days"):
        if not getattr(p, f) and o.get(f):
            setattr(p, f, int(o[f])); changed.append(f)
    if changed:
        p.save(update_fields=changed + ["updated_at"])


def live_offers(user, gsm: str, op: str) -> list[dict]:
    """
    العروض الحيّة لرقمٍ مطابَقةً مع كتالوجنا وبأسعار هذا الوكيل — العروض الوردية
    أوّلاً ثم البقية، كلٌّ من الأرخص. يرمي session_client.SessionError عند تعذّر الجلب.
    تستعملها صفحة الوكيل والواجهة الخارجية معاً.
    """
    offers = session_client.fetch_offers(gsm, op)

    catalog = {p.znet_id: p for p in KontorPackage.objects.filter(
        tenant=user.tenant, operator=op, status=KontorPackage.Status.ACTIVE)}
    rows = []
    for o in offers:
        p = catalog.get(o["znet_id"])
        if not p:
            continue  # غير موجودة في كتالوجنا (استورِد لتظهر وتُسعَّر)
        _learn_specs(p, o)
        rows.append({
            "id": p.id, "link_code": p.link_code, "znet_id": p.znet_id, "name": p.name,
            "details": o.get("details") or p.details,
            "days": o.get("days") or p.days, "gb": o.get("gb") or p.gb,
            "minutes": o.get("minutes") or p.minutes,
            "is_offer": o.get("is_offer", False),
            "price": str(currency.to_display(user, dealer_price(user, p))),
            "recommended_price": str(currency.to_display(user, p.recommended_price)),
        })
    # العروض الخاصة (الوردية) أوّلاً، وكلٌّ من المجموعتين من الأرخص
    rows.sort(key=lambda r: (not r["is_offer"], Decimal(r["price"])))
    return rows


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
        rows = live_offers(user, gsm, op)
    except session_client.SessionError as e:
        return Response({"detail": str(e)}, status=502)
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
        "package_name": o.package_name, "znet_id": o.znet_id,
        "price": str(currency.to_display(user, o.sell_price)),
        "dealer_sell_price": str(currency.to_display(user, o.dealer_sell_price)),
        "dealer_profit": str(currency.to_display(user, o.dealer_profit)),
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
    # سعر بيع الوكيل لزبونه يكتبه بعملة عرضه — يُحفظ بعملة الدفتر
    retail = request.data.get("dealer_sell_price")
    if retail not in (None, ""):
        try:
            retail = currency.from_display(user, str(retail).replace(",", "."))
        except Exception:  # noqa: BLE001
            return Response({"detail": "سعر بيع غير صحيح"}, status=400)
    try:
        order = _create_order(user, pkg, gsm, dealer_sell_price=retail)
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
