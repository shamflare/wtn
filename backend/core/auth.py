"""
منع الخلط بين المتاجر على العناوين الفرعية.

`login_id` فريدٌ عبر المنصّة كلّها، فالدخول ينجح من أيّ عنوان. وهذا مقبولٌ على
الباب العام (`wtn4.com` يبقى مفتوحاً للجميع بقرار المالك)، وغيرُ مقبولٍ على
عنوان متجرٍ بعينه: `islam.wtn4.com` بابُ إسلام ووكلائه لا باب المنصّة كلّها.

والحراسة هنا في **موضعين لا موضع**، لأن للتوكن حياتين:

1. عند **إصداره** — في `login_view`.
2. عند **استعماله** — هنا. توكنٌ صدر من الباب العام يظلّ صالحاً ثماني ساعات،
   وبلا هذا الفحص كان يُلصَق في متصفّحٍ مفتوحٍ على متجرٍ آخر فيعمل.
"""
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.authentication import JWTAuthentication

from .access import check_path

FOREIGN_STORE = "هذا الحساب ليس من هذا المتجر."


class StoreBoundJWTAuthentication(JWTAuthentication):
    """المصادقة المعتادة، وفوقها شرطٌ واحد: الحساب من متجر هذا العنوان."""

    def authenticate(self, request):
        result = super().authenticate(request)
        if result is None:
            return None

        user, token = result
        from .security import session_valid, tenant_suspended
        # تغيير كلمة السر أو «الخروج من كل الأجهزة» يُسقط هذه الجلسة
        if not session_valid(user, token):
            raise AuthenticationFailed("انتهت الجلسة — سجّل الدخول من جديد")
        # `request` هنا طلبُ DRF، وهو يمرّر ما لا يعرفه إلى طلب Django تحته
        store = getattr(request, "store", None)
        if store is not None and user.tenant_id != store.id:
            raise AuthenticationFailed(FOREIGN_STORE)

        # الحساب المعطَّل يُطرد فوراً — لا يبقى يعمل بتوكنه حتى تنتهي ساعاته الثماني
        if user.status != "active":
            raise AuthenticationFailed("الحساب معطّل — تواصل مع الإدارة")
        # والمتجر الموقوف كذلك — من أيّ عنوانٍ جاء (لا من عنوانه وحده)
        if tenant_suspended(user):
            raise AuthenticationFailed("المتجر موقوف — تواصل مع إدارة المنصّة")

        # والدور: الوكيل لا يطرق الأبواب الإدارية (core/access.py)
        check_path(user, request.path)
        return result
