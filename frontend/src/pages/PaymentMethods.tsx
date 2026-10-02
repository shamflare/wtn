import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import Icon from "../components/Icon";
import ImageUpload from "../components/ImageUpload";
import { CURRENCIES, money, symbolOf } from "../currency";

/* ═════════ الأنواع ═════════ */
interface MField {
  id?: number; label: string; kind: string; options: string;
  placeholder: string; required: boolean; sort_order: number;
}
interface Method {
  id: number; name: string; subtitle: string; logo_url: string; color: string;
  currency: string; instructions: string; account_box: string; warning: string;
  min_amount: string; max_amount: string; commission_percent: string;
  account: number | null; account_title: string;
  status: string; status_label: string; sort_order: number;
  fields_list: MField[]; request_count: number;
}
interface Account { id: number; title: string }

const KINDS = [
  { key: "text", label: "نص قصير" },
  { key: "number", label: "رقم" },
  { key: "textarea", label: "نص طويل" },
  { key: "select", label: "قائمة اختيار" },
  { key: "image", label: "صورة (يرفعها الوكيل من جهازه)" },
];

const BLANK = (): Method => ({
  id: 0, name: "", subtitle: "", logo_url: "", color: "#2f6f8f",
  currency: "TRY", instructions: "", account_box: "", warning: "",
  min_amount: "0", max_amount: "0", commission_percent: "0",
  account: null, account_title: "", status: "active", status_label: "",
  sort_order: 0, fields_list: [], request_count: 0,
});

/* ═════════ الصفحة ═════════ */
export default function PaymentMethods() {
  const [methods, setMethods] = useState<Method[]>([]);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState<Method | null>(null);

  function load() {
    setLoading(true);
    api.get("/payments/methods/")
      .then((r) => setMethods(r.data.results || r.data))
      .finally(() => setLoading(false));
  }
  useEffect(() => {
    load();
    api.get("/payments/accounts/").then((r) => setAccounts(r.data.results || r.data)).catch(() => {});
  }, []);

  async function remove(m: Method) {
    if (!confirm(`حذف طريقة الدفع «${m.name}»؟ الطلبات السابقة تبقى محفوظة.`)) return;
    await api.delete(`/payments/methods/${m.id}/`);
    load();
  }

  async function toggle(m: Method) {
    await api.patch(`/payments/methods/${m.id}/`, {
      status: m.status === "active" ? "passive" : "active",
    });
    load();
  }

  return (
    <div style={{ maxWidth: 1340, margin: "0 auto", padding: "18px 16px 40px" }}>
      <div className="card">
        <div className="card-title">
          <Icon name="card" size={16} style={{ color: "var(--primary)" }} /> طرق الدفع — قسم «إضافة رصيد» لدى الوكيل
          <span style={{ marginInlineStart: "auto", display: "flex", gap: 8 }}>
            <Link to="/ayarlar/exchange" className="btn" style={{ height: 32, textDecoration: "none" }}>
              <Icon name="dollar" size={14} style={{ marginInlineEnd: 5, verticalAlign: -2 }} />
              أسعار الصرف
            </Link>
            <button className="btn g" style={{ height: 32 }} onClick={() => setEditing(BLANK())}>
              <Icon name="plus" size={14} style={{ marginInlineEnd: 5, verticalAlign: -2 }} />
              طريقة دفع جديدة
            </button>
          </span>
        </div>
        <div style={hint}>
          كل طريقة تظهر للوكيل بطاقةً في قسم «إضافة رصيد». عند فتحها يرى شرحك وصندوق
          الحساب المنسوخ ثم الحقول التي تبنيها أنت. المبلغ يُحوَّل إلى عملة المحفظة
بـ<b> سعر الصرف المضبوط</b>، وتُخصم منه عمولتك، ولا يُضاف الرصيد إلا
          بقرارك من <b>متابعة الدفع</b>.
        </div>
      </div>

      <div className="card">
        <div className="table-scroll">
          <table className="grid">
            <thead>
              <tr>
                <th>الترتيب</th>
                <th>البطاقة</th>
                <th className="cell-start">الاسم</th>
                <th>العملة</th>
                <th>الحد الأدنى</th>
                <th>الحد الأعلى</th>
                <th>العمولة</th>
                <th>الحقول</th>
                <th>حساب الاستلام</th>
                <th>الطلبات</th>
                <th>الحالة</th>
                <th>إجراء</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan={12} style={{ padding: 26, color: "var(--muted)" }}>جارٍ التحميل...</td></tr>
              ) : methods.length === 0 ? (
                <tr><td colSpan={12} style={{ padding: 26, color: "var(--muted)" }}>
                  لا توجد طرق دفع بعد — أنشئ أولى طرقك ليظهر للوكيل قسم «إضافة رصيد».
                </td></tr>
              ) : methods.map((m) => (
                <tr key={m.id} style={m.status === "passive" ? { opacity: 0.55 } : undefined}>
                  <td className="num">{m.sort_order}</td>
                  <td><MiniCard m={m} /></td>
                  <td className="cell-start">
                    <b>{m.name}</b>
                    {m.subtitle && <div style={{ fontSize: 11.5, color: "var(--muted)" }}>{m.subtitle}</div>}
                  </td>
                  <td>{symbolOf(m.currency)} {m.currency}</td>
                  <td className="num">{Number(m.min_amount) ? money(m.min_amount) : "—"}</td>
                  <td className="num">{Number(m.max_amount) ? money(m.max_amount) : "بلا حد"}</td>
                  <td className="num">{money(m.commission_percent)}%</td>
                  <td className="num">{m.fields_list.length}</td>
                  <td style={{ color: "var(--muted)" }}>{m.account_title || "—"}</td>
                  <td className="num">{m.request_count}</td>
                  <td>
                    <button onClick={() => toggle(m)} style={pill(m.status === "active")}
                      title="تفعيل / تعطيل الظهور للوكيل">
                      {m.status === "active" ? "نشط" : "معطّل"}
                    </button>
                  </td>
                  <td>
                    <div style={{ display: "flex", gap: 4, justifyContent: "center" }}>
                      <MiniBtn name="edit" title="تعديل كل التفاصيل" color="var(--primary)"
                        onClick={() => setEditing({ ...m, fields_list: m.fields_list.map((f) => ({ ...f })) })} />
                      <MiniBtn name="trash" title="حذف" color="var(--danger)" onClick={() => remove(m)} />
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {editing && (
        <MethodEditor method={editing} accounts={accounts}
          onClose={() => setEditing(null)}
          onSaved={() => { setEditing(null); load(); }} />
      )}
    </div>
  );
}

/* ═════════ بطاقة مصغّرة — معاينة ما يراه الوكيل ═════════ */
function MiniCard({ m }: { m: Method }) {
  return (
    <div style={{
      width: 78, height: 46, borderRadius: 7, overflow: "hidden", margin: "0 auto",
      background: m.logo_url ? `#0d1117 center/cover url(${m.logo_url})` : (m.color || "#2f6f8f"),
      display: "flex", alignItems: "flex-end", justifyContent: "center",
      color: "#fff", fontSize: 9, fontWeight: 800, textShadow: "0 1px 3px rgba(0,0,0,.9)",
      border: "1px solid var(--border)",
    }}>
      {!m.logo_url && <span style={{ padding: 3, lineHeight: 1.15 }}>{m.name.slice(0, 18)}</span>}
    </div>
  );
}

/* ═════════ محرّر طريقة الدفع — كل تفصيل ═════════ */
function MethodEditor({
  method, accounts, onClose, onSaved,
}: { method: Method; accounts: Account[]; onClose: () => void; onSaved: () => void }) {
  const [f, setF] = useState<Method>(method);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const isNew = !f.id;
  const set = (k: keyof Method, v: any) => setF((o) => ({ ...o, [k]: v }));

  /* ── الحقول المبنيّة ── */
  const setField = (i: number, k: keyof MField, v: any) =>
    setF((o) => ({ ...o, fields_list: o.fields_list.map((x, j) => (j === i ? { ...x, [k]: v } : x)) }));
  const addField = () =>
    setF((o) => ({
      ...o,
      fields_list: [...o.fields_list, {
        label: "", kind: "text", options: "", placeholder: "",
        required: false, sort_order: o.fields_list.length,
      }],
    }));
  const delField = (i: number) =>
    setF((o) => ({ ...o, fields_list: o.fields_list.filter((_, j) => j !== i) }));
  const moveField = (i: number, d: -1 | 1) =>
    setF((o) => {
      const arr = [...o.fields_list];
      const j = i + d;
      if (j < 0 || j >= arr.length) return o;
      [arr[i], arr[j]] = [arr[j], arr[i]];
      return { ...o, fields_list: arr.map((x, k) => ({ ...x, sort_order: k })) };
    });

  async function save() {
    if (!f.name.trim()) { setErr("اسم طريقة الدفع مطلوب"); return; }
    if (f.fields_list.some((x) => !x.label.trim())) { setErr("كل حقل يحتاج عنواناً"); return; }
    setBusy(true); setErr("");
    const body = {
      name: f.name, subtitle: f.subtitle, logo_url: f.logo_url, color: f.color,
      currency: f.currency, instructions: f.instructions, account_box: f.account_box,
      warning: f.warning, min_amount: f.min_amount || "0", max_amount: f.max_amount || "0",
      commission_percent: f.commission_percent || "0", account: f.account || null,
      status: f.status, sort_order: Number(f.sort_order) || 0,
      fields_list: f.fields_list.map((x, i) => ({ ...x, sort_order: i })),
    };
    try {
      if (isNew) await api.post("/payments/methods/", body);
      else await api.put(`/payments/methods/${f.id}/`, body);
      onSaved();
    } catch (e: any) {
      setErr(e?.response?.data?.detail || "تعذّر الحفظ — راجع الحقول");
    } finally { setBusy(false); }
  }

  return (
    <div style={ovl} onClick={onClose}>
      <div style={{ ...box, width: 980 }} onClick={(e) => e.stopPropagation()}>
        <div style={boxHead}>
          {isNew ? "طريقة دفع جديدة" : `تعديل — ${method.name}`}
          <button type="button" onClick={onClose} style={xBtn}>✕</button>
        </div>

        <div style={{ padding: 16, display: "grid", gap: 16 }}>
          {/* ── الهوية ── */}
          <Section title="هوية البطاقة — ما يراه الوكيل في الشبكة">
            <div style={grid3}>
              <Fld label="الاسم *"><input value={f.name} onChange={(e) => set("name", e.target.value)} style={inp} placeholder="شركة تواصل دولار" /></Fld>
              <Fld label="سطر فرعي"><input value={f.subtitle} onChange={(e) => set("subtitle", e.target.value)} style={inp} placeholder="أوتوماتيكي 24 ساعة" /></Fld>
              <Fld label="ترتيب الظهور"><input type="number" value={f.sort_order} onChange={(e) => set("sort_order", e.target.value)} style={inp} /></Fld>
              <Fld label="صورة البطاقة">
                <ImageUpload value={f.logo_url} onChange={(v) => set("logo_url", v)} size={64} />
              </Fld>
              <Fld label="لون البطاقة (حين لا صورة)">
                <input type="color" value={f.color || "#2f6f8f"} onChange={(e) => set("color", e.target.value)} style={{ ...inp, padding: 2 }} />
              </Fld>
              <Fld label="الحالة">
                <select value={f.status} onChange={(e) => set("status", e.target.value)} style={inp}>
                  <option value="active">نشط — يظهر للوكيل</option>
                  <option value="passive">معطّل — مخفي</option>
                </select>
              </Fld>
            </div>
          </Section>

          {/* ── المال ── */}
          <Section title="المال — العملة والحدود والعمولة">
            <div style={grid3}>
              <Fld label="عملة الإيداع">
                <select value={f.currency} onChange={(e) => set("currency", e.target.value)} style={inp}>
                  {CURRENCIES.map((c) => <option key={c.code} value={c.code}>{c.symbol} {c.label} ({c.code})</option>)}
                </select>
              </Fld>
              <Fld label="الحد الأدنى (0 = بلا حد)"><input type="number" step="0.01" value={f.min_amount} onChange={(e) => set("min_amount", e.target.value)} style={inp} /></Fld>
              <Fld label="الحد الأعلى (0 = بلا حد)"><input type="number" step="0.01" value={f.max_amount} onChange={(e) => set("max_amount", e.target.value)} style={inp} /></Fld>
              <Fld label="العمولة %"><input type="number" step="0.01" value={f.commission_percent} onChange={(e) => set("commission_percent", e.target.value)} style={inp} /></Fld>
              <Fld label="حساب الاستلام (اختياري)">
                <select value={f.account ?? ""} onChange={(e) => set("account", e.target.value ? Number(e.target.value) : null)} style={inp}>
                  <option value="">— بلا ربط —</option>
                  {accounts.map((a) => <option key={a.id} value={a.id}>{a.title}</option>)}
                </select>
              </Fld>
            </div>
            <div style={{ fontSize: 12, color: "var(--muted)", marginTop: 8 }}>
              المبلغ يُحوَّل من {f.currency} إلى عملة الدفتر بـ<b>سعر الصرف</b> المضبوط في
              «أسعار الصرف»، ثم تُخصم العمولة. مثال: 100 {f.currency} وعمولة{" "}
              {money(f.commission_percent || 0)}% → يصل الوكيلَ ما يعادل{" "}
              {money(100 * (100 - Number(f.commission_percent || 0)) / 100)} {f.currency}.
            </div>
          </Section>

          {/* ── الشرح ── */}
          <Section title="الشرح — نصّ صفحة الطريقة">
            <div style={{ display: "grid", gap: 10 }}>
              <Fld label="تفاصيل الإيداع (سطر لكل بند — تُعرض كما هي)">
                <textarea value={f.instructions} onChange={(e) => set("instructions", e.target.value)}
                  rows={6} style={{ ...inp, height: "auto", lineHeight: 1.7 }}
                  placeholder={"📌 تفاصيل الإيداع:\n💰 التحويل إلى: تواصل / اعتماد مباشر\n▼ الحد الأدنى للإيداع: 200$\n💎 العمولة: 0% — بدون رسوم"} />
              </Fld>
              <Fld label="صندوق الحساب (يظهر بخلفية داكنة ويُنسخ بضغطة)">
                <textarea value={f.account_box} onChange={(e) => set("account_box", e.target.value)}
                  rows={2} style={{ ...inp, height: "auto" }} placeholder="( 286 ) رويـال كـاش" />
              </Fld>
              <Fld label="تنبيه فوق النموذج (اختياري)">
                <input value={f.warning} onChange={(e) => set("warning", e.target.value)} style={inp}
                  placeholder="يرجى رفع طلب كتابة اسم المُستلم منك المبلغ في قسم المُلاحظة" />
              </Fld>
            </div>
          </Section>

          {/* ── باني الحقول ── */}
          <Section title={`حقول الطلب — ${f.fields_list.length} حقلاً`}>
            <div style={{ fontSize: 12, color: "var(--muted)", marginBottom: 8 }}>
              كل حقل تبنيه هنا يظهر للوكيل في نموذج هذه الطريقة وحدها، وتصلك قيمته مع الطلب.
              حقل المبلغ موجود دائماً ولا يُبنى.
            </div>
            {f.fields_list.map((x, i) => (
              <div key={i} style={fieldRow}>
                <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                  <button type="button" onClick={() => moveField(i, -1)} style={arrowBtn} title="أعلى">▲</button>
                  <button type="button" onClick={() => moveField(i, 1)} style={arrowBtn} title="أسفل">▼</button>
                </div>
                <input value={x.label} onChange={(e) => setField(i, "label", e.target.value)}
                  placeholder="عنوان الحقل — مثل: اسم المُستلم منك المبلغ" style={{ ...inp, flex: "2 1 220px" }} />
                <select value={x.kind} onChange={(e) => setField(i, "kind", e.target.value)} style={{ ...inp, width: 130 }}>
                  {KINDS.map((k) => <option key={k.key} value={k.key}>{k.label}</option>)}
                </select>
                {x.kind === "select" ? (
                  <input value={x.options} onChange={(e) => setField(i, "options", e.target.value)}
                    placeholder="الخيارات مفصولة بـ |" style={{ ...inp, flex: "1 1 160px" }} />
                ) : (
                  <input value={x.placeholder} onChange={(e) => setField(i, "placeholder", e.target.value)}
                    placeholder="نص إرشادي داخل الحقل" style={{ ...inp, flex: "1 1 160px" }} />
                )}
                <label style={chk}>
                  <input type="checkbox" checked={x.required} onChange={(e) => setField(i, "required", e.target.checked)} />
                  إلزامي
                </label>
                <MiniBtn name="trash" title="حذف الحقل" color="var(--danger)" onClick={() => delField(i)} />
              </div>
            ))}
            <button type="button" className="btn" style={{ height: 32, marginTop: 8 }} onClick={addField}>
              <Icon name="plus" size={13} style={{ marginInlineEnd: 5, verticalAlign: -2 }} />إضافة حقل
            </button>
          </Section>

          {err && <div style={errBox}>{err}</div>}
          <div style={{ display: "flex", gap: 8 }}>
            <button className="btn g" onClick={save} disabled={busy}>
              {busy ? "جارٍ الحفظ..." : "حفظ طريقة الدفع"}
            </button>
            <button className="btn" style={{ background: "#8a999e" }} onClick={onClose}>إلغاء</button>
          </div>
        </div>
      </div>
    </div>
  );
}

/* ═════════ عناصر مشتركة ═════════ */
function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div style={{ border: "1px solid var(--border)", borderRadius: 8, padding: 12 }}>
      <div style={{ fontSize: 12.5, fontWeight: 800, color: "var(--primary-dark)", marginBottom: 10 }}>{title}</div>
      {children}
    </div>
  );
}
function Fld({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <div style={{ fontSize: 12, color: "var(--muted)", fontWeight: 700, marginBottom: 4 }}>{label}</div>
      {children}
    </div>
  );
}
function MiniBtn({ name, title, color = "var(--muted)", onClick }:
  { name: string; title: string; color?: string; onClick?: () => void }) {
  return (
    <button type="button" onClick={onClick} title={title} style={{
      border: "1px solid var(--border)", background: "var(--surface)", color,
      width: 28, height: 28, borderRadius: 7, display: "inline-flex",
      alignItems: "center", justifyContent: "center", cursor: "pointer", flex: "0 0 auto",
    }}>
      <Icon name={name} size={14} />
    </button>
  );
}

const inp: React.CSSProperties = { width: "100%", height: 36, borderRadius: 8 };
const grid3: React.CSSProperties = { display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: "10px 14px" };
const hint: React.CSSProperties = {
  padding: "10px 16px", fontSize: 12.5, color: "var(--muted)", lineHeight: 1.8,
};
const fieldRow: React.CSSProperties = {
  display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap",
  padding: 8, marginBottom: 6, borderRadius: 8, background: "var(--surface-2)",
};
const arrowBtn: React.CSSProperties = {
  border: "1px solid var(--border)", background: "var(--surface)", color: "var(--muted)",
  width: 22, height: 15, borderRadius: 4, cursor: "pointer", fontSize: 8, lineHeight: 1, padding: 0,
};
const chk: React.CSSProperties = {
  display: "inline-flex", alignItems: "center", gap: 5, fontSize: 12.5, whiteSpace: "nowrap",
};
const pill = (on: boolean): React.CSSProperties => ({
  border: 0, borderRadius: 20, padding: "3px 12px", fontSize: 11.5, fontWeight: 800, cursor: "pointer",
  background: on ? "rgba(53,194,69,.15)" : "rgba(125,143,148,.18)",
  color: on ? "var(--ok)" : "var(--muted)",
});
const errBox: React.CSSProperties = {
  fontSize: 12.5, padding: "8px 12px", borderRadius: 6,
  background: "rgba(221,68,68,.10)", color: "var(--danger)",
};
const ovl: React.CSSProperties = {
  position: "fixed", inset: 0, background: "rgba(0,0,0,.45)", zIndex: 70,
  display: "flex", alignItems: "center", justifyContent: "center",
};
const box: React.CSSProperties = {
  background: "var(--surface)", borderRadius: 8, maxWidth: "95vw",
  maxHeight: "92vh", overflow: "auto", boxShadow: "0 10px 40px rgba(0,0,0,.3)",
};
const boxHead: React.CSSProperties = {
  background: "var(--primary)", color: "#fff", padding: "10px 16px",
  fontSize: 15, fontWeight: 700, display: "flex", justifyContent: "space-between",
  position: "sticky", top: 0, zIndex: 1,
};
const xBtn: React.CSSProperties = {
  background: "none", border: 0, color: "#fff", cursor: "pointer", fontSize: 15,
};
