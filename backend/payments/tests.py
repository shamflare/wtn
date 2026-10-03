from decimal import Decimal

from rest_framework.test import APITestCase

from core.models import Tenant, User, Wallet

from .models import ANY_CURRENCY, PaymentMethod, PaymentNotification


class CustomerChosenCurrencyTest(APITestCase):
    """طريقة دفع عملتها «يحددها العميل»: الوكيل يختار العملة التي أرسل بها."""

    def setUp(self):
        self.tenant = Tenant.objects.create(
            subdomain="tpay", name="متجر", base_currency="USD",
            exchange_rates={"TRY": "40"},
        )
        self.dealer = User.objects.create(
            login_id="bayipay", name="دكان", tenant=self.tenant, role=User.Role.BAYI,
        )
        Wallet.objects.create(tenant=self.tenant, user=self.dealer, balance=Decimal("0"))
        self.client.force_authenticate(user=self.dealer)
        self.method = PaymentMethod.objects.create(
            tenant=self.tenant, name="حوالة", currency=ANY_CURRENCY,
            min_amount=Decimal("5000"),   # لا تنطبق حين يختار الوكيل العملة
        )

    def _create(self, **body):
        return self.client.post(
            "/api/payments/store/deposits/create/",
            {"method": self.method.id, "amount": "400", **body}, format="json",
        )

    def test_listing_offers_priced_currencies(self):
        r = self.client.get("/api/payments/store/methods/")
        self.assertEqual(r.status_code, 200, r.content)
        row = next(m for m in r.json()["methods"] if m["id"] == self.method.id)
        self.assertEqual(row["currency"], ANY_CURRENCY)
        # الدولار عملة الدفتر، والليرة لها سعر — والبقية بلا سعر فلا تُعرض
        self.assertEqual(set(row["rates"]), {"USD", "TRY"})
        self.assertEqual(Decimal(row["rates"]["TRY"]), Decimal("0.025"))

    def test_listing_carries_qr_image(self):
        """صورة الباركود التي رفعها صاحب المتجر تصل إلى الوكيل مع الطريقة."""
        self.method.qr_url = "/api/catalog/img/abc/"
        self.method.save()
        r = self.client.get("/api/payments/store/methods/")
        row = next(m for m in r.json()["methods"] if m["id"] == self.method.id)
        self.assertEqual(row["qr_url"], "/api/catalog/img/abc/")

    def test_deposit_in_chosen_currency(self):
        r = self._create(currency="TRY")
        self.assertEqual(r.status_code, 201, r.content)
        notif = PaymentNotification.objects.get()
        self.assertEqual(notif.currency, "TRY")
        self.assertEqual(notif.rate, Decimal("40"))
        self.assertEqual(notif.credit_amount, Decimal("10.00"))

    def test_currency_is_required(self):
        r = self._create()
        self.assertEqual(r.status_code, 400)
        self.assertFalse(PaymentNotification.objects.exists())

    def test_currency_without_rate_is_rejected(self):
        r = self._create(currency="EUR")
        self.assertEqual(r.status_code, 400)
        self.assertFalse(PaymentNotification.objects.exists())

    def test_fixed_currency_method_ignores_sent_currency(self):
        self.method.currency = "USD"
        self.method.min_amount = Decimal("0")
        self.method.save()
        r = self._create(currency="TRY")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(PaymentNotification.objects.get().currency, "USD")
