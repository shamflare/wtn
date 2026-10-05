"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.conf import settings
from django.contrib import admin
from django.http import FileResponse, Http404, HttpResponse
from django.urls import include, path, re_path

from clientapi import store_views as client_store_views
from orders import views as order_views


def spa_index(request):
    """يقدّم SPA (index.html) لأي مسار واجهة — التوجيه يتم في المتصفح."""
    index = settings.FRONTEND_DIST / "index.html"
    if index.is_file():
        return FileResponse(open(index, "rb"), content_type="text/html")
    return HttpResponse(
        "الواجهة غير مبنية بعد (frontend/dist). شغّل npm run build.",
        content_type="text/plain; charset=utf-8",
    )


def tareq_quiz(request):
    """صفحة مستقلّة (بنك أسئلة) على `/tareq` — ملف ثابت من frontend/public/tareq، لا علاقة له بالـ SPA."""
    page = settings.FRONTEND_DIST / "tareq" / "index.html"
    if page.is_file():
        return FileResponse(open(page, "rb"), content_type="text/html; charset=utf-8")
    raise Http404

urlpatterns = [
    path("admin/", admin.site.urls),
    re_path(r"^tareq/?$", tareq_quiz, name="tareq-quiz"),
    path("api/store/catalog/", order_views.store_catalog_view, name="store-catalog"),
    path("api/store/buy/", order_views.store_buy_view, name="store-buy"),
    path("api/store/orders/", order_views.store_orders_view, name="store-orders"),
    path("api/store/summary/", order_views.store_summary_view, name="store-summary"),
    path("api/store/report/", order_views.store_report_view, name="store-report"),
    path("api/store/wallet/", order_views.store_wallet_view, name="store-wallet"),
    path("api/store/change-password/", order_views.store_change_password_view, name="store-change-password"),
    path("api/store/api-token/", client_store_views.my_api_token_view, name="store-api-token"),
    path("api/store/packages/", order_views.store_packages_view, name="store-packages"),
    path("api/subscription/", order_views.subscription_state_view, name="subscription-state"),
    # الواجهة الخارجية: مسارات ZDK حرفاً — خارج /api/ لأن العملاء مكتوبون لها هكذا
    path("client/api/", include("clientapi.urls")),
    path("api/", include("core.urls")),
    path("api/catalog/", include("catalog.urls")),
    path("api/providers/", include("providers.urls")),
    path("api/orders/", include("orders.urls")),
    path("api/pool/", include("pool.urls")),
    path("api/payments/", include("payments.urls")),
    path("api/platform/", include("superadmin.urls")),
    path("api/agent/", include("agent.urls")),
    path("api/whatsapp/", include("whatsapp.urls")),
    path("api/inventory/", include("inventory.urls")),
    path("api/kontor/", include("kontor.urls")),
    # catch-all: أي مسار غير API/admin/أصول → SPA
    re_path(r"^(?!api/|client/api/|admin/|static/|assets/).*$", spa_index, name="spa"),
]
