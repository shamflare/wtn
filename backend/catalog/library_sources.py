"""
ملء المكتبة العالمية من مزوّد، وربط باقات المتاجر به تلقائياً.

ثلاث خطوات، كلٌّ منها دالّة:

1. `fetch_catalog(source)` — كتالوج المزوّد مجمّعاً بالقسم (اللعبة)، وكل قسمٍ
   وباقة موسومان بحالتهما مقابل المكتبة: جديد · موجود · تغيّر سعره · أُزيل.
2. `apply_import(source, picks, …)` — ينشئ ما اختير ويحدّث الموجود. لا يحذف
   شيئاً: الباقة التي أزالها المزوّد تُطفأ (`is_active=False`) فقط.
3. `autolink(tenant, games)` — باقات المتجر المستوردة من مصدرٍ يملكه المتجر
   مزوّداً تُربط به (ProductLink) ويُضبط توجيهها — بلا ضغطة من صاحبها.

«المزوّد نفسه» يُعرف ببصمته: عائلة المحوّل + نطاق الرابط. بركات عند المالك
وبركات عند صاحب المتجر بصمةٌ واحدة، وإن اختلف مفتاحاهما.
"""
import re
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from urllib.parse import urlparse

from django.db import transaction
from django.utils import timezone

CENT = Decimal("0.01")

# عائلات المحوّلات: barakat/apstore متجران ببرمجية ZDK نفسها
_FAMILY = {"zdk": "zdk", "barakat": "zdk", "apstore": "zdk"}
SUPPORTED = {"zdk"}


def family(code: str) -> str:
    return _FAMILY.get((code or "").lower(), (code or "").lower())


def fingerprint(code: str, config: dict) -> str:
    """بصمة المزوّد: `zdk:api.barakat.store` — يتطابق بها مصدر المالك ومزوّد المتجر."""
    from providers.adapters.zdk import DEFAULT_BASE

    fam = family(code)
    base = ((config or {}).get("base_url") or "").strip() or (DEFAULT_BASE if fam == "zdk" else "")
    host = urlparse(base if "://" in base else f"https://{base}").hostname or ""
    return f"{fam}:{host.lower().removeprefix('www.')}"


def provider_fingerprint(provider) -> str:
    """بصمة مزوّد متجر — كوده الصريح، وإلا فنوعه (متجر بطاقات = ZDK)."""
    from providers.models import Provider

    code = (provider.config or {}).get("code") or ""
    if not code and provider.type == Provider.Type.CARD_STORE:
        code = "zdk"
    return fingerprint(code, provider.config or {})


def _dec(v):
    try:
        return Decimal(str(v).replace(",", ".")) if v not in (None, "") else None
    except (InvalidOperation, ValueError):
        return None


# بركات يضع سعراً وهمياً (100,000,000,000) للباقة غير المعروضة للبيع، وأعلى سعرٍ
# حقيقي في كتالوجه عشرات الآلاف. ما بلغ هذا الحدّ «بلا سعر»: لا يُحفظ (يفيض
# الحقل فيسقط الاستيراد كلّه) ولا تُعرض الباقة.
SANE_MAX = Decimal("1000000")


def sane_price(v) -> Decimal | None:
    d = _dec(v)
    return d if d is not None and Decimal("0") < d < SANE_MAX else None


def sellable(p: dict) -> bool:
    """متاحةٌ عند المزوّد وبسعرٍ حقيقي."""
    return p.get("available", True) is not False and sane_price(p.get("price")) is not None


def to_usd(source, cost) -> Decimal | None:
    """سعر المصدر بعملته ⇐ دولار المكتبة."""
    cost = sane_price(cost)
    if cost is None:
        return None
    rate = source.usd_rate if source.currency.upper() != "USD" else Decimal("1")
    if not rate or rate <= 0:
        return None
    return (cost / rate).quantize(CENT, ROUND_HALF_UP)


def with_margin(cost_usd: Decimal, margin) -> Decimal:
    m = _dec(margin) or Decimal("0")
    return (cost_usd * (Decimal("1") + m / Decimal("100"))).quantize(CENT, ROUND_HALF_UP)


# ════════════════ 1. الجلب والمقارنة ════════════════

def _raw_packages(source):
    from providers.adapters.zdk import ZdkAdapter

    if family(source.code) not in SUPPORTED:
        return None, f"نوع المصدر «{source.code}» غير مدعوم بعد (ZDK فقط)"
    res = ZdkAdapter().list_packages(source.config or {})
    if not res.ok:
        return None, res.note or "تعذّر جلب الكتالوج"
    return [p for p in res.packages if not _excluded(p)], ""


# أكواد محفظة بركات نفسه («Barakat Kodu») — ليست منتجاً يُعاد بيعه.
EXCLUDED_WORDS = ("barakat",)


def _excluded(p: dict) -> bool:
    text = f"{p.get('game') or ''} {p.get('name') or ''}".lower()
    return any(w in text for w in EXCLUDED_WORDS)


# بركات يعرض اللعبة الواحدة في قسمين: «4FUN CHAT» فيه منتجٌ «بالكمية» (سعرٌ
# للوحدة، ويختار المشتري كميته)، و«4FUN CHAT-ZNET» فيه **الباقات** الثابتة
# (صُنعت لمن يطلب منه ببرمجية ZNET). فالقسمان لعبةٌ واحدة: يُدمجان تحت الاسم
# بلا اللاحقة، وتُؤخذ الباقات — والمنتج «بالكمية» يُترك متى وُجدت باقات، إذ
# سعره للوحدة ونظامنا يبيع باقاتٍ بكميةٍ ثابتة.
_ZNET_SUFFIX = re.compile(r"[\s_\-]*(znet|zent)\s*$", re.I)
PACKAGE_TYPES = {"package", "specificpackage", ""}


def _norm_key(category: str) -> str:
    return " ".join(_ZNET_SUFFIX.sub("", category or "").split()).upper()


def _is_package(p: dict) -> bool:
    return str(p.get("type") or "").lower() in PACKAGE_TYPES


def _grouped(packages: list):
    """
    ⇐ (groups, amount_only)
    groups: {اسم اللعبة: [باقات]} — باقاتٌ ثابتة فقط، بعد دمج «-ZNET».
    amount_only: {اسم اللعبة: {count, min, max}} — ألعابٌ لا باقات لها بعد.
    """
    # الاسم المعروض: القسم الأصلي (بلا لاحقة) إن وُجد، وإلا اسم قسم ZNET منزوعَ اللاحقة.
    # وهو مفتاح اللعبة في المكتبة (source_key) — فيبقى ثابتاً لما استُورد سابقاً.
    names: dict[str, str] = {}
    for p in packages:
        cat = p.get("game") or "بلا قسم"
        k = _norm_key(cat)
        if not _ZNET_SUFFIX.search(cat):
            names[k] = cat
        elif k not in names:
            names[k] = " ".join(_ZNET_SUFFIX.sub("", cat).split()) or cat
    pkgs: dict[str, list] = {}
    amounts: dict[str, list] = {}
    for p in packages:
        key = names[_norm_key(p.get("game") or "بلا قسم")]
        (pkgs if _is_package(p) else amounts).setdefault(key, []).append(p)
    amount_only = {}
    for key, rows in amounts.items():
        if key in pkgs:
            continue
        q = [r.get("qty") or {} for r in rows]
        amount_only[key] = {"count": len(rows),
                            "min": min((str(x.get("min") or "") for x in q), default=""),
                            "max": max((str(x.get("max") or "") for x in q), default="")}
    return pkgs, amount_only


def fetch_catalog(source) -> dict:
    """الكتالوج مجمّعاً بالقسم، موسوماً بحالته مقابل المكتبة."""
    from .models import LibraryGame

    packages, err = _raw_packages(source)
    if err:
        return {"ok": False, "detail": err}

    groups, amount_only = _grouped(packages)

    existing = {
        g.source_key: g for g in
        LibraryGame.objects.filter(source=source).prefetch_related("products")
    }

    out = []
    for key in sorted(groups, key=str.lower):
        rows = groups[key]
        lib = existing.get(key)
        known = {lp.source_ref: lp for lp in lib.products.all()} if lib else {}
        pkgs, counts = [], {"new": 0, "changed": 0, "same": 0}
        for p in rows:
            ref = str(p.get("id") or "")
            usd = to_usd(source, p.get("price"))
            lp = known.get(ref)
            ok = sellable(p)
            price = sane_price(p.get("price"))
            if lp is None:
                state = "new"
            elif lp.is_active != ok:
                state = "changed"   # توفّرت أو انقطعت
            elif ok and lp.source_cost is not None and Decimal(lp.source_cost) != price:
                state = "changed"
            else:
                state = "same"
            counts[state] += 1
            pkgs.append({
                "ref": ref, "name": p.get("name") or "",
                "price": str(price) if price is not None else "—",
                "usd": str(usd) if usd is not None else None,
                "old_usd": str(lp.suggested_cost) if lp else None,
                "available": ok, "params": p.get("params") or [],
                "state": state,
            })
        live = {pk["ref"] for pk in pkgs}
        removed = [
            {"ref": lp.source_ref, "name": lp.name}
            for lp in known.values() if lp.is_active and lp.source_ref not in live
        ]
        out.append({
            "key": key,
            "state": "existing" if lib else "new",
            "library_id": lib.id if lib else None,
            "library_name": lib.name if lib else "",
            "require_player_id": any(
                any("player" in str(x).lower() for x in pk["params"]) for pk in pkgs),
            "packages": pkgs,
            "counts": {**counts, "removed": len(removed)},
            "removed": removed,
        })
    return {"ok": True, "currency": source.currency, "usd_rate": str(source.usd_rate),
            "total_packages": sum(len(g["packages"]) for g in out), "groups": out,
            "amount_only": [{"key": k, **v} for k, v in sorted(amount_only.items(), key=lambda x: x[0].lower())]}


# ════════════════ 2. الاستيراد والمزامنة ════════════════

def apply_import(source, picks: list, margin=None, update_prices: bool = True) -> dict:
    """
    picks = [{"key": "<اسم القسم لدى المصدر>", "name": "<اسمه في المكتبة، اختياري>"}]

    القسم الجديد ⇐ لعبةٌ جديدة بباقاتها. والموجود ⇐ تُضاف باقاته الجديدة،
    وتُحدَّث أسعار ما تغيّر (`update_prices`)، وتُطفأ ما أزاله المصدر.
    """
    from .models import LibraryGame, LibraryProduct

    packages, err = _raw_packages(source)
    if err:
        return {"ok": False, "detail": err}
    margin = source.default_margin if margin in (None, "") else _dec(margin)
    groups, _ = _grouped(packages)

    summary = {"games_created": 0, "games_updated": 0, "packages_added": 0,
               "prices_updated": 0, "packages_disabled": 0, "skipped": []}
    with transaction.atomic():
        last = LibraryGame.objects.order_by("-sort_order").first()
        order_base = (last.sort_order + 1) if last else 0
        for i, pick in enumerate(picks):
            key = str(pick.get("key") or "")
            rows = groups.get(key)
            if rows is None:
                # لا باقات ثابتة لها (بالكمية فقط، أو أُزيلت): الموجود منها في المكتبة يُطفأ
                lib = LibraryGame.objects.filter(source=source, source_key=key).first()
                if lib is not None:
                    summary["packages_disabled"] += lib.products.filter(is_active=True).update(is_active=False)
                summary["skipped"].append(key)
                continue
            needs_id = any(
                any("player" in str(x).lower() for x in (p.get("params") or [])) for p in rows)
            lib = LibraryGame.objects.filter(source=source, source_key=key).first()
            if lib is None:
                lib = LibraryGame.objects.create(
                    name=(str(pick.get("name") or "").strip() or key)[:120],
                    source=source, source_key=key, require_player_id=needs_id,
                    sort_order=order_base + i,
                )
                summary["games_created"] += 1
            else:
                new_name = str(pick.get("name") or "").strip()
                if new_name and new_name != lib.name:
                    lib.name = new_name[:120]
                    lib.save(update_fields=["name"])
                summary["games_updated"] += 1

            known = {lp.source_ref: lp for lp in lib.products.all()}
            live = set()
            for j, p in enumerate(rows):
                ref = str(p.get("id") or "")
                if not ref:
                    continue
                live.add(ref)
                ok = sellable(p)
                raw = sane_price(p.get("price"))
                usd = to_usd(source, raw)
                lp = known.get(ref)
                if lp is None:
                    # غير المتاحة تُحفظ مطفأة — تتفعّل وحدها في مزامنةٍ تجدها متاحة
                    LibraryProduct.objects.create(
                        game=lib, name=(p.get("name") or ref)[:120], kupur=ref[:60],
                        source_ref=ref, source_name=(p.get("name") or "")[:200], source_cost=raw,
                        suggested_cost=usd or Decimal("0"),
                        suggested_price=with_margin(usd, margin) if usd is not None else Decimal("0"),
                        sort_order=len(known) + j, is_active=ok,
                    )
                    summary["packages_added"] += 1
                    if not ok:
                        summary["packages_unavailable"] = summary.get("packages_unavailable", 0) + 1
                    continue
                fields = []
                if lp.is_active != ok:
                    lp.is_active = ok
                    fields.append("is_active")
                    if not ok:
                        summary["packages_disabled"] += 1
                if update_prices and usd is not None and (lp.source_cost is None or Decimal(lp.source_cost) != raw):
                    lp.source_cost = raw
                    lp.suggested_cost = usd
                    lp.suggested_price = with_margin(usd, margin)
                    fields += ["source_cost", "suggested_cost", "suggested_price"]
                    summary["prices_updated"] += 1
                if fields:
                    lp.save(update_fields=fields)
            for ref, lp in known.items():
                if ref and ref not in live and lp.is_active:
                    lp.is_active = False
                    lp.save(update_fields=["is_active"])
                    summary["packages_disabled"] += 1
        source.last_synced_at = timezone.now()
        source.save(update_fields=["last_synced_at"])
    return {"ok": True, **summary}


# ════════════════ 3. الربط التلقائي عند المتجر ════════════════

def autolink(tenant, games=None) -> dict:
    """
    يربط باقات المتجر المستوردة من مصدرٍ يملكه المتجر مزوّداً.

    - لا يمسّ ربطاً قائماً: ما ربطه صاحب المتجر بيده (أو غيّره) يبقى له.
    - التوجيه: إن لم يكن للباقة مزوّدٌ رئيسي صار هذا المزوّد رئيسيها؛ وإن كان
      لها رئيسيٌّ آخر أُضيف بديلاً في أول خانةٍ فارغة.
    """
    from core import currency
    from providers.models import Provider

    from .models import Game, LibraryGame, Product, ProductLink

    providers = [p for p in Provider.objects.filter(tenant=tenant, status=Provider.Status.ACTIVE)
                 if family((p.config or {}).get("code") or ("zdk" if p.type == Provider.Type.CARD_STORE else "")) in SUPPORTED]
    if not providers:
        return {"linked": 0, "routed": 0, "providers": []}
    by_print: dict[str, list] = {}
    for p in providers:
        by_print.setdefault(provider_fingerprint(p), []).append(p)

    qs = Game.objects.filter(tenant=tenant).exclude(master_library_uuid="")
    if games is not None:
        qs = qs.filter(pk__in=[g.pk for g in games])
    libs = {lg.uuid: lg for lg in LibraryGame.objects.filter(
        uuid__in=qs.values_list("master_library_uuid", flat=True), source__isnull=False,
    ).select_related("source").prefetch_related("products")}

    linked = routed = 0
    used = set()
    with transaction.atomic():
        for game in qs:
            lib = libs.get(game.master_library_uuid)
            if lib is None:
                continue
            matches = by_print.get(fingerprint(lib.source.code, lib.source.config), [])
            if not matches:
                continue
            refs = {lp.kupur: lp for lp in lib.products.all() if lp.source_ref}
            for product in Product.objects.filter(game=game):
                lp = refs.get(product.kupur)
                if lp is None:
                    continue
                for prov in matches:
                    if ProductLink.objects.filter(product=product, provider=prov).exists():
                        continue
                    price = currency.from_provider(tenant, lp.source_cost, prov) if lp.source_cost is not None else None
                    ProductLink.objects.create(
                        tenant=tenant, product=product, provider=prov,
                        package_id=lp.source_ref, package_name=lp.source_name[:200],
                        extra={"auto": True, **({"price": str(price)} if price is not None else {})},
                    )
                    linked += 1
                    used.add(prov.name)
                    chain = [product.provider_id, product.provider_alt1_id, product.provider_alt2_id]
                    if prov.id in chain:
                        continue
                    for field in ("provider", "provider_alt1", "provider_alt2"):
                        if getattr(product, field + "_id") is None:
                            setattr(product, field + "_id", prov.id)
                            fields = [field]
                            if field == "provider":
                                product.execution_type = Product.Execution.AUTO
                                fields.append("execution_type")
                            product.save(update_fields=fields)
                            routed += 1
                            break
    return {"linked": linked, "routed": routed, "providers": sorted(used)}


def matching_provider_names(tenant) -> dict:
    """{بصمة: [أسماء مزوّدي المتجر]} — لعلامة «سيُربط تلقائياً» في تصفّح المكتبة."""
    from providers.models import Provider

    out: dict[str, list] = {}
    for p in Provider.objects.filter(tenant=tenant, status=Provider.Status.ACTIVE):
        out.setdefault(provider_fingerprint(p), []).append(p.name)
    return out
