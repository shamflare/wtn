"""روابط لوحة الوكيل الكبير."""
from django.urls import include, path

from . import pricing, reports, views

urlpatterns = [
    path("summary/", views.summary_view, name="agent-summary"),
    path("dealers/", views.dealers_view, name="agent-dealers"),
    path("orders/", reports.orders_view, name="agent-orders"),
    path("reports/summary/", reports.report_summary_view, name="agent-report-summary"),
    path("reports/dealers/", reports.report_dealers_view, name="agent-report-dealers"),
    # جرد الوكيل: أبواب جرد المتجر نفسها، محصورةً في جرده هو (inventory/views._agent)
    path("inventory/", include("inventory.urls")),
    path("alerts/", reports.alerts_view, name="agent-alerts"),
    path("price-matrix/", pricing.price_matrix_view, name="agent-price-matrix"),
    path("set-price/", pricing.set_price_view, name="agent-set-price"),
    path("bulk-price/", pricing.bulk_price_view, name="agent-bulk-price"),
    path("clear-prices/", pricing.clear_prices_view, name="agent-clear-prices"),
    path("margins/", views.margins_view, name="agent-margins"),
    path("set-margin/", views.set_margin_view, name="agent-set-margin"),
    path("price-groups/", views.price_groups_view, name="agent-price-groups"),
    path("price-groups/prices/", views.group_prices_view, name="agent-group-prices"),
    path("dealer-group/", views.set_dealer_group_view, name="agent-set-dealer-group"),
    path("dealers/<int:dealer_id>/wallet/", views.dealer_wallet_view, name="agent-dealer-wallet"),
    path("dealers/<int:dealer_id>/statement/", views.dealer_statement_view, name="agent-dealer-statement"),
    path("dealers/<int:dealer_id>/settings/", views.dealer_settings_view, name="agent-dealer-settings"),
    path("payments/", include("payments.agent_urls")),
]
