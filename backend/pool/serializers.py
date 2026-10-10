"""DRF serializers لبنك البينات."""
from rest_framework import serializers

from core.tenancy import SameTenantFields

from .models import PinPool


class PinPoolSerializer(SameTenantFields, serializers.ModelSerializer):
    tenant_fields = ("provider",)

    provider_name = serializers.CharField(source="provider.name", read_only=True, default="")
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    created_at = serializers.DateTimeField(format="%Y-%m-%d %H:%M", read_only=True)
    total_cost = serializers.SerializerMethodField()
    pin_count = serializers.SerializerMethodField()
    available_count = serializers.SerializerMethodField()

    class Meta:
        model = PinPool
        fields = [
            "id", "name", "description", "provider", "provider_name",
            "status", "status_label", "created_at",
            "total_cost", "pin_count", "available_count",
        ]
        read_only_fields = ["tenant", "created_at"]

    def get_total_cost(self, obj):
        return str(sum((p.cost for p in obj.pins.all()), start=0))

    def get_pin_count(self, obj):
        return obj.pins.count()

    def get_available_count(self, obj):
        return obj.pins.filter(status="available").count()
