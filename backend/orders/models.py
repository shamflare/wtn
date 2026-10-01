"""
نماذج الطلبات (Takip): طلب شحن لعبة من وكيل، يُنفَّذ عبر مزوّد.
مبني على docs/DATABASE_SCHEMA.md (قسم و).
"""
from decimal import Decimal
from django.db import models

from core.models import Tenant, User
from catalog.models import Game, Product
from providers.models import Provider


class Order(models.Model):
    """طلب شحن (Oyun-Pin Takip)."""

    class Status(models.TextChoices):
        PENDING = "pending", "قيد الانتظار"
        PROCESSING = "processing", "قيد التنفيذ"
        SUCCESS = "success", "ناجح"
        CANCELLED = "cancelled", "ملغى"
        STUCK = "stuck", "عالق"

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="orders")
    receipt_no = models.CharField(max_length=20, unique=True)  # Fiş No
    dealer = models.ForeignKey(User, on_delete=models.PROTECT, related_name="orders")
    game = models.ForeignKey(Game, on_delete=models.PROTECT, related_name="orders")
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="orders")

    player_id = models.CharField(max_length=60, blank=True, default="")     # Oyuncu ID
    # الكمية: 1 للباقة الثابتة، وما كتبه الوكيل للباقة «بالكمية». أسعار الطلب كلّها
    # محسوبةٌ بها سلفاً (product.factor) — فما يُخزَّن هنا للعرض وللمزوّد.
    quantity = models.PositiveBigIntegerField(default=1)
    customer_phone = models.CharField(max_length=20, blank=True, default="")  # Müşteri Tel

    # أرقام **صاحب المتجر**: ما دفعه للمزوّد، وما قبضه فعلاً، وربحه هو.
    # مع وكيل كبير وسيط يبقى `sell_price` ما قبضه المتجر **من الكبير** لا ما دفعه
    # الدكان — وإلّا تضخّمت إيرادات المتجر بربح الوكيل في كل تقرير.
    cost_price = models.DecimalField(max_digits=12, decimal_places=2)   # Alış
    sell_price = models.DecimalField(max_digits=12, decimal_places=2)   # Satış
    profit = models.DecimalField(max_digits=12, decimal_places=2)       # Kazanç

    # الوسيط: وكيل كبير اشترى من المتجر وباع لدكانه. فارغ = لا وسيط.
    agent = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.PROTECT, related_name="agent_orders"
    )
    # ما دفعه المشتري فعلاً: يساوي sell_price بلا وسيط، ويزيد عنه بربح الوسيط.
    buyer_price = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    agent_profit = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))

    # أرقام **الوكيل**: بكم باع لزبونه وكم ربح. شراؤه هو `buyer_price` أعلاه.
    # سعر التوصية تخمين من صاحب المتجر، والوكيل قد يبيع أغلى أو أرخص — لذا
    # يُثبَّت السعر الفعلي وقت البيع ولا يُشتقّ لاحقاً من المنتج.
    dealer_sell_price = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    dealer_profit = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))

    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING)
    provider = models.ForeignKey(
        Provider, null=True, blank=True, on_delete=models.SET_NULL, related_name="orders"
    )
    pin_result = models.CharField(max_length=255, blank=True, default="")   # PIN المسلّم
    api_response = models.CharField(max_length=255, blank=True, default="")  # رد الـ API
    # متابعة الطلب لدى المزوّد بعد إرساله (حلقة المراقبة)
    provider_ref = models.CharField(max_length=120, blank=True, default="")   # referans لدى المزوّد
    provider_note = models.CharField(max_length=255, blank=True, default="")  # ملاحظة/رسالة المزوّد
    last_sync_at = models.DateTimeField(null=True, blank=True)                # آخر استعلام حالة
    dealer_note = models.CharField(max_length=255, blank=True, default="")

    balance_before = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    balance_after = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))

    # `order_uuid` الذي يرسله عميل الواجهة الخارجية — **مفتاح منع التكرار**.
    # الشبكة تنقطع بعد أن نشحن وقبل أن يصله الردّ، فيعيد المحاولة. بدون هذا
    # المفتاح يُشحن اللاعب مرّتين ويُخصم الوكيل مرّتين. القيد أدناه يجعل التكرار
    # مستحيلاً في القاعدة نفسها لا في الكود وحده — فلا يفلت من سباق التزامن.
    # فارغ لطلبات اللوحة والمتجر (لا واجهة خارجية فيها).
    client_uuid = models.UUIDField(null=True, blank=True, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True)   # İşlem Tarihi
    approved_at = models.DateTimeField(null=True, blank=True)  # Onay Tarihi

    class Meta:
        db_table = "orders"
        ordering = ["-created_at"]
        constraints = [
            # النطاق **الوكيل** لا المتجر: المعرّف يخترعه العميل الخارجي لنفسه،
            # فلو كان النطاق المتجر لاصطدم وكيلان بمعرّف واحد — والأسوأ أن
            # الثاني كان سيتلقّى طلب الأوّل جواباً فيرى بيانات ليست له.
            models.UniqueConstraint(
                fields=["dealer", "client_uuid"],
                condition=models.Q(client_uuid__isnull=False),
                name="uniq_order_client_uuid_per_dealer",
            ),
        ]

    def __str__(self):
        return f"طلب {self.receipt_no} — {self.product.name} [{self.status}]"
