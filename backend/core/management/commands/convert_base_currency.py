"""
تحويل عملة دفتر المتجر — يُشغَّل يدوياً مرّة واحدة، لا في النشر.

كل مبلغ محفوظ بعملة الموقع الحالية يُقسَم على السعر المُعطى فيصير بالعملة
الجديدة. مثال: دفتر بالليرة التركية وسعر الدولار 41.5 →

    python manage.py convert_base_currency --to USD --rate 41.5 --tenant alaya

يعمل بلا تنفيذ (معاينة) ما لم تُمرَّر --apply. والتنفيذ داخل معاملة واحدة:
إمّا أن يتحوّل كل شيء أو لا شيء.

خارج التحويل عمداً:
  • أسعار اشتراك المنصّة وفواتيرها — دفتر بين مالك المنصّة والمتجر، لا دفتر المتجر.
  • مبالغ طلبات الإيداع بعملة طريقة الدفع (amount) — محفوظة بعملتها لا بعملة الدفتر.
  • حدود طرق الدفع وعمولاتها — بعملة الطريقة ونِسَب مئوية.
"""
from decimal import Decimal, InvalidOperation

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from catalog.models import LibraryProduct, Product, ProductPrice
from core.models import Tenant, User, Wallet, WalletTransaction
from orders.models import Order
from payments.models import PaymentNotification, ReceivingAccount
from pool.models import Pin
from providers.models import Provider
from kontor.models import KontorOrder, KontorPackage, KontorPackagePrice

# (النموذج، الحقول المحفوظة بعملة الدفتر)
TENANT_SCOPED = [
    (User, ["oyun_load_limit"]),
    (Wallet, ["balance", "credit_limit"]),
    (WalletTransaction, ["amount", "balance_before", "balance_after"]),
    (Product, ["cost_price", "recommended_price"]),
    (ProductPrice, ["price"]),
    (Order, ["cost_price", "sell_price", "profit",
             "dealer_sell_price", "dealer_profit", "balance_before", "balance_after"]),
    (ReceivingAccount, ["balance"]),
    (PaymentNotification, ["credit_amount", "balance_before", "balance_after"]),
    (Pin, ["cost"]),
    (Provider, ["real_balance", "balance", "debt", "balance_alert_threshold"]),
    # الخطوط: provider_cost يبقى بعملة ZNET ولا يُحوَّل
    (KontorPackage, ["cost_price", "recommended_price"]),
    (KontorPackagePrice, ["price"]),
    (KontorOrder, ["cost_price", "sell_price", "profit", "dealer_sell_price", "dealer_profit",
                   "balance_before", "balance_after"]),
]


class Command(BaseCommand):
    help = "تحويل كل مبالغ المتجر إلى عملة دفتر جديدة (معاينة ما لم تُمرَّر --apply)"

    def add_arguments(self, parser):
        parser.add_argument("--to", required=True, help="العملة الجديدة، مثل USD")
        parser.add_argument("--rate", required=True,
                            help="كم وحدةً من العملة الحالية تساوي وحدةً من الجديدة")
        parser.add_argument("--tenant", help="نطاق المتجر (subdomain) — الافتراضي: كل المتاجر")
        parser.add_argument("--apply", action="store_true", help="تنفيذ فعلي بدل المعاينة")
        parser.add_argument("--include-library", action="store_true",
                            help="تحويل أسعار المكتبة العالمية أيضاً (مشتركة بين المتاجر)")

    def handle(self, *args, **o):
        # معطّلة عمداً (مراجعة المال 2026-10-10): لا تشمل حقول الوكيل الكبير (ما دفعه
        # الدكان وربح الوكيل وأسعاره وهوامشه) ولا لقطات الجرد، وتقسم أرصدة المزوّدين
        # وهي بعملتهم لا بعملة الدفتر، وتقرّب حقول الدفتر ذات المنازل الست إلى خانتين.
        # تشغيلها اليوم يُفسد استرجاع الطلبات القديمة وأسعار الوكلاء الكبار.
        raise CommandError(
            "الأداة معطّلة: لا تحوّل حقول الوكيل الكبير ولا تحافظ على دقّة الدفتر — "
            "تُحدَّث قبل أي تحويل عملة."
        )
        new_currency = o["to"].strip().upper()
        try:
            rate = Decimal(str(o["rate"]))
        except (InvalidOperation, TypeError):
            raise CommandError("سعر صرف غير صحيح")
        if rate <= 0:
            raise CommandError("سعر الصرف يجب أن يكون أكبر من صفر")

        tenants = Tenant.objects.all()
        if o.get("tenant"):
            tenants = tenants.filter(subdomain=o["tenant"])
            if not tenants.exists():
                raise CommandError(f"لا متجر بنطاق {o['tenant']}")

        dry = not o["apply"]
        head = "معاينة (بلا تنفيذ)" if dry else "تنفيذ"
        self.stdout.write(self.style.WARNING(f"── {head}: → {new_currency} بسعر {rate} ──"))

        with transaction.atomic():
            for tenant in tenants:
                old = tenant.base_currency or "TRY"
                if old == new_currency:
                    self.stdout.write(f"{tenant.subdomain}: العملة {old} أصلاً — تُخطّى")
                    continue
                self.stdout.write(self.style.MIGRATE_HEADING(
                    f"\n{tenant.name} ({tenant.subdomain}): {old} → {new_currency}"
                ))
                for model, fields in TENANT_SCOPED:
                    qs = model.objects.filter(tenant=tenant)
                    n = qs.count()
                    if not n:
                        continue
                    self.stdout.write(f"  {model.__name__:22} {n:6} صفّاً · {', '.join(fields)}")
                    if not dry:
                        for row in qs.iterator(chunk_size=500):
                            for f in fields:
                                v = getattr(row, f)
                                if v is not None:
                                    setattr(row, f, (Decimal(v) / rate).quantize(Decimal("0.01")))
                            row.save(update_fields=fields)

                # عملة المحافظ اسمٌ للعرض في الإدارة — تتبع عملة الدفتر
                if not dry:
                    Wallet.objects.filter(tenant=tenant).update(currency=new_currency)
                    # سعر صرف طلبات الإيداع كان من عملة الطريقة إلى العملة القديمة
                    for n_ in PaymentNotification.objects.filter(tenant=tenant).iterator():
                        n_.rate = (n_.rate / rate).quantize(Decimal("0.000001"))
                        n_.save(update_fields=["rate"])
                    # الأسعار محفوظة «كم وحدةً من العملة تساوي وحدةً من الدفتر»،
                    # ووحدة الدفتر الجديدة تساوي `rate` من القديمة ⇒ تُضرب فيه
                    converted = {
                        c: str((Decimal(str(v)) * rate).quantize(Decimal("0.000001")))
                        for c, v in (tenant.exchange_rates or {}).items()
                        if c != new_currency
                    }
                    # العملة القديمة صارت عملةً كأي أخرى، فتحتاج سعراً لنفسها
                    converted[old] = str(rate.quantize(Decimal("0.000001")))
                    tenant.exchange_rates = converted
                    tenant.base_currency = new_currency
                    tenant.save(update_fields=["base_currency", "exchange_rates"])
                    # عملة عرض وكيلٍ صارت هي عملة الدفتر ⇒ تُفرَّغ
                    User.objects.filter(tenant=tenant, display_currency=new_currency).update(
                        display_currency=""
                    )

            if o["include_library"]:
                n = LibraryProduct.objects.count()
                self.stdout.write(f"\n  LibraryProduct (عالمية) {n} صفّاً")
                if not dry:
                    for row in LibraryProduct.objects.iterator(chunk_size=500):
                        for f in ("suggested_cost", "suggested_price"):
                            setattr(row, f, (getattr(row, f) / rate).quantize(Decimal("0.01")))
                        row.save(update_fields=["suggested_cost", "suggested_price"])

            if dry:
                self.stdout.write(self.style.WARNING(
                    "\nمعاينة فقط — لم يُكتب شيء. أعد الأمر مع --apply للتنفيذ."
                ))
                transaction.set_rollback(True)
            else:
                self.stdout.write(self.style.SUCCESS("\n✅ تمّ التحويل"))

        if not dry:
            self.stdout.write(
                "تذكير: راجع «أسعار الصرف» في الإعدادات — حُوِّلت آلياً فتحقّق منها،\n"
                "وأسعار اشتراك المنصّة وفواتيرها لم تُمسّ (دفتر مختلف)."
            )
