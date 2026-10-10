"""DRF serializers للكتالوج."""
from rest_framework import serializers

from core.tenancy import SameTenantFields

from .models import Game, LibraryGame, LibraryProduct, PriceGroup, Product


class PriceGroupSerializer(serializers.ModelSerializer):
    # عدد وكلاء المجموعة — نافذة الحذف تعرضه قبل أن ينتقلوا إلى «بلا مجموعة»
    dealer_count = serializers.IntegerField(source="dealers.count", read_only=True)

    class Meta:
        model = PriceGroup
        fields = ["id", "name", "dollar_rate", "dealer_count", "created_at"]
        read_only_fields = ["tenant", "created_at"]


class ProductSerializer(SameTenantFields, serializers.ModelSerializer):
    """
    باقة المتجر.

    **رقم الربط (`kupur`) لا يُعدَّل بعد الإنشاء.** هو جسر ثابت بين باقتك وباقة
    المكتبة العالمية وباقات المزوّدين؛ تغييره يقطع الجسر على طلبات قائمة، ولذلك
    يُختار مرّةً واحدة عند الإضافة من قائمة أرقام المكتبة، ثم يبقى. أمّا الاسم
    والتكلفة والسعر الموصى فيملكها صاحب المتجر ويعدّلها متى شاء.
    """

    profit = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    created_at = serializers.DateTimeField(format="%Y-%m-%d", read_only=True)
    game_name = serializers.CharField(source="game.name", read_only=True)

    class Meta:
        model = Product
        fields = [
            "id", "game", "game_name", "name", "cost_price", "recommended_price", "profit",
            "kupur", "status", "status_label", "is_parcali", "execution_type",
            "provider", "provider_alt1", "provider_alt2", "provider_package_id",
            "description", "sort_order", "created_at",
            "sale_type", "qty_min", "qty_max", "qty_unit",
        ]
        read_only_fields = ["tenant"]

    # المزوّدون واللعبة من متجر صاحب الطلب وحده (core/tenancy.py)
    tenant_fields = ("game", "provider", "provider_alt1", "provider_alt2")

    def validate(self, attrs):
        attrs = super().validate(attrs)
        # حدود الكمية: تُفحص في الإضافة والتعديل معاً
        get = lambda k, d: attrs.get(k, getattr(self.instance, k, d) if self.instance else d)
        if get("sale_type", "package") == Product.SaleType.AMOUNT:
            lo, hi, unit = get("qty_min", 1), get("qty_max", 1), get("qty_unit", 1)
            if not unit or unit < 1:
                raise serializers.ValidationError({"qty_unit": "حجم الكتلة يجب أن يكون 1 فأكثر"})
            if lo < 1 or hi < lo:
                raise serializers.ValidationError({"qty_min": "أقل كمية يجب أن تكون 1 فأكثر ولا تتجاوز أكبر كمية"})

        # التحقّق عند الإضافة فقط — التعديل لا يمسّ رقم الربط أصلاً (انظر update)
        if self.instance is not None:
            return attrs

        game = attrs.get("game")
        kupur = (attrs.get("kupur") or "").strip()
        attrs["kupur"] = kupur
        if game is None:
            return attrs

        if kupur and Product.objects.filter(game=game, kupur=kupur).exists():
            raise serializers.ValidationError(
                {"kupur": f"رقم الربط {kupur} مستعمل في باقة أخرى ضمن هذه اللعبة."}
            )

        # لعبة مستورَدة من المكتبة ⇒ رقم الربط من المكتبة حصراً
        if game.master_library_uuid:
            lib = LibraryGame.objects.filter(uuid=game.master_library_uuid).first()
            if lib is not None:
                allowed = {
                    (p.kupur or "").strip()
                    for p in lib.products.filter(is_active=True)
                    if (p.kupur or "").strip()
                }
                if not kupur:
                    raise serializers.ValidationError(
                        {"kupur": "اختر رقم ربط من المكتبة العالمية."}
                    )
                if kupur not in allowed:
                    raise serializers.ValidationError(
                        {"kupur": f"رقم الربط {kupur} غير معرّف في المكتبة العالمية لهذه اللعبة."}
                    )
        return attrs

    def update(self, instance, validated_data):
        validated_data.pop("kupur", None)  # ثابت — مصدره المكتبة العالمية
        # النوع وحجم الكتلة ثابتان أيضاً: أسعار المزوّدين على الربط محفوظةٌ لكل كتلة،
        # فتغييرهما يجعلها كاذبةً بصمت. الحدّان وحدهما قابلان للتعديل.
        validated_data.pop("sale_type", None)
        validated_data.pop("qty_unit", None)
        return super().update(instance, validated_data)


class GameSerializer(serializers.ModelSerializer):
    product_count = serializers.IntegerField(source="products.count", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    created_at = serializers.DateTimeField(format="%Y-%m-%d", read_only=True)

    class Meta:
        model = Game
        fields = [
            "id", "name", "image_url", "dealer_note", "description", "status",
            "status_label", "require_player_id", "kurulu_sale", "toplu_sale",
            "sms_template", "sort_order", "product_count", "created_at",
        ]
        read_only_fields = ["tenant"]


class GameDetailSerializer(GameSerializer):
    products = ProductSerializer(many=True, read_only=True)

    class Meta(GameSerializer.Meta):
        fields = GameSerializer.Meta.fields + ["products"]


# ─────────── المكتبة العالمية ───────────
class LibraryProductSerializer(serializers.ModelSerializer):
    class Meta:
        model = LibraryProduct
        fields = [
            "id", "uuid", "game", "name", "suggested_cost", "suggested_price",
            "kupur", "is_parcali", "execution_type", "description", "sort_order", "is_active",
            "source_ref", "source_name", "source_cost",
            "sale_type", "qty_min", "qty_max", "qty_unit",
        ]
        read_only_fields = ["uuid", "source_ref", "source_name", "source_cost"]

    def update(self, instance, validated_data):
        # النوع وحجم الكتلة ثابتان بعد الإنشاء: نسخ المتاجر وأسعار الربط محفوظةٌ بهما
        validated_data.pop("sale_type", None)
        validated_data.pop("qty_unit", None)
        return super().update(instance, validated_data)

    def validate(self, attrs):
        """رقم الربط فريد داخل اللعبة — رقمان متطابقان يجعلان الجسر ملتبساً."""
        get = lambda k, d: attrs.get(k, getattr(self.instance, k, d) if self.instance else d)
        if get("sale_type", "package") == Product.SaleType.AMOUNT:
            lo, hi, unit = get("qty_min", 1), get("qty_max", 1), get("qty_unit", 1)
            if not unit or unit < 1 or lo < 1 or hi < lo:
                raise serializers.ValidationError(
                    {"qty_min": "حدّا الكمية: أقلّها 1 فأكثر ولا يتجاوز أكبرها"})
        game = attrs.get("game") or getattr(self.instance, "game", None)
        kupur = (attrs.get("kupur") if "kupur" in attrs else getattr(self.instance, "kupur", ""))
        kupur = (kupur or "").strip()
        attrs["kupur"] = kupur
        if game and kupur:
            clash = LibraryProduct.objects.filter(game=game, kupur=kupur)
            if self.instance is not None:
                clash = clash.exclude(pk=self.instance.pk)
            if clash.exists():
                raise serializers.ValidationError(
                    {"kupur": f"رقم الربط {kupur} مستعمل في باقة أخرى ضمن هذه اللعبة."}
                )
        return attrs


class LibraryGameSerializer(serializers.ModelSerializer):
    product_count = serializers.IntegerField(source="products.count", read_only=True)
    source_name = serializers.CharField(source="source.name", read_only=True, default="")

    class Meta:
        model = LibraryGame
        fields = [
            "id", "uuid", "name", "image_url", "description", "require_player_id",
            "kurulu_sale", "toplu_sale", "sms_template", "sort_order", "is_active",
            "product_count", "created_at", "source", "source_key", "source_name",
        ]
        read_only_fields = ["uuid", "created_at", "source", "source_key"]


class LibraryGameDetailSerializer(LibraryGameSerializer):
    products = LibraryProductSerializer(many=True, read_only=True)

    class Meta(LibraryGameSerializer.Meta):
        fields = LibraryGameSerializer.Meta.fields + ["products"]
