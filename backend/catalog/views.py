"""API للكتالوج: الألعاب والمنتجات ومجموعات الأسعار — معزولة لكل مستأجر."""
from decimal import Decimal, InvalidOperation

from rest_framework import viewsets
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core import currency
from core.models import User
from providers.models import Provider
from django.db import transaction
from .models import Game, LibraryGame, PriceGroup, Product, ProductLink, ProductPrice
from .serializers import (
    GameDetailSerializer, GameSerializer, PriceGroupSerializer, ProductSerializer,
)
from .services import catalog_index, catalog_match, price_from_margin, rank_providers


class GameViewSet(viewsets.ModelViewSet):
    """CRUD الألعاب ضمن مستأجر المستخدم الحالي."""
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Game.objects.filter(tenant=self.request.user.tenant)

    def get_serializer_class(self):
        return GameDetailSerializer if self.action == "retrieve" else GameSerializer

    def perform_create(self, serializer):
        serializer.save(tenant=self.request.user.tenant)

    def destroy(self, request, *args, **kwargs):
        """
        حذف اللعبة مع باقاتها — لصاحب المتجر وحده.

        بلا طلبات ⇐ تُحذف نهائياً. ولها طلبات ⇐ تُؤرشف هي وباقاتها: تختفي من
        كل مكان، ويبقى سجلّ الطلبات سليماً بأسمائه.
        """
        from orders.models import Order

        if not _require_tenant_admin(request):
            return Response({"detail": "الحذف لصاحب المتجر فقط"}, status=403)
        game = self.get_object()
        if Order.objects.filter(game=game).exists():
            with transaction.atomic():
                Product.objects.filter(game=game).update(is_archived=True, status=Product.Status.PASSIVE)
                game.is_archived = True
                game.status = Game.Status.PASSIVE
                game.save(update_fields=["is_archived", "status"])
            return Response({"deleted": True, "archived": True})
        game.delete()
        return Response({"deleted": True, "archived": False})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def price_matrix_view(request):
    """مصفوفة الأسعار: منتجات (مجمّعة حسب اللعبة) × مجموعات الأسعار.
    كل خلية = السعر الصريح للمجموعة، أو السعر الموصى كافتراضي."""
    tenant = request.user.tenant
    groups = list(PriceGroup.objects.filter(tenant=tenant).order_by("id"))

    # جميع الأسعار الصريحة {(product_id, group_id): صفّ السعر}
    explicit = {
        (pp.product_id, pp.price_group_id): pp
        for pp in ProductPrice.objects.filter(tenant=tenant)
    }

    games = []
    products = (
        Product.objects.filter(tenant=tenant).select_related("game").order_by("game__sort_order", "sort_order")
    )
    current = None
    for p in products:
        if current is None or current["game_id"] != p.game_id:
            current = {"game_id": p.game_id, "game_name": p.game.name, "products": []}
            games.append(current)
        cells = {}
        for g in groups:
            row = explicit.get((p.id, g.id))
            cells[g.id] = {
                "price": str(row.price) if row is not None else str(p.recommended_price),
                "custom": row is not None,
                # القاعدة المرتبطة — الجدول يعرضها ليعرف المالك أي خلية تتبع
                # التكلفة وأيّها رقمٌ يدويّ جامد
                "margin": (
                    {"mode": row.margin_mode, "value": str(row.margin_value)}
                    if row is not None and row.linked else None
                ),
            }
        current["products"].append({
            "id": p.id,
            "name": p.name,
            "cost_price": str(p.cost_price),
            "recommended_price": str(p.recommended_price),
            "prices": cells,
        })

    return Response({
        "groups": [{"id": g.id, "name": g.name} for g in groups],
        "games": games,
    })


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def set_price_view(request):
    """تعيين/تحديث سعر منتج لمجموعة (خلية في المصفوفة)."""
    tenant = request.user.tenant
    try:
        product = Product.objects.get(pk=request.data.get("product"), tenant=tenant)
        group = PriceGroup.objects.get(pk=request.data.get("price_group"), tenant=tenant)
        price = Decimal(str(request.data.get("price")))
    except (Product.DoesNotExist, PriceGroup.DoesNotExist):
        return Response({"detail": "المنتج أو المجموعة غير موجود"}, status=404)
    except (InvalidOperation, TypeError):
        return Response({"detail": "سعر غير صحيح"}, status=400)

    # التعديل اليدوي يفكّ ارتباط الخلية بقاعدة التسعير الجماعي: المالك كتب
    # رقماً بيده، فلا يجوز أن يمحوه أوّلُ تغيير في التكلفة.
    pp, _ = ProductPrice.objects.update_or_create(
        tenant=tenant, product=product, price_group=group,
        defaults={"price": price, "margin_mode": "", "margin_value": None},
    )
    return Response({"product": product.id, "price_group": group.id, "price": str(pp.price)})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def bulk_price_view(request):
    """
    تسعير جماعي: سعر مجموعة أسعار بعينها = **تكلفة** كل منتج + هامش.

    الأساس هو التكلفة لا السعر الحالي، فتكرار العملية بالقيمة نفسها يعطي
    النتيجة نفسها — لو كان الأساس السعر الحالي لضاعف كلُّ ضغطة الزيادةَ.

    {price_group, products: [ids] | فارغ = الكل, mode: "percent"|"fixed", value}
    """
    tenant = request.user.tenant
    group = PriceGroup.objects.filter(pk=request.data.get("price_group"), tenant=tenant).first()
    if group is None:
        return Response({"detail": "مجموعة الأسعار غير موجودة"}, status=404)

    mode = request.data.get("mode")
    if mode not in ("percent", "fixed"):
        return Response({"detail": "نوع الهامش غير صحيح"}, status=400)
    try:
        value = Decimal(str(request.data.get("value")).replace(",", "."))
    except (InvalidOperation, TypeError, ValueError):
        return Response({"detail": "القيمة غير صحيحة"}, status=400)

    products = Product.objects.filter(tenant=tenant)
    ids = request.data.get("products") or []
    if ids:
        products = products.filter(id__in=ids)
    products = list(products.order_by("game__sort_order", "sort_order"))
    if not products:
        return Response({"detail": "لم يُحدَّد أي منتج"}, status=400)

    # منتج بتكلفة صفر لا يُسعَّر: أي هامش نسبي عليه يعطي صفراً — أي بيعاً
    # مجّانياً بلا أن ينتبه أحد. يُترك ويُذكر اسمه ليضبط المالك تكلفته.
    priced, zero_cost, negative = [], [], []
    for p in products:
        if p.cost_price <= 0:
            zero_cost.append(p.name)
            continue
        price = price_from_margin(p.cost_price, mode, value)
        if price is None:
            negative.append(p.name)
            continue
        priced.append((p, price))

    if negative:
        return Response(
            {"detail": f"القيمة تجعل سعر {len(negative)} باقة سالباً — لم يُغيَّر شيء"},
            status=400,
        )
    if not priced:
        return Response(
            {"detail": "كل الباقات المختارة تكلفتها صفر — اضبط تكاليفها أولاً"}, status=400
        )

    # تُحفظ القاعدة مع السعر لا السعر وحده: الخلية تبقى مرتبطة بالتكلفة
    # فتتبعها كلّما تغيّرت، حتى يفكّها تسعيرٌ جماعي جديد أو تعديل يدويّ.
    with transaction.atomic():
        for p, price in priced:
            ProductPrice.objects.update_or_create(
                tenant=tenant, product=p, price_group=group,
                defaults={"price": price, "margin_mode": mode, "margin_value": value},
            )

    return Response({
        "updated": len(priced),
        "group": group.name,
        "skipped_zero_cost": zero_cost,
    })


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def refresh_costs_view(request):
    """
    تحديث تكلفة الباقات من كتالوج مزوّد بعينه — تصير تكلفتُنا سعرَه.

    يُجلب الكتالوج **مرّة واحدة** ثم تُطابَق الروابط محلياً. وسعر المزوّد
    وسعرُه بعملته هو (`Provider.currency`) فيُحوَّل إلى عملة الدفتر قبل الحفظ.

    {provider, products: [ids] | فارغ = الكل}
    """
    from providers.adapters.registry import adapter_for

    tenant = request.user.tenant
    provider = Provider.objects.filter(pk=request.data.get("provider"), tenant=tenant).first()
    if provider is None:
        return Response({"detail": "المزوّد غير موجود"}, status=404)

    adapter = adapter_for(provider)
    if adapter is None:
        return Response({"detail": f"«{provider.name}» منفّذ يدوي — لا كتالوج له"}, status=400)

    prov_cur = currency.currency_of(provider)
    if currency.rate_of(tenant, prov_cur) <= 0:
        return Response(
            {"detail": f"لا سعر صرف مضبوط لـ{prov_cur} (عملة «{provider.name}») — "
                       f"اضبطه في «الإعدادات ← أسعار الصرف» أولاً"},
            status=400,
        )

    links = ProductLink.objects.filter(
        tenant=tenant, provider=provider
    ).select_related("product")
    ids = request.data.get("products") or []
    if ids:
        links = links.filter(product_id__in=ids)
    links = list(links)
    if not links:
        return Response(
            {"detail": f"لا باقات مربوطة بـ«{provider.name}» ضمن ما اخترت — اربطها من «ربط الباقات»"},
            status=400,
        )

    try:
        catalog = adapter.list_packages(provider.config or {}, provider=provider)
    except Exception as e:
        return Response({"detail": f"تعذّر جلب كتالوج «{provider.name}»: {e}"}, status=400)
    if not catalog.ok:
        return Response({"detail": catalog.note or "تعذّر جلب الكتالوج"}, status=400)

    index = catalog_index(catalog.packages)
    updated, skipped = [], []
    with transaction.atomic():
        for link in links:
            found, why = catalog_match(index, link)
            if not found:
                skipped.append({"name": link.product.name, "note": why})
                continue
            cost = currency.from_provider(tenant, str(found.get("price") or "").strip(), provider)
            if cost is None or cost <= 0:
                skipped.append({"name": link.product.name, "note": "المزوّد لا يعطي سعراً لها"})
                continue

            product = link.product
            before = product.cost_price
            if before != cost:
                product.cost_price = cost
                product.save(update_fields=["cost_price"])
            # السعر المرجعي لحماية الخسارة — بعملة الدفتر كبقيّة أرقام القاعدة
            extra = dict(link.extra or {})
            extra["price"] = str(cost)
            link.extra = extra
            link.package_name = str(found.get("name") or "")[:200] or link.package_name
            link.save(update_fields=["extra", "package_name", "updated_at"])

            updated.append({"name": product.name, "before": str(before), "after": str(cost)})

    return Response({
        "provider": provider.name,
        "updated": updated,
        "skipped": skipped,
        "currency": currency.base_currency(tenant),
    })


CHAIN_FIELDS = ["provider", "provider_alt1", "provider_alt2"]


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def auto_route_view(request):
    """
    توجيه باقات لعبة تلقائياً حسب السعر: الأرخص رئيسياً ثم الأغلى بديلاً.

    يعمل بخطوتين: `apply=false` يعيد الخطة للمعاينة، و`apply=true` ينفّذها.
    المعاينة ليست ترفاً — التوجيه يقرّر أين تُنفَق أموال كل طلب لاحق.

    {game: <id> | فارغ = كل الألعاب, apply: bool}
    """
    from providers.adapters.registry import adapter_for

    tenant = request.user.tenant

    # المزوّدون المرشَّحون: نشطون ولهم محوّل آلي (المنفّذ اليدوي لا يُوجَّه إليه)
    providers_by_id = {
        p.id: p for p in Provider.objects.filter(tenant=tenant, status=Provider.Status.ACTIVE)
        if adapter_for(p) is not None
    }
    if not providers_by_id:
        return Response({"detail": "لا مزوّدين آليين نشطين"}, status=400)

    products = Product.objects.filter(tenant=tenant).select_related("game")
    game_id = request.data.get("game")
    if game_id:
        products = products.filter(game_id=game_id)
    products = list(products.order_by("game__sort_order", "sort_order", "id"))
    if not products:
        return Response({"detail": "لا باقات في هذا الاختيار"}, status=400)

    links_by_product = {}
    for link in ProductLink.objects.filter(tenant=tenant, product__in=products):
        links_by_product.setdefault(link.product_id, []).append(link)

    apply = bool(request.data.get("apply"))
    plan, changes = [], []
    for p in products:
        before = [
            providers_by_id[pid].name if pid in providers_by_id else "—"
            for pid in (getattr(p, f + "_id") for f in CHAIN_FIELDS) if pid
        ]
        ranked = rank_providers(p, links_by_product.get(p.id, []), providers_by_id)
        chain = ranked[:3]

        row = {
            "id": p.id, "name": p.name, "game": p.game.name,
            "was_manual": p.execution_type == Product.Execution.MANUAL,
            "before": before,
            "after": [{
                "id": r["provider"].id,
                "name": r["provider"].name,
                "price": str(r["price"]) if r["price"] is not None else None,
                "loss": r["tier"] == 2,
            } for r in chain],
            "dropped": len(ranked) - len(chain),
            "note": "" if ranked else "بلا ربط بأي مزوّد آلي — اربطها من «ربط الباقات»",
        }
        new_ids = [r["provider"].id for r in chain]
        old_ids = [getattr(p, f + "_id") for f in CHAIN_FIELDS]
        row["changed"] = ranked and (
            new_ids + [None] * (3 - len(new_ids)) != old_ids
            or p.execution_type == Product.Execution.MANUAL
        )
        plan.append(row)
        if row["changed"]:
            changes.append((p, new_ids))

    if apply:
        with transaction.atomic():
            for p, new_ids in changes:
                for field, pid in zip(CHAIN_FIELDS, new_ids + [None] * (3 - len(new_ids))):
                    setattr(p, field + "_id", pid)
                p.execution_type = Product.Execution.AUTO
                p.save(update_fields=[*CHAIN_FIELDS, "execution_type"])

    return Response({
        "applied": apply,
        "changed": len(changes),
        "total": len(plan),
        "plan": plan,
    })


class PriceGroupViewSet(viewsets.ModelViewSet):
    """CRUD مجموعات الأسعار (Fiyat Grupları)."""
    serializer_class = PriceGroupSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return PriceGroup.objects.filter(tenant=self.request.user.tenant)

    def perform_create(self, serializer):
        serializer.save(tenant=self.request.user.tenant)


class ProductViewSet(viewsets.ModelViewSet):
    """CRUD المنتجات؛ يدعم الفلترة بـ ?game=<id>."""
    serializer_class = ProductSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = Product.objects.filter(tenant=self.request.user.tenant)
        game_id = self.request.query_params.get("game")
        if game_id:
            qs = qs.filter(game_id=game_id)
        return qs

    def perform_create(self, serializer):
        serializer.save(tenant=self.request.user.tenant)

    def destroy(self, request, *args, **kwargs):
        """حذف باقة — ولها طلبات سابقة ⇐ تُؤرشف (كاللعبة)."""
        from orders.models import Order

        if not _require_tenant_admin(request):
            return Response({"detail": "الحذف لصاحب المتجر فقط"}, status=403)
        product = self.get_object()
        if Order.objects.filter(product=product).exists():
            product.is_archived = True
            product.status = Product.Status.PASSIVE
            product.save(update_fields=["is_archived", "status"])
            return Response({"deleted": True, "archived": True})
        product.delete()
        return Response({"deleted": True, "archived": False})


def _require_tenant_admin(request):
    u = request.user
    return u.role == User.Role.TENANT_ADMIN and u.tenant_id is not None


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def library_browse_view(request):
    """تصفّح المكتبة العالمية لصاحب المتجر — مع علامة "مستورَد" لكل لعبة."""
    if not _require_tenant_admin(request):
        return Response({"detail": "مخصّص لصاحب المتجر"}, status=403)
    imported = set(
        Game.objects.filter(tenant=request.user.tenant)
        .exclude(master_library_uuid="")
        .values_list("master_library_uuid", flat=True)
    )
    from .library_sources import fingerprint, matching_provider_names
    mine = matching_provider_names(request.user.tenant)
    rows = []
    for g in LibraryGame.objects.filter(is_active=True).select_related("source").prefetch_related("products"):
        active_products = [p for p in g.products.all() if p.is_active]
        rows.append({
            "id": g.id,
            "uuid": g.uuid,
            "name": g.name,
            "image_url": g.image_url,
            "description": g.description,
            "require_player_id": g.require_player_id,
            "product_count": len(active_products),
            "products": [{
                "name": p.name, "suggested_cost": str(p.suggested_cost),
                "suggested_price": str(p.suggested_price), "kupur": p.kupur,
            } for p in active_products],
            "is_imported": g.uuid in imported,
            # مزوّدو هذا المتجر الذين تُربط بهم الباقات تلقائياً عند الاستيراد
            "auto_link": mine.get(fingerprint(g.source.code, g.source.config), []) if g.source else [],
        })
    return Response({"count": len(rows), "results": rows})


def _norm(name: str) -> str:
    """اسم للمقارنة: بلا مسافات ولا حالة أحرف — «PUBG Mobile» و«pubgmobile» سواء."""
    return "".join((name or "").split()).lower()


def _library_game_for(game):
    """
    لعبة المكتبة التي تُغذّي هذه اللعبة بأرقام الربط.

    الأصل `master_library_uuid`. وإن كان فارغاً — لعبة أُنشئت من بذرة الكتالوج
    أو بيد صاحب المتجر — نبحث بالاسم: تطابقاً ثم احتواءً **وحيداً**، فتجد
    «PUBG Mobile» نظيرتها «PUBG Mobile UC». وعند العثور نثبّت الرابط فلا يتكرّر
    التخمين ولا يتبدّل المصدر من وراء المالك.
    """
    if game.master_library_uuid:
        lib = LibraryGame.objects.filter(uuid=game.master_library_uuid).first()
        if lib is not None:
            return lib

    candidates = list(LibraryGame.objects.filter(is_active=True))
    target = _norm(game.name)
    matches = [g for g in candidates if _norm(g.name) == target]
    if not matches and target:
        matches = [
            g for g in candidates
            if target in _norm(g.name) or _norm(g.name) in target
        ]
    if len(matches) != 1:
        return None

    lib = matches[0]
    game.master_library_uuid = lib.uuid
    if not game.image_url and lib.image_url:
        game.image_url = lib.image_url
    game.save(update_fields=["master_library_uuid", "image_url"])
    _adopt_kupur_from_library(game, lib)
    return lib


def _adopt_kupur_from_library(game, lib) -> int:
    """
    يمنح باقات المتجر أرقامَها من المكتبة بمطابقة الاسم.

    بدونه تُقرأ لعبةٌ فيها «60 UC» بلا رقم وكأن رقم 60 ما زال متاحاً، فيضيفه
    المالك ثانيةً ويصير عنده باقتان لباقة واحدة. نملأ **الفارغ فقط** ولا نلمس
    رقماً موضوعاً، ولا نمنح رقماً أخذته باقة أخرى.
    """
    products = list(game.products.all())
    taken = {p.kupur.strip() for p in products if p.kupur.strip()}
    by_name = {}
    for lp in lib.products.filter(is_active=True):
        if lp.kupur.strip() and lp.kupur.strip() not in taken:
            by_name.setdefault(_norm(lp.name), lp.kupur.strip())

    adopted = 0
    for p in products:
        if p.kupur.strip():
            continue
        kupur = by_name.pop(_norm(p.name), None)
        if kupur:
            p.kupur = kupur
            p.save(update_fields=["kupur"])
            adopted += 1
    return adopted


def _library_games_payload():
    return [
        {"id": g.id, "name": g.name,
         "packages": g.products.filter(is_active=True).count()}
        for g in LibraryGame.objects.filter(is_active=True).order_by("sort_order", "id")
    ]


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def link_game_to_library_view(request, game_id):
    """
    ربط لعبة المتجر بنظيرتها في المكتبة العالمية — مرّة واحدة يدوياً.

    مخرج اللعبة التي لم يجد اسمُها نظيراً: يختار صاحب المتجر النظير فتصير أرقام
    الربط متاحةً لها. الربط لا يمسّ باقاته القائمة، إنما يفتح له قائمة الأرقام.
    """
    tenant = request.user.tenant
    try:
        game = Game.objects.get(pk=game_id, tenant=tenant)
    except Game.DoesNotExist:
        return Response({"detail": "اللعبة غير موجودة"}, status=404)

    lib = LibraryGame.objects.filter(pk=request.data.get("library_game")).first()
    if lib is None:
        return Response({"detail": "لعبة المكتبة غير موجودة"}, status=404)

    game.master_library_uuid = lib.uuid
    game.save(update_fields=["master_library_uuid"])
    adopted = _adopt_kupur_from_library(game, lib)
    return Response({"linked": True, "library_game": lib.name, "adopted": adopted})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def game_library_packages_view(request, game_id):
    """
    أرقام الربط المتاحة لهذه اللعبة من المكتبة العالمية.

    رقم الربط جسرٌ بين الباقات، ومصدره المكتبة العالمية **حصراً** — لا كتابة
    يدوية. نُرجع ما عرّفه مالك المنصّة لهذه اللعبة ولم يُؤخَذ بعد: فإن حُذفت باقة
    عاد رقمها إلى القائمة، ولا يظهر رقم مأخوذ مرّتين.

    `linked=false` تعني لعبةً بلا نظير في المكتبة، ومعها تصل `library_games`
    ليختار صاحب المتجر نظيرها مرّةً واحدة.
    """
    tenant = request.user.tenant
    try:
        game = Game.objects.prefetch_related("products").get(pk=game_id, tenant=tenant)
    except Game.DoesNotExist:
        return Response({"detail": "اللعبة غير موجودة"}, status=404)

    lib = _library_game_for(game)
    if lib is None:
        return Response({
            "linked": False, "results": [], "library_games": _library_games_payload(),
        })

    used = {p.kupur.strip() for p in game.products.all() if p.kupur.strip()}
    rows = [
        {
            "kupur": p.kupur.strip(),
            "name": p.name,
            "suggested_cost": str(p.suggested_cost),
            "suggested_price": str(p.suggested_price),
            "is_parcali": p.is_parcali,
            "execution_type": p.execution_type,
            "description": p.description,
        }
        for p in lib.products.filter(is_active=True).order_by("sort_order", "id")
        if p.kupur.strip() and p.kupur.strip() not in used
    ]
    return Response({"linked": True, "library_game": lib.name, "results": rows})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def library_import_view(request, library_game_id):
    """استيراد لعبة عالمية + كل باقاتها الفعّالة إلى متجر صاحب المتجر (نسخ snapshot)."""
    if not _require_tenant_admin(request):
        return Response({"detail": "مخصّص لصاحب المتجر"}, status=403)
    tenant = request.user.tenant

    # (1) snapshot من المكتبة العالمية
    try:
        lib = LibraryGame.objects.prefetch_related("products").get(
            pk=library_game_id, is_active=True
        )
    except LibraryGame.DoesNotExist:
        return Response({"detail": "غير موجود", "code": "not_found"}, status=404)

    # (2) منع الاستيراد المكرر عبر uuid المصدر
    if Game.objects.filter(tenant=tenant, master_library_uuid=lib.uuid).exists():
        return Response(
            {"detail": "مستورَد مسبقاً", "code": "already_imported"}, status=400
        )

    packages = [p for p in lib.products.all() if p.is_active]

    # (3) نسخ (clone) داخل معاملة ذرّية
    with transaction.atomic():
        last = Game.objects.filter(tenant=tenant).order_by("-sort_order").first()
        game = Game.objects.create(
            tenant=tenant,
            name=lib.name,
            image_url=lib.image_url,
            description=lib.description,
            require_player_id=lib.require_player_id,
            kurulu_sale=lib.kurulu_sale,
            toplu_sale=lib.toplu_sale,
            sms_template=lib.sms_template,
            master_library_uuid=lib.uuid,   # الرابط المنطقي بالمصدر
            sort_order=(last.sort_order + 1) if last else 0,
        )
        for i, p in enumerate(packages):
            Product.objects.create(
                tenant=tenant, game=game, name=p.name,
                cost_price=p.suggested_cost, recommended_price=p.suggested_price,
                kupur=p.kupur, is_parcali=p.is_parcali,
                execution_type=p.execution_type, description=p.description,
                sort_order=i,
            )

    # (4) باقات مصدرٍ يملكه المتجر مزوّداً تُربط به الآن — لا يربطها صاحبها بيده
    from .library_sources import autolink
    linked = autolink(tenant, games=[game])

    return Response(
        GameDetailSerializer(game).data | {"imported_products": len(packages), "autolink": linked},
        status=201,
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def library_autolink_view(request):
    """ربطٌ تلقائي لكل ما استُورد من المكتبة — لمن أضاف المزوّد بعد الاستيراد."""
    from .library_sources import autolink

    if not _require_tenant_admin(request):
        return Response({"detail": "مخصّص لصاحب المتجر"}, status=403)
    return Response(autolink(request.user.tenant))


@api_view(["GET", "POST", "DELETE"])
@permission_classes([IsAuthenticated])
def product_links_view(request):
    """
    ربط الباقات: رقم ربط لكل (منتج × مزوّد).

    GET    → كل روابط المستأجر: [{product, provider, package_id, package_name, extra}]
    POST   → إنشاء/تحديث ربط: {product, provider, package_id, package_name?, extra?}
    DELETE → فكّ الربط: {product, provider}
    """
    tenant = request.user.tenant

    if request.method == "GET":
        rows = ProductLink.objects.filter(tenant=tenant).values(
            "product", "provider", "package_id", "package_name", "extra"
        )
        return Response(list(rows))

    try:
        product = Product.objects.get(pk=request.data.get("product"), tenant=tenant)
        provider = Provider.objects.get(pk=request.data.get("provider"), tenant=tenant)
    except (Product.DoesNotExist, Provider.DoesNotExist):
        return Response({"detail": "المنتج أو المزوّد غير موجود"}, status=404)

    if request.method == "DELETE":
        ProductLink.objects.filter(tenant=tenant, product=product, provider=provider).delete()
        return Response(status=204)

    package_id = str(request.data.get("package_id") or "").strip()
    if not package_id:
        return Response({"detail": "رقم الربط مطلوب"}, status=400)

    extra = request.data.get("extra") or {}
    if not isinstance(extra, dict):
        extra = {}
    # السعر يصل من كتالوج المزوّد بعملته — يُحوَّل هنا فلا يدخل القاعدة
    # رقمٌ بعملة غير عملة الدفتر.
    if extra.get("price") not in (None, ""):
        converted = currency.from_provider(tenant, extra["price"], provider)
        extra = {**extra, "price": str(converted)} if converted is not None else (
            {k: v for k, v in extra.items() if k != "price"}
        )

    link, _ = ProductLink.objects.update_or_create(
        tenant=tenant, product=product, provider=provider,
        defaults={
            "package_id": package_id,
            "package_name": str(request.data.get("package_name") or "")[:200],
            "extra": extra,
        },
    )
    return Response({
        "product": link.product_id, "provider": link.provider_id,
        "package_id": link.package_id, "package_name": link.package_name,
        "extra": link.extra,
    }, status=201)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def refresh_link_prices_view(request):
    """
    تحديث أسعار كل الباقات المربوطة من كتالوجات المزوّدين.

    كتالوج كل مزوّد يُجلب **مرّة واحدة** ثم تُطابَق كل روابطه محلياً — لا طلب
    شبكي لكل باقة. السعر المحفوظ في `extra.price` هو مرجع حماية الخسارة،
    فتقادُمه يعني أن الحماية تحرس بسعر لم يعد قائماً.
    """
    from providers.adapters.registry import adapter_for

    tenant = request.user.tenant
    links = list(ProductLink.objects.filter(tenant=tenant).select_related("provider"))
    if not links:
        return Response({"detail": "لا توجد باقات مربوطة"}, status=400)

    by_provider = {}
    for link in links:
        by_provider.setdefault(link.provider, []).append(link)

    report, total = [], 0
    for provider, rows in by_provider.items():
        adapter = adapter_for(provider)
        if adapter is None:
            report.append({"provider": provider.name, "ok": False,
                           "note": "منفّذ يدوي — لا كتالوج"})
            continue
        try:
            catalog = adapter.list_packages(provider.config or {}, provider=provider)
        except Exception as e:
            report.append({"provider": provider.name, "ok": False, "note": f"خطأ محوّل: {e}"})
            continue
        if not catalog.ok:
            report.append({"provider": provider.name, "ok": False,
                           "note": catalog.note or "تعذّر جلب الكتالوج"})
            continue

        index = catalog_index(catalog.packages)
        changed = 0
        for link in rows:
            found, _ = catalog_match(index, link)
            if not found:
                continue
            extra = dict(link.extra or {})
            # سعر المزوّد بعملته — يُحوَّل إلى عملة الدفتر قبل الحفظ، وإلا
            # قارنته حماية الخسارة بسعر بيعٍ بعملة أخرى فرأت كل طلب خاسراً.
            converted = currency.from_provider(tenant, str(found.get("price") or "").strip(), provider)
            price = str(converted) if converted is not None else ""
            name = str(found.get("name") or "")[:200]
            if not price or (extra.get("price") == price and link.package_name == name):
                continue
            extra["price"] = price
            link.extra = extra
            link.package_name = name or link.package_name
            link.save(update_fields=["extra", "package_name", "updated_at"])
            changed += 1
        total += changed
        report.append({"provider": provider.name, "ok": True, "updated": changed,
                       "checked": len(rows), "catalog": len(index)})

    return Response({"updated": total, "providers": report})


# ════════════════ رفع الصور ════════════════
# النوع يُعرف من أوّل بايتات الملف لا من اسمه ولا من ترويسة المتصفّح:
# ملفٌّ يدّعي أنه صورة وهو HTML أو SVG يصير صفحةً تُفتح من نطاق الموقع نفسه.
_IMAGE_MAX_BYTES = 1_500_000


def _sniff_image(head: bytes) -> str:
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if head.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp"
    if head[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    return ""


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def image_upload_view(request):
    """رفع صورة (multipart، الحقل `file`) ⇐ {"url": "/api/catalog/img/<key>/"}."""
    from .models import ImageAsset

    if request.user.role not in (User.Role.PLATFORM_OWNER, User.Role.TENANT_ADMIN):
        return Response({"detail": "رفع الصور لمالك المنصّة وأصحاب المتاجر"}, status=403)
    f = request.FILES.get("file")
    if f is None:
        return Response({"detail": "لم يصل ملف"}, status=400)
    if f.size > _IMAGE_MAX_BYTES:
        return Response({"detail": "الصورة كبيرة — الحدّ 1.5 ميغابايت"}, status=400)
    data = f.read()
    kind = _sniff_image(data[:16])
    if not kind:
        return Response({"detail": "الملف ليس صورة (PNG · JPG · WEBP · GIF)"}, status=400)
    img = ImageAsset.objects.create(content_type=kind, data=data, size=len(data), uploaded_by=request.user)
    return Response({"url": img.url, "size": img.size}, status=201)


def image_view(request, key):
    """الصورة نفسها — عامّة (تظهر للوكيل ولصفحة الدخول)، وتُخزَّن في المتصفّح سنة."""
    from django.http import Http404, HttpResponse
    from .models import ImageAsset

    img = ImageAsset.objects.filter(key=key).only("content_type", "data").first()
    if img is None:
        raise Http404
    resp = HttpResponse(bytes(img.data), content_type=img.content_type)
    resp["Cache-Control"] = "public, max-age=31536000, immutable"
    resp["X-Content-Type-Options"] = "nosniff"
    resp["Content-Security-Policy"] = "default-src 'none'"
    return resp
