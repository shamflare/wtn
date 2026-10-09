import { useEffect, useState } from "react";
import { api } from "../api";
import Icon from "../components/Icon";
import { symbolOf } from "../currency";

interface Row {
  id: number; login_id: string; name: string;
  balance: string; status: string; price_group: number | null;
}
interface Group { id: number; name: string; dealers: number }

/**
 * قائمة دكاكين الوكيل الكبير — نافذته الوحيدة على مَن تحته.
 *
 * لكل دكان: رصيده، مجموعة أسعاره عنده (بها يشتري منه)، شحن/سحب رصيد، وكشف
 * حساب. الشحن **حوالة** من محفظة الوكيل لا هبةً من العدم.
 */
export default function AgentDealers() {
  const [rows, setRows] = useState<Row[]>([]);
  const [groups, setGroups] = useState<Group[]>([]);
  const [cur, setCur] = useState("");
  const [loading, setLoading] = useState(true);
  const [addOpen, setAddOpen] = useState(false);
  const [walletFor, setWalletFor] = useState<{ row: Row; action: "topup" | "deduct" } | null>(null);
  const [stmtFor, setStmtFor] = useState<Row | null>(null);
  const [toast, setToast] = useState<{ ok: boolean; text: string } | null>(null);

  function load() {
    setLoading(true);
    api.get("/agent/dealers/")
      .then((r) => { setRows(r.data.results || []); setCur(r.data.currency || ""); })
      .finally(() => setLoading(false));
    api.get("/agent/price-groups/").then((r) => setGroups(r.data.results || [])).catch(() => setGroups([]));
  }
  useEffect(() => load(), []);

  async function setGroup(dealer: number, price_group: string) {
    try {
      await api.post("/agent/dealer-group/", { dealer, price_group: price_group || null });
      setRows((ds) => ds.map((d) => (d.id === dealer
        ? { ...d, price_group: price_group ? Number(price_group) : null } : d)));
      setToast({ ok: true, text: "حُفظت مجموعة الأسعار — تسري على طلبه التالي" });
    } catch (e: any) {
      setToast({ ok: false, text: e?.response?.data?.detail || "تعذّر الحفظ" });
    }
  }

  const money = (v: string | number) =>
    Number(v).toLocaleString("en-US", { minimumFractionDigits: 2 });
  const balCls = (v: number) => (v < 0 ? "bal-neg" : v > 0 ? "bal-pos" : "bal-zero");
  const sym = symbolOf(cur);

  return (
    <div style={{ maxWidth: 1320, margin: "0 auto", padding: "22px 20px 40px" }}>
      <div className="toolbar">
        <span style={{ color: "var(--muted)", fontSize: 13 }}>
          العدد: <b style={{ color: "var(--text)" }}>{rows.length}</b>
        </span>
        <button className="btn g" style={{ marginInlineStart: "auto" }} onClick={() => setAddOpen(true)}>
          <Icon name="plus" size={15} style={{ marginInlineEnd: 5, verticalAlign: -2 }} />إضافة دكان
        </button>
      </div>

      <div className="card">
        <div className="card-title">
          <Icon name="users" size={16} style={{ color: "var(--primary)" }} /> قائمة الوكلاء
        </div>
        <div className="table-scroll">
          <table className="grid">
            <thead>
              <tr>
                <th>رقم الدخول</th>
                <th className="cell-start">اسم الدكان</th>
                <th>الرصيد</th>
                <th>مجموعة أسعاره</th>
                <th>الحالة</th>
                <th>إجراءات</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan={6} style={{ padding: 30, color: "var(--muted)" }}>جارٍ التحميل...</td></tr>
              ) : rows.length === 0 ? (
                <tr><td colSpan={6} style={{ padding: 30, color: "var(--muted)" }}>
                  لا دكاكين بعد — أضف أوّل دكان.
                </td></tr>
              ) : rows.map((d) => (
                <tr key={d.id}>
                  <td className="num" style={{ color: "var(--faint)", fontSize: 12.5 }}>{d.login_id}</td>
                  <td className="cell-start" style={{ fontWeight: 700 }}>{d.name}</td>
                  <td>
                    <span className={`num ${balCls(Number(d.balance))}`} style={{ fontSize: 14.5 }}>
                      {money(d.balance)}
                    </span>
                    <span style={{ fontSize: 11, color: "var(--faint)", marginInlineStart: 3 }}>{sym}</span>
                  </td>
                  <td>
                    <select value={d.price_group ?? ""} onChange={(e) => setGroup(d.id, e.target.value)}
                      title="بأسعار هذه المجموعة يشتري منّي">
                      <option value="">— بلا مجموعة (بسعر تكلفتي) —</option>
                      {groups.map((g) => <option key={g.id} value={g.id}>{g.name}</option>)}
                    </select>
                  </td>
                  <td>
                    <span title={d.status === "active" ? "نشط" : "معطّل"} style={{
                      display: "inline-block", width: 14, height: 14, borderRadius: "50%",
                      border: "2px solid rgba(0,0,0,.12)",
                      background: d.status === "active" ? "var(--ok)" : "var(--danger)",
                    }} />
                  </td>
                  <td>
                    <div style={{ display: "flex", gap: 4, justifyContent: "center" }}>
                      <IconBtn name="plus" color="var(--ok)" title="شحن رصيد من محفظتي"
                        onClick={() => setWalletFor({ row: d, action: "topup" })} />
                      <IconBtn name="minus" color="var(--danger)" title="سحب رصيد إلى محفظتي"
                        onClick={() => setWalletFor({ row: d, action: "deduct" })} />
                      <IconBtn name="chart" color="var(--primary)" title="كشف حساب"
                        onClick={() => setStmtFor(d)} />
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {addOpen && (
        <AddDealer onClose={() => setAddOpen(false)}
          onDone={() => { setAddOpen(false); load(); setToast({ ok: true, text: "أُضيف الدكان" }); }} />
      )}

      {walletFor && (
        <WalletBox row={walletFor.row} action={walletFor.action} cur={sym}
          onClose={() => setWalletFor(null)}
          onDone={(text) => { setWalletFor(null); load(); setToast({ ok: true, text }); }} />
      )}

      {stmtFor && <Statement row={stmtFor} onClose={() => setStmtFor(null)} />}

      {toast && (
        <div onClick={() => setToast(null)} style={{
          position: "fixed", insetInlineStart: 20, bottom: 20, zIndex: 90, cursor: "pointer",
          maxWidth: 420, padding: "11px 15px", borderRadius: 9, fontSize: 13,
          background: toast.ok ? "var(--ok)" : "var(--danger)", color: "#fff",
          boxShadow: "0 6px 24px rgba(0,0,0,.25)",
        }}>{toast.text}</div>
      )}
    </div>
  );
}

/* ── إضافة دكان ── */
function AddDealer({ onClose, onDone }: { onClose: () => void; onDone: () => void }) {
  const [f, setF] = useState({ name: "", login_id: "", password: "" });
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true); setErr("");
    try {
      await api.post("/agent/dealers/", f);
      onDone();
    } catch (e: any) {
      setErr(e?.response?.data?.detail || "فشل الإنشاء");
    } finally { setBusy(false); }
  }

  return (
    <Modal title="إضافة دكان تحتي" onClose={onClose}>
      {/* حسابٌ جديد لا دخول: بلا هذا يملأ المتصفح الحقول ببيانات دخول الوكيل نفسه */}
      <form onSubmit={submit} autoComplete="off" style={{ display: "grid", gap: 12 }}>
        <Fld label="اسم الدكان">
          <input style={inp} value={f.name} autoFocus name="shop-name" autoComplete="off"
            placeholder="مثال: دكان النور"
            onChange={(e) => setF({ ...f, name: e.target.value })} />
        </Fld>
        <Fld label="رقم الدخول">
          <input style={{ ...inp, direction: "ltr", textAlign: "left" }} value={f.login_id}
            name="new-shop-login" autoComplete="off" inputMode="numeric" placeholder="5XXXXXXXXX"
            onChange={(e) => setF({ ...f, login_id: e.target.value })} />
        </Fld>
        <Fld label="كلمة السر">
          <input style={inp} type="password" value={f.password}
            name="new-shop-password" autoComplete="new-password"
            onChange={(e) => setF({ ...f, password: e.target.value })} />
        </Fld>
        {err && <div style={errBox}>{err}</div>}
        <div style={{ display: "flex", gap: 8 }}>
          <button className="btn g" disabled={busy}>{busy ? "جارٍ..." : "حفظ"}</button>
          <button type="button" className="btn" style={{ background: "#8a999e" }} onClick={onClose}>
            إلغاء
          </button>
        </div>
      </form>
    </Modal>
  );
}

/* ── شحن/سحب: حوالة بين محفظتين ── */
function WalletBox({ row, action, cur, onClose, onDone }: {
  row: Row; action: "topup" | "deduct"; cur: string;
  onClose: () => void; onDone: (text: string) => void;
}) {
  const [amount, setAmount] = useState("");
  const [note, setNote] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const topup = action === "topup";

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true); setErr("");
    try {
      const r = await api.post(`/agent/dealers/${row.id}/wallet/`, { action, amount, note });
      onDone(topup
        ? `شُحن ${row.name} بـ ${amount} ${cur} — رصيدك الآن ${r.data.agent_balance}`
        : `سُحب ${amount} ${cur} من ${row.name} — رصيدك الآن ${r.data.agent_balance}`);
    } catch (e: any) {
      setErr(e?.response?.data?.detail || "تعذّرت العملية");
    } finally { setBusy(false); }
  }

  return (
    <Modal title={`${topup ? "شحن رصيد" : "سحب رصيد"} — ${row.name}`} onClose={onClose}>
      <form onSubmit={submit} style={{ display: "grid", gap: 12 }}>
        <div style={hint}>
          {topup
            ? "المبلغ يُخصم من محفظتك ويُضاف إلى محفظته — حوالة لا هبة."
            : "المبلغ يُخصم من محفظته ويعود إلى محفظتك."}
        </div>
        <Fld label={`المبلغ (${cur})`}>
          <input style={{ ...inp, direction: "ltr", textAlign: "left" }} type="number" step="0.01"
            autoFocus value={amount} onChange={(e) => setAmount(e.target.value)} />
        </Fld>
        <Fld label="ملاحظة (اختيارية)">
          <input style={inp} value={note} onChange={(e) => setNote(e.target.value)} />
        </Fld>
        {err && <div style={errBox}>{err}</div>}
        <div style={{ display: "flex", gap: 8 }}>
          <button className={topup ? "btn g" : "btn r"} disabled={busy || !amount}>
            {busy ? "جارٍ..." : topup ? "شحن" : "سحب"}
          </button>
          <button type="button" className="btn" style={{ background: "#8a999e" }} onClick={onClose}>
            إلغاء
          </button>
        </div>
      </form>
    </Modal>
  );
}

/* ── كشف حساب دكان ── */
function Statement({ row, onClose }: { row: Row; onClose: () => void }) {
  const [data, setData] = useState<any>(null);
  useEffect(() => {
    api.get(`/agent/dealers/${row.id}/statement/`).then((r) => setData(r.data));
  }, [row.id]);

  const money = (v: string) => Number(v).toLocaleString("en-US", { minimumFractionDigits: 2 });

  return (
    <Modal title={`كشف حساب — ${row.name}`} onClose={onClose} wide>
      {!data ? <div style={{ padding: 20 }}>جارٍ التحميل...</div> : (
        <>
          <div style={{ marginBottom: 10, fontSize: 13.5 }}>
            الرصيد الحالي:{" "}
            <b className={`num ${Number(data.dealer.balance) < 0 ? "bal-neg" : "bal-pos"}`}>
              {money(data.dealer.balance)} {symbolOf(data.currency)}
            </b>
          </div>
          <div className="table-scroll" style={{ maxHeight: "55vh" }}>
            <table className="grid">
              <thead>
                <tr><th>التاريخ</th><th>النوع</th><th>المبلغ</th><th>الرصيد بعدها</th><th className="cell-start">ملاحظة</th></tr>
              </thead>
              <tbody>
                {data.results.length === 0 ? (
                  <tr><td colSpan={5} style={{ padding: 22, color: "var(--muted)" }}>لا حركات بعد</td></tr>
                ) : data.results.map((t: any) => (
                  <tr key={t.id}>
                    <td style={{ color: "var(--muted)", fontSize: 12.5 }}>{t.created_at}</td>
                    <td style={{ fontSize: 12.5 }}>{t.type_label}</td>
                    <td className={`num ${Number(t.amount) < 0 ? "bal-neg" : "bal-pos"}`}>{money(t.amount)}</td>
                    <td className="num">{money(t.balance_after)}</td>
                    <td className="cell-start" style={{ fontSize: 12.5, color: "var(--muted)" }}>{t.note}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </Modal>
  );
}

/* ── عناصر مشتركة ── */
function Modal({ title, children, onClose, wide }: {
  title: string; children: React.ReactNode; onClose: () => void; wide?: boolean;
}) {
  return (
    <div style={ovl} onClick={onClose}>
      <div style={{ ...box, width: wide ? 760 : 440 }} onClick={(e) => e.stopPropagation()}>
        <div style={head}>
          <span>{title}</span>
          <button onClick={onClose} style={{ background: "none", border: 0, color: "#fff", cursor: "pointer" }}>✕</button>
        </div>
        <div style={{ padding: 16 }}>{children}</div>
      </div>
    </div>
  );
}
function Fld({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <div style={{ fontSize: 12, color: "var(--muted)", fontWeight: 700, marginBottom: 5 }}>{label}</div>
      {children}
    </div>
  );
}
function IconBtn({ name, color, title, onClick }:
  { name: string; color: string; title: string; onClick: () => void }) {
  return (
    <button onClick={onClick} title={title} style={{
      border: "1px solid var(--border)", background: "var(--surface)", color,
      width: 30, height: 30, borderRadius: 8, display: "flex",
      alignItems: "center", justifyContent: "center", cursor: "pointer",
    }}>
      <Icon name={name} size={15} />
    </button>
  );
}

const ovl: React.CSSProperties = {
  position: "fixed", inset: 0, background: "rgba(0,0,0,.45)", zIndex: 80,
  display: "flex", alignItems: "center", justifyContent: "center",
};
const box: React.CSSProperties = {
  background: "var(--surface)", borderRadius: 10, maxWidth: "95vw",
  maxHeight: "92vh", overflow: "auto", boxShadow: "0 10px 40px rgba(0,0,0,.3)",
};
const head: React.CSSProperties = {
  background: "var(--primary)", color: "#fff", padding: "11px 16px",
  fontSize: 15, fontWeight: 700, display: "flex", justifyContent: "space-between",
  alignItems: "center", position: "sticky", top: 0, zIndex: 1,
};
const inp: React.CSSProperties = { width: "100%", height: 38, borderRadius: 8 };
const hint: React.CSSProperties = {
  background: "var(--surface-2)", border: "1px solid var(--border)", color: "var(--muted)",
  fontSize: 12.5, padding: "9px 12px", borderRadius: 6, lineHeight: 1.8,
};
const errBox: React.CSSProperties = {
  background: "#fdecea", border: "1px solid #f5c6c2", color: "var(--danger)",
  fontSize: 13, padding: "9px 12px", borderRadius: 5,
};
