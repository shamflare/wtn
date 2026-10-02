import { useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { useAuth, roleHome } from "../auth";
import Icon from "../components/Icon";
import PublicShell, { useStorefront } from "../components/PublicShell";

/**
 * الدخول — للجوال أوّلاً، بهويّة المتجر وألوان واجهة وكلائه. يدخل منه الجميع:
 * الوكيل وصاحب المتجر ومالك المنصّة، وكلٌّ يُوجَّه إلى لوحته.
 */
export default function Login() {
  return (
    <PublicShell narrow>
      <LoginForm />
    </PublicShell>
  );
}

function LoginForm() {
  const { login } = useAuth();
  const store = useStorefront();
  const loc = useLocation();
  const fromGame = !!(loc.state as { fromGame?: boolean } | null)?.fromGame;
  const [loginId, setLoginId] = useState("");
  const [password, setPassword] = useState("");
  const [totp, setTotp] = useState("");
  const [needTotp, setNeedTotp] = useState(false);
  const [showPw, setShowPw] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    const res = await login(loginId, password, totp);
    setBusy(false);
    if ("requireTotp" in res) {
      setNeedTotp(true);
      setError("");
    } else if ("ok" in res && res.ok) {
      // تحميلٌ كامل: لوحة الإدارة ثابتة العرض، وتعيد وسم الشاشة وحجم العرض الخاصّين بها
      window.location.assign(roleHome(res.role));
    } else if ("error" in res) {
      setError(res.error);
    }
  }

  return (
    <form onSubmit={submit} className="ag-card ag-pad ag-auth">
      <div className="ag-auth-head">
        <span className="ag-auth-ico"><Icon name="lock" size={22} /></span>
        <h1>تسجيل الدخول</h1>
        <p>{fromGame ? "سجّل دخولك لترى الباقات والأسعار" : `أهلاً بك في ${store?.name || "المتجر"}`}</p>
      </div>

      <label className="ag-label">رقم الدخول</label>
      <input value={loginId} onChange={(e) => setLoginId(e.target.value)} inputMode="numeric"
        dir="ltr" autoComplete="username" placeholder="5550000007" autoFocus required
        style={{ textAlign: "center", fontWeight: 700, letterSpacing: 1 }} />

      <label className="ag-label">كلمة المرور</label>
      <div style={{ position: "relative" }}>
        <input type={showPw ? "text" : "password"} value={password} autoComplete="current-password"
          onChange={(e) => setPassword(e.target.value)} placeholder="••••••••" required
          style={{ paddingInlineEnd: 52 }} />
        {/* `type="button"`: زرٌّ بلا نوعٍ داخل نموذج يُرسله */}
        <button type="button" className="ag-pw-eye" onClick={() => setShowPw((v) => !v)}
          aria-label={showPw ? "إخفاء كلمة المرور" : "إظهار كلمة المرور"} aria-pressed={showPw}>
          <Icon name="eye" size={18} style={showPw ? { opacity: 0.45 } : undefined} />
        </button>
      </div>

      {needTotp && (
        <>
          <label className="ag-label">رمز التحقق (2FA)</label>
          <input value={totp} onChange={(e) => setTotp(e.target.value)} inputMode="numeric"
            dir="ltr" placeholder="123456" autoFocus style={{ textAlign: "center", letterSpacing: 4 }} />
        </>
      )}

      {error && <div className="ag-msg err">{error}</div>}

      <button className="btn g ag-cta" disabled={busy}>
        {busy ? "جارٍ الدخول..." : <><Icon name="check" size={18} />دخول</>}
      </button>

      {store !== null && (
        <div className="ag-auth-alt">
          ليس لديك حساب؟ <Link to="/register">أنشئ حساب وكيل</Link>
        </div>
      )}
      <div className="ag-auth-alt" style={{ marginTop: 6 }}>
        <Link to="/">← العودة إلى المتجر</Link>
      </div>
    </form>
  );
}
