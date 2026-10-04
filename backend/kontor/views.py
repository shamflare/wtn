"""واجهة إدارة كتالوج الخطوط (لصاحب المتجر)."""
import requests
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.models import User
from providers.models import Provider

from .models import KontorCategory, KontorPackage
from .serializers import KontorCategorySerializer, KontorPackageSerializer
from .services import import_from_znet


def _require_admin(request):
    u = request.user
    return u.role == User.Role.TENANT_ADMIN and u.tenant_id is not None


def _znet_provider(tenant):
    """مزوّد ZNET لهذا المتجر (نفس حساب الألعاب) — يُعرَف بالكود znet في config."""
    for p in Provider.objects.filter(tenant=tenant):
        if ((p.config or {}).get("code") or "").lower() == "znet":
            return p
    return None


@api_view(["GET", "PATCH"])
@permission_classes([IsAuthenticated])
def categories_view(request):
    """GET: كل الفئات. PATCH: تحديث مجموعة (الاسم/الحالة/الاستعلام/الترتيب/الشعار)."""
    if not _require_admin(request):
        return Response({"detail": "مخصّص لصاحب المتجر"}, status=403)
    tenant = request.user.tenant

    if request.method == "GET":
        qs = KontorCategory.objects.filter(tenant=tenant)
        return Response(KontorCategorySerializer(qs, many=True).data)

    # PATCH: قائمة {id, ...حقول قابلة للتعديل}
    rows = request.data if isinstance(request.data, list) else [request.data]
    editable = {"name", "logo_url", "is_query", "status", "sort_order"}
    for row in rows:
        obj = KontorCategory.objects.filter(pk=row.get("id"), tenant=tenant).first()
        if not obj:
            continue
        for f in editable & set(row):
            setattr(obj, f, row[f])
        obj.save()
    return Response({"ok": True})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def packages_view(request):
    """باقات المتجر، مع تصفية اختيارية بالمشغّل ?operator= والنوع ?line_type=."""
    if not _require_admin(request):
        return Response({"detail": "مخصّص لصاحب المتجر"}, status=403)
    qs = KontorPackage.objects.filter(tenant=request.user.tenant).select_related("category")
    op = request.query_params.get("operator")
    lt = request.query_params.get("line_type")
    if op:
        qs = qs.filter(operator=op)
    if lt:
        qs = qs.filter(category__line_type=lt)
    return Response(KontorPackageSerializer(qs, many=True).data)


@api_view(["PATCH"])
@permission_classes([IsAuthenticated])
def package_update_view(request, pk):
    """تعديل باقة: الموصى/النوع/الحالة/التوجيه/التفاصيل/الفلاتر/الترتيب."""
    if not _require_admin(request):
        return Response({"detail": "مخصّص لصاحب المتجر"}, status=403)
    obj = KontorPackage.objects.filter(pk=pk, tenant=request.user.tenant).first()
    if not obj:
        return Response({"detail": "غير موجود"}, status=404)
    ser = KontorPackageSerializer(obj, data=request.data, partial=True)
    ser.is_valid(raise_exception=True)
    ser.save()
    return Response(ser.data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def import_view(request):
    """يستورد الباقات من ZNET مستعملاً بيانات مزوّد ZNET المحفوظة."""
    if not _require_admin(request):
        return Response({"detail": "مخصّص لصاحب المتجر"}, status=403)
    tenant = request.user.tenant
    prov = _znet_provider(tenant)
    if not prov:
        return Response({"detail": "لا مزوّد ZNET مُعدّ — أضِفه أولاً في المزوّدين."}, status=400)
    cfg = prov.config or {}
    base_url, kod, sifre = cfg.get("base_url"), cfg.get("kod"), cfg.get("sifre")
    if not (base_url and kod and sifre):
        return Response({"detail": "إعداد ZNET ناقص (base_url/kod/sifre)."}, status=400)
    try:
        res = import_from_znet(tenant, base_url, kod, sifre)
    except requests.RequestException as e:
        return Response({"detail": f"تعذّر الاتصال بـ ZNET: {e}"}, status=502)
    except ValueError as e:
        return Response({"detail": str(e)}, status=400)
    return Response(res, status=status.HTTP_200_OK)
