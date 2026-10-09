"""
مدفوعات الوكيل الكبير تحت `/api/agent/payments/` — الأبواب نفسها، والنطاق من الدور:
`owner_scope` يحصر كل شيء في طرقه وحساباته وإيداعات دكاكينه هو.
"""
from django.urls import path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("accounts", views.ReceivingAccountViewSet, basename="agent-account")
router.register("methods", views.PaymentMethodViewSet, basename="agent-payment-method")

urlpatterns = [
    path("accounts-total/", views.accounts_total_view, name="agent-accounts-total"),
    path("notifications/", views.payment_notifications_view, name="agent-payment-notifications"),
    path("notifications/bulk-action/", views.payment_bulk_action_view, name="agent-payment-bulk-action"),
    path("notifications/<int:notif_id>/<str:action>/", views.payment_decide_view,
         name="agent-payment-decide"),
] + router.urls
