"""API لوحة المنصّة (SuperAdmin): إدارة المستأجرين + المكتبة العالمية — لمالك المنصّة فقط."""
import re
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from rest_framework import status as http, viewsets
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.response import Response

from catalog.models import LibraryGame, LibraryProduct
from catalog.serializers import (
    LibraryGameDetailSerializer, LibraryGameSerializer, LibraryProductSerializer,
)
from core.text import clean_login_id
from core.models import Invoice, Tenant, User, Wallet
from orders.models import Order
from core.views import _invoice_row


class IsPlatformOwner(BasePermission):
    """يسمح فقط لمالك المنصّة."""
    message = "هذه اللوحة مخصّصة لمالك المنصّة فقط."

    def has_permission(self, request, view):
        return bool(request.user and request.user.role == User.Role.PLATFORM_OWNER)


class LibraryGameViewSet(viewsets.ModelViewSet):
    """CRUD ألعاب المكتبة العالمية — لمالك المنصّة فقط."""
    permission_classes = [IsAuthenticated, IsPlatformOwner]
    queryset = LibraryGame.objects.all()

    def get_serializer_class(self):
        return LibraryGameDetailSerializer if self.action == "retrieve" else LibraryGameSerializer

    def perform_update(self, serializer):
        """
        الصورة تتبع المكتبة ما لم يخصّصها صاحب المتجر.

        الاستيراد ينسخ اللعبة مرّةً، فصورةٌ أُضيفت للمكتبة بعده لم تكن تصل أبداً.
        نسخةٌ صورتها فارغة أو ما زالت صورة المكتبة القديمة لم يمسّها صاحبها —
        فتأخذ الجديدة. ومن وضع صورته بيده تبقى له.
        """
        from django.db.models import Q
        from catalog.models import Game

        old = serializer.instance.image_url
        lib = serializer.save()
        if lib.image_url != old:
            unchanged = Q(image_url="") | (Q(image_url=old) if old else Q(pk__in=[]))
            Game.objects.filter(master_library_uuid=lib.uuid).filter(unchanged).update(image_url=lib.image_url)


class LibrarySourceViewSet(viewsets.ViewSet):
    """
    مصادر المكتبة — مالك المنصّة وحده.

    المفتاح (api_token) لا يُعاد إلى المتصفّح أبداً: يُكتب ولا يُقرأ. وللمصدر
    طريقان: إدخالٌ يدوي، أو نسخُ إعداد مزوّدٍ قائم لدى أحد المتاجر (`from_provider`)
    — فلا يحتاج المالك أن يطلب المفتاح من صاحب المتجر.
    """
    permission_classes = [IsAuthenticated, IsPlatformOwner]

    @staticmethod
    def _row(s):
        from catalog.library_sources import fingerprint
        cfg = s.config or {}
        return {
            "id": s.id, "name": s.name, "code": s.code, "base_url": cfg.get("base_url", ""),
            "has_token": bool(cfg.get("api_token")), "currency": s.currency,
            "usd_rate": str(s.usd_rate), "default_margin": str(s.default_margin),
            "fingerprint": fingerprint(s.code, cfg),
            "games": s.games.count(),
            "last_synced_at": s.last_synced_at.strftime("%Y-%m-%d %H:%M") if s.last_synced_at else None,
        }

    def _get(self, pk):
        from catalog.models import LibrarySource
        return LibrarySource.objects.filter(pk=pk).first()

    @staticmethod
    def _apply(s, data):
        from catalog.library_sources import _dec
        if "name" in data:
            s.name = str(data["name"]).strip()[:120] or s.name
        if "currency" in data:
            s.currency = (str(data["currency"]).strip().upper() or "USD")[:8]
        for f in ("usd_rate", "default_margin"):
            if f in data and _dec(data[f]) is not None:
                setattr(s, f, _dec(data[f]))
        cfg = dict(s.config or {})
        if "base_url" in data:
            cfg["base_url"] = str(data["base_url"]).strip()
        if data.get("api_token"):
            cfg["api_token"] = str(data["api_token"]).strip()
        s.config = cfg

    def list(self, request):
        from catalog.models import LibrarySource
        return Response([self._row(s) for s in LibrarySource.objects.all()])

    def create(self, request):
        from catalog.models import LibrarySource
        from providers.models import Provider

        d = request.data
        s = LibrarySource(name=str(d.get("name") or "").strip()[:120])
        if d.get("from_provider"):
            p = Provider.objects.select_related("tenant").filter(pk=d["from_provider"]).first()
            if p is None:
                return Response({"detail": "المزوّد غير موجود"}, status=404)
            cfg = p.config or {}
            s.name = s.name or p.name
            s.code = "zdk"
            s.config = {"base_url": cfg.get("base_url", ""), "api_token": cfg.get("api_token", "")}
            s.currency = p.currency or "USD"
        self._apply(s, {k: v for k, v in d.items() if k != "api_token" or not d.get("from_provider")})
        if not s.name:
            return Response({"detail": "اسم المصدر مطلوب"}, status=400)
        if not (s.config or {}).get("api_token"):
            return Response({"detail": "مفتاح API مطلوب"}, status=400)
        s.save()
        return Response(self._row(s), status=201)

    def partial_update(self, request, pk=None):
        s = self._get(pk)
        if s is None:
            return Response(status=404)
        self._apply(s, request.data)
        s.save()
        return Response(self._row(s))

    def destroy(self, request, pk=None):
        """حذف المصدر لا يحذف ما استُورد منه — تبقى ألعاب المكتبة بلا مصدر."""
        s = self._get(pk)
        if s is None:
            return Response(status=404)
        s.delete()
        return Response(status=204)


@api_view(["GET"])
@permission_classes([IsAuthenticated, IsPlatformOwner])
def library_source_catalog_view(request, source_id):
    """كتالوج المصدر مجمّعاً، موسوماً بحالته مقابل المكتبة."""
    from catalog.library_sources import fetch_catalog
    from catalog.models import LibrarySource

    s = LibrarySource.objects.filter(pk=source_id).first()
    if s is None:
        return Response({"detail": "المصدر غير موجود"}, status=404)
    data = fetch_catalog(s)
    return Response(data, status=200 if data.get("ok") else 502)


@api_view(["POST"])
@permission_classes([IsAuthenticated, IsPlatformOwner])
def library_source_import_view(request, source_id):
    """
    استيراد/مزامنة: {picks: [{key, name?}], margin?, update_prices?}
    و`sync: true` بلا picks ⇐ كل الألعاب المستوردة من هذا المصدر.
    """
    from catalog.library_sources import apply_import
    from catalog.models import LibrarySource

    s = LibrarySource.objects.filter(pk=source_id).first()
    if s is None:
        return Response({"detail": "المصدر غير موجود"}, status=404)
    picks = request.data.get("picks")
    if request.data.get("sync"):
        picks = [{"key": k} for k in s.games.exclude(source_key="").values_list("source_key", flat=True)]
    if not isinstance(picks, list) or not picks:
        return Response({"detail": "اختر لعبةً واحدة على الأقل"}, status=400)
    data = apply_import(s, picks, margin=request.data.get("margin"),
                        update_prices=request.data.get("update_prices", True) is not False)
    return Response(data, status=200 if data.get("ok") else 502)


@api_view(["GET"])
@permission_classes([IsAuthenticated, IsPlatformOwner])
def tenant_providers_view(request):
    """مزوّدو المتاجر الآليّون (ZDK) — ليُنسخ إعداد أحدهم مصدراً. بلا مفاتيح."""
    from catalog.library_sources import SUPPORTED, family, provider_fingerprint
    from providers.models import Provider

    rows = []
    for p in Provider.objects.select_related("tenant").order_by("tenant_id", "id"):
        code = (p.config or {}).get("code") or ("zdk" if p.type == Provider.Type.CARD_STORE else "")
        if family(code) not in SUPPORTED or not (p.config or {}).get("api_token"):
            continue
        rows.append({"id": p.id, "name": p.name, "tenant": p.tenant.name if p.tenant else "",
                     "currency": p.currency, "fingerprint": provider_fingerprint(p)})
    return Response(rows)


class LibraryProductViewSet(viewsets.ModelViewSet):
    """CRUD باقات المكتبة العالمية — لمالك المنصّة فقط."""
    permission_classes = [IsAuthenticated, IsPlatformOwner]
    serializer_class = LibraryProductSerializer

    def get_queryset(self):
        qs = LibraryProduct.objects.all()
        game = self.request.query_params.get("game")
        return qs.filter(game_id=game) if game else qs


def _tenant_row(t):
    from django.utils import timezone
    dealers = User.objects.filter(tenant=t, role=User.Role.BAYI).count()
    today = timezone.localdate()
    days_left = (t.sub_expires_at - today).days if t.sub_expires_at else None
    return {
        "id": t.id,
        "name": t.name,
        "subdomain": t.subdomain,
        "status": t.status,
        "theme": t.theme,
        "dealers": dealers,
        "created_at": t.created_at.strftime("%Y-%m-%d"),
        "sub_plan": t.sub_plan,
        "sub_plan_label": t.get_sub_plan_display(),
        "sub_monthly_price": str(t.sub_monthly_price),
        "sub_yearly_price": str(t.sub_yearly_price),
        "sub_expires_at": t.sub_expires_at.strftime("%Y-%m-%d") if t.sub_expires_at else None,
        "sub_active": bool(t.sub_expires_at and t.sub_expires_at >= today),
        "sub_days_left": days_left,
        "sub_grace_days": t.sub_grace_days,
        "sub_enforce": t.sub_enforce,
        # مرجعٌ واحد تقرأ منه اللوحة والخادم: ok · warn · grace · blocked
        "sub_state": t.subscription_state(today),
        # العنوان يُبنى على الخادم من `PLATFORM_DOMAIN` — كان مكتوباً
        # `example.com` في الواجهة فظهرت العناوين كلّها خاطئة
        "domain": f"{t.subdomain}.{settings.PLATFORM_DOMAIN}",
        # ما سيُفقد بالحذف — يُعرض قبل السؤال لا بعده
        "orders": Order.objects.filter(tenant=t).count(),
        "users": User.objects.filter(tenant=t).count(),
        # صاحب المتجر — تعرضه نافذة التعديل كي يعرف المالك لمن يبدّل الكلمة.
        # كلمة السرّ لا تُرجَع أبداً: مخزَّنةٌ مُعمّاةً ولا سبيل إلى قراءتها.
        **_tenant_admin_row(t),
    }


def _tenant_admin_row(t):
    """حساب صاحب المتجر — أقدمُ `tenant_admin` إن تعدّدوا."""
    admin = (
        User.objects
        .filter(tenant=t, role=User.Role.TENANT_ADMIN)
        .order_by("id")
        .first()
    )
    if admin is None:
        return {"admin_login_id": None, "admin_name": None, "admin_locked": False}
    return {
        "admin_login_id": admin.login_id,
        "admin_name": admin.name,
        "admin_locked": admin.is_locked,
    }


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated, IsPlatformOwner])
def tenants_view(request):
    if request.method == "POST":
        data = request.data
        subdomain = (data.get("subdomain") or "").strip().lower()
        if not subdomain or not data.get("name"):
            return Response({"detail": "الاسم والنطاق الفرعي مطلوبان"}, status=400)
        if Tenant.objects.filter(subdomain=subdomain).exists():
            return Response({"detail": "النطاق الفرعي مستخدم مسبقاً"}, status=400)
        admin_login = clean_login_id(data.get("admin_login_id"))
        if not admin_login or not data.get("admin_password"):
            return Response({"detail": "بيانات أدمن المستأجر مطلوبة"}, status=400)
        if User.objects.filter(login_id=admin_login).exists():
            return Response({"detail": "رقم دخول الأدمن مستخدم مسبقاً"}, status=400)

        with transaction.atomic():
            tenant = Tenant.objects.create(
                name=data["name"], subdomain=subdomain,
                status=Tenant.Status.ACTIVE, theme=data.get("theme", "teal"),
            )
            admin = User(
                tenant=tenant, role=User.Role.TENANT_ADMIN,
                login_id=admin_login, name=data.get("admin_name", "مدير المستأجر"),
                status=User.Status.ACTIVE, is_staff=True,
            )
            admin.set_password(data["admin_password"])
            admin.save()
            Wallet.objects.create(tenant=tenant, user=admin, balance=Decimal("0"))
        return Response(_tenant_row(tenant), status=http.HTTP_201_CREATED)

    tenants = Tenant.objects.all().order_by("-created_at")
    return Response({
        "count": tenants.count(),
        "results": [_tenant_row(t) for t in tenants],
        "stats": {
            "tenants": tenants.count(),
            "active": tenants.filter(status=Tenant.Status.ACTIVE).count(),
            "dealers": User.objects.filter(role=User.Role.BAYI).count(),
        },
    })


SUBDOMAIN_RE = re.compile(r"^[a-z0-9]([a-z0-9-]{0,30}[a-z0-9])?$")

# أسماء لا تصلح متجراً: بعضها مسارٌ عندنا وبعضها عنوانٌ قائم على النطاق نفسه
RESERVED_SUBDOMAINS = {
    "www", "api", "admin", "static", "assets", "mail", "ftp",
    "app", "platform", "store", "client", "cdn", "ns1", "ns2",
}


@api_view(["PATCH", "DELETE"])
@permission_classes([IsAuthenticated, IsPlatformOwner])
def tenant_detail_view(request, tenant_id):
    """
    تعديل متجر أو حذفه — لمالك المنصّة وحده.

    **الحذف يمحو كل شيء**: الوكلاء ومحافظهم ودفتر الأستاذ والطلبات والفواتير
    (`on_delete=CASCADE` على المستأجر). فلا يقع إلا بكتابة اسم المتجر حرفاً —
    زرٌّ وحده يُضغط بالخطأ، واسمٌ يُكتب لا يُكتب بالخطأ.
    """
    try:
        t = Tenant.objects.get(pk=tenant_id)
    except Tenant.DoesNotExist:
        return Response({"detail": "المستأجر غير موجود"}, status=404)

    if request.method == "DELETE":
        typed = str(request.data.get("confirm") or "").strip()
        if typed != t.subdomain:
            return Response(
                {"detail": f"اكتب «{t.subdomain}» بالضبط لتأكيد الحذف"}, status=400,
            )
        name, orders = t.name, Order.objects.filter(tenant=t).count()
        t.delete()
        return Response({"detail": f"حُذف «{name}» ومعه {orders} طلباً — لا رجعة"})

    data = request.data
    fields = []

    if "name" in data:
        name = str(data["name"] or "").strip()
        if not name:
            return Response({"detail": "اسم المتجر مطلوب"}, status=400)
        t.name = name[:120]
        fields.append("name")

    if "subdomain" in data:
        sub = str(data["subdomain"] or "").strip().lower()
        # نقبل `islam.wtn4.com` ونأخذ منه `islam`: المالك يكتب ما يراه في
        # اللوحة، وكان حفظُه كما هو يُنتج `islam.wtn4.com.wtn4.com`.
        sub = sub.split(".")[0]
        if not SUBDOMAIN_RE.match(sub):
            return Response(
                {"detail": "النطاق: حروف إنجليزية صغيرة وأرقام وشرطات فقط، ولا نقاط"},
                status=400,
            )
        if sub in RESERVED_SUBDOMAINS:
            return Response({"detail": f"«{sub}» اسم محجوز — اختر غيره"}, status=400)
        if Tenant.objects.filter(subdomain=sub).exclude(pk=t.pk).exists():
            return Response({"detail": f"«{sub}» مستعمل لمتجر آخر"}, status=400)
        t.subdomain = sub
        fields.append("subdomain")

    # كلمة سرّ صاحب المتجر — المخرج حين ينساها، وقد كان لا مخرج له إلا الخادم.
    # فارغةً تعني «لا تبدّل»، فحفظُ الاسم وحده لا يمسّ الحساب.
    admin_password = str(data.get("admin_password") or "")
    if admin_password:
        admin = (
            User.objects
            .filter(tenant=t, role=User.Role.TENANT_ADMIN)
            .order_by("id")
            .first()
        )
        if admin is None:
            return Response({"detail": "لا حساب صاحب متجر لهذا المتجر"}, status=400)
        if len(admin_password) < 5:
            return Response({"detail": "كلمة السر قصيرة (5 أحرف على الأقل)"}, status=400)
        admin.set_password(admin_password)
        admin_fields = ["password"]
        # كلمة سرّ جديدة تفتح القفل دائماً — كما في تعديل الوكيل (core/views.py):
        # فتحٌ بلا تبديل يعيد الحساب بكلمةٍ ثبت أن أحدهم يخمّنها.
        if admin.is_locked or admin.failed_login_count:
            admin.locked_at = None
            admin.failed_login_count = 0
            admin_fields += ["locked_at", "failed_login_count"]
        admin.save(update_fields=admin_fields)

    if fields:
        t.save(update_fields=fields)
    return Response(_tenant_row(t))


@api_view(["POST"])
@permission_classes([IsAuthenticated, IsPlatformOwner])
def tenant_status_view(request, tenant_id, action):
    """تعليق/تفعيل مستأجر."""
    if action not in ("suspend", "activate"):
        return Response({"detail": "إجراء غير معروف"}, status=400)
    try:
        t = Tenant.objects.get(pk=tenant_id)
    except Tenant.DoesNotExist:
        return Response({"detail": "المستأجر غير موجود"}, status=404)
    t.status = Tenant.Status.SUSPENDED if action == "suspend" else Tenant.Status.ACTIVE
    t.save(update_fields=["status"])
    return Response(_tenant_row(t))


@api_view(["POST"])
@permission_classes([IsAuthenticated, IsPlatformOwner])
def tenant_subscription_view(request, tenant_id):
    """اشتراك المستأجر: ضبط الأسعار (شهري/سنوي) وتفعيل/إلغاء خطة — لمالك المنصّة."""
    from datetime import datetime, timedelta
    from django.utils import timezone

    try:
        t = Tenant.objects.get(pk=tenant_id)
    except Tenant.DoesNotExist:
        return Response({"detail": "المستأجر غير موجود"}, status=404)

    op = request.data.get("op", "prices")

    if op == "prices":
        try:
            t.sub_monthly_price = Decimal(str(request.data.get("monthly_price", t.sub_monthly_price)))
            t.sub_yearly_price = Decimal(str(request.data.get("yearly_price", t.sub_yearly_price)))
        except Exception:
            return Response({"detail": "أسعار غير صحيحة"}, status=400)
        t.save(update_fields=["sub_monthly_price", "sub_yearly_price"])

    elif op == "activate":
        plan = request.data.get("plan")
        if plan not in (Tenant.SubPlan.MONTHLY, Tenant.SubPlan.YEARLY):
            return Response({"detail": "خطة غير معروفة"}, status=400)
        today = timezone.localdate()
        # التمديد من نهاية الاشتراك الحالي إن كان ساري المفعول، وإلا من اليوم
        base = t.sub_expires_at if (t.sub_expires_at and t.sub_expires_at >= today) else today
        days = 30 if plan == Tenant.SubPlan.MONTHLY else 365
        t.sub_plan = plan
        t.sub_started_at = today
        t.sub_expires_at = base + timedelta(days=days)
        t.save(update_fields=["sub_plan", "sub_started_at", "sub_expires_at"])
        # فاتورة اشتراك عن الفترة المُضافة
        amount = t.sub_monthly_price if plan == Tenant.SubPlan.MONTHLY else t.sub_yearly_price
        Invoice.objects.create(
            tenant=t, plan=plan, amount=amount,
            period_start=base, period_end=t.sub_expires_at,
        )

    elif op == "policy":
        # سياسة الاشتراك لهذا المتجر: مهلة السماح، والإعفاء من المنع أصلاً
        try:
            grace = int(request.data.get("grace_days", t.sub_grace_days))
        except (TypeError, ValueError):
            return Response({"detail": "أيام السماح يجب أن تكون رقماً"}, status=400)
        if not 0 <= grace <= 90:
            return Response({"detail": "أيام السماح بين صفر و90"}, status=400)
        t.sub_grace_days = grace
        if "enforce" in request.data:
            t.sub_enforce = bool(request.data["enforce"])
        t.save(update_fields=["sub_grace_days", "sub_enforce"])

    elif op == "expires":
        # ضبط تاريخ الانتهاء مباشرةً — بلا فاتورة ولا خطة. لتصحيح خطأ أو
        # لمنح مدّة بقرارٍ منك، دون أن تُحسب اشتراكاً مدفوعاً.
        raw = str(request.data.get("expires_at") or "").strip()
        if not raw:
            t.sub_expires_at = None
        else:
            try:
                t.sub_expires_at = datetime.strptime(raw, "%Y-%m-%d").date()
            except ValueError:
                return Response({"detail": "التاريخ بصيغة YYYY-MM-DD"}, status=400)
        t.save(update_fields=["sub_expires_at"])

    elif op == "cancel":
        t.sub_plan = Tenant.SubPlan.NONE
        t.sub_started_at = None
        t.sub_expires_at = None
        t.save(update_fields=["sub_plan", "sub_started_at", "sub_expires_at"])

    else:
        return Response({"detail": "عملية غير معروفة"}, status=400)

    return Response(_tenant_row(t))


@api_view(["GET"])
@permission_classes([IsAuthenticated, IsPlatformOwner])
def invoices_view(request):
    """كل فواتير الاشتراكات — لمالك المنصّة، مع فلتر حالة."""
    qs = Invoice.objects.select_related("tenant").all()
    st = request.query_params.get("status")
    if st in ("paid", "unpaid"):
        qs = qs.filter(status=st)
    rows = [_invoice_row(i) for i in qs]
    totals = {
        "count": len(rows),
        "unpaid": sum(1 for i in qs if i.status == Invoice.Status.UNPAID),
        "total_amount": str(sum((i.amount for i in qs), Decimal("0"))),
    }
    return Response({"results": rows, "totals": totals})


@api_view(["POST"])
@permission_classes([IsAuthenticated, IsPlatformOwner])
def invoice_status_view(request, invoice_id, action):
    """تعليم فاتورة مدفوعة/غير مدفوعة."""
    if action not in ("paid", "unpaid"):
        return Response({"detail": "إجراء غير معروف"}, status=400)
    try:
        inv = Invoice.objects.select_related("tenant").get(pk=invoice_id)
    except Invoice.DoesNotExist:
        return Response({"detail": "الفاتورة غير موجودة"}, status=404)
    inv.status = Invoice.Status.PAID if action == "paid" else Invoice.Status.UNPAID
    inv.save(update_fields=["status"])
    return Response(_invoice_row(inv))


@api_view(["GET", "PUT"])
@permission_classes([IsAuthenticated, IsPlatformOwner])
def platform_announcement_view(request):
    """كتابة/تعديل إعلان المنصّة (يظهر لكل أصحاب المتاجر) — لمالك المنصّة."""
    from core.models import PlatformAnnouncement
    a = PlatformAnnouncement.get()
    if request.method == "PUT":
        a.message = (request.data.get("message") or "").strip()
        a.ticker = (request.data.get("ticker") or "").strip()
        a.save(update_fields=["message", "ticker", "updated_at"])
    return Response({"message": a.message, "ticker": a.ticker})
