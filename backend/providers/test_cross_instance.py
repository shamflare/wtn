"""
التوجيه بين **نسختين مستقلّتين** (plan2.md): متجرٌ على دومين يشتري من متجرٍ على دومينٍ آخر.

داخل المنصّة الواحدة كان «نفس النظام» (`InternalTenantAdapter`) يقرأ قاعدة
المورّد مباشرةً. ونسخُ العملاء لا تتشارك قاعدةً، فالطريق الوحيد بينها الشبكة —
وواجهتنا الخارجية (`/client/api/`) منسوخةٌ عن ZDK حرفاً، فمحوّل ZDK القائم يكفي:
مزوّدٌ من نوع «متجر بطاقات» عنوانُه دومينُ المورّد، ومفتاحُه توكنُ حساب وكيلٍ
فتحه المورّد للمشتري.

هنا تُحاكى الشبكة: نداءات `requests` تُمرَّر إلى عميل الاختبار، فيمرّ الطلب
بالمصادقة والخصم والتحقّق كما يمرّ بين خادمين حقيقيين.
"""
from decimal import Decimal
from types import SimpleNamespace
from unittest import mock
from urllib.parse import urlparse

from rest_framework.test import APITestCase

from catalog.models import Game, PriceGroup, Product, ProductPrice
from clientapi.models import ApiToken
from core.models import Tenant, User, Wallet
from orders.models import Order
from providers.adapters.zdk import ZdkAdapter
from providers.models import Provider


class CrossInstanceRoutingTest(APITestCase):

    def setUp(self):
        # ——— النسخة المورّدة (دومين آخر) ———
        self.sup = Tenant.objects.create(subdomain="sup", name="المورّد", base_currency="USD")
        group = PriceGroup.objects.create(tenant=self.sup, name="عادية")
        game = Game.objects.create(tenant=self.sup, name="PUBG")
        self.product = Product.objects.create(
            tenant=self.sup, game=game, name="60 UC",
            cost_price=Decimal("6"), recommended_price=Decimal("12"),
        )
        ProductPrice.objects.create(tenant=self.sup, product=self.product,
                                    price_group=group, price=Decimal("8"))
        # الحساب الذي فتحه المورّد للمشتري — والإذن بيده هو (api_access_allowed)
        self.account = User.objects.create(
            login_id="buyer-at-sup", name="متجر المشتري", tenant=self.sup,
            role=User.Role.BAYI, price_group=group, dealer_no=1, api_access_allowed=True,
        )
        self.wallet = Wallet.objects.create(tenant=self.sup, user=self.account, balance=Decimal("100"))
        token = ApiToken.objects.create(user=self.account).token

        # ——— النسخة المشترية: مزوّدٌ عادي من نوع ZDK عنوانه دومين المورّد ———
        buyer = Tenant.objects.create(subdomain="buy", name="المشتري", base_currency="USD")
        self.provider = Provider.objects.create(
            tenant=buyer, name="متجر المورّد", type=Provider.Type.CARD_STORE, currency="USD",
            config={"code": "zdk", "base_url": "https://supplier.example", "api_token": token},
        )
        self.adapter = ZdkAdapter()

        # الشبكة بين الخادمين: كل `requests.get` يصل إلى الواجهة الخارجية للمورّد
        def bridge(url, params=None, headers=None, timeout=None, allow_redirects=True):
            assert urlparse(url).netloc == "supplier.example"
            r = self.client.get(urlparse(url).path, params or {},
                                HTTP_API_TOKEN=(headers or {}).get("api-token", ""))
            return SimpleNamespace(json=r.json, text=r.content.decode(), status_code=r.status_code)

        patcher = mock.patch("providers.adapters.zdk.requests.get", side_effect=bridge)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _order(self, receipt="1001"):
        # طلبُ المشتري كما يراه المحوّل: رقم فيش + رقم باقة المورّد
        return SimpleNamespace(receipt_no=receipt, player_id="5121234567", provider_ref="",
                               product=SimpleNamespace(provider_package_id=str(self.product.id)))

    def test_balance_is_the_account_wallet_at_the_supplier(self):
        res = self.adapter.get_balance(self.provider.config)
        self.assertTrue(res.ok, res.note)
        self.assertEqual(res.balance, Decimal("100"))

    def test_catalog_lists_the_supplier_products_at_our_price(self):
        res = self.adapter.list_packages(self.provider.config)
        self.assertTrue(res.ok, res.note)
        row = next(p for p in res.packages if p["id"] == str(self.product.id))
        self.assertEqual(Decimal(row["price"]), Decimal("8"))

    def test_an_order_is_placed_and_charged_at_the_supplier(self):
        res = self.adapter.place_order(self._order(), self.provider.config)
        self.assertIn(res.status, ("success", "processing"), res.note)
        self.assertTrue(res.external_ref)
        self.assertEqual(Order.objects.filter(tenant=self.sup, dealer=self.account).count(), 1)
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, Decimal("92"))

        # والمتابعة تجد الطلب نفسه لدى المورّد
        follow = self.adapter.fetch_status(
            SimpleNamespace(provider_ref=res.external_ref), self.provider.config)
        self.assertNotEqual(follow.status, "unsupported", follow.note)

    def test_a_retry_never_charges_twice(self):
        """الشبكة بين دومينين تنقطع — وإعادة الفيش نفسه لا تُنشئ طلباً ثانياً."""
        self.adapter.place_order(self._order("2002"), self.provider.config)
        self.adapter.place_order(self._order("2002"), self.provider.config)
        self.assertEqual(Order.objects.filter(tenant=self.sup, dealer=self.account).count(), 1)
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, Decimal("92"))

    def test_the_supplier_revoking_access_stops_the_route(self):
        """الإذن بيد المورّد: يطفئه فيتوقّف التوجيه فوراً، بلا تدخّلٍ من المشتري."""
        self.account.api_access_allowed = False
        self.account.save(update_fields=["api_access_allowed"])
        res = self.adapter.place_order(self._order("3003"), self.provider.config)
        self.assertEqual(res.status, "failed")
        self.assertFalse(Order.objects.filter(tenant=self.sup).exists())
