"""اختبارات القلب."""
from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APITestCase

from catalog.models import Game, Product
from orders.models import Order
from providers.models import Provider

from .models import Tenant, User, Wallet

class LoginTest(TestCase):
    """حارس ضد تكرار عطل: حذف `_tokens_for` كسر تسجيل الدخول بخطأ 500."""

    def test_login_returns_tokens(self):
        tenant = Tenant.objects.create(subdomain="t1", name="متجر اختبار")
        user = User.objects.create(login_id="user001", name="مستخدم", tenant=tenant)
        user.set_password("pass123")
        user.save()
        Wallet.objects.create(tenant=tenant, user=user)

        r = self.client.post(
            "/api/auth/login/",
            {"login_id": "user001", "password": "pass123"},
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 200, r.content[:500])
        self.assertIn("access", r.json()["tokens"])
        self.assertIn("refresh", r.json()["tokens"])


class HeaderAlertsTest(APITestCase):
    """
    شريط «ما ينتظر قرارك»: كل عدّاد يقيس ما **يحتاج تدخّلاً** لا ما هو موجود.
    الطلب الناجح والوكيل الموجب والمزوّد السليم لا تُعَدّ.
    """

    def setUp(self):
        self.tenant = Tenant.objects.create(subdomain="t", name="متجر")
        self.admin = User.objects.create(
            login_id="admin", name="مدير", tenant=self.tenant, role=User.Role.TENANT_ADMIN,
        )
        self.client.force_authenticate(user=self.admin)
        self.game = Game.objects.create(tenant=self.tenant, name="PUBG")
        self.product = Product.objects.create(tenant=self.tenant, game=self.game, name="60 UC")

    def test_quiet_store_reports_all_zero(self):
        r = self.client.get("/api/alerts/")
        self.assertEqual(r.status_code, 200, r.content)
        for key, value in r.json().items():
            self.assertEqual(value, 0, f"{key} يجب أن يكون صفراً في متجر هادئ")

    def test_counts_only_what_needs_a_decision(self):
        dealer = self._dealer("bayi1", Decimal("-50"))   # سالب ⇒ يُعَدّ
        self._dealer("bayi2", Decimal("100"))            # موجب ⇒ لا يُعَدّ
        self._order(dealer, Order.Status.PENDING)
        self._order(dealer, Order.Status.STUCK)
        self._order(dealer, Order.Status.SUCCESS)        # محسوم ⇒ لا يُعَدّ
        Provider.objects.create(
            tenant=self.tenant, name="معطّل", status=Provider.Status.PASSIVE)
        Provider.objects.create(
            tenant=self.tenant, name="سليم", status=Provider.Status.ACTIVE)

        d = self.client.get("/api/alerts/").json()

        self.assertEqual(d["dealers_negative"], 1)
        self.assertEqual(d["orders_pending"], 1)
        self.assertEqual(d["orders_stuck"], 1)
        self.assertEqual(d["providers"], 1)

    def test_provider_below_its_own_threshold_is_counted(self):
        """الحدّ يضبطه المالك لكل مزوّد — والمقارنة به هو لا برقم عامّ."""
        Provider.objects.create(
            tenant=self.tenant, name="منخفض", status=Provider.Status.ACTIVE,
            real_balance=Decimal("40"), balance_alert_threshold=Decimal("100"),
        )
        Provider.objects.create(
            tenant=self.tenant, name="كافٍ", status=Provider.Status.ACTIVE,
            real_balance=Decimal("400"), balance_alert_threshold=Decimal("100"),
        )
        Provider.objects.create(  # بلا حدّ مضبوط ⇒ لا إنذار مهما قلّ رصيده
            tenant=self.tenant, name="بلا حدّ", status=Provider.Status.ACTIVE,
            real_balance=Decimal("0"),
        )

        self.assertEqual(self.client.get("/api/alerts/").json()["providers"], 1)

    def _dealer(self, login_id, balance):
        u = User.objects.create(
            login_id=login_id, name=login_id, tenant=self.tenant, role=User.Role.BAYI,
        )
        Wallet.objects.create(tenant=self.tenant, user=u, balance=balance)
        return u

    def _order(self, dealer, status):
        return Order.objects.create(
            tenant=self.tenant, receipt_no=f"R{Order.objects.count() + 1}",
            dealer=dealer, game=self.game, product=self.product, status=status,
            cost_price=Decimal("1"), sell_price=Decimal("2"), profit=Decimal("1"),
        )


class DealerListTest(APITestCase):
    """
    قائمة الوكلاء بعد إعادة تشكيلها: رقم تسلسلي، وتعطيل بنقرة، وإعدادات
    انتقلت إليها من صفحة «أسعار الوكلاء» المحذوفة.
    """

    def setUp(self):
        from catalog.models import PriceGroup

        self.tenant = Tenant.objects.create(subdomain="t9", name="متجر", base_currency="USD")
        self.admin = User.objects.create(
            login_id="admin9", name="صاحب المتجر", tenant=self.tenant,
            role=User.Role.TENANT_ADMIN,
        )
        self.client.force_authenticate(user=self.admin)
        self.group = PriceGroup.objects.create(tenant=self.tenant, name="1")

        self.big = User.objects.create(
            login_id="big9", name="وكيل كبير", tenant=self.tenant,
            role=User.Role.ANA_BAYI, dealer_no=1,
        )
        Wallet.objects.create(tenant=self.tenant, user=self.big, balance=Decimal("100"))
        self.dealer = User.objects.create(
            login_id="bayi9", name="دكان", tenant=self.tenant,
            role=User.Role.BAYI, parent=self.big, dealer_no=2,
        )
        Wallet.objects.create(tenant=self.tenant, user=self.dealer, balance=Decimal("-25"))

    def _list(self):
        r = self.client.get("/api/dealers/")
        self.assertEqual(r.status_code, 200, r.content)
        return r.json()["results"]

    def test_list_carries_the_sequential_number(self):
        self.assertEqual([d["dealer_no"] for d in self._list()], [1])

    def test_new_dealer_gets_the_next_number(self):
        r = self.client.post(
            "/api/dealers/",
            {"login_id": "bayi10", "name": "دكان ثانٍ", "password": "pass123"},
            format="json",
        )
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(User.objects.get(login_id="bayi10").dealer_no, 3)

    def test_toggling_status_disables_and_re_enables(self):
        url = f"/api/dealers/{self.big.id}/settings/"
        self.assertEqual(self.client.post(url, {"status": "passive"}, format="json").status_code, 200)
        self.big.refresh_from_db()
        self.assertEqual(self.big.status, User.Status.PASSIVE)
        self.assertFalse(self._list()[0]["active"])   # يبقى في الردّ، والواجهة تُخفيه

        self.client.post(url, {"status": "active"}, format="json")
        self.big.refresh_from_db()
        self.assertEqual(self.big.status, User.Status.ACTIVE)

    def test_settings_carry_and_save_group_and_load_limit(self):
        url = f"/api/dealers/{self.dealer.id}/settings/"
        row = self.client.get(url).json()
        self.assertEqual(row["price_group"], None)
        self.assertEqual([g["id"] for g in row["price_groups"]], [self.group.id])

        r = self.client.post(
            url, {"price_group": self.group.id, "oyun_load_limit": "25000"}, format="json",
        )
        self.assertEqual(r.status_code, 200, r.content)
        self.dealer.refresh_from_db()
        self.assertEqual(self.dealer.price_group_id, self.group.id)
        self.assertEqual(self.dealer.oyun_load_limit, Decimal("25000"))

    def test_unknown_price_group_is_refused(self):
        r = self.client.post(
            f"/api/dealers/{self.dealer.id}/settings/", {"price_group": 9999}, format="json",
        )
        self.assertEqual(r.status_code, 404)

    def test_sub_dealer_is_nested_under_its_big_agent(self):
        """الدكان التابع لا يقف صفّاً مستقلاً — مكانه داخل صفّ وكيله."""
        rows = self._list()
        self.assertEqual([r["name"] for r in rows], ["وكيل كبير"])
        big = rows[0]
        self.assertTrue(big["is_big"])
        self.assertEqual(big["children_count"], 1)
        self.assertEqual([c["name"] for c in big["children"]], ["دكان"])

    def test_independent_dealer_stands_on_its_own_row(self):
        solo = User.objects.create(
            login_id="solo9", name="دكان مستقلّ", tenant=self.tenant,
            role=User.Role.BAYI, dealer_no=3,
        )
        Wallet.objects.create(tenant=self.tenant, user=solo)
        names = [r["name"] for r in self._list()]
        self.assertIn("دكان مستقلّ", names)
        self.assertNotIn("دكان", names)   # التابع يبقى مطويّاً تحت وكيله

    def test_promoting_a_dealer_to_big_agent(self):
        solo = User.objects.create(
            login_id="solo10", name="مرشّح", tenant=self.tenant,
            role=User.Role.BAYI, parent=self.big, dealer_no=4,
        )
        r = self.client.post(
            f"/api/dealers/{solo.id}/settings/", {"role": "ana_bayi"}, format="json",
        )
        self.assertEqual(r.status_code, 200, r.content)
        solo.refresh_from_db()
        self.assertEqual(solo.role, User.Role.ANA_BAYI)
        self.assertIsNone(solo.parent_id)   # الكبير لا يتبع أحداً

    def test_big_agent_with_shops_cannot_be_demoted(self):
        r = self.client.post(
            f"/api/dealers/{self.big.id}/settings/", {"role": "bayi"}, format="json",
        )
        self.assertEqual(r.status_code, 400)
        self.big.refresh_from_db()
        self.assertEqual(self.big.role, User.Role.ANA_BAYI)

    def test_attaching_a_dealer_to_a_big_agent(self):
        solo = User.objects.create(
            login_id="solo11", name="دكان حرّ", tenant=self.tenant,
            role=User.Role.BAYI, dealer_no=5,
        )
        r = self.client.post(
            f"/api/dealers/{solo.id}/settings/", {"parent": self.big.id}, format="json",
        )
        self.assertEqual(r.status_code, 200, r.content)
        solo.refresh_from_db()
        self.assertEqual(solo.parent_id, self.big.id)
        self.assertNotIn("دكان حرّ", [x["name"] for x in self._list()])

    def test_a_big_agent_cannot_follow_another(self):
        other = User.objects.create(
            login_id="big10", name="كبير آخر", tenant=self.tenant,
            role=User.Role.ANA_BAYI, dealer_no=6,
        )
        r = self.client.post(
            f"/api/dealers/{other.id}/settings/", {"parent": self.big.id}, format="json",
        )
        self.assertEqual(r.status_code, 400)

    def test_creating_a_big_agent_with_a_follower(self):
        r = self.client.post(
            "/api/dealers/",
            {"login_id": "ahmad9", "name": "أحمد العلي", "password": "pass123",
             "role": "ana_bayi"},
            format="json",
        )
        self.assertEqual(r.status_code, 201, r.content)
        ahmad_id = r.json()["id"]
        r2 = self.client.post(
            "/api/dealers/",
            {"login_id": "shop9", "name": "محل النور", "password": "pass123",
             "parent": ahmad_id},
            format="json",
        )
        self.assertEqual(r2.status_code, 201, r2.content)
        row = next(x for x in self._list() if x["id"] == ahmad_id)
        self.assertEqual([c["name"] for c in row["children"]], ["محل النور"])

    def test_removed_dealer_prices_endpoints_are_gone(self):
        self.assertEqual(self.client.get("/api/catalog/dealer-prices/").status_code, 404)


class DealerPasswordTest(APITestCase):
    """تغيير كلمة سرّ وكيل من نافذة الإعدادات — ثم دخوله بها فعلاً."""

    def setUp(self):
        self.tenant = Tenant.objects.create(subdomain="tpw", name="متجر", base_currency="USD")
        self.admin = User.objects.create(
            login_id="adminpw", name="مدير", tenant=self.tenant, role=User.Role.TENANT_ADMIN,
        )
        self.agent = User.objects.create(
            login_id="5553333333", name="أحمد العلي", tenant=self.tenant,
            role=User.Role.ANA_BAYI, dealer_no=1,
        )
        self.agent.set_password("old12345")
        self.agent.save()
        Wallet.objects.create(tenant=self.tenant, user=self.agent, balance=Decimal("3000"))
        self.client.force_authenticate(user=self.admin)

    def _login(self, login_id, password):
        self.client.force_authenticate(user=None)
        r = self.client.post(
            "/api/auth/login/", {"login_id": login_id, "password": password}, format="json",
        )
        self.client.force_authenticate(user=self.admin)
        return r

    def test_changed_password_works_and_is_acknowledged(self):
        r = self.client.post(
            f"/api/dealers/{self.agent.id}/settings/",
            {"new_password": "Asdf1212asdf"}, format="json",
        )
        self.assertEqual(r.status_code, 200, r.content)
        self.assertTrue(r.json()["password_changed"])          # إقرار صريح
        self.assertEqual(self._login("5553333333", "Asdf1212asdf").status_code, 200)
        self.assertEqual(self._login("5553333333", "old12345").status_code, 401)

    def test_saving_without_a_password_says_so(self):
        r = self.client.post(
            f"/api/dealers/{self.agent.id}/settings/", {"status": "active"}, format="json",
        )
        self.assertFalse(r.json()["password_changed"])
        self.assertEqual(self._login("5553333333", "old12345").status_code, 200)

    def test_login_id_with_stray_spaces_still_works(self):
        """مسافة من نسخٍ ولصق كانت تُفشل الدخول برسالة «بيانات غير صحيحة»."""
        self.assertEqual(self._login("  5553333333 ", "old12345").status_code, 200)

    def test_login_id_with_invisible_isolate_marks_still_works(self):
        """
        نسخُ رقمٍ من عرضٍ عربي يجرّ معه محرفَي العزل U+2066 و U+2069 حول الرقم.
        لا يُريان على الشاشة، و`strip()` لا تمسكهما — فيُرفض الدخول أبداً
        برسالة «بيانات غير صحيحة» ولا شيء يفسّرها.
        """
        wrapped = chr(0x2066) + "5553333333" + chr(0x2069)   # LRI … PDI
        self.assertEqual(self._login(wrapped, "old12345").status_code, 200)

    def test_short_password_is_refused(self):
        r = self.client.post(
            f"/api/dealers/{self.agent.id}/settings/", {"new_password": "abc"}, format="json",
        )
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self._login("5553333333", "old12345").status_code, 200)


class LoginLockTest(APITestCase):
    """
    ثلاث محاولات ثم قفل. المخرج الوحيد كلمةُ سرٍّ جديدة من فوقك — لأن القديمة
    ثبت أن أحدهم يخمّنها، ففتحُ القفل عليها إعادةٌ للباب المفتوح.
    """

    def setUp(self):
        self.tenant = Tenant.objects.create(subdomain="t1", name="متجر")
        self.admin = User.objects.create(
            login_id="admin1", name="مدير", tenant=self.tenant,
            role=User.Role.TENANT_ADMIN, is_staff=True,
        )
        self.admin.set_password("adminpass")
        self.admin.save()
        self.dealer = User.objects.create(
            login_id="d1", name="وكيل", tenant=self.tenant, role=User.Role.BAYI, dealer_no=1,
        )
        self.dealer.set_password("right12345")
        self.dealer.save()
        Wallet.objects.create(tenant=self.tenant, user=self.dealer)

    def _login(self, pw, who="d1"):
        return self.client.post("/api/auth/login/", {"login_id": who, "password": pw}, format="json")

    def test_third_failure_locks_the_account(self):
        self.assertEqual(self._login("wrong1").status_code, 401)
        self.assertEqual(self._login("wrong2").status_code, 401)
        third = self._login("wrong3")
        self.assertEqual(third.status_code, 403)
        self.assertIn("قُفل الحساب", third.json()["detail"])
        self.dealer.refresh_from_db()
        self.assertTrue(self.dealer.is_locked)

    def test_the_right_password_no_longer_works_once_locked(self):
        """جوهر الأمر: القفل يسبق فحص كلمة السرّ، فلا يُختبَر التخمين أصلاً."""
        for i in range(3):
            self._login(f"wrong{i}")
        r = self._login("right12345")
        self.assertEqual(r.status_code, 403)

    def test_countdown_warns_before_the_lock(self):
        self.assertIn("تبقّت 2", self._login("x").json()["detail"])
        self.assertIn("تبقّت 1", self._login("x").json()["detail"])

    def test_a_success_resets_the_counter(self):
        self._login("wrong1")
        self._login("wrong2")
        self.assertEqual(self._login("right12345").status_code, 200)
        self.dealer.refresh_from_db()
        self.assertEqual(self.dealer.failed_login_count, 0)
        # وبعدها تبدأ العدّة من جديد لا من اثنين
        self.assertEqual(self._login("wrong1").status_code, 401)
        self.assertEqual(self._login("wrong2").status_code, 401)
        self.assertEqual(self._login("right12345").status_code, 200)

    def test_owner_unlocks_by_setting_a_new_password(self):
        for i in range(3):
            self._login(f"wrong{i}")
        self.client.force_authenticate(self.admin)
        r = self.client.post(
            f"/api/dealers/{self.dealer.id}/settings/",
            {"new_password": "fresh12345"}, format="json",
        )
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.json()["is_locked"])
        self.client.force_authenticate(None)
        self.assertEqual(self._login("fresh12345").status_code, 200)

    def test_saving_settings_without_a_password_keeps_it_locked(self):
        """القفل لا يُفتح بالمرور على النافذة — كلمة سرّ جديدة أو لا شيء."""
        for i in range(3):
            self._login(f"wrong{i}")
        self.client.force_authenticate(self.admin)
        self.client.post(
            f"/api/dealers/{self.dealer.id}/settings/", {"status": "active"}, format="json",
        )
        self.dealer.refresh_from_db()
        self.assertTrue(self.dealer.is_locked)

    def test_command_unlocks_the_platform_owner(self):
        """لا أحد فوق مالك المنصّة — فمخرجه سطر الأوامر."""
        from django.core.management import call_command
        from io import StringIO

        owner = User.objects.create(login_id="9990000000", name="مالك", role=User.Role.PLATFORM_OWNER)
        owner.set_password("old12345")
        owner.save()
        for i in range(3):
            self._login(f"wrong{i}", who="9990000000")
        owner.refresh_from_db()
        self.assertTrue(owner.is_locked)

        call_command("unlock_user", "9990000000", "--password", "new12345", stdout=StringIO())
        self.assertEqual(self._login("new12345", who="9990000000").status_code, 200)


class SubscriptionGateTest(APITestCase):
    """مهلة سماح ثم منع الشراء وحده — القراءة والمحافظ تبقى."""

    def setUp(self):
        self.tenant = Tenant.objects.create(subdomain="t1", name="متجر", base_currency="USD")
        self.game = Game.objects.create(tenant=self.tenant, name="PUBG")
        self.product = Product.objects.create(
            tenant=self.tenant, game=self.game, name="60 UC",
            cost_price=Decimal("6"), recommended_price=Decimal("10"),
        )
        self.dealer = User.objects.create(
            login_id="d1", name="وكيل", tenant=self.tenant, role=User.Role.BAYI, dealer_no=1,
        )
        Wallet.objects.create(tenant=self.tenant, user=self.dealer, balance=Decimal("100"))

    def _set(self, days_ago, grace=3, enforce=True):
        self.tenant.sub_expires_at = timezone.localdate() - timedelta(days=days_ago)
        self.tenant.sub_grace_days = grace
        self.tenant.sub_enforce = enforce
        self.tenant.save()
        self.dealer.refresh_from_db()

    def _buy(self):
        from orders import services
        return services.create_order(self.dealer, self.product)

    def test_active_subscription_buys_fine(self):
        self._set(-30)
        self.assertEqual(self.tenant.subscription_state(), "ok")
        self.assertIsNotNone(self._buy())

    def test_warns_when_it_nears_the_end(self):
        self._set(-3)
        self.assertEqual(self.tenant.subscription_state(), "warn")
        self.assertIsNotNone(self._buy())   # تنبيهٌ لا منع

    def test_grace_period_still_buys(self):
        self._set(2, grace=3)
        self.assertEqual(self.tenant.subscription_state(), "grace")
        self.assertIsNotNone(self._buy())

    def test_after_grace_the_purchase_is_refused_and_nothing_is_charged(self):
        from orders import services

        self._set(5, grace=3)
        self.assertEqual(self.tenant.subscription_state(), "blocked")
        with self.assertRaises(services.OrderError) as cm:
            self._buy()
        self.assertIn("انتهى اشتراك المتجر", str(cm.exception))
        self.assertEqual(Order.objects.count(), 0)
        self.assertEqual(Wallet.objects.get(user=self.dealer).balance, Decimal("100"))

    def test_exempt_tenant_is_never_blocked(self):
        self._set(500, grace=0, enforce=False)
        self.assertEqual(self.tenant.subscription_state(), "ok")
        self.assertIsNotNone(self._buy())

    def test_a_tenant_that_never_subscribed_is_not_punished(self):
        """متجرٌ جديد يُجرَّب، لا متجرٌ متخلّف عن الدفع."""
        self.tenant.sub_expires_at = None
        self.tenant.save()
        self.assertEqual(self.tenant.subscription_state(), "ok")
        self.assertIsNotNone(self._buy())

    def test_zero_grace_blocks_the_day_after(self):
        self._set(1, grace=0)
        self.assertEqual(self.tenant.subscription_state(), "blocked")


class HomeCardsTest(APITestCase):
    """لا يكتب أحدٌ إلا لمن تحته، ولا يقرأ أحدٌ إلا ما كُتب له."""

    def setUp(self):
        self.t1 = Tenant.objects.create(subdomain="t1", name="متجر ١")
        self.t2 = Tenant.objects.create(subdomain="t2", name="متجر ٢")
        self.owner = User.objects.create(login_id="p1", name="مالك", role=User.Role.PLATFORM_OWNER)
        self.admin1 = User.objects.create(
            login_id="a1", name="صاحب ١", tenant=self.t1, role=User.Role.TENANT_ADMIN)
        self.admin2 = User.objects.create(
            login_id="a2", name="صاحب ٢", tenant=self.t2, role=User.Role.TENANT_ADMIN)
        self.dealer1 = User.objects.create(
            login_id="d1", name="وكيل ١", tenant=self.t1, role=User.Role.BAYI, dealer_no=1)
        self.dealer2 = User.objects.create(
            login_id="d2", name="وكيل ٢", tenant=self.t2, role=User.Role.BAYI, dealer_no=1)

    def _post(self, user, body):
        self.client.force_authenticate(user)
        return self.client.post("/api/cards/", body, format="json")

    def _mine(self, user):
        self.client.force_authenticate(user)
        return self.client.get("/api/my-cards/").json()["results"]

    def test_platform_card_reaches_every_store_owner(self):
        self._post(self.owner, {"title": "صيانة الجمعة"})
        self.assertEqual([c["title"] for c in self._mine(self.admin1)], ["صيانة الجمعة"])
        self.assertEqual([c["title"] for c in self._mine(self.admin2)], ["صيانة الجمعة"])

    def test_platform_card_can_target_one_store(self):
        self._post(self.owner, {"title": "لك وحدك", "target_tenant": self.t1.id})
        self.assertEqual(len(self._mine(self.admin1)), 1)
        self.assertEqual(self._mine(self.admin2), [])

    def test_store_card_reaches_only_its_own_dealers(self):
        self._post(self.admin1, {"title": "أسعار جديدة"})
        self.assertEqual([c["title"] for c in self._mine(self.dealer1)], ["أسعار جديدة"])
        self.assertEqual(self._mine(self.dealer2), [])

    def test_platform_cards_do_not_leak_to_dealers(self):
        self._post(self.owner, {"title": "للمتاجر"})
        self.assertEqual(self._mine(self.dealer1), [])

    def test_a_dealer_cannot_write_cards(self):
        self.assertEqual(self._post(self.dealer1, {"title": "أنا"}).status_code, 403)

    def test_a_store_cannot_touch_another_stores_card(self):
        card_id = self._post(self.admin1, {"title": "لي"}).json()["id"]
        self.client.force_authenticate(self.admin2)
        self.assertEqual(self.client.patch(f"/api/cards/{card_id}/", {"title": "لي أنا"},
                                           format="json").status_code, 404)
        self.assertEqual(self.client.delete(f"/api/cards/{card_id}/").status_code, 404)

    def test_hidden_cards_are_not_delivered(self):
        card_id = self._post(self.admin1, {"title": "مخفيّة"}).json()["id"]
        self.client.patch(f"/api/cards/{card_id}/", {"active": False}, format="json")
        self.assertEqual(self._mine(self.dealer1), [])

    def test_title_is_required(self):
        self.assertEqual(self._post(self.admin1, {"body": "بلا عنوان"}).status_code, 400)

    def test_empty_colors_fall_back_instead_of_breaking_the_card(self):
        r = self._post(self.admin1, {"title": "بلا لون", "bg_color": "", "text_color": ""})
        self.assertTrue(r.json()["bg_color"])
        self.assertTrue(r.json()["text_color"])


class StorePackagesTest(APITestCase):
    """قائمة أسعار الوكيل — بسعره هو، وبلا أرقام مزوّدي المتجر."""

    def setUp(self):
        from catalog.models import PriceGroup, ProductPrice

        self.tenant = Tenant.objects.create(subdomain="t1", name="متجر", base_currency="USD")
        self.group = PriceGroup.objects.create(tenant=self.tenant, name="عادية")
        self.game = Game.objects.create(tenant=self.tenant, name="PUBG", require_player_id=True)
        self.product = Product.objects.create(
            tenant=self.tenant, game=self.game, name="60 UC",
            cost_price=Decimal("6"), recommended_price=Decimal("12"),
            provider_package_id="SECRET-9",
        )
        ProductPrice.objects.create(tenant=self.tenant, product=self.product,
                                    price_group=self.group, price=Decimal("8"))
        self.dealer = User.objects.create(
            login_id="d1", name="وكيل", tenant=self.tenant,
            role=User.Role.BAYI, price_group=self.group, dealer_no=1,
        )
        Wallet.objects.create(tenant=self.tenant, user=self.dealer)

    def test_rows_carry_our_product_id_and_his_own_price(self):
        self.client.force_authenticate(self.dealer)
        row = self.client.get("/api/store/packages/").json()["results"][0]
        self.assertEqual(row["id"], self.product.id)        # الرقم الذي يضعه في الـ API
        self.assertEqual(row["buy_price"], "8.00")          # سعر مجموعته لا سعر التوصية
        self.assertEqual(row["recommended_price"], "12.00")
        self.assertTrue(row["require_player_id"])

    def test_the_suppliers_package_id_is_never_exposed(self):
        """رقم الباقة لدى مزوّد المتجر سرٌّ تجاري — كشفُه يدلّ الوكلاء على مصادره."""
        self.client.force_authenticate(self.dealer)
        self.assertNotIn("SECRET-9", self.client.get("/api/store/packages/").content.decode())

    def test_other_tenants_are_not_listed(self):
        other = Tenant.objects.create(subdomain="t2", name="آخر")
        g = Game.objects.create(tenant=other, name="لعبة")
        Product.objects.create(tenant=other, game=g, name="سرّي",
                               cost_price=Decimal("1"), recommended_price=Decimal("2"))
        self.client.force_authenticate(self.dealer)
        names = [r["name"] for r in self.client.get("/api/store/packages/").json()["results"]]
        self.assertNotIn("سرّي", names)

    def test_passive_products_are_hidden(self):
        self.product.status = Product.Status.PASSIVE
        self.product.save(update_fields=["status"])
        self.client.force_authenticate(self.dealer)
        self.assertEqual(self.client.get("/api/store/packages/").json()["results"], [])


class StoreHostTest(APITestCase):
    """
    النطاقات الفرعية: `islam.wtn4.com` باب إسلام، و`wtn4.com` باب الجميع.

    ثلاثة أشياء تُحرَس هنا، وكلّها ثغراتٌ لو انفتحت:
    عنوانٌ لا متجر له لا يعطي صفحة دخولٍ كاذبة · متجرٌ موقوفٌ بابُه مغلق ·
    وحسابُ متجرٍ لا يعمل على عنوان متجرٍ آخر لا عند الدخول ولا بتوكنٍ قديم.
    """

    def setUp(self):
        self.islam = Tenant.objects.create(
            subdomain="islam", name="متجر إسلام", status=Tenant.Status.ACTIVE,
        )
        self.alaya = Tenant.objects.create(
            subdomain="alaya", name="علايا", status=Tenant.Status.ACTIVE,
        )
        self.islam_dealer = User.objects.create(
            login_id="i-bayi", name="وكيل إسلام", tenant=self.islam, role=User.Role.BAYI,
        )
        self.islam_dealer.set_password("pass123")
        self.islam_dealer.save()
        self.alaya_dealer = User.objects.create(
            login_id="a-bayi", name="وكيل علايا", tenant=self.alaya, role=User.Role.BAYI,
        )
        self.alaya_dealer.set_password("pass123")
        self.alaya_dealer.save()

    def _login(self, login_id, host):
        return self.client.post(
            "/api/auth/login/",
            {"login_id": login_id, "password": "pass123"},
            format="json", HTTP_HOST=host,
        )

    # ————— استنتاج المتجر من العنوان —————

    def test_platform_domain_and_reserved_names_are_not_stores(self):
        for host in ("wtn4.com", "www.wtn4.com", "api.wtn4.com"):
            r = self.client.get("/api/storefront/", HTTP_HOST=host)
            self.assertEqual(r.status_code, 200, host)
            self.assertIsNone(r.json()["store"], host)

    def test_store_subdomain_returns_its_identity(self):
        store = self.client.get("/api/storefront/", HTTP_HOST="islam.wtn4.com").json()["store"]
        self.assertEqual(store["name"], "متجر إسلام")
        self.assertEqual(store["subdomain"], "islam")

    def test_localhost_stays_the_general_door(self):
        """بدون هذا ينقطع التطوير المحلّي ونبضةُ البوت التي تنادي `http://web:8000`."""
        for host in ("localhost", "127.0.0.1", "web", "46.224.47.213"):
            r = self.client.get("/api/storefront/", HTTP_HOST=host)
            self.assertEqual(r.status_code, 200, host)
            self.assertIsNone(r.json()["store"], host)

    def test_unknown_subdomain_says_so_instead_of_a_login_page(self):
        """صفحةُ دخولٍ هنا كذبة: يجرّب الزائر كلمته حتى يُقفل حسابه بلا ذنب."""
        r = self.client.get("/", HTTP_HOST="nobody.wtn4.com")
        self.assertEqual(r.status_code, 404)
        self.assertIn("لا متجر بهذا العنوان", r.content.decode())

    def test_unknown_subdomain_answers_json_on_api_paths(self):
        r = self.client.get("/api/storefront/", HTTP_HOST="nobody.wtn4.com")
        self.assertEqual(r.status_code, 404)
        self.assertEqual(r.json()["code"], "store_not_found")

    # ————— المتجر الموقوف: باب مغلق (قرار المالك) —————

    def test_suspended_store_closes_its_door_to_everyone(self):
        self.islam.status = Tenant.Status.SUSPENDED
        self.islam.save(update_fields=["status"])
        r = self.client.get("/", HTTP_HOST="islam.wtn4.com")
        self.assertEqual(r.status_code, 403)
        self.assertIn("متوقّف مؤقّتاً", r.content.decode())

    def test_suspended_store_is_still_reachable_from_the_general_door(self):
        """الإيقاف يغلق عنوان المتجر، ولا يُسقط المنصّة عن أحد."""
        self.islam.status = Tenant.Status.SUSPENDED
        self.islam.save(update_fields=["status"])
        self.assertEqual(self.client.get("/api/storefront/", HTTP_HOST="wtn4.com").status_code, 200)

    # ————— منع الخلط —————

    def test_dealer_enters_from_his_own_store_address(self):
        self.assertEqual(self._login("i-bayi", "islam.wtn4.com").status_code, 200)

    def test_dealer_of_another_store_is_refused(self):
        r = self._login("a-bayi", "islam.wtn4.com")
        self.assertEqual(r.status_code, 403)
        self.assertIn("ليس من متجر", r.json()["detail"])

    def test_the_general_door_stays_open_to_all(self):
        """قرار المالك: `wtn4.com` يبقى بابَ الجميع، فلا ينقطع من حفظ الرابط."""
        for login_id in ("i-bayi", "a-bayi"):
            self.assertEqual(self._login(login_id, "wtn4.com").status_code, 200, login_id)

    def test_a_token_issued_at_the_general_door_does_not_open_another_store(self):
        """للتوكن حياتان: إصدارٌ واستعمال. حراسةُ الإصدار وحدها تترك ثماني ساعات."""
        token = self._login("a-bayi", "wtn4.com").json()["tokens"]["access"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        self.assertEqual(self.client.get("/api/auth/me/", HTTP_HOST="alaya.wtn4.com").status_code, 200)
        # 401 لا 403 عمداً: هي رسالةُ «اعتمادُك لا يصلح هنا»، والواجهة تقرؤها
        # «سجّل دخولك على هذا العنوان» — وهو بالضبط ما نريده منه.
        r = self.client.get("/api/auth/me/", HTTP_HOST="islam.wtn4.com")
        self.assertEqual(r.status_code, 401)
        self.assertIn("ليس من هذا المتجر", r.json()["detail"])


class UiScaleTest(APITestCase):
    """
    حجم العرض حقلٌ تجميلي، لكن حدَّه ليس تجميلياً: قيمةٌ متطرّفة تُقزّم اللوحة
    أو تُخرجها عن الشاشة، فيتعذّر على صاحبها بلوغُ هذه الصفحة نفسها ليصلحها.
    """

    def setUp(self):
        self.tenant = Tenant.objects.create(subdomain="sc", name="متجر")
        self.admin = User.objects.create(
            login_id="sc-admin", name="مدير", tenant=self.tenant,
            role=User.Role.TENANT_ADMIN, status=User.Status.ACTIVE,
        )
        self.client.force_authenticate(self.admin)

    def test_default_is_a_hundred(self):
        self.assertEqual(self.client.get("/api/settings/site/").json()["ui_scale"], 100)

    def test_a_value_in_range_is_saved(self):
        r = self.client.put("/api/settings/site/", {"ui_scale": 85}, format="json")
        self.assertEqual(r.status_code, 200)
        self.tenant.refresh_from_db()
        self.assertEqual(self.tenant.ui_scale, 85)

    def test_a_value_out_of_range_is_refused(self):
        for bad in (10, 300, 0):
            r = self.client.put("/api/settings/site/", {"ui_scale": bad}, format="json")
            self.assertEqual(r.status_code, 400, bad)
        self.tenant.refresh_from_db()
        self.assertEqual(self.tenant.ui_scale, 100)

    def test_the_login_page_knows_the_size_before_any_account(self):
        """وإلّا ظهرت الصفحة بمقاسٍ ثم قفزت إلى آخر بعد الدخول."""
        self.tenant.ui_scale = 90
        self.tenant.save(update_fields=["ui_scale"])
        self.client.force_authenticate(None)
        r = self.client.get("/api/storefront/", HTTP_HOST="sc.wtn4.com")
        self.assertEqual(r.json()["store"]["ui_scale"], 90)


class AgentThemeTest(APITestCase):
    """
    ألوان واجهة الوكلاء تُكتب في وسم <style> على صفحة كل وكيل — فلا يُقبل
    إلا لونٌ سداسي، ولا يكتبها إلا صاحب المتجر.
    """

    def setUp(self):
        self.tenant = Tenant.objects.create(subdomain="th", name="متجر")
        self.admin = User.objects.create(
            login_id="th-admin", name="مدير", tenant=self.tenant,
            role=User.Role.TENANT_ADMIN, status=User.Status.ACTIVE,
        )
        self.agent = User.objects.create(
            login_id="th-agent", name="وكيل", tenant=self.tenant,
            role=User.Role.BAYI, status=User.Status.ACTIVE,
        )

    def test_owner_saves_and_agent_reads(self):
        self.client.force_authenticate(self.admin)
        r = self.client.put("/api/settings/agent-theme/",
                            {"theme": {"primary": "#FF0000", "bg": "#000000"}}, format="json")
        self.assertEqual(r.status_code, 200)
        self.client.force_authenticate(self.agent)
        self.assertEqual(self.client.get("/api/settings/agent-theme/").json()["theme"],
                         {"primary": "#ff0000", "bg": "#000000"})

    def test_agent_cannot_write(self):
        self.client.force_authenticate(self.agent)
        r = self.client.put("/api/settings/agent-theme/", {"theme": {"primary": "#ff0000"}}, format="json")
        self.assertEqual(r.status_code, 403)
        self.tenant.refresh_from_db()
        self.assertEqual(self.tenant.agent_theme, {})

    def test_only_hex_colors_are_accepted(self):
        self.client.force_authenticate(self.admin)
        for bad in ({"primary": "red;}body{display:none"}, {"primary": "#fff"},
                    {"Bad-Key": "#ffffff"}, {"primary": 5}, "x"):
            r = self.client.put("/api/settings/agent-theme/", {"theme": bad}, format="json")
            self.assertEqual(r.status_code, 400, bad)
        self.tenant.refresh_from_db()
        self.assertEqual(self.tenant.agent_theme, {})

    def test_empty_theme_resets(self):
        self.tenant.agent_theme = {"primary": "#ff0000"}
        self.tenant.save(update_fields=["agent_theme"])
        self.client.force_authenticate(self.admin)
        self.client.put("/api/settings/agent-theme/", {"theme": {}}, format="json")
        self.tenant.refresh_from_db()
        self.assertEqual(self.tenant.agent_theme, {})



class DealerRowCurrencyTest(APITestCase):
    """متجرٌ دفتره بالدولار: رصيد الوكيل بالدولار، ومجموعته مجموعة أسعاره."""

    def test_usd_store_shows_usd_and_the_price_group(self):
        from catalog.models import PriceGroup
        t = Tenant.objects.create(subdomain="usd", name="متجر", base_currency="USD")
        admin = User.objects.create(login_id="usd-a", name="م", tenant=t, role=User.Role.TENANT_ADMIN,
                                    status=User.Status.ACTIVE)
        g = PriceGroup.objects.create(tenant=t, name="vip1")
        d = User.objects.create(login_id="usd-d", name="وكيل", tenant=t, role=User.Role.BAYI,
                                status=User.Status.ACTIVE, price_group=g, dealer_no=1)
        w = Wallet.objects.create(tenant=t, user=d, balance=Decimal("-1"))
        self.assertEqual(w.currency, "USD")
        self.client.force_authenticate(admin)
        rows = self.client.get("/api/dealers/").json()
        rows = rows.get("results", rows) if isinstance(rows, dict) else rows
        row = next(r for r in rows if r["id"] == d.id)
        self.assertEqual(row["currency"], "USD")
        self.assertEqual(row["group"], "vip1")



class DealerOwnCurrencyTest(APITestCase):
    """
    دفترٌ بالدولار ووكيلٌ بالليرة (49 ل.ت/$): كل ما يكتبه صاحب المتجر لهذا الوكيل
    بالليرة — الحد الائتماني والشحن — ويُحفظ دولاراً؛ والجدول يعرضه بالليرة.
    """

    def setUp(self):
        self.t = Tenant.objects.create(subdomain="oc", name="متجر", base_currency="USD",
                                       exchange_rates={"TRY": "49"})
        self.admin = User.objects.create(login_id="oc-a", name="م", tenant=self.t,
                                         role=User.Role.TENANT_ADMIN, status=User.Status.ACTIVE)
        self.client.force_authenticate(self.admin)

    def _create(self, **extra):
        r = self.client.post("/api/dealers/", {"login_id": "5550001", "name": "محمد", "password": "pw12345",
                                              **extra}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        return User.objects.get(pk=r.json()["id"])

    def test_create_with_currency_and_credit_in_that_currency(self):
        d = self._create(display_currency="TRY", credit_limit="-4900")
        self.assertEqual(d.display_currency, "TRY")
        self.assertEqual(d.wallet.credit_limit, Decimal("-100.00"))      # 4900 ل.ت = 100$
        rows = self.client.get("/api/dealers/").json()
        rows = rows.get("results", rows) if isinstance(rows, dict) else rows
        row = next(r for r in rows if r["id"] == d.id)
        self.assertEqual((row["own_currency"], row["credit_limit_own"]), ("TRY", "-4900.00"))

    def test_topup_is_written_in_the_dealers_currency(self):
        d = self._create(display_currency="TRY")
        r = self.client.post(f"/api/dealers/{d.id}/topup/", {"amount": "980"}, format="json").json()
        d.wallet.refresh_from_db()
        self.assertEqual(d.wallet.balance, Decimal("20.00"))             # 980 ل.ت = 20$
        self.assertEqual((r["balance_own"], r["own_currency"]), ("980.00", "TRY"))
        self.assertIn("980.00 TRY", d.wallet.transactions.first().note)

    def test_settings_credit_limit_follows_the_new_currency(self):
        d = self._create()
        self.client.post(f"/api/dealers/{d.id}/settings/",
                         {"display_currency": "TRY", "credit_limit": "-2450"}, format="json")
        d.wallet.refresh_from_db()
        self.assertEqual(d.wallet.credit_limit, Decimal("-50.00"))
        row = self.client.get(f"/api/dealers/{d.id}/settings/").json()
        self.assertEqual((row["credit_limit"], row["own_currency"]), ("-2450.00", "TRY"))

    def test_a_base_currency_dealer_is_unchanged(self):
        d = self._create(credit_limit="-500")
        self.assertEqual(d.wallet.credit_limit, Decimal("-500"))
        self.client.post(f"/api/dealers/{d.id}/topup/", {"amount": "10"}, format="json")
        d.wallet.refresh_from_db()
        self.assertEqual(d.wallet.balance, Decimal("10"))


class SelfRegistrationTest(APITestCase):
    """
    التسجيل الذاتي: الحقول إجبارية (ومنها صورة الهوية وواتساب برمز الدولة)، والحساب
    «بانتظار الموافقة» لا يدخل؛ يظهر أعلى قائمة الوكلاء، ويُقبل بعملته وحدّه أو يُرفض.
    """

    IMG = "data:image/png;base64,iVBORw0KGgo="

    def setUp(self):
        from django.core.cache import cache
        cache.clear()
        self.t = Tenant.objects.create(subdomain="rg", name="أهلا كارد", base_currency="USD",
                                       exchange_rates={"TRY": "49"})
        self.admin = User.objects.create(login_id="rg-admin", name="م", tenant=self.t,
                                         role=User.Role.TENANT_ADMIN, status=User.Status.ACTIVE)

    def _form(self, **over):
        return {"name": "محمد الكدرو", "login_id": "5459453007", "password": "secret1",
                "country": "TR", "province": "إسطنبول", "whatsapp": "+905459453007",
                "display_currency": "TRY", "id_image": self.IMG, **over}

    def test_public_games_show_no_prices(self):
        from catalog.models import Game, Product
        g = Game.objects.create(tenant=self.t, name="PUBG", image_url="/x.png")
        Product.objects.create(tenant=self.t, game=g, name="60 UC", cost_price=Decimal("1"),
                               recommended_price=Decimal("2"))
        Game.objects.create(tenant=self.t, name="فارغة")   # بلا باقات ⇐ لا تُعرض
        body = self.client.get("/api/storefront/games/").json()
        self.assertEqual([x["name"] for x in body["games"]], ["PUBG"])
        self.assertNotIn("price", str(body))

    def test_every_field_is_required(self):
        for field in ("name", "login_id", "password", "country", "province", "whatsapp",
                      "display_currency", "id_image"):
            r = self.client.post("/api/storefront/register/", self._form(**{field: ""}), format="json")
            self.assertEqual(r.status_code, 400, field)
            self.assertIn(field, r.json()["errors"])
        self.assertFalse(User.objects.filter(login_id="5459453007").exists())

    def test_whatsapp_needs_country_code_and_image_must_be_an_image(self):
        r = self.client.post("/api/storefront/register/", self._form(whatsapp="abc"), format="json")
        self.assertIn("whatsapp", r.json()["errors"])
        r = self.client.post("/api/storefront/register/", self._form(id_image="hello"), format="json")
        self.assertIn("id_image", r.json()["errors"])

    def test_pending_cannot_log_in_until_approved(self):
        self.assertEqual(self.client.post("/api/storefront/register/", self._form(), format="json").status_code, 201)
        r = self.client.post("/api/auth/login/", {"login_id": "5459453007", "password": "secret1"}, format="json")
        self.assertEqual(r.status_code, 403)
        self.assertIn("قيد المراجعة", r.json()["detail"])

        self.client.force_authenticate(self.admin)
        listing = self.client.get("/api/dealers/").json()
        self.assertEqual([p["name"] for p in listing["pending"]], ["محمد الكدرو"])
        self.assertNotIn("محمد الكدرو", [r["name"] for r in listing["results"]])
        self.assertEqual(self.client.get("/api/alerts/").json()["registrations"], 1)

        pid = listing["pending"][0]["id"]
        r = self.client.post(f"/api/dealers/{pid}/registration/", {
            "action": "approve", "display_currency": "TRY", "credit_limit": "-4900"}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        u = User.objects.get(pk=pid)
        self.assertEqual((u.status, u.display_currency), ("active", "TRY"))
        self.assertEqual(u.wallet.credit_limit, Decimal("-100.00"))
        self.client.force_authenticate(None)
        r = self.client.post("/api/auth/login/", {"login_id": "5459453007", "password": "secret1"}, format="json")
        self.assertEqual(r.status_code, 200)

    def test_reject_removes_the_request(self):
        self.client.post("/api/storefront/register/", self._form(), format="json")
        pid = User.objects.get(login_id="5459453007").id
        self.client.force_authenticate(self.admin)
        r = self.client.post(f"/api/dealers/{pid}/registration/", {"action": "reject"}, format="json")
        self.assertEqual(r.json()["rejected"], True)
        self.assertFalse(User.objects.filter(pk=pid).exists())

    def test_flooding_is_throttled(self):
        for i in range(5):
            self.client.post("/api/storefront/register/", self._form(login_id=f"54594530{10 + i}"), format="json")
        r = self.client.post("/api/storefront/register/", self._form(login_id="5459453099"), format="json")
        self.assertEqual(r.status_code, 429)


    def test_the_dealer_picks_his_currency(self):
        r = self.client.post("/api/storefront/register/", self._form(display_currency="EUR"), format="json")
        self.assertIn("display_currency", r.json()["errors"])     # لا سعر صرف لليورو هنا
        self.client.post("/api/storefront/register/", self._form(), format="json")
        self.assertEqual(User.objects.get(login_id="5459453007").display_currency, "TRY")
        self.assertEqual(self.client.get("/api/storefront/").json()["store"]["currencies"], ["USD", "TRY"])
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.get("/api/dealers/").json()["pending"][0]["display_currency"], "TRY")


class RoleGateTest(APITestCase):
    """
    حاجز الأدوار (core/access.py): الوكيل بنوعيه لا يطرق إلا أبوابه.
    بتوكن حقيقي لا `force_authenticate` — فالحاجز يعيش في المصادقة نفسها.
    """

    def setUp(self):
        from rest_framework_simplejwt.tokens import RefreshToken
        self.tenant = Tenant.objects.create(subdomain="rg", name="متجر")
        mk = lambda lid, role: User.objects.create(
            login_id=lid, name=lid, tenant=self.tenant, role=role)
        self.admin = mk("rg-admin", User.Role.TENANT_ADMIN)
        self.big = mk("rg-big", User.Role.ANA_BAYI)
        self.bayi = mk("rg-bayi", User.Role.BAYI)
        self.tok = {u: str(RefreshToken.for_user(u).access_token)
                    for u in (self.admin, self.big, self.bayi)}

    def _get(self, user, path):
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.tok[user]}")
        return self.client.get(path)

    def test_dealers_are_locked_out_of_admin_doors(self):
        for path in ("/api/payments/methods/", "/api/payments/accounts/",
                     "/api/payments/notifications/", "/api/orders/",
                     "/api/orders/reports/dealers/", "/api/dealers/", "/api/ledger/",
                     "/api/settings/site/", "/api/inventory/live/", "/api/kontor/orders/"):
            for user in (self.big, self.bayi):
                self.assertEqual(self._get(user, path).status_code, 403, (user.login_id, path))

    def test_own_doors_stay_open(self):
        self.assertEqual(self._get(self.bayi, "/api/auth/me/").status_code, 200)
        self.assertEqual(self._get(self.bayi, "/api/payments/store/deposits/").status_code, 200)
        self.assertEqual(self._get(self.big, "/api/agent/summary/").status_code, 200)
        self.assertEqual(self._get(self.bayi, "/api/agent/summary/").status_code, 403)

    def test_owner_is_not_gated(self):
        self.assertEqual(self._get(self.admin, "/api/payments/methods/").status_code, 200)


class WalletLimitMessageTest(TestCase):
    """رسالة الحد الائتماني بعملة صاحب المحفظة — لا بدولارات الدفتر."""

    def test_message_is_in_owner_currency(self):
        from core import services
        t = Tenant.objects.create(subdomain="wl", name="متجر", base_currency="USD",
                                  exchange_rates={"TRY": "50"})
        u = User.objects.create(login_id="wl-1", name="و", tenant=t, role=User.Role.ANA_BAYI,
                                display_currency="TRY")
        w = Wallet.objects.create(tenant=t, user=u, balance=Decimal("0"), credit_limit=Decimal("-40"))
        with self.assertRaises(services.WalletError) as cm:
            services.apply_transaction(w.id, Decimal("-41"), "order_debit")
        msg = str(cm.exception)
        self.assertIn("-2,000.00 ₺", msg)          # 40$ × 50
        self.assertIn("الحد الائتماني", msg)         # يتعرّف بها الـ API الخارجي


class RoleGateUploadTest(RoleGateTest):
    def test_dealer_can_upload_receipt_image(self):
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.tok[self.bayi]}")
        r = self.client.post("/api/catalog/images/", {})
        self.assertEqual(r.status_code, 400)   # «لم يصل ملف» — لا 403
