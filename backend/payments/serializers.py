"""DRF serializers للمدفوعات."""
from rest_framework import serializers

from .models import PaymentMethod, PaymentMethodField, PaymentNotification, ReceivingAccount


class ReceivingAccountSerializer(serializers.ModelSerializer):
    method_label = serializers.CharField(source="get_method_display", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = ReceivingAccount
        fields = [
            "id", "method", "method_label", "title", "account_no", "balance",
            "status", "status_label", "notification_enabled", "sort_order",
        ]
        read_only_fields = ["tenant"]


class PaymentMethodFieldSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(required=False)
    kind_label = serializers.CharField(source="get_kind_display", read_only=True)

    class Meta:
        model = PaymentMethodField
        fields = [
            "id", "label", "kind", "kind_label", "options",
            "placeholder", "required", "sort_order",
        ]


class PaymentMethodSerializer(serializers.ModelSerializer):
    """طريقة دفع مع حقولها المبنيّة — الحقول تُكتب متداخلة في نفس الطلب."""
    fields_list = PaymentMethodFieldSerializer(source="fields", many=True, required=False)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    account_title = serializers.CharField(source="account.title", read_only=True, default="")
    request_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = PaymentMethod
        fields = [
            "id", "name", "subtitle", "logo_url", "color", "currency",
            "instructions", "account_box", "qr_url", "warning",
            "min_amount", "max_amount", "commission_percent",
            "account", "account_title", "status", "status_label", "sort_order",
            "fields_list", "request_count",
        ]
        read_only_fields = ["tenant"]

    def validate_commission_percent(self, v):
        # 100% أو أكثر يجعل الإيداع صفراً أو **خصماً** — لا عمولة كهذه
        if v is None or v < 0 or v >= 100:
            raise serializers.ValidationError("العمولة بين 0 وأقل من 100%")
        return v

    def validate_min_amount(self, v):
        if v is not None and v < 0:
            raise serializers.ValidationError("الحد الأدنى لا يكون سالباً")
        return v

    def validate_max_amount(self, v):
        if v is not None and v < 0:
            raise serializers.ValidationError("الحد الأعلى لا يكون سالباً")
        return v

    def _sync_fields(self, method, rows):
        """يستبدل حقول الطريقة بما أُرسل — الحذف والإضافة والترتيب في نداء واحد."""
        keep = []
        for i, row in enumerate(rows):
            row = dict(row)
            fid = row.pop("id", None)
            row.setdefault("sort_order", i)
            obj = None
            if fid:
                obj = PaymentMethodField.objects.filter(pk=fid, method=method).first()
            if obj:
                for k, v in row.items():
                    setattr(obj, k, v)
                obj.save()
            else:
                obj = PaymentMethodField.objects.create(method=method, **row)
            keep.append(obj.id)
        method.fields.exclude(id__in=keep).delete()

    def create(self, validated):
        rows = validated.pop("fields", None)
        method = super().create(validated)
        if rows is not None:
            self._sync_fields(method, rows)
        return method

    def update(self, instance, validated):
        rows = validated.pop("fields", None)
        method = super().update(instance, validated)
        if rows is not None:
            self._sync_fields(method, rows)
        return method


class PaymentNotificationSerializer(serializers.ModelSerializer):
    dealer_name = serializers.CharField(source="dealer.name", read_only=True)
    dealer_login = serializers.CharField(source="dealer.login_id", read_only=True)
    account_title = serializers.CharField(source="account.title", read_only=True, default="")
    method_name = serializers.CharField(source="method.name", read_only=True, default="")
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    created_at = serializers.DateTimeField(format="%Y-%m-%d %H:%M", read_only=True)
    decided_at = serializers.DateTimeField(format="%Y-%m-%d %H:%M", read_only=True)

    class Meta:
        model = PaymentNotification
        fields = [
            "id", "dealer", "dealer_name", "dealer_login", "account", "account_title",
            "method", "method_name", "amount", "currency", "rate", "commission_percent",
            "credit_amount", "values", "note", "admin_note",
            "status", "status_label", "balance_before", "balance_after",
            "created_at", "decided_at",
        ]
