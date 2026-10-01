"""
اختبارات المسار المالي للوكيل الكبير.

القاعدة التي تحرسها: **دكان الوكيل الكبير لا يشتري من المتجر**. يدفع لوكيله بسعر
مجموعته عنده، والوكيل يدفع للمتجر بسعر مجموعته هو، والفرق ربح الوكيل يدخل محفظته
لحظة الطلب. وأي نقض للطلب يعكس الساقين معاً — وإلّا بقي ربحٌ على طلب ملغى.
"""
from decimal import Decimal

from django.test import TestCase
from rest_framework.test import APITestCase

from catalog.models import (
    AgentPriceGroup, AgentProductPrice, Game, PriceGroup, Product, ProductPrice,
)
from core.models import Tenant, User, Wallet
from providers.models import Provider

from .models import Order
from .services import cancel_order, create_order, execute_order


class BigAgentMoneyTest(APITestCase):
    """أحمد يشتري من المتجر بـ 8، ويبيع دكانه بـ 10، فربحه 2 على كل طلب."""

    def setUp(self):
        self.tenant = Tenant.objects.create(subdomain="tm", name="متجر", base_currency="USD")

        # مجموعتان عند صاحب المتجر: واحدة لأحمد وأخرى لا تخصّ دكانه
        self.store_group = PriceGroup.objects.create(tenant=self.tenant, name="وكلاء كبار")
        self.other_group = PriceGroup.objects.create(tenant=self.tenant, name="عادية")

        self.game = Game.objects.create(tenant=self.tenant, name="PUBG")
        self.product = Product.objects.create(
            tenant=self.tenant, game=self.game, name="60 UC",
            cost_price=Decimal("6.00"), recommended_price=Decimal("12.00"),
        )
        ProductPrice.objects.create(
            tenant=self.tenant, product=self.product,
            price_group=self.store_group, price=Decimal("8.00"),
        )
        ProductPrice.objects.create(
            tenant=self.tenant, product=self.product,
            price_group=self.other_group, price=Decimal("11.00"),
        )

        self.ahmad = User.objects.create(
            login_id="ahmad", name="أحمد العلي", tenant=self.tenant,
            role=User.Role.ANA_BAYI, price_group=self.store_group, dealer_no=1,
        )
        self.ahmad_wallet = Wallet.objects.create(
            tenant=self.tenant, user=self.ahmad, balance=Decimal("100"),
        )

        # مجموعة أحمد لدكاكينه: يبيعهم الباقة بـ 10
        self.group = AgentPriceGroup.objects.create(
            tenant=self.tenant, agent=self.ahmad, name="ذهبية",
        )
        AgentProductPrice.objects.create(
            tenant=self.tenant, group=self.group, product=self.product, price=Decimal("10.00"),
        )

        self.shop = User.objects.create(
            login_id="shop", name="محل النور", tenant=self.tenant, role=User.Role.BAYI,
            parent=self.ahmad, agent_price_group=self.group,
            price_group=self.other_group,   # مجموعة المتجر لا تعنيه: وكيله يسعّره
            dealer_no=2,
        )
        self.shop_wallet = Wallet.objects.create(
            tenant=self.tenant, user=self.shop, balance=Decimal("50"),
        )

    def _balances(self):
        self.shop_wallet.refresh_from_db()
        self.ahmad_wallet.refresh_from_db()
        return self.shop_wallet.balance, self.ahmad_wallet.balance

    def test_order_moves_all_three_legs(self):
        order = create_order(self.shop, self.product)

        self.assertEqual(order.buyer_price, Decimal("10.00"))   # دفع الدكان
        self.assertEqual(order.sell_price, Decimal("8.00"))     # قبض المتجر
        self.assertEqual(order.agent_id, self.ahmad.id)
        self.assertEqual(order.agent_profit, Decimal("2.00"))   # ربح أحمد
        self.assertEqual(order.profit, Decimal("2.00"))         # ربح المتجر (8−6)

        shop, ahmad = self._balances()
        self.assertEqual(shop, Decimal("40.00"))    # 50 − 10
        self.assertEqual(ahmad, Decimal("102.00"))  # 100 + 10 − 8

    def test_store_group_of_the_shop_is_ignored(self):
        """سعر الدكان من وكيله حصراً — لا من مجموعته عند صاحب المتجر."""
        order = create_order(self.shop, self.product)
        self.assertEqual(order.buyer_price, Decimal("10.00"))   # لا 11.00

    def test_independent_dealer_buys_from_the_store(self):
        solo = User.objects.create(
            login_id="solo", name="دكان مستقلّ", tenant=self.tenant,
            role=User.Role.BAYI, price_group=self.other_group, dealer_no=3,
        )
        wallet = Wallet.objects.create(tenant=self.tenant, user=solo, balance=Decimal("50"))

        order = create_order(solo, self.product)
        self.assertIsNone(order.agent_id)
        self.assertEqual(order.buyer_price, Decimal("11.00"))
        self.assertEqual(order.sell_price, Decimal("11.00"))
        self.assertEqual(order.agent_profit, Decimal("0"))
        wallet.refresh_from_db()
        self.assertEqual(wallet.balance, Decimal("39.00"))
        self.ahmad_wallet.refresh_from_db()
        self.assertEqual(self.ahmad_wallet.balance, Decimal("100"))   # لم تُمَسّ

    def test_shop_without_a_group_pays_the_agent_cost(self):
        """بلا تسعير من وكيله يشتري بسعر تكلفة وكيله — لا بأرخص منها."""
        self.shop.agent_price_group = None
        self.shop.save(update_fields=["agent_price_group"])

        order = create_order(self.shop, self.product)
        self.assertEqual(order.buyer_price, Decimal("8.00"))
        self.assertEqual(order.agent_profit, Decimal("0.00"))
        shop, ahmad = self._balances()
        self.assertEqual(shop, Decimal("42.00"))
        self.assertEqual(ahmad, Decimal("100.00"))   # قبض 8 ودفع 8

    def test_cancelling_reverses_both_legs(self):
        order = create_order(self.shop, self.product)
        cancel_order(order)

        shop, ahmad = self._balances()
        self.assertEqual(shop, Decimal("50.00"))     # عاد كما كان
        self.assertEqual(ahmad, Decimal("100.00"))   # لا ربح على طلب ملغى

    def test_re_accepting_a_cancelled_order_re_applies_both_legs(self):
        order = create_order(self.shop, self.product)
        cancel_order(order)
        order.refresh_from_db()
        execute_order(order)

        shop, ahmad = self._balances()
        self.assertEqual(shop, Decimal("40.00"))
        self.assertEqual(ahmad, Decimal("102.00"))
        self.assertEqual(Order.objects.get(pk=order.pk).status, Order.Status.SUCCESS)

    def test_agent_profit_is_independent_of_provider_cost(self):
        """تكلفة المزوّد تمسّ ربح المتجر وحده، لا ربح الوكيل."""
        order = create_order(self.shop, self.product)
        order.cost_price = Decimal("7.00")
        order.profit = order.sell_price - order.cost_price
        order.save(update_fields=["cost_price", "profit"])

        order.refresh_from_db()
        self.assertEqual(order.profit, Decimal("1.00"))
        self.assertEqual(order.agent_profit, Decimal("2.00"))


class AgentPriceGroupApiTest(APITestCase):
    """لوحة الوكيل الكبير: مجموعاته وأسعاره وربط دكاكينه — كلّها مقيّدة بشجرته."""

    def setUp(self):
        self.tenant = Tenant.objects.create(subdomain="tg", name="متجر", base_currency="USD")
        self.group_store = PriceGroup.objects.create(tenant=self.tenant, name="كبار")
        self.game = Game.objects.create(tenant=self.tenant, name="PUBG")
        self.product = Product.objects.create(
            tenant=self.tenant, game=self.game, name="60 UC",
            cost_price=Decimal("6.00"), recommended_price=Decimal("12.00"),
        )
        ProductPrice.objects.create(
            tenant=self.tenant, product=self.product,
            price_group=self.group_store, price=Decimal("8.00"),
        )
        self.ahmad = User.objects.create(
            login_id="ahmad2", name="أحمد", tenant=self.tenant,
            role=User.Role.ANA_BAYI, price_group=self.group_store, dealer_no=1,
        )
        Wallet.objects.create(tenant=self.tenant, user=self.ahmad)
        self.shop = User.objects.create(
            login_id="shop2", name="دكان", tenant=self.tenant, role=User.Role.BAYI,
            parent=self.ahmad, dealer_no=2,
        )
        Wallet.objects.create(tenant=self.tenant, user=self.shop, balance=Decimal("50"))
        self.client.force_authenticate(user=self.ahmad)

    def test_create_group_price_it_and_attach_a_shop(self):
        r = self.client.post("/api/agent/price-groups/", {"name": "ذهبية"}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        gid = r.json()["id"]

        rows = self.client.get("/api/agent/price-groups/prices/", {"group": gid}).json()
        self.assertEqual(rows["results"][0]["cost"], "8.00")
        self.assertEqual(rows["results"][0]["price"], "")     # لم يُسعَّر بعد

        r = self.client.post(
            "/api/agent/price-groups/prices/",
            {"group": gid, "product": self.product.id, "price": "10"}, format="json",
        )
        self.assertEqual(r.status_code, 200, r.content)

        r = self.client.post(
            "/api/agent/dealer-group/",
            {"dealer": self.shop.id, "price_group": gid}, format="json",
        )
        self.assertEqual(r.status_code, 200, r.content)
        self.shop.refresh_from_db()
        self.assertEqual(self.shop.agent_price_group_id, gid)

        order = create_order(self.shop, self.product)
        self.assertEqual(order.buyer_price, Decimal("10.00"))

    def test_price_below_own_cost_is_refused(self):
        gid = self.client.post(
            "/api/agent/price-groups/", {"name": "خاسرة"}, format="json",
        ).json()["id"]
        r = self.client.post(
            "/api/agent/price-groups/prices/",
            {"group": gid, "product": self.product.id, "price": "5"}, format="json",
        )
        self.assertEqual(r.status_code, 400)
        self.assertIn("تكلفتك", r.json()["detail"])

    def test_cannot_touch_another_agents_shop(self):
        other = User.objects.create(
            login_id="other", name="كبير آخر", tenant=self.tenant,
            role=User.Role.ANA_BAYI, dealer_no=3,
        )
        foreign = User.objects.create(
            login_id="foreign", name="دكان غريب", tenant=self.tenant,
            role=User.Role.BAYI, parent=other, dealer_no=4,
        )
        gid = self.client.post(
            "/api/agent/price-groups/", {"name": "ذهبية"}, format="json",
        ).json()["id"]
        r = self.client.post(
            "/api/agent/dealer-group/",
            {"dealer": foreign.id, "price_group": gid}, format="json",
        )
        self.assertEqual(r.status_code, 404)

    def test_a_shop_cannot_manage_price_groups(self):
        self.client.force_authenticate(user=self.shop)
        self.assertEqual(self.client.get("/api/agent/price-groups/").status_code, 403)


class BigAgentPanelNumbersTest(APITestCase):
    """لوحة الوكيل الكبير تعرض **ربحه هو** لا ربح صاحب المتجر."""

    def setUp(self):
        self.tenant = Tenant.objects.create(subdomain="tp", name="متجر", base_currency="USD")
        store_group = PriceGroup.objects.create(tenant=self.tenant, name="كبار")
        self.game = Game.objects.create(tenant=self.tenant, name="PUBG")
        self.product = Product.objects.create(
            tenant=self.tenant, game=self.game, name="60 UC",
            cost_price=Decimal("6.00"), recommended_price=Decimal("12.00"),
        )
        ProductPrice.objects.create(
            tenant=self.tenant, product=self.product,
            price_group=store_group, price=Decimal("8.00"),
        )
        self.ahmad = User.objects.create(
            login_id="ahmad3", name="أحمد", tenant=self.tenant,
            role=User.Role.ANA_BAYI, price_group=store_group, dealer_no=1,
        )
        Wallet.objects.create(tenant=self.tenant, user=self.ahmad, balance=Decimal("100"))
        group = AgentPriceGroup.objects.create(
            tenant=self.tenant, agent=self.ahmad, name="ذهبية",
        )
        AgentProductPrice.objects.create(
            tenant=self.tenant, group=group, product=self.product, price=Decimal("10.00"),
        )
        self.shop = User.objects.create(
            login_id="shop3", name="دكان", tenant=self.tenant, role=User.Role.BAYI,
            parent=self.ahmad, agent_price_group=group, dealer_no=2,
        )
        Wallet.objects.create(tenant=self.tenant, user=self.shop, balance=Decimal("50"))

        order = create_order(self.shop, self.product)
        execute_order(order)
        self.client.force_authenticate(user=self.ahmad)

    def test_summary_shows_the_agents_own_profit(self):
        data = self.client.get("/api/agent/summary/").json()
        self.assertEqual(data["profit"], "2.00")    # لا 2.00 للمتجر مصادفةً؟ 8−6=2
        self.assertEqual(data["orders"], 1)

    def test_orders_list_shows_what_the_shop_paid_him(self):
        row = self.client.get("/api/agent/orders/").json()["results"][0]
        self.assertEqual(row["sell_price"], "10.00")   # دفع دكانه 10
        self.assertEqual(row["profit"], "2.00")        # وربح هو 2


class AgentWalletTransferTest(APITestCase):
    """شحن الوكيل الكبير لدكانه: حوالة من محفظته لا هبة من العدم."""

    def setUp(self):
        self.tenant = Tenant.objects.create(subdomain="tw", name="متجر", base_currency="USD")
        self.ahmad = User.objects.create(
            login_id="ahmad4", name="أحمد", tenant=self.tenant,
            role=User.Role.ANA_BAYI, dealer_no=1,
        )
        self.agent_wallet = Wallet.objects.create(
            tenant=self.tenant, user=self.ahmad, balance=Decimal("100"),
        )
        self.shop = User.objects.create(
            login_id="shop4", name="دكان", tenant=self.tenant,
            role=User.Role.BAYI, parent=self.ahmad, dealer_no=2,
        )
        self.shop_wallet = Wallet.objects.create(
            tenant=self.tenant, user=self.shop, balance=Decimal("0"),
        )
        self.client.force_authenticate(user=self.ahmad)

    def _balances(self):
        self.agent_wallet.refresh_from_db()
        self.shop_wallet.refresh_from_db()
        return self.agent_wallet.balance, self.shop_wallet.balance

    def test_topup_moves_money_from_the_agent(self):
        r = self.client.post(
            f"/api/agent/dealers/{self.shop.id}/wallet/",
            {"action": "topup", "amount": "30"}, format="json",
        )
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(self._balances(), (Decimal("70"), Decimal("30")))

    def test_deduct_returns_money_to_the_agent(self):
        self.client.post(
            f"/api/agent/dealers/{self.shop.id}/wallet/",
            {"action": "topup", "amount": "30"}, format="json",
        )
        r = self.client.post(
            f"/api/agent/dealers/{self.shop.id}/wallet/",
            {"action": "deduct", "amount": "10"}, format="json",
        )
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(self._balances(), (Decimal("80"), Decimal("20")))

    def test_cannot_send_more_than_he_owns(self):
        r = self.client.post(
            f"/api/agent/dealers/{self.shop.id}/wallet/",
            {"action": "topup", "amount": "500"}, format="json",
        )
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self._balances(), (Decimal("100"), Decimal("0")))   # لا ساق نصفية

    def test_cannot_touch_a_shop_that_is_not_his(self):
        other = User.objects.create(
            login_id="other4", name="كبير آخر", tenant=self.tenant,
            role=User.Role.ANA_BAYI, dealer_no=3,
        )
        foreign = User.objects.create(
            login_id="foreign4", name="دكان غريب", tenant=self.tenant,
            role=User.Role.BAYI, parent=other, dealer_no=4,
        )
        Wallet.objects.create(tenant=self.tenant, user=foreign)
        r = self.client.post(
            f"/api/agent/dealers/{foreign.id}/wallet/",
            {"action": "topup", "amount": "10"}, format="json",
        )
        self.assertEqual(r.status_code, 404)

    def test_statement_lists_the_shop_transactions(self):
        self.client.post(
            f"/api/agent/dealers/{self.shop.id}/wallet/",
            {"action": "topup", "amount": "30", "note": "دفعة أولى"}, format="json",
        )
        data = self.client.get(f"/api/agent/dealers/{self.shop.id}/statement/").json()
        self.assertEqual(data["dealer"]["balance"], "30.00")
        self.assertEqual(data["results"][0]["note"], "دفعة أولى")

    def test_zero_or_negative_amount_is_refused(self):
        for bad in ("0", "-5"):
            r = self.client.post(
                f"/api/agent/dealers/{self.shop.id}/wallet/",
                {"action": "topup", "amount": bad}, format="json",
            )
            self.assertEqual(r.status_code, 400, bad)


class LossGuardVisibilityTest(TestCase):
    """
    الحجب يُري الخسارة ولا يُخفيها، ويُعصى إن أصرّ صاحب المتجر.

    الحماية وظيفتها أن **توقف وتنبّه** لا أن تمنع إلى الأبد: تُثبت التكلفة
    الحقيقية على الطلب ليرى صاحبه حجم الخسارة، ثم تُفسح له إن وجّه بيده.
    """

    def setUp(self):
        from catalog.models import PriceGroup, ProductPrice

        self.alaya = Tenant.objects.create(subdomain="alaya", name="علايا", base_currency="USD")
        self.islam = Tenant.objects.create(subdomain="islam", name="إسلام", base_currency="USD")

        a_group = PriceGroup.objects.create(tenant=self.alaya, name="عادية")
        a_game = Game.objects.create(tenant=self.alaya, name="PUBG")
        self.a_product = Product.objects.create(
            tenant=self.alaya, game=a_game, name="60 UC",
            cost_price=Decimal("28"), recommended_price=Decimal("35"),
        )
        ProductPrice.objects.create(tenant=self.alaya, product=self.a_product,
                                    price_group=a_group, price=Decimal("32"))
        self.at_alaya = User.objects.create(
            login_id="islam_at_alaya", name="متجر إسلام", tenant=self.alaya,
            role=User.Role.BAYI, price_group=a_group, internal_supply_allowed=True, dealer_no=1,
        )
        Wallet.objects.create(tenant=self.alaya, user=self.at_alaya,
                              balance=Decimal("1000"), credit_limit=Decimal("-5000"))

        self.provider = Provider.objects.create(
            tenant=self.islam, name="علايا", type=Provider.Type.SAME_SYSTEM,
            config={"dealer_login": "islam_at_alaya"}, loss_guard=True,
        )
        i_group = PriceGroup.objects.create(tenant=self.islam, name="عادية")
        i_game = Game.objects.create(tenant=self.islam, name="PUBG")
        self.i_product = Product.objects.create(
            tenant=self.islam, game=i_game, name="60 UC",
            cost_price=Decimal("0.85"), recommended_price=Decimal("2"),
            execution_type=Product.Execution.AUTO,
            provider=self.provider, provider_package_id=str(self.a_product.id),
        )
        ProductPrice.objects.create(tenant=self.islam, product=self.i_product,
                                    price_group=i_group, price=Decimal("1"))
        self.shop = User.objects.create(
            login_id="tabe3", name="تابع لإسلام", tenant=self.islam,
            role=User.Role.BAYI, price_group=i_group, dealer_no=1,
        )
        Wallet.objects.create(tenant=self.islam, user=self.shop, balance=Decimal("1000"))

    def _place(self):
        from orders import services
        order = services.create_order(self.shop, self.i_product, player_id="5566")
        services.dispatch_order(order)
        order.refresh_from_db()
        return order

    def test_blocked_order_shows_the_real_cost_and_a_negative_profit(self):
        """
        كان يبقى السعر المقدَّر (0.85) فيقرأ صاحب المتجر «ربح 0.15» على طلبٍ
        حُجب لأنه يخسر 31 — والخسارة هي سبب الحجب، فلا معنى لإخفائها.
        """
        order = self._place()
        self.assertEqual(order.status, Order.Status.STUCK)
        self.assertEqual(order.cost_price, Decimal("32.00"))
        self.assertEqual(order.profit, Decimal("-31.00"))
        self.assertIn("حماية الخسارة", order.api_response)

    def test_nothing_was_sent_while_it_was_blocked(self):
        self._place()
        self.assertEqual(Order.objects.filter(tenant=self.alaya).count(), 0)
        self.assertEqual(Wallet.objects.get(user=self.at_alaya).balance, Decimal("1000"))

    def test_manual_dispatch_overrides_the_guard(self):
        """أصرّ صاحب المتجر بعد أن رأى الخسارة — فالنظام لا يعاند صاحبه."""
        from orders import services

        order = self._place()
        services.dispatch_to_provider(order, self.provider)
        order.refresh_from_db()

        self.assertEqual(order.status, Order.Status.PROCESSING)
        self.assertEqual(Order.objects.filter(tenant=self.alaya).count(), 1)
        self.assertEqual(Wallet.objects.get(user=self.at_alaya).balance, Decimal("968.00"))
        self.assertEqual(order.cost_price, Decimal("32.00"))

    def test_automatic_retry_still_obeys_the_guard(self):
        """التجاوز للتوجيه اليدوي وحده — لا لإعادة التشغيل التلقائي."""
        from orders import services

        order = self._place()
        services.dispatch_order(order)          # المسار التلقائي مرّةً أخرى
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.STUCK)
        self.assertEqual(Order.objects.filter(tenant=self.alaya).count(), 0)

    def test_a_profitable_order_is_untouched(self):
        from catalog.models import ProductPrice

        ProductPrice.objects.filter(product=self.i_product).update(price=Decimal("40"))
        order = self._place()
        self.assertEqual(order.status, Order.Status.PROCESSING)
        self.assertEqual(order.cost_price, Decimal("32.00"))
        self.assertEqual(order.profit, Decimal("8.00"))


class DealerNeverSeesStuckTest(APITestCase):
    """
    «عالق» حالةُ متجرٍ لا حالةُ وكيل — تعثُّرُ توجيهِ صاحب المتجر شأنه هو،
    ولا حيلة للوكيل فيه. فيراها انتظاراً، وتبقى ظاهرةً في لوحة المتجر.
    """

    def setUp(self):
        self.tenant = Tenant.objects.create(subdomain="t1", name="متجر", base_currency="USD")
        self.game = Game.objects.create(tenant=self.tenant, name="PUBG")
        self.product = Product.objects.create(
            tenant=self.tenant, game=self.game, name="60 UC",
            cost_price=Decimal("6"), recommended_price=Decimal("10"),
        )
        self.dealer = User.objects.create(
            login_id="d1", name="وكيل", tenant=self.tenant, role=User.Role.BAYI, dealer_no=1)
        Wallet.objects.create(tenant=self.tenant, user=self.dealer, balance=Decimal("100"))
        self.admin = User.objects.create(
            login_id="a1", name="مدير", tenant=self.tenant,
            role=User.Role.TENANT_ADMIN, is_staff=True)

        from orders import services
        self.order = services.create_order(self.dealer, self.product)
        Order.objects.filter(pk=self.order.pk).update(status=Order.Status.STUCK)

    def test_dealer_reads_it_as_pending(self):
        self.client.force_authenticate(self.dealer)
        row = self.client.get("/api/store/orders/").json()["results"][0]
        self.assertEqual(row["status"], "pending")
        self.assertEqual(row["status_label"], "قيد الانتظار")

    def test_the_word_stuck_never_reaches_the_dealer(self):
        self.client.force_authenticate(self.dealer)
        body = self.client.get("/api/store/orders/").content.decode()
        self.assertNotIn("stuck", body)
        self.assertNotIn("عالق", body)

    def test_the_pending_filter_still_finds_it(self):
        """وإلّا اختفى طلبه من الفلترين معاً فظنّه ضائعاً."""
        self.client.force_authenticate(self.dealer)
        rows = self.client.get("/api/store/orders/", {"status": "pending"}).json()["results"]
        self.assertEqual(len(rows), 1)

    def test_the_summary_counts_it_as_pending(self):
        self.client.force_authenticate(self.dealer)
        self.assertEqual(self.client.get("/api/store/summary/").json()["pending"], 1)

    def test_the_status_chips_count_it_as_pending(self):
        """عدّادات الشرائح في لوحة الوكيل تجمع العالق مع الانتظار — ولا مفتاح «stuck»."""
        self.client.force_authenticate(self.dealer)
        counts = self.client.get("/api/store/orders/", {"status": "success"}).json()["counts"]
        self.assertEqual(counts, {"all": 1, "pending": 1})

    def test_search_and_dates_narrow_the_list(self):
        Order.objects.filter(pk=self.order.pk).update(player_id="5121234567")
        self.client.force_authenticate(self.dealer)
        get = lambda **p: self.client.get("/api/store/orders/", p).json()["count"]
        self.assertEqual(get(q="51212"), 1)
        self.assertEqual(get(q="PUBG"), 1)
        self.assertEqual(get(q="لا-يوجد"), 0)
        self.assertEqual(get(date_from="2999-01-01"), 0)
        self.assertEqual(get(date_to="2999-01-01"), 1)

    def test_the_store_owner_still_sees_stuck(self):
        """هو من يعالجها، فلا تُخفى عنه."""
        self.client.force_authenticate(self.admin)
        rows = self.client.get("/api/orders/").json()["results"]
        self.assertEqual(rows[0]["status"], "stuck")
        self.assertEqual(rows[0]["status_label"], "عالق")


class StoreWalletStatementTest(APITestCase):
    """كشف حركات الوكيل: فلترٌ بالنوع والتاريخ، وحركة الطلب تحمل طلبها للتفاصيل."""

    def setUp(self):
        self.tenant = Tenant.objects.create(subdomain="w1", name="متجر", base_currency="USD")
        game = Game.objects.create(tenant=self.tenant, name="PUBG")
        product = Product.objects.create(
            tenant=self.tenant, game=game, name="60 UC",
            cost_price=Decimal("6"), recommended_price=Decimal("10"),
        )
        self.dealer = User.objects.create(
            login_id="w-d1", name="وكيل", tenant=self.tenant, role=User.Role.BAYI, dealer_no=1)
        Wallet.objects.create(tenant=self.tenant, user=self.dealer, balance=Decimal("100"))
        self.order = create_order(self.dealer, product)
        self.client.force_authenticate(self.dealer)

    def test_order_debit_carries_its_order(self):
        rows = self.client.get("/api/store/wallet/").json()["results"]
        debit = next(r for r in rows if r["type"] == "order_debit")
        self.assertEqual(debit["order"]["id"], self.order.id)
        self.assertIn("balance_before", debit)

    def test_type_and_date_filters(self):
        get = lambda **p: self.client.get("/api/store/wallet/", p).json()
        body = get(type="topup")
        self.assertEqual(body["results"], [])
        self.assertGreaterEqual(body["counts"]["order_debit"], 1)
        self.assertEqual(len(get(type="order_debit")["results"]), body["counts"]["order_debit"])
        self.assertEqual(get(date_from="2999-01-01")["counts"]["all"], 0)



class StoreCatalogNotesTest(APITestCase):
    """وصف اللعبة وملاحظة الوكيل يصلان إلى كتالوج الوكيل."""

    def test_description_and_dealer_note_reach_the_agent(self):
        t = Tenant.objects.create(subdomain="cn", name="متجر", base_currency="USD")
        g = Game.objects.create(tenant=t, name="PUBG", description="باقات ببجي عالمي",
                                dealer_note="الطلب لا يسترجع")
        Product.objects.create(tenant=t, game=g, name="60 UC", cost_price=Decimal("1"),
                               recommended_price=Decimal("2"))
        d = User.objects.create(login_id="cn-d", name="وكيل", tenant=t, role=User.Role.BAYI, dealer_no=1)
        Wallet.objects.create(tenant=t, user=d)
        self.client.force_authenticate(d)
        game = self.client.get("/api/store/catalog/").json()["games"][0]
        self.assertEqual(game["description"], "باقات ببجي عالمي")
        self.assertEqual(game["dealer_note"], "الطلب لا يسترجع")



class ProcessingLooksPendingTest(APITestCase):
    """«قيد التنفيذ» و«قيد الانتظار» عند الوكيل حالةٌ واحدة: قيد الانتظار."""

    def test_processing_is_pending_for_the_dealer(self):
        t = Tenant.objects.create(subdomain="pp", name="متجر", base_currency="USD")
        g = Game.objects.create(tenant=t, name="PUBG")
        p = Product.objects.create(tenant=t, game=g, name="60 UC", cost_price=Decimal("1"), recommended_price=Decimal("2"))
        d = User.objects.create(login_id="pp-d", name="وكيل", tenant=t, role=User.Role.BAYI, dealer_no=1)
        Wallet.objects.create(tenant=t, user=d, balance=Decimal("100"))
        o = create_order(d, p)
        Order.objects.filter(pk=o.pk).update(status=Order.Status.PROCESSING)
        self.client.force_authenticate(d)
        body = self.client.get("/api/store/orders/", {"status": "pending"}).json()
        self.assertEqual(body["count"], 1)
        self.assertEqual(body["results"][0]["status"], "pending")
        self.assertEqual(body["results"][0]["status_label"], "قيد الانتظار")
        self.assertEqual(body["counts"], {"all": 1, "pending": 1})
        self.assertEqual(self.client.get("/api/store/summary/").json()["pending"], 1)


class AmountSaleTest(APITestCase):
    """
    الباقة «بالكمية»: أسعارها لكل qty_unit وحدة، وكل مبلغٍ في الطلب مضروبٌ في
    الكمية ÷ qty_unit — الخصم، والتكلفة، وما يقبضه المتجر، وحماية الخسارة،
    والكمية تصل المزوّد كما كتبها الوكيل. ومن لا يدعم الكمية لا تُرسَل إليه.
    """

    def setUp(self):
        from unittest.mock import patch  # noqa: F401
        self.t = Tenant.objects.create(subdomain="am", name="متجر", base_currency="USD",
                                       exchange_rates={"TRY": "40"})
        g = Game.objects.create(tenant=self.t, name="4FUN CHAT")
        # 2.00$ لكل 1000 وحدة، وتكلفتها 1.50$
        self.p = Product.objects.create(
            tenant=self.t, game=g, name="4FUN CHAT", cost_price=Decimal("1.50"),
            recommended_price=Decimal("2.00"), sale_type="amount",
            qty_min=15000, qty_max=15000000, qty_unit=1000)
        self.d = User.objects.create(login_id="am-d", name="وكيل", tenant=self.t,
                                     role=User.Role.BAYI, dealer_no=1)
        self.w = Wallet.objects.create(tenant=self.t, user=self.d, balance=Decimal("100"))

    def test_prices_scale_with_quantity(self):
        o = create_order(self.d, self.p, quantity="15,000")
        self.assertEqual(o.quantity, 15000)
        self.assertEqual(o.buyer_price, Decimal("30.00"))   # 2.00 × 15
        self.assertEqual(o.cost_price, Decimal("22.50"))    # 1.50 × 15
        self.assertEqual(o.profit, Decimal("7.50"))
        self.assertEqual(o.dealer_sell_price, Decimal("30.00"))
        self.w.refresh_from_db()
        self.assertEqual(self.w.balance, Decimal("70.00"))

    def test_quantity_outside_the_range_is_refused_before_any_debit(self):
        from .services import OrderError
        for bad in (14999, 15000001, "", "abc"):
            with self.assertRaises(OrderError):
                create_order(self.d, self.p, quantity=bad)
        self.w.refresh_from_db()
        self.assertEqual(self.w.balance, Decimal("100"))

    def test_a_fixed_package_ignores_quantity(self):
        fixed = Product.objects.create(tenant=self.t, game=self.p.game, name="60 UC",
                                       cost_price=Decimal("1"), recommended_price=Decimal("2"))
        o = create_order(self.d, fixed, quantity=500)
        self.assertEqual((o.quantity, o.buyer_price), (1, Decimal("2.00")))

    def test_zdk_receives_the_real_quantity(self):
        from unittest.mock import MagicMock, patch
        from catalog.models import ProductLink
        from .services import dispatch_order
        prov = Provider.objects.create(tenant=self.t, name="بركات", type=Provider.Type.CARD_STORE,
                                       currency="TRY", loss_guard=False,
                                       config={"code": "zdk", "api_token": "x"})
        ProductLink.objects.create(tenant=self.t, product=self.p, provider=prov, package_id="229")
        self.p.provider = prov
        self.p.save()
        o = create_order(self.d, self.p, quantity=20000)
        resp = MagicMock()
        resp.json.return_value = {"status": "OK", "data": {"status": "wait", "order_id": "1"}}
        with patch("providers.adapters.zdk.requests.get", return_value=resp) as get:
            dispatch_order(o)
        self.assertEqual(get.call_args.kwargs["params"]["qty"], "20000")

    def test_a_provider_without_quantity_support_is_skipped(self):
        from .services import dispatch_order
        znet = Provider.objects.create(tenant=self.t, name="علايا", type=Provider.Type.SAME_SYSTEM,
                                       currency="TRY", config={"code": "znet"})
        self.p.provider = znet
        self.p.save()
        o = dispatch_order(create_order(self.d, self.p, quantity=15000))
        self.assertEqual(o.status, Order.Status.STUCK)
        self.assertIn("لا يدعم البيع بالكمية", o.api_response)

    def test_loss_guard_compares_block_price_times_quantity(self):
        from catalog.models import ProductLink
        from .services import dispatch_order
        prov = Provider.objects.create(tenant=self.t, name="بركات", type=Provider.Type.CARD_STORE,
                                       currency="TRY", config={"code": "zdk", "api_token": "x"})
        # المزوّد: 2.50$ لكل 1000 — والطلب يُباع بـ2.00$ لكل 1000 ⇒ خاسر
        ProductLink.objects.create(tenant=self.t, product=self.p, provider=prov, package_id="229",
                                   extra={"price": "2.50"})
        self.p.provider = prov
        self.p.save()
        o = dispatch_order(create_order(self.d, self.p, quantity=15000))
        self.assertEqual(o.status, Order.Status.STUCK)
        self.assertIn("37.50 > سعر البيع 30.00", o.api_response)

    def test_agent_store_buys_with_quantity(self):
        self.client.force_authenticate(self.d)
        game = self.client.get("/api/store/catalog/").json()["games"][0]
        prod = game["products"][0]
        self.assertEqual((prod["sale_type"], prod["qty_min"], prod["qty_unit"]), ("amount", 15000, 1000))
        r = self.client.post("/api/store/buy/", {"product": self.p.id, "quantity": 50000}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(Order.objects.get().quantity, 50000)
        self.assertEqual(Order.objects.get().buyer_price, Decimal("100.00"))

    def test_manual_link_price_from_catalog_is_scaled_to_the_block(self):
        """كتالوج المزوّد يسعّر الوحدة (0.05 ل.ت) ⇒ لكل 1000 = 50 ل.ت = 1.25$."""
        from catalog.models import ProductLink
        prov = Provider.objects.create(tenant=self.t, name="بركات", type=Provider.Type.CARD_STORE,
                                       currency="TRY", config={"code": "zdk", "api_token": "x"})
        admin = User.objects.create(login_id="am-a", name="م", tenant=self.t, role=User.Role.TENANT_ADMIN)
        self.client.force_authenticate(admin)
        self.client.post("/api/catalog/product-links/", {"product": self.p.id, "provider": prov.id,
                         "package_id": "229", "extra": {"price": "0.05"}}, format="json")
        self.assertEqual(ProductLink.objects.get().extra["price"], "1.25")


class AmountLinkTypeGuardTest(AmountSaleTest):
    """باقةٌ بالكمية لا تُربط بباقةٍ ثابتة لدى المزوّد — لا عند الحفظ ولا عند الإرسال."""

    def _barakat(self, **extra):
        from catalog.models import ProductLink
        prov = Provider.objects.create(tenant=self.t, name="بركات", type=Provider.Type.CARD_STORE,
                                       currency="TRY", loss_guard=False,
                                       config={"code": "zdk", "api_token": "x"})
        if extra:
            ProductLink.objects.create(tenant=self.t, product=self.p, provider=prov,
                                       package_id="2075", extra=extra)
        return prov

    def test_saving_a_mismatched_link_is_refused(self):
        prov = self._barakat()
        admin = User.objects.create(login_id="g-a", name="م", tenant=self.t, role=User.Role.TENANT_ADMIN)
        self.client.force_authenticate(admin)
        r = self.client.post("/api/catalog/product-links/", {"product": self.p.id, "provider": prov.id,
                             "package_id": "2075", "extra": {"type": "package"}}, format="json")
        self.assertEqual(r.status_code, 400)
        ok = self.client.post("/api/catalog/product-links/", {"product": self.p.id, "provider": prov.id,
                              "package_id": "229", "extra": {"type": "amount"}}, format="json")
        self.assertEqual(ok.status_code, 201)

    def test_a_mismatched_link_never_reaches_zdk(self):
        from unittest.mock import patch
        from .services import dispatch_order
        prov = self._barakat(type="package")
        self.p.provider = prov
        self.p.save()
        with patch("providers.adapters.zdk.requests.get") as get:
            o = dispatch_order(create_order(self.d, self.p, quantity=15000))
        get.assert_not_called()
        self.assertIn("الربط خاطئ", o.api_response)

    def test_internal_markers_are_not_sent_as_params(self):
        from unittest.mock import MagicMock, patch
        from .services import dispatch_order
        prov = self._barakat(type="amount", auto=True, price="1.00")
        self.p.provider = prov
        self.p.save()
        resp = MagicMock()
        resp.json.return_value = {"status": "OK", "data": {"status": "wait", "order_id": "1"}}
        with patch("providers.adapters.zdk.requests.get", return_value=resp) as get:
            dispatch_order(create_order(self.d, self.p, quantity=15000))
        params = get.call_args.kwargs["params"]
        self.assertNotIn("auto", params)
        self.assertNotIn("type", params)
