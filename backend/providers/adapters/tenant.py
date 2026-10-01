"""محوّل "نفس النظام" الداخلي: متجر يشتري من متجر آخر على منصّتنا.

الربط: صاحب المتجر (أ) يملك حساب وكيل (bayi) لدى المتجر المورّد (ب).
config = {"dealer_login": "..."} — رقم دخول حسابه هناك.
provider_package_id على المنتج = رقم منتج المورّد (ب).

عند الطلب: يُنشأ طلب حقيقي داخل متجر (ب) باسم ذلك الوكيل (يخصم محفظته هناك)،
ويُنفَّذ لدى (ب) بتوجيهات (ب) نفسها (بنك بيناته أو مزوّده الخارجي...)،
ويعود الـ PIN إلى طلبنا. أي سلسلة توريد كاملة داخل المنصّة.

**الإذن شرطٌ لا خيار:** رقم الدخول فريد عبر المنصّة كلّها وسهل التخمين
(`bayi003`)، فلولا `internal_supply_allowed` لاستطاع أيّ صاحب متجر أن يوجّه
طلباته إلى محفظة وكيلٍ ليس له فينفق رصيده. الإذن يضعه صاحب المتجر المورّد
بيده على الحساب الذي فتحه لهذا الغرض — لا يُشترى ولا يُخمَّن.
"""
from decimal import Decimal

from .base import BalanceResult, BaseAdapter, ExecutionResult, PackageList

# مرجع الطلب لدى المورّد: "tenant:<subdomain>:<رقم الفيش>" — منه تعرف حلقة
# المراقبة أيّ طلبٍ تسأل عنه في أيّ متجر.
REF_PREFIX = "tenant:"


def _to_our_base(buyer_tenant, supplier_tenant, amount):
    """
    من عملة دفتر المورّد إلى عملة دفترنا. None = لا سعر صرف مضبوط.

    المتجران قد يمسكان دفترين بعملتين مختلفتين، وكل رقم يعبر بيننا يجب أن
    يُحوَّل عند الحدّ — وإلّا دخل دفترَنا رقمٌ بعملة غيرنا.
    """
    from core import currency

    if amount is None:
        return None
    src = currency.base_currency(supplier_tenant)
    if src == currency.base_currency(buyer_tenant):
        return amount
    rate = currency.rate_of(buyer_tenant, src)
    if rate <= 0:
        return None
    return (Decimal(str(amount)) / rate).quantize(currency.CENT)


def _supplier_product(order, dealer, provider):
    """
    منتج المورّد المرتبط بهذه الباقة — أو None إن كان الربط ناقصاً/خاطئاً.

    `provider` صريحٌ لا `order.provider`: السلسلة قد تُجرّب البديل الأوّل أو
    الثاني، ولكلٍّ رقمُ ربطه. قراءةُ ربط الرئيسي كانت تسأل عن منتجٍ آخر.
    """
    from catalog.models import Product

    try:
        package_id, _extra = BaseAdapter.link_for(order, provider)
        pid = int(package_id)
    except (TypeError, ValueError):
        return None
    return Product.objects.filter(pk=pid, tenant=dealer.tenant).select_related("game").first()


def _resolve_dealer(config: dict, buyer_tenant_id=None):
    """يعيد (الوكيل، سبب الرفض). الوكيل None ⇒ الرفض مشروح بالعربية."""
    from core.models import User

    login = ((config or {}).get("dealer_login") or "").strip()
    if not login:
        return None, "إعداد ناقص: dealer_login (رقم دخول حسابنا لدى المورّد)"
    dealer = (
        User.objects.filter(login_id=login, role=User.Role.BAYI)
        .select_related("wallet", "tenant").first()
    )
    if dealer is None:
        return None, f"حساب الوكيل '{login}' غير موجود لدى المورّد"
    # الرفض واحد في الحالتين — كي لا يكشف الردّ للمخمّن أن الرقم صحيح
    if not dealer.internal_supply_allowed:
        return None, (
            f"حساب '{login}' غير مأذون له بالتوجيه الداخلي. "
            "على صاحب المتجر المورّد تفعيل «مأذون بالتوجيه الداخلي» "
            "من إعدادات ذلك الوكيل."
        )
    if buyer_tenant_id is not None and dealer.tenant_id == buyer_tenant_id:
        return None, "التوجيه الداخلي يجب أن يكون لمتجر آخر"
    return dealer, ""


class InternalTenantAdapter(BaseAdapter):
    supports_quantity = True   # تعبر الكمية إلى باقة المورّد إن كانت «بالكمية» هي أيضاً


    code = "tenant"

    def get_balance(self, config: dict, provider=None) -> BalanceResult:
        """رصيد محفظتنا (كوكيل) لدى المتجر المورّد — قراءة محلية من القاعدة."""
        dealer, why = _resolve_dealer(config, getattr(provider, "tenant_id", None))
        if dealer is None:
            return BalanceResult(ok=False, note=why)
        wallet = getattr(dealer, "wallet", None)
        if wallet is None:
            return BalanceResult(ok=False, note="الحساب لدى المورّد بلا محفظة")
        # الرصيد محفوظ بعملة دفتر **المورّد** — يُحوَّل إلى دفترنا هنا كما
        # تُحوَّل التكلفة، وإلّا عُرض رقمٌ بعملة غيرنا بلا ما يدلّ عليه.
        bal = _to_our_base(getattr(provider, "tenant", None), dealer.tenant, wallet.balance)
        if bal is None:
            return BalanceResult(
                ok=False,
                note=f"لا سعر صرف لعملة متجر {dealer.tenant.name} — اضبطه في «أسعار الصرف»",
            )
        return BalanceResult(
            ok=True, balance=bal,
            debt=-bal if bal < Decimal("0") else Decimal("0"),
            note=f"رصيدنا لدى متجر {dealer.tenant.name}",
        )

    def list_packages(self, config: dict, provider=None) -> PackageList:
        """كتالوج المورّد: منتجات المتجر الذي نملك حساب وكيل لديه."""
        from catalog.models import Product

        dealer, why = _resolve_dealer(config, getattr(provider, "tenant_id", None))
        if dealer is None:
            return PackageList(ok=False, note=why)
        rows = Product.objects.filter(
            tenant=dealer.tenant, status=Product.Status.ACTIVE
        ).select_related("game").order_by("game__sort_order", "sort_order")
        packages = [
            {"id": str(x.id), "name": x.name, "game": x.game.name,
             "kupur": x.kupur, "price": str(x.recommended_price)}
            for x in rows
        ]
        if not packages:
            return PackageList(ok=False, note=f"لا منتجات نشطة لدى {dealer.tenant.name}")
        return PackageList(ok=True, packages=packages)

    def quote(self, order, config: dict, provider=None):
        """
        ما سيكلّفنا هذا الطلب لدى المورّد **الآن**، بعملة دفترنا.

        سعرٌ يقينيّ بلا نداء شبكة — الرقم في قاعدتنا. به تعمل حماية الخسارة
        **قبل** أوّل طلب لا بعده، فلا يُشترى بخسارةٍ مرّةً كي نتعلّم.
        """
        from orders import services

        dealer, why = _resolve_dealer(config, order.tenant_id)
        if dealer is None:
            return None
        sp = _supplier_product(order, dealer, provider)
        if sp is None:
            return None
        if order.product.is_amount != sp.is_amount:
            return None
        # ما ندفعه نحن = سعر شرائنا كوكيل هناك (سعر مجموعتنا لدى المورّد) × كمية الطلب
        price = services.resolve_sell_price(dealer, sp) * sp.factor(order.quantity)
        return _to_our_base(order.tenant, dealer.tenant, price)

    def fetch_status(self, order, config: dict, provider=None) -> ExecutionResult:
        """
        حالة طلبنا لدى المورّد — قراءة من قاعدتنا، بلا شبكة.

        بدونها كان الطلب يتجمّد عندنا «قيد التنفيذ» إلى الأبد: المورّد ينفّذه
        يدوياً بعد دقائق، ولا شيء يحمل خبره إلينا. المحوّل الأساسي يردّ
        `unsupported` فتتركه حلقة المراقبة كما هو — صمتٌ لا عطلٌ ظاهر.
        """
        from orders.models import Order

        ref = (order.provider_ref or "").strip()
        if not ref.startswith(REF_PREFIX):
            return ExecutionResult(status="unsupported", note="لا مرجع لهذا الطلب لدى المورّد")
        try:
            _, subdomain, receipt = ref.split(":", 2)
        except ValueError:
            return ExecutionResult(status="unsupported", note=f"مرجع غير مفهوم: {ref}")

        sup = Order.objects.filter(
            tenant__subdomain=subdomain, receipt_no=receipt,
        ).select_related("tenant").first()
        if sup is None:
            return ExecutionResult(status="unsupported", note="طلبنا لدى المورّد غير موجود")

        note = (sup.provider_note or sup.api_response or "").strip()
        if sup.status == Order.Status.SUCCESS:
            return ExecutionResult(
                status="success", pin=sup.pin_result, external_ref=ref,
                note=note or f"نُفّذ لدى متجر {sup.tenant.name}",
            )
        if sup.status == Order.Status.CANCELLED:
            # المورّد يردّ المبلغ إلى محفظتنا لديه عند الإلغاء، فلا معنى لحجز
            # مال وكيلنا — وحلقة المراقبة تلغي وتسترجع.
            return ExecutionResult(
                status="failed", external_ref=ref,
                note=note or f"ألغاه متجر {sup.tenant.name}",
            )
        # العالق لدى المورّد ينتظر تدخّل صاحبه ومالُه محجوز هناك — انتظارٌ لا
        # رفض. قولُه فشلاً كان يسترجع لوكيلنا مالاً لم يُستَرجع لنا بعد.
        return ExecutionResult(
            status="processing", external_ref=ref,
            note=note or f"قيد التنفيذ لدى متجر {sup.tenant.name}",
        )

    def place_order(self, order, config: dict, provider=None, depth: int = 0) -> ExecutionResult:
        from orders import services

        dealer, why = _resolve_dealer(config, order.tenant_id)
        if dealer is None:
            return ExecutionResult(status="failed", note=why)

        sp = _supplier_product(order, dealer, provider)
        if sp is None:
            return ExecutionResult(
                status="failed",
                note="رقم الربط يجب أن يكون رقم منتجٍ قائمٍ لدى المتجر المورّد",
            )

        if order.product.is_amount != sp.is_amount:
            return ExecutionResult(
                status="failed",
                note="باقةٌ بالكمية لا تُربط إلا بباقةٍ بالكمية لدى المورّد (والعكس)",
            )

        # أنشئ الطلب لدى المورّد (يخصم محفظتنا هناك بسعرنا لديه)
        try:
            sup_order = services.create_order(
                dealer, sp,
                player_id=order.player_id, customer_phone=order.customer_phone,
                quantity=order.quantity,
            )
        except services.OrderError as e:
            return ExecutionResult(status="failed", note=f"رفض المورّد: {e}")

        # نفّذ لدى المورّد بتوجيهاته هو (عمق +1 يمنع الحلقات)
        services.dispatch_order(sup_order, depth=depth + 1)
        sup_order.refresh_from_db()

        ref = f"{REF_PREFIX}{dealer.tenant.subdomain}:{sup_order.receipt_no}"
        # تكلفتنا = **`buyer_price`** لا `sell_price`: الأوّل ما خُصم من محفظتنا
        # هناك، والثاني ما قبضه المتجر المورّد — ويفترقان إن كان حسابنا لديه
        # تحت وكيل كبير، فيدخل دفترَنا رقمٌ ليس ما دفعناه.
        cost = _to_our_base(order.tenant, dealer.tenant, sup_order.buyer_price)
        if sup_order.status == "success":
            return ExecutionResult(
                status="success", pin=sup_order.pin_result,
                cost=cost, cost_is_base=True, external_ref=ref,
                note=f"نُفّذ عبر متجر {dealer.tenant.name}",
            )
        if sup_order.status in ("pending", "processing"):
            # التكلفة تُعتمد **الآن** لا عند النجاح: المال خُصم من محفظتنا لدى
            # المورّد لحظة الإنشاء. تركُها للاحق كان يُبقي في دفترنا تكلفةً
            # مقدَّرةً وربحاً موهوماً طوال انتظار التنفيذ اليدوي.
            return ExecutionResult(
                status="processing", cost=cost, cost_is_base=True, external_ref=ref,
                note=f"قيد التنفيذ لدى متجر {dealer.tenant.name}",
            )
        return ExecutionResult(
            status="failed", external_ref=ref,
            note=f"فشل لدى المورّد: {sup_order.api_response[:120]}",
        )
