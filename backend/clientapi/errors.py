"""
أكواد أخطاء الواجهة الخارجية.

`120` و`100` مأخوذان من وثيقة ZDK حرفاً ([docs/integrations/ZDK_API.md]) لأن
كود المتاجر الخارجية يتعامل معهما أصلاً. أمّا البقيّة فأرقامنا نحن ضمن المدى
الذي تتركه ZDK غير موصوف — لا تدّعِ أنها تطابق معانيها هناك.
"""
from rest_framework.response import Response

TOKEN_REQUIRED = (120, "Api Token is required!")
TOKEN_INVALID = (121, "Invalid api token")
ACCOUNT_DISABLED = (122, "Account is disabled")
# مستقلّ عن 122 عمداً: «موقوف» يعالجه الوكيل، و«غير مأذون» يعالجه صاحب المتجر
API_NOT_ENABLED = (123, "API access is not enabled for this account")
# توكن متجرٍ نُودي به على عنوان متجرٍ آخر — مستقلّ كي لا يُشخَّص خطأَ توكن
WRONG_STORE_HOST = (124, "This token does not belong to the store at this address")

INSUFFICIENT_BALANCE = (100, "Insufficient balance")
PRODUCT_NOT_FOUND = (105, "Product not found")
PRODUCT_UNAVAILABLE = (106, "Product is not available")
UUID_REQUIRED = (107, "order_uuid is required and must be a valid UUID")
PLAYER_ID_REQUIRED = (108, "playerId is required for this product")
QTY_UNSUPPORTED = (109, "Only qty=1 is supported")
ORDER_REJECTED = (110, "Order rejected")

# شحن الخطوط (موبايل) — أرقامنا نحن، لا مقابل لها في ZDK
GSM_INVALID = (111, "gsm must be a Turkish mobile number: 10 digits starting with 5")
OPERATOR_INVALID = (112, "operator must be one of: Turkcell, Vodafone, Avea, Callback")
QUERY_NOT_ALLOWED = (113, "Live offers query is not allowed for this account on this operator")
LIVE_UNAVAILABLE = (114, "Operator lookup is temporarily unavailable — retry shortly")
OPERATOR_UNKNOWN = (115, "Could not detect the operator for this number")

SERVER_ERROR = (500, "Server error")


def error(spec, detail: str = "", http_status: int = 400) -> Response:
    """جسم خطأ واحد لكل المسارات — `status` و`code` و`message`."""
    code, message = spec
    return Response(
        {"status": "error", "code": code, "message": detail or message},
        status=http_status,
    )
