"""API للمدفوعات: حسابات الاستلام · طرق الدفع · طلبات إضافة الرصيد وقراراتها."""
from decimal import Decimal, InvalidOperation

from django.db.models import Count, Sum
from django.utils import timezone
from rest_framework import viewsets
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core import currency
from core import services as wallet_services
from core.models import User, WalletTransaction
from .models import (
    ANY_CURRENCY, CURRENCIES, PaymentMethod, PaymentNotification, ReceivingAccount,
)
from .serializers import (
    PaymentMethodSerializer, PaymentNotificationSerializer, ReceivingAccountSerializer,
)


# مبالغ طلب الإيداع التي تمسّ محفظة الوكيل — تُعرض له بعملته
DEALER_MONEY = ["credit_amount", "balance_before", "balance_after"]


def _is_admin(user):
    return user.role in (User.Role.TENANT_ADMIN, User.Role.PLATFORM_OWNER)


def owner_scope(user):
    """
    صاحب طرق الدفع التي يديرها `user`: None = المتجر (لصاحبه)، والوكيل الكبير نفسه
    لطرقه هو. كل استعلام هنا يُصفّى بها فلا يرى أحدهما طرق الآخر ولا إيداعاته.
    """
    return user if user.role == User.Role.ANA_BAYI else None


def payee_of(dealer):
    """لمن يدفع هذا الوكيل: لوكيله الكبير إن كان تابعاً له، وإلا للمتجر (None)."""
    from orders.services import big_agent_of
    return big_agent_of(dealer)


def credit_for(method: PaymentMethod, amount: Decimal, rate: Decimal) -> Decimal:
    """
    المبلغ الذي يدخل الدفتر: المبلغ ÷ سعر الصرف − العمولة.
    `rate` = كم وحدةً من عملة الطريقة تساوي وحدةً من عملة الدفتر،
    فالقسمة هي التي تعيد المبلغ إلى عملة الدفتر.
    """
    gross = amount / rate
    net = gross * (Decimal("100") - method.commission_percent) / Decimal("100")
    return net.quantize(Decimal("0.01"))


class ReceivingAccountViewSet(viewsets.ModelViewSet):
    """CRUD حسابات الاستلام (Hesaplarım) — لصاحب المتجر، أو للوكيل الكبير حساباتُه هو."""
    serializer_class = ReceivingAccountSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return ReceivingAccount.objects.filter(
            tenant=self.request.user.tenant, owner=owner_scope(self.request.user))

    def perform_create(self, serializer):
        serializer.save(tenant=self.request.user.tenant, owner=owner_scope(self.request.user))


class PaymentMethodViewSet(viewsets.ModelViewSet):
    """CRUD طرق الدفع بكل تفاصيلها وحقولها المبنيّة — لصاحبها وحده (المتجر أو الوكيل الكبير)."""
    serializer_class = PaymentMethodSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return (
            PaymentMethod.objects.filter(
                tenant=self.request.user.tenant, owner=owner_scope(self.request.user))
            .select_related("account").prefetch_related("fields")
            .annotate(request_count=Count("requests"))
        )

    def _check_account(self, serializer):
        """حساب الاستلام من حسابات صاحب الطريقة نفسه — لا من حسابات غيره."""
        from rest_framework.exceptions import ValidationError
        acc = serializer.validated_data.get("account")
        mine = getattr(owner_scope(self.request.user), "id", None)
        if acc is not None and (acc.tenant_id != self.request.user.tenant_id or acc.owner_id != mine):
            raise ValidationError({"account": "الحساب ليس من حساباتك"})

    def perform_create(self, serializer):
        self._check_account(serializer)
        serializer.save(tenant=self.request.user.tenant, owner=owner_scope(self.request.user))

    def perform_update(self, serializer):
        self._check_account(serializer)
        serializer.save()


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def accounts_total_view(request):
    total = ReceivingAccount.objects.filter(
        tenant=request.user.tenant, owner=owner_scope(request.user)
    ).aggregate(balance=Sum("balance"))["balance"]
    return Response({"balance": str(total or 0)})


# ─────────────────────────── جانب الوكيل ───────────────────────────

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def store_methods_view(request):
    """طرق الدفع النشطة كما يراها الوكيل، مع سعر صرف كلٍّ منها الآن."""
    tenant = request.user.tenant
    # دكان الوكيل الكبير يدفع لوكيله بطرقه هو؛ وغيره يدفع للمتجر
    methods = (
        PaymentMethod.objects.filter(tenant=tenant, status=PaymentMethod.Status.ACTIVE,
                                     owner=payee_of(request.user))
        .prefetch_related("fields")
    )
    # المعامل المعروض للوكيل: من عملة الطريقة إلى **عملة عرضه** مباشرةً، لا إلى
    # عملة الدفتر — فالرقم الذي يراه يجب أن يطابق ما سيظهر في رصيده.
    show_rate = currency.display_rate(request.user)
    def shown(code):
        m_rate = currency.rate_of(tenant, code)
        return str((show_rate / m_rate).quantize(Decimal("0.000001"))) if m_rate else "0"

    # العملات التي لها سعر صرف — منها يختار الوكيل في الطرق التي تترك له العملة
    priced = [code for code, _ in CURRENCIES if currency.rate_of(tenant, code)]
    data = []
    for m in methods:
        row = PaymentMethodSerializer(m).data
        if m.currency == ANY_CURRENCY:
            row["rate"] = "0"
            row["rates"] = {code: shown(code) for code in priced}
        else:
            row["rate"] = shown(m.currency)
        data.append(row)
    return Response({
        "base_currency": tenant.base_currency or "TRY",
        "wallet_currency": currency.display_currency(request.user),
        "methods": data,
    })


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def store_deposits_view(request):
    """سجلّ طلبات إضافة الرصيد الخاصة بالوكيل الحالي."""
    qs = (
        PaymentNotification.objects.filter(tenant=request.user.tenant, dealer=request.user)
        .select_related("method", "account")
    )
    # amount بعملة الطريقة فيبقى كما هو؛ ما يمسّ المحفظة يُعرض بعملة الوكيل
    rows = [
        currency.convert_keys(dict(r), DEALER_MONEY, request.user)
        for r in PaymentNotificationSerializer(qs[:100], many=True).data
    ]
    return Response({"results": rows, "currency": currency.display_currency(request.user)})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def store_deposit_create_view(request):
    """إنشاء طلب إضافة رصيد — يبقى قيد المراجعة حتى يقرّر صاحب الطريقة (المتجر أو الوكيل الكبير)."""
    tenant = request.user.tenant
    try:
        method = PaymentMethod.objects.prefetch_related("fields").get(
            pk=request.data.get("method"), tenant=tenant, status=PaymentMethod.Status.ACTIVE,
            owner=payee_of(request.user),
        )
    except PaymentMethod.DoesNotExist:
        return Response({"detail": "طريقة الدفع غير متاحة"}, status=404)

    try:
        amount = Decimal(str(request.data.get("amount")))
    except (InvalidOperation, TypeError):
        return Response({"detail": "مبلغ غير صحيح"}, status=400)
    if amount <= 0:
        return Response({"detail": "المبلغ يجب أن يكون أكبر من صفر"}, status=400)

    if method.currency == ANY_CURRENCY:
        # الوكيل يحدّد العملة التي أرسل بها — والحدود لا تنطبق (هي بعملة واحدة)
        dep_currency = str(request.data.get("currency") or "").strip().upper()
        if dep_currency not in {code for code, _ in CURRENCIES}:
            return Response({"detail": "اختر العملة التي أرسلت بها"}, status=400)
    else:
        dep_currency = method.currency
        if method.min_amount and amount < method.min_amount:
            return Response({"detail": f"الحد الأدنى للإيداع {method.min_amount} {method.currency}"}, status=400)
        if method.max_amount and amount > method.max_amount:
            return Response({"detail": f"الحد الأعلى للإيداع {method.max_amount} {method.currency}"}, status=400)

    # قيم الحقول المبنيّة — مع التحقّق من الإلزامي منها
    sent = request.data.get("values") or {}
    values = {}
    for f in method.fields.all():
        val = str(sent.get(str(f.id), "")).strip()
        if f.required and not val:
            return Response({"detail": f"الحقل «{f.label}» مطلوب"}, status=400)
        if val:
            values[f.label] = val

    # طريقة بعملة بلا سعر صرف = مبلغ لا يُحسب — تُرفض بدل قيد خاطئ في الدفتر
    rate = currency.rate_of(tenant, dep_currency)
    if not rate:
        return Response(
            {"detail": f"لا سعر صرف مضبوط للعملة {dep_currency} — راجع صاحب المتجر"},
            status=400,
        )

    notif = PaymentNotification.objects.create(
        tenant=tenant, dealer=request.user, owner=method.owner, method=method, account=method.account,
        amount=amount, currency=dep_currency, rate=rate,
        commission_percent=method.commission_percent,
        credit_amount=credit_for(method, amount, rate),
        values=values, note=str(request.data.get("note") or "")[:255],
    )
    row = currency.convert_keys(
        dict(PaymentNotificationSerializer(notif).data), DEALER_MONEY, request.user
    )
    return Response(row, status=201)


# ─────────────────────────── جانب صاحب المتجر ───────────────────────────

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def payment_notifications_view(request):
    """قائمة طلبات إضافة الرصيد — فلترة بالحالة والوكيل والطريقة والمبلغ والتاريخ."""
    p = request.query_params
    qs = PaymentNotification.objects.filter(
        tenant=request.user.tenant, owner=owner_scope(request.user)
    ).select_related("dealer", "account", "method")
    st = p.get("status")
    if st and st != "all":
        qs = qs.filter(status=st)
    if p.get("dealer"):
        qs = qs.filter(dealer_id=p["dealer"])
    if p.get("method"):
        qs = qs.filter(method_id=p["method"])
    if p.get("min"):
        qs = qs.filter(credit_amount__gte=p["min"])
    if p.get("max"):
        qs = qs.filter(credit_amount__lte=p["max"])
    if p.get("date_from"):
        qs = qs.filter(created_at__date__gte=p["date_from"])
    if p.get("date_to"):
        qs = qs.filter(created_at__date__lte=p["date_to"])
    if p.get("q"):
        qs = qs.filter(dealer__name__icontains=p["q"])
    rows = PaymentNotificationSerializer(qs[:300], many=True).data
    agent = owner_scope(request.user)
    if agent is not None:
        # الوكيل الكبير يقرأ مبالغ دكاكينه بعملة عرضه هو
        rows = [currency.convert_keys(dict(r), DEALER_MONEY, agent) for r in rows]
    return Response({
        "count": qs.count(),
        "results": rows,
        "currency": currency.display_currency(agent) if agent else "",
    })


def _apply_decision(notif, action, actor, note=""):
    """
    ينفّذ القرار على طلب واحد ويعيد (نجاح، رسالة).
    القرار قابل للعكس: قبول المرفوض يضيف الرصيد، وإبطال المقبول يسحبه.
    """
    agent_wallet = getattr(notif.owner, "wallet", None) if notif.owner_id else None
    if notif.owner_id and agent_wallet is None:
        return False, "لا توجد محفظة للوكيل الكبير"
    credit = notif.credit_amount or notif.amount

    if action == "approve":
        if notif.status == PaymentNotification.Status.APPROVED:
            return False, "الطلب مقبول أصلاً"
        wallet = getattr(notif.dealer, "wallet", None)
        if wallet is None:
            return False, "لا توجد محفظة للوكيل"
        if agent_wallet is not None:
            # المال وصل إلى الوكيل الكبير؛ والرصيد يعطيه دكانه **من رصيده** —
            # فإن لم يكفِه رصيده (مع حدّه الائتماني) رُفض القبول
            try:
                wallet_services.apply_transaction(
                    agent_wallet.id, -credit, WalletTransaction.Type.MANUAL_DEBIT,
                    created_by=actor, note=f"إيداع {notif.dealer.name} — طلب #{notif.id}",
                    ref_type="payment", ref_id=notif.id,
                )
            except wallet_services.WalletError as e:
                return False, f"رصيدك لا يكفي لإضافة المبلغ لدكانك — {e}"
        txn = wallet_services.apply_transaction(
            wallet.id, notif.credit_amount or notif.amount, WalletTransaction.Type.TOPUP,
            created_by=actor, note=note or f"إضافة رصيد — طلب #{notif.id}",
            ref_type="payment", ref_id=notif.id, allow_below_limit=True,
        )
        notif.balance_before, notif.balance_after = txn.balance_before, txn.balance_after
        notif.status = PaymentNotification.Status.APPROVED
    else:
        # الرفض بعد قبولٍ سابق يسحب ما أُضيف؛ والرفض المبتدأ لا يمسّ المحفظة
        if notif.status == PaymentNotification.Status.REJECTED:
            return False, "الطلب مرفوض أصلاً"
        if notif.status == PaymentNotification.Status.APPROVED:
            wallet = getattr(notif.dealer, "wallet", None)
            if wallet is None:
                return False, "لا توجد محفظة للوكيل"
            txn = wallet_services.apply_transaction(
                wallet.id, -(notif.credit_amount or notif.amount), WalletTransaction.Type.ADJUSTMENT,
                created_by=actor, note=note or f"إبطال إضافة رصيد — طلب #{notif.id}",
                ref_type="payment", ref_id=notif.id, allow_below_limit=True,
            )
            notif.balance_before, notif.balance_after = txn.balance_before, txn.balance_after
            if agent_wallet is not None:
                wallet_services.apply_transaction(
                    agent_wallet.id, credit, WalletTransaction.Type.MANUAL_CREDIT,
                    created_by=actor, note=f"إبطال إيداع {notif.dealer.name} — طلب #{notif.id}",
                    ref_type="payment", ref_id=notif.id, allow_below_limit=True,
                )
        notif.status = PaymentNotification.Status.REJECTED

    notif.approved_by = actor
    notif.decided_at = timezone.now()
    if note:
        notif.admin_note = note[:255]
    notif.save(update_fields=[
        "status", "approved_by", "decided_at", "admin_note", "balance_before", "balance_after",
    ])
    return True, ""


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def payment_decide_view(request, notif_id, action):
    """قبول/رفض طلب واحد."""
    if action not in ("approve", "reject"):
        return Response({"detail": "إجراء غير معروف"}, status=400)
    if not (_is_admin(request.user) or owner_scope(request.user)):
        return Response({"detail": "غير مصرّح"}, status=403)
    try:
        notif = PaymentNotification.objects.select_related("dealer", "owner").get(
            pk=notif_id, tenant=request.user.tenant, owner=owner_scope(request.user)
        )
    except PaymentNotification.DoesNotExist:
        return Response({"detail": "الطلب غير موجود"}, status=404)

    ok, msg = _apply_decision(notif, action, request.user, str(request.data.get("note") or ""))
    if not ok:
        return Response({"detail": msg}, status=400)
    return Response(PaymentNotificationSerializer(notif).data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def payment_bulk_action_view(request):
    """قبول/رفض جماعي على الطلبات المحدَّدة — كإجراءات جدول طلبات الألعاب."""
    if not (_is_admin(request.user) or owner_scope(request.user)):
        return Response({"detail": "غير مصرّح"}, status=403)
    action = request.data.get("action")
    if action not in ("approve", "reject"):
        return Response({"detail": "إجراء غير معروف"}, status=400)
    ids = request.data.get("requests") or []
    note = str(request.data.get("note") or "")

    results, done = [], 0
    for notif in PaymentNotification.objects.select_related("dealer", "owner").filter(
        pk__in=ids, tenant=request.user.tenant, owner=owner_scope(request.user)
    ):
        try:
            ok, msg = _apply_decision(notif, action, request.user, note)
        except wallet_services.WalletError as e:
            ok, msg = False, str(e)
        results.append({"request": notif.id, "ok": ok, "detail": msg})
        done += 1 if ok else 0
    return Response({"done": done, "results": results})
