from rest_framework import serializers

from .models import KontorCategory, KontorPackage, KontorPriceGroup


class KontorCategorySerializer(serializers.ModelSerializer):
    operator_label = serializers.CharField(source="get_operator_display", read_only=True)
    line_type_label = serializers.CharField(source="get_line_type_display", read_only=True)
    package_count = serializers.IntegerField(source="packages.count", read_only=True)

    class Meta:
        model = KontorCategory
        fields = [
            "id", "operator", "operator_label", "line_type", "line_type_label",
            "name", "logo_url", "is_query", "status", "sort_order", "package_count",
        ]
        read_only_fields = ["tenant", "operator", "line_type"]


class KontorPackageSerializer(serializers.ModelSerializer):
    operator_label = serializers.CharField(source="get_operator_display", read_only=True)
    category_name = serializers.CharField(source="category.name", read_only=True, default="")
    kind_label = serializers.CharField(source="get_kind_display", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    profit = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)

    class Meta:
        model = KontorPackage
        fields = [
            "id", "operator", "operator_label", "category", "category_name",
            "znet_id", "name", "details", "days", "gb", "minutes",
            "provider_cost", "cost_price", "recommended_price", "profit",
            "kind", "kind_label", "status", "status_label",
            "provider", "provider_alt1", "provider_alt2", "provider_package_id",
            "sort_order", "updated_at",
        ]
        # المعرّف والكلفة والمشغّل يأتون من الاستيراد؛ المالك يملك الباقي
        read_only_fields = ["tenant", "operator", "znet_id", "provider_cost", "cost_price", "updated_at"]


class KontorPriceGroupSerializer(serializers.ModelSerializer):
    dealer_count = serializers.SerializerMethodField()

    class Meta:
        model = KontorPriceGroup
        fields = ["id", "name", "dealer_count", "created_at"]
        read_only_fields = ["tenant", "created_at"]

    def get_dealer_count(self, obj):
        return obj.dealer_settings.values("dealer").distinct().count()
