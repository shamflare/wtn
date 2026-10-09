"""
منطق الطلبات: إنشاء طلب (تسعير + خصم محفظة)، تنفيذ، إلغاء (استرجاع).
يربط: التسعير (catalog) + المحفظة (core) + المزوّدين (providers).
"""
import random
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.utils import timezone

from core import currency, services as wallet_services
from core.models import User, WalletTransaction
from catalog.models import AgentMargin, AgentProductPrice, Product, ProductPrice
from .models import Order


class OrderError(Exception):
    """خطأ في عملية الطلب."""


def _gen_receipt_no() -> str:
    return timezone.now().strftime("%y%m%d") + str(random.randint(10000, 99999))


def big_agent_of(dealer: User):
    """الوكيل الكبير الذي يتبعه هذا الدكان — أو None إن كان يشتري من المتجر مباشرةً."""
    if dealer.parent_id and getattr(dealer.parent, "role", None) == User.Role.ANA_BAYI:
        return dealer.parent
    return None


def resolve_store_price(buyer: User, product: Product) -> Decimal:
    """ما يقبضه **المتجر**: سعر مجموعة المشتري عند صاحب المتجر، وإلا السعر الموصى."""
    if buyer.price_group_id:
        pp = ProductPrice.objects.filter(
            product=product, price_group_id=buyer.price_group_id
        ).first()
        if pp:
            return pp.price.quantize(Decimal("0.01"))
    return product.recommended_price.quantize(Decimal("0.01"))


def resolve_sell_price(dealer: User, product: Product) -> Decimal:
    """
    ما يدفعه المشتري.

    دكانٌ تابع لوكيل كبير **لا يشتري من المتجر**: يشتري من وكيله بسعر مجموعة
    وضعه الكبير فيها. فإن لم يسعّر له الكبير بعد، نرتدّ إلى هامشه المئوي القديم،
    ثم إلى سعر الكبير نفسه — فلا يُباع الدكان بأرخص ممّا اشترى به وكيله.
    """
    agent = big_agent_of(dealer)
    if agent is None:
        return resolve_store_price(dealer, product)

    agent_cost = resolve_store_price(agent, product)

    if dealer.agent_price_group_id:
        row = AgentProductPrice.objects.filter(
            group_id=dealer.agent_price_group_id, product=product
        ).first()
        if row:
            from catalog.services import agent_row_price, rounds
            return agent_row_price(row, agent_cost, rounds(product, True))

    margin = AgentMargin.objects.filter(agent_id=agent.id, product=product).first()
    if margin and margin.margin_percent:
        return (agent_cost * (Decimal("1") + margin.margin_percent / Decimal("100"))).quantize(
            Decimal("0.01")
        )
    return agent_cost


def resolve_dealer_sell_price(product: Product, raw=None) -> Decimal:
    """
    سعر بيع الوكيل **لزبونه**: ما كتبه بيده إن كتبه، وإلا سعر التوصية.
    سعر التوصية تخمين من صاحب المتجر؛ الوكيل حرّ أن يبيع أغلى أو أرخص.
    """
    if raw in (None, ""):
        return product.recommended_price.quantize(Decimal("0.01"))
    try:
        value = Decimal(str(raw).replace(",", "."))
    except (InvalidOperation, ValueError):
        raise OrderError("سعر البيع غير صالح")
    if value < 0:
        raise OrderError("سعر البيع لا يصحّ أن يكون سالباً")
    return value.quantize(currency.LEDGER)   # كتبه بعملته — بدقّة الدفتر لا بالسنت


CENT = Decimal("0.01")


def clean_quantity(product: Product, quantity) -> int:
    """
    كمية الطلب: 1 للباقة الثابتة دائماً، وللباقة «بالكمية» عددٌ صحيح بين حدّيها.
    الحدّان من المزوّد نفسه — كميةٌ خارجهما يرفضها هو بعد أن نكون خصمنا المحفظة.
    """
    if not product.is_amount:
        return 1
    try:
        q = int(str(quantity).replace(",", "").strip())
    except (TypeError, ValueError):
        raise OrderError(f"اكتب الكمية — من {product.qty_min:,} إلى {product.qty_max:,}")
    if q < product.qty_min or q > product.qty_max:
        raise OrderError(f"الكمية بين {product.qty_min:,} و{product.qty_max:,}")
    return q


@transaction.atomic
def create_order(dealer: User, product: Product, *, player_id="", customer_phone="",
                 dealer_sell_price=None, client_uuid=None, quantity=None) -> Order:
    """
    ينشئ طلباً: يحسب السعر، يخصم من محفظة الوكيل، ويسجّل الطلب (قيد الانتظار).

    الباقة «بالكمية»: أسعارها لكل qty_unit وحدة، فكلّ مبلغٍ في الطلب (ما يدفعه المشتري
    وما يقبضه المتجر والتكلفة وساقا الوكيل الكبير) مضروبٌ في factor = الكمية ÷ qty_unit.
    و`dealer_sell_price` إن كتبه الوكيل فهو **إجمالي** ما باع به لزبونه.
    """
    if product.tenant_id != dealer.tenant_id:
        raise OrderError("المنتج والوكيل من مستأجرين مختلفين")
    # بوّابة الاشتراك هنا وحدها: كل شراء يمرّ من `create_order` — متجرُ الوكيل
    # ولوحةُ الأدمن والواجهةُ الخارجية والتوجيهُ الداخلي. حراستُها في كل مدخل
    # على حدة كانت تترك باباً منسيّاً.
    if dealer.tenant is not None and dealer.tenant.purchases_blocked:
        raise OrderError(
            "انتهى اشتراك المتجر ومهلة السماح — الشراء متوقّف حتى التجديد. "
            "القراءة والتقارير والمحافظ تعمل كما هي."
        )
    if product.status != Product.Status.ACTIVE:
        raise OrderError("المنتج غير متاح للبيع")

    qty = clean_quantity(product, quantity)
    k = product.factor(qty)
    agent = big_agent_of(dealer)
    # بدقّة الدفتر: سعر وكيله الكبير كتبه بعملته
    buyer_price = (resolve_sell_price(dealer, product) * k).quantize(currency.LEDGER)          # ما يدفعه المشتري
    store_price = (resolve_store_price(agent or dealer, product) * k).quantize(CENT)  # ما يقبضه المتجر
    cost = (product.cost_price * k).quantize(CENT)
    retail = (resolve_dealer_sell_price(product) * k).quantize(currency.LEDGER) if dealer_sell_price in (None, "") \
        else resolve_dealer_sell_price(product, dealer_sell_price)
    if product.is_amount and buyer_price <= 0:
        raise OrderError("الكمية صغيرة جداً — قيمتها أقل من سنت")

    wallet = getattr(dealer, "wallet", None)
    if wallet is None:
        raise OrderError("لا توجد محفظة للوكيل")

    # خصم المحفظة (يحترم الحد الائتماني) — قد يرفع WalletError
    try:
        txn = wallet_services.apply_transaction(
            wallet.id, -buyer_price, WalletTransaction.Type.ORDER_DEBIT,
            created_by=dealer, note=f"طلب {product.name}" + (f" × {qty:,}" if product.is_amount else ""),
        )
    except wallet_services.WalletError as e:
        raise OrderError(str(e))

    # ساقا الوكيل الكبير: يقبض من دكانه أوّلاً ثم يدفع للمتجر، فلا يُوقفه حدّه
    # الائتماني في المنتصف على طلب ربحُه موجب أصلاً.
    if agent is not None:
        agent_wallet = getattr(agent, "wallet", None)
        if agent_wallet is None:
            raise OrderError("لا توجد محفظة للوكيل الكبير")
        try:
            wallet_services.apply_transaction(
                agent_wallet.id, buyer_price, WalletTransaction.Type.TOPUP,
                created_by=dealer, note=f"بيع {product.name} لـ{dealer.name}", internal=True,
            )
            wallet_services.apply_transaction(
                agent_wallet.id, -store_price, WalletTransaction.Type.ORDER_DEBIT,
                created_by=dealer, note=f"شراء {product.name} من المتجر لـ{dealer.name}",
            )
        except wallet_services.WalletError as e:
            raise OrderError(f"محفظة الوكيل الكبير: {e}")

    order = Order.objects.create(
        tenant_id=dealer.tenant_id,
        receipt_no=_gen_receipt_no(),
        dealer=dealer, game=product.game, product=product, quantity=qty,
        player_id=player_id, customer_phone=customer_phone,
        cost_price=cost, sell_price=store_price, profit=store_price - cost,
        agent=agent, buyer_price=buyer_price,
        agent_profit=(buyer_price - store_price) if agent else Decimal("0"),
        dealer_sell_price=retail, dealer_profit=retail - buyer_price,
        status=Order.Status.PENDING,
        balance_before=txn.balance_before, balance_after=txn.balance_after,
        client_uuid=client_uuid,
    )
    # ربط الحركة بالطلب
    txn.ref_type = "order"
    txn.ref_id = order.id
    txn.save(update_fields=["ref_type", "ref_id"])
    return order


def _agent_legs(order: Order, *, sign: int) -> None:
    """
    ساقا الوكيل الكبير على طلب دكانه — تُطبَّقان معاً أو لا تُطبَّقان.

    `sign=1` تعني تنفيذ الطلب (يقبض من دكانه ثم يدفع للمتجر)، و`sign=-1` تعني
    نقضه (يردّ للدكان ويستردّ من المتجر). الترتيب مقصود: القبض قبل الدفع في
    الحالتين، فلا يوقف الحدّ الائتماني عمليةً محصّلتها في صالح المحفظة.
    """
    if order.agent_id is None:
        return
    wallet = getattr(order.agent, "wallet", None)
    if wallet is None:
        return
    # (المبلغ، البيان، مع دكانه؟) — ساق الدكان داخلية، وساق المتجر بينه وبين المتجر
    legs = (
        [(order.buyer_price, "بيع", True), (-order.sell_price, "شراء من المتجر", False)] if sign == 1
        else [(order.sell_price, "استرداد من المتجر", False), (-order.buyer_price, "ردّ لدكانه", True)]
    )
    for amount, label, internal in legs:
        wallet_services.apply_transaction(
            wallet.id,
            amount,
            WalletTransaction.Type.TOPUP if amount > 0 else WalletTransaction.Type.ORDER_DEBIT,
            note=f"{label} — طلب {order.receipt_no}",
            ref_type="order", ref_id=order.id, allow_below_limit=True, internal=internal,
        )


@transaction.atomic
def execute_order(order: Order, *, provider=None, pin="") -> Order:
    """
    تنفيذ الطلب يدوياً (ناجح): يسجّل المزوّد والـ PIN إن أُعطي.
    بلا PIN يبقى الحقل فارغاً وتُعرض «شُحن مباشرةً ✓» — لا يجوز اختلاق كود
    وهمي يُسلَّم للوكيل على أنه كود شحن حقيقي.

    ويقبل **عكس قرار سابق**: طلب ملغى يُعاد قبوله. وحينها يُعاد خصم المبلغ
    لأن الإلغاء أرجعه — بدون ذلك يشحن الوكيل مجاناً.
    """
    reinstated = order.status == Order.Status.CANCELLED
    if not reinstated and order.status not in (
        Order.Status.PENDING, Order.Status.PROCESSING, Order.Status.STUCK
    ):
        raise OrderError("لا يمكن تنفيذ طلب بحالته الحالية")

    if reinstated:
        try:
            wallet_services.apply_transaction(
                order.dealer.wallet.id, -order.buyer_price, WalletTransaction.Type.ORDER_DEBIT,
                note=f"إعادة خصم طلب {order.receipt_no} بعد قبوله",
                ref_type="order", ref_id=order.id,
            )
            _agent_legs(order, sign=1)   # يقبض من دكانه ويدفع للمتجر من جديد
        except wallet_services.WalletError as e:
            raise OrderError(f"تعذّر إعادة خصم المبلغ: {e}")

    order.status = Order.Status.SUCCESS
    order.provider = provider or order.provider
    order.pin_result = pin or order.pin_result
    order.api_response = (
        "أعاد المشغّل قبوله بعد إلغائه — أُعيد خصم المبلغ" if reinstated
        else "نفّذه المشغّل يدوياً"
    )
    order.approved_at = timezone.now()
    order.save(update_fields=["status", "provider", "pin_result", "api_response", "approved_at"])
    return order


@transaction.atomic
def set_manual(order: Order) -> Order:
    """
    إعادة الطلب إلى **التنفيذ اليدوي**: يعود «قيد الانتظار» ويُفكّ عن مزوّده.
    مخرج الطلب العالق: يُعاد يدوياً ثم يُنفَّذ أو يُوجَّه إلى مزوّد آخر.
    مرجع المزوّد وملاحظته يبقيان — هما سجلّ ما جرى، ولا يُستعلَم عنهما بعد
    الآن لأن حلقة المراقبة لا تلمس إلا «قيد التنفيذ».
    """
    if order.status in (Order.Status.SUCCESS, Order.Status.CANCELLED):
        raise OrderError("لا يمكن إعادة طلب محسوم إلى اليدوي")
    order.status = Order.Status.PENDING
    order.provider = None
    order.api_response = "أُعيد إلى التنفيذ اليدوي بقرار المشغّل"
    order.save(update_fields=["status", "provider", "api_response"])
    return order


def _link_price(product_id: int, provider_id: int):
    """سعر الباقة لدى المزوّد كما حُفظ وقت الربط من كتالوجه (أو None)."""
    from catalog.models import ProductLink

    link = ProductLink.objects.filter(
        product_id=product_id, provider_id=provider_id
    ).only("extra").first()
    raw = (link.extra or {}).get("price") if link else None
    if raw in (None, ""):
        return None
    try:
        return Decimal(str(raw).replace(",", "."))
    except (InvalidOperation, ValueError):
        return None


def _apply_real_cost(order: Order, result, provider) -> list:
    """
    يعتمد التكلفة **الفعلية** التي أعادها المزوّد بدل التكلفة المقدَّرة على
    المنتج، ويعيد حساب الربح. بدونها يظهر ربح وهمي بينما العملية خاسرة.

    ويُعلّم الربط بهذه التكلفة (`extra.price`) حتى تعمل حماية الخسارة على
    الطلب التالي — فالربط قد يكون أُنشئ يدوياً بلا سعر كتالوج، وبلا سعر
    معروف تمرّ الحماية صامتةً (فشل مفتوح).
    """
    if result.cost is None or result.cost < 0:
        return []
    # المزوّد الخارجي يسعّر بالليرة والدفتر بعملة المتجر — التحويل هنا، عند
    # حدود النظام. بدونه تدخل ليرةٌ إلى حقل دولاري فيظهر الطلب خاسراً بأربعين
    # ضعفاً. أمّا المزوّد الداخلي فقد حوّل بنفسه (المتجران في قاعدتنا ويعرف
    # عملتيهما)، وتمريره على محوّل الليرة كان يقسمه على ~41 فيعكس الخطأ.
    cost = (result.cost if result.cost_is_base
            else currency.from_provider(order.tenant, result.cost, provider))
    if cost is None:
        return []
    order.cost_price = cost
    order.profit = order.sell_price - cost
    # المرجع على الربط سعرٌ لكل qty_unit (كأسعار الباقة) — لا إجمالي هذه الكمية
    k = order.product.factor(order.quantity)
    _learn_link_price(order.product_id, getattr(provider, "id", None),
                      (cost / k).quantize(CENT) if k else cost)
    return ["cost_price", "profit"]


def _learn_link_price(product_id: int, provider_id, cost) -> None:
    """يحفظ التكلفة الفعلية على الربط ليصير سعراً مرجعياً لحماية الخسارة."""
    from catalog.models import ProductLink

    if not provider_id:
        return
    link = ProductLink.objects.filter(
        product_id=product_id, provider_id=provider_id
    ).first()
    if link is None:
        return
    extra = dict(link.extra or {})
    if str(extra.get("price") or "") == str(cost):
        return
    extra["price"] = str(cost)
    link.extra = extra
    link.save(update_fields=["extra", "updated_at"])


def _send_to(order: Order, provider, trail: list, depth: int = 0, force: bool = False) -> bool:
    """
    محاولة إرسال واحدة لدى مزوّد بعينه.
    تُعيد True إن حُسمت المحاولة (ناجح أو قيد تنفيذ) فتتوقّف السلسلة،
    وFalse إن فشلت أو تُخُطّيت — ويُسجَّل السبب في `trail`.

    `force` يتخطّى حماية الخسارة. وظيفة الحماية أن **توقف وتنبّه**، لا أن تمنع
    إلى الأبد: فإن رأى صاحب المتجر الخسارة ثم وجّه الطلب بيده إلى المزوّد نفسه،
    فتلك إرادته المعلَنة على رقمٍ صار يراه — والنظام لا يعاند صاحبه.
    """
    from providers.adapters.registry import adapter_for

    adapter = adapter_for(provider)
    if adapter is None:
        trail.append(f"{provider.name}: منفّذ يدوي — تُخُطّي")
        return False
    if order.product.is_amount and not getattr(adapter, "supports_quantity", False):
        # إرسالها إليه باقةً واحدة يشحن اللاعب غير ما دفع ثمنه
        trail.append(f"{provider.name}: لا يدعم البيع بالكمية — تُخُطّي")
        return False

    # حماية الخسارة (Zarar Ayarı): سعر الباقة المحفوظ وقت الربط مأخوذ من
    # كتالوج المزوّد. إن تجاوز سعر بيعنا، فالطلب خاسر قبل أن يُرسَل —
    # نتخطّى هذا المزوّد بدل إنفاق المال. يُعطَّل بإطفاء loss_guard عليه.
    if provider.loss_guard:
        # سعرٌ حيّ إن استطاع المحوّل (الداخلي يعرفه من قاعدتنا بلا كلفة)،
        # وإلّا السعر المُتعلَّم من طلب سابق. الحيّ أصدق: المتعلَّم قد يكون
        # قديماً، والأهمّ أنه لا يوجد أصلاً قبل أوّل طلب.
        try:
            known = adapter.quote(order, provider.config or {}, provider=provider)
        except Exception:
            known = None
        if known is None:
            known = _link_price(order.product_id, provider.id)
            if known is not None:   # المرجع لكل qty_unit ⇐ تكلفة هذه الكمية
                known = (known * order.product.factor(order.quantity)).quantize(CENT)
        if known is None:
            # لا سعر مرجعي بعد (ربط يدوي مثلاً) — نمرّر ونتعلّم التكلفة من
            # ردّ المزوّد، فتحمي الطلبَ التالي.
            trail.append(f"{provider.name}: حماية الخسارة بلا سعر مرجعي — أول طلب يحدّده")
        elif known > order.sell_price and not force:
            # نثبّت التكلفة الحقيقية على الطلب وإن لم يُرسَل: بدونها يبقى في
            # الجدول السعر المقدَّر على المنتج فيقرأ صاحب المتجر «ربح 0.15»
            # على طلبٍ محجوبٍ لأنه يخسر 31. حجم الخسارة هو سبب الحجب — فليُرَ.
            order.cost_price = known
            order.profit = order.sell_price - known
            trail.append(
                f"{provider.name}: حماية الخسارة — تكلفته {known} > سعر البيع {order.sell_price}"
            )
            return False

    try:
        result = adapter.place_order(order, provider.config or {}, provider=provider, depth=depth)
    except Exception as e:
        trail.append(f"{provider.name}: خطأ محوّل ({e})")
        return False

    note = (result.note or "").strip()
    ref = f" · ref={result.external_ref}" if result.external_ref else ""
    cost_fields = _apply_real_cost(order, result, provider)

    if result.status in ("success", "processing"):
        order.status = (
            Order.Status.SUCCESS if result.status == "success" else Order.Status.PROCESSING
        )
        order.provider = provider
        prefix = f"[بديل بعد: {' | '.join(trail)}] " if trail else ""
        order.api_response = f"{prefix}{note}{ref}"[:250]
        order.provider_ref = result.external_ref or ""
        order.provider_note = note[:250]
        fields = ["status", "provider", "api_response", "provider_ref", "provider_note"]
        if result.status == "success":
            order.pin_result = result.pin or ""
            order.approved_at = timezone.now()
            fields += ["pin_result", "approved_at"]
        order.save(update_fields=fields + cost_fields)
        return True

    trail.append(f"{provider.name}: {note or 'فشل'}")
    return False


def _failover_after_rejection(order: Order, trail: list) -> bool:
    """
    بعد أن يلغي مزوّدٌ طلباً كان قد قبله: تُجرَّب بقيّة سلسلة المنتج من بعده.
    تُعيد True إن التقطه بديل (نجح أو قيد تنفيذ) فيبقى الطلب حيّاً.

    يُبدأ من **موضع المزوّد الحالي** لا من رأس السلسلة، فلا يُعاد الإرسال إلى
    من جُرِّب سلفاً — وهو ما قد يشحن اللاعب مرّتين ويدفع التكلفة مرّتين.

    وإن كان المزوّد الحالي خارج السلسلة (وجّهه المشغّل بيده إلى مزوّد لم
    يُعَدّ على الباقة) تُجرَّب السلسلة كاملةً ما عدا مَن ألغى للتوّ — بقرار
    المالك: الطلب المُوجَّه يدوياً يُكمل السلسلة آلياً كأي طلب.
    """
    product = order.product
    chain = [p for p in (product.provider, product.provider_alt1, product.provider_alt2) if p]
    ids = [p.id for p in chain]
    rest = (
        chain[ids.index(order.provider_id) + 1:] if order.provider_id in ids
        else [p for p in chain if p.id != order.provider_id]
    )
    if not rest:
        trail.append("لا بديل بعد هذا الموضع")
        return False

    for nxt in rest:
        if _send_to(order, nxt, trail):
            return True
    return False


def dispatch_to_provider(order: Order, provider, depth: int = 0, force: bool = True) -> Order:
    """
    توجيه **يدوي** إلى مزوّد يختاره المشغّل — يتخطّى سلسلة المنتج.
    مخرج الطلب العالق أو المُعدّ يدوياً: يُرسَل إلى من يراه المشغّل مناسباً.

    و**يتخطّى حماية الخسارة افتراضياً** (`force`): الحماية أوقفت الطلب وأرَته
    الخسارة، فإن أعاد صاحب المتجر توجيهه بيده بعد أن رآها فقد قرّر. إبقاء
    الحجب هنا كان يجعل الطلب العالق بلا مخرج إلا تعديل التسعير.
    """
    if order.status not in (Order.Status.PENDING, Order.Status.STUCK):
        raise OrderError("لا يُوجَّه إلا طلب قيد الانتظار أو عالق")

    trail = []
    if _send_to(order, provider, trail, depth, force=force):
        return order

    order.status = Order.Status.STUCK
    order.provider = provider
    order.api_response = ("فشل التوجيه اليدوي → " + " | ".join(trail))[:250]
    order.save(update_fields=["status", "provider", "api_response", "cost_price", "profit"])
    return order


def dispatch_order(order: Order, depth: int = 0) -> Order:
    """
    التنفيذ التلقائي مع التوجيه البديل (Failover):
    يُجرَّب المزوّد الرئيسي، وعند الفشل يُجرَّب API 1 ثم API 2 تلقائياً —
    بحسب ما فعّله صاحب المتجر على المنتج (مزوّد واحد أو اثنان أو ثلاثة).
    - success → ناجح + PIN.  - processing → قيد التنفيذ (يتوقّف عندها).
    - فشل الكل → عالق، مع سجلّ محاولات كامل في api_response.
    depth يمنع حلقات التوجيه الداخلي بين المتاجر (متجر → متجر → ...).
    """
    if depth > 2:
        order.status = Order.Status.STUCK
        order.api_response = "تجاوز عمق التوجيه الداخلي المسموح (حلقة متاجر؟)"
        order.save(update_fields=["status", "api_response"])
        return order

    product = order.product
    chain = [p for p in (product.provider, product.provider_alt1, product.provider_alt2) if p]
    if not chain:
        return order  # بلا مزوّد — يبقى قيد الانتظار للتنفيذ اليدوي

    trail = []  # سجلّ المحاولات: "المزوّد: السبب"
    for provider in chain:
        if _send_to(order, provider, trail, depth):
            return order

    # فشلت كل التوجيهات → عالق مع السجلّ الكامل
    order.status = Order.Status.STUCK
    order.provider = chain[-1]
    order.api_response = ("فشلت كل التوجيهات → " + " | ".join(trail))[:250]
    # cost_price/profit قد يكونا صُحّحا بسعر المزوّد الحقيقي عند الحجب
    order.save(update_fields=["status", "provider", "api_response", "cost_price", "profit"])
    return order


@transaction.atomic
def cancel_order(order: Order) -> Order:
    """
    إلغاء الطلب: يسترجع المبلغ لمحفظة الوكيل.
    ويقبل **عكس قرار سابق**: طلب نُفّذ بالخطأ يُبطله المشغّل ويُستَرجع مبلغه.
    """
    if order.status == Order.Status.CANCELLED:
        raise OrderError("الطلب ملغى مسبقاً")
    revoked = order.status == Order.Status.SUCCESS

    wallet = order.dealer.wallet
    wallet_services.apply_transaction(
        wallet.id, order.buyer_price, WalletTransaction.Type.REFUND,
        created_by=order.dealer, note=f"إلغاء طلب {order.receipt_no}",
        ref_type="order", ref_id=order.id, allow_below_limit=True,
    )
    _agent_legs(order, sign=-1)   # ينقض ربح الوكيل الكبير مع المبلغ
    order.status = Order.Status.CANCELLED
    order.api_response = (
        "أبطله المشغّل بعد نجاحه — استُرجع المبلغ" if revoked
        else "أُلغي واسترُجع المبلغ"
    )
    order.save(update_fields=["status", "api_response"])
    return order


def sync_order(order: Order) -> dict:
    """
    استعلام حالة الطلب لدى المزوّد وتحديثه عندنا (حلقة المراقبة).

    يُطبَّق على الطلبات "قيد التنفيذ" فقط — أي ما أكّد المزوّد استلامه ولم
    يحسمه بعد. نتيجة المزوّد:
      • ناجح  → success + الـ PIN + ملاحظته
      • مرفوض → عالق (لا استرجاع تلقائي — القرار للأدمن) + سبب الرفض
      • ما زال → يبقى قيد التنفيذ ونحدّث الملاحظة إن تغيّرت
    """
    from providers.adapters.registry import adapter_for

    out = {"order": order.id, "changed": False, "status": order.status}
    if order.status != Order.Status.PROCESSING or order.provider is None:
        out["note"] = "لا يحتاج متابعة"
        return out

    adapter = adapter_for(order.provider)
    if adapter is None:
        out["note"] = "لا محوّل آلي لهذا المزوّد"
        return out

    try:
        result = adapter.fetch_status(order, order.provider.config or {}, provider=order.provider)
    except Exception as e:                     # لا نُسقِط الحلقة بسبب مزوّد واحد
        out["note"] = f"خطأ محوّل: {e}"
        return out

    # الاستعلام يستغرق ثوانيَ، وقد يحسم المشغّل الطلب خلالها. قرار الإنسان
    # يتقدّم: نتخلّى بلا كتابة، وإلا داس ردُّ المزوّد قراره — وقد يعني ذلك
    # استرجاعاً ثانياً لمبلغ استُرجع أو أُقرّ.
    order.refresh_from_db(fields=["status"])
    if order.status != Order.Status.PROCESSING:
        out.update(status=order.status, note="حسمه المشغّل أثناء الاستعلام — تُرك كما قرّر")
        return out

    note = (result.note or "").strip()
    fields = ["last_sync_at"]
    order.last_sync_at = timezone.now()

    # نسجّل ملاحظة المزوّد؛ وإن ردّ بلا رسالة (مثل "OK|3||") نحفظ الردّ الخام
    # بدل إبقاء ردّ الإرسال القديم الذي يوهم بأن الطلب ما زال مقبولاً.
    fresh = note or (result.raw or "").strip()
    if fresh and fresh != order.provider_note:
        order.provider_note = fresh[:250]
        fields.append("provider_note")

    if result.status == "success":
        order.status = Order.Status.SUCCESS
        order.pin_result = result.pin or order.pin_result
        order.approved_at = timezone.now()
        order.api_response = (f"المزوّد أكّد التنفيذ · {note}" if note else "المزوّد أكّد التنفيذ")[:250]
        fields += ["status", "pin_result", "approved_at", "api_response"]
        out["changed"] = True
    elif result.status == "failed":
        order.save(update_fields=fields)          # نثبّت الملاحظة قبل أي تصرّف

        # رفض المزوّد **بعد قبوله** ليس نهاية الطلب: السلسلة البديلة وُضعت
        # لهذا بالضبط. نجرّب من بعده في سلسلة المنتج قبل أن نلغي على الوكيل.
        trail = [f"{order.provider.name}: ألغى الطلب بعد قبوله" + (f" — {note}" if note else "")]
        if _failover_after_rejection(order, trail):
            order.refresh_from_db()
            out.update(changed=True, status=order.status, note=note, failover=True,
                       provider=order.provider_id, provider_note=order.provider_note,
                       raw=(result.raw or "")[:300], parsed=result.status)
            return out

        # لا بديل التقطه ⇒ إلغاء واسترجاع. ZNET (الحالة 3 = IPTAL) يعيد المبلغ
        # إلى رصيدنا لديه — مؤكَّد عملياً 581.60 ← 625.00 — فلا معنى لحجز
        # مال الوكيل، ولا لتركه "عالقاً" بانتظار الأدمن.
        cancel_order(order)
        order.api_response = (
            "ألغى المزوّد الطلب ولم يلتقطه بديل — استُرجع المبلغ · " + " | ".join(trail)
        )[:250]
        order.save(update_fields=["api_response"])
        out.update(changed=True, status=order.status, note=note,
                   provider_note=order.provider_note, refunded=True,
                   raw=(result.raw or "")[:300], parsed=result.status)
        return out

    order.save(update_fields=fields)
    out.update(
        status=order.status, note=note, pin=order.pin_result,
        provider_note=order.provider_note,
        # الردّ الخام كما ورد من المزوّد — للتشخيص وقراءة رسالته حرفيّاً
        raw=(result.raw or "")[:300],
        parsed=result.status,
    )
    return out


def sync_pending(tenant, limit: int = 50) -> list:
    """يتابع كل الطلبات "قيد التنفيذ" لهذا المستأجر — تستدعيها حلقة المراقبة."""
    qs = (
        Order.objects.filter(tenant=tenant, status=Order.Status.PROCESSING)
        .select_related("provider", "product")
        .order_by("-created_at")[:limit]
    )
    return [sync_order(o) for o in qs]
