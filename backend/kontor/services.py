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


def is_kontor_provider(provider) -> bool:
    """مزوّد يصلح لشحن الخطوط: لوحة ZNET (نفس النظام) — ترسل tl_servis وتجيب tl_kontrol."""
    return ((provider.config or {}).get("code") or "").lower() == "znet"


def kontor_providers(tenant):
    """مزوّدو الخطوط في المتجر (لوحات ZNET) — بالترتيب الذي تظهر به في «مزوّدو API»."""
    from providers.models import Provider
    return [p for p in Provider.objects.filter(tenant=tenant).order_by("sort_order", "id")
            if is_kontor_provider(p)]


def provider_creds(provider):
    """(base_url, kod, sifre) لمزوّد — أو None إن نقص شيء منها."""
    cfg = provider.config or {} if provider else {}
    base, kod, sifre = cfg.get("base_url"), cfg.get("kod"), cfg.get("sifre")
    return (base, kod, sifre) if (base and kod and sifre) else None


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


def upsert_packages(tenant, rows, *, dry_run=False, provider=None, only_new=False) -> dict:
    """
    يُنشئ الفئات الناقصة ويحفظ الباقات. عند وجود باقة سابقة لا يُحدَّث إلا الاسم
    والكلفة — حفاظاً على ما عدّله المالك (الموصى، النوع، الحالة، التوجيه).

    only_new: استيراد المالك من الواجهة — يُضاف الجديد وحده ولا تُمسّ الباقة
    الموجودة أصلاً (بربطها لدى هذا المزوّد، أو برقم ZNET نفسه، أو باسمها في
    الشركة نفسها). تحديث الكلفة له زرّه المستقلّ (refresh_costs).

    الكلفة تصل بعملة ZNET (الليرة): تُحفظ كما هي في provider_cost، ومحوّلةً إلى
    عملة الدفتر في cost_price — فكل سعر بعدها (الموصى، المجموعات، الخصم) بعملة الدفتر.
    """
    if rows and not dry_run:
        _cost_in_base(tenant, rows[0]["cost"], provider)  # يفشل مبكراً إن لم يُضبط الصرف
    created = updated = existing = 0
    known = _known_keys(tenant, provider) if only_new else None
    cats: dict[tuple, KontorCategory] = {}
    for r in rows:
        if dry_run:
            continue
        if known is not None and (
                (r["operator"], "id", r["znet_id"]) in known
                or (r["operator"], "name", _norm_name(r["name"])) in known):
            existing += 1
            continue
        key = (r["operator"], r["line_type"])
        cat = cats.get(key)
        if cat is None:
            cat, _ = KontorCategory.objects.get_or_create(
                tenant=tenant, operator=r["operator"], line_type=r["line_type"], is_custom=False,
                defaults={"name": SHORT_NAME.get(r["line_type"], r["line_type"])},
            )
            cats[key] = cat

        obj = KontorPackage.objects.filter(
            tenant=tenant, operator=r["operator"], znet_id=r["znet_id"]).first()
        cost = _cost_in_base(tenant, r["cost"], provider)
        if obj:
            # الاسم يتبع ZNET ما لم يعدّله المالك (name == provider_name)
            if not obj.provider_name or obj.name == obj.provider_name:
                obj.name = r["name"]
            obj.provider_name = r["name"]
            obj.provider_cost = r["cost"]
            obj.cost_price = cost
            if obj.category_id is None:
                obj.category = cat
            if not obj.link_code:
                obj.link_code = free_link_code(tenant, obj.znet_id, obj.operator, exclude_pk=obj.pk)
            if obj.provider_id is None and provider is not None:
                obj.provider = provider
            obj.save(update_fields=["name", "provider_name", "provider_cost", "cost_price", "category",
                                    "link_code", "provider", "updated_at"])
            _link(tenant, obj, provider, r["znet_id"], r["cost"])
            updated += 1
        else:
            new = KontorPackage.objects.create(
                tenant=tenant, operator=r["operator"], category=cat,
                znet_id=r["znet_id"], name=r["name"], provider_name=r["name"],
                provider_cost=r["cost"], cost_price=cost, provider=provider,
                link_code=free_link_code(tenant, r["znet_id"], r["operator"]),
                kind=KontorPackage.Kind.OFFER if looks_like_offer(r["name"]) else KontorPackage.Kind.GENERAL,
            )
            _link(tenant, new, provider, r["znet_id"], r["cost"])
            created += 1
            if known is not None:
                known.add((r["operator"], "id", r["znet_id"]))
                known.add((r["operator"], "name", _norm_name(r["name"])))
    res = {"received": len(rows), "created": created, "updated": updated}
    if only_new:
        res["existing"] = existing
    return res


def _known_keys(tenant, provider) -> set:
    """مفاتيح الباقات الموجودة: (شركة، id، رقم) و(شركة، name، اسم مطويّ)."""
    from .models import KontorPackageLink
    keys = set()
    for p in KontorPackage.objects.filter(tenant=tenant):
        keys.add((p.operator, "id", p.znet_id))
        for n in (p.name, p.provider_name):
            if n:
                keys.add((p.operator, "name", _norm_name(n)))
    if provider is not None:
        for l in KontorPackageLink.objects.filter(tenant=tenant, provider=provider).select_related("package"):
            keys.add((l.package.operator, "id", l.code))
    return keys


def _link(tenant, package, provider, code, cost):
    """يسجّل/يحدّث ربط الباقة بالمزوّد الذي استوردت منه: رقمها وكلفتها عنده."""
    if provider is None:
        return
    from .models import KontorPackageLink
    KontorPackageLink.objects.update_or_create(
        package=package, provider=provider,
        defaults={"tenant": tenant, "code": str(code), "cost": cost})


_TR_FOLD = str.maketrans({"ı": "i", "ç": "c", "ğ": "g", "ö": "o", "ş": "s", "ü": "u"})


def _norm_name(s: str) -> str:
    """
    اسم للمطابقة بين لوحتين: بلا رموز ولا مسافات، والحروف التركية مطويّة
    (✅ Fırsat 30GB İndirimli ⇐ firsat30gbindirimli = FIRSAT 30GB INDIRIMLI).
    """
    import re
    s = (s or "").replace("İ", "i").replace("I", "i").lower().translate(_TR_FOLD)
    return re.sub(r"[^0-9a-z]", "", s)


def auto_link(tenant, provider) -> dict:
    """
    يربط باقات المتجر بمزوّد ZNET آخر من قائمة باقاته: بالرقم أوّلاً (نفس الشركة
    ونفس رقم ZNET)، وإلا بالاسم. لا يُنشئ باقات — يربط القائم فقط ويحدّث الكلفة
    والرقم لدى هذا المزوّد. يعيد تقريراً بما رُبط وما بقي.
    """
    from .models import KontorPackageLink
    creds = provider_creds(provider)
    if not creds:
        raise ValueError("إعداد المزوّد ناقص (base_url/kod/sifre)")
    rows = parse_feed(fetch_feed(*creds))
    if not rows:
        raise ValueError("لا باقات في رد المزوّد — تحقّق من بيانات الدخول وتفعيل API وثبات الـ IP.")
    by_id = {(r["operator"], r["znet_id"]): r for r in rows}
    by_name: dict = {}
    for r in rows:
        by_name.setdefault((r["operator"], _norm_name(r["name"])), r)

    report = {"by_id": 0, "by_name": 0, "unmatched": [], "received": len(rows)}
    for p in KontorPackage.objects.filter(tenant=tenant):
        r = by_id.get((p.operator, p.znet_id))
        how = "by_id"
        if r is None:
            r = by_name.get((p.operator, _norm_name(p.provider_name or p.name)))
            how = "by_name"
        if r is None:
            report["unmatched"].append(f"{p.link_code} · {p.name}")
            continue
        KontorPackageLink.objects.update_or_create(
            package=p, provider=provider,
            defaults={"tenant": tenant, "code": r["znet_id"], "cost": r["cost"]})
        report[how] += 1
    return report


def fetch_feed(base_url: str, kod: str, sifre: str) -> str:
    """يجلب نصّ paket_listesi من ZNET (يرمي requests.RequestException عند الفشل)."""
    url = f"{base_url.rstrip('/')}/servis/paket_listesi.php"
    resp = requests.get(url, params={"bayi_kodu": kod, "sifre": sifre}, timeout=(5, 30))
    return resp.text


def import_from_znet(tenant, base_url, kod, sifre, *, dry_run=False, provider=None,
                     only_new=False) -> dict:
    """يجلب من ZNET ثم يحفظ. يرفع ValueError برسالة عربية عند عدم وجود باقات."""
    rows = parse_feed(fetch_feed(base_url, kod, sifre))
    if not rows:
        raise ValueError("لا باقات في الرد — تحقّق من بيانات الدخول وتفعيل API وثبات الـ IP.")
    res = upsert_packages(tenant, rows, dry_run=dry_run, provider=provider, only_new=only_new)
    if not dry_run and not only_new:
        from .models import KontorPriceGroup
        for g in KontorPriceGroup.objects.filter(tenant=tenant):
            recompute_group_prices(g)
    return res


def refresh_costs(tenant, provider) -> dict:
    """
    «تحديث التكلفة»: كلفة كل باقة = كلفتها لدى هذا المزوّد. تُطابَق الباقة برقمها
    **لديه** (ربطها في «التوجيه») لا برقم ZNET — فلكل لوحة أرقامها. الباقة غير
    المربوطة به، أو التي لم يعد رقمها في قائمته، لا تُمسّ وتُذكر في التقرير
    مجمّعة بالشركة والفئة (مثل: 7 باقات Turkcell · Tam).
    """
    from .models import KontorPackageLink, KontorPriceGroup
    creds = provider_creds(provider)
    if not creds:
        raise ValueError("إعداد المزوّد ناقص (base_url/kod/sifre)")
    rows = parse_feed(fetch_feed(*creds))
    if not rows:
        raise ValueError("لا باقات في رد المزوّد — تحقّق من بيانات الدخول وتفعيل API وثبات الـ IP.")
    feed = {(r["operator"], r["znet_id"]): r for r in rows}
    _cost_in_base(tenant, rows[0]["cost"], provider)  # يفشل مبكراً إن لم يُضبط الصرف
    links = {l.package_id: l for l in KontorPackageLink.objects.filter(tenant=tenant, provider=provider)}

    updated = unchanged = 0
    skipped: dict[tuple, int] = {}
    for p in KontorPackage.objects.filter(tenant=tenant).select_related("category"):
        link = links.get(p.id)
        r = feed.get((p.operator, link.code)) if link else None
        if r is None:
            key = (p.operator, p.category.name if p.category else "—")
            skipped[key] = skipped.get(key, 0) + 1
            continue
        cost = _cost_in_base(tenant, r["cost"], provider)
        if link.cost != r["cost"]:
            link.cost = r["cost"]
            link.save(update_fields=["cost", "updated_at"])
        if p.provider_cost == r["cost"] and p.cost_price == cost:
            unchanged += 1
            continue
        p.provider_cost = r["cost"]
        p.cost_price = cost
        p.save(update_fields=["provider_cost", "cost_price", "updated_at"])
        updated += 1
    if updated:
        for g in KontorPriceGroup.objects.filter(tenant=tenant):
            recompute_group_prices(g)
    return {
        "provider": provider.name, "received": len(rows),
        "updated": updated, "unchanged": unchanged,
        "skipped_total": sum(skipped.values()),
        "skipped": [{"operator": op, "operator_label": _OP_LABEL.get(op, op), "category": cat, "count": n}
                    for (op, cat), n in sorted(skipped.items())],
    }


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


def store_price(buyer, package) -> Decimal:
    """
    ما يقبضه **المتجر** من هذا المشتري: سعر مجموعته لشركة الباقة، وإلا السعر الموصى.
    """
    from .models import KontorDealerSetting, KontorPackagePrice
    setting = KontorDealerSetting.objects.filter(
        dealer=buyer, operator=package.operator).select_related("group").first()
    if setting and setting.group_id:
        pp = KontorPackagePrice.objects.filter(package=package, group_id=setting.group_id).first()
        if pp:
            return pp.price.quantize(CENT)
    return (package.recommended_price or Decimal("0")).quantize(CENT)


def agent_price(agent, group_id, package) -> Decimal:
    """
    سعر الباقة لدكانٍ عند وكيله الكبير: سعر مجموعته عند وكيله، وإلا تكلفة الوكيل.
    ولا ينزل أبداً تحت تكلفة الوكيل — لو رفع المتجر سعره بعد أن سعّر الوكيل، لا
    يبيع الوكيل بخسارةٍ لا يعرف بها.
    """
    from .models import AgentKontorPrice
    cost = store_price(agent, package)
    if group_id:
        row = AgentKontorPrice.objects.filter(group_id=group_id, package=package).first()
        if row:
            from catalog.services import agent_row_price
            return agent_row_price(row, cost)
    return cost


def dealer_price(dealer, package) -> Decimal:
    """ما يدفعه المشتري: من وكيله الكبير إن كان له وكيل، وإلا من المتجر مباشرةً."""
    from orders.services import big_agent_of
    agent = big_agent_of(dealer)
    if agent is None:
        return store_price(dealer, package)
    return agent_price(agent, dealer.agent_price_group_id, package)


def dealer_can_query(dealer, operator) -> bool:
    """هل يُسمح للوكيل باستعلام العروض الخاصة لهذه الشركة (افتراضاً نعم)."""
    from .models import KontorDealerSetting
    s = KontorDealerSetting.objects.filter(dealer=dealer, operator=operator).first()
    return s.can_query if s else True
