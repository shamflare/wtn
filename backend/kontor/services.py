"""منطق استيراد باقات الخطوط من ZNET — يستعمله أمر الإدارة وواجهة الـ API معاً."""
from decimal import ROUND_UP, Decimal, InvalidOperation

import requests

from .models import KontorCategory, KontorPackage, LineType, Operator

_OPERATORS = {c.value for c in Operator}
_TYPES = {c.value for c in LineType}
_TYPE_LABEL = dict(LineType.choices)
_OP_LABEL = dict(Operator.choices)

# أسماء الفئات القصيرة كما في ZNET (الشعار يدلّ على الشركة فلا يُكرَّر اسمها)،
# مع تصحيح التباسه: 3gPc يصير Wifi كي لا يتشابه مع 3gCep.
SHORT_NAME = {
    "Tam": "Tam", "Ses": "Ses", "Sms": "Sms", "3gCep": "3gCep", "3gPc": "Wifi",
    "Yds": "Yds", "BimCell": "BiP", "Mtn": "MTN", "Syriatel": "Syriatel",
}


def parse_feed(text: str) -> list[dict]:
    """نصّ `paket_listesi` ⇐ قائمة باقات صالحة. يتجاهل الأسطر المشوّهة."""
    rows = []
    for chunk in (text or "").split("^"):
        chunk = chunk.strip()
        if not chunk:
            continue
        parts = chunk.split("|")
        if len(parts) < 5:
            continue
        op, tur, zid, cost, name = (p.strip() for p in parts[:5])
        if op not in _OPERATORS or tur not in _TYPES or not zid:
            continue
        try:
            cost_val = Decimal(cost.replace(",", "."))
        except (InvalidOperation, AttributeError):
            cost_val = Decimal("0")
        rows.append({"operator": op, "line_type": tur, "znet_id": zid,
                     "cost": cost_val, "name": name})
    return rows


def looks_like_offer(name: str) -> bool:
    low = (name or "").lower()
    return any(k in low for k in ("fırsat", "firsat", "indirim", "i̇ndirim"))


# لاحقة الشركة حين يتكرّر رقم ZNET بين شركتين (باقات Tam مرقّمة بقيمتها: 100 لكلٍّ منها)
OP_SUFFIX = {"Turkcell": "T", "Vodafone": "V", "Avea": "A", "Callback": "C"}


def free_link_code(tenant, znet_id: str, operator: str, exclude_pk=None) -> str:
    """
    رقم ربط لباقة جديدة: رقم ZNET نفسه إن كان حرّاً في المتجر، وإلا مع لاحقة
    الشركة (100 ⇐ 100V)، وإلا مع عدّاد. هكذا يبقى من ربط مع ZNET على أرقامه.
    """
    qs = KontorPackage.objects.filter(tenant=tenant)
    if exclude_pk:
        qs = qs.exclude(pk=exclude_pk)
    taken = lambda c: qs.filter(link_code=c).exists()  # noqa: E731
    base = (znet_id or "").strip()
    if base and not taken(base):
        return base
    code = f"{base}{OP_SUFFIX.get(operator, 'X')}"
    n = 2
    while taken(code):
        code = f"{base}{OP_SUFFIX.get(operator, 'X')}{n}"
        n += 1
    return code


def _cost_in_base(tenant, cost, provider):
    """كلفة ZNET (بعملته) ⇐ عملة دفتر المتجر. ValueError إن لم يُضبط سعر الصرف."""
    from core import currency
    val = currency.from_provider(tenant, cost, provider)
    if val is None:
        cur = currency.currency_of(provider)
        raise ValueError(
            f"لا سعر صرف لـ{cur} — اضبطه في «الوكلاء ⟵ أسعار الصرف» قبل الاستيراد، "
            f"فكلفة ZNET بـ{cur} ودفتر المتجر بـ{currency.base_currency(tenant)}.")
    return val


def upsert_packages(tenant, rows, *, dry_run=False, provider=None) -> dict:
    """
    يُنشئ الفئات الناقصة ويحفظ الباقات. عند وجود باقة سابقة لا يُحدَّث إلا الاسم
    والكلفة — حفاظاً على ما عدّله المالك (الموصى، النوع، الحالة، التوجيه).

    الكلفة تصل بعملة ZNET (الليرة): تُحفظ كما هي في provider_cost، ومحوّلةً إلى
    عملة الدفتر في cost_price — فكل سعر بعدها (الموصى، المجموعات، الخصم) بعملة الدفتر.
    """
    if rows and not dry_run:
        _cost_in_base(tenant, rows[0]["cost"], provider)  # يفشل مبكراً إن لم يُضبط الصرف
    created = updated = 0
    cats: dict[tuple, KontorCategory] = {}
    for r in rows:
        if dry_run:
            continue
        key = (r["operator"], r["line_type"])
        cat = cats.get(key)
        if cat is None:
            cat, _ = KontorCategory.objects.get_or_create(
                tenant=tenant, operator=r["operator"], line_type=r["line_type"],
                defaults={"name": SHORT_NAME.get(r["line_type"], r["line_type"])},
            )
            cats[key] = cat

        obj = KontorPackage.objects.filter(
            tenant=tenant, operator=r["operator"], znet_id=r["znet_id"]).first()
        cost = _cost_in_base(tenant, r["cost"], provider)
        if obj:
            obj.name = r["name"]
            obj.provider_cost = r["cost"]
            obj.cost_price = cost
            if obj.category_id is None:
                obj.category = cat
            if not obj.link_code:
                obj.link_code = free_link_code(tenant, obj.znet_id, obj.operator, exclude_pk=obj.pk)
            obj.save(update_fields=["name", "provider_cost", "cost_price", "category",
                                    "link_code", "updated_at"])
            updated += 1
        else:
            KontorPackage.objects.create(
                tenant=tenant, operator=r["operator"], category=cat,
                znet_id=r["znet_id"], name=r["name"], provider_cost=r["cost"], cost_price=cost,
                link_code=free_link_code(tenant, r["znet_id"], r["operator"]),
                kind=KontorPackage.Kind.OFFER if looks_like_offer(r["name"]) else KontorPackage.Kind.GENERAL,
            )
            created += 1
    return {"received": len(rows), "created": created, "updated": updated}


def fetch_feed(base_url: str, kod: str, sifre: str) -> str:
    """يجلب نصّ paket_listesi من ZNET (يرمي requests.RequestException عند الفشل)."""
    url = f"{base_url.rstrip('/')}/servis/paket_listesi.php"
    resp = requests.get(url, params={"bayi_kodu": kod, "sifre": sifre}, timeout=(5, 30))
    return resp.text


def import_from_znet(tenant, base_url, kod, sifre, *, dry_run=False, provider=None) -> dict:
    """يجلب من ZNET ثم يحفظ. يرفع ValueError برسالة عربية عند عدم وجود باقات."""
    rows = parse_feed(fetch_feed(base_url, kod, sifre))
    if not rows:
        raise ValueError("لا باقات في الرد — تحقّق من بيانات الدخول وتفعيل API وثبات الـ IP.")
    res = upsert_packages(tenant, rows, dry_run=dry_run, provider=provider)
    if not dry_run:
        from .models import KontorPriceGroup
        for g in KontorPriceGroup.objects.filter(tenant=tenant):
            recompute_group_prices(g)
    return res


def reprice_costs(tenant, provider=None) -> int:
    """
    يعيد اشتقاق cost_price من provider_cost بسعر الصرف الحالي، ثم يعيد حساب
    الخلايا المرتبطة بقاعدة. يُستدعى عند تغيير أسعار الصرف. بلا سعر صرف ⇐ لا شيء.
    """
    from core import currency
    from .models import KontorPriceGroup
    if provider is None:
        from .execution import znet_provider
        provider = znet_provider(tenant)
    n = 0
    for p in KontorPackage.objects.filter(tenant=tenant, provider_cost__gt=0):
        val = currency.from_provider(tenant, p.provider_cost, provider)
        if val is None:
            return 0
        if val != p.cost_price:
            p.cost_price = val
            p.save(update_fields=["cost_price", "updated_at"])
            n += 1
    if n:
        for g in KontorPriceGroup.objects.filter(tenant=tenant):
            recompute_group_prices(g)
    return n


# ─────────────────────────── التسعير ───────────────────────────

CENT = Decimal("0.01")


def _apply_margin(cost: Decimal, mode: str, value, round_up: bool) -> Decimal:
    """كلفة + قاعدة ⇐ سعر. التقريب لأعلى إلى أقرب نصف كما في الألعاب."""
    value = Decimal(str(value or 0))
    if mode == "percent":
        price = cost * (Decimal("1") + value / Decimal("100"))
    elif mode == "fixed":
        price = cost + value
    else:
        price = cost
    if round_up:
        price = (price * 2).to_integral_value(rounding=ROUND_UP) / 2
    return price.quantize(CENT)


def recompute_group_prices(group) -> int:
    """يعيد حساب أسعار المجموعة المرتبطة بقاعدة بعد تغيّر الكلفة. يعيد عدد ما تغيّر."""
    from .models import KontorPackagePrice
    n = 0
    for pp in KontorPackagePrice.objects.filter(group=group).select_related("package"):
        if pp.margin_mode and pp.margin_value is not None:
            new = _apply_margin(pp.package.cost_price, pp.margin_mode, pp.margin_value, pp.margin_round)
            if new != pp.price:
                pp.price = new
                pp.save(update_fields=["price"])
                n += 1
    return n


def dealer_price(dealer, package) -> Decimal:
    """
    سعر الوكيل لباقة: سعر مجموعته لشركة الباقة، وإلا السعر الموصى.
    """
    from .models import KontorDealerSetting, KontorPackagePrice
    setting = KontorDealerSetting.objects.filter(
        dealer=dealer, operator=package.operator).select_related("group").first()
    if setting and setting.group_id:
        pp = KontorPackagePrice.objects.filter(package=package, group_id=setting.group_id).first()
        if pp:
            return pp.price.quantize(CENT)
    return (package.recommended_price or Decimal("0")).quantize(CENT)


def dealer_can_query(dealer, operator) -> bool:
    """هل يُسمح للوكيل باستعلام العروض الخاصة لهذه الشركة (افتراضاً نعم)."""
    from .models import KontorDealerSetting
    s = KontorDealerSetting.objects.filter(dealer=dealer, operator=operator).first()
    return s.can_query if s else True
