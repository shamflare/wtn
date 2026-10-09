"""
لوحة الوكيل الكبير: طلبات دكاكينه (ألعاب + خطوط) وتقاريره وجرده وتسعيره الجماعي
ووسائل دفعه — كلٌّ محصور في شجرته، وبعملة عرضه.
"""
from datetime import timedelta
from decimal import Decimal

from django.utils import timezone
from rest_framework.test import APITestCase

from catalog.models import AgentPriceGroup, AgentProductPrice, Game, Product
from core.models import Tenant, User, Wallet
from kontor.models import AgentKontorPrice, KontorCategory, KontorOrder, KontorPackage
from orders.models import Order
from orders.services import create_order, resolve_sell_price
from payments.models import PaymentMethod, PaymentNotification


class Base(APITestCase):
    def setUp(self):
        self.t = Tenant.objects.create(subdomain="ag", name="متجر", base_currency="USD",
                                       exchange_rates={"TRY": "40"})
        mk = lambda lid, role, **kw: User.objects.create(  # noqa: E731
            login_id=lid, name=lid, tenant=self.t, role=role, **kw)
        self.owner = mk("own", User.Role.TENANT_ADMIN)
        self.agent = mk("big", User.Role.ANA_BAYI, display_currency="TRY")
        self.other = mk("big2", User.Role.ANA_BAYI)
        self.shop = mk("shop", User.Role.BAYI, parent=self.agent)
        self.direct = mk("direct", User.Role.BAYI)
        for u, bal in ((self.agent, "100"), (self.other, "0"), (self.shop, "50"), (self.direct, "10")):
            Wallet.objects.create(tenant=self.t, user=u, balance=Decimal(bal))
        self.game = Game.objects.create(tenant=self.t, name="PUBG")
        self.prod = Product.objects.create(tenant=self.t, game=self.game, name="60 UC",
                                           cost_price=Decimal("0.80"), recommended_price=Decimal("1.00"))
        self.group = AgentPriceGroup.objects.create(tenant=self.t, agent=self.agent, name="ذهبي")
        self.shop.agent_price_group = self.group
        self.shop.save()
        cat = KontorCategory.objects.create(tenant=self.t, operator="Turkcell", line_type="Ses", name="Ses")
        self.pkg = KontorPackage.objects.create(tenant=self.t, operator="Turkcell", category=cat,
                                                znet_id="1", link_code="1", name="6GB",
                                                cost_price=Decimal("4"), recommended_price=Decimal("5"))
        self.client.force_authenticate(self.agent)

    def kontor(self, status=KontorOrder.Status.SUCCESS, dealer=None, **kw):
        return KontorOrder.objects.create(
            tenant=self.t, dealer=dealer or self.shop, package=self.pkg, operator="Turkcell",
            gsm="5321112233", status=status, cost_price=Decimal("4"), sell_price=Decimal("5"),
            profit=Decimal("1"), agent=self.agent if dealer is None else None,
            buyer_price=Decimal("6"), agent_profit=Decimal("1"), **kw)


class OrdersAndReportsTest(Base):
    def setUp(self):
        super().setUp()
        AgentProductPrice.objects.create(tenant=self.t, group=self.group, product=self.prod, price=Decimal("1.50"))
        self.g = create_order(self.shop, self.prod)
        self.g.status = Order.Status.SUCCESS
        self.g.provider_note = "تم — ملاحظة المزوّد"
        self.g.save()
        self.m = self.kontor()
        self.kontor(dealer=self.direct)          # ليس من دكاكينه
        old = self.kontor()
        KontorOrder.objects.filter(pk=old.pk).update(created_at=timezone.now() - timedelta(days=3))

    def test_orders_merge_games_and_mobile_with_notes(self):
        today = timezone.localdate().isoformat()
        d = self.client.get(f"/api/agent/orders/?date_from={today}&date_to={today}").json()
        kinds = sorted(r["kind"] for r in d["results"])
        self.assertEqual(kinds, ["game", "mobile"])                     # القديم والغريب خارجها
        g = next(r for r in d["results"] if r["kind"] == "game")
        self.assertEqual(g["provider_note"], "تم — ملاحظة المزوّد")
        self.assertEqual((g["sell_price"], g["profit"]), ("60.00", "20.00"))  # 1.5$ ، 0.5$ × 40
        self.assertEqual(d["currency"], "TRY")
        self.assertEqual(len(self.client.get("/api/agent/orders/").json()["results"]), 3)

    def test_reports_and_inventory(self):
        today = timezone.localdate().isoformat()
        r = self.client.get(f"/api/agent/reports/summary/?date_from={today}&date_to={today}").json()
        self.assertEqual({x["game"] for x in r["results"]}, {"PUBG", "موبايل · Turkcell"})
        self.assertEqual(r["totals"]["profit"], "60.00")                # (0.5 + 1) × 40
        d = self.client.get("/api/agent/reports/dealers/").json()
        self.assertEqual([x["dealer"] for x in d["results"]], ["shop"])
        inv = self.client.get("/api/agent/inventory/").json()
        self.assertEqual([l["key"] for l in inv["lines"]], ["wallet", "accounts", "dealers"])

    def test_other_agent_sees_nothing(self):
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.get("/api/agent/orders/").json()["results"], [])


class PricingTest(Base):
    def test_bulk_price_links_to_cost_and_follows_it(self):
        r = self.client.post("/api/agent/bulk-price/", {
            "section": "games", "groups": [self.group.id], "mode": "percent", "value": "10"}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(resolve_sell_price(self.shop, self.prod), Decimal("1.10"))
        self.prod.recommended_price = Decimal("2.00"); self.prod.save()   # تكلفة الوكيل تتغيّر
        self.assertEqual(resolve_sell_price(self.shop, self.prod), Decimal("2.20"))
        m = self.client.get("/api/agent/price-matrix/?section=games").json()
        cell = m["blocks"][0]["products"][0]["prices"][str(self.group.id)]
        self.assertEqual((cell["price"], cell["margin"]["mode"]), ("88.00", "percent"))

    def test_mobile_bulk_and_fixed_margin_in_agent_currency(self):
        r = self.client.post("/api/agent/bulk-price/", {
            "section": "mobile", "groups": [self.group.id], "mode": "fixed", "value": "40"}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        row = AgentKontorPrice.objects.get(group=self.group, package=self.pkg)
        self.assertEqual(row.margin_value, Decimal("1.00"))               # 40 ل.ت = 1$
        from kontor.services import dealer_price
        self.assertEqual(dealer_price(self.shop, self.pkg), Decimal("6.00"))

    def test_manual_price_below_cost_rejected(self):
        r = self.client.post("/api/agent/set-price/", {
            "section": "games", "group": self.group.id, "product": self.prod.id, "price": "10"}, format="json")
        self.assertEqual(r.status_code, 400)                               # 10 ل.ت < 40 ل.ت


class AgentPaymentsTest(Base):
    def setUp(self):
        super().setUp()
        self.store_m = PaymentMethod.objects.create(tenant=self.t, name="للمتجر", currency="USD")
        r = self.client.post("/api/agent/payments/methods/", {"name": "شام كاش الوكيل", "currency": "USD"},
                             format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.mine = PaymentMethod.objects.get(pk=r.json()["id"])

    def test_scopes(self):
        self.assertEqual(self.mine.owner, self.agent)
        names = [m["name"] for m in self.client.get("/api/agent/payments/methods/").json()]
        self.assertEqual(names, ["شام كاش الوكيل"])
        # دكانه يرى طرق وكيله، والوكيل المباشر يرى طرق المتجر
        self.client.force_authenticate(self.shop)
        self.assertEqual([m["name"] for m in self.client.get("/api/payments/store/methods/").json()["methods"]],
                         ["شام كاش الوكيل"])
        self.client.force_authenticate(self.direct)
        self.assertEqual([m["name"] for m in self.client.get("/api/payments/store/methods/").json()["methods"]],
                         ["للمتجر"])
        # والمالك لا يرى طريقة الوكيل
        self.client.force_authenticate(self.owner)
        self.assertEqual([m["name"] for m in self.client.get("/api/payments/methods/").json()],
                         ["للمتجر"])

    def _deposit(self, amount):
        self.client.force_authenticate(self.shop)
        r = self.client.post("/api/payments/store/deposits/create/",
                             {"method": self.mine.id, "amount": amount}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.client.force_authenticate(self.agent)
        return PaymentNotification.objects.get(pk=r.json()["id"])

    def test_approval_is_a_transfer_from_agent_wallet(self):
        n = self._deposit("30")
        self.assertEqual(n.owner, self.agent)
        r = self.client.post(f"/api/agent/payments/notifications/{n.id}/approve/", {}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        bal = lambda u: Wallet.objects.get(user=u).balance  # noqa: E731
        self.assertEqual((bal(self.agent), bal(self.shop)), (Decimal("70.00"), Decimal("80.00")))
        # الإبطال يعيد كلّ شيء
        self.client.post(f"/api/agent/payments/notifications/{n.id}/reject/", {}, format="json")
        self.assertEqual((bal(self.agent), bal(self.shop)), (Decimal("100.00"), Decimal("50.00")))
        # والمالك لا يراه ولا يقرّر فيه
        self.client.force_authenticate(self.owner)
        self.assertEqual(self.client.get("/api/payments/notifications/").json()["results"], [])
        self.assertEqual(self.client.post(f"/api/payments/notifications/{n.id}/approve/").status_code, 404)

    def test_approval_refused_when_agent_balance_short(self):
        n = self._deposit("500")
        r = self.client.post(f"/api/agent/payments/notifications/{n.id}/approve/", {}, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("رصيدك لا يكفي", r.json()["detail"])
        self.assertEqual(Wallet.objects.get(user=self.shop).balance, Decimal("50"))
