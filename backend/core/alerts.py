"""
عدّادات شريط التنبيه في الهيدر: «ما ينتظر قرارك» في كل قسم.

نقطة واحدة تُعيد الأرقام كلّها بدل سبعة نداءات — الشريط يُنادى دورياً، فسبعة
طلبات كل دقيقة ثمنٌ لا داعي له.

كل رقم يعني **شيئاً يحتاج تدخّل صاحب المتجر**، لا مجرّد إحصاء: طلب معلّق،
رسالة لم تُقرأ، إيداع ينتظر موافقة. ما لا يحتاج قراراً لا يُعدّ.
"""
from django.db.models import F, Q
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from orders.models import Order
from payments.models import PaymentNotification
from providers.models import Provider

from .models import PlatformAnnouncement, TicketMessage, User, Wallet
from .tickets import visible_tickets


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def alerts_view(request):
    """حالة كل أيقونة في الهيدر: صفر = باهتة، وأكثر = ملوّنة."""
    user = request.user
    tenant = user.tenant
    if tenant is None:
        return Response({})

    announcement = PlatformAnnouncement.get()

    return Response({
        # إعلان إدارة المنصّة — موجود أو لا
        "announcement": 1 if (announcement.message or "").strip() else 0,

        # رسائل الوكلاء التي لم تُقرأ بعد
        "tickets": TicketMessage.objects.filter(ticket__in=visible_tickets(user))
            .exclude(sender=user).filter(read_by_other=False).count(),

        # طلبات تنتظر تنفيذاً يدوياً
        "orders_pending": Order.objects.filter(
            tenant=tenant, status=Order.Status.PENDING).count(),

        # طلبات عالقة لدى مزوّد — لا تُحسم وحدها
        "orders_stuck": Order.objects.filter(
            tenant=tenant, status=Order.Status.STUCK).count(),

        # مزوّد معطّل، أو رصيده هبط تحت الحدّ الذي ضبطه المالك
        "providers": Provider.objects.filter(tenant=tenant).filter(
            Q(status=Provider.Status.PASSIVE)
            | Q(balance_alert_threshold__isnull=False,
                real_balance__lt=F("balance_alert_threshold"))
        ).count(),

        # وكلاء رصيدهم سالب — دَين على المتجر يتابعه المالك
        "dealers_negative": Wallet.objects.filter(
            tenant=tenant, balance__lt=0,
            user__role__in=[User.Role.BAYI, User.Role.ANA_BAYI],
        ).count(),

        # وكلاء سجّلوا أنفسهم من الباب العام وينتظرون قبولك
        "registrations": User.objects.filter(
            tenant=tenant, status=User.Status.PENDING).count(),

        # طلبات إيداع تنتظر قبولك أو رفضك
        "deposits_pending": PaymentNotification.objects.filter(
            tenant=tenant, status=PaymentNotification.Status.PENDING).count(),
    })
