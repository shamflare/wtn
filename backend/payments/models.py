"""
نماذج المدفوعات: حسابات الاستلام (Hesaplarım) + طرق الدفع وحقولها +
طلبات إضافة الرصيد (إشعارات الدفع) مع مسار الموافقة.
مبني على docs/DATABASE_SCHEMA.md (قسم ج).
"""
from decimal import Decimal
from django.db import models

from core.models import Tenant, User


# العملات المدعومة في طرق الدفع وسعر الصرف العام
CURRENCIES = [
    ("TRY", "ليرة تركية"),
    ("USD", "دولار أمريكي"),
    ("SYP", "ليرة سورية"),
    ("EUR", "يورو"),
    ("SAR", "ريال سعودي"),
    ("AED", "درهم إماراتي"),
    ("EGP", "جنيه مصري"),
]

# عملة طريقة الدفع قد تُترك للوكيل: يختار عند الإيداع العملة التي أرسل بها فعلاً
ANY_CURRENCY = "ANY"
METHOD_CURRENCIES = CURRENCIES + [(ANY_CURRENCY, "يحددها العميل")]


class ReceivingAccount(models.Model):
    """حساب استلام أموال (Hesaplarım) — بنك أو محفظة إلكترونية."""

    class Method(models.TextChoices):
        SHAM_CASH = "sham_cash", "شام كاش"
        MTN_CASH = "mtn_cash", "MTN كاش"
        SYRIATEL_CASH = "syriatel_cash", "سيرياتيل كاش"
        BANK = "bank", "تحويل بنكي"
        CASH = "cash", "نقدي"

    class Status(models.TextChoices):
        ACTIVE = "active", "نشط"
        PASSIVE = "passive", "معطّل"

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="receiving_accounts")
    method = models.CharField(max_length=16, choices=Method.choices, default=Method.SHAM_CASH)
    title = models.CharField(max_length=120)              # Kurum/Şube Adı
    account_no = models.CharField(max_length=120, blank=True, default="")  # Hesap No
    balance = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE)
    notification_enabled = models.BooleanField(default=True)  # Bildirim
    sort_order = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "receiving_accounts"
        ordering = ["sort_order", "id"]

    def __str__(self):
        return f"{self.title} ({self.get_method_display()})"


class PaymentMethod(models.Model):
    """
    طريقة دفع يراها الوكيل في قسم «إضافة رصيد»: بطاقة بصورة وعنوان،
    وعند فتحها شرحٌ وصندوق الحساب المنسوخ وحقولٌ يبنيها صاحب المتجر.
    """

    class Status(models.TextChoices):
        ACTIVE = "active", "نشط"
        PASSIVE = "passive", "معطّل"

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="payment_methods")
    name = models.CharField(max_length=120)                       # شركة تواصل دولار
    subtitle = models.CharField(max_length=160, blank=True, default="")  # سطر تحت الاسم
    logo_url = models.CharField(max_length=500, blank=True, default="")  # صورة البطاقة
    color = models.CharField(max_length=9, blank=True, default="")       # لون البطاقة البديل

    currency = models.CharField(max_length=8, choices=METHOD_CURRENCIES, default="TRY")
    instructions = models.TextField(blank=True, default="")       # الشرح (سطر لكل بند)
    account_box = models.TextField(blank=True, default="")        # الصندوق الأسود المنسوخ
    qr_url = models.CharField(max_length=500, blank=True, default="")  # صورة باركود الدفع (شام كاش…)
    warning = models.CharField(max_length=300, blank=True, default="")  # تنبيه فوق النموذج

    min_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    max_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))  # 0 = بلا حد
    commission_percent = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal("0"))

    # حساب الاستلام الذي تدخل إليه الأموال فعلياً (اختياري — لمتابعة أرصدتك)
    account = models.ForeignKey(
        ReceivingAccount, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="payment_methods",
    )

    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE)
    sort_order = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "payment_methods"
        ordering = ["sort_order", "id"]

    def __str__(self):
        return f"{self.name} ({self.currency})"


class PaymentMethodField(models.Model):
    """حقل يبنيه صاحب المتجر داخل طريقة دفع (اسم المُستلم · رقم العملية · ملاحظة…)."""

    class Kind(models.TextChoices):
        TEXT = "text", "نص قصير"
        NUMBER = "number", "رقم"
        TEXTAREA = "textarea", "نص طويل"
        SELECT = "select", "قائمة اختيار"
        IMAGE = "image", "صورة (رفع من الجهاز)"

    method = models.ForeignKey(PaymentMethod, on_delete=models.CASCADE, related_name="fields")
    label = models.CharField(max_length=160)                       # كتابة اسم المُستلم منك المبلغ
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.TEXT)
    options = models.CharField(max_length=500, blank=True, default="")  # خيارات القائمة، مفصولة بـ |
    placeholder = models.CharField(max_length=160, blank=True, default="")
    required = models.BooleanField(default=False)
    sort_order = models.IntegerField(default=0)

    class Meta:
        db_table = "payment_method_fields"
        ordering = ["sort_order", "id"]

    def __str__(self):
        return self.label


class PaymentNotification(models.Model):
    """
    طلب إضافة رصيد من وكيل: تحويل → طلب → قرار صاحب المتجر → إضافة الرصيد.
    القرار قابل للعكس لاحقاً (إبطال المقبول · قبول المرفوض) كطلبات الألعاب.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "قيد المراجعة"
        APPROVED = "approved", "مقبول"
        REJECTED = "rejected", "مرفوض"

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="payment_notifications")
    dealer = models.ForeignKey(User, on_delete=models.CASCADE, related_name="payment_notifications")
    account = models.ForeignKey(
        ReceivingAccount, null=True, blank=True, on_delete=models.SET_NULL, related_name="notifications"
    )
    method = models.ForeignKey(
        PaymentMethod, null=True, blank=True, on_delete=models.SET_NULL, related_name="requests"
    )

    # amount بعملة الطريقة · credit_amount بعملة محفظة الوكيل (بعد العمولة)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    currency = models.CharField(max_length=8, blank=True, default="")
    rate = models.DecimalField(max_digits=14, decimal_places=6, default=Decimal("1"))
    commission_percent = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal("0"))
    credit_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))

    values = models.JSONField(default=dict, blank=True)   # قيم الحقول المبنيّة {label: value}
    note = models.CharField(max_length=255, blank=True, default="")
    admin_note = models.CharField(max_length=255, blank=True, default="")  # سبب القبول أو الرفض

    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    approved_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    decided_at = models.DateTimeField(null=True, blank=True)
    balance_before = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    balance_after = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "payment_notifications"
        ordering = ["-created_at"]

    def __str__(self):
        return f"دفعة {self.amount} من {self.dealer.name} [{self.status}]"
