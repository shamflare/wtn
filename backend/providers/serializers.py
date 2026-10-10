"""DRF serializers للمزوّدين."""
from rest_framework import serializers

from .models import Provider

# تسميات العرض حسب config.code — تميّز البرمجية التي يعمل بها المزوّد الخارجي
# (ZNET / ZDK) عن نوعه التخزيني العام (card_store).
# `barakat` و`apstore` متجران على برمجية ZDK — يُعرضان بها لا باسميهما، فاسم
# المتجر نفسه محفوظ في حقل `name`.
KIND_LABELS = {
    "znet": "ZNET",
    "zdk": "ZDK",
    "barakat": "ZDK",
    "apstore": "ZDK",
}


class ProviderSerializer(serializers.ModelSerializer):
    type_label = serializers.SerializerMethodField()
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    # الأرقام محفوظة **بعملة المزوّد** كما ردّها. ويرافقها مقابلُها بعملة
    # الدفتر محسوباً هنا لا في المتصفّح — سعر الصرف مرجعٌ واحد على الخادم،
    # وحسابُه في الواجهة يكرّره ويجعله يختلف بين شاشة وأخرى.
    base_currency = serializers.SerializerMethodField()
    # `currency` هو الحقل المحفوظ (يُكتب من النافذة)، و`shown_currency` هو
    # المعروض فعلاً: يساوي عملة الدفتر لمن لا يسعّر بعملته — بنكِ الأكواد
    # والمنفّذ اليدوي والمتجر الداخلي — فلا يُكتب «₺» تحت بنك أكوادٍ محلّي.
    shown_currency = serializers.SerializerMethodField()
    # وبها تعرف الواجهة متى تُظهر قائمة اختيار العملة أصلاً
    has_own_currency = serializers.BooleanField(
        source="prices_in_own_currency", read_only=True
    )
    real_balance_base = serializers.SerializerMethodField()
    balance_base = serializers.SerializerMethodField()
    debt_base = serializers.SerializerMethodField()

    class Meta:
        model = Provider
        fields = [
            "id", "name", "type", "type_label", "config", "status", "status_label",
            "currency", "shown_currency", "base_currency", "has_own_currency",
            "real_balance", "balance", "debt",
            "real_balance_base", "balance_base", "debt_base",
            "loss_guard", "auto_update",
            "balance_alert_threshold", "sort_order", "created_at",
        ]
        read_only_fields = ["tenant", "created_at"]

    def validate_config(self, config):
        """رابط المزوّد عنوانٌ عامّ على الإنترنت — لا داخلي (core/netguard.py)."""
        from core import netguard
        base = str((config or {}).get("base_url") or "").strip()
        if base:
            try:
                netguard.check(base)
            except netguard.UnsafeURL as e:
                raise serializers.ValidationError(f"رابط المزوّد: {e}")
        return config

    def _base(self, obj, value):
        """None = لا سعر صرف مضبوط لهذه العملة — تقولها الواجهة صراحةً."""
        from core import currency as cur

        if cur.currency_of(obj) == cur.base_currency(obj.tenant):
            return None          # لا معنى لسطرٍ ثانٍ يكرّر الرقم نفسه
        converted = cur.to_base(obj.tenant, value, cur.currency_of(obj))
        return str(converted) if converted is not None else None

    def get_base_currency(self, obj) -> str:
        from core import currency as cur

        return cur.base_currency(obj.tenant)

    def get_shown_currency(self, obj) -> str:
        from core import currency as cur

        return cur.currency_of(obj)

    def get_real_balance_base(self, obj):
        return self._base(obj, obj.real_balance)

    def get_balance_base(self, obj):
        return self._base(obj, obj.balance)

    def get_debt_base(self, obj):
        return self._base(obj, obj.debt)

    def get_type_label(self, obj) -> str:
        code = ((obj.config or {}).get("code") or "").lower()
        return KIND_LABELS.get(code) or obj.get_type_display()
