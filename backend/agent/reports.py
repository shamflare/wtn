"""
طلبات الوكيل الكبير وتقاريره وجرده — بمنظوره هو.

منظوره: **تكلفته** ما دفعه للمتجر (`sell_price`)، و**مبيعاته** ما دفعه دكانه له
(`buyer_price`)، و**ربحه** فرقهما (`agent_profit`). الألعاب والخطوط في قائمة واحدة
وتقرير واحد، كما يراها صاحب المتجر.

كل رقم يخرج بعملة عرض الوكيل، وكل فترة تبدأ «اليوم» في الواجهة.
"""
from decimal import Decimal

from django.db.models import Count, Q, Sum
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from core import currency
from core.models import User, Wallet
from kontor import reporting as kr
from kontor.models import KontorOrder
from orders.models import Order
from orders.serializers import DEALER_STATUS, dealer_filter
from payments.models import PaymentNotification, ReceivingAccount

from .views import AGENT

ZERO = Decimal("0")


def _dated(qs, p):
    if p.get("date_from"):
        qs = qs.filter(created_at__date__gte=p["date_from"])
    if p.get("date_to"):
        qs = qs.filter(created_at__date__lte=p["date_to"])
    return qs


def _scoped(agent, p):
    """(طلبات الألعاب، طلبات الخطوط) لدكاكينه بعد فلاتر التاريخ والدكان والبحث — قبل الحالة."""
    games = Order.objects.filter(agent=agent).select_related("dealer", "game", "product")
    mobile = KontorOrder.objects.filter(agent=agent).select_related("dealer")
    games, mobile = _dated(games, p), _dated(mobile, p)
    if p.get("dealer"):
        games, mobile = games.filter(dealer_id=p["dealer"]), mobile.filter(dealer_id=p["dealer"])
    q = (p.get("q") or "").strip()
    if q:
        games = games.filter(Q(receipt_no__icontains=q) | Q(player_id__icontains=q)
                             | Q(product__name__icontains=q) | Q(game__name__icontains=q))
        digits = q.upper().lstrip("M")
        cond = Q(gsm__icontains=q) | Q(package_name__icontains=q)
        if digits.isdigit():
            cond |= Q(id=int(digits))
        mobile = mobile.filter(cond)
    kind = p.get("kind")
    if kind == "games":
        mobile = mobile.none()
    elif kind == "mobile":
        games = games.none()
    return games, mobile


@api_view(["GET"])
@permission_classes(AGENT)
def orders_view(request):
    """
    طلبات دكاكينه — الألعاب والخطوط معاً. فلاتر: date_from/date_to · status
    (success|pending|cancelled) · kind (games|mobile) · dealer · q.
    """
    agent, p = request.user, request.query_params
    games, mobile = _scoped(agent, p)

    counts = {"all": 0}
    for row in games.order_by().values("status").annotate(n=Count("id")):
        key = DEALER_STATUS.get(row["status"], row["status"])
        counts[key] = counts.get(key, 0) + row["n"]
    for key, n in kr.dealer_counts(mobile).items():
        counts[key] = counts.get(key, 0) + n
    counts["all"] = sum(v for k, v in counts.items() if k != "all")

    st = p.get("status")
    if st and st != "all":
        games = games.filter(status__in=dealer_filter(st))
        mobile = mobile.filter(status__in=kr.statuses_for(st))

    ok_g = games.filter(status=Order.Status.SUCCESS).aggregate(
        s=Sum("buyer_price"), c=Sum("sell_price"), p=Sum("agent_profit"))
    ok_m = mobile.filter(status=KontorOrder.Status.SUCCESS).aggregate(
        s=Sum("buyer_price"), c=Sum("sell_price"), p=Sum("agent_profit"))
    show = lambda v: str(currency.to_display(agent, v or 0))  # noqa: E731

    rows = []
    for o in games[:300]:
        st_ = DEALER_STATUS.get(o.status, o.status)
        rows.append((o.created_at, {
            "kind": "game", "id": o.id, "receipt_no": o.receipt_no,
            "dealer_name": o.dealer.name, "game_name": o.game.name, "product_name": o.product.name,
            "quantity": o.quantity, "player_id": o.player_id,
            "sell_price": show(o.buyer_price), "cost": show(o.sell_price), "profit": show(o.agent_profit),
            "status": st_, "status_label": dict(Order.Status.choices)[st_],
            "pin_result": o.pin_result, "provider_note": o.provider_note, "dealer_note": o.dealer_note,
            "created_at": o.created_at.strftime("%Y-%m-%d %H:%M"),
        }))
    for o in mobile.order_by("-created_at")[:300]:
        st_ = kr.DEALER_STATUS.get(o.status, "pending")
        rows.append((o.created_at, {
            "kind": "mobile", "id": f"m{o.id}", "receipt_no": kr.receipt_of(o),
            "dealer_name": o.dealer.name, "game_name": kr.OP_LABEL.get(o.operator, o.operator),
            "product_name": o.package_name, "quantity": 1, "player_id": o.gsm,
            "sell_price": show(o.buyer_price), "cost": show(o.sell_price), "profit": show(o.agent_profit),
            "status": st_, "status_label": kr.LABEL[st_],
            "pin_result": "", "provider_note": o.provider_note, "dealer_note": "",
            "created_at": o.created_at.strftime("%Y-%m-%d %H:%M"),
        }))
    rows.sort(key=lambda t: t[0], reverse=True)
    return Response({
        "count": games.count() + mobile.count(),
        "counts": counts,
        "totals": {
            "sales": show((ok_g["s"] or ZERO) + (ok_m["s"] or ZERO)),
            "cost": show((ok_g["c"] or ZERO) + (ok_m["c"] or ZERO)),
            "profit": show((ok_g["p"] or ZERO) + (ok_m["p"] or ZERO)),
        },
        "results": [r for _, r in rows[:300]],
        "currency": currency.display_currency(agent),
    })


def _success(agent, p):
    games, mobile = _scoped(agent, p)
    return games.filter(status=Order.Status.SUCCESS), mobile.filter(status=KontorOrder.Status.SUCCESS)


SUMS = dict(count=Count("id"), cost=Sum("sell_price"), sell=Sum("buyer_price"), profit=Sum("agent_profit"))


def _money_row(agent, r):
    show = lambda v: str(currency.to_display(agent, v or 0))  # noqa: E731
    return {"count": r["count"], "cost": show(r["cost"]), "sell": show(r["sell"]), "profit": show(r["profit"])}


def _totals(agent, rows):
    t = {"count": 0, "cost": ZERO, "sell": ZERO, "profit": ZERO}
    for r in rows:
        t["count"] += r["count"]
        for k in ("cost", "sell", "profit"):
            t[k] += r[k] or ZERO
    return _money_row(agent, t)


@api_view(["GET"])
@permission_classes(AGENT)
def report_summary_view(request):
    """تقرير الطلبات الناجحة مجمّعاً باللعبة (والخطوط سطرٌ لكل شركة) — كتقرير صاحب المتجر."""
    agent = request.user
    games, mobile = _success(agent, request.query_params)
    raw = []
    for r in games.values("game__name").annotate(**SUMS):
        raw.append({**r, "game": r["game__name"], "kind": "game"})
    for r in mobile.values("operator").annotate(**SUMS):
        raw.append({**r, "game": f"موبايل · {kr.OP_LABEL.get(r['operator'], r['operator'])}",
                    "kind": "mobile"})
    raw.sort(key=lambda r: -r["count"])
    return Response({
        "results": [{"game": r["game"], "kind": r["kind"], **_money_row(agent, r)} for r in raw],
        "totals": _totals(agent, raw),
        "currency": currency.display_currency(agent),
    })


@api_view(["GET"])
@permission_classes(AGENT)
def report_dealers_view(request):
    """أرباحه من كل دكان في الفترة (الناجحة فقط)."""
    agent = request.user
    games, mobile = _success(agent, request.query_params)
    per: dict = {}
    for qs in (games, mobile):
        for r in qs.values("dealer_id", "dealer__name").annotate(**SUMS):
            cur = per.setdefault(r["dealer_id"], {"dealer": r["dealer__name"], "count": 0,
                                                  "cost": ZERO, "sell": ZERO, "profit": ZERO})
            cur["count"] += r["count"]
            for k in ("cost", "sell", "profit"):
                cur[k] += r[k] or ZERO
    raw = sorted(per.values(), key=lambda r: -r["profit"])
    return Response({
        "results": [{"dealer": r["dealer"], **_money_row(agent, r)} for r in raw],
        "totals": _totals(agent, raw),
        "currency": currency.display_currency(agent),
    })


@api_view(["GET"])
@permission_classes(AGENT)
def alerts_view(request):
    """عدّادات هيدر الوكيل الكبير: ما ينتظر قراره هو."""
    agent = request.user
    from core.tickets import visible_tickets
    from core.models import TicketMessage
    return Response({
        "deposits_pending": PaymentNotification.objects.filter(
            owner=agent, status=PaymentNotification.Status.PENDING).count(),
        "orders_pending": Order.objects.filter(
            agent=agent, status__in=[Order.Status.PENDING, Order.Status.PROCESSING,
                                     Order.Status.STUCK]).count()
        + KontorOrder.objects.filter(
            agent=agent, status__in=[KontorOrder.Status.PENDING, KontorOrder.Status.PROCESSING]).count(),
        "dealers_negative": Wallet.objects.filter(
            user__parent=agent, user__role=User.Role.BAYI, balance__lt=0).count(),
        "tickets": TicketMessage.objects.filter(ticket__in=visible_tickets(agent))
        .exclude(sender=agent).filter(read_by_other=False).count(),
    })
