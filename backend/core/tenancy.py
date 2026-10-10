"""
حقول تشير إلى سجلّاتٍ أخرى (مزوّد · لعبة · فئة) تُقبل من **متجر صاحب الطلب وحده**.

DRF يقبل في هذه الحقول أي رقمٍ موجود في القاعدة كلّها. والأرقام متسلسلة، فكان
صاحب متجرٍ يربط باقته بمزوّد متجرٍ آخر فتُخصم طلباته من رصيد ذلك المتجر لدى ZNET.
"""
from rest_framework import serializers


class SameTenantFields:
    """
    `tenant_fields = (...)` في الـ serializer: يُرفض أيّ حقلٍ منها يشير إلى سجلٍّ من
    متجرٍ غير متجر المستخدم. يحتاج `request` في السياق (الـ ViewSet يمرّره).
    """
    tenant_fields: tuple = ()

    def validate(self, attrs):
        attrs = super().validate(attrs)
        request = self.context.get("request")
        tenant_id = getattr(getattr(request, "user", None), "tenant_id", None)
        if request is None:
            raise serializers.ValidationError("سياق الطلب مفقود")
        for name in self.tenant_fields:
            obj = attrs.get(name)
            if obj is not None and getattr(obj, "tenant_id", None) != tenant_id:
                raise serializers.ValidationError({name: "غير موجود"})
        return attrs
