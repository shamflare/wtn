"""
نماذج الكتالوج: الألعاب (Oyunlar) + المنتجات (Ürünler/Pinler) + مجموعات الأسعار.
مبني على docs/DATABASE_SCHEMA.md (أقسام د + هـ).
"""
import uuid
from decimal import Decimal
from django.db import models

from core.models import Tenant


def _uuid_hex() -> str:
    return uuid.uuid4().hex


class ActiveManager(models.Manager):
    """
    المدير الافتراضي: يُخفي المؤرشف من كل استعلام (القوائم، المتجر، الأسعار…).

    لعبةٌ لها طلباتٌ سابقة لا تُحذف — الطلب يشير إليها (PROTECT) وعليها تقوم
    أسماؤه في السجلّ والتقارير. فتُؤرشف: تختفي من كل مكان، والطلبات القديمة
    تبلغها عبر العلاقة نفسها (`order.game`) لأن Django يستعمل لها المدير الأساسي
    لا هذا. وما احتاج المؤرشف صراحةً فله `all_objects`.
    """

    def get_queryset(self):
        return super().get_queryset().filter(is_archived=False)


class Game(models.Model):
    """لعبة (Oyun) — تحتها منتجات/بينات."""

    class Status(models.TextChoices):
        ACTIVE = "active", "نشط"
        PASSIVE = "passive", "معطّل"

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="games")
    name = models.CharField(max_length=120)
    image_url = models.CharField(max_length=300, blank=True, default="")
    dealer_note = models.CharField(max_length=255, blank=True, default="")  # Bayiye Açıklama
    description = models.TextField(blank=True, default="")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE)
    require_player_id = models.BooleanField(default=False)  # Zorunlu Oyuncu ID/GSM
    kurulu_sale = models.BooleanField(default=True)   # Kurulu Satış — بيع بالحزم المعرّفة
    toplu_sale = models.BooleanField(default=False)   # Toplu Satış — بيع بالكمية
    sms_template = models.TextField(blank=True, default="")  # Sms Şablonu
    sort_order = models.PositiveIntegerField(default=0)  # ترتيب العرض (drag & drop)
    # رابط منطقي بمنتج المكتبة العالمية الذي استُورد منه (نصّ، لمنع التكرار)
    master_library_uuid = models.CharField(
        max_length=64, blank=True, default="", db_index=True
    )
    is_archived = models.BooleanField(default=False, db_index=True)  # «حُذفت» ولها طلبات سابقة
    created_at = models.DateTimeField(auto_now_add=True)

    objects = ActiveManager()
    all_objects = models.Manager()

    class Meta:
        db_table = "games"
        ordering = ["sort_order", "id"]

    def __str__(self):
        return self.name


class PriceGroup(models.Model):
    """مجموعة أسعار (Fiyat Grubu) — كل وكيل ينتمي لمجموعة."""

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="price_groups")
    name = models.CharField(max_length=60)
    dollar_rate = models.DecimalField(max_digits=10, decimal_places=4, default=Decimal("1"))
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "price_groups"

    def __str__(self):
        return f"مجموعة {self.name}"


class AgentPriceGroup(models.Model):
    """
    مجموعة أسعار **يملكها وكيل كبير** لدكاكينه.

    صاحب المتجر يبيع الوكيل الكبير بسعر مجموعته عنده، ثم الكبير حرٌّ يبيع
    دكاكينه بما يشاء: ينشئ مجموعاته هو، ويسعّر فيها كل باقة، ويضع كل دكان في
    مجموعة. ربحه فرقُ السعرين، ويدخل محفظته لحظة الطلب.
    """

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="agent_price_groups")
    agent = models.ForeignKey(
        "core.User", on_delete=models.CASCADE, related_name="owned_price_groups"
    )
    name = models.CharField(max_length=60)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "agent_price_groups"
        constraints = [
            models.UniqueConstraint(fields=["agent", "name"], name="uniq_agent_group_name")
        ]
        ordering = ["id"]

    def __str__(self):
        return f"{self.agent.name} / {self.name}"


class AgentProductPrice(models.Model):
    """سعر باقة داخل مجموعة الوكيل الكبير — ما يدفعه دكانه فيها."""

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="agent_product_prices")
    group = models.ForeignKey(AgentPriceGroup, on_delete=models.CASCADE, related_name="prices")
    product = models.ForeignKey("catalog.Product", on_delete=models.CASCADE, related_name="agent_prices")
    price = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        db_table = "agent_product_prices"
        constraints = [
            models.UniqueConstraint(fields=["group", "product"], name="uniq_agent_group_product")
        ]

    def __str__(self):
        return f"{self.group} — {self.product_id} = {self.price}"


class Product(models.Model):
    """منتج داخل لعبة (60 UC, 300 UC …)."""

    class Status(models.TextChoices):
        ACTIVE = "active", "نشط"
        PASSIVE = "passive", "معطّل"
        SALE_PAUSED = "sale_paused", "بيع موقوف مؤقتاً"

    class Execution(models.TextChoices):
        MANUAL = "manual", "يدوي"
        AUTO = "auto", "تلقائي"

    class SaleType(models.TextChoices):
        PACKAGE = "package", "باقة ثابتة"
        AMOUNT = "amount", "بالكمية"

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="products")
    game = models.ForeignKey(Game, on_delete=models.CASCADE, related_name="products")
    name = models.CharField(max_length=120)
    cost_price = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))  # Maliyet
    recommended_price = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))  # Tavsiye
    kupur = models.CharField(max_length=60, blank=True, default="")
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.ACTIVE)
    is_parcali = models.BooleanField(default=False)  # يُقسّم لطلبات فرعية
    execution_type = models.CharField(max_length=8, choices=Execution.choices, default=Execution.AUTO)
    # التنفيذ التلقائي: المزوّد ومعرّف الباقة لديه (ZNET oyun / Barakat package_id / بنك بينات)
    provider = models.ForeignKey(
        "providers.Provider", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="products",
    )
    # التوجيه البديل: عند فشل الرئيسي يُجرَّب API 1 ثم API 2 تلقائياً
    provider_alt1 = models.ForeignKey(
        "providers.Provider", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="products_alt1",
    )
    provider_alt2 = models.ForeignKey(
        "providers.Provider", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="products_alt2",
    )
    provider_package_id = models.CharField(max_length=120, blank=True, default="")
    description = models.CharField(max_length=255, blank=True, default="")
    sort_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    # ── البيع بالكمية ──
    # الباقة الثابتة كميتها 1. والباقة «بالكمية» يكتب الوكيل كميتها بين الحدّين،
    # وأسعارها كلّها (التكلفة · الموصى · مجموعات الأسعار · سعر المزوّد على الربط)
    # **لكل `qty_unit` وحدة**: سعر الوحدة الواحدة كسورٌ دقيقة (0.003) لا تحملها
    # خانتا الأسعار العشريتان. فقيمة الطلب = السعر × الكمية ÷ qty_unit.
    sale_type = models.CharField(max_length=8, choices=SaleType.choices, default=SaleType.PACKAGE)
    qty_min = models.PositiveBigIntegerField(default=1)
    qty_max = models.PositiveBigIntegerField(default=1)
    qty_unit = models.PositiveBigIntegerField(default=1)

    is_archived = models.BooleanField(default=False, db_index=True)

    objects = ActiveManager()
    all_objects = models.Manager()

    class Meta:
        db_table = "products"
        ordering = ["sort_order", "id"]

    def __str__(self):
        return f"{self.game.name} — {self.name}"

    @property
    def profit(self) -> Decimal:
        """الربح المرجعي = السعر الموصى − التكلفة."""
        return self.recommended_price - self.cost_price

    @property
    def is_amount(self) -> bool:
        return self.sale_type == self.SaleType.AMOUNT

    def factor(self, quantity) -> Decimal:
        """مضاعف الأسعار لطلبٍ بهذه الكمية: 1 للباقة الثابتة، والكمية ÷ qty_unit للكمية."""
        if not self.is_amount:
            return Decimal("1")
        return Decimal(int(quantity)) / Decimal(self.qty_unit or 1)

    def block_price(self, raw):
        """سعرٌ للوحدة الواحدة من كتالوج مزوّد ⇐ سعرٌ لكل qty_unit (ما تحمله الحقول)."""
        try:
            value = Decimal(str(raw).replace(",", "."))
        except Exception:
            return None
        return value * Decimal(self.qty_unit or 1) if self.is_amount else value


class AgentMargin(models.Model):
    """هامش الوكيل الكبير على منتج (نسبته % فوق سعره لدكاكينه)."""

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="agent_margins")
    agent = models.ForeignKey(
        "core.User", on_delete=models.CASCADE, related_name="margins"
    )  # الوكيل الكبير
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="agent_margins")
    margin_percent = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal("0"))

    class Meta:
        db_table = "agent_margins"
        unique_together = ("agent", "product")

    def __str__(self):
        return f"{self.agent.name} +{self.margin_percent}% على {self.product.name}"


class ProductPrice(models.Model):
    """
    سعر منتج لمجموعة أسعار معيّنة (خلية في مصفوفة Fiyat Grupları).

    السعر إمّا **مرتبط بقاعدة** من التسعير الجماعي (تكلفة + نسبة أو مبلغ)
    فيتبع التكلفة كلّما تغيّرت، وإمّا **يدويّ** فيبقى كما كُتب. الحقلان أدناه
    هما ما يميّز الحالتين: فارغان = يدويّ.

    ينفكّ الارتباط بأمرين لا ثالث لهما: تسعير جماعي جديد يحلّ محلّه، أو
    تعديل يدويّ للخلية.
    """

    class Margin(models.TextChoices):
        PERCENT = "percent", "نسبة مئوية من التكلفة"
        FIXED = "fixed", "مبلغ ثابت فوق التكلفة"

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="product_prices")
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="group_prices")
    price_group = models.ForeignKey(PriceGroup, on_delete=models.CASCADE, related_name="prices")
    price = models.DecimalField(max_digits=12, decimal_places=2)  # سعر بالليرة لهذه المجموعة

    # قاعدة التسعير المرتبطة — فارغة تعني سعراً يدوياً لا يتبع التكلفة
    margin_mode = models.CharField(
        max_length=8, choices=Margin.choices, blank=True, default=""
    )
    margin_value = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    # تقريب الناتج لأعلى إلى رقم صحيح (0.94 ⇐ 1) — جزء من القاعدة فيبقى عند كل إعادة حساب
    margin_round = models.BooleanField(default=False)

    class Meta:
        db_table = "product_prices"
        unique_together = ("product", "price_group")

    def __str__(self):
        return f"{self.product.name} @ {self.price_group.name} = {self.price}"

    @property
    def linked(self) -> bool:
        """هل السعر مرتبط بالتكلفة بقاعدة؟"""
        return bool(self.margin_mode) and self.margin_value is not None


# ─────────── المكتبة العالمية (Global Library) — يحرّرها مالك المنصّة فقط ───────────
class LibrarySource(models.Model):
    """
    مصدرٌ تُملأ منه المكتبة: مزوّدٌ (ZDK كبركات) يُقرأ كتالوجه **ولا يُشترى منه**.

    مالك المنصّة يجلب الكتالوج، يختار الألعاب، فتُنشأ في المكتبة بباقاتها
    وأسعارها — ثم «مزامنة» تُظهر ما تغيّر عند المزوّد. وكل باقةٍ تحفظ رقمها
    لديه (`LibraryProduct.source_ref`): صاحب المتجر الذي يملك المزوّد نفسه
    تُربط باقاته به تلقائياً عند الاستيراد.

    أسعار المكتبة بالدولار؛ `usd_rate` = كم وحدةً من عملة المصدر تساوي دولاراً.
    """

    name = models.CharField(max_length=120)
    code = models.CharField(max_length=20, default="zdk")       # عائلة المحوّل
    config = models.JSONField(default=dict, blank=True)         # {base_url, api_token}
    currency = models.CharField(max_length=8, default="USD")
    usd_rate = models.DecimalField(max_digits=14, decimal_places=4, default=Decimal("1"))
    default_margin = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal("10"))
    last_synced_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "library_sources"
        ordering = ["id"]

    def __str__(self):
        return f"[Source] {self.name}"


class LibraryGame(models.Model):
    """قالب لعبة عالمي مشترك — يستطيع أي صاحب متجر استيراده مع باقاته."""

    uuid = models.CharField(max_length=64, unique=True, editable=False, default=_uuid_hex)
    name = models.CharField(max_length=120)
    image_url = models.CharField(max_length=300, blank=True, default="")
    description = models.TextField(blank=True, default="")
    require_player_id = models.BooleanField(default=True)   # الافتراض: يطلب معرّف اللاعب
    kurulu_sale = models.BooleanField(default=True)
    toplu_sale = models.BooleanField(default=False)
    sms_template = models.TextField(blank=True, default="")
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True, db_index=True)
    # من أين جاءت (فارغ = أُضيفت يدوياً) + اسم القسم لدى المصدر — به تُطابَق عند المزامنة
    source = models.ForeignKey(LibrarySource, null=True, blank=True,
                               on_delete=models.SET_NULL, related_name="games")
    source_key = models.CharField(max_length=200, blank=True, default="", db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "library_games"
        ordering = ["sort_order", "id"]

    def __str__(self):
        return f"[Library] {self.name}"


class LibraryProduct(models.Model):
    """باقة تحت لعبة عالمية (تُطابق Product عند الاستيراد)."""

    uuid = models.CharField(max_length=64, unique=True, editable=False, default=_uuid_hex)
    game = models.ForeignKey(LibraryGame, on_delete=models.CASCADE, related_name="products")
    name = models.CharField(max_length=120)
    suggested_cost = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    suggested_price = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    kupur = models.CharField(max_length=60, blank=True, default="")
    is_parcali = models.BooleanField(default=False)
    execution_type = models.CharField(
        max_length=8, choices=Product.Execution.choices, default=Product.Execution.AUTO
    )
    description = models.CharField(max_length=255, blank=True, default="")
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True, db_index=True)
    # رقم الباقة واسمها وسعرها لدى المصدر — للمزامنة وللربط التلقائي عند المتاجر
    source_ref = models.CharField(max_length=120, blank=True, default="", db_index=True)
    source_name = models.CharField(max_length=200, blank=True, default="")
    source_cost = models.DecimalField(max_digits=14, decimal_places=4, null=True, blank=True)
    # البيع بالكمية — كما في Product: الأسعار لكل qty_unit وحدة
    sale_type = models.CharField(max_length=8, choices=Product.SaleType.choices,
                                 default=Product.SaleType.PACKAGE)
    qty_min = models.PositiveBigIntegerField(default=1)
    qty_max = models.PositiveBigIntegerField(default=1)
    qty_unit = models.PositiveBigIntegerField(default=1)

    class Meta:
        db_table = "library_products"
        ordering = ["sort_order", "id"]

    def __str__(self):
        return f"[Library] {self.game.name} — {self.name}"


class ProductLink(models.Model):
    """
    رقم ربط الباقة لدى مزوّد بعينه.

    كل مزوّد يسمّي الباقة كما يشاء، لكن **رقم الربط** هو صلة الوصل. ولأن المنتج
    قد يُوجَّه إلى أكثر من مزوّد (رئيسي + بديلان)، يلزم رقم ربط **لكل مزوّد على
    حدة** — لا رقم واحد مشترك.

    `extra` يحمل ما يحتاجه المزوّد زيادةً على المعرّف؛ ZNET مثلاً يطلب
    `oyun` (معرّف اللعبة) **و** `kupur` (كود الكوبون) معاً.
    """

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="product_links")
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="links")
    provider = models.ForeignKey(
        "providers.Provider", on_delete=models.CASCADE, related_name="product_links"
    )
    package_id = models.CharField(max_length=120)          # المعرّف الأساسي لدى المزوّد
    package_name = models.CharField(max_length=200, blank=True, default="")  # اسمه هناك (للعرض)
    extra = models.JSONField(default=dict, blank=True)     # {"kupur": "...", ...}
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "product_links"
        constraints = [
            models.UniqueConstraint(
                fields=["product", "provider"], name="uniq_product_provider_link"
            )
        ]
        ordering = ["product_id", "provider_id"]

    def __str__(self):
        return f"{self.product} ← {self.provider}: {self.package_id}"


class ImageAsset(models.Model):
    """
    صورةٌ مرفوعة من جهاز المستخدم (صور المكتبة العالمية أوّلاً).

    تُحفظ في القاعدة لا على القرص: لا مجلّد وسائط في المشروع، والنسخة
    الاحتياطية الليلية للقاعدة تحملها معها. وتُقدَّم برابطٍ قصير ثابت
    (`/api/catalog/img/<key>/`) يُخزّنه المتصفّح سنةً — فلا تُحمَّل الصورة
    إلا مرّةً، ولا يثقل بها كتالوج الوكيل كما لو كانت نصّاً داخل كل لعبة.
    والصورة لا تتبدّل تحت رابطها أبداً: صورةٌ جديدة ⇐ مفتاحٌ جديد.
    """

    key = models.CharField(max_length=32, unique=True, default=_uuid_hex, editable=False)
    content_type = models.CharField(max_length=40)
    data = models.BinaryField()
    size = models.PositiveIntegerField()
    uploaded_by = models.ForeignKey(
        "core.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "image_assets"

    @property
    def url(self) -> str:
        return f"/api/catalog/img/{self.key}/"
