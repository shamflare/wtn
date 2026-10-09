"""
تقارير المال لصاحب المتجر — أربعة أسئلة لا تجيبها التقارير الأخرى:

1. الوكلاء الكبار: كم ربحتُ من شبكة كل وكيل كبير، وكم ربح هو، وكم يدين المتجر لشبكته.
2. الحركات اليدوية: كل مالٍ أُضيف أو خُصم **باليد** — أسرع طريقٍ لكشف مالٍ لا طلب وراءه.
3. الإيداعات: ما دخل من كل حساب وطريقة دفع، وعمولته.
4. عمر الديون: من رصيده سالب، ومنذ متى، ومتى دفع آخر مرّة.

كلّها بعملة الدفتر، ولصاحب المتجر وحده (الوكلاء لا يطرقون `finance/` — core/access.py).
وما بين الوكيل الكبير ودكاكينه دفترُه هو: لا يدخل هنا إلا مجموعاً في تقرير شبكته.
"""
from decimal import Decimal

from django.db.models import Count, Max, Q, Sum
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from . import currency
from .models import User, Wallet, WalletTransaction
from .statement import paginate

ZERO = Decimal("0")


def _m(v) -> str:
    return str(Decimal(v or 0).quantize(currency.CENT))


def _owner(request):
    if request.user.role != User.Role.TENANT_ADMIN or request.user.tenant is None:
        return None, Response({"detail": "تقارير المال لصاحب المتجر وحده"}, status=403)
    return request.user.tenant, None


def _dated(qs, p, field="created_at"):
    if p.get("date_from"):
        qs = qs.filter(**{f"{field}__date__gte": p["date_from"]})
    if p.get("date_to"):
        qs = qs.filter(**{f"{field}__date__lte": p["date_to"]})
    return qs


# ─────────────────────────── 1. الوكلاء الكبار ───────────────────────────

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def agents_view(request):
    """
    لكل وكيل كبير في الفترة (الطلبات الناجحة، ألعاباً وخطوطاً):
    مبيعات المتجر له · تكلفتها · ربح المتجر · ربح الوكيل · ما دفعته دكاكينه.
    ومعها الآن: رصيده ومجموع أرصدة دكاكينه — وهما معاً ما يدين به المتجر لشبكته.
    """
    from kontor.models import KontorOrder
    from orders.models import Order

    tenant, err = _owner(request)
    if err:
        return err
    p = request.query_params
    rows, totals = [], {k: ZERO for k in ("sell", "cost", "profit", "agent_profit", "buyer", "exposure")}
    totals["count"] = 0
    for a in User.objects.filter(tenant=tenant, role=User.Role.ANA_BAYI).order_by("name"):
        agg = {k: ZERO for k in ("count", "sell", "cost", "profit", "agent_profit", "buyer")}
        for qs in (Order.objects.filter(agent=a, status=Order.Status.SUCCESS),
                   KontorOrder.objects.filter(agent=a, status=KontorOrder.Status.SUCCESS)):
            r = _dated(qs, p).aggregate(count=Count("id"), sell=Sum("sell_price"), cost=Sum("cost_price"),
                                        profit=Sum("profit"), agent_profit=Sum("agent_profit"),
                                        buyer=Sum("buyer_price"))
            for k in agg:
                agg[k] += r[k] or ZERO
        own = Wallet.objects.filter(user=a).values_list("balance", flat=True).first() or ZERO
        shops = Wallet.objects.filter(user__parent=a, user__role=User.Role.BAYI).aggregate(
            s=Sum("balance"), n=Count("id"))
        exposure = own + (shops["s"] or ZERO)
        rows.append({
            "id": a.id, "name": a.name, "login_id": a.login_id, "shops": shops["n"] or 0,
            "count": int(agg["count"]), "sell": _m(agg["sell"]), "cost": _m(agg["cost"]),
            "profit": _m(agg["profit"]), "agent_profit": _m(agg["agent_profit"]), "buyer": _m(agg["buyer"]),
            "balance": _m(own), "shops_balance": _m(shops["s"]), "exposure": _m(exposure),
        })
        totals["count"] += int(agg["count"])
        for k in ("sell", "cost", "profit", "agent_profit", "buyer"):
            totals[k] += agg[k]
        totals["exposure"] += exposure
    return Response({
        "results": rows,
        "totals": {k: (v if k == "count" else _m(v)) for k, v in totals.items()},
        "currency": currency.base_currency(tenant),
    })


# ─────────────────────────── 2. الحركات اليدوية ───────────────────────────

MANUAL_TYPES = [WalletTransaction.Type.MANUAL_CREDIT, WalletTransaction.Type.MANUAL_DEBIT,
                WalletTransaction.Type.ADJUSTMENT]


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def manual_view(request):
    """
    كل إضافة وخصم وتسوية باليد في الفترة — مَن، لمن، كم، ولماذا. فلاتر: التاريخ ·
    `type` · `dealer` · `by` (من نفّذها). والمجاميع لكل نوع على كل ما طابق، لا الصفحة.
    حوالات الوكيل الكبير لدكاكينه خارجها (دفتره هو)؛ وإبطال الإيداع «تسوية» فيدخلها.
    """
    tenant, err = _owner(request)
    if err:
        return err
    p = request.query_params
    qs = (WalletTransaction.objects.filter(tenant=tenant, type__in=MANUAL_TYPES, internal=False)
          .select_related("wallet__user", "created_by"))
    qs = _dated(qs, p)
    if p.get("type") in MANUAL_TYPES:
        qs = qs.filter(type=p["type"])
    if p.get("dealer"):
        qs = qs.filter(wallet__user_id=p["dealer"])
    if p.get("by"):
        qs = qs.filter(created_by_id=p["by"])

    by_type = {r["type"]: r for r in qs.values("type").annotate(n=Count("id"), s=Sum("amount"))}
    labels = dict(WalletTransaction.Type.choices)
    summary = [{"type": t, "label": labels[t], "count": (by_type.get(t) or {}).get("n", 0),
                "amount": _m((by_type.get(t) or {}).get("s"))} for t in MANUAL_TYPES]
    agg = qs.aggregate(inc=Sum("amount", filter=Q(amount__gt=0)), out=Sum("amount", filter=Q(amount__lt=0)))
    page, paging = paginate(qs.order_by("-created_at"), p)
    actors = (User.objects.filter(tenant=tenant, id__in=qs.values("created_by_id"))
              .values("id", "name").order_by("name"))
    return Response({
        "summary": summary,
        "totals": {"in": _m(agg["inc"]), "out": _m(agg["out"]), "net": _m((agg["inc"] or 0) + (agg["out"] or 0))},
        "actors": list(actors),
        "paging": paging,
        "results": [{
            "id": t.id, "created_at": t.created_at.strftime("%Y-%m-%d %H:%M"),
            "dealer": t.wallet.user.name, "dealer_id": t.wallet.user_id,
            "is_big": t.wallet.user.role == User.Role.ANA_BAYI,
            "type": t.type, "type_label": t.get_type_display(),
            "amount": _m(t.amount), "balance_after": _m(t.balance_after),
            "by": t.created_by.name if t.created_by else "—", "note": t.note,
        } for t in page],
        "currency": currency.base_currency(tenant),
    })


# ─────────────────────────── 3. الإيداعات ───────────────────────────

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def deposits_view(request):
    """
    الإيداعات المقبولة في الفترة (بتاريخ القرار) مجمّعةً بالحساب والطريقة والعملة:
    العدد · المبلغ المُرسل بعملته · ما أُضيف للمحافظ · العمولة (بعملة الدفتر).
    ومعها عدد المعلّق والمرفوض في الفترة نفسها (بتاريخ الإنشاء). إيداعات دكاكين
    الوكلاء الكبار عندهم لا هنا.
    """
    from payments.models import PaymentNotification as PN

    tenant, err = _owner(request)
    if err:
        return err
    p = request.query_params
    base = PN.objects.filter(tenant=tenant, owner__isnull=True)
    ok = _dated(base.filter(status=PN.Status.APPROVED), p, "decided_at").select_related("account", "method")

    groups: dict = {}
    for n in ok:
        key = (n.account_id, n.method_id, n.currency)
        g = groups.setdefault(key, {
            "account": n.account.title if n.account else "— بلا حساب —",
            "method": n.method.name if n.method else "— طريقة محذوفة —",
            "currency": n.currency, "count": 0, "amount": ZERO, "credit": ZERO, "commission": ZERO,
        })
        gross = (n.amount / n.rate) if n.rate else ZERO       # ما يساويه المُرسل بعملة الدفتر
        g["count"] += 1
        g["amount"] += n.amount
        g["credit"] += n.credit_amount or ZERO
        g["commission"] += max(gross - (n.credit_amount or ZERO), ZERO)
    rows = sorted(groups.values(), key=lambda g: -g["credit"])
    created = _dated(base, p)
    return Response({
        "results": [{**g, "amount": _m(g["amount"]), "credit": _m(g["credit"]),
                     "commission": _m(g["commission"])} for g in rows],
        "totals": {
            "count": sum(g["count"] for g in rows),
            "credit": _m(sum((g["credit"] for g in rows), ZERO)),
            "commission": _m(sum((g["commission"] for g in rows), ZERO)),
            "pending": created.filter(status=PN.Status.PENDING).count(),
            "rejected": created.filter(status=PN.Status.REJECTED).count(),
        },
        "currency": currency.base_currency(tenant),
    })


# ─────────────────────────── 4. عمر الديون ───────────────────────────

BUCKETS = [(7, "حتى أسبوع"), (30, "حتى شهر"), (90, "حتى 3 أشهر"), (None, "أكثر من 3 أشهر")]


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def debts_view(request):
    """
    كل محفظة سالبة الآن (وكلاء المتجر ووكلاؤه الكبار — دكاكين الكبير دَينها عليه):
    منذ متى هي سالبة (آخر حركةٍ عبرت بها من الصفر إلى السالب)، وآخر دفعةٍ له
    (آخر حركةٍ موجبة ليست استرجاعاً)، ومقدار ما استُخدم من حدّه الائتماني.
    """
    tenant, err = _owner(request)
    if err:
        return err
    now = timezone.now()
    wallets = (Wallet.objects.filter(tenant=tenant, balance__lt=0,
                                     user__role__in=[User.Role.BAYI, User.Role.ANA_BAYI])
               .exclude(user__parent__role=User.Role.ANA_BAYI)
               .select_related("user").order_by("balance"))
    rows, buckets = [], {label: {"count": 0, "amount": ZERO} for _, label in BUCKETS}
    for w in wallets:
        txns = w.transactions.filter(internal=False)
        crossed = (txns.filter(balance_before__gte=0, balance_after__lt=0)
                   .aggregate(t=Max("created_at"))["t"])
        since = crossed or txns.aggregate(t=Max("created_at"))["t"] or w.user.created_at
        last_pay = (txns.filter(amount__gt=0).exclude(type=WalletTransaction.Type.REFUND)
                    .aggregate(t=Max("created_at"))["t"])
        days = max(0, (now - since).days)
        label = next(l for limit, l in BUCKETS if limit is None or days <= limit)
        buckets[label]["count"] += 1
        buckets[label]["amount"] += w.balance
        used = (w.balance / w.credit_limit * 100) if w.credit_limit < 0 else None
        rows.append({
            "id": w.user_id, "name": w.user.name, "login_id": w.user.login_id,
            "is_big": w.user.role == User.Role.ANA_BAYI, "status": w.user.status,
            "whatsapp": f"+{w.user.whatsapp}" if w.user.whatsapp else "",
            "balance": _m(w.balance), "credit_limit": _m(w.credit_limit),
            "balance_own": _m(currency.to_display(w.user, w.balance)),
            "own_currency": currency.display_currency(w.user),
            "limit_used": f"{used:.0f}" if used is not None else "",
            "since": since.strftime("%Y-%m-%d"), "days": days, "bucket": label,
            "last_payment": last_pay.strftime("%Y-%m-%d") if last_pay else "",
            "last_payment_days": (now - last_pay).days if last_pay else None,
        })
    rows.sort(key=lambda r: -r["days"])
    return Response({
        "results": rows,
        "buckets": [{"label": l, "count": buckets[l]["count"], "amount": _m(buckets[l]["amount"])}
                    for _, l in BUCKETS],
        "total": _m(sum((w.balance for w in wallets), ZERO)),
        "currency": currency.base_currency(tenant),
    })
