"""DRF serializers للطلبات."""
from rest_framework import serializers

from .models import Order

# «عالق» حالةُ متجرٍ لا حالةُ وكيل: معناها أن توجيه صاحب المتجر تعثّر — إعدادٌ
# خاطئ أو مزوّد ساقط أو تسعير خاسر. والوكيل لا شأن له بذلك ولا حيلة له فيه،
# فيراها **انتظاراً**: طلبه لم يُحسم بعد، وهذا كل ما يعنيه الأمر بعينه.
# وتبقى «عالق» ظاهرةً في لوحة صاحب المتجر وحده — فهو من يعالجها.
# ما يراه الوكيل: «عالق» تعثّرٌ في توجيه صاحب المتجر لا شأن للوكيل به، و«قيد التنفيذ»
# و«قيد الانتظار» عنده معنىً واحد: لم يُحسم بعد. فكلاهما «قيد الانتظار».
DEALER_STATUS = {Order.Status.STUCK: Order.Status.PENDING,
                 Order.Status.PROCESSING: Order.Status.PENDING}


def dealer_filter(status: str) -> list:
    """الحالات الفعلية خلف حالةٍ يختارها الوكيل في فلتره."""
    return [s for s in Order.Status.values if DEALER_STATUS.get(s, s) == status] or [status]


class OrderSerializer(serializers.ModelSerializer):
    dealer_name = serializers.CharField(source="dealer.name", read_only=True)
    game_name = serializers.CharField(source="game.name", read_only=True)
    product_name = serializers.CharField(source="product.name", read_only=True)
    provider_name = serializers.CharField(source="provider.name", read_only=True, default="")
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    created_at = serializers.DateTimeField(format="%Y-%m-%d %H:%M", read_only=True)

    class Meta:
        model = Order
        fields = [
            "id", "receipt_no", "dealer", "dealer_name", "game_name",
            "product", "product_name", "quantity", "player_id", "customer_phone",
            "cost_price", "sell_price", "profit", "status", "status_label",
            "provider", "provider_name", "pin_result", "api_response",
            "provider_ref", "provider_note", "last_sync_at",
            "dealer_sell_price", "dealer_profit", "dealer_note",
            "balance_before", "balance_after", "created_at",
        ]


class StoreOrderSerializer(serializers.ModelSerializer):
    """
    الطلب **بمنظور الوكيل**: شراؤه هو ما دفعه فعلاً (`buyer_price`) — لصاحب
    المتجر إن كان مستقلاً، ولوكيله الكبير إن كان تابعاً — وبيعه هو ما باع به
    لزبونه. أرقام المالك (تكلفة المزوّد وربحه) واسم المزوّد وسجلّ التوجيه لا
    تخرج إلى لوحة الوكيل.
    """
    game_name = serializers.CharField(source="game.name", read_only=True)
    product_name = serializers.CharField(source="product.name", read_only=True)
    status = serializers.SerializerMethodField()
    status_label = serializers.SerializerMethodField()
    paid_price = serializers.DecimalField(
        source="buyer_price", max_digits=12, decimal_places=2, read_only=True
    )
    created_at = serializers.DateTimeField(format="%Y-%m-%d %H:%M", read_only=True)

    def get_status(self, o) -> str:
        return DEALER_STATUS.get(o.status, o.status)

    def get_status_label(self, o) -> str:
        return dict(Order.Status.choices)[self.get_status(o)]

    class Meta:
        model = Order
        fields = [
            "id", "receipt_no", "game_name", "product", "product_name", "quantity",
            "player_id", "customer_phone",
            "paid_price", "dealer_sell_price", "dealer_profit",
            "status", "status_label", "pin_result", "provider_note",
            # ملاحظة المشغّل على الطلب — سبب القبول أو الرفض اليدوي
            "dealer_note",
            "last_sync_at", "balance_before", "balance_after", "created_at",
        ]
