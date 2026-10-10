"""
بناء لقطة الجرد — نفس الدالّة تخدم العرض الحيّ والحفظ.

مصدرٌ واحد للحقيقة: لو حسبت الشاشةُ شيئاً وحسب الحفظُ شيئاً آخر لصار الجرد
المحفوظ لا يطابق ما رآه المالك حين ضغط «حفظ».
"""
from decimal import Decimal

from django.db.models import Count, Q, Sum

from core import currency as cur
from core.models import Invoice, User, Wallet
from payments.models import ReceivingAccount
from providers.models import Provider

from .models import InventoryConfig, ManualItem, Snapshot

ZERO = Decimal("0")
CENT = Decimal("0.01")

# المصادر التلقائية — يقرؤها النظام من قاعدته، بلا روبوت ولا API خارجي
SOURCES = [
    ("providers", "أرصدتنا لدى المزوّدين"),
    ("receiving", "حساباتنا والنقد"),
    ("dealer_wallets", "محافظ الوكلاء"),
    ("subscription", "اشتراك المنصّة غير المدفوع"),
]


def config_for(tenant) -> InventoryConfig:
    obj, _ = InventoryConfig.objects.get_or_create(tenant=tenant)
    return obj


def _to_base(tenant, amount, currency):
    """المبلغ بعملة الدفتر، أو None إن لم يكن للعملة سعر صرف مضبوط."""
    amount = Decimal(amount or 0)
    if currency == cur.base_currency(tenant):
        return amount.quantize(CENT)
    rate = cur.rate_of(tenant, currency)
    return (amount / rate).quantize(CENT) if rate > 0 else None


def _line(tenant, name, amount, currency, *, note="", source="auto", item_id=None):
    base = _to_base(tenant, amount, currency)
    return {
        "id": item_id,
        "name": name,
        "amount": str(Decimal(amount or 0).quantize(CENT)),
        "currency": currency,
        "base": str(base) if base is not None else None,
        "note": note,
        "source": source,
    }


def _group(key, label, lines, *, hint="", enabled=True, auto=True):
    total = sum((Decimal(l["base"]) for l in lines if l["base"] is not None), ZERO)
    return {
        "key": key, "label": label, "hint": hint, "auto": auto, "enabled": enabled,
        "lines": lines,
        "total_base": str(total),
        "unresolved": sum(1 for l in lines if l["base"] is None),
    }


def build(tenant, agent=None) -> dict:
    """
    اللقطة الحالية كاملةً: المجموعات التلقائية + البنود اليدوية + المجاميع.

    كل مبلغ **موقّع**: الموجب لنا والسالب علينا. فالمجموع الكلي = صافي رأس
    المال مباشرةً، بلا طرحٍ لاحق يمكن أن يُنسى.
    """
    if agent is not None:
        return _build_agent(tenant, agent)
    conf = config_for(tenant)
    base = cur.base_currency(tenant)
    groups = []

    # ── المزوّدون ──
    # الرقم المعتمد هو `real_balance` (ما ردّه المزوّد فعلاً)، وقد يكون سالباً
    # فيعني أننا مدينون له. و`balance`/`debt` اليدويان يُعرضان ملاحظةً ولا
    # يُجمعان: النموذج لا يوثّق عملتهما، وجمع رقمٍ بعملة مجهولة يفسد الجرد كلّه.
    # وكل مزوّد يُحسب **بعملته هو** (`Provider.currency`) لا بليرةٍ مفترضة.
    prov_lines = []
    providers = list(Provider.objects.filter(tenant=tenant).order_by("sort_order", "id"))
    for p in providers:
        bits = []
        if p.balance:
            bits.append(f"رصيد يدوي {p.balance}")
        if p.debt:
            bits.append(f"دَين {p.debt}")
        prov_lines.append(_line(
            # كلٌّ بعملته هو — لا بليرةٍ مفترضةٍ للجميع
            tenant, p.name, p.real_balance, cur.currency_of(p),
            note=" · ".join(bits), item_id=p.id,
        ))
    groups.append(_group(
        "providers", "أرصدتنا لدى المزوّدين", prov_lines,
        hint="ما ردّه كل مزوّد آخر مرّة. السالب يعني أننا مدينون له.",
        enabled=conf.enabled("providers"),
    ))

    # ── حسابات الاستلام والنقد ──
    recv_lines = [
        _line(tenant, f"{a.title} · {a.get_method_display()}", a.balance, base, item_id=a.id)
        for a in ReceivingAccount.objects.filter(
            tenant=tenant, owner__isnull=True, status=ReceivingAccount.Status.ACTIVE
        ).order_by("sort_order", "id")
    ]
    groups.append(_group(
        "receiving", "حساباتنا والنقد", recv_lines,
        hint="حسابات الاستلام المفعّلة من «الوكلاء ← حساباتي».",
        enabled=conf.enabled("receiving"),
    ))

    # ── محافظ الوكلاء — بالإشارة المعكوسة ──
    # كل محافظ الوكلاء — **ومعها دكاكين الوكلاء الكبار**: ما أعطاه الكبير لدكانه خرج
    # من محفظته إلى محفظة الدكان، وما زال مالاً يُصرف عند المتجر. فما يدين به المتجر
    # لشبكة الكبير = محفظته + محافظ دكاكينه، أعطاهم أم لم يعطهم.
    agg = Wallet.objects.filter(
        tenant=tenant, user__role__in=[User.Role.BAYI, User.Role.ANA_BAYI]).aggregate(
        net=Sum("balance"),
        credit=Sum("balance", filter=Q(balance__gt=0)),
        credit_n=Count("id", filter=Q(balance__gt=0)),
        debt=Sum("balance", filter=Q(balance__lt=0)),
        debt_n=Count("id", filter=Q(balance__lt=0)),
    )
    wallet_lines = [_line(
        tenant, "صافي محافظ الوكلاء", -(agg["net"] or ZERO), base,
        note=(f"{agg['credit_n'] or 0} برصيد موجب = {agg['credit'] or 0} علينا · "
              f"{agg['debt_n'] or 0} برصيد سالب = {-(agg['debt'] or ZERO)} لنا"),
    )]
    groups.append(_group(
        "dealer_wallets", "محافظ الوكلاء", wallet_lines,
        hint="رصيد الوكيل الموجب مالٌ قبضناه ولم نقدّم مقابله — يُطرح لا يُجمع.",
        enabled=conf.enabled("dealer_wallets"),
    ))

    # ── اشتراك المنصّة ──
    unpaid = Invoice.objects.filter(tenant=tenant, status=Invoice.Status.UNPAID)
    unpaid_total = unpaid.aggregate(s=Sum("amount"))["s"] or ZERO
    sub_lines = [_line(
        tenant, f"{unpaid.count()} فاتورة غير مدفوعة", -unpaid_total, base,
    )] if unpaid_total else []
    groups.append(_group(
        "subscription", "اشتراك المنصّة غير المدفوع", sub_lines,
        hint="دفترٌ بينك وبين مالك المنصّة.",
        enabled=conf.enabled("subscription"),
    ))

    # ── البنود اليدوية ──
    manual_lines = [
        _line(tenant, m.name, m.amount, m.currency, note=m.note,
              source="manual", item_id=m.id)
        for m in ManualItem.objects.filter(tenant=tenant, owner__isnull=True, active=True)
    ]
    manual = _group(
        "manual", "البنود اليدوية", manual_lines,
        hint="ما لا يعرفه النظام: نقدٌ في الصندوق، دَينٌ شخصي، حوالة عند أحدهم.",
        auto=False,
    )

    # ── المجاميع ──
    counted = [g for g in groups if g["enabled"]] + [manual]
    all_lines = [l for g in counted for l in g["lines"]]

    total = sum((Decimal(l["base"]) for l in all_lines if l["base"] is not None), ZERO)
    assets = sum((Decimal(l["base"]) for l in all_lines
                  if l["base"] is not None and Decimal(l["base"]) > 0), ZERO)
    liabilities = -sum((Decimal(l["base"]) for l in all_lines
                        if l["base"] is not None and Decimal(l["base"]) < 0), ZERO)

    # مجاميع كل عملة على حدة — كما في لوحة الجرد التي يعرفها المالك
    by_currency = {}
    for l in all_lines:
        by_currency.setdefault(l["currency"], ZERO)
        by_currency[l["currency"]] += Decimal(l["amount"])

    previous = Snapshot.objects.filter(
        tenant=tenant, owner__isnull=True, kind=Snapshot.Kind.DAILY
    ).order_by("-taken_at", "-id").first()
    prev_total = previous.total_base if previous else ZERO

    notes = []
    if any(g["unresolved"] for g in counted):
        notes.append("بنودٌ عملتها بلا سعر صرف مضبوط لا تدخل المجموع — اضبط سعرها في «أسعار الصرف».")
    missing = sorted({
        c for c in (cur.currency_of(p) for p in providers) if not cur.rate_of(tenant, c)
    })
    if missing:
        notes.append(
            f"لا سعر صرف لـ{'، '.join(missing)} — أرصدة مزوّديها لا تُحوَّل."
        )

    return {
        "base_currency": base,
        "rates": {k: str(v) for k, v in (tenant.exchange_rates or {}).items()},
        "groups": groups,
        "manual": manual,
        "by_currency": {k: str(v.quantize(CENT)) for k, v in sorted(by_currency.items())},
        "totals": {
            "total": str(total),
            "assets": str(assets),
            "liabilities": str(liabilities),
            "previous_total": str(prev_total),
            "profit": str(total - prev_total if previous else ZERO),
        },
        "previous": {
            "id": previous.id,
            "taken_at": previous.taken_at.strftime("%Y-%m-%d %H:%M"),
            "total": str(prev_total),
        } if previous else None,
        "sources": [{"key": k, "label": lbl, "enabled": conf.enabled(k)} for k, lbl in SOURCES],
        "notes": notes,
    }


# ─────────────────────────── جرد الوكيل الكبير ───────────────────────────

def _summarise(tenant, groups, manual, previous, *, base, sources, notes):
    """المجاميع والملخّص — مشتركة بين جرد المتجر وجرد الوكيل الكبير."""
    counted = [g for g in groups if g["enabled"]] + [manual]
    all_lines = [l for g in counted for l in g["lines"]]
    vals = [Decimal(l["base"]) for l in all_lines if l["base"] is not None]
    total = sum(vals, ZERO)
    by_currency = {}
    for l in all_lines:
        by_currency.setdefault(l["currency"], ZERO)
        by_currency[l["currency"]] += Decimal(l["amount"])
    prev_total = previous.total_base if previous else ZERO
    return {
        "base_currency": base,
        "rates": {k: str(v) for k, v in (tenant.exchange_rates or {}).items()},
        "groups": groups, "manual": manual,
        "by_currency": {k: str(v.quantize(CENT)) for k, v in sorted(by_currency.items())},
        "totals": {
            "total": str(total),
            "assets": str(sum((v for v in vals if v > 0), ZERO)),
            "liabilities": str(-sum((v for v in vals if v < 0), ZERO)),
            "previous_total": str(prev_total),
            "profit": str(total - prev_total if previous else ZERO),
        },
        "previous": {
            "id": previous.id, "taken_at": previous.taken_at.strftime("%Y-%m-%d %H:%M"),
            "total": str(prev_total),
        } if previous else None,
        "sources": sources,
        "notes": notes,
    }


def _build_agent(tenant, agent) -> dict:
    """
    جرد الوكيل الكبير — لا مزوّدين ولا اشتراك منصّة عنده:
    رصيده لدى المتجر · حساباته ونقده · محافظ دكاكينه (معكوسة) · بنوده اليدوية.
    """
    base = cur.base_currency(tenant)
    wallet = Wallet.objects.filter(user=agent).first()
    own = wallet.balance if wallet else ZERO
    groups = [
        _group("agent_wallet", "رصيدي لدى المتجر",
               [_line(tenant, "محفظتي", own, base)],
               hint="الموجب مالٌ لك عند المتجر، والسالب دَينٌ عليك له."),
        _group("receiving", "حساباتي والنقد", [
            _line(tenant, f"{a.title} · {a.get_method_display()}", a.balance, base, item_id=a.id)
            for a in ReceivingAccount.objects.filter(
                tenant=tenant, owner=agent, status=ReceivingAccount.Status.ACTIVE
            ).order_by("sort_order", "id")
        ], hint="حساباتك المفعّلة من «الوكلاء ← حساباتي»."),
    ]
    agg = Wallet.objects.filter(user__parent=agent, user__role=User.Role.BAYI).aggregate(
        net=Sum("balance"),
        credit=Sum("balance", filter=Q(balance__gt=0)), credit_n=Count("id", filter=Q(balance__gt=0)),
        debt=Sum("balance", filter=Q(balance__lt=0)), debt_n=Count("id", filter=Q(balance__lt=0)),
    )
    show = lambda v: cur.to_display(agent, v or ZERO)  # noqa: E731
    # أرصدة الدكاكين **للاطّلاع لا للجمع**: ما أعطاه الوكيل لدكانه خرج من محفظته
    # (فنقصت هنا) ودخل صندوقه نقداً (فزاد هناك) — رأس ماله تغيّر شكلاً لا قيمةً.
    # وما في محفظة الدكان دَينٌ عليه لدكانه ومالٌ له عند المتجر معاً: يتعادلان.
    groups.append(_group("dealer_wallets", "أرصدة دكاكيني (للاطّلاع)", [_line(
        tenant, "مجموع أرصدة دكاكيني", agg["net"] or ZERO, base,
        note=(f"{agg['credit_n'] or 0} برصيد موجب = {show(agg['credit'])} · "
              f"{agg['debt_n'] or 0} برصيد سالب = {show(-(agg['debt'] or ZERO))} مدينون لك"),
    )], hint="لا تدخل المجموع: ما أعطيته لدكانه نقص من محفظتك ودخل صندوقك — "
             "ورصيده عند المتجر يقابله دَينك له.", enabled=False))
    manual = _group("manual", "البنود اليدوية", [
        _line(tenant, m.name, m.amount, m.currency, note=m.note, source="manual", item_id=m.id)
        for m in ManualItem.objects.filter(tenant=tenant, owner=agent, active=True)
    ], hint="ما لا يعرفه النظام: دَينٌ خارجي، مصروف، نقدٌ في الصندوق…", auto=False)
    previous = Snapshot.objects.filter(
        tenant=tenant, owner=agent, kind=Snapshot.Kind.DAILY).order_by("-taken_at", "-id").first()
    return _summarise(tenant, groups, manual, previous, base=base, sources=[], notes=[])


def for_viewer(data: dict, agent) -> dict:
    """
    الجرد بعملة الوكيل الكبير لعرضه: الحساب كلّه بعملة الدفتر (ومنه تُحفظ اللقطات)،
    والتحويل عند الخروج وحده.
    """
    if agent is None:
        return data
    show = lambda v: str(cur.to_display(agent, v)) if v is not None else None  # noqa: E731
    for g in data["groups"] + [data["manual"]]:
        g["total_base"] = show(g["total_base"])
        for l in g["lines"]:
            l["base"] = show(l["base"])
    data["totals"] = {k: show(v) for k, v in data["totals"].items()}
    if data["previous"]:
        data["previous"]["total"] = show(data["previous"]["total"])
    data["base_currency"] = cur.display_currency(agent)
    data["rates"] = {}
    return data
