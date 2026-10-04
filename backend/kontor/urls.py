"""روابط إدارة كتالوج الخطوط وتسعيرها."""
from django.urls import path

from .views import (
    categories_view, import_view, package_update_view, packages_bulk_view, packages_view,
)
from .views_store import (
    buy_view, detect_view, my_orders_view, store_offers_view, store_packages_view,
)
from .views_pricing import (
    admin_orders_view, bulk_price_view, dealer_settings_view, price_group_delete_view,
    price_groups_view, price_matrix_view, set_price_view,
)

urlpatterns = [
    path("categories/", categories_view, name="kontor-categories"),
    path("packages/", packages_view, name="kontor-packages"),
    path("packages/bulk/", packages_bulk_view, name="kontor-packages-bulk"),
    path("packages/<int:pk>/", package_update_view, name="kontor-package-update"),
    path("import/", import_view, name="kontor-import"),
    # المرحلة 2 — الأسعار وربط الوكلاء
    path("price-groups/", price_groups_view, name="kontor-price-groups"),
    path("price-groups/<int:pk>/", price_group_delete_view, name="kontor-price-group-delete"),
    path("price-matrix/", price_matrix_view, name="kontor-price-matrix"),
    path("set-price/", set_price_view, name="kontor-set-price"),
    path("bulk-price/", bulk_price_view, name="kontor-bulk-price"),
    path("dealer-settings/", dealer_settings_view, name="kontor-dealer-settings"),
    path("orders/", admin_orders_view, name="kontor-admin-orders"),
    # نقاط الوكيل (store)
    path("store/detect/", detect_view, name="kontor-store-detect"),
    path("store/packages/", store_packages_view, name="kontor-store-packages"),
    path("store/offers/", store_offers_view, name="kontor-store-offers"),
    path("store/buy/", buy_view, name="kontor-store-buy"),
    path("store/orders/", my_orders_view, name="kontor-store-orders"),
]
