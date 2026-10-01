"""
اقتراحات «ربط تلقائي» لعمود مزوّدٍ واحد في «ربط الباقات» — لا تُحفظ إلا بموافقة.

طريقان، كلٌّ بدرجة ثقته:

- **مؤكَّد (exact):** باقةٌ مستوردة من المكتبة، ومصدرها هو هذا المزوّد نفسه
  (البصمة) — رقمها لديه محفوظٌ في المكتبة. لا تخمين فيه.
- **مطابقة بالاسم (smart):** لمزوّدٍ أرقامه غير أرقامنا (ZNET). تُقارن اللعبة
  بالاسم، والباقة بالرقم (60 ↔ 60) والوحدة (UC ↔ UC)، ثم السعر بسعرٍ مرجعيّ
  نعرفه (ربطٌ قائم بمزوّدٍ آخر، أو تكلفة الباقة). وهذا تخمين، فدرجته:
    · high  — اللعبة مطابقة بلا لبس + الرقم + الوحدة + سعرٌ متقارب ⇒ يُحدَّد مسبقاً
    · medium — شرطٌ ناقص (سعرٌ بعيد أو مجهول، أو اسمٌ غير مطابقٍ تماماً) ⇒ لا يُحدَّد
  والوحدة المختلفة رفضٌ قاطع: 60 UC لا تقابل 60 BC أبداً.
"""
import re
from decimal import Decimal, InvalidOperation

from django.db import transaction

# كلماتٌ لا تميّز لعبةً عن أخرى — تُسقط قبل المقارنة. وتبقى «lite» و«epin» و«manual»
# لأنها تفرّق فعلاً (PUBG Lite لعبةٌ أخرى، وEpin أكوادٌ لا شحنٌ مباشر).
_FILLER = {"mobile", "global", "the", "official", "game", "app", "online", "live", "chat"}

# وحدات العملات داخل الألعاب، وما يرادفها
_UNITS = {
    "uc": "uc", "bc": "bc", "cp": "cp", "gold": "gold", "golds": "gold",
    "diamond": "diamond", "diamonds": "diamond", "elmas": "diamond", "dm": "diamond",
    "coin": "coin", "coins": "coin", "gem": "gem", "gems": "gem",
    "crystal": "crystal", "crystals": "crystal", "token": "token", "tokens": "token",
    "point": "point", "points": "point", "star": "star", "stars": "star",
}

PRICE_OK = (Decimal("0.75"), Decimal("1.33"))


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z؀-ۿ]+|\d+", (text or "").lower())


def game_tokens(name: str) -> set[str]:
    return {w for w in _words(name) if not w.isdigit() and w not in _FILLER} or set(_words(name))


def game_score(a: str, b: str) -> float:
    ta, tb = game_tokens(a), game_tokens(b)
    if not ta or not tb:
        return 0.0
    if ta == tb:
        return 1.0
    return len(ta & tb) / len(ta | tb)


def numbers(text: str) -> set[int]:
    """الأرقام في الاسم: «1.000 Diamond» و«1,000» و«1000» كلّها ألف."""
    t = re.sub(r"(?<=\d)[.,](?=\d{3}\b)", "", text or "")
    return {int(n) for n in re.findall(r"\d+", t) if len(n) < 10}


def units(text: str) -> set[str]:
    return {_UNITS[w] for w in _words(text) if w in _UNITS}


def _dec(v):
    try:
        return Decimal(str(v).replace(",", ".")) if v not in (None, "") else None
    except (InvalidOperation, ValueError):
        return None


def suggest(tenant, provider) -> dict:
    """اقتراحات الربط لمزوّدٍ واحد — لباقاتٍ غير مربوطة به بعد."""
    from core import currency
    from providers.adapters.registry import adapter_for

    from .library_sources import fingerprint, provider_fingerprint
    from .models import LibraryGame, Product, ProductLink

    products = list(Product.objects.filter(tenant=tenant).select_related("game")
                    .order_by("game__sort_order", "sort_order", "id"))
    linked_here = set(ProductLink.objects.filter(tenant=tenant, provider=provider)
                      .values_list("product_id", flat=True))
    todo = [p for p in products if p.id not in linked_here]

    # السعر المرجعي لكل باقة: أرخص سعرٍ معروف لدى مزوّدٍ آخر، وإلا تكلفتها
    ref_price: dict[int, Decimal] = {}
    for l in ProductLink.objects.filter(tenant=tenant).exclude(provider=provider):
        price = _dec((l.extra or {}).get("price"))
        if price and price > 0 and (l.product_id not in ref_price or price < ref_price[l.product_id]):
            ref_price[l.product_id] = price

    out, unmatched = [], []
    exact_done = set()

    # (١) المؤكَّد: من المكتبة، والمصدر هو هذا المزوّد نفسه
    my_print = provider_fingerprint(provider)
    lib_by_uuid = {lg.uuid: lg for lg in LibraryGame.objects.filter(
        uuid__in={p.game.master_library_uuid for p in todo if p.game.master_library_uuid},
        source__isnull=False).select_related("source").prefetch_related("products")}
    for p in todo:
        lg = lib_by_uuid.get(p.game.master_library_uuid)
        if lg is None or fingerprint(lg.source.code, lg.source.config) != my_print:
            continue
        lp = next((x for x in lg.products.all() if x.kupur == p.kupur and x.source_ref), None)
        if lp is None:
            continue
        price = currency.from_provider(tenant, lp.source_cost, provider) if lp.source_cost is not None else None
        out.append({
            "product": p.id, "product_name": p.name, "game_name": p.game.name,
            "package": {"id": lp.source_ref, "name": lp.source_name, "game": lg.source_key, "kupur": "",
                        "price": str(lp.source_cost) if lp.source_cost is not None else ""},
            "price_base": str(price) if price is not None else None,
            "ref_price": str(ref_price[p.id]) if p.id in ref_price else None,
            "confidence": "exact", "reasons": ["رقمها لدى المزوّد محفوظٌ في المكتبة"],
        })
        exact_done.add(p.id)

    rest = [p for p in todo if p.id not in exact_done]
    if not rest:
        return {"ok": True, "suggestions": out, "unmatched": []}

    # (٢) بالاسم: كتالوج المزوّد مرّةً واحدة
    adapter = adapter_for(provider)
    if adapter is None:
        return {"ok": True, "suggestions": out, "unmatched": [], "note": "منفّذٌ يدوي — لا كتالوج يُطابَق"}
    cat = adapter.list_packages(provider.config or {}, provider=provider)
    if not cat.ok:
        if out:
            return {"ok": True, "suggestions": out, "unmatched": [], "note": cat.note}
        return {"ok": False, "detail": cat.note or "تعذّر جلب كتالوج المزوّد"}

    by_game: dict[str, list] = {}
    for pk in cat.packages:
        by_game.setdefault(pk.get("game") or "", []).append(pk)

    taken: set[tuple] = set()   # باقة المزوّد لا تُقترح لباقتين
    game_cache: dict[str, list] = {}
    for p in rest:
        gname = p.game.name
        if p.is_amount:
            # «بالكمية» لا يُطابَق بالرقم في الاسم — رقمها حدودٌ لا باقة
            unmatched.append({"product": p.id, "product_name": p.name, "game_name": gname,
                              "why": "باقةٌ بالكمية — تُربط بيدك من الجدول"})
            continue
        if gname not in game_cache:
            scored = sorted(((game_score(gname, g), g) for g in by_game), reverse=True)
            game_cache[gname] = [(s, g) for s, g in scored if s >= 0.5][:3]
        cands = game_cache[gname]
        want_n = numbers(p.name)
        want_u = units(p.name)
        best = None
        for score, g in cands:
            for pk in by_game[g]:
                have_n = numbers(pk.get("name") or "") | ({int(pk["kupur"])} if str(pk.get("kupur") or "").isdigit() else set())
                if not want_n or not (max(want_n) in have_n):
                    continue
                have_u = units(pk.get("name") or "")
                if want_u and have_u and not (want_u & have_u):
                    continue   # وحدةٌ مختلفة: رفضٌ قاطع
                key = (str(pk.get("id")), str(pk.get("kupur") or ""))
                if key in taken:
                    continue
                if best is None or score > best[0]:
                    best = (score, g, pk, key)
            if best:
                break   # أعلى لعبةٍ فيها مطابقة تكفي
        if best is None:
            unmatched.append({"product": p.id, "product_name": p.name, "game_name": gname,
                              "why": "لا لعبة مشابهة لدى المزوّد" if not cands else "لا باقة بالرقم نفسه"})
            continue
        score, g, pk, key = best
        taken.add(key)
        price = currency.from_provider(tenant, pk.get("price"), provider) if pk.get("price") else None
        ref = ref_price.get(p.id) or (p.cost_price if p.cost_price and p.cost_price > 0 else None)

        reasons, warnings = [], []
        reasons.append(f"الرقم {max(want_n)}")
        if want_u and units(pk.get("name") or ""):
            reasons.append("الوحدة نفسها")
        ambiguous = len(cands) > 1 and cands[1][0] >= cands[0][0] - 0.15
        if score >= 0.999:
            reasons.append("اسم اللعبة مطابق")
        else:
            warnings.append(f"اللعبة عنده «{g}» — ليست مطابقةً تماماً لـ«{gname}»")
        if ambiguous:
            warnings.append("أكثر من لعبةٍ مشابهة لديه")
        price_ok = None
        if price is not None and ref:
            ratio = price / ref
            price_ok = PRICE_OK[0] <= ratio <= PRICE_OK[1]
            pct = int(round((ratio - 1) * 100))
            (reasons if price_ok else warnings).append(
                f"السعر {'متقارب' if price_ok else 'بعيد'} ({'+' if pct >= 0 else ''}{pct}% عن المرجع)")
        else:
            warnings.append("لا سعر مرجعيّ للمقارنة")
        high = score >= 0.999 and not ambiguous and price_ok is True
        out.append({
            "product": p.id, "product_name": p.name, "game_name": gname,
            "package": {"id": str(pk.get("id") or ""), "name": pk.get("name") or "", "game": g,
                        "kupur": str(pk.get("kupur") or ""), "price": str(pk.get("price") or "")},
            "price_base": str(price) if price is not None else None,
            "ref_price": str(ref) if ref else None,
            "confidence": "high" if high else "medium", "reasons": reasons, "warnings": warnings,
        })
    return {"ok": True, "suggestions": out, "unmatched": unmatched}


def apply_links(tenant, provider, picks: list) -> dict:
    """
    يحفظ ما وافق عليه صاحب المتجر: [{product, package_id, kupur?, name?, price?}].
    لا يمسّ ربطاً قائماً، ويضبط التوجيه كالربط التلقائي (رئيسيٌّ إن خلا، وإلا بديل).
    """
    from core import currency

    from .models import Product, ProductLink

    linked = routed = 0
    with transaction.atomic():
        for pick in picks:
            product = Product.objects.filter(tenant=tenant, pk=pick.get("product")).first()
            pid = str(pick.get("package_id") or "").strip()
            if product is None or not pid:
                continue
            if ProductLink.objects.filter(product=product, provider=provider).exists():
                continue
            extra = {"auto": True}
            if pick.get("kupur"):
                extra["kupur"] = str(pick["kupur"])
            price = currency.from_provider(tenant, pick.get("price"), provider) if pick.get("price") not in (None, "") else None
            if price is not None:
                extra["price"] = str(price)
            ProductLink.objects.create(tenant=tenant, product=product, provider=provider, package_id=pid,
                                       package_name=str(pick.get("name") or "")[:200], extra=extra)
            linked += 1
            if provider.id in (product.provider_id, product.provider_alt1_id, product.provider_alt2_id):
                continue
            for field in ("provider", "provider_alt1", "provider_alt2"):
                if getattr(product, field + "_id") is None:
                    setattr(product, field + "_id", provider.id)
                    fields = [field]
                    if field == "provider":
                        product.execution_type = Product.Execution.AUTO
                        fields.append("execution_type")
                    product.save(update_fields=fields)
                    routed += 1
                    break
    return {"linked": linked, "routed": routed}
