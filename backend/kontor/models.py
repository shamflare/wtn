"""
شحن الخطوط التركية (Kontör) — نماذج الكتالوج.

البنية تحاكي الألعاب (catalog): فئة ⇐ باقات، مع توجيه كل باقة إلى مزوّد وبدائله.
مزوّدنا الفعلي الآن هو ZNET (عبر `tl_servis.php`)، وهو يوجّه داخلياً إلى مزوّديه؛
نُبقي حقول البدائل لفتح الباب لمزوّدين آخرين لاحقاً — كما في الألعاب.

التفاصيل الفنية ومصادر البيانات في `mobilecharge.md`.
"""
from decimal import Decimal

from django.db import models

from core.models import Tenant


class Operator(models.TextChoices):
    """شركة الخط. `Avea` هو الاسم الداخلي لـ Türk Telekom في ZNET."""
    TURKCELL = "Turkcell", "Turkcell"
    VODAFONE = "Vodafone", "Vodafone"
    AVEA = "Avea", "Türk Telekom"
    CALLBACK = "Callback", "دولي (Callback)"


class LineType(models.TextChoices):
    """نوع الباقة (Tür في ZNET) — عليه تقوم «الكرات»."""
    TAM = "Tam", "رصيد ليرة (TL)"
    SES = "Ses", "باقات"
    SMS = "Sms", "رسائل"
    CEP3G = "3gCep", "إنترنت"
    PC3G = "3gPc", "إنترنت واي‑فاي / PC"
    YDS = "Yds", "دولي"
    BIMCELL = "BimCell", "BiP (BimCell)"
    MTN = "Mtn", "MTN سوري"
    SYRIATEL = "Syriatel", "Syriatel سوري"


class KontorCategory(models.Model):
    """
    فئة (Kontor Kategorisi) = شركة + نوع، باسمٍ معروض وشعار وترتيب — هي «الكرة»
    التي تظهر بجانب حقل الرقم بعد كشف الشركة.
    """

    class Status(models.TextChoices):
        ACTIVE = "active", "نشط"
        PASSIVE = "passive", "معطّل"

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="kontor_categories")
    operator = models.CharField(max_length=10, choices=Operator.choices)
    line_type = models.CharField(max_length=10, choices=LineType.choices)
    name = models.CharField(max_length=120)                 # الاسم المعروض (عربي/تركي)
    logo_url = models.CharField(max_length=300, blank=True, default="")
    is_query = models.BooleanField(default=True)            # Sorgu — تُستعلَم ضمن العروض
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE)
    sort_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "kontor_categories"
        ordering = ["sort_order", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "operator", "line_type"],
                name="uniq_kontor_category",
            )
        ]

    def __str__(self):
        return f"{self.get_operator_display()} · {self.name}"


class KontorPackage(models.Model):
    """باقة واحدة داخل فئة (تطابق سطر `yukle_onay` / صفّ `paket_listesi`)."""

    class Status(models.TextChoices):
        ACTIVE = "active", "نشط"
        PASSIVE = "passive", "معطّل"
        SALE_PAUSED = "sale_paused", "بيع موقوف مؤقتاً"

    class Kind(models.TextChoices):
        GENERAL = "general", "عامة"       # تصلح لكل خطوط الشركة (أصفر)
        OFFER = "offer", "عرض"            # عرض مخفّض (Fırsat/İndirim — وردي)

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="kontor_packages")
    operator = models.CharField(max_length=10, choices=Operator.choices)
    category = models.ForeignKey(
        KontorCategory, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="packages",
    )
    # معرّف الباقة لدى ZNET (Küpür) — يُرسَل في `kontor=` إلى `tl_servis.php`
    znet_id = models.CharField(max_length=40)
    name = models.CharField(max_length=160)
    details = models.CharField(max_length=300, blank=True, default="")  # 30 Gün, 1000 Dk…

    # لفلاتر «المدة/الإنترنت/الدقائق» — تُملأ لاحقاً من صفحات اللوحة (0 = غير معروف)
    days = models.PositiveIntegerField(default=0)
    gb = models.PositiveIntegerField(default=0)
    minutes = models.PositiveIntegerField(default=0)

    cost_price = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))        # كلفة المزوّد
    recommended_price = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))  # الموصى

    kind = models.CharField(max_length=8, choices=Kind.choices, default=Kind.GENERAL)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.ACTIVE)

    # التوجيه: المزوّد الرئيسي ثم بدائله (كبدائل الألعاب)
    provider = models.ForeignKey(
        "providers.Provider", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="kontor_packages",
    )
    provider_alt1 = models.ForeignKey(
        "providers.Provider", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="kontor_packages_alt1",
    )
    provider_alt2 = models.ForeignKey(
        "providers.Provider", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="kontor_packages_alt2",
    )
    # معرّف الباقة لدى المزوّد إن اختلف عن znet_id (افتراضاً = znet_id)
    provider_package_id = models.CharField(max_length=60, blank=True, default="")

    sort_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "kontor_packages"
        ordering = ["operator", "sort_order", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "operator", "znet_id"],
                name="uniq_kontor_package",
            )
        ]

    def __str__(self):
        return f"{self.get_operator_display()} · {self.name} ({self.znet_id})"

    @property
    def profit(self) -> Decimal:
        return self.recommended_price - self.cost_price


class KontorPriceGroup(models.Model):
    """مجموعة أسعار للخطوط (Fiyat Grubu) — يُربط بها الوكيل لكل شركة."""

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="kontor_price_groups")
    name = models.CharField(max_length=60)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "kontor_price_groups"
        ordering = ["id"]

    def __str__(self):
        return self.name


class KontorPackagePrice(models.Model):
    """سعر بيع باقةٍ لمجموعة أسعار (خلية في مصفوفة الأسعار) — كنظيره في الألعاب."""

    class Margin(models.TextChoices):
        PERCENT = "percent", "نسبة مئوية من الكلفة"
        FIXED = "fixed", "مبلغ ثابت فوق الكلفة"

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="kontor_package_prices")
    package = models.ForeignKey(KontorPackage, on_delete=models.CASCADE, related_name="group_prices")
    group = models.ForeignKey(KontorPriceGroup, on_delete=models.CASCADE, related_name="prices")
    price = models.DecimalField(max_digits=12, decimal_places=2)

    # قاعدة مرتبطة بالكلفة — فارغة تعني سعراً يدوياً جامداً (كالألعاب)
    margin_mode = models.CharField(max_length=8, choices=Margin.choices, blank=True, default="")
    margin_value = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    margin_round = models.BooleanField(default=False)

    class Meta:
        db_table = "kontor_package_prices"
        constraints = [
            models.UniqueConstraint(fields=["package", "group"], name="uniq_kontor_package_price")
        ]

    def __str__(self):
        return f"{self.package.name} @ {self.group.name} = {self.price}"


class KontorDealerSetting(models.Model):
    """
    إعداد وكيل لشركةٍ معيّنة (Bayi Fiyat Ayarları + Paket Sorgu):
    مجموعة سعره لهذه الشركة، وهل يُسمح له باستعلام العروض الخاصة.
    """

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="kontor_dealer_settings")
    dealer = models.ForeignKey(
        "core.User", on_delete=models.CASCADE, related_name="kontor_settings"
    )
    operator = models.CharField(max_length=10, choices=Operator.choices)
    group = models.ForeignKey(
        KontorPriceGroup, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="dealer_settings",
    )
    can_query = models.BooleanField(default=True)  # إذن استعلام العروض لهذه الشركة

    class Meta:
        db_table = "kontor_dealer_settings"
        constraints = [
            models.UniqueConstraint(fields=["dealer", "operator"], name="uniq_kontor_dealer_operator")
        ]

    def __str__(self):
        return f"{self.dealer.name} · {self.operator}"


class KontorOrder(models.Model):
    """طلب شحن خطّ (Transfer Takip). القرار المالي عند الإنشاء؛ يُرجَع عند الفشل."""

    class Status(models.TextChoices):
        PENDING = "pending", "قيد الإرسال"
        PROCESSING = "processing", "قيد التنفيذ"
        SUCCESS = "success", "نجح"
        FAILED = "failed", "فشل"
        REFUNDED = "refunded", "مُسترجَع"

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="kontor_orders")
    dealer = models.ForeignKey("core.User", on_delete=models.PROTECT, related_name="kontor_orders")
    package = models.ForeignKey(KontorPackage, on_delete=models.PROTECT, related_name="orders")
    operator = models.CharField(max_length=10, choices=Operator.choices)
    gsm = models.CharField(max_length=15)

    # المبالغ بعملة الموقع (الدفتر)
    cost_price = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    sell_price = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))  # ما دفعه الوكيل
    profit = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))

    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING)
    provider = models.ForeignKey(
        "providers.Provider", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="kontor_orders",
    )
    tekil = models.CharField(max_length=40, blank=True, default="", db_index=True)  # معرّفنا الفريد لدى ZNET
    provider_note = models.CharField(max_length=300, blank=True, default="")
    balance_before = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    balance_after = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "kontor_orders"
        ordering = ["-id"]

    def __str__(self):
        return f"#{self.id} {self.gsm} · {self.package.name} [{self.status}]"
