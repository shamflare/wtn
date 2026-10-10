"""
حارس الاتصال الخارجي (SSRF): الخادم لا يتصل بعنوانٍ داخلي بطلب صاحب متجر.

صاحب المتجر يكتب رابط مزوّده، وخادمنا يتصل به ويعرض الردّ. بلا هذا الحارس يكتب
عنواناً داخلياً (`169.254.169.254` بيانات الخادم، `kontor-session:8700`، `web:8000`،
`localhost`…) فيتصل **خادمُنا من داخل الشبكة** ويعيد له ما وجد.

القاعدة (قرار المالك 2026-10-10): http وhttps كلاهما مقبول — ZNET يعمل أحياناً بلا S —
لكن العنوان يجب أن يكون **عاماً على الإنترنت**: لا عنوان خاصّ ولا محلّي ولا اسم خدمةٍ
داخلية. ويُفحص عند الحفظ، وعند **كل اتصال** (فالاسم قد يتغيّر عنوانه بعد الحفظ)، وعند
**كل تحويل** (redirect) — خادمٌ خارجيّ قد يحوّل الاتصال إلى عنوانٍ داخلي.
"""
import ipaddress
import socket
from urllib.parse import urljoin, urlparse

import requests
from django.conf import settings

REDIRECTS = (301, 302, 303, 307, 308)
MAX_REDIRECTS = 3
# أسماء خدماتنا داخل شبكة Docker وأشباهها — لا تُقبل وإن لم تُحَلّ إلى عنوانٍ خاص
INTERNAL_NAMES = {"localhost", "web", "db", "caddy", "bot", "kontor-session", "redis", "postgres"}


class UnsafeURL(Exception):
    pass


def _bad_ip(ip: str) -> bool:
    a = ipaddress.ip_address(ip)
    return (a.is_private or a.is_loopback or a.is_link_local or a.is_reserved
            or a.is_multicast or a.is_unspecified or not a.is_global)


def check(url: str) -> None:
    """يرفع UnsafeURL إن لم يكن الرابط http(s) إلى عنوانٍ عامّ. لا شيء إن كان سليماً."""
    if not getattr(settings, "NET_GUARD", True):
        return
    p = urlparse(str(url or "").strip())
    if p.scheme not in ("http", "https") or not p.hostname:
        raise UnsafeURL("الرابط يجب أن يبدأ بـ http:// أو https://")
    host = p.hostname.lower().rstrip(".")
    if host in INTERNAL_NAMES or host.endswith(".local") or host.endswith(".internal") or "." not in host:
        raise UnsafeURL("عنوانٌ داخلي غير مسموح")
    try:
        if _bad_ip(host):
            raise UnsafeURL("عنوانٌ داخلي غير مسموح")
        return                                    # عنوان IP عامّ
    except ValueError:
        pass                                      # اسمٌ لا رقم — يُحَلّ
    try:
        infos = socket.getaddrinfo(host, p.port or (443 if p.scheme == "https" else 80))
    except socket.gaierror:
        raise UnsafeURL("تعذّر الوصول إلى هذا العنوان")
    if not infos or any(_bad_ip(i[4][0]) for i in infos):
        raise UnsafeURL("عنوانٌ داخلي غير مسموح")


def get(url: str, **kw):
    """
    `requests.get` محروس: يفحص الرابط، ولا يتبع التحويل إلا بعد فحص وجهته.
    (يُنادى `requests.get` باسمه فتعمل بدائل الاختبارات عليه كما كانت.)
    """
    kw["allow_redirects"] = False
    for _ in range(MAX_REDIRECTS + 1):
        check(url)
        resp = requests.get(url, **kw)
        code = getattr(resp, "status_code", 200)
        if not (isinstance(code, int) and code in REDIRECTS and resp.headers.get("Location")):
            return resp
        url = urljoin(url, resp.headers["Location"])
        kw.pop("params", None)                    # المعاملات صارت في الرابط المحوَّل إليه
    raise UnsafeURL("تحويلاتٌ كثيرة من المزوّد")


def brief(text, limit: int = 160) -> str:
    """
    ردّ المزوّد كما يُعرض للمستخدم: مختصراً، ولا صفحة HTML خاماً — فلا يصير حقل
    «ملاحظة» نافذةً على محتوى ما وراء الرابط.
    """
    s = " ".join(str(text or "").split())
    if s[:1] == "<" or "<html" in s[:200].lower():
        return "ردٌّ غير متوقّع من المزوّد (صفحة ويب لا ردّ API)"
    return s[:limit] + ("…" if len(s) > limit else "")
