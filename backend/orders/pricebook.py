"""
دفتر الأسعار: كل أسعار مستخدمٍ واحد تُحمَّل **مرّةً واحدة** لكل صفحة.

صفحات قوائم الأسعار (كتالوج الوكيل، قائمة الباقات، مصفوفة الوكيل الكبير، الـ API)
كانت تسأل القاعدة لكل باقةٍ على حدة: مجموعته، ثم سعر وكيله الكبير، ثم هامشه —
فصفحةٌ بـ250 باقة = 600 استعلام، وثوانٍ من الانتظار على الخادم الحيّ.

هنا القواعد نفسها حرفاً (`orders.services.resolve_sell_price` / `resolve_store_price`
و`kontor.services.dealer_price` / `store_price`) لكن من خرائط في الذاكرة. والشراء نفسه
يبقى على الدوالّ الأصلية — باقةٌ واحدة لا تحتاج دفتراً. واختبارٌ يضمن تطابق الاثنين.
"""
from decimal import Decimal

CENT = Decimal("0.01")


class GamePrices:
    """أسعار الألعاب لمشترٍ واحد: ما يدفعه هو، وما يقبضه المتجر."""

    def __init__(self, buyer):
        from catalog.models import AgentMargin, AgentProductPrice, ProductPrice
        from .services import big_agent_of

        self.buyer = buyer
        self.agent = big_agent_of(buyer)
        payer = self.agent or buyer                    # من يشتري من المتجر فعلاً
        self._store = self._group_map(ProductPrice, payer.price_group_id)
        self._agent_rows, self._margins = {}, {}
        if self.agent is not None:
            if buyer.agent_price_group_id:
                self._agent_rows = {r.product_id: r for r in
                                    AgentProductPrice.objects.filter(group_id=buyer.agent_price_group_id)}
            self._margins = {m.product_id: m.margin_percent for m in
                             AgentMargin.objects.filter(agent_id=self.agent.id)}

    @staticmethod
    def _group_map(model, group_id) -> dict:
        if not group_id:
            return {}
        return dict(model.objects.filter(price_group_id=group_id).values_list("product_id", "price"))

    def store_price(self, product) -> Decimal:
        """ما يقبضه المتجر من المشتري (أو من وكيله الكبير)."""
        p = self._store.get(product.id)
        return (p if p is not None else product.recommended_price).quantize(CENT)

    def price(self, product) -> Decimal:
        """ما يدفعه المشتري — كـ resolve_sell_price حرفاً."""
        if self.agent is None:
            return self.store_price(product)
        cost = self.store_price(product)
        row = self._agent_rows.get(product.id)
        if row is not None:
            from catalog.services import agent_row_price, rounds
            return agent_row_price(row, cost, rounds(product, True))
        pct = self._margins.get(product.id)
        if pct:
            return (cost * (Decimal("1") + pct / Decimal("100"))).quantize(CENT)
        return cost


class MobilePrices:
    """أسعار الخطوط لمشترٍ واحد — كـ kontor.services.dealer_price / store_price حرفاً."""

    def __init__(self, buyer):
        from orders.services import big_agent_of
        from kontor.models import AgentKontorPrice

        self.buyer = buyer
        self.agent = big_agent_of(buyer)
        payer = self.agent or buyer
        self._groups, self._prices = self._load(payer)
        self._agent_rows = {}
        if self.agent is not None and buyer.agent_kontor_price_group_id:   # مجموعة الرصيد
            self._agent_rows = {r.package_id: r for r in
                                AgentKontorPrice.objects.filter(group_id=buyer.agent_kontor_price_group_id)}

    @staticmethod
    def _load(payer):
        """مجموعة المشتري لكل شركة، وأسعار تلك المجموعات — استعلامان للكلّ."""
        from kontor.models import KontorDealerSetting, KontorPackagePrice
        groups = {s.operator: s.group_id for s in
                  KontorDealerSetting.objects.filter(dealer=payer).exclude(group_id=None)}
        prices = {}
        if groups:
            for pkg_id, gid, price in KontorPackagePrice.objects.filter(
                    group_id__in=set(groups.values())).values_list("package_id", "group_id", "price"):
                prices[(pkg_id, gid)] = price
        return groups, prices

    def store_price(self, package) -> Decimal:
        gid = self._groups.get(package.operator)
        p = self._prices.get((package.id, gid)) if gid else None
        return (p if p is not None else (package.recommended_price or Decimal("0"))).quantize(CENT)

    def price(self, package) -> Decimal:
        if self.agent is None:
            return self.store_price(package)
        cost = self.store_price(package)
        row = self._agent_rows.get(package.id)
        if row is not None:
            from catalog.services import agent_row_price
            return agent_row_price(row, cost)
        return cost
