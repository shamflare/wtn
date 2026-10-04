"""
عميل خدمة جلسة ZNET من جهة Django: ينادي الخدمة المستقلّة ويحلّل ردّها.

عنوان الخدمة من `KONTOR_SESSION_URL` (افتراضاً http://kontor-session:8700).
يُبقي المتصفّح خارج عمّال gunicorn — هنا طلب HTTP داخليّ خفيف فقط.
"""
import os

import requests

from .panel_parse import parse_offers, parse_operator

# رمزنا ⇐ صيغة ZNET في رابط العروض
_TO_ZNET = {"Turkcell": "TURKCELL", "Vodafone": "VODAFONE",
            "Avea": "AVEA", "Callback": "CALLBACK"}


def _base() -> str:
    return os.environ.get("KONTOR_SESSION_URL", "http://kontor-session:8700").rstrip("/")


class SessionError(Exception):
    """تعذّر الوصول إلى خدمة الجلسة أو فشلها."""


def _get(path: str, params: dict) -> dict:
    try:
        r = requests.get(f"{_base()}{path}", params=params, timeout=(5, 60))
    except requests.RequestException as e:
        raise SessionError(f"تعذّر الاتصال بخدمة الجلسة: {e}")
    if r.status_code != 200:
        detail = (r.json().get("detail") if r.headers.get("content-type", "").startswith("application/json") else r.text)
        raise SessionError(detail or f"HTTP {r.status_code}")
    return r.json()


def detect_operator(gsm: str) -> str | None:
    """الشركة المكتشفة ⇐ رمزنا (Turkcell/Vodafone/Avea/Callback) أو None."""
    html = _get("/detect", {"gsm": gsm}).get("html", "")
    return parse_operator(html)


def fetch_offers(gsm: str, operator: str) -> list[dict]:
    """عروض الرقم الخاصة (بصيغة panel_parse). operator برمزنا."""
    znet_op = _TO_ZNET.get(operator, operator.upper())
    html = _get("/offers", {"gsm": gsm, "operator": znet_op}).get("html", "")
    return parse_offers(html)


def health() -> bool:
    try:
        return bool(_get("/health", {}).get("ok"))
    except SessionError:
        return False
