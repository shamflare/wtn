"""
مزوّدو الخطوط وتوجيه الباقات (لصاحب المتجر) — على نسق الألعاب:
لكل باقة مزوّد رئيسي وبديلان، ولكل مزوّد رقم الباقة لديه.

المزوّدون أنفسهم هم «مزوّدو API» المشتركون مع الألعاب (لوحات ZNET)؛ هنا نختار
منهم لكل باقة ونربط أرقامها.
"""
from decimal import Decimal, InvalidOperation

import requests
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from providers.models import Provider

from .models import KontorPackage, KontorPackageLink
from .services import auto_link, kontor_providers, provider_creds
from .views import _require_admin

ROUTE_FIELDS = ("provider", "provider_alt1", "provider_alt2")


def _prov_row(p: Provider) -> dict:
    return {"id": p.id, "name": p.name, "status": p.status,
            "ready": bool(provider_creds(p)), "currency": p.currency or "TRY"}


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def providers_view(request):
    """مزوّدو الخطوط المتاحون للتوجيه (لوحات ZNET في «مزوّدو API»)."""
    if not _require_admin(request):
        return Response({"detail": "مخصّص لصاحب المتجر"}, status=403)
    return Response([_prov_row(p) for p in kontor_providers(request.user.tenant)])


@api_view(["GET", "PATCH"])
@permission_classes([IsAuthenticated])
def routing_view(request):
    """
    GET ?operator=: الباقات بمزوّديها الثلاثة وأرقامها لدى كل مزوّد.
    PATCH: {packages:[ids], provider?, provider_alt1?, provider_alt2?} — توجيه دفعة
    (القيمة null تفرّغ الخانة؛ والخانة الغائبة تبقى كما هي).
    """
    if not _require_admin(request):
        return Response({"detail": "مخصّص لصاحب المتجر"}, status=403)
    tenant = request.user.tenant
    allowed = {p.id for p in kontor_providers(tenant)}

    if request.method == "PATCH":
        ids = request.data.get("packages") or []
        changes = {}
        for f in ROUTE_FIELDS:
            if f in request.data:
                v = request.data[f]
                if v not in (None, "") and int(v) not in allowed:
                    return Response({"detail": "مزوّد غير صالح لشحن الخطوط"}, status=400)
                changes[f"{f}_id"] = int(v) if v not in (None, "") else None
        if not ids or not changes:
            return Response({"detail": "حدّد باقات وتوجيهاً"}, status=400)
        n = KontorPackage.objects.filter(tenant=tenant, pk__in=ids).update(**changes)
        return Response({"updated": n})

    qs = KontorPackage.objects.filter(tenant=tenant).select_related("category")
    op = request.query_params.get("operator")
    if op:
        qs = qs.filter(operator=op)
    links: dict = {}
    for l in KontorPackageLink.objects.filter(tenant=tenant, package__in=qs):
        links.setdefault(l.package_id, {})[str(l.provider_id)] = {"code": l.code, "cost": str(l.cost)}
    rows = [{
        "id": p.id, "link_code": p.link_code, "name": p.name, "znet_id": p.znet_id,
        "category": p.category.name if p.category else "", "status": p.status, "kind": p.kind,
        "provider": p.provider_id, "provider_alt1": p.provider_alt1_id, "provider_alt2": p.provider_alt2_id,
        "links": links.get(p.id, {}),
    } for p in qs.order_by("category__sort_order", "sort_order", "id")]
    return Response({"providers": [_prov_row(p) for p in kontor_providers(tenant)], "rows": rows})


@api_view(["POST", "DELETE"])
@permission_classes([IsAuthenticated])
def link_view(request):
    """POST {package, provider, code, cost?} ربط/تعديل · DELETE {package, provider} فكّ."""
    if not _require_admin(request):
        return Response({"detail": "مخصّص لصاحب المتجر"}, status=403)
    tenant = request.user.tenant
    pkg = KontorPackage.objects.filter(pk=request.data.get("package"), tenant=tenant).first()
    prov = next((p for p in kontor_providers(tenant) if p.id == int(request.data.get("provider") or 0)), None)
    if not (pkg and prov):
        return Response({"detail": "باقة أو مزوّد غير صحيح"}, status=400)
    if request.method == "DELETE":
        KontorPackageLink.objects.filter(package=pkg, provider=prov).delete()
        return Response({"deleted": True})
    code = str(request.data.get("code") or "").strip()
    if not code:
        return Response({"detail": "رقم الباقة لدى المزوّد مطلوب"}, status=400)
    defaults = {"tenant": tenant, "code": code}
    if request.data.get("cost") not in (None, ""):
        try:
            defaults["cost"] = Decimal(str(request.data["cost"]).replace(",", "."))
        except InvalidOperation:
            return Response({"detail": "كلفة غير صحيحة"}, status=400)
    link, _ = KontorPackageLink.objects.update_or_create(package=pkg, provider=prov, defaults=defaults)
    return Response({"package": pkg.id, "provider": prov.id, "code": link.code, "cost": str(link.cost)})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def auto_link_view(request):
    """POST {provider}: يربط باقات المتجر بمزوّد ZNET آخر من قائمته — بالرقم ثم بالاسم."""
    if not _require_admin(request):
        return Response({"detail": "مخصّص لصاحب المتجر"}, status=403)
    tenant = request.user.tenant
    prov = next((p for p in kontor_providers(tenant) if p.id == int(request.data.get("provider") or 0)), None)
    if not prov:
        return Response({"detail": "اختر مزوّد خطوط"}, status=400)
    try:
        report = auto_link(tenant, prov)
    except requests.RequestException as e:
        return Response({"detail": f"تعذّر الاتصال بالمزوّد: {e}"}, status=502)
    except ValueError as e:
        return Response({"detail": str(e)}, status=400)
    report["provider"] = prov.name
    return Response(report)
