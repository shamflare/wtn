"""
نماذج القلب (Core): المستأجرون، المستخدمون/الأدوار، المحفظة الموقّعة + دفتر الأستاذ.
مبني على docs/DATABASE_SCHEMA.md.
"""
from decimal import Decimal
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models

# كم يوماً قبل انتهاء الاشتراك يبدأ التنبيه
SUB_WARN_DAYS = 7

# محاولات الدخول الفاشلة قبل قفل الحساب. ثلاثٌ بقرار المالك (2026-08-16):
# تكفي لخطأٍ بشريّ في الكتابة، ولا تكفي لتخمينٍ آليّ.
LOGIN_ATTEMPTS_BEFORE_LOCK = 3


# حدود حجم العرض. أضيق من 75% يصير النصّ غير مقروء، وأوسع من 125% يخرج
# التصميم ذو العرض الثابت (1366px) عن الشاشة — وفي الحالين يتعذّر الرجوع.
UI_SCALE_MIN = 75
UI_SCALE_MAX = 125
UI_SCALE_DEFAULT = 100


# ─────────────────────────── المستأجرون (Platform) ───────────────────────────
class Tenant(models.Model):
    """مستأجر = وكيل اشترى النظام، له نطاق فرعي ولوحته الخاصة."""

    class Status(models.TextChoices):
        ACTIVE = "active", "نشط"
        SUSPENDED = "suspended", "موقوف"
        TRIAL = "trial", "تجريبي"

    name = models.CharField(max_length=120)
    subdomain = models.SlugField(max_length=63, unique=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.TRIAL)
    theme = models.CharField(max_length=20, default="teal")  # teal | blue | orange | custom
    font = models.CharField(max_length=20, default="cairo")  # cairo | tajawal
    theme_color = models.CharField(max_length=9, blank=True, default="")  # لون مخصّص #RRGGBB
    # حجم العرض بالمئة (75–125). التصميم مرسومٌ بالبكسل لا بالنسب، فلا يكفي
    # تكبير الخط وحده: يتباعد السطر ولا يكبر الزرّ معه، فينكسر الصفّ. ولذلك
    # رقمٌ واحد يُطبَّق بـ `zoom` على الجذر — يكبر كلُّ شيء معاً كما في زوم
    # المتصفّح: الخطوط والأزرار والحقول والتباعد.
    ui_scale = models.PositiveSmallIntegerField(default=100)
    # نصّاً: رابط خارجي أو `data:image/...` مرفوعاً من اللوحة. كان `CharField(300)`
    # فلا يسع صورةً مرفوعة، وكان صاحب المتجر يحتاج استضافةً خارجية لشعاره.
    logo_url = models.TextField(blank=True, default="")
    # السطر تحت الاسم في صفحة الدخول. فارغاً يعود إلى «نظام شحن الألعاب».
    tagline = models.CharField(max_length=120, blank=True, default="")
    # سطرٌ أسفل بطاقة الدخول — نصٌّ صِرف لا HTML: الصفحة مفتوحة بلا توكن،
    # وحقنُ وسمٍ فيها يصيب كل زائر. (`footer_html` يبقى للوحة الداخلية.)
    login_footer = models.CharField(max_length=200, blank=True, default="")
    # روابط التواصل: {"whatsapp": "+9055…", "telegram": "https://t.me/…", …}
    # قاموسٌ لا ثمانية أعمدة: إضافة منصّةٍ جديدة لا تستحقّ هجرةً في القاعدة.
    social_links = models.JSONField(default=dict, blank=True)
    default_locale = models.CharField(max_length=5, default="ar")
    # إعدادات الموقع (Web Site Ayarları)
    founded_year = models.CharField(max_length=8, blank=True, default="")   # Kuruluş Yılı
    short_name = models.CharField(max_length=60, blank=True, default="")    # Kısa İsim / Logo
    full_name = models.CharField(max_length=120, blank=True, default="")    # Tam İsim
    address = models.CharField(max_length=255, blank=True, default="")      # Adres
    email = models.CharField(max_length=120, blank=True, default="")        # E-Posta
    phone = models.CharField(max_length=40, blank=True, default="")         # Telefon
    homepage_text = models.TextField(blank=True, default="")                # Anasayfa Orta Metin
    footer_html = models.TextField(blank=True, default="")                  # Sayfa Altı Metin
    # إعدادات SMS (Sms Servisleri)
    sms_provider = models.CharField(max_length=60, blank=True, default="")
    sms_api_key = models.CharField(max_length=200, blank=True, default="")
    sms_sender = models.CharField(max_length=60, blank=True, default="")
    sms_enabled = models.BooleanField(default=False)
    # الاشتراك (يحدّده مالك المنصّة لكل متجر): سعر شهري/سنوي + الخطة الحالية ومدّتها
    class SubPlan(models.TextChoices):
        NONE = "none", "بلا اشتراك"
        MONTHLY = "monthly", "شهري"
        YEARLY = "yearly", "سنوي"

    # ── سعر الصرف العام للمتجر ──
    # base_currency = عملة محافظ الوكلاء. exchange_rates = {"USD": "41.50", …}
    # أي: كم وحدة من عملة المتجر تساوي وحدةً واحدة من تلك العملة.
    base_currency = models.CharField(max_length=8, default="USD")
    exchange_rates = models.JSONField(default=dict, blank=True)

    theme_config = models.JSONField(default=dict, blank=True)  # تخصيص المظهر (لوحة التخصيص)
    # ألوان واجهة الوكلاء (/store): {"primary": "#2fe27b", …} — ما لم يُذكر يبقى افتراضياً
    agent_theme = models.JSONField(default=dict, blank=True)
    sub_monthly_price = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0"))
    sub_yearly_price = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0"))
    sub_plan = models.CharField(max_length=8, choices=SubPlan.choices, default=SubPlan.NONE)
    sub_started_at = models.DateField(null=True, blank=True)
    sub_expires_at = models.DateField(null=True, blank=True)
    # أيام السماح بعد الانتهاء: يبقى فيها كل شيء يعمل والتنبيه أحمر. صفرٌ يعني
    # المنع يوم الانتهاء نفسه. يضبطها مالك المنصّة لكل متجر على حدة.
    sub_grace_days = models.PositiveSmallIntegerField(default=3)
    # مفتاح إعفاء: متجرٌ لا يُمنع مهما انتهى اشتراكه (شريك · تجربة ممتدّة ·
    # متجرك أنت). بدونه كان الإعفاء يتطلّب تمديداً وهمياً للتاريخ.
    sub_enforce = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "tenants"

    def __str__(self):
        return f"{self.name} ({self.subdomain})"

    # ————— حالة الاشتراك: مرجعٌ واحد يقرأ منه الجميع —————

    def subscription_state(self, today=None) -> str:
        """`ok` · `warn` (قارب) · `grace` (انتهى وفي السماح) · `blocked`."""
        from django.utils import timezone

        if not self.sub_enforce:
            return "ok"
        if self.sub_expires_at is None:
            # لم يُفعَّل اشتراك قطّ — متجرٌ جديد يُجرَّب، لا متجرٌ متخلّف عن الدفع
            return "ok"
        today = today or timezone.localdate()
        left = (self.sub_expires_at - today).days
        if left >= 0:
            return "warn" if left <= SUB_WARN_DAYS else "ok"
        return "grace" if -left <= self.sub_grace_days else "blocked"

    @property
    def purchases_blocked(self) -> bool:
        return self.subscription_state() == "blocked"


# ─────────────────────────── المستخدمون والأدوار ───────────────────────────
class UserManager(BaseUserManager):
    def create_user(self, login_id, password=None, **extra):
        if not login_id:
            raise ValueError("login_id مطلوب")
        user = self.model(login_id=login_id, **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, login_id, password=None, **extra):
        extra.setdefault("role", User.Role.PLATFORM_OWNER)
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        extra.setdefault("status", User.Status.ACTIVE)
        return self.create_user(login_id, password, **extra)


class User(AbstractBaseUser, PermissionsMixin):
    """مستخدم النظام عبر كل الأدوار (هرمية Ana Bayi → Bayi → Alt Bayi)."""

    class Role(models.TextChoices):
        PLATFORM_OWNER = "platform_owner", "مالك المنصّة"
        TENANT_ADMIN = "tenant_admin", "صاحب المتجر"
        ANA_BAYI = "ana_bayi", "وكيل كبير"
        BAYI = "bayi", "وكيل"

    class Status(models.TextChoices):
        ACTIVE = "active", "نشط"
        PASSIVE = "passive", "معطّل"
        BLACKLISTED = "blacklisted", "قائمة سوداء"

    tenant = models.ForeignKey(
        Tenant, null=True, blank=True, on_delete=models.CASCADE, related_name="users"
    )  # null = مستخدم منصّة (سوبر أدمن)
    parent = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="children"
    )
    role = models.CharField(max_length=16, choices=Role.choices, default=Role.BAYI)

    login_id = models.CharField(max_length=32, unique=True)  # رقم الدخول (5550000007)
    # الرقم المعروض في «قائمة الوكلاء»: تسلسلي داخل المتجر يبدأ من 1.
    # مستقلّ عن login_id لأن الأخير فريد عبر المتاجر كلّها فلا يصلح تسلسلاً محلياً.
    dealer_no = models.PositiveIntegerField(null=True, blank=True, db_index=True)
    name = models.CharField(max_length=120)
    phone = models.CharField(max_length=20, blank=True, default="")

    totp_secret = models.CharField(max_length=64, blank=True, default="")  # مفتاح 2FA
    totp_enabled = models.BooleanField(default=False)

    country = models.CharField(max_length=2, default="SY")
    province = models.CharField(max_length=80, blank=True, default="")  # المحافظة
    foreign_ip_allowed = models.BooleanField(default=False)  # Bayi Yurt Dışı Ip İzin
    # وثائق الوكيل — تُحفظ كـ data URL داخل القاعدة لا كملفّات على القرص،
    # لأن قرص الاستضافة مؤقّت ويُمسح مع كل نشر. اختيارية دائماً.
    id_image = models.TextField(blank=True, default="")     # صورة الهوية
    shop_image = models.TextField(blank=True, default="")   # صورة لوحة المحل
    # موافقة الوكيل على تحصيل دَينه آلياً — عليها يُفلتر الإرسال الجماعي بواتساب
    auto_debt_collection = models.BooleanField(default=False)
    # إذن الربط الخارجي (API): مغلق افتراضياً بقرار المالك (2026-08-15).
    # الـ API لا يمنح الوكيل صلاحيةً جديدة — يستطيع الطلب من لوحته أصلاً — لكنه
    # يجعل إعادة البيع بالجملة **آليةً بلا كلفة**، فقرارُ فتحه تجاريّ لا تقنيّ
    # ومكانه يد صاحب المتجر. مغلقاً: لا يبدأ أحدٌ ذلك قبل أن يعلم.
    api_access_allowed = models.BooleanField(default=False)
    # إذن صريح بأن يُستعمل هذا الحساب من متجر آخر على المنصّة كـ«مزوّد داخلي».
    # مطفأ افتراضياً: رقم الدخول فريد عبر المنصّة كلّها وسهل التخمين، فبدون هذا
    # الإذن كان أي صاحب متجر يوجّه طلباته إلى محفظة وكيل ليس له وينفق رصيده.
    internal_supply_allowed = models.BooleanField(default=False)
    # رقم واتساب مطبَّعاً: أرقام فقط برمز الدولة بلا + ولا صفر بادئ (905551234567).
    # يُطبَّع عند الحفظ لا عند الإرسال — انظر whatsapp/phone.py
    whatsapp = models.CharField(max_length=24, blank=True, default="")
    oyun_load_limit = models.DecimalField(  # Bayi Oyun Yükleme Limiti
        max_digits=12, decimal_places=2, default=Decimal("10000")
    )
    price_group = models.ForeignKey(  # مجموعة أسعار الوكيل (Fiyat Grubu)
        "catalog.PriceGroup", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="dealers",
    )
    # مجموعة أسعار **وكيله الكبير** — بها يشتري الدكان من وكيله لا من المتجر.
    # فارغة تعني أن الكبير لم يسعّر له بعد (انظر orders.services.resolve_sell_price).
    agent_price_group = models.ForeignKey(
        "catalog.AgentPriceGroup", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="dealers",
    )
    # عملة العرض في لوحة الوكيل — فارغة تعني عملة الموقع.
    # عرضٌ فقط: الدفتر كلّه يبقى بعملة الموقع (انظر core/currency.py).
    display_currency = models.CharField(max_length=8, blank=True, default="")

    status = models.CharField(max_length=12, choices=Status.choices, default=Status.ACTIVE)
    modules = models.JSONField(default=dict, blank=True)  # تفعيل الموديولات (النقاط الملوّنة)
    failed_login_count = models.PositiveIntegerField(default=0)
    # لحظة القفل بعد استنفاد المحاولات. كان العدّاد يُعدّ ولا يُقرأ أبداً، أي
    # أن تخمين كلمات السرّ آلياً كان مفتوحاً بلا حدّ على حساباتٍ تملك محافظ.
    locked_at = models.DateTimeField(null=True, blank=True)

    @property
    def is_locked(self) -> bool:
        return self.locked_at is not None

    def unlock(self) -> None:
        """يفتح القفل ويصفّر العدّاد — يصاحب دائماً كلمةَ سرّ جديدة."""
        self.locked_at = None
        self.failed_login_count = 0
        self.save(update_fields=["locked_at", "failed_login_count"])

    is_staff = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = UserManager()

    USERNAME_FIELD = "login_id"
    REQUIRED_FIELDS = ["name"]

    class Meta:
        db_table = "users"

    def __str__(self):
        return f"{self.name} #{self.login_id} [{self.role}]"


# ─────────────────────────── المحفظة (رصيد موقّع) ───────────────────────────
class Wallet(models.Model):
    """رصيد واحد موقّع (±). السالب = دين. مع حد ائتماني (Kredi Limiti)."""

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="wallets")
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="wallet")
    balance = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    credit_limit = models.DecimalField(  # أقصى قيمة سالبة مسموحة (مثال -500)
        max_digits=14, decimal_places=2, default=Decimal("0")
    )
    currency = models.CharField(max_length=8, default="TRY")

    class Meta:
        db_table = "wallets"

    def __str__(self):
        return f"محفظة {self.user.name}: {self.balance} {self.currency}"

    @property
    def available(self) -> Decimal:
        """المتاح للصرف = الرصيد − حد الائتمان (كم يقدر ينزل تحته)."""
        return self.balance - self.credit_limit


class WalletTransaction(models.Model):
    """دفتر الأستاذ (Ledger) — كل حركة تسجّل before/after للتدقيق."""

    class Type(models.TextChoices):
        TOPUP = "topup", "شحن"
        ORDER_DEBIT = "order_debit", "خصم طلب"
        REFUND = "refund", "استرجاع"
        MANUAL_CREDIT = "manual_credit", "إضافة يدوية"
        MANUAL_DEBIT = "manual_debit", "خصم يدوي"
        ADJUSTMENT = "adjustment", "تسوية"

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="wallet_txns")
    wallet = models.ForeignKey(Wallet, on_delete=models.CASCADE, related_name="transactions")
    type = models.CharField(max_length=16, choices=Type.choices)
    amount = models.DecimalField(max_digits=14, decimal_places=2)  # ± موقّع
    balance_before = models.DecimalField(max_digits=14, decimal_places=2)
    balance_after = models.DecimalField(max_digits=14, decimal_places=2)
    ref_type = models.CharField(max_length=20, blank=True, default="")
    ref_id = models.BigIntegerField(null=True, blank=True)
    note = models.CharField(max_length=255, blank=True, default="")
    created_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "wallet_transactions"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.type} {self.amount} → {self.balance_after}"


# ─────────────────────────── إعلان المنصّة (المبرمج → أصحاب المتاجر) ───────────────────────────
class PlatformAnnouncement(models.Model):
    """إعلان عام يكتبه مالك المنصّة ويظهر فوق هيدر لوحات أصحاب المتاجر.
    صفّ واحد فقط (singleton) — message للشريط الثابت، ticker للشريط العاجل المتحرّك."""

    message = models.TextField(blank=True, default="")
    ticker = models.TextField(blank=True, default="")  # عناصر مفصولة بأسطر
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "platform_announcement"

    @classmethod
    def get(cls):
        obj = cls.objects.first()
        return obj if obj else cls.objects.create()

    def __str__(self):
        return f"إعلان المنصّة ({self.updated_at:%Y-%m-%d})"


# ─────────────────────────── التذاكر / الرسائل ───────────────────────────
class Ticket(models.Model):
    """تذكرة دعم/رسالة: من مستخدم إلى إدارة متجره أو إلى مالك المنصّة."""

    class Target(models.TextChoices):
        ADMIN = "admin", "إدارة المتجر"       # وكيل → صاحب المتجر
        PLATFORM = "platform", "مالك المنصّة"  # صاحب المتجر → المنصّة
        DEALER = "dealer", "وكيل"             # صاحب المتجر → وكيلٍ بعينه

    class Status(models.TextChoices):
        OPEN = "open", "مفتوحة"
        CLOSED = "closed", "مغلقة"

    tenant = models.ForeignKey(Tenant, null=True, blank=True, on_delete=models.CASCADE, related_name="tickets")
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name="tickets")
    target = models.CharField(max_length=10, choices=Target.choices, default=Target.ADMIN)
    # المخاطَب المعيَّن — لوجهة `dealer` وحدها. وبدونه كانت التذاكر تصعد
    # دائماً: يردّ صاحب المتجر على من راسله، ولا يبدأ هو رسالةً إلى وكيل.
    recipient = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.CASCADE, related_name="incoming_tickets",
    )
    subject = models.CharField(max_length=200)
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.OPEN)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "tickets"
        ordering = ["-updated_at"]

    def __str__(self):
        return f"[{self.get_target_display()}] {self.subject}"


class TicketMessage(models.Model):
    """رسالة داخل تذكرة."""

    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name="messages")
    sender = models.ForeignKey(User, on_delete=models.CASCADE, related_name="ticket_messages")
    body = models.TextField()
    read_by_other = models.BooleanField(default=False)  # هل قرأها الطرف الآخر؟
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "ticket_messages"
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.sender.name}: {self.body[:30]}"


# ─────────────────────────── الفوترة (المنصّة ↔ المستأجرون) ───────────────────────────
class Invoice(models.Model):
    """فاتورة اشتراك يصدرها مالك المنصّة لمستأجر عند التفعيل/التجديد."""

    class Status(models.TextChoices):
        UNPAID = "unpaid", "غير مدفوعة"
        PAID = "paid", "مدفوعة"

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="invoices")
    plan = models.CharField(max_length=8)  # monthly | yearly
    amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0"))
    period_start = models.DateField()
    period_end = models.DateField()
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.UNPAID)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "invoices"
        ordering = ["-created_at"]

    def __str__(self):
        return f"فاتورة {self.tenant.name} — {self.amount}"


# ─────────────────────────── بطاقات اللوحة الرئيسية ───────────────────────────
class HomeCard(models.Model):
    """
    بطاقة تظهر في الصفحة الرئيسية لمن هم **تحتك** في السلسلة.

    مالك المنصّة يكتب بطاقات يراها أصحاب المتاجر، وصاحب المتجر يكتب بطاقات
    يراها وكلاؤه. نموذج واحد لأن السلوك واحد؛ ما يتغيّر هو من يكتب ومن يقرأ.

    الألوان تُحفظ على البطاقة نفسها لا في سمة عامّة: البطاقة إعلانٌ يُقصد به
    أن يُلفت، وتنبيهٌ أحمر وترحيبٌ هادئ لا يجمعهما لون واحد.
    """

    class Audience(models.TextChoices):
        # يكتبها مالك المنصّة ← يراها أصحاب المتاجر (tenant فارغ = للجميع)
        TENANTS = "tenants", "أصحاب المتاجر"
        # يكتبها صاحب المتجر ← يراها وكلاؤه
        DEALERS = "dealers", "الوكلاء"

    audience = models.CharField(max_length=8, choices=Audience.choices)
    # كاتب البطاقة: فارغ = مالك المنصّة. ولجمهور `tenants` يجوز تحديد متجر
    # بعينه فتصله وحده — إعلانٌ خاصّ لا عامّ.
    tenant = models.ForeignKey(
        Tenant, null=True, blank=True, on_delete=models.CASCADE, related_name="home_cards"
    )
    target_tenant = models.ForeignKey(
        Tenant, null=True, blank=True, on_delete=models.CASCADE, related_name="targeted_cards"
    )

    title = models.CharField(max_length=120)
    body = models.TextField(blank=True, default="")
    icon = models.CharField(max_length=24, blank=True, default="bell")

    bg_color = models.CharField(max_length=24, default="#0f766e")
    bg_color2 = models.CharField(max_length=24, blank=True, default="")  # تدرّج اختياري
    text_color = models.CharField(max_length=24, default="#ffffff")

    link_url = models.CharField(max_length=300, blank=True, default="")
    link_label = models.CharField(max_length=60, blank=True, default="")

    sort_order = models.PositiveIntegerField(default=0)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "home_cards"
        ordering = ["sort_order", "id"]


class HomeCardRead(models.Model):
    """
    أثرُ أن فلاناً رأى هذه البطاقة.

    صفٌّ لكل (قارئ، بطاقة) لا ختمُ وقتٍ واحد على المستخدم: البطاقات تُحرَّر
    وتُعاد ترتيباً، فختمٌ واحد يجعل تحريرَ بطاقةٍ قديمة يُشعل الجرس لبطاقات
    قُرئت كلُّها. وحذفُ البطاقة يمحو أثرها معها (`CASCADE`).
    """

    card = models.ForeignKey(HomeCard, on_delete=models.CASCADE, related_name="reads")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="card_reads")
    read_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "home_card_reads"
        constraints = [
            models.UniqueConstraint(fields=["card", "user"], name="uniq_card_read"),
        ]

    def __str__(self):
        return f"{self.user.name} ← {self.card.title}"

    def __str__(self):
        return f"بطاقة {self.get_audience_display()}: {self.title}"
