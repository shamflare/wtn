"""
طلبات الخطوط داخل «طلباتي» والتقارير — بنفس شكل طلبات الألعاب.

الوكيل يرى طلباته كلّها في قائمة واحدة، وصاحب المتجر يرى أرباحه كلّها في تقرير
واحد. فبدل أن تعرف كل شاشة نوعين من الطلبات، تُترجَم طلبات الخطوط هنا إلى لغة
طلبات الألعاب (الحالات · الحقول · المبالغ) وتُدمج.

خريطة الحالات للوكيل (كالألعاب: ما لم يُحسم «قيد الانتظار»):
  success ⇐ success · pending/processing ⇐ pending · failed/refunded ⇐ cancelled
"""
from decimal import Decimal

from django.db.models import Count, Q, Sum

from core import currency

from .models import KontorOrder, Operator

OP_LABEL = dict(Operator.choices) | {"Avea": "Türk Telekom", "Callback": "دولي"}

DEALER_STATUS = {
    KontorOrder.Status.SUCCESS: "success",
    KontorOrder.Status.PENDING: "pending",
    KontorOrder.Status.PROCESSING: "pending",
    KontorOrder.Status.FAILED: "cancelled",
    KontorOrder.Status.REFUNDED: "cancelled",
}
LABEL = {"success": "ناجح", "pending": "قيد الانتظار", "cancelled": "ملغى"}
# المال الذي لم يعد للوكيل (الملغى أُرجع إليه)
SPENT = [KontorOrder.Status.SUCCESS, KontorOrder.Status.PENDING, KontorOrder.Status.PROCESSING]


def statuses_for(dealer_status: str) -> list:
    """حالات الخطوط الفعلية خلف حالةٍ يختارها الوكيل أو المالك (success/pending/cancelled)."""
    if dealer_status == "processing":       # المالك قد يطلب «قيد التنفيذ» صراحةً
        dealer_status = "pending"
    if dealer_status == "stuck":             # لا «عالق» في الخطوط — الانقطاع يُتابَع آلياً
        return []
    return [s for s, d in DEALER_STATUS.items() if d == dealer_status]


def receipt_of(o: KontorOrder) -> str:
    """رقم الفيش للخط — M قبله كي لا يلتبس بفيش الألعاب."""
    return f"M{o.id}"


def dealer_orders(user, params) -> "QuerySet":
    """طلبات خطوط الوكيل بنفس فلاتر «طلباتي» (التاريخ · البحث) — قبل فلتر الحالة."""
    qs = KontorOrder.objects.filter(tenant=user.tenant, dealer=user)
    if params.get("date_from"):
        qs = qs.filter(created_at__date__gte=params["date_from"])
    if params.get("date_to"):
        qs = qs.filter(created_at__date__lte=params["date_to"])
    q = (params.get("q") or "").strip()
    if q:
        digits = q.upper().lstrip("M")
        cond = Q(gsm__icontains=q) | Q(package_name__icontains=q)
        if digits.isdigit():
            cond |= Q(id=int(digits))
        qs = qs.filter(cond)
    return qs


def dealer_row(o: KontorOrder, user) -> dict:
    """طلب خطّ بشكل صفّ «طلباتي» (StoreOrderSerializer) — مع kind=mobile."""
    show = lambda v: str(currency.to_display(user, v))  # noqa: E731
    st = DEALER_STATUS.get(o.status, "pending")
    return {
        "kind": "mobile", "id": f"m{o.id}", "receipt_no": receipt_of(o),
        "operator": o.operator, "game_name": OP_LABEL.get(o.operator, o.operator),
        "product": o.package_id, "product_name": o.package_name, "quantity": 1,
        "player_id": o.gsm, "customer_phone": "",
        "paid_price": show(o.sell_price), "dealer_sell_price": show(o.dealer_sell_price),
        "dealer_profit": show(o.dealer_profit),
        "status": st, "status_label": LABEL[st], "pin_result": "",
        "provider_note": o.provider_note, "dealer_note": "", "last_sync_at": None,
        "balance_before": show(o.balance_before), "balance_after": show(o.balance_after),
        "created_at": o.created_at.strftime("%Y-%m-%d %H:%M"),
    }


def dealer_counts(qs) -> dict:
    """عدّادات شرائح الحالة بلغة الوكيل."""
    out: dict = {}
    for row in qs.order_by().values("status").annotate(n=Count("id")):
        key = DEALER_STATUS.get(row["status"], row["status"])
        out[key] = out.get(key, 0) + row["n"]
    return out


def admin_orders(request) -> "QuerySet | None":
    """
    طلبات الخطوط بفلاتر تقارير المالك (وكيل · تاريخ · حالة؛ الناجحة افتراضاً).
    فلتر لعبة أو منتج أو `section=games` ⇐ None: التقرير يخصّ الألعاب وحدها.
    """
    p = request.query_params
    if p.get("game") or p.get("product") or p.get("section") == "games":
        return None
    qs = KontorOrder.objects.filter(tenant=request.user.tenant)
    if p.get("dealer"):
        qs = qs.filter(dealer_id=p["dealer"])
    if p.get("date_from"):
        qs = qs.filter(created_at__date__gte=p["date_from"])
    if p.get("date_to"):
        qs = qs.filter(created_at__date__lte=p["date_to"])
    status = p.get("status", "success")
    if status and status != "all":
        qs = qs.filter(status__in=statuses_for(status))
    return qs


def add(totals: dict, extra: dict) -> dict:
    """جمع مجاميع (أرقام نصّية أو Decimal) — count عددٌ صحيح والبقية مبالغ."""
    out = {}
    for k in set(totals) | set(extra):
        a, b = totals.get(k) or 0, extra.get(k) or 0
        out[k] = int(a) + int(b) if k == "count" else Decimal(str(a)) + Decimal(str(b))
    return out


def sums(qs, **fields) -> dict:
    """aggregate مختصر: sums(qs, cost="cost_price") ⇐ {"count": n, "cost": Decimal}."""
    agg = qs.aggregate(count=Count("id"), **{k: Sum(v) for k, v in fields.items()})
    return {k: (v or 0) for k, v in agg.items()}
