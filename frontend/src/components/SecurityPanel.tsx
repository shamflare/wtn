import { useEffect, useState } from "react";
import { api } from "../api";
import { useAuth } from "../auth";

/**
 * أمان الحساب — لكل الأدوار:
 * - التحقق بخطوتين (2FA) بتطبيق المصادقة: اختياري، وإلزامي لمالك المنصّة.
 * - الخروج من كل الأجهزة: يُسقط كل جلسة مفتوحة (هاتف قديم، جهاز ضائع…).
 */
export default function SecurityPanel() {
  const { logout } = useAuth();
  const [state, setState] = useState<{ enabled: boolean; required: boolean } | null>(null);
  const [setup, setSetup] = useState<{ qr: string; secret: string } | null>(null);
  const [code, setCode] = useState("");
  const [pw, setPw] = useState("");
  const [off, setOff] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

  const load = () => api.get("/auth/2fa/").then((r) => setState(r.data)).catch(() => {});
  useEffect(() => { load(); }, []);

  async function run(fn: () => Promise<any>, ok: string) {
    setBusy(true); setMsg(null);
    try { await fn(); setMsg({ ok: true, text: ok }); setCode(""); setPw(""); await load(); return true; }
    catch (e: any) { setMsg({ ok: false, text: e?.response?.data?.detail || "تعذّرت العملية" }); return false; }
    finally { setBusy(false); }
  }

  const start = () => run(async () => setSetup((await api.post("/auth/2fa/", {})).data), "امسح الرمز ثم اكتب الرقم الظاهر");
  const confirm = async () => {
    if (await run(() => api.post("/auth/2fa/", { code }), "فُعّل التحقق بخطوتين ✓")) setSetup(null);
  };
  const disable = async () => {
    if (await run(() => api.delete("/auth/2fa/", { data: { password: pw, code } }), "أُوقف التحقق بخطوتين")) setOff(false);
  };
  async function logoutAll() {
    if (!window.confirm("الخروج من كل الأجهزة؟ ستحتاج لتسجيل الدخول من جديد هنا وفي كل مكان.")) return;
    await api.post("/auth/logout-all/").catch(() => {});
    logout();
    window.location.assign("/login");
  }

  if (!state) return <div style={{ padding: 16, color: "var(--muted)" }}>جارٍ التحميل...</div>;

  return (
    <div style={{ display: "grid", gap: 14, maxWidth: 560 }}>
      <section style={box}>
        <h3 style={h3}>التحقق بخطوتين (2FA)</h3>
        <p style={p}>
          مع كلمة السر يُطلب رمزٌ من 6 أرقام يتغيّر كل 30 ثانية في تطبيق المصادقة على هاتفك
          (Google Authenticator أو Microsoft Authenticator). فلا يكفي من يعرف كلمة سرّك أن يدخل.
        </p>
        <div style={{ fontWeight: 800, color: state.enabled ? "var(--ok)" : "var(--muted)", marginBottom: 10 }}>
          {state.enabled ? "✓ مفعّل" : "غير مفعّل"}{state.required && " — إلزاميٌّ لحسابك"}
        </div>

        {!state.enabled && !setup && <button className="btn g" disabled={busy} onClick={start}>تفعيل التحقق بخطوتين</button>}

        {setup && (
          <div style={{ display: "grid", gap: 10, justifyItems: "start" }}>
            <ol style={{ ...p, margin: 0, paddingInlineStart: 18 }}>
              <li>افتح تطبيق المصادقة واختر «إضافة حساب» ثم «مسح رمز QR».</li>
              <li>اكتب الرقم الظاهر في التطبيق واضغط «تأكيد».</li>
            </ol>
            <div style={{ background: "#fff", padding: 8, borderRadius: 10 }}>
              <img src={setup.qr} alt="رمز QR" style={{ width: 180, height: 180, display: "block" }} />
            </div>
            <div style={{ fontSize: 12, color: "var(--muted)" }}>
              أو أدخل المفتاح يدوياً: <code dir="ltr" style={{ wordBreak: "break-all" }}>{setup.secret}</code>
            </div>
            <div style={{ display: "flex", gap: 8 }}>
              <input value={code} onChange={(e) => setCode(e.target.value)} inputMode="numeric" dir="ltr"
                placeholder="123456" maxLength={6} style={{ width: 130, textAlign: "center", letterSpacing: 3 }} />
              <button className="btn g" disabled={busy || code.length < 6} onClick={confirm}>تأكيد</button>
            </div>
          </div>
        )}

        {state.enabled && !state.required && !off && (
          <button className="btn r" onClick={() => setOff(true)}>إيقاف التحقق بخطوتين</button>
        )}
        {off && (
          <div style={{ display: "grid", gap: 8, maxWidth: 320 }}>
            <input type="password" autoComplete="current-password" value={pw} onChange={(e) => setPw(e.target.value)}
              placeholder="كلمة السر الحالية" />
            <input value={code} onChange={(e) => setCode(e.target.value)} inputMode="numeric" dir="ltr"
              placeholder="رمز التطبيق" maxLength={6} style={{ textAlign: "center", letterSpacing: 3 }} />
            <div style={{ display: "flex", gap: 8 }}>
              <button className="btn r" disabled={busy || !pw || code.length < 6} onClick={disable}>إيقاف</button>
              <button className="btn" style={{ background: "#8a999e" }} onClick={() => setOff(false)}>إلغاء</button>
            </div>
          </div>
        )}
      </section>

      <section style={box}>
        <h3 style={h3}>الجلسات المفتوحة</h3>
        <p style={p}>
          إن شككتَ أن أحداً دخل حسابك، أو فقدتَ جهازاً كان مفتوحاً عليه: اخرج من كل الأجهزة.
          وتغيير كلمة السر يفعل ذلك تلقائياً.
        </p>
        <button className="btn r" onClick={logoutAll}>الخروج من كل الأجهزة</button>
      </section>

      {msg && <div style={{ fontSize: 13, color: msg.ok ? "var(--ok)" : "var(--danger)" }}>{msg.text}</div>}
    </div>
  );
}

const box: React.CSSProperties = {
  border: "1px solid var(--border, rgba(127,127,127,.25))", borderRadius: 12, padding: 16,
  background: "var(--surface)",
};
const h3: React.CSSProperties = { margin: "0 0 6px", fontSize: 16 };
const p: React.CSSProperties = { fontSize: 13, color: "var(--muted)", lineHeight: 1.8, margin: "0 0 10px" };
