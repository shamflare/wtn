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
