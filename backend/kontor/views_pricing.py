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
            "id": p.id, "name": p.name, "details": p.details,
            "category": p.category.name if p.category else "",
            "category_id": p.category_id, "kind": p.kind, "status": p.status,
            "znet_id": p.znet_id, "cost_price": str(p.cost_price),
            "provider_cost": str(p.provider_cost),
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
    تسعير جماعي لباقات شركةٍ واحدة (كنظيره في الألعاب):
      {group, operator, mode, value, round, packages?}  قاعدة مرتبطة بالكلفة لمجموعة.
      {group:"recommended", operator, mode, value, round, packages?}  تُكتب في الموصى مرّة واحدة.
      {group, operator, to_recommended:true, packages?}  خلايا المجموعة = الموصى.
    `packages` فارغة ⇐ كل باقات الشركة. الباقة بلا كلفة تُتخطّى في القواعد.
    """
    if not _require_admin(request):
        return Response({"detail": "مخصّص لصاحب المتجر"}, status=403)
    tenant = request.user.tenant
    to_rec_col = request.data.get("group") == "recommended"
    grp = None
    if not to_rec_col:
        grp = KontorPriceGroup.objects.filter(pk=request.data.get("group"), tenant=tenant).first()
        if not grp:
            return Response({"detail": "مجموعة غير صحيحة"}, status=400)
    op = request.data.get("operator") or Operator.TURKCELL
    pkgs = KontorPackage.objects.filter(tenant=tenant, operator=op)
    ids = request.data.get("packages") or []
    if ids:
        pkgs = pkgs.filter(pk__in=ids)

    to_rec = bool(request.data.get("to_recommended")) and not to_rec_col
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

    n, skipped = 0, []
    for p in pkgs:
        if not to_rec and not p.cost_price:
            skipped.append(p.name)
            continue
        if to_rec_col:
            p.recommended_price = services._apply_margin(p.cost_price, mode, value, rnd)
            p.save(update_fields=["recommended_price", "updated_at"])
        else:
            if to_rec:
                defaults = {"price": (p.recommended_price or Decimal("0")),
                            "margin_mode": "", "margin_value": None, "margin_round": False}
            else:
                defaults = {"price": services._apply_margin(p.cost_price, mode, value, rnd),
                            "margin_mode": mode, "margin_value": value, "margin_round": rnd}
            KontorPackagePrice.objects.update_or_create(
                tenant=tenant, package=p, group=grp, defaults=defaults)
        n += 1
    return Response({"updated": n, "group": grp.name if grp else "", "skipped_zero_cost": skipped})


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
    """
    طلبات شحن الخطوط (لصاحب المتجر) مع ملخّصها. تصفية: ?status= ?operator=
    ?dealer= ?q= (رقم/باقة/مرجع) ?date_from= ?date_to= (YYYY-MM-DD).
    """
    if not _require_admin(request):
        return Response({"detail": "مخصّص لصاحب المتجر"}, status=403)
    from django.db.models import Count, Q, Sum
    from .models import KontorOrder
    qs = (KontorOrder.objects.filter(tenant=request.user.tenant)
          .select_related("package", "dealer", "provider"))
    qp = request.query_params
    if qp.get("operator"):
        qs = qs.filter(operator=qp["operator"])
    if qp.get("dealer"):
        qs = qs.filter(dealer_id=qp["dealer"])
    if qp.get("q"):
        t = qp["q"].strip()
        qs = qs.filter(Q(gsm__icontains=t) | Q(package__name__icontains=t) | Q(tekil__icontains=t))
    if qp.get("date_from"):
        qs = qs.filter(created_at__date__gte=qp["date_from"])
    if qp.get("date_to"):
        qs = qs.filter(created_at__date__lte=qp["date_to"])

    # الملخّص قبل تصفية الحالة — فتبقى أعداد الكرات صحيحة أيّاً كان المختار
    counts = {r["status"]: r["n"] for r in qs.values("status").annotate(n=Count("id"))}
    ok = qs.filter(status=KontorOrder.Status.SUCCESS).aggregate(s=Sum("sell_price"), p=Sum("profit"))
    st = qp.get("status")
    if st:
        qs = qs.filter(status=st)
    rows = [{
        "id": o.id, "gsm": o.gsm, "operator": o.operator,
        "dealer": o.dealer.name, "dealer_id": o.dealer_id,
        "package_name": o.package.name, "znet_id": o.package.znet_id,
        "cost_price": str(o.cost_price), "sell_price": str(o.sell_price), "profit": str(o.profit),
        "status": o.status, "status_label": o.get_status_display(),
        "provider": o.provider.name if o.provider else "", "note": o.provider_note,
        "tekil": o.tekil, "balance_before": str(o.balance_before), "balance_after": str(o.balance_after),
        "created_at": o.created_at.strftime("%Y-%m-%d %H:%M"),
        "updated_at": o.updated_at.strftime("%Y-%m-%d %H:%M"),
    } for o in qs[:300]]
    return Response({
        "results": rows,
        "summary": {
            "counts": counts, "total": sum(counts.values()),
            "sales": str(ok["s"] or 0), "profit": str(ok["p"] or 0),
        },
    })
