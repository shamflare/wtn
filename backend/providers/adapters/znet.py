"""محوّل ZNET — مصادقة بـ query params، استجابات pipe-separated (النمط التركي)."""
import json
import random
import time
from decimal import Decimal, InvalidOperation

import re

import requests

from core import netguard

from .base import BalanceResult, BaseAdapter, ExecutionResult, PackageList


class ZnetAdapter(BaseAdapter):
    """
    config المتوقّع: {base_url, kod, sifre, orders_path?}
    place_order → GET {base}/servis/pin_ekle.php?kod&sifre&oyun&referans&musteri_tel&oyuncu_bilgi
    استجابة النجاح: "OK|cost|balance" · الفشل: "<code>|رسالة"
    get_balance → GET {base}/servis/bakiye_kontrol.php?kod&sifre → "OK|رصيد|دين"
    """

    code = "znet"

    def _base(self, config: dict) -> str:
        return (config.get("base_url") or "").rstrip("/")

    @staticmethod
    def _gen_referans() -> str:
        return str(int(time.time() * 1000) + random.randint(100, 999))

    def place_order(self, order, config: dict, provider=None, depth: int = 0) -> ExecutionResult:
        base = self._base(config)
        if not base or not config.get("kod") or not config.get("sifre"):
            return ExecutionResult(status="failed", note="إعداد ZNET ناقص (base_url/kod/sifre)")

        referans = self._gen_referans()
        path = _path(config, "orders_path", "servis/pin_ekle.php")
        # ZNET يطلب `oyun` (معرّف اللعبة) **و** `kupur` (كود الكوبون) معاً —
        # إرسال `oyun` وحده يردّ "Kupur Bilgisi Bulunamadı".
        package_id, extra = self.link_for(order, provider)
        kupur = extra.get("kupur") or order.product.kupur or ""
        params = {
            "kod": config["kod"], "sifre": config["sifre"],
            "oyun": package_id,
            "referans": referans,
            "musteri_tel": order.customer_phone or order.player_id,
            "oyuncu_bilgi": order.player_id,
        }
        if kupur:
            params["kupur"] = kupur
        try:
            resp = netguard.get(
                f"{base}/{path}", params=params,
                headers={"Accept": "application/json"}, timeout=(5, 30),
            )
        except (requests.RequestException, netguard.UnsafeURL) as e:
            return ExecutionResult(status="failed", note=_conn_note("ZNET", e))

        return self.parse_place(resp.text, referans, resp.status_code)

    def get_balance(self, config: dict, provider=None) -> BalanceResult:
        base = self._base(config)
        if not base or not config.get("kod") or not config.get("sifre"):
            return BalanceResult(ok=False, note="إعداد ZNET ناقص (base_url/kod/sifre)")
        path = _path(config, "balance_path", "servis/bakiye_kontrol.php")
        try:
            resp = netguard.get(
                f"{base}/{path}",
                params={"kod": config["kod"], "sifre": config["sifre"]},
                timeout=(5, 20),
            )
        except (requests.RequestException, netguard.UnsafeURL) as e:
            return BalanceResult(ok=False, note=_conn_note("ZNET", e))
        return self.parse_balance(resp.text, resp.status_code)

    def fetch_status(self, order, config: dict, provider=None) -> ExecutionResult:
        """GET servis/pin_kontrol.php?kod&sifre&tahsilat_api_islem_id={referans}."""
        base = self._base(config)
        ref = (order.provider_ref or "").strip()
        if not base or not config.get("kod") or not config.get("sifre"):
            return ExecutionResult(status="unsupported", note="إعداد ZNET ناقص")
        if not ref:
            return ExecutionResult(status="unsupported", note="لا مرجع (referans) لهذا الطلب")
        path = _path(config, "status_path", "servis/pin_kontrol.php")
        try:
            resp = netguard.get(
                f"{base}/{path}",
                params={"kod": config["kod"], "sifre": config["sifre"],
                        "tahsilat_api_islem_id": ref},
                headers={"Accept": "application/json"}, timeout=(5, 20),
            )
        except (requests.RequestException, netguard.UnsafeURL) as e:
            return ExecutionResult(status="unsupported", note=_conn_note("ZNET", e))
        if resp.status_code >= 400:
            return ExecutionResult(status="unsupported", note=f"HTTP {resp.status_code}",
                                   raw=resp.text)
        return self.parse_status(resp.text)

    def list_packages(self, config: dict, provider=None) -> PackageList:
        """كتالوج ZNET: GET servis/pin_listesi.php?kod&sifre."""
        base = self._base(config)
        if not base or not config.get("kod") or not config.get("sifre"):
            return PackageList(ok=False, note="إعداد ZNET ناقص (base_url/kod/sifre)")
        path = _path(config, "catalog_path", "servis/pin_listesi.php")
        try:
            resp = netguard.get(
                f"{base}/{path}",
                params={"kod": config["kod"], "sifre": config["sifre"]},
                headers={"Accept": "application/json"}, timeout=(5, 30),
            )
        except (requests.RequestException, netguard.UnsafeURL) as e:
            return PackageList(ok=False, note=_conn_note("ZNET", e))
        return self.parse_packages(resp.text, resp.status_code)

    @classmethod
    def parse_packages(cls, text: str, http_status: int = 200) -> PackageList:
        """
        ZNET يردّ إمّا JSON ({success, result:[…]} أو مصفوفة)، أو أسطراً
        pipe-separated: id|الاسم|اللعبة|kupur|السعر.
        """
        if http_status >= 400:
            return PackageList(ok=False, note=f"HTTP {http_status}", raw=text)

        text = (text or "").strip()
        if not text:
            return PackageList(ok=False, note="استجابة فارغة من ZNET")

        rows = None
        try:
            data = json.loads(text)
        except ValueError:
            data = None
        if isinstance(data, list):
            rows = data
        elif isinstance(data, dict):
            # الوثيقة: عند الخطأ success=false وشرحه في الحقل error
            if data.get("success") is False:
                msg = data.get("error") or data.get("message") or "رفض ZNET الطلب"
                return PackageList(ok=False, note=str(msg), raw=text)
            rows = data.get("result")
            if rows is None:
                rows = data.get("data")
            if rows is None:
                rows = data.get("products")
            if rows is None:
                msg = data.get("error") or data.get("message") or "استجابة ZNET غير متوقّعة"
                return PackageList(ok=False, note=str(msg), raw=text)

        packages = []
        if rows is not None:
            for it in rows:
                if not isinstance(it, dict):
                    continue
                packages.append({
                    # `oyun` المُرسَل في pin_ekle هو oyun_bilgi_id إن وُجد
                    "id": str(it.get("oyun_bilgi_id") or it.get("id") or ""),
                    "name": str(it.get("adi") or it.get("name") or ""),
                    "game": str(it.get("oyun_adi") or it.get("game") or ""),
                    "kupur": str(it.get("kupur") or ""),
                    "price": str(it.get("fiyat") or it.get("price") or ""),
                    "note": str(it.get("aciklama") or "")[:160],
                })
        else:
            # ارتداد: أسطر pipe-separated — id|الاسم|اللعبة|kupur|السعر
            rows_p = [cls.split_pipe(l) for l in text.splitlines() if l.strip()]
            # سطر واحد بجزأين أو أقل = رسالة خطأ لا كتالوج ("3|Yetkisiz erisim")
            if len(rows_p) == 1 and len(rows_p[0]) <= 2:
                only = rows_p[0]
                return PackageList(
                    ok=False, note=only[1] if len(only) > 1 else text, raw=text,
                )
            for p in rows_p:
                if len(p) < 2 or p[0].upper() == "OK":
                    continue
                packages.append({
                    "id": p[0], "name": p[1],
                    "game": p[2] if len(p) > 2 else "",
                    "kupur": p[3] if len(p) > 3 else "",
                    "price": p[4] if len(p) > 4 else "",
                })

        if not packages:
            return PackageList(ok=False, note="لم يُعِد ZNET أي باقة", raw=text)
        return PackageList(ok=True, packages=packages, raw=text[:2000])

    def parse_balance(self, text: str, http_status: int = 200) -> BalanceResult:
        """تحليل bakiye_kontrol: "OK|رصيد|دين" أو "<code>|رسالة"."""
        if http_status >= 400:
            return BalanceResult(ok=False, note=f"HTTP {http_status}", raw=text)
        parts = self.split_pipe(text)
        if parts and parts[0].upper() == "OK":
            def dec(i):
                try:
                    return Decimal(parts[i].replace(",", "."))
                except (IndexError, InvalidOperation, ValueError):
                    return None
            return BalanceResult(ok=True, balance=dec(1), debt=dec(2), raw=text)
        if not (text or "").strip():
            # الوثيقة: الوكيل غير موجود · API غير مفعّل · IP الثابت غير مطابق
            return BalanceResult(ok=False, raw=text, note=(
                "ردّ ZNET فارغ — أحد ثلاثة: الحساب غير موجود · صلاحية API غير "
                "مفعّلة · الـ IP الثابت غير مطابق"
            ))
        msg = parts[1] if len(parts) > 1 else text
        return BalanceResult(ok=False, note=netguard.brief(msg), raw=text)

    def parse_place(self, text: str, referans: str, http_status: int = 200) -> ExecutionResult:
        """تحليل استجابة pin_ekle: OK|cost|balance أو code|message."""
        if http_status >= 400:
            return ExecutionResult(status="failed", note=f"HTTP {http_status}", raw=text)
        parts = self.split_pipe(text)
        if parts and parts[0].upper() == "OK":
            cost = None
            if len(parts) > 1:
                try:
                    cost = Decimal(parts[1])
                except (InvalidOperation, ValueError):
                    cost = None
            # ZNET يؤكّد الإرسال؛ الـ PIN يُجلب لاحقاً عبر fetch_status → نعدّه قيد المعالجة
            return ExecutionResult(
                status="processing", external_ref=referans, cost=cost,
                note=text.strip(), raw=text,
            )
        msg = parts[1] if len(parts) > 1 else (text or "فشل غير معروف")
        return ExecutionResult(status="failed", note=msg, external_ref=referans, raw=text)

    @staticmethod
    def parse_status(text: str) -> ExecutionResult:
        """تحليل pin_kontrol: OK|<1|2|3>|PIN|رسالة."""
        parts = [p.strip() for p in (text or "").split("|")]
        if not parts or parts[0].upper() != "OK":
            # ردّ غير OK = فشل **الاستعلام** لا فشل الطلب — لا نغيّر حالة الطلب
            msg = parts[1] if len(parts) > 1 else (text or "استجابة فارغة")
            return ExecutionResult(status="unsupported", note=msg, raw=text)
        code = parts[1] if len(parts) > 1 else ""
        pin = parts[2] if len(parts) > 2 else ""
        # ملاحظة مسؤول ZNET هي **كل** ما بعد الحقل الثالث: قد يكتب فيها `|`
        # فتنقسم، وأخذ الجزء الأول وحده كان يقطعها.
        msg = " | ".join(p for p in parts[3:] if p)
        mapping = {"1": "processing", "2": "success", "3": "failed"}
        status = mapping.get(code, "processing")
        if status == "failed" and pin and not msg:
            # إلغاءٌ بلا كود: ما كُتب في خانة الكود هو سبب الإلغاء لا كود
            msg, pin = pin, ""
        return ExecutionResult(status=status, pin=pin, note=msg, raw=text)


def _conn_note(name: str, e: Exception) -> str:
    """
    سبب تعذّر الاتصال **بلا الرابط**: نصّ استثناء requests يحوي الرابط كاملاً بمعاملاته
    (kod/sifre) — ويظهر في ملاحظات الطلب لصاحب المتجر. والعنوان الداخلي يُذكر صراحةً.
    """
    if isinstance(e, netguard.UnsafeURL):
        return f"رابط المزوّد مرفوض: {e}"
    return f"تعذّر الاتصال بـ {name} ({type(e).__name__})"


PATH_RE = re.compile(r"^servis/[A-Za-z0-9_]+\.php$")


def _path(config: dict, key: str, default: str) -> str:
    """مسارٌ مخصّص يُقبل بنمط ZNET وحده (servis/xxx.php) — لا مسارَ عشوائياً على الخادم."""
    v = str(config.get(key) or "").strip().lstrip("/")
    return v if PATH_RE.match(v) else default
