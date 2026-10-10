"""API لوحة الوكيل الكبير (Ana Bayi) — كل شيء مُقيّد بشجرته الفرعية."""
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.db.models import Count, Sum
from rest_framework import status as http
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.response import Response

from core import currency
from orders.serializers import DEALER_STATUS, dealer_filter
from core.text import clean_login_id
from core.models import User, Wallet, WalletTransaction
from catalog.models import AgentMargin, AgentPriceGroup, AgentProductPrice, Product
from orders.models import Order
from orders.services import resolve_sell_price


class IsAnaBayi(BasePermission):
    message = "هذه اللوحة مخصّصة للوكيل الكبير فقط."

    def has_permission(self, request, view):
        return bool(request.user and request.user.role == User.Role.ANA_BAYI)


AGENT = [IsAuthenticated, IsAnaBayi]


def _dealer_ids(agent):
    return list(User.objects.filter(parent=agent, role=User.Role.BAYI).values_list("id", flat=True))


@api_view(["GET"])
@permission_classes(AGENT)
def summary_view(request):
    """رئيسية الوكيل الكبير: رصيده وحدّه، ودكاكينه، وطلبات اليوم وربحه (ألعاب + خطوط)."""
    from django.utils import timezone
    from kontor.models import KontorOrder
    from payments.models import PaymentNotification

    agent = request.user
    ids = _dealer_ids(agent)
    today = timezone.localdate()
    g_ok = Order.objects.filter(agent=agent, status=Order.Status.SUCCESS)
    m_ok = KontorOrder.objects.filter(agent=agent, status=KontorOrder.Status.SUCCESS)

    def stats(g, m):
        a = g.aggregate(c=Count("id"), p=Sum("agent_profit"), s=Sum("buyer_price"))
        b = m.aggregate(c=Count("id"), p=Sum("agent_profit"), s=Sum("buyer_price"))
        return ((a["c"] or 0) + (b["c"] or 0), (a["p"] or 0) + (b["p"] or 0), (a["s"] or 0) + (b["s"] or 0))

    all_n, all_p, _ = stats(g_ok, m_ok)
    day_n, day_p, day_s = stats(g_ok.filter(created_at__date=today), m_ok.filter(created_at__date=today))
    wallet = getattr(agent, "wallet", None)
    show = lambda v: str(currency.to_display(agent, v))  # noqa: E731
    return Response({
        "balance": show(wallet.balance) if wallet else "0.00",
        "credit_limit": show(wallet.credit_limit) if wallet else "0.00",
        "available": show(wallet.balance - wallet.credit_limit) if wallet else "0.00",
        "dealers": len(ids),
        "dealers_balance": show(Wallet.objects.filter(user_id__in=ids).aggregate(s=Sum("balance"))["s"] or 0),
        "orders": all_n,
        "profit": show(all_p),
        "today": {"orders": day_n, "profit": show(day_p), "sales": show(day_s)},
        "deposits_pending": PaymentNotification.objects.filter(
            owner=agent, status=PaymentNotification.Status.PENDING).count(),
        "currency": currency.display_currency(agent),
    })


@api_view(["GET", "POST"])
@permission_classes(AGENT)
def dealers_view(request):
    agent = request.user
    if request.method == "POST":
        data = request.data
        login_id = clean_login_id(data.get("login_id"))
        if not login_id or not data.get("password") or not data.get("name"):
            return Response({"detail": "الاسم ورقم الدخول وكلمة السر مطلوبة"}, status=400)
        if len(str(data["password"])) < 6:
            return Response({"detail": "كلمة السر قصيرة (6 أحرف على الأقل)"}, status=400)
        if User.objects.filter(login_id=login_id).exists():
            return Response({"detail": "رقم الدخول مستخدم مسبقاً"}, status=400)
        extra, err = _profile_fields(data, agent)
        if err:
            return Response({"detail": err}, status=400)
        with transaction.atomic():
            # الدكان يرث عملة وكيله: يرى أسعاره ورسائله بالعملة التي يتعاملان بها
            u = User(tenant=agent.tenant, parent=agent, role=User.Role.BAYI,
                     login_id=login_id, name=data["name"], status=User.Status.ACTIVE,
                     display_currency=agent.display_currency or "",
                     modules={"oyun": True, "shopping": True}, **extra)
            u.set_password(data["password"])
            u.save()
            Wallet.objects.create(tenant=agent.tenant, user=u, balance=Decimal("0"))
        return Response({"id": u.id, "login_id": u.login_id, "name": u.name}, status=http.HTTP_201_CREATED)

    rows = []
    for u in User.objects.filter(parent=agent, role=User.Role.BAYI).select_related("wallet").order_by("name"):
        w = getattr(u, "wallet", None)
        rows.append({
            "id": u.id, "login_id": u.login_id, "name": u.name,
            # أرصدة دكاكينه بعملة **عرضه هو** — لوحته كلّها بعملة واحدة
            "balance": str(currency.to_display(agent, w.balance)) if w else "0.00",
            "status": u.status,
            "price_group": u.agent_price_group_id,
            "whatsapp": f"+{u.whatsapp}" if u.whatsapp else "",
            "has_id": bool(u.id_image),
        })
    return Response({
        "count": len(rows), "results": rows,
        "currency": currency.display_currency(agent),
    })


def _profile_fields(data, agent):
    """
    بيانات الدكان التي يديرها وكيله: واتساب (مطبَّعاً) · صورة الهوية والمحل · المحافظة.
    ⇐ (الحقول، رسالة الخطأ). ما لم يُرسَل لا يُمسّ.
    """
    from core.registration import _image
    from whatsapp.phone import normalize
    out = {}
    if "whatsapp" in data:
        raw = str(data.get("whatsapp") or "").strip()
        wa = normalize(raw, agent.country or "") if raw else ""
        if raw and not wa:
            return {}, "اكتب رقم واتساب مع رمز الدولة، مثل +905551234567"
        out["whatsapp"] = wa
        out["phone"] = wa
    for field, label in (("id_image", "صورة الهوية"), ("shop_image", "صورة المحل")):
        if field in data:
            img, err = _image(data.get(field), label, required=False)
            if err:
                return {}, err
            out[field] = img
    if "province" in data:
        out["province"] = str(data.get("province") or "")[:80]
    return out, ""


def _dealer_profile(agent, u):
    w = getattr(u, "wallet", None)
    return {
        "id": u.id, "login_id": u.login_id, "name": u.name,
        "whatsapp": f"+{u.whatsapp}" if u.whatsapp else "",
        "id_image": u.id_image, "shop_image": u.shop_image, "province": u.province,
        "status": u.status, "price_group": u.agent_price_group_id,
        "balance": str(currency.to_display(agent, w.balance)) if w else "0.00",
        "currency": currency.display_currency(agent),
        "locked": u.is_locked,
        "created_at": u.created_at.strftime("%Y-%m-%d"),
    }


@api_view(["GET", "PATCH"])
@permission_classes(AGENT)
def dealer_settings_view(request, dealer_id):
    """
    إعدادات دكانٍ من دكاكينه: بياناته ووثائقه، وحالته، وكلمة سرّه — يغيّرها وكيله
    بنفسه (`password`) فيفتح قفله إن كان مقفلاً.
    """
    agent = request.user
    u = User.objects.filter(pk=dealer_id, parent=agent, role=User.Role.BAYI).select_related("wallet").first()
    if u is None:
        return Response({"detail": "الدكان ليس من دكاكينك"}, status=404)
    if request.method == "GET":
        return Response(_dealer_profile(agent, u))

    data = request.data
    extra, err = _profile_fields(data, agent)
    if err:
        return Response({"detail": err}, status=400)
    fields = list(extra)
    for k, v in extra.items():
        setattr(u, k, v)
    if "name" in data:
        name = str(data.get("name") or "").strip()[:120]
        if not name:
            return Response({"detail": "اسم الدكان مطلوب"}, status=400)
        u.name = name
        fields.append("name")
    if "status" in data:
        if data["status"] not in (User.Status.ACTIVE, User.Status.PASSIVE):
            return Response({"detail": "حالة غير معروفة"}, status=400)
        # القائمة السوداء وطلب التسجيل قرار صاحب المتجر — الوكيل لا يتجاوزه
        if u.status not in (User.Status.ACTIVE, User.Status.PASSIVE) and data["status"] != u.status:
            return Response({"detail": "حالة هذا الدكان يقرّرها صاحب المتجر"}, status=403)
        u.status = data["status"]
        fields.append("status")
    pw = str(data.get("password") or "")
    if pw:
        if len(pw) < 6:
            return Response({"detail": "كلمة السر قصيرة (6 أحرف على الأقل)"}, status=400)
        u.set_password(pw)
        u.locked_at = None
        u.lock_until = None
        u.failed_login_count = 0
        fields += ["password", "locked_at", "lock_until", "failed_login_count"]
    if fields:
        u.save(update_fields=fields)
    return Response(_dealer_profile(agent, u) | {"password_changed": bool(pw)})


@api_view(["GET", "POST", "DELETE"])
@permission_classes(AGENT)
def price_groups_view(request):
    """
    مجموعات أسعار الوكيل الكبير لدكاكينه.

    GET    → المجموعات + عدد دكاكين كل واحدة
    POST   → إنشاء مجموعة {name}
    DELETE → حذف مجموعة {id} (دكاكينها تعود بلا مجموعة)
    """
    agent = request.user

    if request.method == "POST":
        name = str(request.data.get("name") or "").strip()[:60]
        if not name:
            return Response({"detail": "الاسم مطلوب"}, status=400)
        if AgentPriceGroup.objects.filter(agent=agent, name=name).exists():
            return Response({"detail": "لديك مجموعة بهذا الاسم"}, status=400)
        g = AgentPriceGroup.objects.create(tenant=agent.tenant, agent=agent, name=name)
        return Response({"id": g.id, "name": g.name, "dealers": 0}, status=http.HTTP_201_CREATED)

    if request.method == "DELETE":
        g = AgentPriceGroup.objects.filter(pk=request.data.get("id"), agent=agent).first()
        if g is None:
            return Response({"detail": "المجموعة غير موجودة"}, status=404)
        g.delete()      # دكاكينها تعود بلا مجموعة (SET_NULL)
        return Response(status=204)

    rows = [
        {"id": g.id, "name": g.name, "dealers": g.dealers.count()}
        for g in AgentPriceGroup.objects.filter(agent=agent).order_by("id")
    ]
    return Response({"count": len(rows), "results": rows})


@api_view(["POST"])
@permission_classes(AGENT)
def set_dealer_group_view(request):
    """وضع دكان في إحدى مجموعات الوكيل الكبير — {dealer, price_group|null}."""
    agent = request.user
    dealer = User.objects.filter(
        pk=request.data.get("dealer"), parent=agent, role=User.Role.BAYI
    ).first()
    if dealer is None:
        return Response({"detail": "الدكان ليس من دكاكينك"}, status=404)

    gid = request.data.get("price_group")
    if gid in (None, ""):
        dealer.agent_price_group = None
    else:
        group = AgentPriceGroup.objects.filter(pk=gid, agent=agent).first()
        if group is None:
            return Response({"detail": "المجموعة غير موجودة"}, status=404)
        dealer.agent_price_group = group
    dealer.save(update_fields=["agent_price_group"])
    return Response({"dealer": dealer.id, "price_group": dealer.agent_price_group_id})


@api_view(["GET", "POST"])
@permission_classes(AGENT)
def group_prices_view(request):
    """
    أسعار مجموعة بعينها: لكل باقة تكلفةُ الوكيل الكبير وسعرُ دكاكينه فيها.

    GET  ?group=<id> → الباقات مع `cost` و`price` (فارغ = لم يُسعَّر بعد)
    POST {group, product, price} → تسعير باقة (سعر أقلّ من التكلفة يُرفض:
         بيعٌ بخسارة صامتة لا يريده أحد).
    """
    agent = request.user
    group = AgentPriceGroup.objects.filter(
        pk=request.query_params.get("group") or request.data.get("group"), agent=agent
    ).first()
    if group is None:
        return Response({"detail": "المجموعة غير موجودة"}, status=404)

    if request.method == "POST":
        product = Product.objects.filter(
            pk=request.data.get("product"), tenant=agent.tenant
        ).first()
        if product is None:
            return Response({"detail": "الباقة غير موجودة"}, status=404)
        raw = request.data.get("price")
        if raw in (None, ""):
            AgentProductPrice.objects.filter(group=group, product=product).delete()
            return Response({"product": product.id, "price": None})
        try:
            price = currency.from_display(agent, Decimal(str(raw)))
        except (InvalidOperation, TypeError):
            return Response({"detail": "سعر غير صحيح"}, status=400)
        cost = resolve_sell_price_for_agent(agent, product)
        if price < cost:
            return Response(
                {"detail": f"السعر أقلّ من تكلفتك ({currency.to_display(agent, cost)})"},
                status=400,
            )
        AgentProductPrice.objects.update_or_create(
            tenant=agent.tenant, group=group, product=product, defaults={"price": price},
        )
        return Response({"product": product.id, "price": str(currency.to_display(agent, price))})

    priced = {p.product_id: p.price for p in group.prices.all()}
    products = (
        Product.objects.filter(tenant=agent.tenant, status=Product.Status.ACTIVE)
        .select_related("game").order_by("game__sort_order", "sort_order")
    )
    rows = []
    for p in products:
        cost = resolve_sell_price_for_agent(agent, p)
        price = priced.get(p.id)
        rows.append({
            "product": p.id, "name": p.name, "game": p.game.name,
            "cost": str(currency.to_display(agent, cost)),
            "price": str(currency.to_display(agent, price)) if price is not None else "",
            "profit": str(currency.to_display(agent, price - cost)) if price is not None else "",
            "sale_type": p.sale_type, "qty_unit": p.qty_unit,
        })
    return Response({
        "group": {"id": group.id, "name": group.name},
        "results": rows,
        "currency": currency.display_currency(agent),
    })


@api_view(["POST"])
@permission_classes(AGENT)
def dealer_wallet_view(request, dealer_id):
    """
    تحويل رصيد بين الوكيل الكبير ودكانه — {action: topup|deduct, amount, note}.

    **حوالة لا هبة:** ما يُضاف إلى الدكان يُخصم من محفظة وكيله، والعكس بالعكس.
    الوكيل الكبير لا يطبع رصيداً من العدم؛ يوزّع ما اشتراه من صاحب المتجر.
    والساقان في معاملة واحدة: إمّا تمّتا أو لم تحدث أيّ منهما.
    """
    agent = request.user
    dealer = User.objects.filter(
        pk=dealer_id, parent=agent, role=User.Role.BAYI
    ).select_related("wallet").first()
    if dealer is None:
        return Response({"detail": "الدكان ليس من دكاكينك"}, status=404)

    action = request.data.get("action")
    if action not in ("topup", "deduct"):
        return Response({"detail": "عملية غير معروفة"}, status=400)

    try:
        raw = currency.parse_amount(request.data.get("amount", ""))
        if raw is None:
            raise InvalidOperation
        amount = currency.from_display(agent, raw)
    except (InvalidOperation, TypeError):
        return Response({"detail": "مبلغ غير صحيح"}, status=400)
    if amount <= 0:
        return Response({"detail": "المبلغ يجب أن يكون أكبر من صفر"}, status=400)

    agent_wallet = getattr(agent, "wallet", None)
    dealer_wallet = getattr(dealer, "wallet", None)
    if agent_wallet is None or dealer_wallet is None:
        return Response({"detail": "لا توجد محفظة"}, status=400)

    note = str(request.data.get("note") or "")[:255]
    sign = Decimal("1") if action == "topup" else Decimal("-1")

    from core import services as wallet_services

    try:
        with transaction.atomic():
            # قفل المحفظتين معاً بترتيب رقميهما — كما يقفلهما الطلب — فلا تنتظر
            # حوالةٌ طلباً ينتظرها (تعانقٌ مميت يُسقط أحدهما بخطأ خادم)
            list(Wallet.objects.select_for_update().filter(
                id__in=[agent_wallet.id, dealer_wallet.id]).order_by("id"))
            # الخصم أوّلاً حين يشحن دكانه: لا يُشحن الدكان من رصيد لا يملكه وكيله
            wallet_services.apply_transaction(
                agent_wallet.id, -sign * amount,
                WalletTransaction.Type.MANUAL_DEBIT if action == "topup"
                else WalletTransaction.Type.MANUAL_CREDIT,
                created_by=agent,
                note=note or (f"تحويل إلى {dealer.name}" if action == "topup"
                              else f"سحب من {dealer.name}"),
                internal=True,
            )
            wallet_services.apply_transaction(
                dealer_wallet.id, sign * amount,
                WalletTransaction.Type.MANUAL_CREDIT if action == "topup"
                else WalletTransaction.Type.MANUAL_DEBIT,
                created_by=agent,
                note=note or (f"شحن من وكيلك {agent.name}" if action == "topup"
                              else f"سحب لصالح وكيلك {agent.name}"),
                internal=True,
            )
    except wallet_services.WalletError as e:
        return Response({"detail": str(e)}, status=400)

    agent_wallet.refresh_from_db()
    dealer_wallet.refresh_from_db()
    return Response({
        "dealer_balance": str(currency.to_display(agent, dealer_wallet.balance)),
        "agent_balance": str(currency.to_display(agent, agent_wallet.balance)),
    })


@api_view(["GET"])
@permission_classes(AGENT)
def dealer_statement_view(request, dealer_id):
    """كشف حركات دكان بعينه — بعملة عرض الوكيل الكبير."""
    agent = request.user
    dealer = User.objects.filter(
        pk=dealer_id, parent=agent, role=User.Role.BAYI
    ).select_related("wallet").first()
    if dealer is None or getattr(dealer, "wallet", None) is None:
        return Response({"detail": "الدكان ليس من دكاكينك"}, status=404)

    from core.statement import build
    show = lambda v: currency.to_display(agent, v)  # noqa: E731
    return Response({
        "dealer": {
            "id": dealer.id, "name": dealer.name,
            "balance": str(show(dealer.wallet.balance)),
        },
        "types": [{"key": k, "label": label} for k, label in WalletTransaction.Type.choices],
        "currency": currency.display_currency(agent),
        **build(dealer.wallet, request.query_params, show),
    })


@api_view(["GET"])
@permission_classes(AGENT)
def margins_view(request):
    """الباقات + تكلفة الوكيل الكبير (سعره من صاحب المتجر) + هامشه + سعر دكاكينه."""
    agent = request.user
    margins = {m.product_id: m.margin_percent for m in AgentMargin.objects.filter(agent=agent)}
    products = Product.objects.filter(tenant=agent.tenant, status=Product.Status.ACTIVE).select_related("game").order_by("game__sort_order", "sort_order")
    rows = []
    for p in products:
        cost = resolve_sell_price_for_agent(agent, p)
        pct = margins.get(p.id, Decimal("0"))
        dealer_price = (cost * (Decimal("1") + pct / Decimal("100"))).quantize(Decimal("0.01"))
        rows.append({
            "product": p.id, "name": p.name, "game": p.game.name,
            # الهامش نسبة مئوية فلا يُحوَّل — والسعران بعملة عرضه
            "cost": str(currency.to_display(agent, cost)),
            "margin_percent": str(pct),
            "dealer_price": str(currency.to_display(agent, dealer_price)),
            "sale_type": p.sale_type, "qty_unit": p.qty_unit,
        })
    return Response({"results": rows, "currency": currency.display_currency(agent)})


def resolve_sell_price_for_agent(agent, product):
    """سعر الوكيل الكبير نفسه (من صاحب المتجر) دون هامشه — بتجاهل parent."""
    from catalog.models import ProductPrice
    if agent.price_group_id:
        pp = ProductPrice.objects.filter(product=product, price_group_id=agent.price_group_id).first()
        if pp:
            return pp.price
    return product.recommended_price


@api_view(["POST"])
@permission_classes(AGENT)
def set_margin_view(request):
    agent = request.user
    try:
        product = Product.objects.get(pk=request.data.get("product"), tenant=agent.tenant)
        pct = Decimal(str(request.data.get("margin_percent")))
    except (Product.DoesNotExist, InvalidOperation, TypeError):
        return Response({"detail": "بيانات غير صحيحة"}, status=400)
    AgentMargin.objects.update_or_create(
        tenant=agent.tenant, agent=agent, product=product,
        defaults={"margin_percent": pct},
    )
    return Response({"product": product.id, "margin_percent": str(pct)})
