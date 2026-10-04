"""
خدمة HTTP صغيرة تمسك جلسة ZNET واحدة (متصفّح خفيّ) وتُجيب عن الكشف والعروض.

تعمل في حاوية مستقلّة (انظر deploy). تقرأ الإعداد من البيئة:
  KONTOR_BASE_URL · KONTOR_USER · KONTOR_PASS · KONTOR_SECURITY_IMAGE · KONTOR_SESSION_PORT

نقاط:
  GET /health                      ⇐ {"ok": true}
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


def _get_session() -> KontorSession:
    global _session
    if _session is None:
        _session = KontorSession(
            base_url=os.environ["KONTOR_BASE_URL"],
            user=os.environ["KONTOR_USER"],
            password=os.environ["KONTOR_PASS"],
            security_image=os.environ.get("KONTOR_SECURITY_IMAGE", "D"),
        )
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
            if u.path == "/detect":
                gsm = (q.get("gsm") or [""])[0]
                if not gsm.isdigit():
                    return self._send(400, {"detail": "gsm غير صحيح"})
                return self._send(200, {"html": _get_session().detect(gsm)})
            if u.path == "/offers":
                gsm = (q.get("gsm") or [""])[0]
                op = (q.get("operator") or [""])[0]
                if not gsm.isdigit() or not op:
                    return self._send(400, {"detail": "gsm/operator مطلوب"})
                return self._send(200, {"html": _get_session().offers(gsm, op)})
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
