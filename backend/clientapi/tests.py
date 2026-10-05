"""
اختبارات الواجهة الخارجية.

القاعدة التي تحرسها فوق كل شيء: **نفس `order_uuid` لا يشحن مرّتين ولا يخصم
مرّتين، مهما تكرّر النداء.** الشبكة تنقطع بعد الشحن وقبل وصول الردّ، فيعيد
العميل المحاولة — وهذا أكثر ما يكلّف مالاً حقيقياً في هذا الباب.
"""
from decimal import Decimal
from unittest import mock
from uuid import UUID, uuid4

from django.db import IntegrityError, transaction
from rest_framework.test import APITestCase

from catalog.models import Game, PriceGroup, Product, ProductPrice
from core.models import Tenant, User, Wallet
from orders.models import Order

from .models import ApiToken

# معرّف ثابت لمحاكاة السباق — العشوائي لا يلزم هنا وثباته يجعل الاختبار مقروءاً
SHARED_UUID = UUID("11111111-2222-3333-4444-555555555555")


class ClientApiTest(APITestCase):

    def setUp(self):
        self.tenant = Tenant.objects.create(subdomain="t1", name="متجر", base_currency="USD")
        self.group = PriceGroup.objects.create(tenant=self.tenant, name="عادية")
        self.game = Game.objects.create(tenant=self.tenant, name="PUBG")
        self.product = Product.objects.create(
            tenant=self.tenant, game=self.game, name="60 UC",
            cost_price=Decimal("6"), recommended_price=Decimal("12"),
        )
        ProductPrice.objects.create(
            tenant=self.tenant, product=self.product,
            price_group=self.group, price=Decimal("8"),
        )
        self.dealer = User.objects.create(
            login_id="d1", name="وكيل", tenant=self.tenant,
            role=User.Role.BAYI, price_group=self.group, dealer_no=1,
            api_access_allowed=True,
        )
        self.wallet = Wallet.objects.create(
            tenant=self.tenant, user=self.dealer, balance=Decimal("100"),
        )
        self.token = ApiToken.objects.create(user=self.dealer)

    def get(self, path, token=True, **params):
        headers = {"HTTP_API_TOKEN": self.token.token} if token else {}
        return self.client.get(path, params, **headers)

    def order_url(self, pid=None):
        return f"/client/api/newOrder/{pid or self.product.id}/params"

    # ————————————————— المصادقة —————————————————

    def test_missing_token_returns_120(self):
        r = self.get("/client/api/profile", token=False)
        self.assertEqual(r.status_code, 401)
        self.assertEqual(r.json()["code"], 120)
        self.assertEqual(r.json()["message"], "Api Token is required!")

    def test_invalid_token_returns_121(self):
        r = self.client.get("/client/api/profile", **{"HTTP_API_TOKEN": "nope"})
        self.assertEqual(r.json()["code"], 121)

    def test_regenerated_token_kills_the_old_one(self):
        old = self.token.token
        self.token.token = "brand-new-token-value"
        self.token.save(update_fields=["token"])
        r = self.client.get("/client/api/profile", **{"HTTP_API_TOKEN": old})
        self.assertEqual(r.json()["code"], 121)

    def test_suspended_dealer_returns_122(self):
        self.dealer.status = User.Status.PASSIVE
        self.dealer.save(update_fields=["status"])
        self.assertEqual(self.get("/client/api/profile").json()["code"], 122)

    def test_suspended_tenant_returns_122(self):
        self.tenant.status = Tenant.Status.SUSPENDED
        self.tenant.save(update_fields=["status"])
        self.assertEqual(self.get("/client/api/profile").json()["code"], 122)

    def test_dealer_without_permission_returns_123(self):
        """مغلق افتراضياً: مفتاحٌ صحيح لا يكفي — يلزم إذن صاحب المتجر."""
        self.dealer.api_access_allowed = False
        self.dealer.save(update_fields=["api_access_allowed"])
        body = self.get("/client/api/profile").json()
        self.assertEqual(body["code"], 123)
        self.assertNotEqual(body["code"], 122)  # ليس إيقافاً — تشخيصان مختلفان

    def test_revoking_permission_stops_a_live_link_at_once(self):
        """
        السحب يوقف الربط فوراً لا عند توليد مفتاح جديد — وإلّا بقي ربطٌ سُحب
        إذنه يشتري إلى الأبد، لأن أحداً لن يولّد مفتاحاً بعد السحب.
        """
        self.assertEqual(self.get("/client/api/profile").status_code, 200)
        self.dealer.api_access_allowed = False
        self.dealer.save(update_fields=["api_access_allowed"])
        self.assertEqual(self.get("/client/api/profile").json()["code"], 123)

    def test_permission_blocks_orders_too_not_just_reads(self):
        self.dealer.api_access_allowed = False
        self.dealer.save(update_fields=["api_access_allowed"])
        r = self.get(self.order_url(), qty="1", order_uuid=str(uuid4()))
        self.assertEqual(r.json()["code"], 123)
        self.assertEqual(Order.objects.count(), 0)
        self.assertEqual(Wallet.objects.get(pk=self.wallet.pk).balance, Decimal("100"))

    def test_restoring_permission_keeps_the_same_key(self):
        """إعادة الإذن تُحيي المفتاح نفسه — فلا يُعاد ضبط الجهة الخارجية."""
        before = self.token.token
        self.dealer.api_access_allowed = False
        self.dealer.save(update_fields=["api_access_allowed"])
        self.dealer.api_access_allowed = True
        self.dealer.save(update_fields=["api_access_allowed"])
        self.assertEqual(self.get("/client/api/profile").status_code, 200)
        self.assertEqual(ApiToken.objects.get(user=self.dealer).token, before)

    # ————————————————— الرصيد والكتالوج —————————————————

    def test_profile_shape(self):
        d = self.get("/client/api/profile").json()["data"]
        self.assertEqual(d["balance"], "100.00")
        self.assertEqual(d["available"], "100.00")
        self.assertEqual(d["currency"], "USD")

    def test_products_uses_this_dealers_price(self):
        rows = self.get("/client/api/products").json()["data"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["id"], self.product.id)
        self.assertEqual(rows[0]["price"], "8.00")          # سعر مجموعته لا سعر التوصية
        self.assertEqual(rows[0]["category_name"], "PUBG")
        self.assertEqual(rows[0]["params"], [])

    def test_products_declares_player_id_when_required(self):
        self.game.require_player_id = True
        self.game.save(update_fields=["require_player_id"])
        self.assertEqual(self.get("/client/api/products").json()["data"][0]["params"], ["playerId"])

    def test_products_hides_other_tenants(self):
        other = Tenant.objects.create(subdomain="t2", name="آخر")
        g = Game.objects.create(tenant=other, name="لعبة أخرى")
        Product.objects.create(tenant=other, game=g, name="سرّي",
                               cost_price=Decimal("1"), recommended_price=Decimal("2"))
        names = [x["name"] for x in self.get("/client/api/products").json()["data"]]
        self.assertNotIn("سرّي", names)

    # ————————————————— منع التكرار: القلب —————————————————

    def test_same_uuid_never_charges_twice(self):
        u = str(uuid4())
        first = self.get(self.order_url(), qty="1", order_uuid=u).json()
        after_first = Wallet.objects.get(pk=self.wallet.pk).balance

        second = self.get(self.order_url(), qty="1", order_uuid=u).json()
        after_second = Wallet.objects.get(pk=self.wallet.pk).balance

        self.assertEqual(first["data"]["order_id"], second["data"]["order_id"])
        self.assertTrue(second.get("duplicate"))
        self.assertEqual(after_first, Decimal("92.00"))   # خُصم مرّة واحدة
        self.assertEqual(after_second, after_first)       # ولم يُخصم ثانيةً
        self.assertEqual(Order.objects.count(), 1)

    def test_ten_retries_still_one_order(self):
        u = str(uuid4())
        for _ in range(10):
            self.get(self.order_url(), qty="1", order_uuid=u)
        self.assertEqual(Order.objects.count(), 1)
        self.assertEqual(Wallet.objects.get(pk=self.wallet.pk).balance, Decimal("92.00"))

    def test_different_uuid_is_a_new_order(self):
        self.get(self.order_url(), qty="1", order_uuid=str(uuid4()))
        self.get(self.order_url(), qty="1", order_uuid=str(uuid4()))
        self.assertEqual(Order.objects.count(), 2)
        self.assertEqual(Wallet.objects.get(pk=self.wallet.pk).balance, Decimal("84.00"))

    def test_uuid_is_scoped_to_the_dealer(self):
        """وكيلان يرسلان المعرّف نفسه — طلبان مستقلّان، ولا يرى أحدهما طلب الآخر."""
        other = User.objects.create(
            login_id="d2", name="وكيل ٢", tenant=self.tenant,
            role=User.Role.BAYI, price_group=self.group, dealer_no=2,
            api_access_allowed=True,
        )
        Wallet.objects.create(tenant=self.tenant, user=other, balance=Decimal("100"))
        other_token = ApiToken.objects.create(user=other)

        u = str(uuid4())
        a = self.get(self.order_url(), qty="1", order_uuid=u).json()
        b = self.client.get(self.order_url(), {"qty": "1", "order_uuid": u},
                            **{"HTTP_API_TOKEN": other_token.token}).json()

        self.assertNotEqual(a["data"]["order_id"], b["data"]["order_id"])
        self.assertEqual(Order.objects.count(), 2)

    def test_database_itself_refuses_a_duplicate(self):
        """
        الضمانة لا تتّكئ على فحصٍ في الكود: نداءان متوازيان قد يمرّان معاً من
        «هل الطلب موجود؟» قبل أن يُكتب أوّلهما. القيد في القاعدة هو الحارس.
        """
        u = str(uuid4())
        self.get(self.order_url(), qty="1", order_uuid=u)
        first = Order.objects.get()
        with self.assertRaises(IntegrityError), transaction.atomic():
            Order.objects.create(
                tenant=self.tenant, receipt_no="DUP1", dealer=self.dealer,
                game=self.game, product=self.product,
                cost_price=Decimal("6"), sell_price=Decimal("8"), profit=Decimal("2"),
                client_uuid=first.client_uuid,
            )

    def test_race_loser_gets_the_winners_order_not_an_error(self):
        """
        محاكاة السباق: القيد يرفض الثاني، فيجب أن يُعيد المستخدمُ طلبَ الأوّل
        لا خطأً — وإلّا ظنّ العميل أن الطلب فشل فأعاده بمعرّف جديد فاشترى مرّتين.
        """
        u = str(uuid4())
        winner = self.get(self.order_url(), qty="1", order_uuid=u).json()["data"]

        # نداء بمعرّف مختلف، لكن `create_order` يسقط بـ IntegrityError كما لو
        # سبقنا نداءٌ متوازٍ إلى المعرّف نفسه
        Order.objects.filter(receipt_no=winner["order_id"]).update(client_uuid=SHARED_UUID)
        with mock.patch("orders.services.create_order", side_effect=IntegrityError("dup")):
            body = self.get(self.order_url(), qty="1", order_uuid=str(SHARED_UUID)).json()

        self.assertTrue(body.get("duplicate"))
        self.assertEqual(body["data"]["order_id"], winner["order_id"])
        self.assertEqual(Order.objects.count(), 1)

    def test_missing_uuid_returns_107(self):
        r = self.get(self.order_url(), qty="1")
        self.assertEqual(r.json()["code"], 107)
        self.assertEqual(Order.objects.count(), 0)

    def test_malformed_uuid_returns_107(self):
        self.assertEqual(self.get(self.order_url(), qty="1", order_uuid="123").json()["code"], 107)

    # ————————————————— بقيّة قواعد الطلب —————————————————

    def test_insufficient_balance_returns_100_and_creates_nothing(self):
        self.wallet.balance = Decimal("1")
        self.wallet.save(update_fields=["balance"])
        r = self.get(self.order_url(), qty="1", order_uuid=str(uuid4()))
        self.assertEqual(r.json()["code"], 100)
        self.assertEqual(Order.objects.count(), 0)
        self.assertEqual(Wallet.objects.get(pk=self.wallet.pk).balance, Decimal("1"))

    def test_player_id_required_returns_108(self):
        self.game.require_player_id = True
        self.game.save(update_fields=["require_player_id"])
        r = self.get(self.order_url(), qty="1", order_uuid=str(uuid4()))
        self.assertEqual(r.json()["code"], 108)
        self.assertEqual(Order.objects.count(), 0)

    def test_qty_other_than_one_is_refused(self):
        r = self.get(self.order_url(), qty="3", order_uuid=str(uuid4()))
        self.assertEqual(r.json()["code"], 109)
        self.assertEqual(Order.objects.count(), 0)

    def test_unknown_product_returns_105(self):
        self.assertEqual(
            self.get(self.order_url(99999), qty="1", order_uuid=str(uuid4())).json()["code"], 105,
        )

    def test_cannot_order_another_tenants_product(self):
        other = Tenant.objects.create(subdomain="t3", name="آخر")
        g = Game.objects.create(tenant=other, name="لعبة")
        p = Product.objects.create(tenant=other, game=g, name="سرّي",
                                   cost_price=Decimal("1"), recommended_price=Decimal("2"))
        r = self.get(self.order_url(p.id), qty="1", order_uuid=str(uuid4()))
        self.assertEqual(r.json()["code"], 105)

    def test_passive_product_returns_106(self):
        self.product.status = Product.Status.PASSIVE
        self.product.save(update_fields=["status"])
        self.assertEqual(
            self.get(self.order_url(), qty="1", order_uuid=str(uuid4())).json()["code"], 106,
        )

    def test_order_without_provider_stays_wait(self):
        """منتج بلا تنفيذ آلي: الطلب قائم وينتظر المتجر — لا 'ناجح' ولا 'مرفوض'."""
        body = self.get(self.order_url(), qty="1", order_uuid=str(uuid4())).json()
        self.assertEqual(body["status"], "wait")
        self.assertEqual(body["data"]["price"], "8.00")
        self.assertEqual(body["data"]["quantity"], 1)

    # ————————————————— الاستعلام —————————————————

    def test_check_by_receipt_and_by_uuid(self):
        u = str(uuid4())
        created = self.get(self.order_url(), qty="1", order_uuid=u).json()["data"]

        by_id = self.get("/client/api/check", orders=created["order_id"]).json()["data"]
        self.assertEqual(len(by_id), 1)
        self.assertEqual(by_id[0]["order_id"], created["order_id"])

        by_uuid = self.get("/client/api/check", orders=u, uuid="1").json()["data"]
        self.assertEqual(len(by_uuid), 1)
        self.assertEqual(by_uuid[0]["order_uuid"], u)

    def test_check_reports_the_current_status_not_the_old_one(self):
        u = str(uuid4())
        created = self.get(self.order_url(), qty="1", order_uuid=u).json()["data"]
        order = Order.objects.get(receipt_no=created["order_id"])
        order.status = Order.Status.SUCCESS
        order.pin_result = "PIN-9"
        order.save(update_fields=["status", "pin_result"])

        row = self.get("/client/api/check", orders=u, uuid="1").json()["data"][0]
        self.assertEqual(row["status"], "accept")
        self.assertEqual(row["pin"], "PIN-9")

    def test_stuck_order_reads_as_wait_not_reject(self):
        """العالق ينتظر تدخّلاً يدوياً ومالُه محجوز — قولُه reject يدفع لإعادة الشراء."""
        u = str(uuid4())
        created = self.get(self.order_url(), qty="1", order_uuid=u).json()["data"]
        Order.objects.filter(receipt_no=created["order_id"]).update(status=Order.Status.STUCK)
        self.assertEqual(
            self.get("/client/api/check", orders=u, uuid="1").json()["data"][0]["status"], "wait",
        )

    def test_check_cannot_read_another_dealers_order(self):
        other = User.objects.create(
            login_id="d9", name="غريب", tenant=self.tenant,
            role=User.Role.BAYI, price_group=self.group, dealer_no=9,
            api_access_allowed=True,
        )
        Wallet.objects.create(tenant=self.tenant, user=other, balance=Decimal("100"))
        other_token = ApiToken.objects.create(user=other)

        mine = self.get(self.order_url(), qty="1", order_uuid=str(uuid4())).json()["data"]
        r = self.client.get("/client/api/check", {"orders": mine["order_id"]},
                            **{"HTTP_API_TOKEN": other_token.token})
        self.assertEqual(r.json()["data"], [])

    def test_check_with_no_orders_param_is_empty_not_error(self):
        self.assertEqual(self.get("/client/api/check").json(), {"status": "OK", "data": []})


class StoreApiTokenPageTest(APITestCase):
    """صفحة API في لوحة الوكيل."""

    def setUp(self):
        self.tenant = Tenant.objects.create(subdomain="t1", name="متجر")
        self.dealer = User.objects.create(
            login_id="d1", name="وكيل", tenant=self.tenant, role=User.Role.BAYI,
            api_access_allowed=True,
        )
        self.dealer.set_password("pw12345")
        self.dealer.save()
        Wallet.objects.create(tenant=self.tenant, user=self.dealer)

    def test_unpermitted_dealer_sees_an_explanation_not_a_key(self):
        """مغلق ⇒ لا يُولَّد مفتاح أصلاً، والردّ 200 بشرح لا 403 بخطأ."""
        self.dealer.api_access_allowed = False
        self.dealer.save(update_fields=["api_access_allowed"])
        self.client.force_authenticate(self.dealer)
        r = self.client.get("/api/store/api-token/")
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.json()["allowed"])
        self.assertNotIn("token", r.json())
        self.assertEqual(ApiToken.objects.count(), 0)

    def test_first_visit_creates_a_token(self):
        self.client.force_authenticate(self.dealer)
        r = self.client.get("/api/store/api-token/")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(len(r.json()["token"]) >= 32)
        self.assertEqual(ApiToken.objects.count(), 1)

    def test_token_is_stable_across_visits(self):
        """
        المفتاح ثابت: يُسلَّم مرّةً لمن يربط ولا يُراجَع. لو تبدّل بزيارةٍ أو
        بإعادة دخولٍ لانقطع كل ربط قائم بلا سبب ولا إنذار.
        """
        self.client.force_authenticate(self.dealer)
        first = self.client.get("/api/store/api-token/").json()["token"]
        for _ in range(5):
            self.assertEqual(self.client.get("/api/store/api-token/").json()["token"], first)
        self.assertEqual(ApiToken.objects.count(), 1)

    def test_regenerate_replaces_the_token(self):
        self.client.force_authenticate(self.dealer)
        first = self.client.get("/api/store/api-token/").json()["token"]
        second = self.client.post("/api/store/api-token/").json()["token"]
        self.assertNotEqual(first, second)
        self.assertEqual(ApiToken.objects.count(), 1)

    def test_store_owner_has_no_api_page(self):
        admin = User.objects.create(
            login_id="a1", name="مدير", tenant=self.tenant, role=User.Role.TENANT_ADMIN,
        )
        self.client.force_authenticate(admin)
        self.assertEqual(self.client.get("/api/store/api-token/").status_code, 403)

    def test_anonymous_is_refused(self):
        self.assertIn(self.client.get("/api/store/api-token/").status_code, (401, 403))


class ClientApiAmountTest(APITestCase):
    """الواجهة الخارجية بلغة ZDK: الباقة بالكمية تُعرض amount بسعر الوحدة، وتُطلب بـqty."""

    setUp_base = ClientApiTest.setUp
    get = ClientApiTest.get
    order_url = ClientApiTest.order_url

    def setUp(self):
        self.setUp_base()
        # 2.00$ لكل 1000 ⇒ سعر الوحدة 0.002$
        self.amount = Product.objects.create(
            tenant=self.tenant, game=self.game, name="Coins", cost_price=Decimal("1"),
            recommended_price=Decimal("2.00"), sale_type="amount",
            qty_min=1000, qty_max=100000, qty_unit=1000)

    def test_listing_and_order_with_quantity(self):
        rows = self.get("/client/api/products").json()["data"]
        row = next(r for r in rows if r["id"] == self.amount.id)
        self.assertEqual((row["product_type"], row["price"]), ("amount", "0.002"))
        self.assertEqual(row["qty_values"], {"min": 1000, "max": 100000})
        body = self.get(self.order_url(self.amount.id), qty="5000",
                        order_uuid="7d1a0e0b-6b67-4b0b-9a0e-1f6b1a2c3d4e", playerId="5").json()
        self.assertEqual(body["data"]["quantity"], 5000)
        self.assertEqual(body["data"]["price"], "10.00")

    def test_qty_still_refused_on_a_fixed_package(self):
        body = self.get(self.order_url(), qty="3",
                        order_uuid="8d1a0e0b-6b67-4b0b-9a0e-1f6b1a2c3d4e", playerId="5").json()
        self.assertEqual(body.get("status"), "error")


class MobileClientApiTest(APITestCase):
    """واجهة شحن الخطوط: نفس عقد الألعاب — ونفس القاعدة: uuid واحد لا يخصم مرّتين."""

    def setUp(self):
        from kontor.models import KontorCategory, KontorPackage
        from providers.models import Provider
        self.tenant = Tenant.objects.create(subdomain="t1", name="متجر", base_currency="USD",
                                            exchange_rates={"TRY": "40"})
        self.dealer = User.objects.create(login_id="d1", name="وكيل", tenant=self.tenant,
                                          role=User.Role.BAYI, dealer_no=1, api_access_allowed=True)
        self.wallet = Wallet.objects.create(tenant=self.tenant, user=self.dealer, balance=Decimal("100"))
        self.token = ApiToken.objects.create(user=self.dealer)
        Provider.objects.create(tenant=self.tenant, name="ZNET", type=Provider.Type.SAME_SYSTEM,
                                config={"code": "znet", "base_url": "http://z", "kod": "k", "sifre": "s"})
        cat = KontorCategory.objects.create(tenant=self.tenant, operator="Turkcell", line_type="Ses", name="Ses")
        self.pkg = KontorPackage.objects.create(
            tenant=self.tenant, operator="Turkcell", category=cat, znet_id="476647",
            name="Fırsat 30GB", kind="offer", provider_cost=Decimal("970"),
            cost_price=Decimal("24.25"), recommended_price=Decimal("26"))
        KontorPackage.objects.create(
            tenant=self.tenant, operator="Turkcell", category=cat, znet_id="9",
            name="Normal", provider_cost=Decimal("400"), cost_price=Decimal("10"),
            recommended_price=Decimal("12"))

    def get(self, path, **params):
        return self.client.get(path, params, HTTP_API_TOKEN=self.token.token)

    def order(self, uid, gsm="5442199992", **extra):
        with mock.patch("kontor.execution.requests.get", return_value=mock.Mock(text="OK|1|ok|970")):
            return self.get(f"/client/api/mobile/newOrder/{self.pkg.id}/params",
                            gsm=gsm, order_uuid=str(uid), **extra)

    def test_packages_list_offers_first_with_link_id(self):
        r = self.get("/client/api/mobile/packages", operator="Turkcell").json()
        self.assertEqual(r["status"], "OK")
        self.assertEqual(r["data"][0]["id"], self.pkg.id)
        self.assertEqual(r["data"][0]["category_name"], "Ses*")
        self.assertEqual(r["data"][0]["price"], "26.00")
        self.assertEqual(r["data"][0]["params"], ["gsm"])
        self.assertEqual(self.get("/client/api/mobile/packages", operator="X").json()["code"], 112)

    def test_new_order_debits_once_per_uuid(self):
        uid = uuid4()
        a = self.order(uid).json()
        b = self.order(uid).json()
        self.assertEqual(a["status"], "wait")
        self.assertTrue(b["duplicate"])
        self.assertEqual(a["data"]["order_id"], b["data"]["order_id"])
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, Decimal("74.00"))  # خُصم مرّة واحدة

    def test_insufficient_balance_is_100_and_not_debited(self):
        self.wallet.balance = Decimal("5"); self.wallet.save()
        self.assertEqual(self.order(uuid4()).json()["code"], 100)
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, Decimal("5"))

    def test_validation_errors(self):
        self.assertEqual(self.order(uuid4(), gsm="123").json()["code"], 111)
        self.assertEqual(self.get(f"/client/api/mobile/newOrder/{self.pkg.id}/params",
                                  gsm="5442199992").json()["code"], 107)
        self.assertEqual(self.get("/client/api/mobile/newOrder/99999/params", gsm="5442199992",
                                  order_uuid=str(uuid4())).status_code, 404)

    def test_rejected_order_refunds_and_reports_reject(self):
        with mock.patch("kontor.execution.requests.get", return_value=mock.Mock(text="OK|3|bakiye yok|")):
            r = self.get(f"/client/api/mobile/newOrder/{self.pkg.id}/params",
                         gsm="5442199992", order_uuid=str(uuid4())).json()
        self.assertEqual(r["status"], "reject")
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, Decimal("100.00"))

    def test_check_by_id_and_uuid(self):
        uid = uuid4()
        oid = self.order(uid).json()["data"]["order_id"]
        by_id = self.get("/client/api/mobile/check", orders=oid).json()["data"]
        by_uuid = self.get("/client/api/mobile/check", orders=str(uid), uuid="1").json()["data"]
        self.assertEqual(by_id[0]["order_id"], oid)
        self.assertEqual(by_uuid[0]["order_uuid"], str(uid))

    def test_detect_and_offers(self):
        with mock.patch("kontor.session_client.detect_operator", return_value="Vodafone"):
            d = self.get("/client/api/mobile/detect", gsm="05442199992").json()
        self.assertEqual(d["data"]["operator"], "Vodafone")
        offers = [{"znet_id": "476647", "is_offer": True}]
        with mock.patch("kontor.session_client.fetch_offers", return_value=offers):
            o = self.get("/client/api/mobile/offers", gsm="5442199992", operator="Turkcell").json()
        self.assertEqual(o["data"][0]["id"], self.pkg.id)
        self.assertNotIn("znet_id", o["data"][0])
