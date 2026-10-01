"""اختبارات الكتالوج: التسعير الجماعي، تحديث التكاليف، حذف المجموعة."""
from decimal import Decimal
from unittest.mock import patch

from rest_framework.test import APITestCase

from core.models import Tenant, User
from providers.adapters.base import PackageList
from providers.models import Provider

from .models import (
    Game, LibraryGame, LibraryProduct, PriceGroup, Product, ProductLink, ProductPrice,
)


class CatalogToolsTest(APITestCase):
    """
    الدفتر بالدولار وسعر الليرة 40 — فكل سعر مزوّد بالليرة يُقسَم على 40.
    الرقم مستدير عمداً ليبقى المتوقَّع مقروءاً في التوكيدات.
    """

    def setUp(self):
        self.tenant = Tenant.objects.create(
            subdomain="t", name="متجر", base_currency="USD",
            exchange_rates={"TRY": "40"},
        )
        self.admin = User.objects.create(
            login_id="admin", name="مدير", tenant=self.tenant,
            role=User.Role.TENANT_ADMIN,
        )
        self.client.force_authenticate(user=self.admin)  # المصادقة JWT لا جلسات

        self.game = Game.objects.create(tenant=self.tenant, name="PUBG")
        self.p60 = Product.objects.create(
            tenant=self.tenant, game=self.game, name="60 UC",
            cost_price=Decimal("1.00"), recommended_price=Decimal("1.20"),
        )
        self.p325 = Product.objects.create(
            tenant=self.tenant, game=self.game, name="325 UC",
            cost_price=Decimal("4.00"), recommended_price=Decimal("4.50"),
        )
        self.group = PriceGroup.objects.create(tenant=self.tenant, name="1")

    # ── التسعير الجماعي ────────────────────────────────────────────
    def test_bulk_percent_prices_from_cost(self):
        r = self.client.post(
            "/api/catalog/bulk-price/",
            {"price_group": self.group.id, "products": [], "mode": "percent", "value": "25"},
            format="json",
        )
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()["updated"], 2)
        self.assertEqual(self._price(self.p60), Decimal("1.25"))
        self.assertEqual(self._price(self.p325), Decimal("5.00"))

    def test_bulk_is_repeatable(self):
        """الأساس هو التكلفة — فتطبيقان بالقيمة نفسها لا يضاعفان الزيادة."""
        body = {"price_group": self.group.id, "products": [], "mode": "percent", "value": "25"}
        self.client.post("/api/catalog/bulk-price/", body, format="json")
        self.client.post("/api/catalog/bulk-price/", body, format="json")
        self.assertEqual(self._price(self.p60), Decimal("1.25"))

    def test_bulk_fixed_and_selection(self):
        r = self.client.post(
            "/api/catalog/bulk-price/",
            {"price_group": self.group.id, "products": [self.p60.id],
             "mode": "fixed", "value": "0.50"},
            format="json",
        )
        self.assertEqual(r.json()["updated"], 1)
        self.assertEqual(self._price(self.p60), Decimal("1.50"))
        # لم تُحدَّد فلا تُسعَّر
        self.assertIsNone(self._price(self.p325))

    def test_bulk_skips_zero_cost(self):
        """باقة بتكلفة صفر لا تُسعَّر بصفر — تُترك ويُذكر اسمها."""
        free = Product.objects.create(
            tenant=self.tenant, game=self.game, name="بلا تكلفة", cost_price=Decimal("0"),
        )
        r = self.client.post(
            "/api/catalog/bulk-price/",
            {"price_group": self.group.id, "products": [], "mode": "percent", "value": "25"},
            format="json",
        )
        self.assertEqual(r.json()["updated"], 2)
        self.assertIn("بلا تكلفة", r.json()["skipped_zero_cost"])
        self.assertIsNone(self._price(free))

    def test_bulk_rejects_negative_result(self):
        r = self.client.post(
            "/api/catalog/bulk-price/",
            {"price_group": self.group.id, "products": [], "mode": "fixed", "value": "-9"},
            format="json",
        )
        self.assertEqual(r.status_code, 400)
        self.assertIsNone(self._price(self.p60))  # لم يُكتب شيء

    # ── ارتباط السعر بالتكلفة ──────────────────────────────────────
    def test_bulk_links_price_to_cost(self):
        """التسعير الجماعي يحفظ قاعدة لا رقماً — والسعر يتبع التكلفة بعدها."""
        self._bulk("percent", "25")
        self.assertEqual(self._price(self.p60), Decimal("1.25"))

        self.p60.cost_price = Decimal("2.00")
        self.p60.save()

        self.assertEqual(self._price(self.p60), Decimal("2.50"))  # تبع التكلفة وحده

    def test_refresh_costs_pulls_linked_prices(self):
        """تغيّر التكلفة من «تحديث التكاليف» يجرّ السعر المرتبط معه."""
        self._bulk("percent", "25")
        provider = self._provider()
        ProductLink.objects.create(
            tenant=self.tenant, product=self.p60, provider=provider, package_id="1",
        )
        catalog = PackageList(ok=True, packages=[{"id": "1", "name": "PUBG 60", "price": "80"}])

        with patch("providers.adapters.znet.ZnetAdapter.list_packages", return_value=catalog):
            self.client.post(
                "/api/catalog/refresh-costs/",
                {"provider": provider.id, "products": []}, format="json",
            )

        self.p60.refresh_from_db()
        self.assertEqual(self.p60.cost_price, Decimal("2.00"))   # 80 ل.ت ÷ 40
        self.assertEqual(self._price(self.p60), Decimal("2.50"))  # 2.00 + 25%

    def test_manual_edit_breaks_the_link(self):
        """الرقم المكتوب باليد لا يمحوه أوّلُ تغيير في التكلفة."""
        self._bulk("percent", "25")
        self.client.post(
            "/api/catalog/set-price/",
            {"product": self.p60.id, "price_group": self.group.id, "price": "9.99"},
            format="json",
        )

        self.p60.cost_price = Decimal("2.00")
        self.p60.save()

        self.assertEqual(self._price(self.p60), Decimal("9.99"))  # ثبت كما كُتب
        self.assertFalse(self._row(self.p60).linked)

    def test_new_bulk_replaces_the_rule(self):
        """تسعير جماعي جديد يحلّ محلّ القاعدة القديمة لا يتراكم عليها."""
        self._bulk("percent", "25")
        self._bulk("fixed", "0.50")
        self.assertEqual(self._price(self.p60), Decimal("1.50"))

        self.p60.cost_price = Decimal("2.00")
        self.p60.save()

        self.assertEqual(self._price(self.p60), Decimal("2.50"))  # 2.00 + 0.50 لا +25%
        self.assertEqual(self._row(self.p60).margin_mode, "fixed")

    def test_unlinked_cells_never_move(self):
        """باقة لم تدخل التسعير الجماعي لا يمسّها تغيّر تكلفتها."""
        self.client.post(
            "/api/catalog/set-price/",
            {"product": self.p325.id, "price_group": self.group.id, "price": "4.44"},
            format="json",
        )
        self.p325.cost_price = Decimal("9.00")
        self.p325.save()
        self.assertEqual(self._price(self.p325), Decimal("4.44"))

    def test_matrix_exposes_the_rule(self):
        self._bulk("percent", "25")
        r = self.client.get("/api/catalog/price-matrix/")
        cell = r.json()["games"][0]["products"][0]["prices"][str(self.group.id)]
        self.assertEqual(cell["margin"]["mode"], "percent")
        self.assertEqual(Decimal(cell["margin"]["value"]), Decimal("25"))

    # ── تحديث التكاليف ─────────────────────────────────────────────
    def test_refresh_costs_converts_provider_lira(self):
        """سعر المزوّد 44 ل.ت ⇒ تكلفتنا 1.10$ لا 44$."""
        provider = self._provider()
        ProductLink.objects.create(
            tenant=self.tenant, product=self.p60, provider=provider, package_id="1",
        )
        catalog = PackageList(ok=True, packages=[{"id": "1", "name": "PUBG 60", "price": "44"}])

        with patch("providers.adapters.znet.ZnetAdapter.list_packages", return_value=catalog):
            r = self.client.post(
                "/api/catalog/refresh-costs/",
                {"provider": provider.id, "products": []}, format="json",
            )

        self.assertEqual(r.status_code, 200, r.content)
        self.p60.refresh_from_db()
        self.assertEqual(self.p60.cost_price, Decimal("1.10"))
        # السعر المرجعي لحماية الخسارة يُحفظ بعملة الدفتر كذلك
        link = ProductLink.objects.get(product=self.p60, provider=provider)
        self.assertEqual(link.extra["price"], "1.10")

    def test_refresh_costs_matches_by_kupur_not_id_alone(self):
        """
        زينت يرقّم بـpackage_id **اللعبة** لا الباقة: باقات ببجي كلّها رقمها 1
        ويميّزها الكوبون. المطابقة بالرقم وحده كانت تلصق سعر أوّل باقة بكلّها.
        """
        provider = self._provider()
        ProductLink.objects.create(
            tenant=self.tenant, product=self.p60, provider=provider,
            package_id="1", extra={"kupur": "60"},
        )
        ProductLink.objects.create(
            tenant=self.tenant, product=self.p325, provider=provider,
            package_id="1", extra={"kupur": "325"},
        )
        catalog = PackageList(ok=True, packages=[
            {"id": "1", "kupur": "60", "name": "PUBG 60 UC", "price": "40"},
            {"id": "1", "kupur": "325", "name": "PUBG 325 UC", "price": "160"},
        ])

        with patch("providers.adapters.znet.ZnetAdapter.list_packages", return_value=catalog):
            self.client.post(
                "/api/catalog/refresh-costs/",
                {"provider": provider.id, "products": []}, format="json",
            )

        self.p60.refresh_from_db()
        self.p325.refresh_from_db()
        self.assertEqual(self.p60.cost_price, Decimal("1.00"))    # 40 ÷ 40
        self.assertEqual(self.p325.cost_price, Decimal("4.00"))   # 160 ÷ 40 — لا 1.00

    def test_refresh_costs_refuses_ambiguous_link(self):
        """رابط بلا كوبون واللعبة فيها أكثر من باقة: نمتنع بدل أن نخمّن."""
        provider = self._provider()
        ProductLink.objects.create(
            tenant=self.tenant, product=self.p60, provider=provider, package_id="1", extra={},
        )
        catalog = PackageList(ok=True, packages=[
            {"id": "1", "kupur": "60", "name": "PUBG 60 UC", "price": "40"},
            {"id": "1", "kupur": "325", "name": "PUBG 325 UC", "price": "160"},
        ])

        with patch("providers.adapters.znet.ZnetAdapter.list_packages", return_value=catalog):
            r = self.client.post(
                "/api/catalog/refresh-costs/",
                {"provider": provider.id, "products": []}, format="json",
            )

        self.assertEqual(r.json()["updated"], [])
        self.assertIn("حدّد الكوبون", r.json()["skipped"][0]["note"])
        self.p60.refresh_from_db()
        self.assertEqual(self.p60.cost_price, Decimal("1.00"))  # لم تُمَسّ

    def test_refresh_costs_matches_single_package_without_kupur(self):
        """مزوّد بلا كوبونات (ZDK): المعرّف وحده يكفي ما دام فريداً."""
        provider = self._provider()
        ProductLink.objects.create(
            tenant=self.tenant, product=self.p60, provider=provider,
            package_id="823", extra={},
        )
        catalog = PackageList(ok=True, packages=[{"id": "823", "name": "PUBG 60", "price": "44"}])

        with patch("providers.adapters.znet.ZnetAdapter.list_packages", return_value=catalog):
            self.client.post(
                "/api/catalog/refresh-costs/",
                {"provider": provider.id, "products": []}, format="json",
            )

        self.p60.refresh_from_db()
        self.assertEqual(self.p60.cost_price, Decimal("1.10"))

    def test_refresh_costs_reports_missing_package(self):
        provider = self._provider()
        ProductLink.objects.create(
            tenant=self.tenant, product=self.p60, provider=provider, package_id="999",
        )
        catalog = PackageList(ok=True, packages=[{"id": "1", "name": "غيرها", "price": "44"}])

        with patch("providers.adapters.znet.ZnetAdapter.list_packages", return_value=catalog):
            r = self.client.post(
                "/api/catalog/refresh-costs/",
                {"provider": provider.id, "products": []}, format="json",
            )

        self.assertEqual(r.json()["updated"], [])
        self.assertEqual(len(r.json()["skipped"]), 1)
        self.p60.refresh_from_db()
        self.assertEqual(self.p60.cost_price, Decimal("1.00"))  # لم تُمسّ

    def test_refresh_costs_needs_exchange_rate(self):
        """بلا سعر صرف مضبوط يُرفض التحديث بدل أن يُحسب بمعامل 1 صامت."""
        self.tenant.exchange_rates = {}
        self.tenant.save()
        provider = self._provider()
        ProductLink.objects.create(
            tenant=self.tenant, product=self.p60, provider=provider, package_id="1",
        )
        r = self.client.post(
            "/api/catalog/refresh-costs/",
            {"provider": provider.id, "products": []}, format="json",
        )
        self.assertEqual(r.status_code, 400)
        self.p60.refresh_from_db()
        self.assertEqual(self.p60.cost_price, Decimal("1.00"))

    # ── التوجيه التلقائي حسب السعر ─────────────────────────────────
    def test_auto_route_orders_cheapest_first(self):
        cheap = self._provider("رخيص")
        mid = self._provider("وسط")
        dear = self._provider("غالٍ")
        self._link(self.p325, dear, "3", "3.90")
        self._link(self.p325, cheap, "1", "1.50")
        self._link(self.p325, mid, "2", "2.70")

        r = self.client.post("/api/catalog/auto-route/", {"apply": True}, format="json")

        self.assertEqual(r.status_code, 200, r.content)
        self.p325.refresh_from_db()
        self.assertEqual(self.p325.provider_id, cheap.id)
        self.assertEqual(self.p325.provider_alt1_id, mid.id)
        self.assertEqual(self.p325.provider_alt2_id, dear.id)
        self.assertEqual(self.p325.execution_type, Product.Execution.AUTO)

    def test_auto_route_puts_loss_provider_last(self):
        """سعر بيع 4.50 — فمن سعره 6.00 خاسر ويُؤخَّر مهما كان ترتيبه بالسعر."""
        loser = self._provider("خاسر")
        winner = self._provider("رابح")
        self._link(self.p325, loser, "1", "6.00")
        self._link(self.p325, winner, "2", "4.00")

        r = self.client.post("/api/catalog/auto-route/", {"apply": True}, format="json")

        self.p325.refresh_from_db()
        self.assertEqual(self.p325.provider_id, winner.id)
        self.assertEqual(self.p325.provider_alt1_id, loser.id)
        row = next(x for x in r.json()["plan"] if x["id"] == self.p325.id)
        self.assertTrue(row["after"][1]["loss"])  # مَوسوم في المعاينة

    def test_auto_route_places_unknown_price_after_winners(self):
        known = self._provider("معروف")
        unknown = self._provider("مجهول")
        self._link(self.p325, known, "1", "4.00")
        self._link(self.p325, unknown, "2", None)

        self.client.post("/api/catalog/auto-route/", {"apply": True}, format="json")

        self.p325.refresh_from_db()
        self.assertEqual(self.p325.provider_id, known.id)
        self.assertEqual(self.p325.provider_alt1_id, unknown.id)

    def test_auto_route_preview_changes_nothing(self):
        """المعاينة تُري الخطة ولا تكتب — وإلا فلا معنى لكونها معاينة."""
        cheap = self._provider("رخيص")
        self._link(self.p325, cheap, "1", "1.50")

        r = self.client.post("/api/catalog/auto-route/", {"apply": False}, format="json")

        self.assertFalse(r.json()["applied"])
        self.p325.refresh_from_db()
        self.assertIsNone(self.p325.provider_id)

    def test_auto_route_reports_unlinked_package(self):
        self._provider("مزوّد")
        r = self.client.post("/api/catalog/auto-route/", {"apply": True}, format="json")
        row = next(x for x in r.json()["plan"] if x["id"] == self.p325.id)
        self.assertIn("بلا ربط", row["note"])
        self.assertFalse(row["changed"])

    def test_auto_route_keeps_only_three_and_counts_the_rest(self):
        for i, price in enumerate(["1.00", "2.00", "3.00", "4.00"], start=1):
            self._link(self.p325, self._provider(f"م{i}"), str(i), price)

        r = self.client.post("/api/catalog/auto-route/", {"apply": True}, format="json")

        row = next(x for x in r.json()["plan"] if x["id"] == self.p325.id)
        self.assertEqual(len(row["after"]), 3)
        self.assertEqual(row["dropped"], 1)

    def test_auto_route_converts_manual_package(self):
        self.p325.execution_type = Product.Execution.MANUAL
        self.p325.save()
        self._link(self.p325, self._provider("مزوّد"), "1", "1.50")

        r = self.client.post("/api/catalog/auto-route/", {"apply": True}, format="json")

        self.p325.refresh_from_db()
        self.assertEqual(self.p325.execution_type, Product.Execution.AUTO)
        row = next(x for x in r.json()["plan"] if x["id"] == self.p325.id)
        self.assertTrue(row["was_manual"])

    # ── حذف المجموعة ───────────────────────────────────────────────
    def test_delete_group_moves_dealers_out(self):
        dealer = User.objects.create(
            login_id="bayi1", name="وكيل", tenant=self.tenant,
            role=User.Role.BAYI, price_group=self.group,
        )
        ProductPrice.objects.create(
            tenant=self.tenant, product=self.p60, price_group=self.group, price=Decimal("1.11"),
        )

        r = self.client.delete(f"/api/catalog/price-groups/{self.group.id}/")

        self.assertEqual(r.status_code, 204)
        dealer.refresh_from_db()
        self.assertIsNone(dealer.price_group_id)  # لا يُحذف الوكيل مع مجموعته
        self.assertFalse(ProductPrice.objects.filter(price_group_id=self.group.id).exists())

    def test_price_group_list_carries_dealer_count(self):
        User.objects.create(
            login_id="bayi2", name="وكيل", tenant=self.tenant,
            role=User.Role.BAYI, price_group=self.group,
        )
        r = self.client.get("/api/catalog/price-groups/")
        self.assertEqual(r.json()[0]["dealer_count"], 1)

    # ── مساعدات ────────────────────────────────────────────────────
    def _provider(self, name="زينت"):
        return Provider.objects.create(
            tenant=self.tenant, name=name, type=Provider.Type.CARD_STORE,
            config={"code": "znet"},
        )

    def _link(self, product, provider, package_id, price):
        return ProductLink.objects.create(
            tenant=self.tenant, product=product, provider=provider,
            package_id=package_id, extra={"price": price} if price else {},
        )

    def _bulk(self, mode, value, products=None):
        return self.client.post(
            "/api/catalog/bulk-price/",
            {"price_group": self.group.id, "products": products or [],
             "mode": mode, "value": value},
            format="json",
        )

    def _row(self, product):
        return ProductPrice.objects.filter(product=product, price_group=self.group).first()

    def _price(self, product):
        pp = self._row(product)
        return pp.price if pp else None


class LibraryLinkNumberTest(APITestCase):
    """
    رقم الربط جسر ثابت مصدره المكتبة العالمية.

    ثلاث قواعد تُختبَر هنا: لا يُخترع رقم من خارج المكتبة، ولا يتكرّر رقمان في
    لعبة واحدة، ولا يتغيّر رقم بعد إنشائه — ويعود إلى قائمة المتاح متى حُذفت باقته.
    """

    def setUp(self):
        self.tenant = Tenant.objects.create(subdomain="t2", name="متجر", base_currency="USD")
        self.admin = User.objects.create(
            login_id="admin2", name="مدير", tenant=self.tenant, role=User.Role.TENANT_ADMIN,
        )
        self.client.force_authenticate(user=self.admin)

        self.lib = LibraryGame.objects.create(name="PUBG")
        for i, (kupur, name, cost, price) in enumerate([
            ("60", "60 UC", "0.92", "1.20"),
            ("325", "325 UC", "4.57", "3.81"),
            ("660", "660 UC", "6.70", "7.52"),
        ]):
            LibraryProduct.objects.create(
                game=self.lib, name=name, kupur=kupur, sort_order=i,
                suggested_cost=Decimal(cost), suggested_price=Decimal(price),
            )

        self.game = Game.objects.create(
            tenant=self.tenant, name="PUBG", master_library_uuid=self.lib.uuid,
        )
        self.p60 = Product.objects.create(
            tenant=self.tenant, game=self.game, name="60 UC", kupur="60",
            cost_price=Decimal("0.92"), recommended_price=Decimal("1.20"),
        )

    def _available(self):
        r = self.client.get(f"/api/catalog/games/{self.game.id}/library-packages/")
        self.assertEqual(r.status_code, 200, r.content)
        return r.json()

    def _add(self, kupur, name="باقة"):
        return self.client.post(
            "/api/catalog/products/",
            {"game": self.game.id, "name": name, "kupur": kupur,
             "cost_price": "1", "recommended_price": "2"},
            format="json",
        )

    def test_available_excludes_numbers_already_taken(self):
        data = self._available()
        self.assertTrue(data["linked"])
        self.assertEqual([p["kupur"] for p in data["results"]], ["325", "660"])
        # القيم المقترحة تصل معها لتملأ النموذج
        self.assertEqual(data["results"][0]["suggested_cost"], "4.57")

    def test_deleting_a_package_returns_its_number_to_the_pool(self):
        self.client.delete(f"/api/catalog/products/{self.p60.id}/")
        self.assertEqual([p["kupur"] for p in self._available()["results"]], ["60", "325", "660"])

    def test_number_outside_the_library_is_refused(self):
        r = self._add("999")
        self.assertEqual(r.status_code, 400, r.content)
        self.assertIn("المكتبة", str(r.json()["kupur"]))

    def test_empty_number_is_refused_for_a_library_game(self):
        self.assertEqual(self._add("").status_code, 400)

    def test_duplicate_number_in_the_same_game_is_refused(self):
        r = self._add("60")
        self.assertEqual(r.status_code, 400, r.content)
        self.assertIn("مستعمل", str(r.json()["kupur"]))

    def test_available_number_is_accepted_with_its_library_values(self):
        r = self._add("325", name="325 UC")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.json()["kupur"], "325")

    def test_update_never_changes_the_number(self):
        r = self.client.patch(
            f"/api/catalog/products/{self.p60.id}/",
            {"kupur": "999", "name": "اسم جديد", "cost_price": "2.00"}, format="json",
        )
        self.assertEqual(r.status_code, 200, r.content)
        self.p60.refresh_from_db()
        self.assertEqual(self.p60.kupur, "60")          # الجسر ثابت
        self.assertEqual(self.p60.name, "اسم جديد")      # وما يملكه صاحب المتجر يتغيّر
        self.assertEqual(self.p60.cost_price, Decimal("2.00"))

    def test_game_outside_the_library_keeps_manual_numbers(self):
        own = Game.objects.create(tenant=self.tenant, name="لعبة يدوية")
        r = self.client.post(
            "/api/catalog/products/",
            {"game": own.id, "name": "باقة", "kupur": "abc",
             "cost_price": "1", "recommended_price": "2"}, format="json",
        )
        self.assertEqual(r.status_code, 201, r.content)
        data = self.client.get(f"/api/catalog/games/{own.id}/library-packages/").json()
        self.assertFalse(data["linked"])

    def test_library_refuses_two_packages_with_the_same_number(self):
        owner = User.objects.create(
            login_id="owner", name="مالك المنصّة", role=User.Role.PLATFORM_OWNER,
        )
        self.client.force_authenticate(user=owner)
        r = self.client.post(
            "/api/platform/library/products/",
            {"game": self.lib.id, "name": "مكرّر", "kupur": "60",
             "suggested_cost": "1", "suggested_price": "2"}, format="json",
        )
        self.assertEqual(r.status_code, 400, r.content)


class LibraryLinkingTest(APITestCase):
    """ربط لعبة المتجر بنظيرتها في المكتبة — بالاسم تلقائياً أو باختيار المالك."""

    def setUp(self):
        self.tenant = Tenant.objects.create(subdomain="t3", name="متجر", base_currency="USD")
        self.admin = User.objects.create(
            login_id="admin3", name="مدير", tenant=self.tenant, role=User.Role.TENANT_ADMIN,
        )
        self.client.force_authenticate(user=self.admin)

        self.lib = LibraryGame.objects.create(name="PUBG Mobile UC")
        for i, (kupur, name) in enumerate([("60", "60 UC"), ("325", "325 UC"), ("660", "660 UC")]):
            LibraryProduct.objects.create(
                game=self.lib, name=name, kupur=kupur, sort_order=i,
                suggested_cost=Decimal("1"), suggested_price=Decimal("2"),
            )

    def _packages(self, game):
        return self.client.get(f"/api/catalog/games/{game.id}/library-packages/").json()

    def test_name_match_links_and_adopts_numbers(self):
        """«PUBG Mobile» تجد «PUBG Mobile UC»، وباقاتها تنال أرقامها بالاسم."""
        game = Game.objects.create(tenant=self.tenant, name="PUBG Mobile")
        p60 = Product.objects.create(tenant=self.tenant, game=game, name="60 UC")
        p325 = Product.objects.create(tenant=self.tenant, game=game, name="325 UC")

        data = self._packages(game)
        self.assertTrue(data["linked"])
        p60.refresh_from_db(); p325.refresh_from_db()
        self.assertEqual(p60.kupur, "60")
        self.assertEqual(p325.kupur, "325")
        # ولا يبقى متاحاً إلا ما لم يُؤخَذ
        self.assertEqual([r["kupur"] for r in data["results"]], ["660"])

    def test_unmatched_game_offers_the_library_list(self):
        game = Game.objects.create(tenant=self.tenant, name="لعبة لا نظير لها")
        data = self._packages(game)
        self.assertFalse(data["linked"])
        self.assertEqual([g["name"] for g in data["library_games"]], ["PUBG Mobile UC"])
        self.assertEqual(data["library_games"][0]["packages"], 3)

    def test_manual_link_adopts_numbers_too(self):
        game = Game.objects.create(tenant=self.tenant, name="ببجي")
        Product.objects.create(tenant=self.tenant, game=game, name="660 UC")

        r = self.client.post(
            f"/api/catalog/games/{game.id}/link-library/", {"library_game": self.lib.id},
            format="json",
        )
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()["adopted"], 1)
        self.assertEqual([x["kupur"] for x in self._packages(game)["results"]], ["60", "325"])

    def test_adoption_never_overwrites_an_existing_number(self):
        game = Game.objects.create(tenant=self.tenant, name="ببجي 2")
        p = Product.objects.create(tenant=self.tenant, game=game, name="60 UC", kupur="325")

        self.client.post(
            f"/api/catalog/games/{game.id}/link-library/", {"library_game": self.lib.id},
            format="json",
        )
        p.refresh_from_db()
        self.assertEqual(p.kupur, "325")   # ما وضعه المالك يبقى
        self.assertEqual([x["kupur"] for x in self._packages(game)["results"]], ["60", "660"])

    def test_two_similar_library_games_stay_unlinked(self):
        """الاحتواء المتعدّد لا يُخمَّن — يختار المالك بنفسه."""
        LibraryGame.objects.create(name="PUBG Mobile Global")
        game = Game.objects.create(tenant=self.tenant, name="PUBG Mobile")
        self.assertFalse(self._packages(game)["linked"])



class ImageUploadTest(APITestCase):
    """رفع صور المكتبة: صورٌ حقيقية فقط، ولمالك المنصّة وأصحاب المتاجر وحدهم، وعرضها عام."""

    PNG = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00"
           b"\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xf8\xff\xff?\x00\x05\xfe\x02\xfe\xa7\x9a\xa0\xa0"
           b"\x00\x00\x00\x00IEND\xaeB`\x82")

    def setUp(self):
        from core.models import User
        self.owner = User.objects.create(login_id="img-owner", name="مالك", role=User.Role.PLATFORM_OWNER)
        self.tenant = Tenant.objects.create(subdomain="img", name="متجر")
        self.agent = User.objects.create(login_id="img-agent", name="وكيل", tenant=self.tenant, role=User.Role.BAYI)

    def _upload(self, content, name="a.png"):
        from django.core.files.uploadedfile import SimpleUploadedFile
        return self.client.post("/api/catalog/images/",
                                {"file": SimpleUploadedFile(name, content, content_type="image/png")},
                                format="multipart")

    def test_upload_then_anyone_can_view(self):
        self.client.force_authenticate(self.owner)
        r = self._upload(self.PNG)
        self.assertEqual(r.status_code, 201)
        url = r.json()["url"]
        self.client.force_authenticate(None)
        img = self.client.get(url)
        self.assertEqual(img.status_code, 200)
        self.assertEqual(img["Content-Type"], "image/png")
        self.assertIn("immutable", img["Cache-Control"])
        self.assertEqual(img.content, self.PNG)

    def test_a_fake_image_is_refused(self):
        """HTML باسم صورة — لو قُبل لصار صفحةً تُفتح من نطاق الموقع."""
        self.client.force_authenticate(self.owner)
        r = self._upload(b"<html><script>alert(1)</script></html>")
        self.assertEqual(r.status_code, 400)

    def test_an_agent_cannot_upload(self):
        self.client.force_authenticate(self.agent)
        self.assertEqual(self._upload(self.PNG).status_code, 403)

    def test_library_game_keeps_the_uploaded_url_and_can_be_edited(self):
        self.client.force_authenticate(self.owner)
        url = self._upload(self.PNG).json()["url"]
        g = self.client.post("/api/platform/library/games/", {"name": "PUBG", "image_url": url}, format="json").json()
        r = self.client.patch(f"/api/platform/library/games/{g['id']}/", {"name": "PUBG Mobile"}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["name"], "PUBG Mobile")
        self.assertEqual(r.json()["image_url"], url)



class LibraryImageFollowsTest(APITestCase):
    """صورة المكتبة تصل إلى المتاجر التي استوردت قبل إضافتها — إلا من خصّص صورته."""

    def setUp(self):
        from .models import Game, LibraryGame
        self.owner = User.objects.create(login_id="lif-owner", name="مالك", role=User.Role.PLATFORM_OWNER)
        self.lib = LibraryGame.objects.create(name="PUBG")
        t1 = Tenant.objects.create(subdomain="lif1", name="أ")
        t2 = Tenant.objects.create(subdomain="lif2", name="ب")
        self.plain = Game.objects.create(tenant=t1, name="PUBG", master_library_uuid=self.lib.uuid)
        self.custom = Game.objects.create(tenant=t2, name="PUBG", master_library_uuid=self.lib.uuid,
                                          image_url="/mine.png")
        self.client.force_authenticate(self.owner)

    def test_new_library_image_reaches_untouched_copies_only(self):
        r = self.client.patch(f"/api/platform/library/games/{self.lib.id}/",
                              {"image_url": "/api/catalog/img/abc/"}, format="json")
        self.assertEqual(r.status_code, 200)
        self.plain.refresh_from_db(); self.custom.refresh_from_db()
        self.assertEqual(self.plain.image_url, "/api/catalog/img/abc/")
        self.assertEqual(self.custom.image_url, "/mine.png")

    def test_a_second_change_follows_too(self):
        url = f"/api/platform/library/games/{self.lib.id}/"
        self.client.patch(url, {"image_url": "/api/catalog/img/one/"}, format="json")
        self.client.patch(url, {"image_url": "/api/catalog/img/two/"}, format="json")
        self.plain.refresh_from_db()
        self.assertEqual(self.plain.image_url, "/api/catalog/img/two/")



class GameDeleteTest(APITestCase):
    """«حذف» اللعبة: نهائيٌّ بلا طلبات، وأرشفةٌ تحفظ سجلّ الطلبات إن وُجدت."""

    def setUp(self):
        from core.models import Wallet
        from .models import Game, Product
        self.tenant = Tenant.objects.create(subdomain="gd", name="متجر", base_currency="USD")
        self.admin = User.objects.create(login_id="gd-admin", name="مدير", tenant=self.tenant,
                                         role=User.Role.TENANT_ADMIN, is_staff=True)
        self.dealer = User.objects.create(login_id="gd-d", name="وكيل", tenant=self.tenant,
                                          role=User.Role.BAYI, dealer_no=1)
        Wallet.objects.create(tenant=self.tenant, user=self.dealer, balance=Decimal("100"))
        self.game = Game.objects.create(tenant=self.tenant, name="PUBG", master_library_uuid="lib-1")
        self.product = Product.objects.create(tenant=self.tenant, game=self.game, name="60 UC",
                                              cost_price=Decimal("6"), recommended_price=Decimal("10"))

    def test_no_orders_deletes_for_good(self):
        from .models import Game, Product
        self.client.force_authenticate(self.admin)
        r = self.client.delete(f"/api/catalog/games/{self.game.id}/")
        self.assertEqual(r.json(), {"deleted": True, "archived": False})
        self.assertFalse(Game.all_objects.filter(pk=self.game.id).exists())
        self.assertFalse(Product.all_objects.filter(pk=self.product.id).exists())

    def test_with_orders_it_vanishes_but_history_stays(self):
        from orders.services import create_order
        from .models import Game
        order = create_order(self.dealer, self.product)
        self.client.force_authenticate(self.admin)
        r = self.client.delete(f"/api/catalog/games/{self.game.id}/")
        self.assertEqual(r.json()["archived"], True)
        # يختفي من قائمة صاحب المتجر ومن متجر الوكيل
        self.assertNotIn("PUBG", self.client.get("/api/catalog/games/").content.decode())
        self.client.force_authenticate(self.dealer)
        self.assertEqual(self.client.get("/api/store/catalog/").json()["games"], [])
        # والطلب القديم يُقرأ باسمه
        row = self.client.get("/api/store/orders/").json()["results"][0]
        self.assertEqual(row["id"], order.id)
        self.assertEqual(row["game_name"], "PUBG")
        self.assertEqual(row["product_name"], "60 UC")
        # ويُستورد من المكتبة من جديد (لا يعدّه «مستورداً»)
        self.assertFalse(Game.objects.filter(master_library_uuid="lib-1").exists())

    def test_an_agent_cannot_delete(self):
        self.client.force_authenticate(self.dealer)
        self.assertEqual(self.client.delete(f"/api/catalog/games/{self.game.id}/").status_code, 403)
