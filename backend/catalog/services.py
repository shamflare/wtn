"""
قواعد التسعير: ربط سعر مجموعة الأسعار بتكلفة الباقة.

التسعير الجماعي لا يكتب رقماً ويمضي — يحفظ **قاعدة** (نسبة أو مبلغ فوق
التكلفة) تبقى نافذة. فمتى تغيّرت التكلفة تبعها السعر تلقائياً، من أي طريق
تغيّرت: تحرير الخلية، أو «تحديث التكاليف» من مزوّد، أو تحويل عملة الدفتر.

ولأن الطرق كثيرة وستزيد، إعادة الحساب معلّقة على **حفظ الباقة نفسها**
(إشارة `post_save`) لا على كل نقطة استدعاء — فلا تفلت واحدة منها.
"""
from decimal import ROUND_CEILING, Decimal

from core.currency import CENT

HUNDRED = Decimal("100")


def price_from_margin(cost: Decimal, mode: str, value: Decimal, round_up: bool = False,
                      quantum: Decimal = CENT):
    """
    السعر الناتج عن قاعدة، أو None إن تعذّر.

    تكلفة صفر لا تُسعَّر: النسبة عليها تعطي صفراً — أي بيعاً مجّانياً بلا أن
    ينتبه أحد. وسعرٌ سالب يُرفض كذلك.

    `round_up` يرفع الناتج إلى أقرب **نصف** فوقه: 0.94 ⇐ 1، 1.01…1.50 ⇐ 1.50،
    1.51…2.00 ⇐ 2. لأعلى لا للأقرب: التقريب للأقرب ينزل بالسعر أحياناً تحت التكلفة.
    """
    if cost is None or cost <= 0 or value is None:
        return None
    price = (
        cost * (Decimal("1") + Decimal(value) / HUNDRED) if mode == "percent"
        else cost + Decimal(value)
    ).quantize(quantum)
    if round_up:
        price = ((price * 2).to_integral_value(rounding=ROUND_CEILING) / 2).quantize(CENT)
    return price if price >= 0 else None


def agent_row_price(row, cost: Decimal, round_ok: bool = True) -> Decimal:
    """
    سعر خلية الوكيل الكبير الفعلي الآن: قاعدتها على تكلفته الحالية إن كانت
    مرتبطة، وإلا الرقم المكتوب. ولا ينزل تحت التكلفة — لا بيع بخسارة صامتة.
    """
    from core.currency import LEDGER
    price = row.price
    if row.margin_mode and row.margin_value is not None:
        price = price_from_margin(cost, row.margin_mode, row.margin_value,
                                  round_ok and row.margin_round, LEDGER) or price
    return max(Decimal(price).quantize(LEDGER), Decimal(cost).quantize(LEDGER))


def rounds(product, round_up: bool) -> bool:
    """
    التقريب لا يمسّ باقات «بالكمية»: سعرها مخزّن لكتلة (مثلاً 2.00 لكل 1000)،
    وتقريبه إلى نصف يغيّر سعر الوحدة بنسبة كبيرة بلا أن يظهر ذلك.
    """
    return round_up and not product.is_amount


def catalog_index(packages) -> dict:
    """
    فهرس كتالوج المزوّد بمفتاح **(المعرّف، الكوبون)** معاً.

    المعرّف وحده لا يميّز الباقة: زينت يرقّم به **اللعبة** (`oyun_bilgi_id`)،
    فباقات ببجي كلّها معرّفها `1` ويميّزها `kupur`. المطابقة به وحده تُلصق
    سعر أوّل باقة في اللعبة بكل باقاتها.
    """
    index = {}
    for p in packages:
        pid = str(p.get("id") or "").strip()
        if not pid:
            continue
        index[(pid, str(p.get("kupur") or "").strip())] = p
    return index


def catalog_match(index: dict, link):
    """
    باقة الرابط في الفهرس: (المطابقة، سبب الإخفاق).

    الرابط اليدويّ قد يكون بلا كوبون. حينها نقبل المطابقة **إن لم يكن في
    الكتالوج إلا باقة واحدة بهذا المعرّف**؛ فإن تعدّدت فالأمر ملتبس ونمتنع —
    التخمين هنا يكتب سعر باقة على أخرى بلا أن ينتبه أحد.
    """
    pid = str(link.package_id).strip()
    kupur = str((link.extra or {}).get("kupur") or "").strip()

    found = index.get((pid, kupur))
    if found is not None:
        return found, ""

    same_id = [v for (k_id, _), v in index.items() if k_id == pid]
    if not same_id:
        return None, "لا وجود لها في كتالوج المزوّد"
    if kupur:
        return None, f"الكوبون {kupur} غير موجود لدى المزوّد"
    if len(same_id) > 1:
        return None, f"أكثر من باقة بالرقم {pid} — حدّد الكوبون في «ربط الباقات»"
    return same_id[0], ""


def rank_providers(product, links, providers_by_id) -> list:
    """
    ترتيب مزوّدي الباقة للتوجيه التلقائي: **الأرخص أولاً**.

    ثلاث طبقات، والترتيب داخل كلٍّ منها بالسعر تصاعدياً:

    1. **رابح** — سعره معروف ولا يتجاوز سعر بيعنا.
    2. **مجهول السعر** — رابط بلا سعر مرجعي بعد. يأتي بعد الرابحين لأنه لا
       يُرتَّب، ولا يُستبعَد لأنه ملاذ صالح والنظام يتعلّم سعره من أول طلب.
    3. **خاسر** — سعره يتجاوز سعر بيعنا. يبقى ملاذاً أخيراً لا يُستبعَد:
       حماية الخسارة تمنعه وقت الإرسال، وإن رفع المالك سعر بيعه غداً صار
       صالحاً بلا إعادة توجيه.

    يُعيد قائمة قواميس مرتّبة، كلٌّ منها يحمل المزوّد وسعره وسبب طبقته.
    """
    sell = product.recommended_price or Decimal("0")
    ranked = []
    for link in links:
        provider = providers_by_id.get(link.provider_id)
        if provider is None:
            continue
        raw = (link.extra or {}).get("price")
        price = None
        if raw not in (None, ""):
            try:
                price = Decimal(str(raw).replace(",", "."))
            except Exception:
                price = None

        if price is None:
            tier, sort_key = 1, Decimal("0")
        elif sell > 0 and price > sell:
            tier, sort_key = 2, price
        else:
            tier, sort_key = 0, price

        ranked.append({
            "provider": provider,
            "price": price,
            "tier": tier,
            # المزوّد الأقدم يتقدّم عند تساوي السعر — ترتيب ثابت لا عشوائي
            "_sort": (tier, sort_key, provider.sort_order, provider.id),
        })

    ranked.sort(key=lambda r: r["_sort"])
    return ranked


def apply_margin_rules(product) -> int:
    """
    يعيد حساب أسعار المجموعات المرتبطة بقاعدة لهذه الباقة.

    يُعيد عدد الأسعار التي تغيّرت فعلاً. الأسعار اليدوية (بلا قاعدة) لا تُمَسّ.
    """
    from .models import ProductPrice

    rows = ProductPrice.objects.filter(product=product).exclude(margin_mode="")
    changed = 0
    for row in rows:
        price = price_from_margin(product.cost_price, row.margin_mode, row.margin_value,
                                  rounds(product, row.margin_round))
        if price is None or price == row.price:
            continue
        row.price = price
        row.save(update_fields=["price"])
        changed += 1
    return changed
