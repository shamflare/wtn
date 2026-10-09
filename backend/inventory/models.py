"""
نماذج الجرد النهائي.

**المبدأ:** الجرد لقطةٌ لكل مالك في لحظة، والفرق بين لقطتين هو ربحك.

كل سطر في الجرد **مبلغ موقّع**: الموجب لنا والسالب علينا. فمحفظة وكيل رصيدها
+500 تدخل الجرد بـ‍−500، لأن ذلك المال قبضناه ولم نقدّم مقابله بعد — التزامٌ
لا أصل. وجمعُه أصلاً يضخّم رأس المال ضخّماً كاذباً، ويجعل كل شحنة رصيد يقوم
بها وكيلٌ تبدو ربحاً وهي ليست كذلك.

**ما يميّز جردنا عن نظام JRD:** هناك لزمت روبوتات وAPI لجلب كل رقم؛ وهنا
معظم الأرقام في قاعدتنا أصلاً — فالمصادر التلقائية تُقرأ لا تُجلَب. ولا يبقى
يدوياً إلا ما لا يعرفه النظام: صندوق نقد، دَينٌ شخصي، حوالة عند فلان.
"""
from decimal import Decimal

from django.db import models

from core.models import Tenant, User


class ManualItem(models.Model):
    """بند يدوي يضيفه صاحب المتجر — ما لا تعرفه القاعدة."""

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="inv_items")
    # صاحب الجرد: فارغ = المتجر، أو وكيلٌ كبير له جرده هو (core.User)
    owner = models.ForeignKey(User, null=True, blank=True, on_delete=models.CASCADE, related_name="+")
    name = models.CharField(max_length=120)
    amount = models.DecimalField(max_digits=16, decimal_places=2, default=Decimal("0"))
    currency = models.CharField(max_length=8, default="USD")
    note = models.CharField(max_length=200, blank=True, default="")
    sort_order = models.IntegerField(default=0)
    active = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "inventory_manual_items"
        ordering = ["sort_order", "id"]

    def __str__(self):
        return f"{self.name}: {self.amount} {self.currency}"


class InventoryConfig(models.Model):
    """
    أي المصادر التلقائية تدخل الجرد. القرار للمالك لا لنا: قد يرى أن أرصدة
    الوكلاء ليست من جرده، وقد يرى العكس — فالمفتاح بيده لا في الكود.
    """

    tenant = models.OneToOneField(Tenant, on_delete=models.CASCADE, related_name="inv_config")
    sources = models.JSONField(default=dict, blank=True)  # {"providers": true, …}
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "inventory_config"

    def enabled(self, key: str) -> bool:
        return bool((self.sources or {}).get(key, True))  # الافتراضي: مُفعَّل


class Snapshot(models.Model):
    """جرد محفوظ — لقطة كاملة لا تُمسّ بعد حفظها."""

    class Kind(models.TextChoices):
        DAILY = "daily", "يومي"
        MONTHLY = "monthly", "شهري"

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="inv_snapshots")
    # صاحب الجرد: فارغ = المتجر، أو وكيلٌ كبير له جرده هو (core.User)
    owner = models.ForeignKey(User, null=True, blank=True, on_delete=models.CASCADE, related_name="+")
    kind = models.CharField(max_length=8, choices=Kind.choices, default=Kind.DAILY)
    taken_at = models.DateTimeField(auto_now_add=True)
    base_currency = models.CharField(max_length=8, default="USD")
    # أسعار الصرف **لحظة الجرد** — تُحفظ لأن سعر اليوم ليس سعر الغد،
    # ولو أعدنا الحساب لاحقاً بسعرٍ آخر لتغيّر ربحٌ سبق أن أُقفل.
    rates = models.JSONField(default=dict, blank=True)

    total_base = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0"))
    assets_base = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0"))
    liabilities_base = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0"))

    previous = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    previous_total = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0"))
    profit = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0"))

    # للشهري: مجموع أرباح الجرود اليومية داخل الفترة، وعددها
    period_from = models.DateTimeField(null=True, blank=True)
    period_profit = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0"))
    daily_count = models.PositiveIntegerField(default=0)

    # شاهدٌ مستقلّ: ما تقوله دفاتر الطلبات عن ربح الفترة نفسها.
    # اختلافه عن `profit` ليس خطأً بالضرورة — لكنه سؤال يستحقّ أن يُطرح.
    orders_profit = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0"))
    orders_count = models.PositiveIntegerField(default=0)

    note = models.CharField(max_length=300, blank=True, default="")
    created_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        db_table = "inventory_snapshots"
        ordering = ["-taken_at", "-id"]

    def __str__(self):
        return f"جرد {self.get_kind_display()} {self.taken_at:%Y-%m-%d} = {self.total_base}"


class SnapshotLine(models.Model):
    """سطر داخل لقطة — يُحفظ بقيمته وعملته وسعر تحويله كما كانت."""

    snapshot = models.ForeignKey(Snapshot, on_delete=models.CASCADE, related_name="lines")
    group = models.CharField(max_length=32)      # providers · receiving · manual …
    group_label = models.CharField(max_length=80)
    name = models.CharField(max_length=160)
    amount = models.DecimalField(max_digits=16, decimal_places=2, default=Decimal("0"))
    currency = models.CharField(max_length=8, default="USD")
    base_amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0"))
    source = models.CharField(max_length=8, default="auto")  # auto | manual
    note = models.CharField(max_length=200, blank=True, default="")
    sort_order = models.IntegerField(default=0)

    class Meta:
        db_table = "inventory_snapshot_lines"
        ordering = ["sort_order", "id"]

    def __str__(self):
        return f"{self.name}: {self.amount} {self.currency}"
