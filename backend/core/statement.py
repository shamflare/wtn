"""
كشف حساب محفظة — مصدرٌ واحد لكل نوافذ الكشف: كشف الوكيل عند صاحب المتجر، وكشف
الدكان عند وكيله الكبير. الفلاتر والمجاميع والصفحات هنا، والعرض بعملة من يقرأ.

المجاميع (الوارد · الصادر · العدد) على **كل** ما طابق الفلتر لا على الصفحة وحدها،
وإلا تغيّرت الأرقام فوق الجدول كلّما قلب القارئ صفحة.
"""
from decimal import Decimal

from django.db.models import Count, Q, Sum

PAGE_SIZE = 20


def paginate(qs, params, size=PAGE_SIZE):
    """(صفوف الصفحة، بيانات التنقّل). `page` من 1، و`page_size` حتى 100."""
    try:
        size = max(1, min(100, int(params.get("page_size") or size)))
    except (TypeError, ValueError):
        size = PAGE_SIZE
    count = qs.count()
    pages = max(1, -(-count // size))
    try:
        page = max(1, min(pages, int(params.get("page") or 1)))
    except (TypeError, ValueError):
        page = 1
    rows = list(qs[(page - 1) * size: page * size])
    return rows, {"page": page, "pages": pages, "count": count, "page_size": size}


def filtered(qs, params, *, scoped: bool = False):
    """
    فلاتر الكشف: التاريخ · النوع · الاتجاه (in/out). و`scoped` لمحفظة وكيلٍ كبير:
    `scope=store` (الافتراضي) حركاته مع المتجر وحدها، `agent` حركاته مع دكاكينه،
    `all` الكل.
    """
    p = params
    if p.get("date_from"):
        qs = qs.filter(created_at__date__gte=p["date_from"])
    if p.get("date_to"):
        qs = qs.filter(created_at__date__lte=p["date_to"])
    if p.get("type") and p["type"] != "all":
        qs = qs.filter(type=p["type"])
    if p.get("dir") == "in":
        qs = qs.filter(amount__gt=0)
    elif p.get("dir") == "out":
        qs = qs.filter(amount__lt=0)
    if scoped:
        scope = p.get("scope") or "store"
        if scope == "store":
            qs = qs.filter(internal=False)
        elif scope == "agent":
            qs = qs.filter(internal=True)
    return qs


def build(wallet, params, show, *, scoped=False) -> dict:
    """الكشف كاملاً: المجاميع + الصفحة المطلوبة. `show` يحوّل مبلغ الدفتر لعملة القارئ."""
    qs = filtered(wallet.transactions.all(), params, scoped=scoped)
    agg = qs.aggregate(
        n=Count("id"),
        inc=Sum("amount", filter=Q(amount__gt=0)),
        out=Sum("amount", filter=Q(amount__lt=0)),
    )
    rows, meta = paginate(qs, params)
    return {
        "totals": {"count": agg["n"] or 0, "in": str(show(agg["inc"] or Decimal("0"))),
                   "out": str(show(agg["out"] or Decimal("0")))},
        "paging": meta,
        "results": [{
            "id": t.id, "type": t.type, "type_label": t.get_type_display(),
            "amount": str(show(t.amount)),
            "balance_before": str(show(t.balance_before)),
            "balance_after": str(show(t.balance_after)),
            "note": t.note, "internal": t.internal,
            "created_at": t.created_at.strftime("%Y-%m-%d %H:%M"),
        } for t in rows],
    }
