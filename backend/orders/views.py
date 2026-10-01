"""API للطلبات (Takip): قائمة + إنشاء + تنفيذ + إلغاء + تقارير."""
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.db.models import Count, Q, Sum
from rest_framework import status as http
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core import currency
from core.models import User
from catalog.models import Product
from providers.models import Provider
from . import services
from .models import Order
from .serializers import DEALER_STATUS, OrderSerializer, StoreOrderSerializer


def _filtered_orders(request):
    """طلبات المستأجر بعد تطبيق فلاتر التقرير (وكيل/لعبة/منتج/تاريخ/حالة)."""
    qs = Order.objects.filter(tenant=request.user.tenant)
    p = request.query_params
    if p.get("dealer"):
        qs = qs.filter(dealer_id=p["dealer"])
    if p.get("game"):
        qs = qs.filter(game_id=p["game"])
    if p.get("product"):
        qs = qs.filter(product_id=p["product"])
    if p.get("date_from"):
        qs = qs.filter(created_at__date__gte=p["date_from"])
    if p.get("date_to"):
        qs = qs.filter(created_at__date__lte=p["date_to"])
    # التقارير تحسب الطلبات الناجحة فقط افتراضياً (Olumsuz işlemler dahil edilmez)
    status = p.get("status", "success")
    if status and status != "all":
        qs = qs.filter(status=status)
    return qs


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def report_summary_view(request):
    """تقرير مجمّع حسب اللعبة (Oyun Pin Toplam Raporu)."""
    qs = _filtered_orders(request)
    rows = (
        qs.values("game__name")
        .annotate(count=Count("id"), cost=Sum("cost_price"),
                  sell=Sum("sell_price"), profit=Sum("profit"))
        .order_by("-count")
    )
    results = [{
        "game": r["game__name"],
        "count": r["count"],
        "cost": str(r["cost"] or 0),
        "sell": str(r["sell"] or 0),
        "profit": str(r["profit"] or 0),
    } for r in rows]
    totals = qs.aggregate(count=Count("id"), cost=Sum("cost_price"),
                          sell=Sum("sell_price"), profit=Sum("profit"))
    return Response({
        "results": results,
        "totals": {k: str(v or 0) for k, v in totals.items()},
    })


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def orders_view(request):
    tenant = request.user.tenant

    if request.method == "POST":
        # إنشاء طلب: dealer + product (+ player_id/customer_phone)
        try:
            dealer = User.objects.get(pk=request.data.get("dealer"), tenant=tenant)
            product = Product.objects.select_related("game").get(
                pk=request.data.get("product"), tenant=tenant
            )
        except (User.DoesNotExist, Product.DoesNotExist):
            return Response({"detail": "الوكيل أو المنتج غير موجود"}, status=404)
        try:
            order = services.create_order(
                dealer, product,
                player_id=request.data.get("player_id", ""),
                customer_phone=request.data.get("customer_phone", ""),
                dealer_sell_price=request.data.get("dealer_sell_price"),
            )
        except services.OrderError as e:
            return Response({"detail": str(e)}, status=http.HTTP_400_BAD_REQUEST)
        _maybe_auto_execute(order)
        return Response(OrderSerializer(order).data, status=http.HTTP_201_CREATED)

    # GET: قائمة + فلاتر (كل فلاتر لوحة المرجع: لعبة/منتج/وكيل/API/فيش/هاتف/مبلغ/تاريخ/لاعب)
    qs = Order.objects.filter(tenant=tenant).select_related(
        "dealer", "game", "product", "provider"
    )
    p = request.query_params
    status_filter = p.get("status")
    if status_filter and status_filter != "all":
        qs = qs.filter(status=status_filter)
    if p.get("q", "").strip():
        qs = qs.filter(receipt_no__icontains=p["q"].strip())
    for param, field in (("game", "game_id"), ("product", "product_id"),
                         ("dealer", "dealer_id"), ("provider", "provider_id")):
        if p.get(param):
            qs = qs.filter(**{field: p[param]})
    if p.get("phone", "").strip():
        qs = qs.filter(customer_phone__icontains=p["phone"].strip())
    if p.get("player", "").strip():
        qs = qs.filter(player_id__icontains=p["player"].strip())
    try:
        if p.get("min"):
            qs = qs.filter(sell_price__gte=Decimal(p["min"]))
        if p.get("max"):
            qs = qs.filter(sell_price__lte=Decimal(p["max"]))
    except InvalidOperation:
        pass
    if p.get("date_from"):
        qs = qs.filter(created_at__date__gte=p["date_from"])
    if p.get("date_to"):
        qs = qs.filter(created_at__date__lte=p["date_to"])

    return Response({
        "count": qs.count(),
        "results": OrderSerializer(qs[:200], many=True).data,
    })


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def report_dealers_view(request):
    """تقرير مجمّع حسب الوكيل (كشف الوكلاء / تقرير الأرباح)."""
    qs = _filtered_orders(request)
    rows = (
        qs.values("dealer__name")
        .annotate(count=Count("id"), sell=Sum("sell_price"), profit=Sum("profit"))
        .order_by("-profit")
    )
    results = [{
        "dealer": r["dealer__name"],
        "count": r["count"],
        "sell": str(r["sell"] or 0),
        "profit": str(r["profit"] or 0),
    } for r in rows]
    totals = qs.aggregate(count=Count("id"), sell=Sum("sell_price"), profit=Sum("profit"))
    return Response({
        "results": results,
        "totals": {k: str(v or 0) for k, v in totals.items()},
    })


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def store_catalog_view(request):
    """كتالوج المتجر: الألعاب النشطة ومنتجاتها بسعر المشتري (سعر مجموعته)."""
    from catalog.models import Game

    user = request.user
    games = Game.objects.filter(
        tenant=user.tenant, status=Game.Status.ACTIVE
    ).prefetch_related("products").order_by("sort_order")
    result = []
    for g in games:
        products = []
        for p in g.products.filter(status=Product.Status.ACTIVE):
            products.append({
                "id": p.id,
                "name": p.name,
                # الأسعار بعملة عرض الوكيل — الدفتر يبقى بعملة الموقع
                "price": str(currency.to_display(user, services.resolve_sell_price(user, p))),
                # السعر الذي يقترحه صاحب المتجر للبيع لزبون الوكيل
                "recommended_price": str(currency.to_display(user, p.recommended_price)),
                "require_player_id": g.require_player_id,
            })
        if products:
            result.append({
                "id": g.id, "name": g.name, "image_url": g.image_url,
                "require_player_id": g.require_player_id, "products": products,
                # ما يكتبه صاحب المتجر في «تفاصيل اللعبة» — يراه الوكيل في صفحتها وعند الشراء
                "description": g.description, "dealer_note": g.dealer_note,
            })
    return Response({"games": result, "currency": currency.display_currency(user)})


# مبالغ الطلب بمنظور الوكيل — تُحوَّل إلى عملة عرضه عند الخروج
STORE_ORDER_MONEY = ["paid_price", "dealer_sell_price", "dealer_profit",
                     "balance_before", "balance_after"]


def _store_order_row(order, user):
    return currency.convert_keys(
        dict(StoreOrderSerializer(order).data), STORE_ORDER_MONEY, user
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def store_buy_view(request):
    """شراء من المتجر: ينشئ طلباً للمستخدم الحالي (يخصم محفظته)."""
    try:
        product = Product.objects.select_related("game").get(
            pk=request.data.get("product"), tenant=request.user.tenant
        )
    except Product.DoesNotExist:
        return Response({"detail": "المنتج غير موجود"}, status=404)

    # سعر بيع الوكيل لزبونه يكتبه بعملة عرضه — يُحفظ بعملة الموقع
    retail = request.data.get("dealer_sell_price")
    if retail not in (None, ""):
        try:
            retail = currency.from_display(request.user, retail)
        except (InvalidOperation, TypeError):
            return Response({"detail": "سعر بيع غير صحيح"}, status=http.HTTP_400_BAD_REQUEST)

    try:
        order = services.create_order(
            request.user, product,
            player_id=request.data.get("player_id", ""),
            customer_phone=request.data.get("customer_phone", ""),
            # يتركه الوكيل فارغاً ⇒ سعر التوصية؛ ويكتبه إن باع بسعر آخر.
            dealer_sell_price=retail,
        )
    except services.OrderError as e:
        return Response({"detail": str(e)}, status=http.HTTP_400_BAD_REQUEST)
    _maybe_auto_execute(order)
    return Response(_store_order_row(order, request.user), status=http.HTTP_201_CREATED)


def _maybe_auto_execute(order):
    """ينفّذ الطلب آلياً إن كان منتجه تلقائياً وله أي مزوّد في سلسلة التوجيه."""
    p = order.product
    if p.execution_type == Product.Execution.AUTO and (
        p.provider_id or p.provider_alt1_id or p.provider_alt2_id
    ):
        services.dispatch_order(order)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def store_orders_view(request):
    """طلبات الوكيل نفسه فقط (Pin Takip الخاصة به) — معزولة عن باقي الوكلاء."""
    qs = Order.objects.filter(
        tenant=request.user.tenant, dealer=request.user
    ).select_related("game", "product", "provider").order_by("-created_at")
    p = request.query_params
    if p.get("date_from"):
        qs = qs.filter(created_at__date__gte=p["date_from"])
    if p.get("date_to"):
        qs = qs.filter(created_at__date__lte=p["date_to"])
    search = p.get("q", "").strip()
    if search:
        # الوكيل يبحث بما يعرفه عن طلبه: الفيش أو معرّف اللاعب أو هاتف زبونه أو الباقة
        qs = qs.filter(
            Q(receipt_no__icontains=search) | Q(player_id__icontains=search)
            | Q(customer_phone__icontains=search) | Q(product__name__icontains=search)
            | Q(game__name__icontains=search)
        )
    # عدّادات شرائح الحالة — قبل فلتر الحالة، وبنفس تجميع الوكيل (العالق انتظار)
    counts = {"all": 0}
    for row in qs.order_by().values("status").annotate(n=Count("id")):
        key = DEALER_STATUS.get(row["status"], row["status"])
        counts[key] = counts.get(key, 0) + row["n"]
        counts["all"] += row["n"]
    status_filter = p.get("status")
    if status_filter and status_filter != "all":
        # الوكيل يرى العالق انتظاراً (انظر DEALER_STATUS)، فليجده مع الانتظار —
        # وإلّا اختفى طلبه من الفلترين معاً فظنّه ضائعاً.
        wanted = ([Order.Status.PENDING, Order.Status.STUCK]
                  if status_filter == Order.Status.PENDING else [status_filter])
        qs = qs.filter(status__in=wanted)
    return Response({
        "count": qs.count(),
        "counts": counts,
        # إجمالي ما دفعه الوكيل في النتيجة المعروضة (بلا الملغاة — مالها عاد إليه)
        "total_paid": str(currency.to_display(request.user, qs.exclude(
            status=Order.Status.CANCELLED).aggregate(s=Sum("buyer_price"))["s"] or 0)),
        "results": [_store_order_row(o, request.user) for o in qs[:200]],
        "currency": currency.display_currency(request.user),
    })


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def store_wallet_view(request):
    """
    محفظة الوكيل نفسه + كشف حركاتها (Hesap Hareketleri الخاصة به).

    فلاتر: `type` (نوع الحركة) · `date_from` / `date_to`. والعدّادات `counts`
    تُحسب على نطاق التاريخ وحده — فيرى الوكيل كم حركةً من كل نوع قبل أن يختار.
    وحركة الطلب تحمل طلبها كاملاً (`order`) لزرّ «التفاصيل».
    """
    from core.models import WalletTransaction

    wallet = getattr(request.user, "wallet", None)
    if wallet is None:
        return Response({"detail": "لا توجد محفظة"}, status=404)
    user = request.user
    show = currency.to_display
    p = request.query_params

    qs = wallet.transactions.all()
    if p.get("date_from"):
        qs = qs.filter(created_at__date__gte=p["date_from"])
    if p.get("date_to"):
        qs = qs.filter(created_at__date__lte=p["date_to"])
    counts = {r["type"]: r["n"] for r in qs.values("type").annotate(n=Count("id")).order_by()}
    counts["all"] = sum(counts.values())
    kind = p.get("type") or "all"
    if kind != "all":
        qs = qs.filter(type=kind)
    txns = list(qs[:200])

    order_ids = [t.ref_id for t in txns if t.ref_type == "order" and t.ref_id]
    orders = {
        o.id: _store_order_row(o, user)
        for o in Order.objects.filter(id__in=order_ids, tenant=user.tenant, dealer=user)
        .select_related("product", "game")
    }

    return Response({
        "balance": str(show(user, wallet.balance)),
        "credit_limit": str(show(user, wallet.credit_limit)),
        "available": str(show(user, wallet.balance - wallet.credit_limit)),
        "currency": currency.display_currency(user),
        "counts": counts,
        "types": [{"key": k, "label": label} for k, label in WalletTransaction.Type.choices],
        "results": [{
            "id": t.id, "type": t.type, "type_label": t.get_type_display(),
            "amount": str(show(user, t.amount)),
            "balance_before": str(show(user, t.balance_before)),
            "balance_after": str(show(user, t.balance_after)),
            "note": t.note, "created_at": t.created_at.strftime("%Y-%m-%d %H:%M"),
            "ref_type": t.ref_type, "ref_id": t.ref_id,
            "order": orders.get(t.ref_id) if t.ref_type == "order" else None,
        } for t in txns],
    })


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def store_change_password_view(request):
    """تغيير الوكيل كلمة سرّه بنفسه (Ayarlar)."""
    user = request.user
    current = request.data.get("current_password") or ""
    new = request.data.get("new_password") or ""
    if not user.check_password(current):
        return Response({"detail": "كلمة السر الحالية غير صحيحة"}, status=400)
    if len(new) < 5:
        return Response({"detail": "كلمة السر الجديدة قصيرة (5 أحرف على الأقل)"}, status=400)
    user.set_password(new)
    user.save(update_fields=["password"])
    return Response({"detail": "تم تغيير كلمة السر"})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def store_report_view(request):
    """تقرير إجماليات الوكيل نفسه (Oyun Pin Toplam Raporu) — مجمّع حسب المنتج."""
    user = request.user
    qs = Order.objects.filter(tenant=user.tenant, dealer=user)
    p = request.query_params
    if not p.get("include_cancelled"):
        qs = qs.exclude(status=Order.Status.CANCELLED)
    if p.get("date_from"):
        qs = qs.filter(created_at__date__gte=p["date_from"])
    if p.get("date_to"):
        qs = qs.filter(created_at__date__lte=p["date_to"])
    # بمنظور الوكيل: تكلفته = ما دفعه لصاحب المتجر · مبيعاته وربحه له وحده
    rows = (
        qs.values("game__name", "product__name")
        .annotate(count=Count("id"), cost=Sum("sell_price"),
                  sell=Sum("dealer_sell_price"), profit=Sum("dealer_profit"))
        .order_by("game__name", "-count")
    )
    show = currency.to_display
    results = [{
        "game": r["game__name"], "product": r["product__name"],
        "count": r["count"], "cost": str(show(user, r["cost"] or 0)),
        "sell": str(show(user, r["sell"] or 0)), "profit": str(show(user, r["profit"] or 0)),
    } for r in rows]
    totals = qs.aggregate(count=Count("id"), cost=Sum("sell_price"),
                          sell=Sum("dealer_sell_price"), profit=Sum("dealer_profit"))
    return Response({
        "results": results,
        "products": len(results),
        "totals": {
            k: str(v or 0) if k == "count" else str(show(user, v or 0))
            for k, v in totals.items()
        },
        "currency": currency.display_currency(user),
    })


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def store_summary_view(request):
    """ملخّص لوحة الوكيل: رصيده + عدد طلباته الناجحة + أرباحه (من طلباته هو)."""
    user = request.user
    wallet = getattr(user, "wallet", None)
    mine = Order.objects.filter(tenant=user.tenant, dealer=user)
    # «أرباحي» في لوحة الوكيل = ربحه هو، لا ربح صاحب المتجر منه
    agg = mine.filter(status=Order.Status.SUCCESS).aggregate(
        count=Count("id"), profit=Sum("dealer_profit"), sell=Sum("dealer_sell_price")
    )
    show = currency.to_display
    return Response({
        "balance": str(show(user, wallet.balance)) if wallet else "0.00",
        "credit_limit": str(show(user, wallet.credit_limit)) if wallet else "0.00",
        "currency": currency.display_currency(user),
        "orders": agg["count"] or 0,
        "profit": str(show(user, agg["profit"] or 0)),
        "sell": str(show(user, agg["sell"] or 0)),
        "pending": mine.filter(
            status__in=[Order.Status.PENDING, Order.Status.STUCK]
        ).count(),
        # هويّة المتجر لرأس لوحة الوكيل — تعمل على الباب العام أيضاً لا على عنوان المتجر وحده
        "store": {
            "name": user.tenant.name if user.tenant else "",
            "short_name": (user.tenant.short_name or user.tenant.name) if user.tenant else "",
            "logo_url": user.tenant.logo_url if user.tenant else "",
        },
    })


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def order_execute_view(request, order_id):
    try:
        order = Order.objects.get(pk=order_id, tenant=request.user.tenant)
    except Order.DoesNotExist:
        return Response({"detail": "الطلب غير موجود"}, status=404)
    provider = None
    pid = request.data.get("provider")
    if pid:
        provider = Provider.objects.filter(pk=pid, tenant=request.user.tenant).first()
    try:
        order = services.execute_order(order, provider=provider, pin=request.data.get("pin", ""))
    except services.OrderError as e:
        return Response({"detail": str(e)}, status=http.HTTP_400_BAD_REQUEST)
    return Response(OrderSerializer(order).data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def order_cancel_view(request, order_id):
    try:
        order = Order.objects.get(pk=order_id, tenant=request.user.tenant)
    except Order.DoesNotExist:
        return Response({"detail": "الطلب غير موجود"}, status=404)
    try:
        order = services.cancel_order(order)
    except services.OrderError as e:
        return Response({"detail": str(e)}, status=http.HTTP_400_BAD_REQUEST)
    return Response(OrderSerializer(order).data)


#: إجراءات المشغّل الجماعية على الطلبات المحدَّدة (Toplu İşlem)
BULK_ACTIONS = ("approve", "reject", "dispatch", "manual")


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def orders_bulk_action_view(request):
    """
    إجراء جماعي على الطلبات المحدَّدة:
      • `approve`  → تنفيذ يدوي (ناجح) — مع PIN اختياري
      • `reject`   → إلغاء واسترجاع المبلغ للوكيل
      • `dispatch` → توجيه إلى مزوّد يختاره المشغّل (يتخطّى سلسلة المنتج)
      • `manual`   → إعادة إلى «قيد الانتظار» وفكّ الطلب عن مزوّده

    `note` تُحفظ في `dealer_note` — **يراها الوكيل**، فهي سبب القبول أو الرفض.
    كل طلب يُعالَج على حدة وتُعاد نتيجته، فلا يُسقِط طلبٌ فاشل البقيةَ.
    """
    tenant = request.user.tenant
    action = (request.data.get("action") or "").strip()
    ids = request.data.get("orders") or []
    note = (request.data.get("note") or "").strip()[:255]
    pin = (request.data.get("pin") or "").strip()

    if action not in BULK_ACTIONS:
        return Response({"detail": "إجراء غير معروف"}, status=http.HTTP_400_BAD_REQUEST)
    if not isinstance(ids, list) or not ids:
        return Response({"detail": "لم تُحدَّد أي طلبات"}, status=http.HTTP_400_BAD_REQUEST)

    provider = None
    if action == "dispatch":
        provider = Provider.objects.filter(
            pk=request.data.get("provider"), tenant=tenant
        ).first()
        if provider is None:
            return Response({"detail": "اختر مزوّداً للتوجيه"}, status=http.HTTP_400_BAD_REQUEST)
        if provider.status != Provider.Status.ACTIVE:
            return Response({"detail": f"المزوّد «{provider.name}» معطّل"},
                            status=http.HTTP_400_BAD_REQUEST)

    results = []
    for oid in ids[:100]:
        order = Order.objects.filter(pk=oid, tenant=tenant).select_related("product").first()
        if order is None:
            results.append({"order": oid, "ok": False, "detail": "غير موجود"})
            continue
        try:
            _apply_bulk_action(order, action, provider=provider, note=note, pin=pin)
        except services.OrderError as e:
            results.append({"order": oid, "receipt_no": order.receipt_no,
                            "ok": False, "detail": str(e)})
            continue
        except Exception as e:                    # لا يُسقِط مزوّدٌ متعثّر البقية
            results.append({"order": oid, "receipt_no": order.receipt_no,
                            "ok": False, "detail": f"خطأ غير متوقّع: {e}"})
            continue
        order.refresh_from_db()
        results.append({"order": oid, "receipt_no": order.receipt_no, "ok": True,
                        "status": order.status, "status_label": order.get_status_display()})

    done = sum(1 for r in results if r["ok"])
    return Response({"done": done, "failed": len(results) - done, "results": results})


def _apply_bulk_action(order, action, *, provider, note, pin):
    """
    ينفّذ إجراءً واحداً على طلب واحد.

    التوجيه (`dispatch`) يُستدعى **خارج** معاملة قاعدة البيانات عمداً: فيه نداء
    HTTP خارجي قد يستغرق ثوانيَ، وقفل صفّ الطلب طوالها يخنق القاعدة.
    """
    if action == "dispatch":
        services.dispatch_to_provider(order, provider)
    else:
        with transaction.atomic():
            # قفل الصف يمنع تنفيذ إجراءين متزامنين على الطلب نفسه —
            # وأخطرها استرجاعان للمبلغ ذاته.
            locked = Order.objects.select_for_update().get(pk=order.pk)
            if action == "approve":
                services.execute_order(locked, pin=pin)
            elif action == "reject":
                services.cancel_order(locked)
            elif action == "manual":
                services.set_manual(locked)
    if note:
        order.refresh_from_db()
        order.dealer_note = note
        order.save(update_fields=["dealer_note"])


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def order_sync_view(request, order_id):
    """متابعة طلب واحد لدى مزوّده وتحديث حالته."""
    try:
        order = Order.objects.select_related("provider").get(
            pk=order_id, tenant=request.user.tenant
        )
    except Order.DoesNotExist:
        return Response({"detail": "الطلب غير موجود"}, status=404)
    result = services.sync_order(order)
    order.refresh_from_db()
    return Response({"sync": result, "order": OrderSerializer(order).data})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def orders_sync_pending_view(request):
    """
    حلقة المراقبة: تتابع كل الطلبات "قيد التنفيذ" دفعةً واحدة.
    تستدعيها الواجهة دورياً (كل ~6 ثوانٍ) ما دام هناك طلب قيد التنفيذ.
    """
    results = services.sync_pending(request.user.tenant)
    changed = [r for r in results if r.get("changed")]
    return Response({
        "checked": len(results), "changed": len(changed), "results": results,
    })


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def order_trace_view(request, order_id):
    """
    تتبّع مسار الطلب: هل وُجِّهت الباقة؟ إلى أي مزوّد؟ برقم ربط أي؟ وبأي ردّ؟
    تغذّي نافذة "تفاصيل" في متابعة الطلبات.
    """
    from catalog.models import ProductLink

    try:
        order = Order.objects.select_related(
            "product", "provider", "dealer", "game",
            "product__provider", "product__provider_alt1", "product__provider_alt2",
        ).get(pk=order_id, tenant=request.user.tenant)
    except Order.DoesNotExist:
        return Response({"detail": "الطلب غير موجود"}, status=404)

    product = order.product
    chain_providers = [
        ("الرئيسي", product.provider),
        ("API 1", product.provider_alt1),
        ("API 2", product.provider_alt2),
    ]
    links = {
        l.provider_id: l
        for l in ProductLink.objects.filter(product=product).select_related("provider")
    }

    chain = []
    for slot, prov in chain_providers:
        if prov is None:
            chain.append({"slot": slot, "provider": None, "provider_name": "بديل مغلق",
                          "linked": False, "package_id": "", "extra": {}})
            continue
        link = links.get(prov.id)
        pkg = link.package_id if link else (product.provider_package_id or "")
        chain.append({
            "slot": slot,
            "provider": prov.id,
            "provider_name": prov.name,
            "provider_kind": (prov.config or {}).get("code") or prov.type,
            "linked": bool(pkg),
            "package_id": pkg,
            "package_name": link.package_name if link else "",
            "extra": dict(link.extra or {}) if link else {},
            "used": order.provider_id == prov.id,
        })

    auto = product.execution_type == Product.Execution.AUTO
    any_provider = any(c["provider"] for c in chain)
    if not auto:
        routing = "تنفيذ يدوي — لا إرسال آلي للمزوّد"
    elif not any_provider:
        routing = "لا مزوّد على الباقة — تبقى قيد الانتظار للتنفيذ اليدوي"
    elif not any(c["linked"] for c in chain if c["provider"]):
        routing = "موجَّهة لمزوّد لكن **بلا رقم ربط** — لن يعرف المزوّد أي باقة"
    else:
        routing = "موجَّهة وجاهزة"

    return Response({
        "order": OrderSerializer(order).data,
        "product": {
            "id": product.id, "name": product.name, "game": order.game.name,
            "kupur": product.kupur, "execution_type": product.execution_type,
        },
        "routing_summary": routing,
        "chain": chain,
    })


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def store_packages_view(request):
    """
    قائمة أسعار الوكيل — قراءةٌ فقط.

    `id` هو **رقم المنتج عندنا**: هو ما يضعه الوكيل في
    `newOrder/{id}/params` عند الربط الخارجي. ولا يُعرض هنا رقمُ الباقة لدى
    مزوّد المتجر بحال — ذاك سرُّ صاحب المتجر التجاري، وكشفُه يدلّ وكلاءه على
    مصادره.
    """
    from catalog.models import Game

    user = request.user
    rows = []
    games = Game.objects.filter(
        tenant=user.tenant, status=Game.Status.ACTIVE
    ).prefetch_related("products").order_by("sort_order", "name")
    for g in games:
        for p in g.products.filter(status=Product.Status.ACTIVE).order_by("sort_order", "id"):
            rows.append({
                "id": p.id,
                "game": g.name,
                "name": p.name,
                # سعر شرائه هو (سعر مجموعته) وسعر التوصية — كلاهما بعملة عرضه
                "buy_price": str(currency.to_display(user, services.resolve_sell_price(user, p))),
                "recommended_price": str(currency.to_display(user, p.recommended_price)),
                "require_player_id": g.require_player_id,
            })
    return Response({
        "count": len(rows), "results": rows,
        "currency": currency.display_currency(user),
    })


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def subscription_state_view(request):
    """حالة اشتراك متجري — يقرأها شريط التنبيه في لوحة صاحب المتجر."""
    tenant = request.user.tenant
    if tenant is None:
        return Response({"state": "ok"})
    state = tenant.subscription_state()
    days_left = None
    if tenant.sub_expires_at:
        from django.utils import timezone
        days_left = (tenant.sub_expires_at - timezone.localdate()).days
    return Response({
        "state": state,
        "expires_at": tenant.sub_expires_at.strftime("%Y-%m-%d") if tenant.sub_expires_at else None,
        "days_left": days_left,
        "grace_days": tenant.sub_grace_days,
        "plan_label": tenant.get_sub_plan_display(),
    })
