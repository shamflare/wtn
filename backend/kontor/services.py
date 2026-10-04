"""منطق استيراد باقات الخطوط من ZNET — يستعمله أمر الإدارة وواجهة الـ API معاً."""
from decimal import ROUND_UP, Decimal, InvalidOperation

import requests

from .models import KontorCategory, KontorPackage, LineType, Operator

_OPERATORS = {c.value for c in Operator}
_TYPES = {c.value for c in LineType}
_TYPE_LABEL = dict(LineType.choices)
_OP_LABEL = dict(Operator.choices)


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


def upsert_packages(tenant, rows, *, dry_run=False) -> dict:
    """
    يُنشئ الفئات الناقصة ويحفظ الباقات. عند وجود باقة سابقة لا يُحدَّث إلا الاسم
    والكلفة — حفاظاً على ما عدّله المالك (الموصى، النوع، الحالة، التوجيه).
    """
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
                defaults={"name": f"{_OP_LABEL[r['operator']]} — {_TYPE_LABEL[r['line_type']]}"},
            )
            cats[key] = cat

        obj = KontorPackage.objects.filter(
            tenant=tenant, operator=r["operator"], znet_id=r["znet_id"]).first()
        if obj:
            obj.name = r["name"]
            obj.cost_price = r["cost"]
            if obj.category_id is None:
                obj.category = cat
            obj.save(update_fields=["name", "cost_price", "category", "updated_at"])
            updated += 1
        else:
            KontorPackage.objects.create(
                tenant=tenant, operator=r["operator"], category=cat,
                znet_id=r["znet_id"], name=r["name"], cost_price=r["cost"],
                kind=KontorPackage.Kind.OFFER if looks_like_offer(r["name"]) else KontorPackage.Kind.GENERAL,
            )
            created += 1
    return {"received": len(rows), "created": created, "updated": updated}


def fetch_feed(base_url: str, kod: str, sifre: str) -> str:
    """يجلب نصّ paket_listesi من ZNET (يرمي requests.RequestException عند الفشل)."""
    url = f"{base_url.rstrip('/')}/servis/paket_listesi.php"
    resp = requests.get(url, params={"bayi_kodu": kod, "sifre": sifre}, timeout=(5, 30))
    return resp.text


def import_from_znet(tenant, base_url, kod, sifre, *, dry_run=False) -> dict:
    """يجلب من ZNET ثم يحفظ. يرفع ValueError برسالة عربية عند عدم وجود باقات."""
    rows = parse_feed(fetch_feed(base_url, kod, sifre))
    if not rows:
        raise ValueError("لا باقات في الرد — تحقّق من بيانات الدخول وتفعيل API وثبات الـ IP.")
    res = upsert_packages(tenant, rows, dry_run=dry_run)
    if not dry_run:
        from .models import KontorPriceGroup
        for g in KontorPriceGroup.objects.filter(tenant=tenant):
            recompute_group_prices(g)
    return res


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
