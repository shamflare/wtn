"""
حاجز الأدوار: ما يحقّ للوكيل والوكيل الكبير طرقه من `/api/`.

الأبواب الإدارية كانت تكتفي بشرط «من هذا المتجر» — فأيّ وكيلٍ مسجّلٍ كان يقرأ
طرق الدفع ويعدّلها، ويرى إيداعات الجميع وطلباتهم. والفحص بابٌ بابٌ يُنسى في
الباب التالي، فالحاجز هنا **قائمة سماح**: ما لم يُذكر مغلقٌ على غير صاحب المتجر.

بابٌ جديدٌ للوكيل يُضاف هنا صراحةً، وأبواب الوكيل الكبير كلّها تحت `agent/`.
"""
from rest_framework.exceptions import PermissionDenied

from .models import User

# ما يطرقه كل وكيل — بنوعيه
DEALER_PREFIXES = (
    "auth/", "storefront/", "store/", "subscription/",
    "tickets/", "notifications/", "my-cards/", "announcement/",
    "settings/theme/", "settings/agent-theme/",   # القراءة فقط — الكتابة محروسة في الباب
    "kontor/store/", "payments/store/", "catalog/img/",
    "catalog/images/",   # رفع صورة إيصال التحويل في «شحن رصيد»
)
# وفوقها للوكيل الكبير: لوحته كلّها وعدّادات هيدره
AGENT_PREFIXES = DEALER_PREFIXES + ("agent/", "alerts/")

LIMITED_ROLES = {User.Role.BAYI: DEALER_PREFIXES, User.Role.ANA_BAYI: AGENT_PREFIXES}


def check_path(user, path: str) -> None:
    """يرفع 403 إن كان الدور محدوداً والمسار خارج ما سُمح له."""
    allowed = LIMITED_ROLES.get(user.role)
    if allowed is None or not path.startswith("/api/"):
        return
    if not path[len("/api/"):].startswith(allowed):
        raise PermissionDenied("غير مصرّح")
