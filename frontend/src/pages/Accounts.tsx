import { useEffect, useState } from "react";
import { api } from "../api";
import Icon from "../components/Icon";
import { money, symbolOf, useBaseCurrency } from "../currency";

interface Account {
  id: number; method: string; method_label: string; title: string;
  account_no: string; balance: string; status: string; status_label: string;
  notification_enabled: boolean; sort_order: number;
}

const METHOD_ICON: Record<string, string> = {
  sham_cash: "💵", mtn_cash: "📱", syriatel_cash: "📲", bank: "🏦", cash: "💰",
};
const METHODS: [string, string][] = [
  ["sham_cash", "شام كاش"], ["mtn_cash", "MTN كاش"], ["syriatel_cash", "سيرياتيل كاش"],
  ["bank", "تحويل بنكي"], ["cash", "نقدي"],
];
const BLANK = { method: "sham_cash", title: "", account_no: "", balance: "0", status: "active",
  notification_enabled: true, sort_order: 0 };

/**
 * حساباتي — البنوك والمحافظ التي تصل إليها الأموال، وأرصدتها تدخل «الجرد».
 * لصاحب المتجر بعملة الموقع، وللوكيل الكبير (`agent`) حساباته هو بعملته.
 */
export default function Accounts({ agent }: { agent?: boolean } = {}) {
  // الوكيل الكبير يدير طرقه وحساباته وإيداعات دكاكينه هو — الصفحة نفسها بأبوابه
  const P = agent ? "/agent/payments" : "/payments";
  const base = useBaseCurrency();
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [cur, setCur] = useState("");
  const [loading, setLoading] = useState(true);
  const [edit, setEdit] = useState<(typeof BLANK & { id?: number }) | null>(null);
  const [err, setErr] = useState("");

  function load() {
    setLoading(true);
    api.get(`${P}/accounts/`)
      .then((r) => setAccounts(r.data.results || r.data))
      .finally(() => setLoading(false));
  }
  useEffect(() => {
    load();
    // أرصدة حسابات الوكيل الكبير بعملته هو
    if (agent) api.get("/agent/summary/").then((r) => setCur(r.data.currency || "")).catch(() => {});
  }, []);

  async function save() {
    if (!edit) return;
    setErr("");
    try {
      if (edit.id) await api.put(`${P}/accounts/${edit.id}/`, edit);
      else await api.post(`${P}/accounts/`, edit);
      setEdit(null); load();
    } catch (e: any) {
      const d = e?.response?.data;
      setErr(d?.detail || (d && typeof d === "object" ? Object.values(d).flat().join(" · ") : "تعذّر الحفظ"));
    }
  }
  async function remove(a: Account) {
    if (!confirm(`حذف الحساب «${a.title}»؟ طرق الدفع المرتبطة به تبقى بلا حساب.`)) return;
    await api.delete(`${P}/accounts/${a.id}/`).catch(() => {});
    load();
  }
  async function toggle(a: Account, field: "status" | "notification_enabled") {
    const patch = field === "status"
      ? { status: a.status === "active" ? "passive" : "active" }
      : { notification_enabled: !a.notification_enabled };
    await api.patch(`${P}/accounts/${a.id}/`, patch).catch(() => {});
    load();
  }

  const sym = symbolOf(cur || base);
  const total = accounts.reduce((s, a) => s + Number(a.balance), 0);

  return (
    <div style={{ padding: 16 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 14, flexWrap: "wrap" }}>
        <h2 style={{ fontSize: 20, color: "var(--primary-dark)" }}>حساباتي (البنوك والمحافظ)</h2>
        <button className="btn g" onClick={() => { setErr(""); setEdit({ ...BLANK }); }}>
          <Icon name="plus" size={15} style={{ marginInlineEnd: 5 }} />إضافة حساب
        </button>
        <button className="btn" onClick={load}>
          <Icon name="refresh" size={15} style={{ marginInlineEnd: 5 }} />تحديث
        </button>
        <span style={{ fontSize: 12.5, color: "var(--muted)" }}>
          الأرصدة بـ<b>{sym}</b> — تدخل «الجرد» كما هي. اربط كل طريقة دفع بحسابها من «طرق الدفع».
        </span>
      </div>

      <table style={table}>
        <thead>
          <tr>
            {["الحساب", "الوسيلة", "رقم الحساب", `الرصيد (${sym})`, "الحالة", "إشعار", "ترتيب", "إجراء"]
              .map((h) => <th key={h} style={th}>{h}</th>)}
          </tr>
        </thead>
        <tbody>
          {loading ? (
            <tr><td colSpan={8} style={{ ...td, padding: 24 }}>جارٍ التحميل...</td></tr>
          ) : accounts.length === 0 ? (
            <tr><td colSpan={8} style={{ ...td, padding: 24, color: "var(--muted)" }}>
              لا حسابات بعد — أضف حساباً تستلم عليه الأموال.
            </td></tr>
          ) : accounts.map((a, i) => (
            <tr key={a.id} style={{ background: i % 2 ? "var(--row-alt)" : "#fff" }}>
              <td style={{ ...td, textAlign: "right", paddingInlineStart: 12, fontWeight: 600 }}>
                <span style={{ marginInlineEnd: 6 }}>{METHOD_ICON[a.method]}</span>{a.title}
              </td>
              <td style={td}>{a.method_label}</td>
              <td style={{ ...td, color: "var(--muted)", direction: "ltr" }}>{a.account_no || "—"}</td>
              <td style={{ ...td, fontWeight: 600 }}>{money(a.balance)}</td>
              <td style={td}><Dot on={a.status === "active"} onClick={() => toggle(a, "status")} /></td>
              <td style={td}><Dot on={a.notification_enabled} onClick={() => toggle(a, "notification_enabled")} /></td>
              <td style={{ ...td, color: "var(--muted)" }}>{a.sort_order}</td>
              <td style={td}>
                <div style={{ display: "flex", gap: 6, justifyContent: "center" }}>
                  <button style={iconBtn} title="تعديل"
                    onClick={() => { setErr(""); setEdit({ ...a }); }}>
                    <Icon name="edit" size={15} color="var(--primary)" />
                  </button>
                  <button style={iconBtn} title="حذف" onClick={() => remove(a)}>
                    <Icon name="trash" size={15} color="var(--danger)" />
                  </button>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
        <tfoot>
          <tr style={{ background: "#eef4f5", fontWeight: 700 }}>
            <td style={td} colSpan={3}>إجمالي الأرصدة</td>
            <td style={td}>{money(total)} {sym}</td>
            <td style={td} colSpan={4}></td>
          </tr>
        </tfoot>
      </table>

      {edit && (
        <div style={ovl} onClick={() => setEdit(null)}>
          <div style={box} onClick={(e) => e.stopPropagation()}>
            <div style={head}>
              <span>{edit.id ? "تعديل حساب" : "إضافة حساب"}</span>
              <button onClick={() => setEdit(null)} style={{ background: "none", border: 0, color: "#fff", cursor: "pointer" }}>✕</button>
            </div>
            <div style={{ padding: 16, display: "grid", gap: 11 }}>
              <Fld label="اسم الحساب">
                <input style={inp} value={edit.title} autoFocus placeholder="مثال: شام كاش — المكتب"
                  onChange={(e) => setEdit({ ...edit, title: e.target.value })} />
              </Fld>
              <Fld label="الوسيلة">
                <select style={inp} value={edit.method} onChange={(e) => setEdit({ ...edit, method: e.target.value })}>
                  {METHODS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
                </select>
              </Fld>
              <Fld label="رقم الحساب (اختياري)">
                <input style={{ ...inp, direction: "ltr", textAlign: "left" }} value={edit.account_no}
                  onChange={(e) => setEdit({ ...edit, account_no: e.target.value })} />
              </Fld>
              <Fld label={`الرصيد الحالي (${sym})`}>
                <input style={{ ...inp, direction: "ltr", textAlign: "left" }} type="number" step="0.01"
                  value={edit.balance} onChange={(e) => setEdit({ ...edit, balance: e.target.value })} />
              </Fld>
              <Fld label="الترتيب">
                <input style={{ ...inp, direction: "ltr", textAlign: "left" }} type="number"
                  value={edit.sort_order} onChange={(e) => setEdit({ ...edit, sort_order: Number(e.target.value) })} />
              </Fld>
              {err && <div style={errBox}>{err}</div>}
              <div style={{ display: "flex", gap: 8 }}>
                <button className="btn g" onClick={save} disabled={!edit.title.trim()}>حفظ</button>
                <button className="btn" style={{ background: "#8a999e" }} onClick={() => setEdit(null)}>إلغاء</button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function Dot({ on, onClick }: { on: boolean; onClick?: () => void }) {
  return <span onClick={onClick} title={onClick ? "اضغط للتبديل" : undefined}
    style={{ display: "inline-block", width: 11, height: 11, borderRadius: "50%",
      cursor: onClick ? "pointer" : undefined, background: on ? "var(--ok)" : "var(--danger)" }} />;
}
function Fld({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <div style={{ fontSize: 12, color: "var(--muted)", fontWeight: 700, marginBottom: 5 }}>{label}</div>
      {children}
    </div>
  );
}

const table: React.CSSProperties = {
  width: "100%", borderCollapse: "collapse", background: "var(--surface)", fontSize: 13.5,
};
const th: React.CSSProperties = {
  background: "var(--th-bg)", color: "var(--th-ink)", padding: "11px 10px",
  textAlign: "center", fontWeight: 800, fontSize: 12.5, whiteSpace: "nowrap",
  border: "1px solid var(--border)", borderTop: 0,
};
const td: React.CSSProperties = {
  padding: 10, textAlign: "center", whiteSpace: "nowrap", verticalAlign: "middle",
  background: "var(--surface)", border: "1px solid var(--border)",
  borderBottom: "3px solid var(--row-sep)",
};
const iconBtn: React.CSSProperties = {
  border: "1px solid var(--border)", background: "var(--surface)", width: 28, height: 28,
  borderRadius: 7, display: "inline-flex", alignItems: "center", justifyContent: "center", cursor: "pointer",
};
const ovl: React.CSSProperties = {
  position: "fixed", inset: 0, background: "rgba(0,0,0,.45)", zIndex: 80,
  display: "flex", alignItems: "center", justifyContent: "center",
};
const box: React.CSSProperties = {
  background: "var(--surface)", borderRadius: 10, width: 440, maxWidth: "95vw",
  maxHeight: "92vh", overflow: "auto", boxShadow: "0 10px 40px rgba(0,0,0,.3)",
};
const head: React.CSSProperties = {
  background: "var(--primary)", color: "#fff", padding: "11px 16px",
  fontSize: 15, fontWeight: 700, display: "flex", justifyContent: "space-between", alignItems: "center",
};
const inp: React.CSSProperties = { width: "100%", height: 38, borderRadius: 8 };
const errBox: React.CSSProperties = {
  background: "#fdecea", border: "1px solid #f5c6c2", color: "var(--danger)",
  fontSize: 13, padding: "9px 12px", borderRadius: 5,
};
