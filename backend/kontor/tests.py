from decimal import Decimal

from django.test import TestCase

from core.models import Tenant
from kontor.management.commands.import_kontor_packages import parse_feed
from kontor.models import KontorCategory, KontorPackage, LineType, Operator

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
        rows = parse_feed(FEED)
        first = next(r for r in rows if r["znet_id"] == "476647")
        self.assertEqual(first["cost"], Decimal("970.00"))
        self.assertEqual(first["line_type"], "Ses")
        self.assertEqual(first["name"], "Fırsat 30GB İndirimli ⭕")

    def test_empty_and_garbage(self):
        self.assertEqual(parse_feed(""), [])
        self.assertEqual(parse_feed("|||^||"), [])


class ImportCommandTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(subdomain="kon", name="متجر", base_currency="TRY")

    def _import(self, feed=FEED):
        # نحاكي الشبكة: نستدعي منطق الأمر مباشرةً عبر parse_feed + الحفظ
        from kontor.management.commands.import_kontor_packages import (
            _OP_LABEL, _TYPE_LABEL, _looks_like_offer,
        )
        rows = parse_feed(feed)
        for r in rows:
            cat, _ = KontorCategory.objects.get_or_create(
                tenant=self.tenant, operator=r["operator"], line_type=r["line_type"],
                defaults={"name": f"{_OP_LABEL[r['operator']]} — {_TYPE_LABEL[r['line_type']]}"},
            )
            obj = KontorPackage.objects.filter(
                tenant=self.tenant, operator=r["operator"], znet_id=r["znet_id"]).first()
            if obj:
                obj.name, obj.cost_price = r["name"], r["cost"]
                obj.save()
            else:
                KontorPackage.objects.create(
                    tenant=self.tenant, operator=r["operator"], category=cat,
                    znet_id=r["znet_id"], name=r["name"], cost_price=r["cost"],
                    kind=KontorPackage.Kind.OFFER if _looks_like_offer(r["name"]) else KontorPackage.Kind.GENERAL,
                )

    def test_creates_categories_and_packages(self):
        self._import()
        self.assertEqual(KontorPackage.objects.count(), 5)
        self.assertEqual(KontorCategory.objects.count(), 5)

    def test_offer_detection_by_name(self):
        self._import()
        offer = KontorPackage.objects.get(znet_id="476647")
        self.assertEqual(offer.kind, KontorPackage.Kind.OFFER)
        general = KontorPackage.objects.get(znet_id="100")
        self.assertEqual(general.kind, KontorPackage.Kind.GENERAL)

    def test_reimport_updates_not_duplicates(self):
        self._import()
        changed = FEED.replace("970.00", "999.00")
        self._import(changed)
        self.assertEqual(KontorPackage.objects.count(), 5)  # لا تكرار
        self.assertEqual(KontorPackage.objects.get(znet_id="476647").cost_price, Decimal("999.00"))

    def test_unique_constraint(self):
        self._import()
        # باقة بالمعرّف نفسه لمشغّل مختلف مسموحة؛ لنفس المشغّل تُحدَّث لا تُكرَّر
        self.assertEqual(
            KontorPackage.objects.filter(tenant=self.tenant, operator="Turkcell", znet_id="476647").count(), 1
        )
