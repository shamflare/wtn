"""
اختبارات المزوّدين والتوجيه وتعديل الاسم وإعداد الكشف العامّ (/sorgula).

القاعدة التي تحرسها: **لا يُشحن رقمٌ مرّتين ولا يُخصم الوكيل مرّتين.** الانتقال
إلى مزوّد بديل لا يقع إلا بعد رفضٍ صريح أو فشل اتصالٍ قبل الإرسال؛ أمّا انقطاعٌ
بعد الإرسال فقد يكون نُفّذ — فيُتابَع ولا يُعاد.
"""
from decimal import Decimal
from unittest import mock

import requests
from django.test import TestCase
from rest_framework.test import APITestCase

from core.models import Tenant, User, Wallet
from providers.models import Provider

from .execution import create_order, execute, poll
from .models import KontorCategory, KontorOrder, KontorPackage, KontorPackageLink, KontorSessionConfig
from .services import auto_link, parse_feed, upsert_packages

FEED = "Turkcell|Ses|476647|970.00|Fırsat 30GB İndirimli ⭕|^Turkcell|Tam|100|148.00|✅100 TL|^"


def _resp(text):
    return mock.Mock(text=text)


class Base(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(subdomain="kon", name="متجر", base_currency="TRY")
        self.admin = User.objects.create(login_id="own", name="مالك", tenant=self.tenant,
                                         role=User.Role.TENANT_ADMIN)
        self.dealer = User.objects.create(login_id="bayi", name="وكيل", tenant=self.tenant,
                                          role=User.Role.BAYI)
        self.wallet = Wallet.objects.create(tenant=self.tenant, user=self.dealer, balance=Decimal("5000"))
        self.a = Provider.objects.create(tenant=self.tenant, name="ZNET-A", type=Provider.Type.SAME_SYSTEM,
                                         config={"code": "znet", "base_url": "http://a", "kod": "k", "sifre": "s"})
        self.b = Provider.objects.create(tenant=self.tenant, name="ZNET-B", type=Provider.Type.SAME_SYSTEM,
                                         config={"code": "znet", "base_url": "http://b", "kod": "k", "sifre": "s"})
        upsert_packages(self.tenant, parse_feed(FEED), provider=self.a)
        self.p = KontorPackage.objects.get(znet_id="476647")
        self.p.recommended_price = Decimal("1000"); self.p.save()

    def order(self):
        return create_order(self.dealer, self.p, "5442199992")


class ImportAndNameTest(Base):
    def test_import_routes_and_links_to_source_provider(self):
        self.assertEqual(self.p.provider_id, self.a.id)
        link = KontorPackageLink.objects.get(package=self.p, provider=self.a)
        self.assertEqual((link.code, link.cost), ("476647", Decimal("970.00")))

    def test_owner_name_survives_reimport_and_blank_restores(self):
        self.client.force_authenticate(self.admin)
        self.client.patch(f"/api/kontor/packages/{self.p.id}/", {"name": "30 جيجا عرض"}, format="json")
        upsert_packages(self.tenant, parse_feed(FEED.replace("İndirimli", "Yeni")), provider=self.a)
        self.p.refresh_from_db()
        self.assertEqual(self.p.name, "30 جيجا عرض")
        self.assertIn("Yeni", self.p.provider_name)
        self.client.patch(f"/api/kontor/packages/{self.p.id}/", {"name": " "}, format="json")
        self.p.refresh_from_db()
        self.assertEqual(self.p.name, self.p.provider_name)

    def test_unedited_name_follows_znet(self):
        upsert_packages(self.tenant, parse_feed(FEED.replace("İndirimli", "Yeni")), provider=self.a)
        self.p.refresh_from_db()
        self.assertIn("Yeni", self.p.name)


class FailoverTest(Base):
    def setUp(self):
        super().setUp()
        self.p.provider_alt1 = self.b; self.p.save()
        KontorPackageLink.objects.create(tenant=self.tenant, package=self.p, provider=self.b,
                                         code="9001", cost=Decimal("960"))

    def test_rejection_moves_to_alternate_with_its_own_code(self):
        o = self.order()
        with mock.patch("kontor.execution.requests.get",
                        side_effect=[_resp("OK|3|stok yok|"), _resp("OK|1|ok|960")]) as g:
            execute(o)
        o.refresh_from_db()
        self.assertEqual((o.status, o.provider_id), (KontorOrder.Status.PROCESSING, self.b.id))
        self.assertEqual(g.call_args_list[0].kwargs["params"]["kontor"], "476647")
        self.assertEqual(g.call_args_list[1].kwargs["params"]["kontor"], "9001")
        self.assertEqual(o.cost_price, Decimal("960.00"))  # كلفة المزوّد الذي نفّذ فعلاً
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, Decimal("4000.00"))

    def test_all_reject_refunds_once(self):
        o = self.order()
        with mock.patch("kontor.execution.requests.get", side_effect=[_resp("OK|3|x|"), _resp("OK|3|y|")]):
            execute(o)
        o.refresh_from_db()
        self.assertEqual(o.status, KontorOrder.Status.REFUNDED)
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, Decimal("5000.00"))

    def test_read_timeout_is_followed_not_resent(self):
        o = self.order()
        with mock.patch("kontor.execution.requests.get", side_effect=requests.ReadTimeout("slow")) as g:
            execute(o)
        o.refresh_from_db()
        self.assertEqual((o.status, o.provider_id), (KontorOrder.Status.PROCESSING, self.a.id))
        self.assertEqual(g.call_count, 1)  # لم يُرسَل إلى البديل
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, Decimal("4000.00"))  # لا إرجاع — قد يكون نُفّذ

    def test_connect_failure_moves_to_alternate(self):
        o = self.order()
        err = requests.ConnectionError("NewConnectionError: Failed to establish a new connection")
        with mock.patch("kontor.execution.requests.get", side_effect=[err, _resp("OK|1|ok|")]):
            execute(o)
        o.refresh_from_db()
        self.assertEqual(o.provider_id, self.b.id)

    def test_unlinked_alternate_is_skipped(self):
        KontorPackageLink.objects.filter(provider=self.b).delete()
        o = self.order()
        with mock.patch("kontor.execution.requests.get", side_effect=[_resp("OK|3|x|")]) as g:
            execute(o)
        self.assertEqual(g.call_count, 1)
        o.refresh_from_db()
        self.assertEqual(o.status, KontorOrder.Status.REFUNDED)

    def test_poll_uses_order_provider_and_fails_over_on_cancel(self):
        o = self.order()
        with mock.patch("kontor.execution.requests.get", side_effect=[_resp("OK|1|ok|")]):
            execute(o)
        with mock.patch("kontor.execution.requests.get",
                        side_effect=[_resp("3:iptal"), _resp("OK|1|ok|")]) as g:
            poll(o)
        self.assertTrue(g.call_args_list[0].args[0].startswith("http://a/servis/tl_kontrol"))
        self.assertTrue(g.call_args_list[1].args[0].startswith("http://b/servis/tl_servis"))
        o.refresh_from_db()
        self.assertEqual((o.status, o.provider_id), (KontorOrder.Status.PROCESSING, self.b.id))


class RoutingApiTest(Base):
    def setUp(self):
        super().setUp()
        self.client.force_authenticate(self.admin)

    def test_routing_matrix_and_bulk_patch(self):
        d = self.client.get("/api/kontor/routing/?operator=Turkcell").json()
        self.assertEqual({p["name"] for p in d["providers"]}, {"ZNET-A", "ZNET-B"})
        row = next(r for r in d["rows"] if r["id"] == self.p.id)
        self.assertEqual(row["links"][str(self.a.id)]["code"], "476647")
        r = self.client.patch("/api/kontor/routing/", {"packages": [self.p.id], "provider": self.b.id,
                                                       "provider_alt1": self.a.id}, format="json")
        self.assertEqual(r.json()["updated"], 1)
        self.p.refresh_from_db()
        self.assertEqual((self.p.provider_id, self.p.provider_alt1_id), (self.b.id, self.a.id))

    def test_non_kontor_provider_rejected(self):
        other = Provider.objects.create(tenant=self.tenant, name="Barakat", type=Provider.Type.CARD_STORE)
        r = self.client.patch("/api/kontor/routing/", {"packages": [self.p.id], "provider": other.id},
                              format="json")
        self.assertEqual(r.status_code, 400)

    def test_manual_link_and_auto_link(self):
        r = self.client.post("/api/kontor/links/", {"package": self.p.id, "provider": self.b.id,
                                                    "code": "777", "cost": "900"}, format="json")
        self.assertEqual(r.json()["code"], "777")
        feed_b = "Turkcell|Ses|5555|950.00|FIRSAT 30GB INDIRIMLI|^Turkcell|Tam|100|149.00|100 TL|^"
        with mock.patch("kontor.services.fetch_feed", return_value=feed_b):
            rep = auto_link(self.tenant, self.b)
        self.assertEqual((rep["by_id"], rep["by_name"]), (1, 1))  # 100 بالرقم، والعرض بالاسم
        self.assertEqual(KontorPackageLink.objects.get(package=self.p, provider=self.b).code, "5555")


class SorgulaTest(APITestCase):
    def setUp(self):
        self.owner = User.objects.create(login_id="root", name="المبرمج", role=User.Role.PLATFORM_OWNER)

    def test_owner_sets_account_password_never_returned(self):
        self.client.force_authenticate(self.owner)
        r = self.client.put("/api/platform/sorgula/", {"base_url": "https://panel.x/", "username": "u",
                                                       "password": "secret", "security_image": "d"},
                            format="json").json()
        self.assertNotIn("password", r)
        self.assertTrue(r["has_password"] and r["configured"])
        self.assertEqual((r["base_url"], r["security_image"]), ("https://panel.x", "D"))
        # كلمة سر فارغة ⇐ تبقى القديمة
        self.client.put("/api/platform/sorgula/", {"base_url": "https://panel.x", "username": "u2"},
                        format="json")
        self.assertEqual(KontorSessionConfig.get().password, "secret")

    def test_bad_image_letter_rejected(self):
        self.client.force_authenticate(self.owner)
        r = self.client.put("/api/platform/sorgula/", {"base_url": "https://p", "username": "u",
                                                       "security_image": "D=D"}, format="json")
        self.assertEqual(r.status_code, 400)

    def test_live_test_ignores_switch_but_reports_it(self):
        self.client.force_authenticate(self.owner)
        cfg = KontorSessionConfig.get()
        cfg.base_url, cfg.username, cfg.password, cfg.enabled = "https://p", "u", "pw", False
        cfg.save()
        with mock.patch("kontor.session_client.requests.get",
                        return_value=mock.Mock(status_code=200, json=lambda: {"ok": True})):
            r = self.client.post("/api/platform/sorgula/test/", {}, format="json").json()
        self.assertTrue(r["steps"][0]["ok"])                # الدخول جُرِّب رغم الإيقاف
        self.assertEqual(r["steps"][-1]["step"], "التفعيل للمتاجر")
        self.assertFalse(r["ok"])

    def test_store_admin_forbidden(self):
        t = Tenant.objects.create(subdomain="z", name="z")
        admin = User.objects.create(login_id="a", name="a", tenant=t, role=User.Role.TENANT_ADMIN)
        self.client.force_authenticate(admin)
        self.assertEqual(self.client.get("/api/platform/sorgula/").status_code, 403)


class SessionHeadersTest(TestCase):
    def test_db_account_sent_as_headers_and_disable_blocks(self):
        from . import session_client
        cfg = KontorSessionConfig.get()
        cfg.base_url, cfg.username, cfg.password, cfg.security_image = "https://p", "u", "pw", "D"
        cfg.save()
        with mock.patch("kontor.session_client.requests.get",
                        return_value=mock.Mock(status_code=200, json=lambda: {"html": ""})) as g:
            session_client.detect_operator("5442199992")
        self.assertEqual(g.call_args.kwargs["headers"]["X-Kontor-User"], "u")
        cfg.refresh_from_db()
        self.assertIsNotNone(cfg.last_ok_at)
        cfg.enabled = False; cfg.save()
        with self.assertRaises(session_client.SessionError):
            session_client.detect_operator("5442199992")

    def test_unconfigured_falls_back_to_env(self):
        from . import session_client
        with mock.patch("kontor.session_client.requests.get",
                        return_value=mock.Mock(status_code=200, json=lambda: {"html": ""})) as g:
            session_client.detect_operator("5442199992")
        self.assertEqual(g.call_args.kwargs["headers"], {})
