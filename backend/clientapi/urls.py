"""مسارات الواجهة الخارجية — أسماؤها منسوخة عن ZDK حرفاً فلا يُعدّل كود العميل."""
from django.urls import path

from . import mobile_views, views

urlpatterns = [
    path("profile", views.profile_view, name="client-profile"),
    path("products", views.products_view, name="client-products"),
    path("newOrder/<str:product_id>/params", views.new_order_view, name="client-new-order"),
    path("check", views.check_view, name="client-check"),
    # شحن الخطوط التركية — مسارات منفصلة كي لا تختلط بمنتجات الألعاب
    path("mobile/packages", mobile_views.packages_view, name="client-mobile-packages"),
    path("mobile/detect", mobile_views.detect_view, name="client-mobile-detect"),
    path("mobile/offers", mobile_views.offers_view, name="client-mobile-offers"),
    path("mobile/newOrder/<str:package_id>/params", mobile_views.new_order_view, name="client-mobile-new-order"),
    path("mobile/check", mobile_views.check_view, name="client-mobile-check"),
]
