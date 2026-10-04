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
