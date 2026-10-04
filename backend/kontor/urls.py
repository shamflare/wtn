"""روابط إدارة كتالوج الخطوط."""
from django.urls import path

from .views import (
    categories_view, import_view, package_update_view, packages_view,
)

urlpatterns = [
    path("categories/", categories_view, name="kontor-categories"),
    path("packages/", packages_view, name="kontor-packages"),
    path("packages/<int:pk>/", package_update_view, name="kontor-package-update"),
    path("import/", import_view, name="kontor-import"),
]
