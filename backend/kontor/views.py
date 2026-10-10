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


@api_view(["GET", "POST", "PATCH", "DELETE"])
@permission_classes([IsAuthenticated])
def categories_view(request):
    """
    GET: كل الفئات. PATCH: تحديث مجموعة (الاسم/الحالة/الاستعلام/الترتيب/الشعار).
    POST {operator, name, line_type}: فئة يضيفها المالك. DELETE {id}: حذف فئة فارغة.
    """
    if not _require_admin(request):
        return Response({"detail": "مخصّص لصاحب المتجر"}, status=403)
    tenant = request.user.tenant

    if request.method == "GET":
        qs = KontorCategory.objects.filter(tenant=tenant)
        return Response(KontorCategorySerializer(qs, many=True).data)

    if request.method == "POST":
        from django.db.models import Max

        from .models import LineType, Operator
        op, lt = request.data.get("operator"), request.data.get("line_type")
        name = (request.data.get("name") or "").strip()[:120]
        if op not in Operator.values or lt not in LineType.values:
            return Response({"detail": "اختر الشركة ونوع الشحن"}, status=400)
        if not name:
            return Response({"detail": "اسم الفئة مطلوب"}, status=400)
        if KontorCategory.objects.filter(tenant=tenant, operator=op, name__iexact=name).exists():
            return Response({"detail": f"لدى هذه الشركة فئة باسم «{name}» أصلاً"}, status=400)
        top = KontorCategory.objects.filter(tenant=tenant, operator=op).aggregate(m=Max("sort_order"))["m"] or 0
        logo = (KontorCategory.objects.filter(tenant=tenant, operator=op).exclude(logo_url="")
                .values_list("logo_url", flat=True).first() or "")
        cat = KontorCategory.objects.create(tenant=tenant, operator=op, line_type=lt, name=name,
                                            is_custom=True, sort_order=top + 10, logo_url=logo)
        return Response(KontorCategorySerializer(cat).data, status=status.HTTP_201_CREATED)

    if request.method == "DELETE":
        cat = KontorCategory.objects.filter(pk=request.data.get("id"), tenant=tenant).first()
        if not cat:
            return Response({"detail": "غير موجودة"}, status=404)
        if cat.packages.exists():
            return Response({"detail": "في الفئة باقات — انقلها أو احذفها أولاً"}, status=400)
        cat.delete()
        return Response({"deleted": True})

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


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def packages_view(request):
    """
    GET: باقات المتجر، مع تصفية اختيارية بالمشغّل ?operator= والنوع ?line_type=.
    POST: باقة يدوية {operator, line_type, name, cost, recommended_price?, details?,
    link_code?, kind?} — لباقة ليست لدى ZNET؛ كلفتها بعملة الدفتر.
    """
    if not _require_admin(request):
        return Response({"detail": "مخصّص لصاحب المتجر"}, status=403)
    if request.method == "POST":
        return _create_manual(request)
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
    ser = KontorPackageSerializer(obj, data=request.data, partial=True, context={"request": request})
    ser.is_valid(raise_exception=True)
    ser.save()
    return Response(ser.data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def import_view(request):
    """
    يستورد الباقات **الجديدة** من مزوّد خطوط يختاره المالك (لوحة ZNET). {provider?} —
    افتراضاً أوّل مزوّد ZNET. الجديدة تُوجَّه إليه وتُربط برقمها لديه، والموجودة لا تُمسّ.
    """
    if not _require_admin(request):
        return Response({"detail": "مخصّص لصاحب المتجر"}, status=403)
    from .services import kontor_providers, provider_creds
    tenant = request.user.tenant
    want = request.data.get("provider") if hasattr(request, "data") else None
    provs = kontor_providers(tenant)
    prov = next((p for p in provs if want and p.id == int(want)), None) if want else (provs[0] if provs else None)
    if not prov:
        return Response({"detail": "لا مزوّد خطوط (ZNET) مُعدّ — أضِفه أولاً في «مزوّدو API»."}, status=400)
    creds = provider_creds(prov)
    if not creds:
        return Response({"detail": "إعداد ZNET ناقص (base_url/kod/sifre)."}, status=400)
    try:
        res = import_from_znet(tenant, *creds, provider=prov, only_new=True)
    except requests.RequestException as e:
        return Response({"detail": f"تعذّر الاتصال بـ ZNET: {e}"}, status=502)
    except ValueError as e:
        return Response({"detail": str(e)}, status=400)
    res["provider"] = prov.name
    return Response(res, status=status.HTTP_200_OK)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def packages_bulk_view(request):
    """تعديل جماعي: {ids:[...], status?, kind?} — تفعيل/تعطيل/إيقاف بيع أو تغيير النوع."""
    if not _require_admin(request):
        return Response({"detail": "مخصّص لصاحب المتجر"}, status=403)
    ids = request.data.get("ids") or []
    changes = {}
    if request.data.get("status") in KontorPackage.Status.values:
        changes["status"] = request.data["status"]
    if request.data.get("kind") in KontorPackage.Kind.values:
        changes["kind"] = request.data["kind"]
    if not ids or not changes:
        return Response({"detail": "حدّد باقات وتعديلاً"}, status=400)
    n = KontorPackage.objects.filter(tenant=request.user.tenant, pk__in=ids).update(**changes)
    return Response({"updated": n})


def _pick_provider(request):
    from .services import kontor_providers
    want = request.data.get("provider")
    try:
        want = int(want)
    except (TypeError, ValueError):
        return None
    return next((p for p in kontor_providers(request.user.tenant) if p.id == want), None)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def refresh_costs_view(request):
    """{provider}: كلفة الباقات = كلفتها لدى هذا المزوّد؛ غير المربوطة به تبقى وتُذكر."""
    if not _require_admin(request):
        return Response({"detail": "مخصّص لصاحب المتجر"}, status=403)
    from .services import refresh_costs
    prov = _pick_provider(request)
    if not prov:
        return Response({"detail": "اختر مزوّد خطوط (ZNET)"}, status=400)
    try:
        return Response(refresh_costs(request.user.tenant, prov))
    except requests.RequestException as e:
        return Response({"detail": f"تعذّر الاتصال بالمزوّد: {e}"}, status=502)
    except ValueError as e:
        return Response({"detail": str(e)}, status=400)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def packages_delete_view(request):
    """
    {ids}: حذف نهائي — للباقات **المعطّلة** وحدها. الطلبات السابقة لا تتأثّر: صفّها
    مجمَّد (الاسم والأرقام والمبالغ محفوظة فيه). وتُرفض باقة لها طلب لم ينتهِ بعد.
    """
    if not _require_admin(request):
        return Response({"detail": "مخصّص لصاحب المتجر"}, status=403)
    from .models import KontorOrder
    ids = request.data.get("ids") or []
    qs = KontorPackage.objects.filter(tenant=request.user.tenant, pk__in=ids)
    active = qs.exclude(status=KontorPackage.Status.PASSIVE).count()
    if active:
        return Response({"detail": f"عطّل الباقات أولاً — {active} منها غير معطّلة"}, status=400)
    busy = list(KontorOrder.objects.filter(
        package__in=qs, status__in=[KontorOrder.Status.PENDING, KontorOrder.Status.PROCESSING])
        .values_list("package__name", flat=True).distinct())
    if busy:
        return Response({"detail": "لها طلبات قيد التنفيذ — انتظر انتهاءها: " + "، ".join(busy)}, status=400)
    n = qs.count()
    qs.delete()
    return Response({"deleted": n})


def _create_manual(request):
    from decimal import Decimal, InvalidOperation

    from .models import LineType, Operator
    from .services import SHORT_NAME, free_link_code
    tenant = request.user.tenant
    d = request.data
    op, lt = d.get("operator"), d.get("line_type")
    name = (d.get("name") or "").strip()
    cat = None
    if d.get("category"):
        cat = KontorCategory.objects.filter(pk=d.get("category"), tenant=tenant, operator=op).first()
        if not cat:
            return Response({"detail": "الفئة لا تتبع هذه الشركة"}, status=400)
    elif op not in Operator.values or lt not in LineType.values:
        return Response({"detail": "اختر الشركة والفئة"}, status=400)
    if not name:
        return Response({"detail": "اسم الباقة مطلوب"}, status=400)
    try:
        cost = Decimal(str(d.get("cost") or "0").replace(",", ".")).quantize(Decimal("0.01"))
        rec = Decimal(str(d.get("recommended_price") or "0").replace(",", ".")).quantize(Decimal("0.01"))
    except InvalidOperation:
        return Response({"detail": "الكلفة أو السعر غير صحيح"}, status=400)
    if cost < 0 or rec < 0:
        return Response({"detail": "الأسعار لا تكون سالبة"}, status=400)

    if cat is None:
        cat, _ = KontorCategory.objects.get_or_create(
            tenant=tenant, operator=op, line_type=lt, is_custom=False,
            defaults={"name": SHORT_NAME.get(lt, lt)})
    n = 1
    while KontorPackage.objects.filter(tenant=tenant, operator=op, znet_id=f"M{n}").exists():
        n += 1
    pkg = KontorPackage(
        tenant=tenant, operator=op, category=cat, znet_id=f"M{n}", name=name, provider_name=name,
        details=(d.get("details") or "").strip()[:300], cost_price=cost, recommended_price=rec,
        kind=d.get("kind") if d.get("kind") in KontorPackage.Kind.values else KontorPackage.Kind.GENERAL,
        is_manual=True,
    )
    code = (d.get("link_code") or "").strip()
    if code:
        ser = KontorPackageSerializer(instance=pkg)
        try:
            pkg.link_code = ser.validate_link_code(code)
        except Exception as e:  # noqa: BLE001 — ValidationError برسالته العربية
            msg = getattr(e, "detail", [str(e)])
            return Response({"detail": msg[0] if isinstance(msg, list) else str(msg)}, status=400)
    else:
        pkg.link_code = free_link_code(tenant, pkg.znet_id, op)
    pkg.save()
    return Response(KontorPackageSerializer(pkg).data, status=status.HTTP_201_CREATED)
