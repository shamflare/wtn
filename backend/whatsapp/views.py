"""
واجهات واتساب لصاحب المتجر: الربط والقالب والإرسال الفردي والجماعي.

لا شيء هنا يتّصل بواتساب. كلّه يكتب في القاعدة، والبوت يلتقط.
"""
from decimal import Decimal
from uuid import uuid4

from django.db import transaction
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core import currency as cur
from core.models import User

from . import messages as tpl, phone
from .models import OutboundMessage, WhatsAppAccount


def _guard(request):
    """صاحب المتجر وحده — هو من يملك الرقم ويرسل. يعيد (account, error)."""
    if request.user.role != User.Role.TENANT_ADMIN:
        return None, Response({"detail": "قسم واتساب لصاحب المتجر وحده"}, status=403)
    tenant = request.user.tenant
    if tenant is None:
        return None, Response({"detail": "لا يوجد متجر"}, status=400)
    account, _ = WhatsAppAccount.objects.get_or_create(tenant=tenant)
    return account, None


def _stale(account) -> bool:
    """هل صمت البوت؟ نبضته كل بضع ثوانٍ، فدقيقتان صمتاً تعني أنه لا يعمل."""
    if not account.last_seen:
        return True
    return (timezone.now() - account.last_seen).total_seconds() > 120


def _account_row(account) -> dict:
    running = not _stale(account)
    return {
        "status": account.status if running else WhatsAppAccount.Status.CLOSED,
        "status_label": account.get_status_display() if running else "البوت لا يعمل",
        "bot_running": running,
        "qr": account.qr if running else "",
        "device_number": phone.pretty(account.device_number),
        "error": account.error,
        "enabled": account.enabled,
        "min_delay": account.min_delay,
        "max_delay": account.max_delay,
        "batch_size": account.batch_size,
        "batch_pause": account.batch_pause,
        "balance_template": account.balance_template,
        "last_seen": account.last_seen.strftime("%Y-%m-%d %H:%M:%S") if account.last_seen else "",
        "placeholders": [
            {"token": ar, "alt": en, "desc": desc} for ar, en, desc in tpl.PLACEHOLDERS
        ],
    }


@api_view(["GET", "PUT"])
@permission_classes([IsAuthenticated])
def settings_view(request):
    """قراءة/تحديث قالب الرسالة وإعدادات التهدئة."""
    account, err = _guard(request)
    if err:
        return err

    if request.method == "PUT":
        data = request.data
        if "balance_template" in data:
            text = str(data["balance_template"] or "")
            if len(text) > 2000:
                return Response({"detail": "القالب طويل جداً (2000 حرف كحدّ أقصى)"}, status=400)
            account.balance_template = text
        if "enabled" in data:
            account.enabled = bool(data["enabled"])
        for key, lo, hi in (("min_delay", 1, 600), ("max_delay", 1, 600),
                            ("batch_size", 1, 500), ("batch_pause", 0, 7200)):
            if key in data:
                try:
                    val = int(data[key])
                except (TypeError, ValueError):
                    return Response({"detail": f"قيمة غير صحيحة لـ {key}"}, status=400)
                if not lo <= val <= hi:
                    return Response({"detail": f"{key} خارج المدى المسموح"}, status=400)
                setattr(account, key, val)
        if account.min_delay > account.max_delay:
            return Response({"detail": "أقلّ تأخير يجب ألّا يتجاوز أكثره"}, status=400)
        account.save()

    return Response(_account_row(account))


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def status_view(request):
    """حالة الجلسة — تستفتيها الواجهة كل ثانيتين أثناء الربط."""
    account, err = _guard(request)
    if err:
        return err
    return Response(_account_row(account))


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def connect_view(request):
    """يطلب من البوت بدء جلسة — يلتقط الطلب في نبضته التالية ويعيد رمز QR."""
    account, err = _guard(request)
    if err:
        return err
    if _stale(account):
        return Response(
            {"detail": "برنامج واتساب لا يعمل الآن — شغّله على الجهاز ثم أعد المحاولة"},
            status=409,
        )
    account.want = WhatsAppAccount.Want.START
    account.error = ""
    account.save(update_fields=["want", "error", "updated_at"])
    return Response(_account_row(account))


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def logout_view(request):
    """قطع الجلسة ومسح مفاتيحها — يلزم بعدها مسح رمز QR من جديد."""
    account, err = _guard(request)
    if err:
        return err
    account.want = WhatsAppAccount.Want.LOGOUT
    account.save(update_fields=["want", "updated_at"])
    return Response(_account_row(account))


def _dealers(tenant):
    return (
        # طلب تسجيلٍ لم يُقبل بعد ليس وكيلاً: لا تُرسَل إليه رسائل تحصيلٍ ولا إعلانات
        User.objects.filter(tenant=tenant, role=User.Role.BAYI)
        .exclude(status=User.Status.PENDING)
        .select_related("wallet", "tenant")
        .order_by("name")
    )


def _dealer_of(request, dealer_id):
    return _dealers(request.user.tenant).get(pk=dealer_id)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def preview_view(request):
    """معاينة القالب على وكيل حقيقي — بلا حفظ وبلا إرسال."""
    account, err = _guard(request)
    if err:
        return err
    template = request.data.get("balance_template", account.balance_template)
    dealer_id = request.data.get("dealer_id")
    dealer = None
    if dealer_id:
        try:
            dealer = _dealer_of(request, dealer_id)
        except User.DoesNotExist:
            return Response({"detail": "الوكيل غير موجود"}, status=404)
    else:
        dealer = _dealers(request.user.tenant).filter(whatsapp__gt="").first() \
            or _dealers(request.user.tenant).first()
    if dealer is None:
        return Response({"text": "", "detail": "لا يوجد وكلاء للمعاينة"})
    return Response({
        "text": tpl.render(template, dealer),
        "dealer": {"id": dealer.id, "name": dealer.name,
                   "whatsapp": phone.pretty(dealer.whatsapp)},
    })


def _target_row(d):
    balance = cur.to_display(d, getattr(d, "wallet", None).balance
                             if getattr(d, "wallet", None) else Decimal("0"))
    return {
        "id": d.id, "name": d.name, "login_id": d.login_id,
        "whatsapp": phone.pretty(d.whatsapp),
        "balance": str(balance), "currency": cur.display_currency(d),
    }


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def targets_view(request):
    """
    مَن سيصله الإرسال الجماعي ومَن لا — **قبل** الضغط لا بعده.
    الشرط: رصيد سالب + موافقة على التحصيل الآلي + رقم واتساب صالح.
    """
    account, err = _guard(request)
    if err:
        return err
    eligible, no_consent, no_number = [], [], []
    for d in _dealers(request.user.tenant):
        wallet = getattr(d, "wallet", None)
        if not wallet or wallet.balance >= 0:
            continue
        if not d.auto_debt_collection:
            no_consent.append(_target_row(d))
        elif not d.whatsapp:
            no_number.append(_target_row(d))
        else:
            eligible.append(_target_row(d))
    return Response({
        "eligible": eligible, "no_consent": no_consent, "no_number": no_number,
        "counts": {"eligible": len(eligible), "no_consent": len(no_consent),
                   "no_number": len(no_number)},
    })


def _queue(tenant, batch=""):
    qs = OutboundMessage.objects.filter(tenant=tenant).select_related("to_user")
    if batch:
        qs = qs.filter(batch=batch)
    return qs.order_by("-id")[:100]


def _msg_row(m):
    return {
        "id": m.id,
        "name": m.to_user.name if m.to_user else "",
        "number": phone.pretty(m.to_number),
        "status": m.status, "status_label": m.get_status_display(),
        "error": m.error, "attempts": m.attempts, "batch": m.batch,
        "created_at": m.created_at.strftime("%Y-%m-%d %H:%M"),
        "sent_at": m.sent_at.strftime("%Y-%m-%d %H:%M") if m.sent_at else "",
    }


def _enqueue(account, dealers, created_by, batch=""):
    """يضع الرسائل في الطابور. البوت وحده يرسل — هنا كتابةٌ في القاعدة فقط."""
    rows = [
        OutboundMessage(
            tenant=account.tenant, to_user=d, to_number=d.whatsapp,
            text=tpl.render(account.balance_template, d),
            created_by=created_by, batch=batch,
        )
        for d in dealers
    ]
    OutboundMessage.objects.bulk_create(rows)
    return rows


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def send_view(request):
    """
    إرسال فردي لوكيل واحد — زرّ صفّه في «قائمة الوكلاء».
    لا يشترط رصيداً سالباً ولا موافقة: المالك يقصد هذا الوكيل بعينه.
    """
    account, err = _guard(request)
    if err:
        return err
    if not account.enabled:
        return Response({"detail": "إرسال واتساب معطّل من الإعدادات"}, status=400)
    try:
        dealer = _dealer_of(request, request.data.get("dealer_id"))
    except (User.DoesNotExist, ValueError, TypeError):
        return Response({"detail": "الوكيل غير موجود"}, status=404)
    if not dealer.whatsapp:
        return Response(
            {"detail": "لا رقم واتساب لهذا الوكيل — أضفه من ⚙ إعدادات الوكيل"}, status=400
        )
    rows = _enqueue(account, [dealer], request.user)
    return Response({"queued": 1, "message": _msg_row(rows[0])}, status=201)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def send_bulk_view(request):
    """
    إرسال جماعي لكل مدين وافق على التحصيل الآلي — زرّ أعلى الجدول.
    يرجع فوراً بعدد ما جُدول؛ الإرسال الفعلي يجري على مهله في البوت.
    """
    account, err = _guard(request)
    if err:
        return err
    if not account.enabled:
        return Response({"detail": "إرسال واتساب معطّل من الإعدادات"}, status=400)

    targets = [
        d for d in _dealers(request.user.tenant)
        if getattr(d, "wallet", None) and d.wallet.balance < 0
        and d.auto_debt_collection and d.whatsapp
    ]
    if not targets:
        return Response({"detail": "لا يوجد وكيل مستوفٍ للشروط"}, status=400)

    batch = uuid4().hex[:12]
    with transaction.atomic():
        _enqueue(account, targets, request.user, batch=batch)
    return Response({"queued": len(targets), "batch": batch}, status=201)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def queue_view(request):
    """آخر مئة رسالة في الطابور — لمتابعة التقدّم ومعرفة مَن فشل ولماذا."""
    account, err = _guard(request)
    if err:
        return err
    batch = request.query_params.get("batch", "")
    rows = [_msg_row(m) for m in _queue(request.user.tenant, batch)]
    pending = OutboundMessage.objects.filter(
        tenant=request.user.tenant,
        status__in=[OutboundMessage.Status.PENDING, OutboundMessage.Status.SENDING],
    ).count()
    return Response({"pending": pending, "results": rows, "session": _account_row(account)})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def cancel_pending_view(request):
    """إلغاء ما لم يُرسل بعد — مخرج الطوارئ إن انطلقت دفعة بالخطأ."""
    account, err = _guard(request)
    if err:
        return err
    n = OutboundMessage.objects.filter(
        tenant=request.user.tenant, status=OutboundMessage.Status.PENDING
    ).update(status=OutboundMessage.Status.CANCELED, error="أُلغيت يدوياً")
    return Response({"canceled": n})
