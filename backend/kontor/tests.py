from decimal import Decimal

from django.test import TestCase
from rest_framework.test import APITestCase

from core.models import Tenant, User
from kontor.models import KontorCategory, KontorPackage
from kontor.services import parse_feed, upsert_packages

# عيّنة مختصرة من رد paket_listesi.php الحقيقي
FEED = (
    "Turkcell|Ses|476647|970.00|Fırsat 30GB İndirimli ⭕|^"
    "Turkcell|Tam|100|148.00|✅100 TL|^"
    "Vodafone|Ses|515.00|300.00|5G Haftalik|^"
    "Avea|3gCep|1209|61.44|✅GUNLUK 1 GB|^"
    "Callback|Syriatel|9001|50.00|رصيد سوري|^"
    "BADLINE_NO_PIPES^"
    "Unknown|Ses|1|1|x|^"          # مشغّل غير معروف — يُتجاهَل
    "Turkcell|BadType|1|1|x|^"     # نوع غير معروف — يُتجاهَل
)


class ParseFeedTest(TestCase):
    def test_parses_valid_rows_only(self):
        rows = parse_feed(FEED)
        self.assertEqual(len(rows), 5)
        self.assertEqual({r["operator"] for r in rows},
                         {"Turkcell", "Vodafone", "Avea", "Callback"})

    def test_cost_and_fields(self):
        first = next(r for r in parse_feed(FEED) if r["znet_id"] == "476647")
        self.assertEqual(first["cost"], Decimal("970.00"))
        self.assertEqual(first["line_type"], "Ses")
        self.assertEqual(first["name"], "Fırsat 30GB İndirimli ⭕")

    def test_empty_and_garbage(self):
        self.assertEqual(parse_feed(""), [])
        self.assertEqual(parse_feed("|||^||"), [])


class UpsertTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(subdomain="kon", name="متجر", base_currency="TRY")

    def test_creates_categories_and_packages(self):
        res = upsert_packages(self.tenant, parse_feed(FEED))
        self.assertEqual(res, {"received": 5, "created": 5, "updated": 0})
        self.assertEqual(KontorPackage.objects.count(), 5)
        self.assertEqual(KontorCategory.objects.count(), 5)

    def test_offer_detection_by_name(self):
        upsert_packages(self.tenant, parse_feed(FEED))
        self.assertEqual(KontorPackage.objects.get(znet_id="476647").kind, KontorPackage.Kind.OFFER)
        self.assertEqual(KontorPackage.objects.get(znet_id="100").kind, KontorPackage.Kind.GENERAL)

    def test_reimport_updates_cost_keeps_edits(self):
        upsert_packages(self.tenant, parse_feed(FEED))
        p = KontorPackage.objects.get(znet_id="476647")
        p.recommended_price = Decimal("1200"); p.kind = KontorPackage.Kind.GENERAL; p.save()
        res = upsert_packages(self.tenant, parse_feed(FEED.replace("970.00", "999.00")))
        self.assertEqual(res["updated"], 5)
        p.refresh_from_db()
        self.assertEqual(p.cost_price, Decimal("999.00"))       # الكلفة تُحدَّث
        self.assertEqual(p.recommended_price, Decimal("1200"))   # تعديل المالك باقٍ
        self.assertEqual(p.kind, KontorPackage.Kind.GENERAL)
        self.assertEqual(KontorPackage.objects.count(), 5)       # لا تكرار

    def test_dry_run_saves_nothing(self):
        self.assertEqual(upsert_packages(self.tenant, parse_feed(FEED), dry_run=True)["created"], 0)
        self.assertEqual(KontorPackage.objects.count(), 0)


class ApiTest(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(subdomain="kon", name="متجر", base_currency="TRY")
        self.admin = User.objects.create(login_id="own", name="مالك", tenant=self.tenant,
                                         role=User.Role.TENANT_ADMIN)
        self.dealer = User.objects.create(login_id="bayi", name="وكيل", tenant=self.tenant,
                                          role=User.Role.BAYI)
        upsert_packages(self.tenant, parse_feed(FEED))

    def test_dealer_forbidden(self):
        self.client.force_authenticate(self.dealer)
        self.assertEqual(self.client.get("/api/kontor/packages/").status_code, 403)

    def test_admin_lists_and_filters(self):
        self.client.force_authenticate(self.admin)
        self.assertEqual(len(self.client.get("/api/kontor/packages/").json()), 5)
        r = self.client.get("/api/kontor/packages/?operator=Turkcell")
        self.assertEqual(len(r.json()), 2)
        self.assertEqual(len(self.client.get("/api/kontor/categories/").json()), 5)

    def test_admin_edits_package(self):
        self.client.force_authenticate(self.admin)
        pk = KontorPackage.objects.get(znet_id="100").pk
        r = self.client.patch(f"/api/kontor/packages/{pk}/",
                              {"recommended_price": "175.00", "kind": "offer"}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        obj = KontorPackage.objects.get(pk=pk)
        self.assertEqual(obj.recommended_price, Decimal("175.00"))
        self.assertEqual(obj.kind, "offer")

    def test_znet_id_and_cost_are_read_only(self):
        self.client.force_authenticate(self.admin)
        p = KontorPackage.objects.get(znet_id="100")
        self.client.patch(f"/api/kontor/packages/{p.pk}/",
                          {"znet_id": "999", "cost_price": "1.00"}, format="json")
        p.refresh_from_db()
        self.assertEqual(p.znet_id, "100")
        self.assertEqual(p.cost_price, Decimal("148.00"))

    def test_import_without_provider(self):
        self.client.force_authenticate(self.admin)
        r = self.client.post("/api/kontor/import/")
        self.assertEqual(r.status_code, 400)


class PricingTest(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(subdomain="kon", name="متجر", base_currency="TRY")
        self.admin = User.objects.create(login_id="own", name="مالك", tenant=self.tenant,
                                         role=User.Role.TENANT_ADMIN)
        self.dealer = User.objects.create(login_id="bayi", name="وكيل", tenant=self.tenant,
                                          role=User.Role.BAYI)
        upsert_packages(self.tenant, parse_feed(FEED))
        self.client.force_authenticate(self.admin)

    def _group(self, name="VIP"):
        return self.client.post("/api/kontor/price-groups/", {"name": name}, format="json").json()

    def test_create_group_and_set_manual_price(self):
        g = self._group()
        pk = KontorPackage.objects.get(znet_id="100").pk
        r = self.client.post("/api/kontor/set-price/",
                             {"package": pk, "group": g["id"], "price": "160.00"}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        from kontor.models import KontorPackagePrice
        self.assertEqual(KontorPackagePrice.objects.get(package_id=pk, group_id=g["id"]).price,
                         Decimal("160.00"))

    def test_margin_rule_and_recompute_on_reimport(self):
        from kontor.models import KontorPackagePrice, KontorPriceGroup
        from kontor.services import recompute_group_prices, upsert_packages
        g = self._group()
        pk = KontorPackage.objects.get(znet_id="100")  # كلفة 148
        self.client.post("/api/kontor/set-price/",
                         {"package": pk.id, "group": g["id"], "mode": "percent", "value": "10"},
                         format="json")
        pp = KontorPackagePrice.objects.get(package=pk, group_id=g["id"])
        self.assertEqual(pp.price, Decimal("162.80"))  # 148 + 10%
        # إعادة استيراد بكلفة أعلى ⇐ السعر المرتبط يُعاد حسابه
        upsert_packages(self.tenant, parse_feed(FEED.replace("148.00", "200.00")))
        recompute_group_prices(KontorPriceGroup.objects.get(pk=g["id"]))
        pp.refresh_from_db()
        self.assertEqual(pp.price, Decimal("220.00"))  # 200 + 10%

    def test_bulk_price_to_recommended(self):
        g = self._group()
        p = KontorPackage.objects.filter(operator="Turkcell").first()
        p.recommended_price = Decimal("500"); p.save()
        r = self.client.post("/api/kontor/bulk-price/",
                             {"group": g["id"], "operator": "Turkcell", "to_recommended": True},
                             format="json")
        self.assertEqual(r.status_code, 200)
        from kontor.models import KontorPackagePrice
        self.assertEqual(KontorPackagePrice.objects.get(package=p, group_id=g["id"]).price, Decimal("500"))

    def test_dealer_price_resolution(self):
        from kontor.models import KontorDealerSetting
        from kontor.services import dealer_price
        g = self._group()
        pk = KontorPackage.objects.get(znet_id="100")
        self.client.post("/api/kontor/set-price/",
                         {"package": pk.id, "group": g["id"], "price": "170.00"}, format="json")
        # بلا ربط ⇐ السعر الموصى
        pk.recommended_price = Decimal("199"); pk.save()
        self.assertEqual(dealer_price(self.dealer, pk), Decimal("199.00"))
        # بعد الربط ⇐ سعر المجموعة
        KontorDealerSetting.objects.create(tenant=self.tenant, dealer=self.dealer,
                                           operator="Turkcell", group_id=g["id"])
        self.assertEqual(dealer_price(self.dealer, pk), Decimal("170.00"))

    def test_dealer_settings_api(self):
        g = self._group()
        r = self.client.patch("/api/kontor/dealer-settings/",
                              [{"dealer": self.dealer.id, "operator": "Vodafone",
                                "group": g["id"], "can_query": False}], format="json")
        self.assertEqual(r.status_code, 200)
        from kontor.services import dealer_can_query
        self.assertFalse(dealer_can_query(self.dealer, "Vodafone"))
        self.assertTrue(dealer_can_query(self.dealer, "Turkcell"))  # افتراضي

    def test_bulk_price_selected_packages_and_recommended_column(self):
        from kontor.models import KontorPackagePrice
        g = self._group()
        p = KontorPackage.objects.get(znet_id="100")  # كلفة 148
        others = KontorPackage.objects.filter(operator="Turkcell").exclude(pk=p.pk)
        r = self.client.post("/api/kontor/bulk-price/",
                             {"group": g["id"], "operator": "Turkcell", "mode": "fixed",
                              "value": "2", "packages": [p.pk]}, format="json")
        self.assertEqual(r.json()["updated"], 1)
        self.assertEqual(KontorPackagePrice.objects.get(package=p).price, Decimal("150.00"))
        self.assertFalse(KontorPackagePrice.objects.filter(package__in=others).exists())
        # عمود الموصى: يُكتب في الباقة نفسها مع التقريب لأعلى إلى النصف
        self.client.post("/api/kontor/bulk-price/",
                         {"group": "recommended", "operator": "Turkcell", "mode": "percent",
                          "value": "10", "round": True, "packages": [p.pk]}, format="json")
        p.refresh_from_db()
        self.assertEqual(p.recommended_price, Decimal("163.00"))  # 162.80 ⇐ 163

    def test_bulk_price_skips_zero_cost(self):
        g = self._group()
        p = KontorPackage.objects.get(znet_id="100")
        p.cost_price = Decimal("0"); p.save()
        r = self.client.post("/api/kontor/bulk-price/",
                             {"group": g["id"], "operator": "Turkcell", "mode": "percent",
                              "value": "5", "packages": [p.pk]}, format="json").json()
        self.assertEqual(r["updated"], 0)
        self.assertEqual(r["skipped_zero_cost"], [p.name])

    def test_packages_bulk_edit(self):
        ids = list(KontorPackage.objects.filter(operator="Turkcell").values_list("pk", flat=True))
        r = self.client.post("/api/kontor/packages/bulk/",
                             {"ids": ids, "status": "passive", "kind": "offer"}, format="json")
        self.assertEqual(r.json()["updated"], len(ids))
        self.assertFalse(KontorPackage.objects.filter(pk__in=ids, status="active").exists())
        self.assertEqual(self.client.post("/api/kontor/packages/bulk/", {"ids": ids, "status": "x"},
                                          format="json").status_code, 400)

    def test_admin_orders_summary_and_filters(self):
        from kontor.models import KontorOrder
        p = KontorPackage.objects.get(znet_id="100")
        for gsm, st in (("5321112233", "success"), ("5329998877", "failed")):
            KontorOrder.objects.create(tenant=self.tenant, dealer=self.dealer, package=p,
                                       operator=p.operator, gsm=gsm, status=st,
                                       sell_price=Decimal("160"), profit=Decimal("12"))
        d = self.client.get("/api/kontor/orders/?status=success").json()
        self.assertEqual(len(d["results"]), 1)
        self.assertEqual(d["summary"]["counts"], {"success": 1, "failed": 1})
        self.assertEqual(Decimal(d["summary"]["profit"]), Decimal("12"))
        d = self.client.get("/api/kontor/orders/?q=99988").json()
        self.assertEqual([o["gsm"] for o in d["results"]], ["5329998877"])

    def test_dealer_cannot_access_pricing(self):
        self.client.force_authenticate(self.dealer)
        self.assertEqual(self.client.get("/api/kontor/price-matrix/?operator=Turkcell").status_code, 403)


class PanelParseTest(TestCase):
    """تحليل مخرجات اللوحة من عيّنة حقيقية (kontor/tests_fixture.html)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        import os
        path = os.path.join(os.path.dirname(__file__), "tests_fixture.html")
        with open(path, encoding="utf-8") as f:
            cls.html = f.read()

    def test_operator_detection_last_loader_wins(self):
        from kontor.panel_parse import parse_operator
        self.assertEqual(parse_operator("gsm_loader('Turkcell'); gsm_loader('VODAFONE','');"), "Vodafone")
        self.assertEqual(parse_operator("gsm_loader('Turkcell'); gsm_loader('AVEA','');"), "Avea")
        self.assertEqual(parse_operator("gsm_loader('Turkcell');"), "Turkcell")
        self.assertIsNone(parse_operator("<html>no loader</html>"))

    def test_parse_offers_from_fixture(self):
        from kontor.panel_parse import parse_offers
        rows = parse_offers(self.html)
        self.assertTrue(len(rows) >= 3)
        first = rows[0]
        self.assertEqual(first["znet_id"], "476647")       # 476647.00 ⇐ 476647
        self.assertEqual(first["operator"], "Turkcell")
        self.assertEqual(first["line_type"], "Ses")
        self.assertTrue(first["is_offer"])                  # خلفية وردية
        self.assertEqual(first["cost"], "970.00")
        self.assertEqual(first["days"], 30)
        self.assertEqual(first["gb"], 30)

    def test_offer_flag_matches_pink_only(self):
        from kontor.panel_parse import parse_offers
        rows = parse_offers(self.html)
        # في العيّنة: صفوف وردية (عرض) وأخرى صفراء (عامة)
        self.assertTrue(any(r["is_offer"] for r in rows))

    def test_norm_id_handles_integers_and_floats(self):
        from kontor.panel_parse import _norm_id
        self.assertEqual(_norm_id("476647.00"), "476647")
        self.assertEqual(_norm_id("100"), "100")
        self.assertEqual(_norm_id("abc"), "abc")


class StoreTest(APITestCase):
    def setUp(self):
        from core.models import Wallet
        self.tenant = Tenant.objects.create(subdomain="kon", name="متجر", base_currency="TRY")
        self.dealer = User.objects.create(login_id="bayi", name="وكيل", tenant=self.tenant,
                                          role=User.Role.BAYI)
        Wallet.objects.create(tenant=self.tenant, user=self.dealer, balance=Decimal("0"))
        upsert_packages(self.tenant, parse_feed(FEED))
        # تفعيل باقة Turkcell وسعرها الموصى
        self.p = KontorPackage.objects.get(znet_id="476647")
        self.p.recommended_price = Decimal("1000"); self.p.status = "active"; self.p.save()
        self.client.force_authenticate(self.dealer)

    def test_clean_gsm(self):
        from kontor.views_store import _clean_gsm, _valid
        self.assertEqual(_clean_gsm("0544 219 99 92"), "5442199992")
        self.assertEqual(_clean_gsm("905442199992"), "5442199992")
        self.assertEqual(_clean_gsm("٥٤٤٢١٩٩٩٩٢"), "5442199992")
        self.assertTrue(_valid("5442199992"))
        self.assertFalse(_valid("44219"))

    def test_detect(self):
        from unittest.mock import patch
        with patch("kontor.session_client.detect_operator", return_value="Turkcell"):
            r = self.client.post("/api/kontor/store/detect/", {"gsm": "5442199992"}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()["operator"], "Turkcell")

    def test_detect_bad_number(self):
        r = self.client.post("/api/kontor/store/detect/", {"gsm": "123"}, format="json")
        self.assertEqual(r.status_code, 400)

    def test_store_packages_grouped(self):
        r = self.client.get("/api/kontor/store/packages/?operator=Turkcell")
        self.assertEqual(r.status_code, 200, r.content)
        data = r.json()
        self.assertEqual(data["operator"], "Turkcell")
        # فئتان لـTurkcell في العيّنة (Ses, Tam)
        names = {c["line_type"] for c in data["categories"]}
        self.assertTrue({"Ses", "Tam"} <= names)

    def test_offers_live_merge(self):
        from unittest.mock import patch
        fake = [{"znet_id": "476647", "operator": "Turkcell", "line_type": "Ses",
                 "name": "x", "details": "d", "days": 30, "gb": 30, "minutes": 1000,
                 "shown_price": "1000", "cost": "970", "is_offer": True}]
        with patch("kontor.session_client.fetch_offers", return_value=fake):
            r = self.client.post("/api/kontor/store/offers/",
                                 {"gsm": "5442199992", "operator": "Turkcell"}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        offers = r.json()["offers"]
        self.assertEqual(len(offers), 1)
        self.assertTrue(offers[0]["is_offer"])
        self.assertEqual(offers[0]["price"], "1000.00")  # السعر الموصى (بلا مجموعة)

    def test_offers_denied_when_not_allowed(self):
        from kontor.models import KontorDealerSetting
        KontorDealerSetting.objects.create(tenant=self.tenant, dealer=self.dealer,
                                           operator="Turkcell", can_query=False)
        r = self.client.post("/api/kontor/store/offers/",
                             {"gsm": "5442199992", "operator": "Turkcell"}, format="json")
        self.assertEqual(r.status_code, 403)


class ExecutionTest(APITestCase):
    def setUp(self):
        from core.models import Wallet
        from providers.models import Provider
        self.tenant = Tenant.objects.create(subdomain="kon", name="متجر", base_currency="TRY")
        self.dealer = User.objects.create(login_id="bayi", name="وكيل", tenant=self.tenant,
                                          role=User.Role.BAYI)
        self.wallet = Wallet.objects.create(tenant=self.tenant, user=self.dealer, balance=Decimal("5000"))
        Provider.objects.create(tenant=self.tenant, name="ZNET", type=Provider.Type.SAME_SYSTEM,
                                config={"code": "znet", "base_url": "http://z", "kod": "k", "sifre": "s"})
        upsert_packages(self.tenant, parse_feed(FEED))
        self.p = KontorPackage.objects.get(znet_id="476647")
        self.p.recommended_price = Decimal("1000"); self.p.cost_price = Decimal("970"); self.p.save()
        self.client.force_authenticate(self.dealer)

    def _buy(self):
        return self.client.post("/api/kontor/store/buy/",
                               {"package": self.p.id, "gsm": "5442199992"}, format="json")

    def test_accepted_debits_and_processing(self):
        from unittest.mock import MagicMock, patch
        with patch("kontor.execution.requests.get", return_value=MagicMock(text="OK|1|Talebiniz İşleme Alındı|970.00")):
            r = self._buy()
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.json()["status"], "processing")
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, Decimal("4000"))  # 5000 - 1000

    def test_rejected_refunds(self):
        from unittest.mock import MagicMock, patch
        with patch("kontor.execution.requests.get", return_value=MagicMock(text="OK|3|Hatali numara|0.00")):
            r = self._buy()
        self.assertEqual(r.json()["status"], "refunded")
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, Decimal("5000"))  # أُعيد المبلغ

    def test_insufficient_balance(self):
        self.wallet.balance = Decimal("100"); self.wallet.save()
        r = self._buy()
        self.assertEqual(r.status_code, 400)
        from kontor.models import KontorOrder
        self.assertEqual(KontorOrder.objects.count(), 0)

    def test_poll_success(self):
        from unittest.mock import MagicMock, patch
        from kontor.execution import poll
        from kontor.models import KontorOrder
        with patch("kontor.execution.requests.get", return_value=MagicMock(text="OK|1|ok|970")):
            self._buy()
        o = KontorOrder.objects.latest("id")
        with patch("kontor.execution.requests.get", return_value=MagicMock(text="1:olumlu_islem:970")):
            poll(o)
        o.refresh_from_db()
        self.assertEqual(o.status, "success")

    def test_poll_cancel_refunds(self):
        from unittest.mock import MagicMock, patch
        from kontor.execution import poll
        from kontor.models import KontorOrder
        with patch("kontor.execution.requests.get", return_value=MagicMock(text="OK|1|ok|970")):
            self._buy()
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, Decimal("4000"))
        o = KontorOrder.objects.latest("id")
        with patch("kontor.execution.requests.get", return_value=MagicMock(text="3:iptal nedeni")):
            poll(o)
        o.refresh_from_db()
        self.assertEqual(o.status, "refunded")
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, Decimal("5000"))

    def test_tip_mapping(self):
        from kontor.execution import _tip
        self.assertEqual(_tip(self.p), "ses")  # فئة Ses ⇐ ses

    def test_parse_place(self):
        from kontor.execution import _parse_place
        self.assertEqual(_parse_place("OK|1|ok|5.5")[0], 1)
        self.assertEqual(_parse_place("OK|3|bad|0")[0], 3)
        self.assertEqual(_parse_place("garbage")[0], None)


class CurrencyTest(APITestCase):
    """كلفة ZNET بالليرة ⇐ عملة دفتر المتجر (هنا الدولار) — لا تُعامَل الليرة كأنها دولار."""

    def setUp(self):
        from core.models import Wallet
        from providers.models import Provider
        self.tenant = Tenant.objects.create(subdomain="usd", name="متجر", base_currency="USD",
                                            exchange_rates={"TRY": "40"})
        self.admin = User.objects.create(login_id="own", name="مالك", tenant=self.tenant,
                                         role=User.Role.TENANT_ADMIN)
        self.dealer = User.objects.create(login_id="bayi", name="وكيل", tenant=self.tenant,
                                          role=User.Role.BAYI)
        self.wallet = Wallet.objects.create(tenant=self.tenant, user=self.dealer, balance=Decimal("100"))
        self.prov = Provider.objects.create(
            tenant=self.tenant, name="ZNET", type=Provider.Type.SAME_SYSTEM,
            config={"code": "znet", "base_url": "http://z", "kod": "k", "sifre": "s"})

    def test_import_converts_try_cost_to_base(self):
        upsert_packages(self.tenant, parse_feed(FEED), provider=self.prov)
        p = KontorPackage.objects.get(znet_id="476647")  # 970 ل.ت
        self.assertEqual(p.provider_cost, Decimal("970.00"))
        self.assertEqual(p.cost_price, Decimal("24.25"))  # 970 ÷ 40

    def test_import_refuses_without_rate(self):
        self.tenant.exchange_rates = {}
        self.tenant.save()
        with self.assertRaises(ValueError):
            upsert_packages(self.tenant, parse_feed(FEED), provider=self.prov)
        self.assertFalse(KontorPackage.objects.exists())

    def test_rate_change_reprices_costs_and_linked_cells(self):
        from kontor.models import KontorPackagePrice, KontorPriceGroup
        upsert_packages(self.tenant, parse_feed(FEED), provider=self.prov)
        p = KontorPackage.objects.get(znet_id="476647")
        g = KontorPriceGroup.objects.create(tenant=self.tenant, name="VIP")
        self.client.force_authenticate(self.admin)
        self.client.post("/api/kontor/set-price/", {"package": p.id, "group": g.id,
                                                    "mode": "percent", "value": "10"}, format="json")
        r = self.client.put("/api/settings/exchange/",
                            {"base_currency": "USD", "exchange_rates": {"TRY": "50"}}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        p.refresh_from_db()
        self.assertEqual(p.cost_price, Decimal("19.40"))  # 970 ÷ 50
        self.assertEqual(KontorPackagePrice.objects.get(package=p, group=g).price, Decimal("21.34"))

    def test_buy_debits_base_currency_not_lira(self):
        from unittest.mock import MagicMock, patch
        upsert_packages(self.tenant, parse_feed(FEED), provider=self.prov)
        p = KontorPackage.objects.get(znet_id="476647")
        p.recommended_price = Decimal("26.00"); p.save()
        self.client.force_authenticate(self.dealer)
        with patch("kontor.execution.requests.get", return_value=MagicMock(text="OK|1|ok|970")):
            r = self.client.post("/api/kontor/store/buy/", {"package": p.id, "gsm": "5442199992"}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, Decimal("74.00"))  # 100 − 26$ لا 970

    def test_guards_block_unpriced_and_loss(self):
        from kontor.execution import KontorOrderError, create_order
        upsert_packages(self.tenant, parse_feed(FEED), provider=self.prov)
        p = KontorPackage.objects.get(znet_id="476647")  # كلفة 24.25$
        with self.assertRaises(KontorOrderError):     # بلا سعر موصى
            create_order(self.dealer, p, "5442199992")
        p.recommended_price = Decimal("20"); p.save()
        with self.assertRaises(KontorOrderError):     # دون الكلفة
            create_order(self.dealer, p, "5442199992")
        p.cost_price = Decimal("0"); p.recommended_price = Decimal("30"); p.save()
        with self.assertRaises(KontorOrderError):     # بلا كلفة
            create_order(self.dealer, p, "5442199992")
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, Decimal("100"))


class StoreDisplayTest(APITestCase):
    """أسماء الفئات القصيرة، كرة العروض بنجمة، وسعر بيع الوكيل لزبونه."""

    def setUp(self):
        from core.models import Wallet
        from providers.models import Provider
        self.tenant = Tenant.objects.create(subdomain="kon", name="متجر", base_currency="TRY")
        self.dealer = User.objects.create(login_id="bayi", name="وكيل", tenant=self.tenant,
                                          role=User.Role.BAYI)
        self.wallet = Wallet.objects.create(tenant=self.tenant, user=self.dealer, balance=Decimal("5000"))
        Provider.objects.create(tenant=self.tenant, name="ZNET", type=Provider.Type.SAME_SYSTEM,
                                config={"code": "znet", "base_url": "http://z", "kod": "k", "sifre": "s"})
        upsert_packages(self.tenant, parse_feed(FEED + "Turkcell|Ses|777|500.00|Normal 10GB|^"))
        KontorPackage.objects.update(recommended_price=Decimal("1100"))
        self.client.force_authenticate(self.dealer)

    def test_short_category_names(self):
        names = set(KontorCategory.objects.values_list("line_type", "name"))
        self.assertIn(("Ses", "Ses"), names)
        self.assertIn(("Tam", "Tam"), names)

    def test_offers_split_into_starred_chip(self):
        d = self.client.get("/api/kontor/store/packages/?operator=Turkcell").json()
        chips = {c["name"]: [p["znet_id"] for p in c["packages"]] for c in d["categories"]}
        self.assertEqual(chips["Ses"], ["777"])
        self.assertEqual(chips["Ses*"], ["476647"])  # Fırsat ⇐ عرض
        self.assertIn("recommended_price", d["categories"][0]["packages"][0])

    def test_dealer_sell_price_custom_and_default(self):
        from unittest.mock import MagicMock, patch
        from kontor.models import KontorOrder
        p = KontorPackage.objects.get(znet_id="777")
        with patch("kontor.execution.requests.get", return_value=MagicMock(text="OK|1|ok|500")):
            self.client.post("/api/kontor/store/buy/", {"package": p.id, "gsm": "5442199992",
                                                        "dealer_sell_price": "1250"}, format="json")
            self.client.post("/api/kontor/store/buy/", {"package": p.id, "gsm": "5442199992"}, format="json")
        a, b = KontorOrder.objects.order_by("id")
        self.assertEqual((a.dealer_sell_price, a.dealer_profit), (Decimal("1250.00"), Decimal("150.00")))
        self.assertEqual((b.dealer_sell_price, b.dealer_profit), (Decimal("1100.00"), Decimal("0.00")))
