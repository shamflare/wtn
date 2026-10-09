"""
تنفيذ شحن الخطوط عبر ZNET الرسمي ومتابعته، مع خصم محفظة الوكيل وإرجاعها عند الفشل.

- الإرسال:  servis/tl_servis.php  ⇐ OK|كود|شرح|كلفة   (1 مقبول · 3 مرفوض · 8 يحتاج تحقّقاً)
- المتابعة: servis/tl_kontrol.php ⇐ 1:... نجح · 2:... قيد التنفيذ · 3:... أُلغي

التوجيه كالألعاب: لكل باقة مزوّد رئيسي وبديلان (لوحات ZNET مختلفة)، ولكلٍّ منها
رقم الباقة لديه (KontorPackageLink). الرفض الصريح ينقل إلى البديل التالي.

القرار المالي عند الإنشاء: يُخصم من الوكيل، فإن رفضه كل المزوّدين يُعاد المبلغ.
"""
from decimal import Decimal, InvalidOperation

import requests
from django.db import transaction

from core import services as wallet_services
from core.models import WalletTransaction
from providers.models import Provider

from .models import KontorOrder, KontorPackage
from .services import dealer_price, store_price

CENT = Decimal("0.01")

# رمز فئتنا ⇐ `tip` في tl_servis.php (صيغة ZNET الرسمية، أحرف صغيرة)
TIP_MAP = {"Tam": "tam", "Ses": "ses", "Sms": "sms",
           "3gCep": "3gcep", "3gPc": "3g", "Yds": "yds"}


class KontorOrderError(Exception):
    pass


def znet_provider(tenant):
    for p in Provider.objects.filter(tenant=tenant):
        if ((p.config or {}).get("code") or "").lower() == "znet":
            return p
    return None


def _tip(package: KontorPackage) -> str:
    lt = package.category.line_type if package.category else ""
    return TIP_MAP.get(lt, lt.lower())


def _parse_place(text: str):
    """OK|كود|شرح|كلفة ⇐ (code:int|None, note, cost). code: 1 مقبول · 3 مرفوض · 8 تحقّق."""
    parts = (text or "").strip().split("|")
    if len(parts) < 2 or parts[0].strip().upper() != "OK":
        return None, (text or "").strip()[:280], None
    try:
        code = int(parts[1])
    except ValueError:
        code = None
    note = parts[2].strip() if len(parts) > 2 else ""
    cost = parts[3].strip() if len(parts) > 3 else None
    return code, note, cost


@transaction.atomic
def create_order(dealer, package: KontorPackage, gsm: str, dealer_sell_price=None,
                 client_uuid=None) -> KontorOrder:
    """
    ينشئ الطلب ويخصم المحفظة (قيد الإرسال). لا ينفّذ بعد — يليه execute().
    `dealer_sell_price` (بعملة الدفتر): ما باع به الوكيل لزبونه؛ فارغ ⇐ السعر المقترح.
    """
    if package.tenant_id != dealer.tenant_id:
        raise KontorOrderError("الباقة والوكيل من متجرين مختلفين")
    if package.status != KontorPackage.Status.ACTIVE:
        raise KontorOrderError("الباقة غير متاحة للبيع")
    if dealer.tenant is not None and getattr(dealer.tenant, "purchases_blocked", False):
        raise KontorOrderError("الشراء متوقّف (اشتراك المتجر)")

    from orders.services import big_agent_of
    agent = big_agent_of(dealer)
    from core.currency import LEDGER
    buyer = dealer_price(dealer, package).quantize(LEDGER)                 # ما يدفعه المشتري
    sell = store_price(agent or dealer, package).quantize(CENT)          # ما يقبضه المتجر
    cost = (package.cost_price or Decimal("0")).quantize(CENT)
    # حرّاس المال: بلا كلفة محوّلة (لا سعر صرف) أو بلا سعر أو بسعر دون الكلفة ⇐ لا بيع
    if cost <= 0:
        raise KontorOrderError("الباقة بلا كلفة بعملة المتجر — تواصل مع الإدارة")
    if sell <= 0:
        raise KontorOrderError("الباقة غير مسعّرة بعد — تواصل مع الإدارة")
    if sell < cost:
        raise KontorOrderError("سعر الباقة أقل من كلفتها — أوقف البيع حمايةً من الخسارة")

    if dealer_sell_price in (None, ""):
        retail = (package.recommended_price or Decimal("0")).quantize(CENT)
    else:
        try:
            retail = Decimal(str(dealer_sell_price).replace(",", ".")).quantize(LEDGER)
        except (InvalidOperation, ValueError):
            raise KontorOrderError("سعر البيع غير صالح")
        if retail < 0:
            raise KontorOrderError("سعر البيع لا يصحّ أن يكون سالباً")

    wallet = getattr(dealer, "wallet", None)
    if wallet is None:
        raise KontorOrderError("لا توجد محفظة للوكيل")
    try:
        txn = wallet_services.apply_transaction(
            wallet.id, -buyer, WalletTransaction.Type.ORDER_DEBIT,
            created_by=dealer, note=f"شحن {package.name} ⟵ {gsm}",
        )
    except wallet_services.WalletError as e:
        raise KontorOrderError(str(e))

    # ساقا الوكيل الكبير (كالألعاب): يقبض من دكانه أوّلاً ثم يدفع للمتجر
    if agent is not None:
        agent_wallet = getattr(agent, "wallet", None)
        if agent_wallet is None:
            raise KontorOrderError("لا توجد محفظة للوكيل الكبير")
        try:
            wallet_services.apply_transaction(
                agent_wallet.id, buyer, WalletTransaction.Type.TOPUP,
                created_by=dealer, note=f"بيع {package.name} لـ{dealer.name} ⟵ {gsm}", internal=True,
            )
            wallet_services.apply_transaction(
                agent_wallet.id, -sell, WalletTransaction.Type.ORDER_DEBIT,
                created_by=dealer, note=f"شراء {package.name} من المتجر لـ{dealer.name}",
            )
        except wallet_services.WalletError as e:
            raise KontorOrderError(f"محفظة الوكيل الكبير: {e}")

    order = KontorOrder.objects.create(
        tenant_id=dealer.tenant_id, dealer=dealer, package=package,
        operator=package.operator, gsm=gsm,
        cost_price=cost, sell_price=sell, profit=sell - cost,
        agent=agent, buyer_price=buyer,
        agent_profit=(buyer - sell) if agent else Decimal("0"),
        dealer_sell_price=retail, dealer_profit=retail - buyer, client_uuid=client_uuid,
        status=KontorOrder.Status.PENDING,
        balance_before=txn.balance_before, balance_after=txn.balance_after,
    )
    order.tekil = str(order.id)
    order.save(update_fields=["tekil"])
    txn.ref_type = "kontor_order"; txn.ref_id = order.id
    txn.save(update_fields=["ref_type", "ref_id"])
    from .session_client import forget_offers
    forget_offers(gsm)  # الشحن يغيّر عروض الرقم — لا تُعرض عروض الأمس بعده
    return order


def _refund(order: KontorOrder, note: str):
    wallet = getattr(order.dealer, "wallet", None)
    if wallet is None:
        return
    # الوكيل الكبير أوّلاً: يستردّ من المتجر ثم يردّ لدكانه — والدكان يستردّ ما دفعه هو
    agent_wallet = getattr(order.agent, "wallet", None) if order.agent_id else None
    if agent_wallet is not None:
        for amount, label, internal in ((order.sell_price, "استرداد من المتجر", False),
                                        (-order.buyer_price, "ردّ لدكانه", True)):
            wallet_services.apply_transaction(
                agent_wallet.id, amount,
                WalletTransaction.Type.TOPUP if amount > 0 else WalletTransaction.Type.ORDER_DEBIT,
                note=f"{label} — خط M{order.id}", ref_type="kontor_order", ref_id=order.id,
                allow_below_limit=True, internal=internal,
            )
    wallet_services.apply_transaction(
        wallet.id, order.buyer_price or order.sell_price, WalletTransaction.Type.REFUND,
        created_by=order.dealer, note=note, ref_type="kontor_order", ref_id=order.id,
        allow_below_limit=True,
    )


# ─────────────────────── التوجيه: سلسلة المزوّدين ───────────────────────

def provider_chain(package: KontorPackage) -> list:
    """
    مزوّدو الباقة بالترتيب: الرئيسي ثم API 1 ثم API 2 (كالألعاب)، بلا تكرار
    وبلا معطّل. بلا توجيه على الباقة ⇐ مزوّد ZNET الافتراضي للمتجر (السلوك القديم).
    """
    seen, chain = set(), []
    for p in (package.provider, package.provider_alt1, package.provider_alt2):
        if p is not None and p.id not in seen and p.status == Provider.Status.ACTIVE:
            seen.add(p.id)
            chain.append(p)
    if not chain:
        fallback = znet_provider(package.tenant)
        if fallback is not None:
            chain.append(fallback)
    return chain


def _code_for(package: KontorPackage, provider) -> str | None:
    """
    رقم الباقة لدى هذا المزوّد. بلا ربط ⇐ None فلا يُرسَل إليه — إلا باقة لا ربط
    لها أصلاً (قديمة) فيُرسَل رقم ZNET كما كان قبل التوجيه.
    """
    link = package.links.filter(provider=provider).first()
    if link is not None:
        return link.code
    if not package.links.exists() and not package.is_manual:
        return package.znet_id
    return None


# نتائج محاولة الإرسال إلى مزوّد واحد
SENT, REJECTED, UNKNOWN = "sent", "rejected", "unknown"


def _send(order: KontorOrder, provider) -> tuple[str, str]:
    """
    يرسل الطلب إلى مزوّد واحد ⇐ (النتيجة، الملاحظة).

    REJECTED آمنٌ للانتقال إلى البديل: رفضٌ صريح، أو لم يغادر الطلب أصلاً
    (تعذّر الاتصال). أمّا UNKNOWN (انقطع الردّ بعد الإرسال) فقد يكون نُفّذ —
    فلا بديل ولا إرجاع، بل متابعة بـ tl_kontrol حتى يُحسم. هكذا لا يُشحن رقمٌ مرّتين.
    """
    from .services import provider_creds
    creds = provider_creds(provider)
    if not creds:
        return REJECTED, "إعداد ناقص"
    code = _code_for(order.package, provider)
    if not code:
        return REJECTED, "الباقة غير مربوطة لديه"
    base, kod, sifre = creds
    params = {
        "bayi_kodu": kod, "sifre": sifre,
        "operator": order.operator, "tip": _tip(order.package),
        "kontor": code, "gsmno": order.gsm, "tekilnumara": order.tekil,
    }
    try:
        resp = requests.get(f"{base.rstrip('/')}/servis/tl_servis.php", params=params, timeout=(5, 40))
    except requests.RequestException as e:
        if _never_sent(e):
            return REJECTED, "تعذّر الاتصال"
        return UNKNOWN, "انقطع الردّ بعد الإرسال — يُتابَع"
    status, note, _cost = _parse_place(resp.text)
    if status in (1, 8):  # 8: أُرسل سابقاً بنفس المعرّف — يُتحقَّق بالمتابعة
        return SENT, note
    return REJECTED, note[:280]


def _never_sent(e: Exception) -> bool:
    """
    هل فشل الاتصال **قبل** أن يصل الطلب إلى المزوّد؟ (مهلة الاتصال، اسم لا يُحَلّ،
    اتصال مرفوض). وحدها تُجيز الانتقال إلى البديل. أمّا انقطاع بعد الإرسال
    (مهلة القراءة، إغلاق الخادم للاتصال) فقد يكون نُفّذ — فيُتابَع لا يُعاد.
    """
    if isinstance(e, requests.ConnectTimeout):
        return True
    if isinstance(e, requests.ConnectionError):
        text = str(e)
        return any(k in text for k in ("NewConnectionError", "Failed to establish",
                                        "NameResolutionError", "Name or service not known",
                                        "getaddrinfo failed", "Connection refused"))
    return False


def _adopt(order: KontorOrder, provider, note: str):
    """الطلب صار عند هذا المزوّد: نسجّله وكلفته الفعلية لديه (إن عُرفت)."""
    from core import currency
    order.provider = provider
    order.status = KontorOrder.Status.PROCESSING
    order.provider_note = note[:300]
    link = order.package.links.filter(provider=provider).first()
    if link is not None and link.cost:
        real = currency.from_provider(order.tenant, link.cost, provider)
        if real:
            order.cost_price = real
            order.profit = order.sell_price - real
    order.save(update_fields=["provider", "status", "provider_note", "cost_price", "profit", "updated_at"])


def _try_chain(order: KontorOrder, chain: list, trail: list) -> bool:
    """
    يجرّب المزوّدين بالترتيب. True إن التقطه أحدهم (أُرسل أو حالته مجهولة فتُتابَع).
    `trail` يجمع (اسم المزوّد، رسالته) لكل رفض.
    """
    for prov in chain:
        result, note = _send(order, prov)
        if result in (SENT, UNKNOWN):
            _adopt(order, prov, note)
            return True
        trail.append((prov.name, note))
    return False


def _fail_and_refund(order: KontorOrder, trail: list, why: str):
    """
    الوكيل يقرأ رسالة **آخر** مزوّد رفض كما كتبها (سبب الإلغاء) بلا اسمه؛
    والمسار كاملاً بالأسماء في `trace` لصاحب المتجر.
    """
    order.status = KontorOrder.Status.FAILED
    order.provider_note = ((trail[-1][1] if trail else "") or why)[:300]
    order.trace = (" | ".join(f"{name}: {note}" for name, note in trail) or why)[:500]
    order.save(update_fields=["status", "provider_note", "trace", "updated_at"])
    _refund(order, f"إرجاع — {why}: {order.provider_note[:120]} (طلب #{order.id})")
    order.status = KontorOrder.Status.REFUNDED
    order.save(update_fields=["status", "updated_at"])


def execute(order: KontorOrder) -> KontorOrder:
    """
    يرسل الطلب عبر سلسلة مزوّدي الباقة (الرئيسي ثم البدائل). يُرجع المال فوراً
    إن رفضه الجميع صراحةً — ولا يُرجعه ما دام أحدهم قد يكون نفّذه.
    """
    chain = provider_chain(order.package)
    if not chain:
        _fail_and_refund(order, [], "لا مزوّد خطوط مُعدّ")
        return order
    trail: list = []
    if not _try_chain(order, chain, trail):
        _fail_and_refund(order, trail, "رفضه كل المزوّدين")
    return order


def _parse_status(text: str):
    """
    1:شرح:مبلغ=نجح · 2:شرح:مبلغ=قيد التنفيذ · 3:سبب=أُلغي ⇐ (code:int|None, note).
    المبلغ في آخر الردّ ليس من الملاحظة فيُنزع؛ والشرح نفسه قد يحوي `:` فيبقى كاملاً.
    """
    s = (text or "").strip()
    if not s or ":" not in s:
        return None, s[:280]
    head, _, rest = s.partition(":")
    try:
        code = int(head)
    except ValueError:
        return None, s[:280]
    body, sep, tail = rest.rpartition(":")
    if sep and _is_amount(tail):
        rest = body
    return code, rest.strip()


def _is_amount(s: str) -> bool:
    try:
        Decimal(s.strip().replace(",", "."))
        return True
    except (InvalidOperation, ValueError):
        return False


def poll(order: KontorOrder) -> KontorOrder:
    """
    يتابع طلباً قيد التنفيذ لدى **مزوّده هو**. إن ألغاه المزوّد: تُجرَّب بقيّة
    السلسلة **من بعده** (لا من رأسها، فلا يُعاد إلى من رفض)، وإلا يُرجع المال.
    """
    from .services import provider_creds
    if order.status != KontorOrder.Status.PROCESSING:
        return order
    prov = order.provider or znet_provider(order.tenant)
    creds = provider_creds(prov)
    if not creds:
        return order
    base, kod, sifre = creds
    try:
        resp = requests.get(f"{base.rstrip('/')}/servis/tl_kontrol.php",
                            params={"bayi_kodu": kod, "sifre": sifre, "tekilnumara": order.tekil},
                            timeout=(5, 40))
        code, note = _parse_status(resp.text)
    except requests.RequestException:
        return order

    if code == 1:
        order.status = KontorOrder.Status.SUCCESS
        order.provider_note = note[:300]
        order.save(update_fields=["status", "provider_note", "updated_at"])
    elif code == 2:
        # ما زال قيد التنفيذ — لكن قد يكتب مسؤول المزوّد ملاحظةً قبل الحسم
        if note and note != order.provider_note:
            order.provider_note = note[:300]
            order.save(update_fields=["provider_note", "updated_at"])
    elif code == 3:
        trail = [(prov.name, note[:280])]
        chain = provider_chain(order.package) if order.package_id else []  # باقة محذوفة ⇐ لا بديل
        ids = [p.id for p in chain]
        rest = chain[ids.index(prov.id) + 1:] if prov.id in ids else [p for p in chain if p.id != prov.id]
        if not _try_chain(order, rest, trail):
            _fail_and_refund(order, trail, "ألغاه المزوّد ولا بديل")
    return order


def poll_all_processing(limit: int = 200) -> int:
    """يتابع كل طلبات الخطوط «قيد التنفيذ» (لمهمّة sync الدورية). يعيد عدد المتغيّر."""
    changed = 0
    qs = KontorOrder.objects.filter(status=KontorOrder.Status.PROCESSING).select_related("package", "dealer")[:limit]
    for o in qs:
        before = o.status
        try:
            poll(o)
        except Exception:  # noqa: BLE001 — طلبٌ واحد لا يُسقط الدورة
            continue
        if o.status != before:
            changed += 1
    return changed
