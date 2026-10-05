"""طلبات الخطوط داخل «طلباتي» وتقارير الوكيل والمالك — بجانب الألعاب لا بدلها."""
from decimal import Decimal

from rest_framework.test import APITestCase

from catalog.models import Game, Product
from core.models import Tenant, User, Wallet
from orders.models import Order

from .models import KontorCategory, KontorOrder, KontorPackage


class MobileInReportsTest(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(subdomain="kon", name="متجر", base_currency="USD")
        self.admin = User.objects.create(login_id="own", name="مالك", tenant=self.tenant,
                                         role=User.Role.TENANT_ADMIN)
        self.dealer = User.objects.create(login_id="bayi", name="وكيل", tenant=self.tenant,
                                          role=User.Role.BAYI, dealer_no=1)
        Wallet.objects.create(tenant=self.tenant, user=self.dealer, balance=Decimal("100"))
        game = Game.objects.create(tenant=self.tenant, name="PUBG")
        prod = Product.objects.create(tenant=self.tenant, game=game, name="60 UC",
                                      cost_price=Decimal("6"), recommended_price=Decimal("9"))
        Order.objects.create(tenant=self.tenant, dealer=self.dealer, game=game, product=prod,
                             status=Order.Status.SUCCESS, cost_price=Decimal("6"), sell_price=Decimal("8"),
                             profit=Decimal("2"), buyer_price=Decimal("8"),
                             dealer_sell_price=Decimal("9"), dealer_profit=Decimal("1"))
        cat = KontorCategory.objects.create(tenant=self.tenant, operator="Turkcell", line_type="Ses", name="Ses")
        pkg = KontorPackage.objects.create(tenant=self.tenant, operator="Turkcell", category=cat,
                                           znet_id="1", link_code="1", name="Günlük 6GB")
        mk = lambda st, gsm: KontorOrder.objects.create(  # noqa: E731
            tenant=self.tenant, dealer=self.dealer, package=pkg, operator="Turkcell", gsm=gsm, status=st,
            cost_price=Decimal("4"), sell_price=Decimal("5"), profit=Decimal("1"),
            dealer_sell_price=Decimal("6"), dealer_profit=Decimal("1"))
        self.ok = mk(KontorOrder.Status.SUCCESS, "5321112233")
        mk(KontorOrder.Status.REFUNDED, "5329998877")
        mk(KontorOrder.Status.PROCESSING, "5320000000")

    def test_dealer_orders_list_merges_both(self):
        self.client.force_authenticate(self.dealer)
        d = self.client.get("/api/store/orders/").json()
        kinds = [r["kind"] for r in d["results"]]
        self.assertEqual(kinds.count("mobile"), 3)
        self.assertEqual(kinds.count("game"), 1)
        self.assertEqual(d["counts"], {"all": 4, "success": 2, "cancelled": 1, "pending": 1})
        self.assertEqual(Decimal(d["total_paid"]), Decimal("18.00"))  # 8 + 5 + 5 (المُسترجَع لا يُحسب)
        row = next(r for r in d["results"] if r.get("receipt_no") == f"M{self.ok.id}")
        self.assertEqual((row["player_id"], row["status"]), ("5321112233", "success"))
        # فلتر الحالة والبحث يعملان على الخطوط أيضاً
        self.assertEqual(len(self.client.get("/api/store/orders/?status=cancelled").json()["results"]), 1)
        self.assertEqual(len(self.client.get("/api/store/orders/?q=99988").json()["results"]), 1)

    def test_dealer_summary_and_report_include_mobile(self):
        self.client.force_authenticate(self.dealer)
        s = self.client.get("/api/store/summary/").json()
        self.assertEqual((s["orders"], Decimal(s["profit"]), s["pending"]), (2, Decimal("2.00"), 1))
        r = self.client.get("/api/store/report/").json()
        self.assertIn("موبايل · Turkcell", {x["game"] for x in r["results"]})
        self.assertEqual(Decimal(r["totals"]["profit"]), Decimal("3.00"))  # 1 لعبة + 1 + 1 قيد التنفيذ

    def test_owner_reports_include_mobile_profit(self):
        self.client.force_authenticate(self.admin)
        r = self.client.get("/api/orders/reports/summary/").json()
        mobile = next(x for x in r["results"] if x["kind"] == "mobile")
        self.assertEqual((mobile["game"], mobile["count"]), ("موبايل · Turkcell", 1))
        self.assertEqual(Decimal(r["totals"]["profit"]), Decimal("3.00"))  # 2 لعبة + 1 خط
        only = self.client.get("/api/orders/reports/summary/?section=mobile").json()
        self.assertEqual(Decimal(only["totals"]["profit"]), Decimal("1"))
        d = self.client.get("/api/orders/reports/dealers/").json()
        self.assertEqual((d["results"][0]["count"], Decimal(d["results"][0]["profit"])), (2, Decimal("3")))

    def test_game_filter_excludes_mobile(self):
        self.client.force_authenticate(self.admin)
        gid = Game.objects.get().id
        r = self.client.get(f"/api/orders/reports/summary/?game={gid}").json()
        self.assertFalse(any(x["kind"] == "mobile" for x in r["results"]))
