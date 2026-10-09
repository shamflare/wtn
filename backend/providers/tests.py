"""
اختبارات المزوّد الداخلي («نفس النظام») — وحارسها الأول: **الإذن**.

رقم الدخول فريد عبر المنصّة كلّها وسهل التخمين (`bayi003`). فلولا إذنٌ صريح على
حساب الوكيل لاستطاع أيّ صاحب متجر أن يضيف مزوّداً داخلياً برقم دخول وكيلٍ ليس
له — ثم ينفق رصيده. الإذن يضعه صاحب المتجر المورّد بيده على الحساب الذي فتحه
لهذا الغرض وحده.
"""
from decimal import Decimal

from django.test import TestCase
from rest_framework.test import APITestCase

from catalog.models import Game, Product
from core.models import Tenant, User, Wallet
from orders.models import Order

from .adapters.tenant import InternalTenantAdapter
from .models import Provider


class InternalSupplyPermissionTest(TestCase):
    """متجران: علايا (المورّد) وإسلام (المشتري)."""

    def setUp(self):
        self.alaya = Tenant.objects.create(subdomain="alaya", name="علايا", base_currency="USD")
        self.islam = Tenant.objects.create(subdomain="islam", name="إسلام", base_currency="USD")

        # وكيل بشريّ عند علايا — لا علاقة له بإسلام ولم يُؤذن له بشيء
        self.human = User.objects.create(
            login_id="bayi003", name="abd shop", tenant=self.alaya, role=User.Role.BAYI,
        )
        Wallet.objects.create(tenant=self.alaya, user=self.human, balance=Decimal("25000"))

        # الحساب الذي فتحته علايا لمتجر إسلام — مأذون
        self.linked = User.objects.create(
            login_id="islam_at_alaya", name="متجر إسلام", tenant=self.alaya,
            role=User.Role.BAYI, internal_supply_allowed=True,
        )
        Wallet.objects.create(tenant=self.alaya, user=self.linked, balance=Decimal("500"))

        # منتج عند علايا + مشترٍ عند إسلام
        game = Game.objects.create(tenant=self.alaya, name="PUBG")
        self.supplier_product = Product.objects.create(
            tenant=self.alaya, game=game, name="60 UC",
            cost_price=Decimal("6"), recommended_price=Decimal("10"),
        )
        self.buyer = User.objects.create(
            login_id="d1", name="وكيل إسلام", tenant=self.islam, role=User.Role.BAYI,
        )
        Wallet.objects.create(tenant=self.islam, user=self.buyer, balance=Decimal("100"))

        self.adapter = InternalTenantAdapter()

    def _provider(self, login):
        return Provider.objects.create(
            tenant=self.islam, name="علايا", type=Provider.Type.SAME_SYSTEM,
            config={"dealer_login": login},
        )

    def _order(self, provider):
        game = Game.objects.create(tenant=self.islam, name="PUBG")
        product = Product.objects.create(
            tenant=self.islam, game=game, name="60 UC",
            cost_price=Decimal("10"), recommended_price=Decimal("14"),
            provider=provider, provider_package_id=str(self.supplier_product.id),
        )
        return Order.objects.create(
            tenant=self.islam, receipt_no=f"T{provider.id}", dealer=self.buyer,
            game=game, product=product,
            cost_price=Decimal("10"), sell_price=Decimal("14"), profit=Decimal("4"),
        )

    # ——— الرفض: حساب غير مأذون ———

    def test_balance_refused_for_unpermitted_dealer(self):
        """الثغرة الأصلية: إسلام يكتب bayi003 فيقرأ رصيد وكيل علايا."""
        res = self.adapter.get_balance({"dealer_login": "bayi003"}, self._provider("bayi003"))
        self.assertFalse(res.ok)
        self.assertIn("غير مأذون", res.note)

    def test_packages_refused_for_unpermitted_dealer(self):
        res = self.adapter.list_packages({"dealer_login": "bayi003"}, self._provider("bayi003"))
        self.assertFalse(res.ok)
        self.assertIn("غير مأذون", res.note)

    def test_order_refused_and_wallet_untouched(self):
        """الأهمّ: لا يُخصم قرش من محفظة الوكيل غير المأذون."""
        provider = self._provider("bayi003")
        order = self._order(provider)
        before = self.human.wallet.balance

        res = self.adapter.place_order(order, provider.config, provider)

        self.assertEqual(res.status, "failed")
        self.assertIn("غير مأذون", res.note)
        self.human.wallet.refresh_from_db()
        self.assertEqual(self.human.wallet.balance, before)
        self.assertEqual(Order.objects.filter(tenant=self.alaya).count(), 0)

    def test_permission_revoked_stops_working(self):
        """سحب الإذن يوقف مزوّداً كان يعمل — لا يبقى نافذاً بحكم الماضي."""
        provider = self._provider("islam_at_alaya")
        self.assertTrue(self.adapter.get_balance(provider.config, provider).ok)

        self.linked.internal_supply_allowed = False
        self.linked.save(update_fields=["internal_supply_allowed"])

        self.assertFalse(self.adapter.get_balance(provider.config, provider).ok)

    # ——— القبول: الحساب المأذون يعمل كما كان ———

    def test_permitted_dealer_balance_and_packages(self):
        provider = self._provider("islam_at_alaya")

        bal = self.adapter.get_balance(provider.config, provider)
        self.assertTrue(bal.ok)
        self.assertEqual(bal.balance, Decimal("500"))

        pkgs = self.adapter.list_packages(provider.config, provider)
        self.assertTrue(pkgs.ok)
        self.assertEqual([p["id"] for p in pkgs.packages], [str(self.supplier_product.id)])

    def test_own_tenant_still_refused(self):
        """الإذن لا يُلغي منع التوجيه إلى المتجر نفسه."""
        mine = User.objects.create(
            login_id="mine", name="وكيلي", tenant=self.islam,
            role=User.Role.BAYI, internal_supply_allowed=True,
        )
        Wallet.objects.create(tenant=self.islam, user=mine, balance=Decimal("50"))
        provider = self._provider("mine")
        res = self.adapter.place_order(self._order(provider), provider.config, provider)
        self.assertEqual(res.status, "failed")
        self.assertIn("متجر آخر", res.note)

    def test_unknown_login_refused(self):
        res = self.adapter.get_balance({"dealer_login": "nope"}, self._provider("nope"))
        self.assertFalse(res.ok)
        self.assertIn("غير موجود", res.note)


class InternalRoundTripTest(TestCase):
    """
    الدورة الكاملة كما جرت حيّاً: دكانٌ يطلب من إسلام ← إسلام يوجّه إلى علايا
    ← علايا تنفّذ **يدوياً بعد حين**. المطلوب أن يصل الخبر إلى إسلام ودكانه.
    """

    def setUp(self):
        from catalog.models import PriceGroup, ProductPrice

        self.alaya = Tenant.objects.create(subdomain="alaya", name="علايا", base_currency="USD")
        self.islam = Tenant.objects.create(subdomain="islam", name="إسلام", base_currency="USD")

        # علايا تبيع حسابَ إسلام الباقةَ بـ 32.00
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

        # إسلام: مزوّد داخلي نحو علايا + منتج بتكلفة مقدَّرة 0.85 وسعر بيع 1.00
        self.provider = Provider.objects.create(
            tenant=self.islam, name="علايا", type=Provider.Type.SAME_SYSTEM,
            config={"dealer_login": "islam_at_alaya"}, loss_guard=False,
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

    def test_supplier_manual_approval_reaches_us(self):
        """**العطل المبلَّغ:** علايا توافق يدوياً ويبقى الطلب عندنا قيد التنفيذ."""
        from orders import services

        order = self._place()
        self.assertEqual(order.status, Order.Status.PROCESSING)

        sup = Order.objects.get(tenant=self.alaya)
        services.execute_order(sup, pin="PIN-777")     # موافقة يدوية عند علايا

        services.sync_pending(self.islam)              # حلقة المراقبة عند إسلام
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.SUCCESS)
        self.assertEqual(order.pin_result, "PIN-777")

    def test_cost_is_the_real_one_at_once_not_the_typed_guess(self):
        """
        تكلفتنا 32.00 (ما خُصم من محفظتنا لدى علايا) لا 0.85 المكتوبة على
        المنتج — ولا تنتظر النجاح، فالمال خرج لحظة الإنشاء.
        """
        order = self._place()
        self.assertEqual(order.cost_price, Decimal("32.00"))
        self.assertEqual(order.profit, Decimal("1.00") - Decimal("32.00"))
        # وخُصم فعلاً من محفظتنا هناك
        self.assertEqual(Wallet.objects.get(user=self.at_alaya).balance, Decimal("968.00"))

    def test_cost_is_not_divided_by_the_lira_rate(self):
        """
        المزوّد الداخلي يسلّم الرقم بعملة دفترنا. تمريره على محوّل الليرة كان
        يقسمه على ~41 فيظهر الطلب رابحاً وهو خاسر.
        """
        self.islam.exchange_rates = {"TRY": "41.5"}
        self.islam.save(update_fields=["exchange_rates"])
        self.assertEqual(self._place().cost_price, Decimal("32.00"))

    def test_cost_crosses_a_currency_border_correctly(self):
        """دفتر علايا بالليرة ودفترنا بالدولار: 1$ = 41.5 ل.ت ⇒ 32 ل.ت = 0.77$."""
        self.alaya.base_currency = "TRY"
        self.alaya.save(update_fields=["base_currency"])
        self.islam.exchange_rates = {"TRY": "41.5"}
        self.islam.save(update_fields=["exchange_rates"])
        self.assertEqual(self._place().cost_price, Decimal("0.77"))

    def test_loss_guard_blocks_before_the_first_order(self):
        """
        نبيع بـ 1.00 ونشتري بـ 32.00 — خسارة. الحماية تمنع **قبل** أوّل طلب:
        السعر في قاعدتنا فلا داعي لخسارة طلبٍ كي نتعلّمه.
        """
        self.provider.loss_guard = True
        self.provider.save(update_fields=["loss_guard"])

        order = self._place()

        self.assertEqual(order.status, Order.Status.STUCK)
        self.assertIn("حماية الخسارة", order.api_response)
        self.assertEqual(Order.objects.filter(tenant=self.alaya).count(), 0)
        self.assertEqual(Wallet.objects.get(user=self.at_alaya).balance, Decimal("1000"))

    def test_loss_guard_lets_a_profitable_order_through(self):
        from catalog.models import ProductPrice

        ProductPrice.objects.filter(product=self.i_product).update(price=Decimal("40"))
        self.provider.loss_guard = True
        self.provider.save(update_fields=["loss_guard"])
        self.assertEqual(self._place().status, Order.Status.PROCESSING)

    def test_supplier_cancellation_refunds_our_dealer(self):
        """علايا تلغي ⇒ المال عاد إلينا هناك، فيعود إلى وكيلنا هنا تلقائياً."""
        from orders import services

        order = self._place()
        before = Wallet.objects.get(user=self.shop).balance

        services.cancel_order(Order.objects.get(tenant=self.alaya))
        services.sync_pending(self.islam)

        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.CANCELLED)
        self.assertEqual(Wallet.objects.get(user=self.shop).balance, before + Decimal("1.00"))

    def test_supplier_stuck_keeps_us_waiting_not_refunded(self):
        """العالق لدى علايا مالُه محجوز هناك — فلا نسترجع لوكيلنا مالاً لم يعد."""
        from orders import services

        order = self._place()
        Order.objects.filter(tenant=self.alaya).update(status=Order.Status.STUCK)
        before = Wallet.objects.get(user=self.shop).balance

        services.sync_pending(self.islam)

        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.PROCESSING)
        self.assertEqual(Wallet.objects.get(user=self.shop).balance, before)


class ProviderCurrencyTest(APITestCase):
    """
    لكل مزوّد عملته. كان النظام يفترضها ليرةً للجميع، فيقسم سعر مزوّدٍ دولاريّ
    على ~41 ويظهر رخيصاً أربعين ضعفاً — ثم تمرّره حماية الخسارة مطمئنّة.
    """

    def setUp(self):
        self.tenant = Tenant.objects.create(
            subdomain="t1", name="متجر", base_currency="USD",
            exchange_rates={"TRY": "41.5"},
        )
        self.admin = User.objects.create(
            login_id="a1", name="مدير", tenant=self.tenant,
            role=User.Role.TENANT_ADMIN, is_staff=True,
        )
        self.client.force_authenticate(self.admin)

    def _provider(self, currency="TRY", **kw):
        return Provider.objects.create(
            tenant=self.tenant, name=kw.pop("name", "مزوّد"),
            type=Provider.Type.CARD_STORE, config={"code": "znet"},
            currency=currency, **kw,
        )

    def test_lira_balance_shows_its_dollar_equivalent(self):
        """100 ل.ت مع 1$ = 41.5 ل.ت ⇒ 2.41$."""
        self._provider("TRY", real_balance=Decimal("100"), debt=Decimal("100"))
        row = self.client.get("/api/providers/").json()[0]
        self.assertEqual(row["currency"], "TRY")
        self.assertEqual(row["real_balance"], "100.00")
        self.assertEqual(row["real_balance_base"], "2.41")
        self.assertEqual(row["debt_base"], "2.41")
        self.assertEqual(row["base_currency"], "USD")

    def test_a_dollar_provider_has_no_second_line(self):
        """عملته عملةُ الدفتر — فسطرٌ ثانٍ يكرّر الرقم نفسه لغوٌ."""
        self._provider("USD", real_balance=Decimal("100"))
        row = self.client.get("/api/providers/").json()[0]
        self.assertIsNone(row["real_balance_base"])

    def test_a_currency_without_a_rate_says_so_instead_of_lying(self):
        self._provider("EUR", real_balance=Decimal("100"))
        row = self.client.get("/api/providers/").json()[0]
        self.assertEqual(row["currency"], "EUR")
        self.assertIsNone(row["real_balance_base"])   # الواجهة تكتب «لا سعر صرف لـEUR»

    def test_totals_convert_before_summing(self):
        """جمعُ ليرةٍ على دولار يخرج رقماً بلا معنى — فيُحوَّل كلٌّ أوّلاً."""
        self._provider("TRY", name="ZNET", real_balance=Decimal("415"))    # = 10$
        self._provider("USD", name="ZDK", real_balance=Decimal("5"))       # = 5$
        totals = self.client.get("/api/providers/totals/").json()
        self.assertEqual(totals["real_balance"], "15.00")
        self.assertEqual(totals["currency"], "USD")
        self.assertEqual(totals["unconverted"], [])

    def test_totals_name_what_they_could_not_convert(self):
        """الإسقاط الصامت يجعل المجموع كاذباً بهدوء."""
        self._provider("USD", name="ZDK", real_balance=Decimal("5"))
        self._provider("EUR", name="آخر", real_balance=Decimal("99"))
        totals = self.client.get("/api/providers/totals/").json()
        self.assertEqual(totals["real_balance"], "5.00")
        self.assertEqual(totals["unconverted"], ["EUR"])

    def test_a_pool_shows_the_ledger_currency_not_a_lira(self):
        """
        بنك الأكواد بلا كتالوج خارجيّ ولا رصيد لدى أحد — أرقامه أرقامُنا.
        وكان الجدول يكتب تحته «₺ 0.00 · ≈ $0.00» بلا معنى.
        """
        Provider.objects.create(tenant=self.tenant, name="بنك", type=Provider.Type.POOL)
        row = self.client.get("/api/providers/").json()[0]
        self.assertEqual(row["shown_currency"], "USD")
        self.assertFalse(row["has_own_currency"])
        self.assertIsNone(row["real_balance_base"])

    def test_a_manual_loader_is_the_same(self):
        Provider.objects.create(tenant=self.tenant, name="يدوي", type=Provider.Type.LOADER)
        row = self.client.get("/api/providers/").json()[0]
        self.assertEqual(row["shown_currency"], "USD")
        self.assertFalse(row["has_own_currency"])

    def test_an_internal_store_carries_no_currency_of_its_own(self):
        """يعبر حدود العملة بنفسه من دفتر المورّد — فما يصل منه بعملتنا."""
        Provider.objects.create(tenant=self.tenant, name="متجر داخلي",
                                type=Provider.Type.SAME_SYSTEM)
        row = self.client.get("/api/providers/").json()[0]
        self.assertEqual(row["shown_currency"], "USD")
        self.assertFalse(row["has_own_currency"])

    def test_an_external_store_keeps_its_own(self):
        self._provider("TRY", real_balance=Decimal("100"))
        row = self.client.get("/api/providers/").json()[0]
        self.assertEqual(row["shown_currency"], "TRY")
        self.assertTrue(row["has_own_currency"])

    def test_totals_ignore_the_lira_default_of_a_pool(self):
        """بنكٌ رصيده 100 بعملة الدفتر لا يُقسم على 41.5."""
        Provider.objects.create(tenant=self.tenant, name="بنك",
                                type=Provider.Type.POOL, real_balance=Decimal("100"))
        self.assertEqual(self.client.get("/api/providers/totals/").json()["real_balance"], "100.00")

    def test_old_providers_default_to_lira(self):
        """المُعدّون قبل الحقل يبقون على السلوك السابق فلا تنقلب أسعارهم."""
        p = Provider.objects.create(tenant=self.tenant, name="قديم",
                                    type=Provider.Type.CARD_STORE)
        self.assertEqual(p.currency, "TRY")


class CostConversionUsesProviderCurrencyTest(TestCase):
    """تكلفة الطلب تُحوَّل بعملة مزوّدها هو — لا بليرةٍ مفترضة للجميع."""

    def setUp(self):
        self.tenant = Tenant.objects.create(
            subdomain="t1", name="متجر", base_currency="USD",
            exchange_rates={"TRY": "41.5"},
        )
        self.game = Game.objects.create(tenant=self.tenant, name="PUBG")
        self.product = Product.objects.create(
            tenant=self.tenant, game=self.game, name="60 UC",
            cost_price=Decimal("6"), recommended_price=Decimal("100"),
        )
        self.dealer = User.objects.create(
            login_id="d1", name="وكيل", tenant=self.tenant, role=User.Role.BAYI, dealer_no=1)
        Wallet.objects.create(tenant=self.tenant, user=self.dealer, balance=Decimal("1000"))

    def _apply(self, provider_currency, reported_cost):
        from orders import services
        from providers.adapters.base import ExecutionResult

        provider = Provider.objects.create(
            tenant=self.tenant, name="مزوّد", type=Provider.Type.CARD_STORE,
            config={"code": "znet"}, currency=provider_currency,
        )
        order = services.create_order(self.dealer, self.product)
        result = ExecutionResult(status="success", cost=Decimal(reported_cost))
        services._apply_real_cost(order, result, provider)
        return order

    def test_a_lira_provider_is_divided_by_the_rate(self):
        self.assertEqual(self._apply("TRY", "41.50").cost_price, Decimal("1.00"))

    def test_a_dollar_provider_is_taken_as_is(self):
        """كان يُقسم على 41.5 فيصير 1.00 — أي طلبٌ خاسر يبدو رابحاً."""
        self.assertEqual(self._apply("USD", "41.50").cost_price, Decimal("41.50"))

    def test_profit_follows_the_corrected_cost(self):
        order = self._apply("USD", "41.50")
        self.assertEqual(order.profit, order.sell_price - Decimal("41.50"))


class ZnetNoteTest(TestCase):
    """ملاحظة مسؤول ZNET تصل كاملة — وإن احتوت `|`."""

    def test_note_with_pipes_is_kept_whole(self):
        from providers.adapters.znet import ZnetAdapter
        r = ZnetAdapter.parse_status("OK|3| |الرقم خطأ | أعد المحاولة")
        self.assertEqual(r.status, "failed")
        self.assertEqual(r.note, "الرقم خطأ | أعد المحاولة")

    def test_cancel_reason_written_in_pin_box(self):
        from providers.adapters.znet import ZnetAdapter
        r = ZnetAdapter.parse_status("OK|3|الحساب محظور|")
        self.assertEqual((r.status, r.note, r.pin), ("failed", "الحساب محظور", ""))

    def test_success_keeps_pin_and_note(self):
        from providers.adapters.znet import ZnetAdapter
        r = ZnetAdapter.parse_status("OK|2|AB12-CD34|تم الشحن")
        self.assertEqual((r.status, r.pin, r.note), ("success", "AB12-CD34", "تم الشحن"))
