"""
واجهات الجرد النهائي: اللقطة الحيّة · البنود اليدوية · جلب الأرصدة · الحفظ والسجلّ.
"""
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.db.models import Count, Sum
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core import currency as cur
from core.models import User
from orders.models import Order
from payments.models import CURRENCIES
from providers.adapters.registry import adapter_for
from providers.models import Provider

from . import services
from .models import InventoryConfig, ManualItem, Snapshot, SnapshotLine

ZERO = Decimal("0")
CENT = Decimal("0.01")


def _money_base(v) -> str:
    """كل مبلغ يخرج بخانتين عشريتين — «0» و«0.00» في الردّ نفسه تربك الواجهة."""
    return str(Decimal(v or 0).quantize(CENT))


def _guard(request):
    """الجرد لصاحب المتجر، وللوكيل الكبير جرده هو (يُعرف بـ `_agent`)."""
    if request.user.role not in (User.Role.TENANT_ADMIN, User.Role.ANA_BAYI):
        return None, Response({"detail": "الجرد لصاحب المتجر وحده"}, status=403)
    if request.user.tenant is None:
        return None, Response({"detail": "لا يوجد متجر"}, status=400)
    return request.user.tenant, None


def _agent(request):
    """الوكيل الكبير صاحب هذا الجرد — أو None لجرد المتجر."""
    return request.user if request.user.role == User.Role.ANA_BAYI else None


def _owner_only(request):
    """ما يخصّ المتجر وحده (المزوّدون ومصادرهم) — لا يطرقه الوكيل الكبير."""
    if _agent(request) is not None:
        return Response({"detail": "لا مزوّدين في جرد الوكيل"}, status=403)
    return None


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def live_view(request):
    """اللقطة الحالية — ما سيُحفظ لو ضغطتَ «حفظ الجرد» الآن."""
    tenant, err = _guard(request)
    if err:
        return err
    agent = _agent(request)
    data = services.for_viewer(services.build(tenant, agent), agent)
    data["currencies"] = [{"code": c, "label": lbl} for c, lbl in CURRENCIES]
    return Response(data)


# ─────────────────────────── البنود اليدوية ───────────────────────────

def _item_row(m):
    return {
        "id": m.id, "name": m.name, "amount": _money_base(m.amount),
        "currency": m.currency, "note": m.note, "sort_order": m.sort_order,
    }


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def item_create_view(request):
    """إضافة بند يدوي — بالاسم وحده يكفي، والمبلغ يُعدَّل بعدها من الجدول."""
    tenant, err = _guard(request)
    if err:
        return err
    name = str(request.data.get("name") or "").strip()
    if not name:
        return Response({"detail": "اسم البند مطلوب"}, status=400)
    currency = str(request.data.get("currency") or cur.base_currency(tenant))
    if currency != cur.base_currency(tenant) and not cur.rate_of(tenant, currency):
        return Response(
            {"detail": f"لا سعر صرف مضبوط للعملة {currency} — اضبطه في «أسعار الصرف» أولاً"},
            status=400,
        )
    agent = _agent(request)
    if agent is not None and "currency" not in request.data:
        currency = cur.display_currency(agent)        # بند الوكيل بعملته افتراضاً
    last = ManualItem.objects.filter(tenant=tenant, owner=agent).order_by("-sort_order").first()
    m = ManualItem.objects.create(
        tenant=tenant, owner=agent, name=name[:120], currency=currency,
        sort_order=(last.sort_order + 1) if last else 0,
    )
    return Response(_item_row(m), status=201)


@api_view(["POST", "DELETE"])
@permission_classes([IsAuthenticated])
def item_view(request, item_id):
    """تعديل بند يدوي أو حذفه."""
    tenant, err = _guard(request)
    if err:
        return err
    try:
        m = ManualItem.objects.get(pk=item_id, tenant=tenant, owner=_agent(request))
    except ManualItem.DoesNotExist:
        return Response({"detail": "البند غير موجود"}, status=404)

    if request.method == "DELETE":
        m.delete()
        return Response({"deleted": True})

    data = request.data
    if "name" in data:
        name = str(data["name"] or "").strip()
        if not name:
            return Response({"detail": "اسم البند مطلوب"}, status=400)
        m.name = name[:120]
    if "amount" in data:
        try:
            m.amount = Decimal(str(data["amount"] or "0").replace(",", ""))
        except (InvalidOperation, TypeError):
            return Response({"detail": "مبلغ غير صحيح"}, status=400)
    if "currency" in data:
        c = str(data["currency"] or "")
        if c != cur.base_currency(tenant) and not cur.rate_of(tenant, c):
            return Response({"detail": f"لا سعر صرف مضبوط للعملة {c}"}, status=400)
        m.currency = c
    if "note" in data:
        m.note = str(data["note"] or "")[:200]
    m.save()
    return Response(_item_row(m))


@api_view(["PUT"])
@permission_classes([IsAuthenticated])
def sources_view(request):
    """تفعيل/تعطيل مصدر تلقائي — أي البنود تدخل رأس مالك قرارُك أنت."""
    tenant, err = _guard(request)
    if err or (err := _owner_only(request)):
        return err
    conf, _ = InventoryConfig.objects.get_or_create(tenant=tenant)
    incoming = request.data.get("sources")
    if not isinstance(incoming, dict):
        return Response({"detail": "صيغة غير صحيحة"}, status=400)
    known = {k for k, _ in services.SOURCES}
    conf.sources = {k: bool(v) for k, v in incoming.items() if k in known}
    conf.save(update_fields=["sources", "updated_at"])
    return Response(services.build(tenant))


# ─────────────────────────── جلب الأرصدة ───────────────────────────

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def refresh_view(request):
    """
    «جلب الأرصدة» — يسأل كل مزوّد عن رصيده الآن.

    يُكمل على من فشل بدل أن يسقط كلّه: مزوّدٌ معطوب لا يجوز أن يمنعك من جرد
    البقيّة. ويعيد سطراً لكل مزوّد بما جرى معه.
    """
    tenant, err = _guard(request)
    if err or (err := _owner_only(request)):
        return err
    only = request.data.get("provider")
    qs = Provider.objects.filter(tenant=tenant)
    if only:
        qs = qs.filter(pk=only)

    results = []
    for p in qs.order_by("sort_order", "id"):
        adapter = adapter_for(p)
        if adapter is None:
            results.append({"id": p.id, "name": p.name, "ok": False,
                            "note": "منفّذ يدوي — لا رصيد آلياً"})
            continue
        try:
            res = adapter.get_balance(p.config or {}, provider=p)
        except Exception as e:  # مزوّد يرمي استثناءً لا يُسقط الجرد كلّه
            results.append({"id": p.id, "name": p.name, "ok": False,
                            "note": f"{type(e).__name__}: {e}"[:180]})
            continue
        if not res.ok:
            results.append({"id": p.id, "name": p.name, "ok": False,
                            "note": (res.note or "فشل الجلب")[:180]})
            continue
        fields = []
        if res.balance is not None:
            p.real_balance = res.balance
            fields.append("real_balance")
        if res.debt is not None:
            p.debt = res.debt
            fields.append("debt")
        if fields:
            p.save(update_fields=fields)
        results.append({"id": p.id, "name": p.name, "ok": True,
                        "balance": str(p.real_balance), "note": (res.note or "")[:180]})

    return Response({
        "results": results,
        "ok_count": sum(1 for r in results if r["ok"]),
        "fail_count": sum(1 for r in results if not r["ok"]),
        "live": services.build(tenant),
    })


# ─────────────────────────── الحفظ والسجلّ ───────────────────────────

def _orders_profit(tenant, since, agent=None):
    """
    ربح الطلبات في الفترة — شاهدٌ مستقلّ على فرق رأس المال.

    ليس بديلاً عن الجرد: الجرد يرى المال كلّه (نقداً وديوناً وأرصدة)، ودفتر
    الطلبات يرى المبيعات وحدها. لكن تباعدهما الكبير يستحقّ سؤالاً.
    """
    if agent is not None:
        # الوكيل الكبير: ربحه هو من طلبات دكاكينه — ألعاباً وخطوطاً
        from kontor.models import KontorOrder
        p, n = ZERO, 0
        for qs in (Order.objects.filter(agent=agent, status="success"),
                   KontorOrder.objects.filter(agent=agent, status="success")):
            if since:
                qs = qs.filter(created_at__gt=since)
            agg = qs.aggregate(p=Sum("agent_profit"), n=Count("id"))
            p, n = p + (agg["p"] or ZERO), n + (agg["n"] or 0)
        return p, n
    qs = Order.objects.filter(tenant=tenant, status="success")
    if since:
        qs = qs.filter(created_at__gt=since)
    agg = qs.aggregate(p=Sum("profit"), n=Count("id"))
    return (agg["p"] or ZERO), (agg["n"] or 0)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def snapshot_create_view(request):
    """حفظ جرد (يومي أو شهري) — لقطة كاملة لا تتغيّر بعدها."""
    tenant, err = _guard(request)
    if err:
        return err
    kind = request.data.get("kind", Snapshot.Kind.DAILY)
    if kind not in Snapshot.Kind.values:
        return Response({"detail": "نوع جرد غير معروف"}, status=400)

    agent = _agent(request)
    live = services.build(tenant, agent)   # بعملة الدفتر — واللقطة تُحفظ بها
    counted = [g for g in live["groups"] if g["enabled"]] + [live["manual"]]

    previous = Snapshot.objects.filter(
        tenant=tenant, owner=agent, kind=kind).order_by("-taken_at", "-id").first()
    prev_total = previous.total_base if previous else ZERO
    total = Decimal(live["totals"]["total"])

    orders_profit, orders_count = _orders_profit(tenant, previous.taken_at if previous else None, agent)

    period_profit, daily_count = ZERO, 0
    if kind == Snapshot.Kind.MONTHLY:
        dailies = Snapshot.objects.filter(tenant=tenant, owner=agent, kind=Snapshot.Kind.DAILY)
        if previous:
            dailies = dailies.filter(taken_at__gt=previous.taken_at)
        agg = dailies.aggregate(p=Sum("profit"), n=Count("id"))
        period_profit, daily_count = (agg["p"] or ZERO), (agg["n"] or 0)

    with transaction.atomic():
        snap = Snapshot.objects.create(
            tenant=tenant, owner=agent, kind=kind,
            base_currency=live["base_currency"], rates=live["rates"],
            total_base=total,
            assets_base=Decimal(live["totals"]["assets"]),
            liabilities_base=Decimal(live["totals"]["liabilities"]),
            previous=previous, previous_total=prev_total, profit=total - prev_total,
            period_from=previous.taken_at if previous else None,
            period_profit=period_profit, daily_count=daily_count,
            orders_profit=orders_profit, orders_count=orders_count,
            note=str(request.data.get("note") or "")[:300],
            created_by=request.user,
        )
        order = 0
        rows = []
        for g in counted:
            for l in g["lines"]:
                rows.append(SnapshotLine(
                    snapshot=snap, group=g["key"], group_label=g["label"],
                    name=l["name"][:160], amount=Decimal(l["amount"]),
                    currency=l["currency"],
                    base_amount=Decimal(l["base"]) if l["base"] is not None else ZERO,
                    source=l["source"], note=l["note"][:200], sort_order=order,
                ))
                order += 1
        SnapshotLine.objects.bulk_create(rows)

    return Response(_snapshot_row(snap, with_lines=True, agent=agent), status=201)


def _snapshot_row(s, with_lines=False, agent=None):
    # جرد الوكيل الكبير يُعرض بعملته — المحفوظ بعملة الدفتر
    _money = _money_base if agent is None else (
        lambda v: str(cur.to_display(agent, Decimal(v or 0))))
    row = {
        "id": s.id, "kind": s.kind, "kind_label": s.get_kind_display(),
        "taken_at": s.taken_at.strftime("%Y-%m-%d %H:%M"),
        "date": s.taken_at.strftime("%Y-%m-%d"),
        "base_currency": s.base_currency if agent is None else cur.display_currency(agent),
        "total": _money(s.total_base),
        "assets": _money(s.assets_base), "liabilities": _money(s.liabilities_base),
        "previous_total": _money(s.previous_total), "profit": _money(s.profit),
        "period_profit": _money(s.period_profit), "daily_count": s.daily_count,
        "orders_profit": _money(s.orders_profit), "orders_count": s.orders_count,
        "note": s.note,
        "by": s.created_by.name if s.created_by else "",
    }
    if with_lines:
        row["lines"] = [{
            "group": l.group, "group_label": l.group_label, "name": l.name,
            "amount": _money_base(l.amount), "currency": l.currency,
            "base": _money(l.base_amount), "source": l.source, "note": l.note,
        } for l in s.lines.all()]
        row["rates"] = s.rates if agent is None else {}
    return row


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def snapshots_view(request):
    """سجلّ الجرود — يومية وشهرية."""
    tenant, err = _guard(request)
    if err:
        return err
    agent = _agent(request)
    qs = Snapshot.objects.filter(tenant=tenant, owner=agent).select_related("created_by")
    kind = request.query_params.get("kind")
    if kind in Snapshot.Kind.values:
        qs = qs.filter(kind=kind)
    return Response({"count": qs.count(), "results": [_snapshot_row(s, agent=agent) for s in qs[:200]]})


@api_view(["GET", "DELETE"])
@permission_classes([IsAuthenticated])
def snapshot_view(request, snapshot_id):
    """تفاصيل جرد محفوظ أو حذفه."""
    tenant, err = _guard(request)
    if err:
        return err
    try:
        s = Snapshot.objects.select_related("created_by").get(
            pk=snapshot_id, tenant=tenant, owner=_agent(request))
    except Snapshot.DoesNotExist:
        return Response({"detail": "الجرد غير موجود"}, status=404)
    if request.method == "DELETE":
        s.delete()
        return Response({"deleted": True})
    return Response(_snapshot_row(s, with_lines=True, agent=_agent(request)))
