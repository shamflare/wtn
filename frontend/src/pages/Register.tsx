import { useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import Icon from "../components/Icon";
import PublicShell, { useStorefront } from "../components/PublicShell";
import { labelOf, symbolOf } from "../currency";

/**
 * طلب فتح حساب وكيل — يُراجعه صاحب المتجر قبل أن يدخل صاحبه.
 *
 * الحقول كلّها إجبارية، ومنها صورة الهوية: صاحب المتجر يُقرض وكلاءه رصيداً،
 * فلا يُفتح حسابٌ لمجهول. والصور تُصغَّر هنا قبل الإرسال (أطول ضلع 1600px).
 */
export default function Register() {
  return (
    <PublicShell narrow>
      <RegisterForm />
    </PublicShell>
  );
}

const COUNTRIES: { code: string; label: string }[] = [
  { code: "SY", label: "سوريا 🇸🇾" }, { code: "TR", label: "تركيا 🇹🇷" },
  { code: "IQ", label: "العراق 🇮🇶" }, { code: "SA", label: "السعودية 🇸🇦" },
  { code: "LB", label: "لبنان 🇱🇧" }, { code: "JO", label: "الأردن 🇯🇴" },
  { code: "EG", label: "مصر 🇪🇬" }, { code: "AE", label: "الإمارات 🇦🇪" },
  { code: "KW", label: "الكويت 🇰🇼" }, { code: "QA", label: "قطر 🇶🇦" },
  { code: "PS", label: "فلسطين 🇵🇸" }, { code: "YE", label: "اليمن 🇾🇪" },
  { code: "LY", label: "ليبيا 🇱🇾" }, { code: "DZ", label: "الجزائر 🇩🇿" },
  { code: "MA", label: "المغرب 🇲🇦" }, { code: "TN", label: "تونس 🇹🇳" },
  { code: "SD", label: "السودان 🇸🇩" }, { code: "DE", label: "ألمانيا 🇩🇪" },
  { code: "OTHER", label: "دولة أخرى" },
];

/** صورةٌ من الجهاز ⇐ data URL مصغّرة (JPEG) — تبقى الهوية مقروءة ويخفّ الحجم */
async function shrinkToDataUrl(file: File, maxSide = 1600): Promise<string> {
  const url = URL.createObjectURL(file);
  try {
    const img = await new Promise<HTMLImageElement>((ok, bad) => {
      const i = new Image(); i.onload = () => ok(i); i.onerror = () => bad(new Error("bad")); i.src = url;
    });
    const k = Math.min(1, maxSide / Math.max(img.naturalWidth, img.naturalHeight));
    const c = document.createElement("canvas");
    c.width = Math.round(img.naturalWidth * k); c.height = Math.round(img.naturalHeight * k);
    c.getContext("2d")!.drawImage(img, 0, 0, c.width, c.height);
    return c.toDataURL("image/jpeg", 0.85);
  } finally { URL.revokeObjectURL(url); }
}

function PhotoField({ label, hint, value, onChange, required, error }: {
  label: string; hint: string; value: string; onChange: (v: string) => void; required?: boolean; error?: string;
}) {
  const input = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  async function pick(f?: File) {
    if (!f || !f.type.startsWith("image/")) return;
    setBusy(true);
    try { onChange(await shrinkToDataUrl(f)); } finally { setBusy(false); }
  }
  return (
    <>
      <label className="ag-label">{label}{required && " *"}</label>
      <button type="button" className={`ag-photo${value ? " has" : ""}${error ? " bad" : ""}`}
        onClick={() => input.current?.click()}>
        {value ? <img src={value} alt="" /> : (
          <span>
            <Icon name="download" size={24} style={{ transform: "rotate(180deg)" }} />
            <b>{busy ? "جارٍ التجهيز..." : "اضغط لاختيار صورة"}</b>
            <small>{hint}</small>
          </span>
        )}
      </button>
      {value && (
        <button type="button" className="ag-photo-redo" onClick={() => input.current?.click()}>تغيير الصورة</button>
      )}
      {error && <div className="ag-field-err">{error}</div>}
      <input ref={input} type="file" accept="image/*" hidden onChange={(e) => pick(e.target.files?.[0])} />
    </>
  );
}

function RegisterForm() {
  const store = useStorefront();
  const [f, setF] = useState({
    name: "", login_id: "", password: "", password2: "", country: "", province: "",
    whatsapp: "", display_currency: "", id_image: "", shop_image: "",
  });
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState<string | null>(null);
  const set = (k: keyof typeof f, v: string) => { setF((s) => ({ ...s, [k]: v })); setErrors((e) => ({ ...e, [k]: "" })); };

  /** فحصٌ هنا قبل الإرسال — والخادم يعيده كلّه، فلا يُعتمد على هذا وحده */
  function check(): Record<string, string> {
    const e: Record<string, string> = {};
    if (f.name.trim().length < 3) e.name = "اكتب الاسم الكامل";
    if (!/^\d{6,15}$/.test(f.login_id.trim())) e.login_id = "أرقامٌ فقط (من 6 إلى 15) — رقم جوالك مثلاً";
    if (f.password.length < 6) e.password = "6 أحرف على الأقل";
    if (f.password2 !== f.password) e.password2 = "كلمتا السر غير متطابقتين";
    if (!f.country) e.country = "اختر الدولة";
    if (f.province.trim().length < 2) e.province = "اكتب المدينة / المحافظة";
    if (!f.display_currency) e.display_currency = "اختر العملة التي تتعامل بها";
    if (!/^\+?\d[\d\s-]{7,}$/.test(f.whatsapp.trim())) e.whatsapp = "اكتب الرقم مع رمز الدولة، مثل ‎+905551234567";
    if (!f.id_image) e.id_image = "صورة الهوية مطلوبة";
    return e;
  }

  async function submit(ev: React.FormEvent) {
    ev.preventDefault();
    setMsg("");
    const e = check();
    setErrors(e);
    if (Object.values(e).some(Boolean)) { setMsg("أكمل الحقول المعلَّمة بالأحمر"); return; }
    setBusy(true);
    try {
      const { password2: _, ...body } = f;
      const r = await api.post("/storefront/register/", body);
      setDone(r.data.login_id);
      window.scrollTo(0, 0);
    } catch (err: any) {
      const d = err?.response?.data;
      setErrors(d?.errors || {});
      setMsg(d?.detail || "تعذّر إرسال الطلب");
    } finally { setBusy(false); }
  }

  if (done) {
    return (
      <div className="ag-card ag-pad ag-auth" style={{ textAlign: "center" }}>
        <span className="ag-auth-ico ok"><Icon name="check" size={26} /></span>
        <h1 style={{ fontSize: 20, margin: "12px 0 6px" }}>وصل طلبك ✓</h1>
        <p style={{ color: "var(--muted)", lineHeight: 1.9 }}>
          تراجع إدارة {store?.name || "المتجر"} بياناتك الآن. تستطيع الدخول برقم
          <b dir="ltr" style={{ color: "var(--text)" }}> {done} </b>
          فور قبول الطلب — وسيصلك التواصل على واتساب.
        </p>
        <Link to="/" className="btn ag-cta" style={{ textDecoration: "none" }}>العودة إلى المتجر</Link>
      </div>
    );
  }

  const field = (k: keyof typeof f) => (errors[k] ? { borderColor: "var(--danger)" } : undefined);
  const err = (k: string) => errors[k] && <div className="ag-field-err">{errors[k]}</div>;

  return (
    <form onSubmit={submit} className="ag-card ag-pad ag-auth" noValidate>
      <div className="ag-auth-head">
        <span className="ag-auth-ico"><Icon name="user" size={22} /></span>
        <h1>إنشاء حساب وكيل</h1>
        <p>تُراجع الإدارة طلبك ثم تُفعّل حسابك. الحقول كلّها إجبارية.</p>
      </div>

      <label className="ag-label">الاسم الكامل *</label>
      <input value={f.name} onChange={(e) => set("name", e.target.value)} style={field("name")}
        placeholder="الاسم كما في الهوية" autoComplete="name" />
      {err("name")}

      <label className="ag-label">رقم الدخول *</label>
      <input value={f.login_id} onChange={(e) => set("login_id", e.target.value.replace(/[^\d]/g, ""))}
        style={{ ...field("login_id"), textAlign: "center", letterSpacing: 1 }} inputMode="numeric" dir="ltr"
        placeholder="رقم جوالك مثلاً: 5551234567" autoComplete="username" />
      {err("login_id")}

      <div className="ag-row2">
        <div>
          <label className="ag-label">كلمة السر *</label>
          <input type="password" value={f.password} onChange={(e) => set("password", e.target.value)}
            style={field("password")} autoComplete="new-password" placeholder="6 أحرف على الأقل" />
          {err("password")}
        </div>
        <div>
          <label className="ag-label">تأكيد كلمة السر *</label>
          <input type="password" value={f.password2} onChange={(e) => set("password2", e.target.value)}
            style={field("password2")} autoComplete="new-password" />
          {err("password2")}
        </div>
      </div>

      <label className="ag-label">رقم واتساب *</label>
      {/* التوضيح داخل الحقل نفسه — وسمٌ عند حافته، والرقم في اتجاهه */}
      <div className="ag-adorn">
        <span className="ag-adorn-tag">مع رمز الدولة</span>
        <input value={f.whatsapp} onChange={(e) => set("whatsapp", e.target.value)} dir="ltr" inputMode="tel"
          style={{ ...field("whatsapp"), letterSpacing: 0.5 }}
          placeholder="+90 555 123 4567" autoComplete="tel" />
      </div>
      <div className="ag-field-hint">اكتب رمز الدولة قبل الرقم: <b dir="ltr">+90</b> لتركيا، <b dir="ltr">+963</b> لسوريا، <b dir="ltr">+964</b> للعراق</div>
      {err("whatsapp")}

      <div className="ag-row2">
        <div>
          <label className="ag-label">الدولة *</label>
          <select value={f.country} onChange={(e) => set("country", e.target.value)} style={field("country")}>
            <option value="">— اختر —</option>
            {COUNTRIES.map((c) => <option key={c.code} value={c.code}>{c.label}</option>)}
          </select>
          {err("country")}
        </div>
        <div>
          <label className="ag-label">المدينة / المحافظة *</label>
          <input value={f.province} onChange={(e) => set("province", e.target.value)} style={field("province")}
            placeholder="مثلاً: إسطنبول" />
          {err("province")}
        </div>
      </div>

      <label className="ag-label">العملة التي تتعامل بها *</label>
      <div className="ag-cur-pick">
        {(store?.currencies || []).map((c) => (
          <button type="button" key={c} className={`ag-chip${f.display_currency === c ? " on" : ""}`}
            onClick={() => set("display_currency", c)}>
            <b style={{ fontSize: 15 }}>{symbolOf(c)}</b> {labelOf(c)}
          </button>
        ))}
      </div>
      <div className="ag-field-hint">بها ترى رصيدك وأسعار الباقات، وبها تشحن محفظتك.</div>
      {err("display_currency")}

      <PhotoField label="صورة الهوية" hint="الوجه الأمامي واضحاً — تراها الإدارة وحدها" required
        value={f.id_image} onChange={(v) => set("id_image", v)} error={errors.id_image} />
      <PhotoField label="صورة المحل (اختيارية)" hint="واجهة المحل أو مكان العمل"
        value={f.shop_image} onChange={(v) => set("shop_image", v)} error={errors.shop_image} />

      {msg && <div className="ag-msg err">{msg}</div>}
      <button className="btn g ag-cta" disabled={busy}>
        {busy ? "جارٍ الإرسال..." : <><Icon name="check" size={18} />إرسال الطلب</>}
      </button>
      <div className="ag-auth-alt">لديك حساب؟ <Link to="/login">تسجيل الدخول</Link></div>
    </form>
  );
}
