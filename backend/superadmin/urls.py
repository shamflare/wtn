"""روابط لوحة المنصّة."""
from django.urls import path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("library/games", views.LibraryGameViewSet, basename="library-game")
router.register("library/products", views.LibraryProductViewSet, basename="library-product")
router.register("library/sources", views.LibrarySourceViewSet, basename="library-source")

urlpatterns = [
    path("tenants/", views.tenants_view, name="platform-tenants"),
    path("library/sources/<int:source_id>/catalog/", views.library_source_catalog_view, name="library-source-catalog"),
    path("library/sources/<int:source_id>/import/", views.library_source_import_view, name="library-source-import"),
    path("library/tenant-providers/", views.tenant_providers_view, name="library-tenant-providers"),
    path("tenants/<int:tenant_id>/subscription/", views.tenant_subscription_view, name="platform-tenant-subscription"),
    # التعديل والحذف قبل مسار <str:action> وإلا ابتلعهما
    path("tenants/<int:tenant_id>/", views.tenant_detail_view, name="platform-tenant-detail"),
    path("tenants/<int:tenant_id>/<str:action>/", views.tenant_status_view, name="platform-tenant-status"),
    path("announcement/", views.platform_announcement_view, name="platform-announcement"),
    path("sorgula/", views.sorgula_view, name="platform-sorgula"),
    path("sorgula/test/", views.sorgula_test_view, name="platform-sorgula-test"),
    path("sorgula/cache/", views.sorgula_cache_view, name="platform-sorgula-cache"),
    path("invoices/", views.invoices_view, name="platform-invoices"),
    path("invoices/<int:invoice_id>/<str:action>/", views.invoice_status_view, name="platform-invoice-status"),
] + router.urls
