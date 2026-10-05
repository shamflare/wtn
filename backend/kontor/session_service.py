"""
خدمة HTTP صغيرة تمسك جلسة ZNET واحدة (متصفّح خفيّ) وتُجيب عن الكشف والعروض.

تعمل في حاوية مستقلّة (انظر deploy). الحساب يأتي مع كل طلب في ترويسات من Django
(X-Kontor-Base/User/Pass/Image) — يضبطه مالك المنصّة من /sorgula فيُخزَّن في القاعدة.
بلا ترويسات ⇐ متغيّرات البيئة القديمة: KONTOR_BASE_URL · KONTOR_USER · KONTOR_PASS ·
KONTOR_SECURITY_IMAGE. تغيّر الحساب ⇐ تُغلق الجلسة القديمة ويُدخَل بالجديد.
المنفذ داخليّ (expose لا ports) فلا يصل إليه أحد من خارج شبكة الحاويات.

نقاط:
  GET /health                      ⇐ {"ok": true}
  GET /login                       ⇐ {"ok": true} بعد التأكّد من الدخول (اختبار الحساب)
  GET /detect?gsm=NNNNNNNNNN       ⇐ {"html": "..."}
  GET /offers?gsm=NN&operator=XX   ⇐ {"html": "..."}   (operator بصيغة ZNET)

وحيدة الخيط عمداً: حساب ZNET فردي، فتُسلسَل الطلبات.
"""
import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

from kontor.session_playwright import KontorSession

_session: KontorSession | None = None
_key: tuple | None = None


def _get_session(headers) -> KontorSession:
    """الجلسة للحساب المطلوب — تُعاد كما هي ما دام الحساب نفسه، وتُبدَّل إن تغيّر."""
    global _session, _key
    base = headers.get("X-Kontor-Base") or os.environ.get("KONTOR_BASE_URL", "")
    user = headers.get("X-Kontor-User") or os.environ.get("KONTOR_USER", "")
    pwd = headers.get("X-Kontor-Pass") or os.environ.get("KONTOR_PASS", "")
    img = headers.get("X-Kontor-Image") or os.environ.get("KONTOR_SECURITY_IMAGE", "D")
    if not (base and user and pwd):
        raise RuntimeError("حساب لوحة الكشف غير مضبوط — اضبطه من /sorgula في لوحة المنصّة")
    key = (base, user, pwd, img)
    if _session is None or key != _key:
        if _session is not None:
            try:
                _session.close()
            except Exception:  # noqa: BLE001
                pass
        _session = KontorSession(base_url=base, user=user, password=pwd, security_image=img)
        _key = key
    return _session


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, obj: dict):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        try:
            if u.path == "/health":
                return self._send(200, {"ok": True})
            if u.path == "/login":
                return self._send(200, {"ok": _get_session(self.headers).check()})
            if u.path == "/detect":
                gsm = (q.get("gsm") or [""])[0]
                if not gsm.isdigit():
                    return self._send(400, {"detail": "gsm غير صحيح"})
                return self._send(200, {"html": _get_session(self.headers).detect(gsm)})
            if u.path == "/offers":
                gsm = (q.get("gsm") or [""])[0]
                op = (q.get("operator") or [""])[0]
                if not gsm.isdigit() or not op:
                    return self._send(400, {"detail": "gsm/operator مطلوب"})
                return self._send(200, {"html": _get_session(self.headers).offers(gsm, op)})
            return self._send(404, {"detail": "not found"})
        except Exception as e:  # noqa: BLE001 — نُعيد الخطأ لا نُسقط الخدمة
            return self._send(500, {"detail": str(e)})

    def log_message(self, *args):  # صمت — لا نطبع الأرقام في السجل
        pass


def serve():
    port = int(os.environ.get("KONTOR_SESSION_PORT", "8700"))
    HTTPServer(("0.0.0.0", port), Handler).serve_forever()


if __name__ == "__main__":
    serve()
