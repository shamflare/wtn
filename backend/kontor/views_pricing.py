"""المرحلة 2: مجموعات الأسعار، مصفوفة التسعير، وربط الوكلاء (لصاحب المتجر)."""
from decimal import Decimal, InvalidOperation

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.models import User

from . import services
from .models import (
    KontorDealerSetting, KontorPackage, KontorPackagePrice, KontorPriceGroup, Operator,
)
from .serializers import KontorPriceGroupSerializer
from .views import _require_admin


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def price_groups_view(request):
    if not _require_admin(request):
        return Response({"detail": "مخصّص لصاحب المتجر"}, status=403)
    tenant = request.user.tenant
    if request.method == "GET":
        qs = KontorPriceGroup.objects.filter(tenant=tenant)
        return Response(KontorPriceGroupSerializer(qs, many=True).data)
    name = (request.data.get("name") or "").strip()
    if not name:
        return Response({"detail": "الاسم مطلوب"}, status=400)
    g = KontorPriceGroup.objects.create(tenant=tenant, name=name)
    return Response(KontorPriceGroupSerializer(g).data, status=201)


@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def price_group_delete_view(request, pk):
    if not _require_admin(request):
        return Response({"detail": "مخصّص لصاحب المتجر"}, status=403)
    g = KontorPriceGroup.objects.filter(pk=pk, tenant=request.user.tenant).first()
    if not g:
        return Response({"detail": "غير موجود"}, status=404)
    g.delete()
    return Response({"deleted": True})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def price_matrix_view(request):
    """مصفوفة أسعار شركةٍ واحدة: الباقات × المجموعات. ?operator= (افتراضاً Turkcell)."""
    if not _require_admin(request):
        return Response({"detail": "مخصّص لصاحب المتجر"}, status=403)
    tenant = request.user.tenant
    op = request.query_params.get("operator") or Operator.TURKCELL
    groups = list(KontorPriceGroup.objects.filter(tenant=tenant))
    pkgs = (KontorPackage.objects.filter(tenant=tenant, operator=op)
            .select_related("category").order_by("category__line_type", "sort_order", "id"))
    prices = {
        (pp.package_id, pp.group_id): pp
        for pp in KontorPackagePrice.objects.filter(tenant=tenant, package__operator=op)
    }
    rows = []
    for p in pkgs:
        cells = {}
        for g in groups:
            pp = prices.get((p.id, g.id))
            cells[str(g.id)] = {
                "price": str(pp.price) if pp else "",
                "linked": bool(pp and pp.margin_mode and pp.margin_value is not None),
                "mode": pp.margin_mode if pp else "",
                "value": str(pp.margin_value) if (pp and pp.margin_value is not None) else "",
                "round": bool(pp.margin_round) if pp else False,
            }
        rows.append({
            "id": p.id, "name": p.name,
            "category": p.category.name if p.category else "",
            "znet_id": p.znet_id, "cost_price": str(p.cost_price),
            "recommended_price": str(p.recommended_price), "prices": cells,
        })
    return Response({
        "operator": op,
        "groups": KontorPriceGroupSerializer(groups, many=True).data,
        "rows": rows,
    })


def _dec(v):
    return Decimal(str(v).replace(",", "."))


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def set_price_view(request):
    """خلية: {package, group, price} يدوي، أو {package, group, mode, value, round} قاعدة."""
    if not _require_admin(request):
        return Response({"detail": "مخصّص لصاحب المتجر"}, status=403)
    tenant = request.user.tenant
    pkg = KontorPackage.objects.filter(pk=request.data.get("package"), tenant=tenant).first()
    grp = KontorPriceGroup.objects.filter(pk=request.data.get("group"), tenant=tenant).first()
    if not (pkg and grp):
        return Response({"detail": "باقة أو مجموعة غير صحيحة"}, status=400)

    mode = request.data.get("mode") or ""
    if mode in ("percent", "fixed"):
        try:
            value = _dec(request.data.get("value"))
        except (InvalidOperation, TypeError):
            return Response({"detail": "قيمة القاعدة غير صحيحة"}, status=400)
        rnd = bool(request.data.get("round"))
        price = services._apply_margin(pkg.cost_price, mode, value, rnd)
        defaults = {"price": price, "margin_mode": mode, "margin_value": value, "margin_round": rnd}
    else:
        try:
            price = _dec(request.data.get("price"))
        except (InvalidOperation, TypeError):
            return Response({"detail": "سعر غير صحيح"}, status=400)
        defaults = {"price": price, "margin_mode": "", "margin_value": None, "margin_round": False}

    pp, _ = KontorPackagePrice.objects.update_or_create(
        tenant=tenant, package=pkg, group=grp, defaults=defaults)
    return Response({"package": pkg.id, "group": grp.id, "price": str(pp.price)})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def bulk_price_view(request):
    """
    قاعدة على كل باقات شركةٍ لمجموعة: {group, operator, mode, value, round}،
    أو {group, operator, to_recommended:true} لضبطها على السعر الموصى.
    """
    if not _require_admin(request):
        return Response({"detail": "مخصّص لصاحب المتجر"}, status=403)
    tenant = request.user.tenant
    grp = KontorPriceGroup.objects.filter(pk=request.data.get("group"), tenant=tenant).first()
    if not grp:
        return Response({"detail": "مجموعة غير صحيحة"}, status=400)
    op = request.data.get("operator") or Operator.TURKCELL
    pkgs = KontorPackage.objects.filter(tenant=tenant, operator=op)

    to_rec = request.data.get("to_recommended")
    mode = request.data.get("mode") or ""
    value = None
    rnd = bool(request.data.get("round"))
    if not to_rec:
        if mode not in ("percent", "fixed"):
            return Response({"detail": "القاعدة غير صحيحة"}, status=400)
        try:
            value = _dec(request.data.get("value"))
        except (InvalidOperation, TypeError):
            return Response({"detail": "قيمة غير صحيحة"}, status=400)

    n = 0
    for p in pkgs:
        if to_rec:
            defaults = {"price": (p.recommended_price or Decimal("0")),
                        "margin_mode": "", "margin_value": None, "margin_round": False}
        else:
            defaults = {"price": services._apply_margin(p.cost_price, mode, value, rnd),
                        "margin_mode": mode, "margin_value": value, "margin_round": rnd}
        KontorPackagePrice.objects.update_or_create(tenant=tenant, package=p, group=grp, defaults=defaults)
        n += 1
    return Response({"updated": n})


@api_view(["GET", "PATCH"])
@permission_classes([IsAuthenticated])
def dealer_settings_view(request):
    """
    GET: الوكلاء مع مجموعتهم وإذن الاستعلام لكل شركة.
    PATCH: [{dealer, operator, group?, can_query?}] دفعة.
    """
    if not _require_admin(request):
        return Response({"detail": "مخصّص لصاحب المتجر"}, status=403)
    tenant = request.user.tenant
    ops = [c.value for c in Operator]

    if request.method == "GET":
        dealers = User.objects.filter(tenant=tenant, role=User.Role.BAYI).order_by("name")
        settings = {(s.dealer_id, s.operator): s
                    for s in KontorDealerSetting.objects.filter(tenant=tenant)}
        data = []
        for d in dealers:
            per_op = {op: {"group": (s := settings.get((d.id, op))) and s.group_id,
                           "can_query": s.can_query if s else True} for op in ops}
            data.append({"id": d.id, "name": d.name, "login_id": d.login_id, "operators": per_op})
        return Response({
            "operators": ops,
            "groups": KontorPriceGroupSerializer(
                KontorPriceGroup.objects.filter(tenant=tenant), many=True).data,
            "dealers": data,
        })

    rows = request.data if isinstance(request.data, list) else [request.data]
    for row in rows:
        dealer = User.objects.filter(pk=row.get("dealer"), tenant=tenant, role=User.Role.BAYI).first()
        op = row.get("operator")
        if not dealer or op not in ops:
            continue
        defaults = {}
        if "group" in row:
            defaults["group_id"] = row["group"] or None
        if "can_query" in row:
            defaults["can_query"] = bool(row["can_query"])
        KontorDealerSetting.objects.update_or_create(
            tenant=tenant, dealer=dealer, operator=op, defaults=defaults)
    return Response({"ok": True})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def admin_orders_view(request):
    """كل طلبات شحن الخطوط (لصاحب المتجر) — مع تصفية ?status= و?operator=."""
    if not _require_admin(request):
        return Response({"detail": "مخصّص لصاحب المتجر"}, status=403)
    from .models import KontorOrder
    qs = (KontorOrder.objects.filter(tenant=request.user.tenant)
          .select_related("package", "dealer", "provider"))
    st = request.query_params.get("status")
    op = request.query_params.get("operator")
    if st:
        qs = qs.filter(status=st)
    if op:
        qs = qs.filter(operator=op)
    rows = [{
        "id": o.id, "gsm": o.gsm, "operator": o.operator,
        "dealer": o.dealer.name, "package_name": o.package.name, "znet_id": o.package.znet_id,
        "cost_price": str(o.cost_price), "sell_price": str(o.sell_price), "profit": str(o.profit),
        "status": o.status, "status_label": o.get_status_display(),
        "provider": o.provider.name if o.provider else "", "note": o.provider_note,
        "created_at": o.created_at.strftime("%Y-%m-%d %H:%M"),
    } for o in qs[:300]]
    return Response(rows)
