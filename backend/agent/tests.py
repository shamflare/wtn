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
        inv = self.client.get("/api/agent/inventory/live/").json()
        self.assertEqual([g["key"] for g in inv["groups"]], ["agent_wallet", "receiving", "dealer_wallets"])
        self.assertEqual(inv["base_currency"], "TRY")

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
        mg = AgentPriceGroup.objects.create(tenant=self.t, agent=self.agent, name="رصيد", section="mobile")
        self.shop.agent_kontor_price_group = mg
        self.shop.save()
        # مجموعة ألعاب لا تُسعَّر بها الرصيد
        self.assertEqual(self.client.post("/api/agent/bulk-price/", {
            "section": "mobile", "groups": [self.group.id], "mode": "fixed", "value": "40"},
            format="json").status_code, 400)
        r = self.client.post("/api/agent/bulk-price/", {
            "section": "mobile", "groups": [mg.id], "mode": "fixed", "value": "40"}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        row = AgentKontorPrice.objects.get(group=mg, package=self.pkg)
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


class AgentAccountsCurrencyTest(Base):
    def test_balance_in_agent_currency(self):
        r = self.client.post("/api/agent/payments/accounts/", {"title": "صندوقي", "balance": "400"}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.json()["balance"], "400.00")
        from payments.models import ReceivingAccount
        acc = ReceivingAccount.objects.get(title="صندوقي")
        self.assertEqual((acc.balance, acc.owner_id), (Decimal("10.00"), self.agent.id))   # 400 ل.ت = 10$
        self.assertEqual(self.client.get("/api/agent/payments/accounts/").json()[0]["balance"], "400.00")
        inv = self.client.get("/api/agent/inventory/live/").json()
        self.assertEqual(inv["groups"][1]["lines"][0]["base"], "400.00")


class AddDealerTest(Base):
    def test_new_shop_inherits_agent_currency(self):
        r = self.client.post("/api/agent/dealers/", {"name": "دكان", "login_id": "5550001111", "password": "x12345"},
                             format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(User.objects.get(login_id="5550001111").display_currency, "TRY")


class LedgerPrecisionAndStatementTest(Base):
    """1000 ل.ت يشحنها المالك تصل 1000 بالضبط، وكشف الكبير عند المالك بلا حركات دكاكينه."""

    def setUp(self):
        super().setUp()
        self.t.exchange_rates = {"TRY": "41.3"}
        self.t.save()

    def test_owner_topup_in_agent_currency_is_exact(self):
        self.client.force_authenticate(self.owner)
        r = self.client.post(f"/api/dealers/{self.agent.id}/topup/", {"amount": "1000"}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        before = Decimal("100") * Decimal("41.3")
        self.assertEqual(Decimal(r.json()["balance_own"]), before + Decimal("1000.00"))
        # والوكيل يحوّل الألف كاملةً لدكانه (بعملته هو أيضاً) فتصله ألفاً
        self.shop.display_currency = "TRY"; self.shop.save()
        self.client.force_authenticate(self.agent)
        r = self.client.post(f"/api/agent/dealers/{self.shop.id}/wallet/", {"action": "topup", "amount": "1000"},
                             format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(Decimal(r.json()["dealer_balance"]), Decimal("50") * Decimal("41.3") + 1000)

    def test_owner_statement_hides_agent_internal_moves(self):
        self.client.post(f"/api/agent/dealers/{self.shop.id}/wallet/", {"action": "topup", "amount": "41.3"},
                         format="json")
        self.client.force_authenticate(self.owner)
        self.client.post(f"/api/dealers/{self.agent.id}/topup/", {"amount": "41.3"}, format="json")
        url = f"/api/dealers/{self.agent.id}/transactions/"
        store = self.client.get(url).json()
        self.assertEqual([t["internal"] for t in store["results"]], [False])
        self.assertTrue(store["dealer"]["is_big"])
        agent_side = self.client.get(url + "?scope=agent").json()
        self.assertEqual([t["internal"] for t in agent_side["results"]], [True])
        self.assertEqual(self.client.get(url + "?scope=all").json()["totals"]["count"], 2)

    def test_statement_is_paginated(self):
        from core import services
        w = Wallet.objects.get(user=self.shop)
        for _ in range(25):
            services.apply_transaction(w.id, Decimal("1"), "topup")
        d = self.client.get(f"/api/agent/dealers/{self.shop.id}/statement/").json()
        self.assertEqual((len(d["results"]), d["paging"]["pages"], d["totals"]["count"]), (20, 2, 25))
        self.assertEqual(len(self.client.get(f"/api/agent/dealers/{self.shop.id}/statement/?page=2").json()["results"]), 5)


class AgentInventoryTest(Base):
    def test_manual_items_and_snapshots_are_his_own(self):
        r = self.client.post("/api/agent/inventory/items/", {"name": "دَين خارجي"}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.json()["currency"], "TRY")
        self.client.post(f"/api/agent/inventory/items/{r.json()['id']}/", {"amount": "-400"}, format="json")
        live = self.client.get("/api/agent/inventory/live/").json()
        self.assertEqual(live["manual"]["lines"][0]["base"], "-400.00")
        # المحفظة 100$ = 4000 ل.ت والبند −400 — وأرصدة دكاكينه للاطّلاع لا تُطرح
        self.assertEqual(live["totals"]["total"], "3600.00")
        s = self.client.post("/api/agent/inventory/snapshots/save/", {"kind": "daily"}, format="json")
        self.assertEqual(s.status_code, 201, s.content)
        self.assertEqual(s.json()["total"], "3600.00")
        self.assertEqual(s.json()["profit"], "0.00")          # أوّل جرد: لا ربح يُقارَن به
        self.assertEqual(len(self.client.get("/api/agent/inventory/snapshots/").json()["results"]), 1)
        # والمالك لا يرى بند الوكيل ولا لقطته
        self.client.force_authenticate(self.owner)
        own = self.client.get("/api/inventory/live/").json()
        self.assertEqual(own["manual"]["lines"], [])
        self.assertEqual(self.client.get("/api/inventory/snapshots/").json()["results"], [])
        self.client.force_authenticate(self.agent)
        self.assertEqual(self.client.post("/api/agent/inventory/refresh/", {}).status_code, 403)


class DealerSettingsTest(Base):
    def test_add_with_profile_and_manage(self):
        r = self.client.post("/api/agent/dealers/", {
            "name": "دكان", "login_id": "5550002222", "password": "abc123",
            "whatsapp": "+905551234567", "id_image": "data:image/jpeg;base64,AAAA"}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        u = User.objects.get(login_id="5550002222")
        self.assertEqual((u.whatsapp, u.id_image[:10]), ("905551234567", "data:image"))
        url = f"/api/agent/dealers/{u.id}/settings/"
        self.assertEqual(self.client.get(url).json()["whatsapp"], "+905551234567")
        r = self.client.patch(url, {"password": "newpass1", "status": "passive"}, format="json")
        self.assertTrue(r.json()["password_changed"])
        u.refresh_from_db()
        self.assertTrue(u.check_password("newpass1"))
        self.assertEqual(u.status, "passive")
        # ودكان غيره لا يُمسّ
        self.assertEqual(self.client.get(f"/api/agent/dealers/{self.direct.id}/settings/").status_code, 404)


class FinanceReportsTest(Base):
    """تقارير المال لصاحب المتجر: الوكلاء الكبار · اليدوي · الإيداعات · عمر الديون."""

    def setUp(self):
        super().setUp()
        AgentProductPrice.objects.create(tenant=self.t, group=self.group, product=self.prod, price=Decimal("1.50"))
        o = create_order(self.shop, self.prod)
        o.status = Order.Status.SUCCESS; o.save()
        self.client.force_authenticate(self.owner)

    def test_agents_report(self):
        r = self.client.get("/api/finance/agents/").json()
        row = next(x for x in r["results"] if x["id"] == self.agent.id)
        self.assertEqual((row["count"], row["profit"], row["agent_profit"]), (1, "0.20", "0.50"))
        # ما يدين به المتجر لشبكته = رصيده + أرصدة دكاكينه
        self.assertEqual(Decimal(row["exposure"]), Decimal(row["balance"]) + Decimal(row["shops_balance"]))

    def test_manual_report_and_debts(self):
        Wallet.objects.filter(user=self.direct).update(credit_limit=Decimal("-100"))
        self.client.post(f"/api/dealers/{self.direct.id}/deduct/", {"amount": "30"}, format="json")
        m = self.client.get("/api/finance/manual/").json()
        self.assertEqual([x["type"] for x in m["results"]], ["manual_debit"])
        self.assertEqual(m["results"][0]["by"], self.owner.name)
        d = self.client.get("/api/finance/debts/").json()
        self.assertEqual([x["id"] for x in d["results"]], [self.direct.id])   # 10 − 30 = −20
        self.assertEqual(d["results"][0]["days"], 0)

    def test_deposits_report(self):
        from payments.models import PaymentMethod
        m = PaymentMethod.objects.create(tenant=self.t, name="شام", currency="TRY", commission_percent=Decimal("10"))
        self.client.force_authenticate(self.direct)
        r = self.client.post("/api/payments/store/deposits/create/", {"method": m.id, "amount": "400"}, format="json")
        self.client.force_authenticate(self.owner)
        self.client.post(f"/api/payments/notifications/{r.json()['id']}/approve/", {}, format="json")
        d = self.client.get("/api/finance/deposits/").json()
        self.assertEqual((d["totals"]["count"], d["results"][0]["credit"], d["results"][0]["commission"]),
                         (1, "9.00", "1.00"))   # 400 ل.ت = 10$ ، عمولة 10%

    def test_dealers_locked_out(self):
        self.client.force_authenticate(self.agent)
        self.assertEqual(self.client.get("/api/finance/agents/").status_code, 403)


class DepositSafetyTest(Base):
    def setUp(self):
        super().setUp()
        from payments.models import PaymentMethod, ReceivingAccount
        self.acc = ReceivingAccount.objects.create(tenant=self.t, title="صندوق")
        self.m = PaymentMethod.objects.create(tenant=self.t, name="نقد", currency="USD", account=self.acc)

    def _deposit(self, amount="20"):
        self.client.force_authenticate(self.direct)
        r = self.client.post("/api/payments/store/deposits/create/", {"method": self.m.id, "amount": amount},
                             format="json")
        self.client.force_authenticate(self.owner)
        return r

    def test_stale_double_approve_credits_once(self):
        from payments.models import PaymentNotification
        from payments.views import _apply_decision
        nid = self._deposit().json()["id"]
        a = PaymentNotification.objects.get(pk=nid)
        b = PaymentNotification.objects.get(pk=nid)          # نسخةٌ ثانية تقرأ «قيد المراجعة»
        self.assertEqual(_apply_decision(a, "approve", self.owner)[0], True)
        self.assertEqual(_apply_decision(b, "approve", self.owner)[0], False)
        self.assertEqual(Wallet.objects.get(user=self.direct).balance, Decimal("30.00"))
        self.acc.refresh_from_db()
        self.assertEqual(self.acc.balance, Decimal("20.00"))  # الحساب تبع القبول

    def test_commission_bounds_and_nan(self):
        r = self.client.post("/api/payments/methods/", {"name": "x", "currency": "USD", "commission_percent": "100"},
                             format="json")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self._deposit("NaN").status_code, 400)


class OwnerInventoryTreeTest(Base):
    """
    مثال المالك: للوكيل الكبير رصيد، أعطى دكانه منه — المتجر مدينٌ بالمبلغ نفسه في
    الحالتين، فجرد المالك لا يتغيّر بالحوالة. وجرد الوكيل لا يتغيّر إن دخل ثمنها
    صندوقه (إيداع الدكان على حسابه)؛ أمّا حوالةٌ بلا ثمنٍ مسجَّل فتُنقص جرده فعلاً.
    """

    def test_shop_paying_agent_changes_neither_inventory(self):
        from payments.models import PaymentMethod, ReceivingAccount
        acc = ReceivingAccount.objects.create(tenant=self.t, owner=self.agent, title="صندوقي")
        m = PaymentMethod.objects.create(tenant=self.t, owner=self.agent, name="نقد", currency="USD", account=acc)
        self.client.force_authenticate(self.owner)
        owner_before = self.client.get("/api/inventory/live/").json()["totals"]["total"]
        self.client.force_authenticate(self.agent)
        agent_before = self.client.get("/api/agent/inventory/live/").json()["totals"]["total"]

        self.client.force_authenticate(self.shop)
        nid = self.client.post("/api/payments/store/deposits/create/", {"method": m.id, "amount": "50"},
                               format="json").json()["id"]
        self.client.force_authenticate(self.agent)
        r = self.client.post(f"/api/agent/payments/notifications/{nid}/approve/", {}, format="json")
        self.assertEqual(r.status_code, 200, r.content)

        self.assertEqual(self.client.get("/api/agent/inventory/live/").json()["totals"]["total"], agent_before)
        self.client.force_authenticate(self.owner)
        self.assertEqual(self.client.get("/api/inventory/live/").json()["totals"]["total"], owner_before)

    def test_owner_inventory_counts_the_whole_tree(self):
        self.client.post(f"/api/agent/dealers/{self.shop.id}/wallet/", {"action": "topup", "amount": "800"},
                         format="json")
        self.client.force_authenticate(self.owner)
        g = next(g for g in self.client.get("/api/inventory/live/").json()["groups"] if g["key"] == "dealer_wallets")
        # الوكيل 100$ − 20$ + دكانه 50$ + 20$ + المباشر 10$ = 160$ علينا
        self.assertEqual(Decimal(g["total_base"]), Decimal("-160.00"))


class AgentReversalAbuseTest(Base):
    """قبول ⇐ سحب ⇐ إبطال: كان يرفع محفظة الوكيل فوق حدّه بدكانٍ وهمي سالب."""

    def test_reversal_refused_when_shop_cannot_cover_it(self):
        from payments.models import PaymentMethod
        m = PaymentMethod.objects.create(tenant=self.t, owner=self.agent, name="نقد", currency="USD")
        self.client.force_authenticate(self.shop)
        nid = self.client.post("/api/payments/store/deposits/create/", {"method": m.id, "amount": "40"},
                               format="json").json()["id"]
        self.client.force_authenticate(self.agent)
        self.client.post(f"/api/agent/payments/notifications/{nid}/approve/", {}, format="json")
        # يسحب ما أعطاه + رصيد الدكان الأصلي (50$ + 40$ = 90$ = 3600 ل.ت)
        self.client.post(f"/api/agent/dealers/{self.shop.id}/wallet/", {"action": "deduct", "amount": "3600"},
                         format="json")
        before = Wallet.objects.get(user=self.agent).balance
        r = self.client.post(f"/api/agent/payments/notifications/{nid}/reject/", {}, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("لا يكفي", r.json()["detail"])
        self.assertEqual(Wallet.objects.get(user=self.agent).balance, before)
        self.assertEqual(Wallet.objects.get(user=self.shop).balance, Decimal("0"))


class SmallHardeningTest(DepositSafetyTest):
    def test_pending_deposits_capped_at_five(self):
        for _ in range(5):
            self.assertEqual(self._deposit("1").status_code, 201)
        self.assertEqual(self._deposit("1").status_code, 400)

    def test_disabled_game_cannot_be_bought(self):
        from orders.services import OrderError
        self.game.status = "passive"
        self.game.save()
        with self.assertRaises(OrderError):
            create_order(self.direct, self.prod)


class SeparateGroupsTest(Base):
    """مجموعات الألعاب معزولة عن مجموعات الرصيد، والدكان في مجموعةٍ من كلٍّ منهما."""

    def test_sections_are_separate(self):
        self.client.post("/api/agent/price-groups/", {"name": "ذهبي", "section": "mobile"}, format="json")
        games = [g["name"] for g in self.client.get("/api/agent/price-groups/?section=games").json()["results"]]
        mobile = [g["name"] for g in self.client.get("/api/agent/price-groups/?section=mobile").json()["results"]]
        self.assertEqual((games, mobile), (["ذهبي"], ["ذهبي"]))   # الاسم نفسه مسموح في القسمين
        mg = AgentPriceGroup.objects.get(section="mobile")
        # دكانٌ لا يوضع في مجموعة رصيد على أنها ألعاب
        r = self.client.post("/api/agent/dealer-group/", {"dealer": self.shop.id, "price_group": mg.id,
                                                          "section": "games"}, format="json")
        self.assertEqual(r.status_code, 404)
        r = self.client.post("/api/agent/dealer-group/", {"dealer": self.shop.id, "price_group": mg.id,
                                                          "section": "mobile"}, format="json")
        self.assertEqual(r.status_code, 200)
        self.shop.refresh_from_db()
        self.assertEqual((self.shop.agent_price_group_id, self.shop.agent_kontor_price_group_id),
                         (self.group.id, mg.id))

    def test_migration_split_keeps_old_prices(self):
        """المجموعة القديمة المشتركة: أسعار رصيدها تنتقل لتوأمٍ رصيد، ودكاكينها معها."""
        import importlib
        AgentKontorPrice.objects.create(tenant=self.t, group=self.group, package=self.pkg, price=Decimal("5.5"))
        mig = importlib.import_module("kontor.migrations.0019_split_agent_groups")
        from django.apps import apps
        mig.split(apps, None)
        twin = AgentPriceGroup.objects.get(section="mobile", name=self.group.name)
        self.assertEqual(AgentKontorPrice.objects.get(package=self.pkg).group_id, twin.id)
        self.shop.refresh_from_db()
        self.assertEqual(self.shop.agent_kontor_price_group_id, twin.id)
        from kontor.services import dealer_price
        self.assertEqual(dealer_price(self.shop, self.pkg), Decimal("5.50"))


class OwnerKontorGroupTest(Base):
    """نافذة إعدادات الوكيل عند المالك: مجموعة أسعار الرصيد بجانب مجموعة الألعاب."""

    def test_owner_sets_one_mobile_group_for_all_operators(self):
        from kontor.models import KontorDealerSetting, KontorPriceGroup
        kg = KontorPriceGroup.objects.create(tenant=self.t, name="ذهبية")
        self.client.force_authenticate(self.owner)
        url = f"/api/dealers/{self.direct.id}/settings/"
        self.assertIsNone(self.client.get(url).json()["kontor_price_group"])
        r = self.client.post(url, {"kontor_price_group": kg.id}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(set(KontorDealerSetting.objects.filter(dealer=self.direct).values_list("group_id", flat=True)),
                         {kg.id})
        self.assertEqual(self.client.get(url).json()["kontor_price_group"], kg.id)
        # مختلفةٌ لكل شركة ⇐ «mixed» ولا تُمسّ إن عادت كما هي
        KontorDealerSetting.objects.filter(dealer=self.direct, operator="Vodafone").update(group=None)
        self.assertEqual(self.client.get(url).json()["kontor_price_group"], "mixed")
        self.client.post(url, {"kontor_price_group": "mixed"}, format="json")
        self.assertIsNone(KontorDealerSetting.objects.get(dealer=self.direct, operator="Vodafone").group_id)
