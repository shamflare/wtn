"""
تنفيذ شحن الخطوط عبر ZNET الرسمي ومتابعته، مع خصم محفظة الوكيل وإرجاعها عند الفشل.

- الإرسال:  servis/tl_servis.php  ⇐ OK|كود|شرح|كلفة   (1 مقبول · 3 مرفوض · 8 يحتاج تحقّقاً)
- المتابعة: servis/tl_kontrol.php ⇐ 1:... نجح · 2:... قيد التنفيذ · 3:... أُلغي

القرار المالي عند الإنشاء: يُخصم من الوكيل، فإن رفض ZNET فوراً يُعاد المبلغ.
"""
from decimal import Decimal, InvalidOperation

import requests
from django.db import transaction

from core import services as wallet_services
from core.models import WalletTransaction
from providers.models import Provider

from .models import KontorOrder, KontorPackage
from .services import dealer_price

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

    sell = dealer_price(dealer, package).quantize(CENT)
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
            retail = Decimal(str(dealer_sell_price).replace(",", ".")).quantize(CENT)
        except (InvalidOperation, ValueError):
            raise KontorOrderError("سعر البيع غير صالح")
        if retail < 0:
            raise KontorOrderError("سعر البيع لا يصحّ أن يكون سالباً")

    wallet = getattr(dealer, "wallet", None)
    if wallet is None:
        raise KontorOrderError("لا توجد محفظة للوكيل")
    try:
        txn = wallet_services.apply_transaction(
            wallet.id, -sell, WalletTransaction.Type.ORDER_DEBIT,
            created_by=dealer, note=f"شحن {package.name} ⟵ {gsm}",
        )
    except wallet_services.WalletError as e:
        raise KontorOrderError(str(e))

    order = KontorOrder.objects.create(
        tenant_id=dealer.tenant_id, dealer=dealer, package=package,
        operator=package.operator, gsm=gsm,
        cost_price=cost, sell_price=sell, profit=sell - cost,
        dealer_sell_price=retail, dealer_profit=retail - sell, client_uuid=client_uuid,
        status=KontorOrder.Status.PENDING,
        balance_before=txn.balance_before, balance_after=txn.balance_after,
    )
    order.tekil = str(order.id)
    order.save(update_fields=["tekil"])
    txn.ref_type = "kontor_order"; txn.ref_id = order.id
    txn.save(update_fields=["ref_type", "ref_id"])
    return order


def _refund(order: KontorOrder, note: str):
    wallet = getattr(order.dealer, "wallet", None)
    if wallet is None:
        return
    wallet_services.apply_transaction(
        wallet.id, order.sell_price, WalletTransaction.Type.REFUND,
        created_by=order.dealer, note=note, ref_type="kontor_order", ref_id=order.id,
        allow_below_limit=True,
    )


def execute(order: KontorOrder) -> KontorOrder:
    """يرسل الطلب إلى ZNET. يُرجع المال فوراً عند الرفض (3) أو خطأ الاتصال."""
    prov = znet_provider(order.tenant)
    cfg = (prov.config if prov else {}) or {}
    base, kod, sifre = cfg.get("base_url"), cfg.get("kod"), cfg.get("sifre")
    if not (base and kod and sifre):
        order.status = KontorOrder.Status.FAILED
        order.provider_note = "إعداد ZNET ناقص"
        order.save(update_fields=["status", "provider_note", "updated_at"])
        _refund(order, f"إرجاع — إعداد ZNET ناقص (طلب #{order.id})")
        order.status = KontorOrder.Status.REFUNDED
        order.save(update_fields=["status", "updated_at"])
        return order

    order.provider = prov
    params = {
        "bayi_kodu": kod, "sifre": sifre,
        "operator": order.operator, "tip": _tip(order.package),
        "kontor": order.package.znet_id, "gsmno": order.gsm, "tekilnumara": order.tekil,
    }
    try:
        resp = requests.get(f"{base.rstrip('/')}/servis/tl_servis.php", params=params, timeout=(5, 40))
        code, note, _cost = _parse_place(resp.text)
    except requests.RequestException as e:
        code, note = None, f"تعذّر الاتصال: {e}"

    order.provider_note = note[:300]
    if code == 1:
        order.status = KontorOrder.Status.PROCESSING
    elif code == 8:
        order.status = KontorOrder.Status.PROCESSING  # أُرسل سابقاً — يُتحقّق بالمتابعة
    else:  # 3 أو خطأ ⇐ رفض فوري ⇐ إرجاع
        order.status = KontorOrder.Status.FAILED
        order.save(update_fields=["status", "provider", "provider_note", "updated_at"])
        _refund(order, f"إرجاع — رفض ZNET: {note[:120]} (طلب #{order.id})")
        order.status = KontorOrder.Status.REFUNDED
        order.save(update_fields=["status", "updated_at"])
        return order
    order.save(update_fields=["status", "provider", "provider_note", "updated_at"])
    return order


def _parse_status(text: str):
    """1:...=نجح · 2:...=قيد التنفيذ · 3:...=أُلغي ⇐ (code:int|None, note)."""
    s = (text or "").strip()
    if not s or ":" not in s:
        return None, s[:280]
    head, _, rest = s.partition(":")
    try:
        return int(head), rest.strip()
    except ValueError:
        return None, s[:280]


def poll(order: KontorOrder) -> KontorOrder:
    """يتابع حالة طلبٍ قيد التنفيذ، ويُرجع المال إن أُلغي."""
    if order.status != KontorOrder.Status.PROCESSING:
        return order
    prov = znet_provider(order.tenant)
    cfg = (prov.config if prov else {}) or {}
    base, kod, sifre = cfg.get("base_url"), cfg.get("kod"), cfg.get("sifre")
    if not (base and kod and sifre):
        return order
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
    elif code == 3:
        order.provider_note = note[:300]
        order.save(update_fields=["provider_note", "updated_at"])
        _refund(order, f"إرجاع — ألغى ZNET: {note[:120]} (طلب #{order.id})")
        order.status = KontorOrder.Status.REFUNDED
        order.save(update_fields=["status", "updated_at"])
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
