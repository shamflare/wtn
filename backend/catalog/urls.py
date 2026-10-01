"""روابط الكتالوج (router + مسارات مخصّصة)."""
from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    GameViewSet, PriceGroupViewSet, ProductViewSet,
    auto_route_view, bulk_price_view,
    game_library_packages_view, image_upload_view, image_view,
    library_autolink_view, library_browse_view, library_import_view,
    link_game_to_library_view,
    price_matrix_view, product_links_view, refresh_costs_view, refresh_link_prices_view,
    set_price_view,
)

router = DefaultRouter()
router.register("games", GameViewSet, basename="game")
router.register("products", ProductViewSet, basename="product")
router.register("price-groups", PriceGroupViewSet, basename="price-group")

urlpatterns = [
    path("images/", image_upload_view, name="image-upload"),
    path("img/<str:key>/", image_view, name="image"),
    path("price-matrix/", price_matrix_view, name="price-matrix"),
    path("set-price/", set_price_view, name="set-price"),
    path("bulk-price/", bulk_price_view, name="bulk-price"),
    path("auto-route/", auto_route_view, name="auto-route"),
    path("refresh-costs/", refresh_costs_view, name="refresh-costs"),
    path("games/<int:game_id>/library-packages/", game_library_packages_view,
         name="game-library-packages"),
    path("games/<int:game_id>/link-library/", link_game_to_library_view,
         name="game-link-library"),
    path("library/", library_browse_view, name="library-browse"),
    path("library/autolink/", library_autolink_view, name="library-autolink"),
    path("library/<int:library_game_id>/import/", library_import_view, name="library-import"),
    path("product-links/", product_links_view, name="product-links"),
    path("product-links/refresh-prices/", refresh_link_prices_view, name="product-links-refresh"),
] + router.urls
