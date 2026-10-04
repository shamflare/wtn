"""
جلسة لوحة ZNET بمتصفّح خفيّ (Playwright) — تسجيل الدخول واجتياز الصورة الأمنية،
ثم كشف الشركة وجلب العروض من داخل الجلسة. منقولة من نسخة puppeteer المُثبتة.

لا تُستورَد في مسار Django العادي: Playwright مطلوب فقط في خدمة الجلسة المستقلّة.
"""
import threading


class KontorSession:
    """جلسة واحدة مُعاد استعمالها. كل العمليات تحت قفلٍ واحد (حساب ZNET فردي)."""

    def __init__(self, base_url: str, user: str, password: str, security_image: str):
        self.base = base_url.rstrip("/")
        self.user = user
        self.password = password
        self.sec = security_image.strip().upper()  # اسم ملف الصورة بلا امتداد، مثل D
        self._lock = threading.Lock()
        self._pw = None
        self._browser = None
        self._page = None
        self._logged = False

    # ─────────── الإقلاع والدخول ───────────
    def _ensure_browser(self):
        if self._page is not None:
            return
        from playwright.sync_api import sync_playwright
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(headless=True, args=["--no-sandbox"])
        self._page = self._browser.new_context().new_page()
        self._page.on("dialog", lambda d: d.dismiss())

    def _login(self):
        self._ensure_browser()
        p = self._page
        p.goto(f"{self.base}/index.php?giris=true", wait_until="networkidle", timeout=45000)
        p.fill("#kullanici_adi", self.user)
        p.fill("#password", self.password)
        p.evaluate("() => { const b = document.getElementById('girisbutton'); if (b) b.style.display='block'; }")
        p.wait_for_timeout(2500)
        p.evaluate("() => EntryPoint.login.login()")
        p.wait_for_timeout(1500)
        if "parolax" in p.url:
            ok = p.evaluate(
                "(name) => { const i=[...document.querySelectorAll('img')]"
                ".find(x => (x.getAttribute('src')||'').endsWith(name)); if(i){i.click();return true;} return false; }",
                f"{self.sec}.png",
            )
            if not ok:
                raise RuntimeError("تعذّر إيجاد الصورة الأمنية — تحقّق من KONTOR_SECURITY_IMAGE")
            p.wait_for_load_state("networkidle", timeout=45000)
            p.wait_for_timeout(1200)
        p.goto(f"{self.base}/Kontor/index.php", wait_until="networkidle", timeout=45000)
        has_fn = p.evaluate("() => typeof znet_token_ver === 'function'")
        if not has_fn:
            raise RuntimeError("الجلسة لم تكتمل بعد الدخول (znet_token_ver غير متاح)")
        self._logged = True

    def _ensure_login(self):
        if not self._logged:
            self._login()

    def _post(self, path: str) -> str:
        return self._page.evaluate(
            "(u) => fetch(u, {method:'POST', headers:{'X-Requested-With':'XMLHttpRequest'}}).then(r => r.text())",
            path,
        )

    @staticmethod
    def _logged_out(html: str) -> bool:
        return bool(html) and "location.href" in html and len(html) < 120

    # ─────────── العمليات ───────────
    def detect(self, gsm: str) -> str:
        """رد كشف الشركة (HTML) — يعيد الدخول تلقائياً إن انتهت الجلسة."""
        with self._lock:
            self._ensure_login()
            html = self._post(f"/Kontor/bilgi_api.php?GSMNO={gsm}&operatoru=bul&kisitlama=undefined&")
            if self._logged_out(html):
                self._logged = False
                self._ensure_login()
                html = self._post(f"/Kontor/bilgi_api.php?GSMNO={gsm}&operatoru=bul&kisitlama=undefined&")
            return html

    def offers(self, gsm: str, operator: str) -> str:
        """رد العروض الخاصة (HTML). operator بصيغة ZNET (TURKCELL/AVEA/VODAFONE)."""
        with self._lock:
            self._ensure_login()
            tok = self._page.evaluate("(g) => znet_token_ver(g, g)", gsm)
            url = (f"/Kontor/bilgi_api_paketsor.php?GSMNO={gsm}"
                   f"&paketsorgula=true&operator={operator}&znet_token={tok}&")
            html = self._post(url)
            if self._logged_out(html):
                self._logged = False
                self._ensure_login()
                tok = self._page.evaluate("(g) => znet_token_ver(g, g)", gsm)
                html = self._post(url)
            return html

    def close(self):
        with self._lock:
            try:
                if self._browser:
                    self._browser.close()
                if self._pw:
                    self._pw.stop()
            finally:
                self._page = self._browser = self._pw = None
                self._logged = False
