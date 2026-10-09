"""روابط الـ API للقلب."""
from django.urls import path

from . import registration, alerts, cards, finance, tickets, views

urlpatterns = [
    # هويّة متجر هذا العنوان — مفتوحةٌ بلا توكن، تقرأها صفحة الدخول
    path("storefront/", views.storefront_view, name="storefront"),
    path("storefront/games/", registration.public_games_view, name="storefront-games"),
    path("storefront/register/", registration.register_view, name="storefront-register"),
    path("auth/login/", views.login_view, name="login"),
    path("auth/me/", views.me_view, name="me"),
    path("settings/site/", views.site_settings_view, name="site-settings"),
    path("settings/sms/", views.sms_settings_view, name="sms-settings"),
    path("settings/theme/", views.theme_config_view, name="theme-config"),
    path("settings/agent-theme/", views.agent_theme_view, name="agent-theme"),
    path("settings/exchange/", views.exchange_rates_view, name="exchange-rates"),
    path("ledger/", views.ledger_view, name="ledger"),
    path("dealers/", views.dealers_view, name="dealers"),
    path("dealers/<int:dealer_id>/transactions/", views.wallet_transactions_view, name="wallet-txns"),
    # قبل مسار <str:action> وإلا ابتلعه
    path("dealers/<int:dealer_id>/settings/", views.dealer_settings_view, name="dealer-settings"),
    path("dealers/<int:dealer_id>/registration/", registration.registration_review_view,
         name="dealer-registration"),
    path("dealers/<int:dealer_id>/<str:action>/", views.wallet_operation_view, name="wallet-op"),
    # التذاكر / الرسائل
    path("tickets/", tickets.tickets_view, name="tickets"),
    path("tickets/unread-count/", tickets.unread_count_view, name="tickets-unread"),
    path("tickets/<int:ticket_id>/", tickets.ticket_thread_view, name="ticket-thread"),
    path("tickets/<int:ticket_id>/reply/", tickets.ticket_reply_view, name="ticket-reply"),
    path("tickets/<int:ticket_id>/close/", tickets.ticket_close_view, name="ticket-close"),
    path("announcement/", views.announcement_view, name="announcement"),
    # بطاقات الصفحة الرئيسية: كتابةٌ لمن تحتي، وقراءةٌ لما كُتب لي
    path("cards/", cards.cards_view, name="cards"),
    path("cards/<int:card_id>/", cards.card_detail_view, name="card-detail"),
    path("my-cards/", cards.my_cards_view, name="my-cards"),
    path("my-cards/seen/", cards.mark_cards_seen_view, name="my-cards-seen"),
    path("notifications/", tickets.notifications_view, name="notifications"),
    path("alerts/", alerts.alerts_view, name="alerts"),
    # تقارير المال لصاحب المتجر (core/finance.py)
    path("finance/agents/", finance.agents_view, name="finance-agents"),
    path("finance/manual/", finance.manual_view, name="finance-manual"),
    path("finance/deposits/", finance.deposits_view, name="finance-deposits"),
    path("finance/debts/", finance.debts_view, name="finance-debts"),
    # فواتير المستأجر الحالي
    path("invoices/", views.my_invoices_view, name="my-invoices"),
]
