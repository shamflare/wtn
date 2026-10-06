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
    # رقم الربط الذي يراه الوكيل ويرسله في الـ API — افتراضه رقم ZNET نفسه (فمن ربط
    # مع ZNET يبقى على أرقامه)، ويعدّله المالك. فريد في المتجر كله لا في الشركة وحدها.
    link_code = models.CharField(max_length=40, blank=True, default="", db_index=True)
    name = models.CharField(max_length=160)  # الاسم المعروض — يعدّله المالك كما يشاء
    # اسم الباقة كما في ZNET — يتحدّث مع كل استيراد. حين يطابق name فالاسم لم يُعدَّل
    # فيتبع ZNET؛ وحين يختلف فالمالك سمّاها بنفسه فلا يمسّه الاستيراد.
    provider_name = models.CharField(max_length=160, blank=True, default="")
    details = models.CharField(max_length=300, blank=True, default="")  # 30 Gün, 1000 Dk…

    # لفلاتر «المدة/الإنترنت/الدقائق» — تُملأ لاحقاً من صفحات اللوحة (0 = غير معروف)
    days = models.PositiveIntegerField(default=0)
    gb = models.PositiveIntegerField(default=0)
    minutes = models.PositiveIntegerField(default=0)

    # كلفة ZNET كما وصلت بعملته (الليرة) — المرجع الذي تُشتقّ منه cost_price
    provider_cost = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    # كل ما يلي بعملة دفتر المتجر (Tenant.base_currency) — كبقية المشروع، لا بالليرة
    cost_price = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))        # الكلفة محوّلة
    recommended_price = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))  # الموصى

    kind = models.CharField(max_length=8, choices=Kind.choices, default=Kind.GENERAL)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.ACTIVE)
    # أضافها المالك بيده (ليست من استيراد ZNET) — znet_id عندها معرّف داخلي M1، M2…
    # فلا يُرسَل إلى أي مزوّد إلا برقمها لديه في «التوجيه».
    is_manual = models.BooleanField(default=False)

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
            ),
            models.UniqueConstraint(
                fields=["tenant", "link_code"],
                condition=~models.Q(link_code=""),
                name="uniq_kontor_link_code",
            ),
        ]

    def __str__(self):
        return f"{self.get_operator_display()} · {self.name} ({self.znet_id})"

    @property
    def profit(self) -> Decimal:
        return self.recommended_price - self.cost_price


class KontorPackageLink(models.Model):
    """
    ربط باقة بمزوّد: رقمها لديه وكلفتها عنده (بعملته) — كربط باقات الألعاب.

    لكل مزوّد ZNET (لوحة) أرقامه؛ فالباقة نفسها قد تكون 732 هنا و1450 هناك.
    التنفيذ يرسل إلى كل مزوّد في سلسلة الباقة رقمَها **لديه**، ولا يرسل إلى مزوّد
    ليست مربوطة عنده — كي لا يُشحن رقمٌ بباقة غير المقصودة.
    """

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="kontor_links")
    package = models.ForeignKey(KontorPackage, on_delete=models.CASCADE, related_name="links")
    provider = models.ForeignKey("providers.Provider", on_delete=models.CASCADE, related_name="kontor_links")
    code = models.CharField(max_length=40)                    # رقم الباقة لدى هذا المزوّد (kontor=)
    cost = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))  # بعملة المزوّد
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "kontor_package_links"
        constraints = [
            models.UniqueConstraint(fields=["package", "provider"], name="uniq_kontor_package_link")
        ]

    def __str__(self):
        return f"{self.package.name} @ {self.provider.name} = {self.code}"


class KontorSessionConfig(models.Model):
    """
    حساب لوحة ZNET لكشف الشركة والعروض الخاصة — **على مستوى المنصّة** لا المتجر.

    يضبطه مالك المنصّة من /sorgula مرّةً فيخدم كل المتاجر (كل نسخة مبيعة).
    صفّ واحد (singleton). فارغٌ ⇐ تعود الخدمة إلى متغيّرات البيئة KONTOR_* كما كانت.
    """

    base_url = models.CharField(max_length=200, blank=True, default="")
    username = models.CharField(max_length=120, blank=True, default="")
    password = models.CharField(max_length=200, blank=True, default="")
    security_image = models.CharField(max_length=20, blank=True, default="D")
    enabled = models.BooleanField(default=True)
    last_ok_at = models.DateTimeField(null=True, blank=True)
    last_error = models.CharField(max_length=300, blank=True, default="")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "kontor_session_config"

    @classmethod
    def get(cls):
        obj = cls.objects.first()
        return obj if obj else cls.objects.create()

    @property
    def configured(self) -> bool:
        return bool(self.base_url and self.username and self.password)


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
    # الطلب ماضٍ مجمَّد: يحمل اسم الباقة وأرقامها ومبالغه وقت إنشائه، فحذف الباقة
    # لاحقاً أو تغيير اسمها أو كلفتها أو سعر الصرف لا يغيّر صفّه شيئاً.
    package = models.ForeignKey(
        KontorPackage, null=True, blank=True, on_delete=models.SET_NULL, related_name="orders")
    package_name = models.CharField(max_length=160, blank=True, default="")
    znet_id = models.CharField(max_length=40, blank=True, default="")
    link_code = models.CharField(max_length=40, blank=True, default="")
    operator = models.CharField(max_length=10, choices=Operator.choices)
    gsm = models.CharField(max_length=15)

    # المبالغ بعملة الموقع (الدفتر)
    cost_price = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    sell_price = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))  # ما دفعه الوكيل
    profit = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    # ما باع به الوكيل لزبونه (يكتبه أو يُؤخذ المقترح) وربحه هو — كالألعاب
    dealer_sell_price = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    dealer_profit = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))

    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING)
    provider = models.ForeignKey(
        "providers.Provider", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="kontor_orders",
    )
    tekil = models.CharField(max_length=40, blank=True, default="", db_index=True)  # معرّفنا الفريد لدى ZNET
    # معرّف العميل الخارجي (order_uuid) — يمنع الشحن المزدوج عند إعادة المحاولة عبر الـ API
    client_uuid = models.UUIDField(null=True, blank=True, db_index=True)
    provider_note = models.CharField(max_length=300, blank=True, default="")
    balance_before = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    balance_after = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "kontor_orders"
        ordering = ["-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["dealer", "client_uuid"],
                condition=models.Q(client_uuid__isnull=False),
                name="uniq_kontor_order_client_uuid_per_dealer",
            )
        ]

    def save(self, *args, **kwargs):
        # لقطة الباقة تُؤخذ مرّة عند الإنشاء ثم لا تتبعها
        if self.package_id and not self.package_name:
            p = self.package
            self.package_name, self.znet_id, self.link_code = p.name, p.znet_id, p.link_code
        super().save(*args, **kwargs)

    def __str__(self):
        return f"#{self.id} {self.gsm} · {self.package_name} [{self.status}]"
