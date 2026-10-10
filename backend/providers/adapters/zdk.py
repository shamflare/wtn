"""
محوّل **ZDK** — البرمجية التي تُدار بها متاجر بطاقات عدّة (Ap4Stor · Barakat
وغيرها). المتجر يتغيّر، والـ API واحد: مصادقة بـ `api-token` في الهيدر فقط
(لا اسم مستخدم ولا كلمة سر) واستجابات JSON تحت `/client/api/`.

لذلك النوع عندنا `zdk` لا اسم متجر بعينه — فكل متجر جديد على البرمجية نفسها
يُضاف بلا محوّل جديد ولا اسم نوع جديد. الكودان القديمان `barakat`/`apstore`
ما زالا يُقبَلان في `registry.adapter_for` حفاظاً على المزوّدين المُعدّين سابقاً.

الوثيقة الرسمية: <https://api.ap4stor.com/api-docs> — ملخّصها المعتمد في
`docs/integrations/ZDK_API.md`.
"""
import uuid
from decimal import Decimal, InvalidOperation
from urllib.parse import quote

import requests

from core import netguard

from .base import BalanceResult, BaseAdapter, ExecutionResult, PackageList


# المتجر الافتراضي حين لا يضبط الأدمن رابطاً — البرمجية واحدة والمضيف يتغيّر
DEFAULT_BASE = "https://api.ap4stor.com"

# مفاتيح `ProductLink.extra` الخاصّة بنا — لا تُرسل إلى المزوّد.
# `price` يكتبه تعلّم حماية الخسارة، و`kupur` خاصّ بـ ZNET.
# مفاتيحنا الداخلية على الربط — لا تُرسَل للمزوّد معاملاتٍ (auto وtype وسمان عندنا)
_RESERVED_EXTRA = {"price", "kupur", "name", "note", "auto", "type"}

# ZDK: accept = نُفّذ · reject = رُفض · wait = قيد المعالجة
_STATUS_MAP = {
    "accept": "success", "success": "success", "ok": "success",
    "done": "success", "complete": "success", "completed": "success",
    "reject": "failed", "rejected": "failed", "failed": "failed",
    "fail": "failed", "error": "failed", "cancelled": "failed",
    "wait": "processing", "pending": "processing", "processing": "processing",
    "inprogress": "processing", "queued": "processing",
}


def _map_status(s: str) -> str:
    """حالة غير معروفة ⇒ processing: نُبقي الطلب تحت المتابعة ولا نحسمه بالظنّ."""
    return _STATUS_MAP.get((s or "").strip().lower(), "processing")


def _replay_note(d: dict) -> str:
    """
    `replay_api` رسالة المزوّد للزبون — تأتي بشكلين:
    `[{"replay": ["نص"]}]` في newOrder و `["نص"]` في check.
    """
    rows = d.get("replay_api")
    if not rows:
        return ""
    out = []
    for it in rows if isinstance(rows, list) else [rows]:
        if isinstance(it, dict):
            r = it.get("replay")
            out += [str(x) for x in r] if isinstance(r, list) else [str(r or "")]
        else:
            out.append(str(it))
    return " · ".join(x for x in out if x.strip())[:250]


class ZdkAdapter(BaseAdapter):
    """
    config المتوقّع: {api_token} — و`base_url` اختياري لتحديد المتجر.
    place_order  → GET {base}/client/api/newOrder/{package_id}/params?qty&order_uuid&playerId
    fetch_status → GET {base}/client/api/check?orders={ref}[&uuid=1]
    get_balance  → GET {base}/client/api/profile
    """

    code = "zdk"
    supports_quantity = True   # newOrder/{id}/params?qty=…

    def _base(self, config: dict) -> str:
        return ((config.get("base_url") or "").strip() or DEFAULT_BASE).rstrip("/")

    def _headers(self, config: dict) -> dict:
        return {"api-token": config.get("api_token") or "", "Accept": "application/json"}

    @staticmethod
    def _order_uuid(order) -> str:
        """
        UUID ثابت مشتقّ من رقم الفيش. الوثيقة تنصّ أن الطلب **idempotent** بالـ
        uuid — فإعادة إرسال الفيش نفسه لا تُنشئ طلباً مكرّراً لدى المزوّد.
        عشوائيٌّ جديد كل محاولة كان سيفتح باب الشحن المزدوج.
        """
        return str(uuid.uuid5(uuid.NAMESPACE_URL, f"wtn:order:{order.receipt_no}"))

    def place_order(self, order, config: dict, provider=None, depth: int = 0) -> ExecutionResult:
        base = self._base(config)
        if not config.get("api_token"):
            return ExecutionResult(status="failed", note="إعداد ZDK ناقص (api-token)")

        package_id, extra = self.link_for(order, provider)
        if not package_id:
            return ExecutionResult(status="failed", note="لا رقم ربط لهذه الباقة لدى ZDK")
        their = str((extra or {}).get("type") or "").lower()
        is_amount = getattr(order.product, "is_amount", False)
        if their and (their == "amount") != is_amount:
            return ExecutionResult(status="failed", note=(
                "الربط خاطئ: باقةٌ بالكمية مربوطةٌ بباقةٍ ثابتة لدى ZDK — صحّحه من «ربط الباقات»"
                if is_amount else
                "الربط خاطئ: باقةٌ ثابتة مربوطةٌ بمنتجٍ بالكمية لدى ZDK — صحّحه من «ربط الباقات»"))

        order_uuid = self._order_uuid(order)
        # الكمية للباقة «بالكمية» (منتج amount لدى ZDK)، و1 للباقة الثابتة
        qty = order.quantity if getattr(order.product, "is_amount", False) else 1
        params = {"qty": str(qty), "order_uuid": order_uuid}
        if order.player_id:
            params["playerId"] = order.player_id
        # معاملات إضافية يطلبها المنتج (حقل `params` في كتالوج ZDK) — يضبطها
        # الأدمن على الربط. الوثيقة تسمح بمفاتيح إضافية حرّة.
        for k, v in (extra or {}).items():
            if k not in _RESERVED_EXTRA and v not in (None, ""):
                params[k] = str(v)

        try:
            resp = netguard.get(
                f"{base}/client/api/newOrder/{quote(str(package_id))}/params",
                params=params, headers=self._headers(config), timeout=(5, 30),
            )
            data = resp.json()
        except (requests.RequestException, netguard.UnsafeURL) as e:
            return ExecutionResult(status="failed", note=_conn_note("ZDK", e))
        except ValueError:
            return ExecutionResult(status="failed", note="استجابة ZDK غير صالحة", raw=resp.text)

        return self.parse_place(data, order_uuid)

    def fetch_status(self, order, config: dict, provider=None) -> ExecutionResult:
        """GET client/api/check?orders={order_id} — أو بالـ uuid عند غياب رقم المزوّد."""
        base = self._base(config)
        ref = (order.provider_ref or "").strip()
        if not config.get("api_token"):
            return ExecutionResult(status="unsupported", note="إعداد ZDK ناقص (api-token)")
        if not ref:
            return ExecutionResult(status="unsupported", note="لا مرجع لهذا الطلب لدى ZDK")

        params = {"orders": ref}
        if self._is_uuid(ref):
            params["uuid"] = "1"
        try:
            resp = netguard.get(
                f"{base}/client/api/check", params=params,
                headers=self._headers(config), timeout=(5, 20),
            )
            data = resp.json()
        except (requests.RequestException, netguard.UnsafeURL) as e:
            return ExecutionResult(status="unsupported", note=_conn_note("ZDK", e))
        except ValueError:
            return ExecutionResult(status="unsupported", note="استجابة ZDK غير صالحة",
                                   raw=getattr(resp, "text", ""))
        return self.parse_status(data)

    @staticmethod
    def _is_uuid(value: str) -> bool:
        try:
            uuid.UUID(value)
            return True
        except (ValueError, AttributeError, TypeError):
            return False

    def list_packages(self, config: dict, provider=None) -> PackageList:
        """كتالوج ZDK: GET {base}/client/api/products بترويسة api-token."""
        base = self._base(config)
        if not config.get("api_token"):
            return PackageList(ok=False, note="إعداد ZDK ناقص (api-token)")
        try:
            resp = netguard.get(
                f"{base}/client/api/products",
                headers=self._headers(config), timeout=(5, 30),
            )
            data = resp.json()
        except (requests.RequestException, netguard.UnsafeURL) as e:
            return PackageList(ok=False, note=_conn_note("ZDK", e))
        except ValueError:
            return PackageList(ok=False, note="استجابة ZDK غير صالحة", raw=resp.text)

        rows = data if isinstance(data, list) else (data or {}).get("data") or []
        packages = [
            {
                "id": str(it.get("id") or ""),
                "name": str(it.get("name") or ""),
                "game": str(it.get("category_name") or ""),
                "kupur": "",
                "price": str(it.get("price") or ""),
                "available": bool(it.get("available", True)),
                # المعاملات التي يطلبها هذا المنتج (playerId مثلاً) — تُعين
                # الأدمن على معرفة ما يجب ضبطه على الربط.
                "note": ", ".join(str(x) for x in (it.get("params") or []))[:160],
                "params": [str(x) for x in (it.get("params") or [])],
                # «package» باقةٌ ثابتة · «amount» سعرٌ للوحدة والكمية يختارها المشتري
                "type": str(it.get("product_type") or ""),
                "qty": it.get("qty_values") or {},
            }
            for it in rows if isinstance(it, dict)
        ]
        if not packages:
            return PackageList(ok=False, note="لم يُعِد المزوّد أي باقة")
        return PackageList(ok=True, packages=packages)

    def get_balance(self, config: dict, provider=None) -> BalanceResult:
        """GET {base}/client/api/profile → {"balance": "...", "email": "..."}."""
        base = self._base(config)
        if not config.get("api_token"):
            return BalanceResult(ok=False, note="إعداد ZDK ناقص (api-token)")
        try:
            resp = netguard.get(
                f"{base}/client/api/profile",
                headers=self._headers(config), timeout=(5, 20),
            )
            data = resp.json()
        except (requests.RequestException, netguard.UnsafeURL) as e:
            return BalanceResult(ok=False, note=_conn_note("ZDK", e))
        except ValueError:
            return BalanceResult(ok=False, note="استجابة ZDK غير صالحة", raw=resp.text)

        d = data.get("data", data) if isinstance(data, dict) else {}
        raw_balance = d.get("balance") if isinstance(d, dict) else None
        if raw_balance is None:
            return BalanceResult(ok=False, raw=str(data), note=self._error_note(data))
        try:
            return BalanceResult(ok=True, balance=Decimal(str(raw_balance)), raw=str(data))
        except (InvalidOperation, ValueError):
            return BalanceResult(ok=False, note=f"رصيد غير مفهوم: {raw_balance}", raw=str(data))

    @staticmethod
    def _error_note(data) -> str:
        """رسالة الخطأ كما يعيدها ZDK — مع كودها إن وُجد (120 · 100 …)."""
        if not isinstance(data, dict):
            return "استجابة غير متوقّعة من ZDK"
        msg = data.get("message") or data.get("error") or data.get("msg") or ""
        code = data.get("code") or data.get("error_code") or ""
        if msg and code:
            return f"{code} — {msg}"[:250]
        return str(msg or code or "لم يُعِد المزوّد رسالة")[:250]

    @staticmethod
    def _cost_of(d: dict):
        try:
            return Decimal(str(d["price"])) if d.get("price") is not None else None
        except (InvalidOperation, ValueError):
            return None

    def parse_place(self, data: dict, order_uuid: str = "") -> ExecutionResult:
        """
        استجابة newOrder: {status, data:{order_id, status, price, data, replay_api}}.
        الحالة تُقرأ من `data.status` (accept/reject/wait).
        """
        if not isinstance(data, dict) or "data" not in data or not isinstance(data.get("data"), dict):
            return ExecutionResult(status="failed", note=self._error_note(data), raw=str(data))

        d = data["data"]
        # المرجع للمتابعة: رقم الطلب لدى المزوّد، وإلا الـ uuid (check يقبل كليهما)
        ref = str(d.get("order_id") or "") or order_uuid
        return ExecutionResult(
            status=_map_status(str(d.get("status") or data.get("status") or "wait")),
            pin=str(d.get("pin") or ""),
            external_ref=ref,
            note=_replay_note(d) or str(d.get("note") or ""),
            cost=self._cost_of(d),
            raw=str(data)[:2000],
        )

    def parse_status(self, data: dict) -> ExecutionResult:
        """استجابة check: {status:"OK", data:[{order_id, status, price, replay_api, …}]}."""
        rows = data.get("data") if isinstance(data, dict) else None
        if isinstance(rows, dict):
            rows = [rows]
        if not isinstance(rows, list) or not rows or not isinstance(rows[0], dict):
            # فشل **الاستعلام** لا فشل الطلب — لا نحسم حالة الطلب بالظنّ
            return ExecutionResult(status="unsupported", note=self._error_note(data),
                                   raw=str(data)[:2000])
        d = rows[0]
        return ExecutionResult(
            status=_map_status(str(d.get("status") or "wait")),
            pin=str(d.get("pin") or ""),
            external_ref=str(d.get("order_id") or ""),
            note=_replay_note(d),
            cost=self._cost_of(d),
            raw=str(data)[:2000],
        )


def _conn_note(name: str, e: Exception) -> str:
    """
    سبب تعذّر الاتصال **بلا الرابط**: نصّ استثناء requests يحوي الرابط كاملاً بمعاملاته
    (kod/sifre) — ويظهر في ملاحظات الطلب لصاحب المتجر. والعنوان الداخلي يُذكر صراحةً.
    """
    if isinstance(e, netguard.UnsafeURL):
        return f"رابط المزوّد مرفوض: {e}"
    return f"تعذّر الاتصال بـ {name} ({type(e).__name__})"
