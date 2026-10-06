"""تحديث التكلفة من مزوّد مختار، الاستيراد للجديد وحده، وحذف الباقات المعطّلة."""
from decimal import Decimal
from unittest import mock

from rest_framework.test import APITestCase

from core.models import Tenant, User, Wallet
from providers.models import Provider

from .execution import create_order
from .models import KontorOrder, KontorPackage, KontorPackageLink, KontorPackagePrice, KontorPriceGroup
from .services import parse_feed, upsert_packages

FEED = ("Turkcell|Ses|476647|970.00|Fırsat 30GB İndirimli ⭕|^"
        "Turkcell|Tam|100|148.00|✅100 TL|^"
        "Turkcell|Tam|200|290.00|✅200 TL|^")


def _resp(text):
    return mock.Mock(text=text)


class Base(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(subdomain="kon", name="متجر", base_currency="TRY")
        self.admin = User.objects.create(login_id="own", name="مالك", tenant=self.tenant,
                                         role=User.Role.TENANT_ADMIN)
        self.dealer = User.objects.create(login_id="bayi", name="وكيل", tenant=self.tenant,
                                          role=User.Role.BAYI)
        Wallet.objects.create(tenant=self.tenant, user=self.dealer, balance=Decimal("5000"))
        self.a = Provider.objects.create(tenant=self.tenant, name="ZNET-A", type=Provider.Type.SAME_SYSTEM,
                                         config={"code": "znet", "base_url": "http://a", "kod": "k", "sifre": "s"})
        self.b = Provider.objects.create(tenant=self.tenant, name="ZNET-B", type=Provider.Type.SAME_SYSTEM,
                                         config={"code": "znet", "base_url": "http://b", "kod": "k", "sifre": "s"})
        upsert_packages(self.tenant, parse_feed(FEED), provider=self.a)
        self.client.force_authenticate(self.admin)

    def pkg(self, zid):
        return KontorPackage.objects.get(znet_id=zid)


class RefreshCostsTest(Base):
    def test_updates_by_provider_code_and_reports_unlinked(self):
        # B يعرف 476647 برقمه 9001 فقط؛ الباقتان Tam غير مربوطتين به
        KontorPackageLink.objects.create(tenant=self.tenant, package=self.pkg("476647"), provider=self.b,
                                         code="9001", cost=Decimal("0"))
        g = KontorPriceGroup.objects.create(tenant=self.tenant, name="VIP")
        self.client.post("/api/kontor/set-price/", {"package": self.pkg("476647").id, "group": g.id,
                                                    "mode": "percent", "value": "10"}, format="json")
        feed_b = "Turkcell|Ses|9001|1000.00|Fırsat|^Turkcell|Tam|100|1.00|غير مقصودة|^"
        with mock.patch("kontor.services.requests.get", return_value=_resp(feed_b)):
            r = self.client.post("/api/kontor/refresh-costs/", {"provider": self.b.id}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        d = r.json()
        self.assertEqual(d["updated"], 1)
        self.assertEqual(d["skipped_total"], 2)
        self.assertEqual(d["skipped"], [{"operator": "Turkcell", "operator_label": "Turkcell",
                                         "category": "Tam", "count": 2}])
        p = self.pkg("476647")
        self.assertEqual((p.provider_cost, p.cost_price), (Decimal("1000.00"), Decimal("1000.00")))
        self.assertEqual(KontorPackagePrice.objects.get(package=p, group=g).price, Decimal("1100.00"))
        # رقم 100 لدى B ليس باقتنا (لا ربط) ⇐ لا تُمسّ كلفتها
        self.assertEqual(self.pkg("100").cost_price, Decimal("148.00"))

    def test_requires_provider(self):
        self.assertEqual(self.client.post("/api/kontor/refresh-costs/", {}, format="json").status_code, 400)


class ImportOnlyNewTest(Base):
    def test_existing_untouched_new_created(self):
        p = self.pkg("100")
        feed = FEED.replace("148.00", "999.00") + "Turkcell|Tam|500|700.00|✅500 TL|^"
        with mock.patch("kontor.services.requests.get", return_value=_resp(feed)):
            r = self.client.post("/api/kontor/import/", {"provider": self.a.id}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual((r.json()["created"], r.json()["existing"]), (1, 3))
        p.refresh_from_db()
        self.assertEqual(p.cost_price, Decimal("148.00"))
        self.assertTrue(KontorPackage.objects.filter(znet_id="500", provider=self.a).exists())

    def test_same_package_under_other_number_is_not_duplicated(self):
        feed_b = "Turkcell|Ses|9001|1000.00|FIRSAT 30GB INDIRIMLI|^"
        with mock.patch("kontor.services.requests.get", return_value=_resp(feed_b)):
            r = self.client.post("/api/kontor/import/", {"provider": self.b.id}, format="json")
        self.assertEqual(r.json()["created"], 0)
        self.assertEqual(KontorPackage.objects.count(), 3)


class DeleteTest(Base):
    def test_only_disabled_and_orders_stay_frozen(self):
        p = self.pkg("476647")
        p.recommended_price = Decimal("1000"); p.save()
        o = create_order(self.dealer, p, "5442199992")
        o.status = KontorOrder.Status.SUCCESS; o.save()

        r = self.client.post("/api/kontor/packages/delete/", {"ids": [p.id]}, format="json")
        self.assertEqual(r.status_code, 400)  # غير معطّلة

        p.status = KontorPackage.Status.PASSIVE; p.save()
        r = self.client.post("/api/kontor/packages/delete/", {"ids": [p.id]}, format="json")
        self.assertEqual(r.json(), {"deleted": 1})
        o.refresh_from_db()
        self.assertIsNone(o.package_id)
        self.assertEqual((o.package_name, o.znet_id, o.sell_price), (p.name, "476647", Decimal("1000.00")))
        rows = self.client.get("/api/kontor/orders/").json()["results"]
        self.assertEqual(rows[0]["package_name"], p.name)

    def test_refuses_with_pending_order(self):
        p = self.pkg("476647")
        p.recommended_price = Decimal("1000"); p.save()
        o = create_order(self.dealer, p, "5442199992")
        o.status = KontorOrder.Status.PROCESSING; o.save()
        p.status = KontorPackage.Status.PASSIVE; p.save()
        r = self.client.post("/api/kontor/packages/delete/", {"ids": [p.id]}, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertTrue(KontorPackage.objects.filter(pk=p.id).exists())


class ManualCostTest(Base):
    def test_manual_cost_then_refresh_restores_znet(self):
        p = self.pkg("476647")
        g = KontorPriceGroup.objects.create(tenant=self.tenant, name="VIP")
        self.client.post("/api/kontor/set-price/", {"package": p.id, "group": g.id,
                                                    "mode": "fixed", "value": "5"}, format="json")
        r = self.client.post("/api/kontor/set-cost/", {"package": p.id, "cost": "800"}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        p.refresh_from_db()
        self.assertEqual((p.cost_price, p.provider_cost), (Decimal("800.00"), Decimal("0")))
        self.assertEqual(KontorPackagePrice.objects.get(package=p, group=g).price, Decimal("805.00"))

        with mock.patch("kontor.services.requests.get", return_value=_resp(FEED)):
            self.client.post("/api/kontor/refresh-costs/", {"provider": self.a.id}, format="json")
        p.refresh_from_db()
        self.assertEqual(p.cost_price, Decimal("970.00"))
        self.assertEqual(KontorPackagePrice.objects.get(package=p, group=g).price, Decimal("975.00"))

    def test_rejects_negative(self):
        r = self.client.post("/api/kontor/set-cost/", {"package": self.pkg("100").id, "cost": "-1"}, format="json")
        self.assertEqual(r.status_code, 400)


class ManualPackageTest(Base):
    def test_create_manual_package(self):
        r = self.client.post("/api/kontor/packages/", {
            "operator": "Vodafone", "line_type": "Ses", "name": "باقة خاصة",
            "cost": "120", "recommended_price": "130"}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        p = KontorPackage.objects.get(pk=r.json()["id"])
        self.assertTrue(p.is_manual)
        self.assertEqual((p.znet_id, p.link_code, p.cost_price), ("M1", "M1", Decimal("120.00")))
        self.assertEqual(p.category.line_type, "Ses")
        r2 = self.client.post("/api/kontor/packages/", {
            "operator": "Vodafone", "line_type": "Ses", "name": "ثانية", "cost": "1"}, format="json")
        self.assertEqual(r2.json()["znet_id"], "M2")

    def test_link_code_taken_and_validation(self):
        r = self.client.post("/api/kontor/packages/", {
            "operator": "Turkcell", "line_type": "Tam", "name": "x", "cost": "1", "link_code": "100"}, format="json")
        self.assertEqual(r.status_code, 400)
        r = self.client.post("/api/kontor/packages/", {"operator": "Turkcell", "name": "x"}, format="json")
        self.assertEqual(r.status_code, 400)

    def test_manual_unlinked_is_never_sent(self):
        from .execution import _code_for
        r = self.client.post("/api/kontor/packages/", {
            "operator": "Turkcell", "line_type": "Ses", "name": "يدوية", "cost": "1"}, format="json")
        p = KontorPackage.objects.get(pk=r.json()["id"])
        self.assertIsNone(_code_for(p, self.a))
        KontorPackageLink.objects.create(tenant=self.tenant, package=p, provider=self.a, code="555")
        self.assertEqual(_code_for(p, self.a), "555")
