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
    # فارغٌ مسموح هنا ليصل إلى validate_name فيعيده إلى اسم ZNET (لا خطأ «لا يكون فارغاً»)
    name = serializers.CharField(max_length=160, allow_blank=True, trim_whitespace=True, required=False)
    operator_label = serializers.CharField(source="get_operator_display", read_only=True)
    category_name = serializers.CharField(source="category.name", read_only=True, default="")
    kind_label = serializers.CharField(source="get_kind_display", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    profit = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)

    class Meta:
        model = KontorPackage
        fields = [
            "id", "operator", "operator_label", "category", "category_name",
            "znet_id", "link_code", "name", "provider_name", "details", "days", "gb", "minutes",
            "provider_cost", "cost_price", "recommended_price", "profit",
            "kind", "kind_label", "status", "status_label",
            "provider", "provider_alt1", "provider_alt2", "provider_package_id",
            "sort_order", "updated_at",
        ]
        # المعرّف والكلفة والمشغّل يأتون من الاستيراد؛ المالك يملك الباقي
        read_only_fields = ["tenant", "operator", "znet_id", "provider_name", "provider_cost", "cost_price", "updated_at"]

    def validate_name(self, value):
        """الاسم شكليّ يسمّيه المالك كما يشاء — فارغٌ يعيده إلى اسم ZNET."""
        value = (value or "").strip()
        return value or (self.instance.provider_name if self.instance else value)

    def validate_link_code(self, value):
        """رقم الربط: حروف لاتينية وأرقام و - _ فقط، وفريد في المتجر."""
        import re
        value = (value or "").strip()
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,40}", value):
            raise serializers.ValidationError("رقم الربط: أرقام وحروف لاتينية و - _ فقط (حتى 40)")
        taken = KontorPackage.objects.filter(tenant=self.instance.tenant, link_code=value)             .exclude(pk=self.instance.pk).first()
        if taken:
            raise serializers.ValidationError(f"رقم الربط {value} مستعمل لباقة «{taken.name}»")
        return value


class KontorPriceGroupSerializer(serializers.ModelSerializer):
    dealer_count = serializers.SerializerMethodField()

    class Meta:
        model = KontorPriceGroup
        fields = ["id", "name", "dealer_count", "created_at"]
        read_only_fields = ["tenant", "created_at"]

    def get_dealer_count(self, obj):
        return obj.dealer_settings.values("dealer").distinct().count()
