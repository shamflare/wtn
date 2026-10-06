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


class CustomCategoryTest(Base):
    def test_add_category_then_package_in_it(self):
        from .models import KontorCategory
        r = self.client.post("/api/kontor/categories/", {
            "operator": "Turkcell", "name": "باقات الطلاب", "line_type": "Ses"}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        cat = KontorCategory.objects.get(pk=r.json()["id"])
        self.assertTrue(cat.is_custom)
        # الاسم مكرّر في الشركة نفسها ⇐ مرفوض
        r = self.client.post("/api/kontor/categories/", {
            "operator": "Turkcell", "name": "باقات الطلاب", "line_type": "Ses"}, format="json")
        self.assertEqual(r.status_code, 400)

        r = self.client.post("/api/kontor/packages/", {
            "operator": "Turkcell", "category": cat.id, "name": "طالب 10GB", "cost": "50"}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.json()["category"], cat.id)
        # فئة شركة أخرى ⇐ مرفوض
        r = self.client.post("/api/kontor/packages/", {
            "operator": "Vodafone", "category": cat.id, "name": "x", "cost": "1"}, format="json")
        self.assertEqual(r.status_code, 400)
        # الاستيراد لا يتعثّر بالفئة المخصّصة ذات النوع نفسه
        upsert_packages(self.tenant, parse_feed("Turkcell|Ses|777|10.00|Yeni|^"), provider=self.a)
        self.assertFalse(KontorPackage.objects.get(znet_id="777").category.is_custom)

    def test_delete_only_empty(self):
        from .models import KontorCategory
        full = KontorCategory.objects.filter(tenant=self.tenant).first()
        self.assertEqual(self.client.delete("/api/kontor/categories/", {"id": full.id}, format="json").status_code, 400)
        r = self.client.post("/api/kontor/categories/", {
            "operator": "Avea", "name": "فارغة", "line_type": "Tam"}, format="json")
        self.assertEqual(self.client.delete("/api/kontor/categories/", {"id": r.json()["id"]}, format="json").status_code, 200)


class LookupCacheTest(Base):
    def test_operator_month_offers_day_and_forget(self):
        from datetime import timedelta

        from django.utils import timezone

        from . import session_client as sc
        from .models import KontorLookupCache
        html = {"/detect": {"html": "x"}, "/offers": {"html": "y"}}
        offers = [{"znet_id": "476647", "name": "n", "details": "", "days": 0, "gb": 0, "minutes": 0,
                   "shown_price": "1", "cost": "1", "is_offer": True}]
        with mock.patch.object(sc, "_get", side_effect=lambda p, *a, **k: html[p]) as g, \
                mock.patch.object(sc, "parse_operator", return_value="Turkcell"), \
                mock.patch.object(sc, "parse_offers", return_value=offers):
            self.assertEqual(sc.detect_operator("5442199992"), "Turkcell")
            self.assertEqual(sc.detect_operator("5442199992"), "Turkcell")
            self.assertEqual(sc.fetch_offers("5442199992", "Turkcell"), offers)
            self.assertEqual(sc.fetch_offers("5442199992", "Turkcell"), offers)
            self.assertEqual(g.call_count, 2)  # مرّة لكلٍّ منهما — الثانية من الكاش
            op_row = KontorLookupCache.objects.get(kind="operator")
            self.assertGreater(op_row.expires_at, timezone.now() + timedelta(days=29))
            of_row = KontorLookupCache.objects.get(kind="offers")
            self.assertLess(of_row.expires_at, timezone.now() + timedelta(hours=25))
            # بعد انتهاء المدّة يُكشف من جديد
            KontorLookupCache.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
            sc.detect_operator("5442199992")
            self.assertEqual(g.call_count, 3)
            # اختبار /sorgula يتجاوز الكاش
            sc.detect_operator("5442199992", ignore_switch=True)
            self.assertEqual(g.call_count, 4)
            # الشحن ينسى العروض
            sc.fetch_offers("5442199992", "Turkcell")
            p = self.pkg("476647"); p.recommended_price = Decimal("1000"); p.save()
            create_order(self.dealer, p, "5442199992")
            self.assertFalse(KontorLookupCache.objects.filter(kind="offers").exists())


class CacheResetTest(APITestCase):
    def test_platform_owner_clears_cache(self):
        from datetime import timedelta

        from django.utils import timezone

        from .models import KontorLookupCache
        owner = User.objects.create(login_id="plat", name="منصّة", role=User.Role.PLATFORM_OWNER)
        exp = timezone.now() + timedelta(days=1)
        for k, g in (("operator", "5442199992"), ("operator", "5321112233"), ("offers", "5442199992")):
            KontorLookupCache.objects.create(kind=k, gsm=g, operator="" if k == "operator" else "Turkcell",
                                             data={"v": "x"}, expires_at=exp)
        self.client.force_authenticate(owner)
        self.assertEqual(self.client.get("/api/platform/sorgula/cache/").json(), {"operator": 2, "offers": 1})
        r = self.client.delete("/api/platform/sorgula/cache/", {"kind": "all", "gsm": "+90 544 219 99 92"}, format="json")
        self.assertEqual(r.json()["deleted"], 2)
        r = self.client.delete("/api/platform/sorgula/cache/", {"kind": "all"}, format="json")
        self.assertEqual(r.json()["deleted"], 1)
        self.assertFalse(KontorLookupCache.objects.exists())

    def test_tenant_admin_forbidden(self):
        t = Tenant.objects.create(subdomain="x", name="x")
        u = User.objects.create(login_id="a", name="a", tenant=t, role=User.Role.TENANT_ADMIN)
        self.client.force_authenticate(u)
        self.assertEqual(self.client.delete("/api/platform/sorgula/cache/", {}, format="json").status_code, 403)
