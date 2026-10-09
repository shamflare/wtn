import { Fragment, useEffect, useState } from "react";
import { api } from "../api";
import Icon from "../components/Icon";
import { money, symbolOf, useBaseCurrency } from "../currency";

interface Req {
  id: number; dealer: number; dealer_name: string; dealer_login: string;
  account_title: string; method: number | null; method_name: string;
  amount: string; currency: string; rate: string; commission_percent: string;
  credit_amount: string; values: Record<string, string>;
  note: string; admin_note: string; status: string; status_label: string;
  balance_before: string | null; balance_after: string | null;
  created_at: string; decided_at: string | null;
}
interface Opt { id: number; name: string }

const DOT: Record<string, string> = { pending: "wait", approved: "ok", rejected: "err" };
const ROW_TONE: Record<string, string> = { pending: "row-wait" };
const EMPTY = { dealer: "", method: "", q: "", min: "", max: "", date_from: "", date_to: "" };

export default function PaymentTracking({ agent }: { agent?: boolean } = {}) {
  // الوكيل الكبير يدير طرقه وحساباته وإيداعات دكاكينه هو — الصفحة نفسها بأبوابه
  const P = agent ? "/agent/payments" : "/payments";
  const base = useBaseCurrency();
  const [reqs, setReqs] = useState<Req[]>([]);
  const [status, setStatus] = useState("all");
  const [f, setF] = useState({ ...EMPTY });
  const [loading, setLoading] = useState(true);
  const [showFilters, setShowFilters] = useState(false);
  const [expanded, setExpanded] = useState<number | null>(null);
  const [dealers, setDealers] = useState<Opt[]>([]);
  const [methods, setMethods] = useState<Opt[]>([]);
  const [picked, setPicked] = useState<number[]>([]);
  const [bulkNote, setBulkNote] = useState("");
  const [bulkBusy, setBulkBusy] = useState("");
  const [bulkMsg, setBulkMsg] = useState<{ ok: boolean; text: string } | null>(null);

  function load(st = status, filters = f) {
    setLoading(true);
    const params: any = { status: st };
    Object.entries(filters).forEach(([k, v]) => { if (v) params[k] = v; });
    api.get(`${P}/notifications/`, { params })
      .then((r) => setReqs(r.data.results))
      .finally(() => setLoading(false));
  }
  useEffect(() => {
    load();
    api.get(agent ? "/agent/dealers/" : "/dealers/").then((r) => setDealers(r.data.results)).catch(() => {});
    api.get(`${P}/methods/`)
      .then((r) => setMethods((r.data.results || r.data).map((m: any) => ({ id: m.id, name: m.name }))))
      .catch(() => {});
  }, []);

  function setStatusAndLoad(st: string) {
    setStatus(st); setPicked([]); setBulkMsg(null); load(st);
  }
  function clearFilters() {
    setF({ ...EMPTY }); setPicked([]); load(status, { ...EMPTY });
  }

  /**
   * وضع الإجراءات تابع لفلتر الحالة — كجدول طلبات الألعاب:
   * • مقبول  → عكس قرار: **إبطال** فقط (يُسحب المبلغ من المحفظة).
   * • مرفوض  → عكس قرار: **قبول** فقط (يُضاف المبلغ).
   * • غير ذلك → طلب لم يُحسم: قبول أو رفض.
   */
  const mode: "revoke" | "restore" | "open" =
    status === "approved" ? "revoke" : status === "rejected" ? "restore" : "open";

  const selectable = (r: Req) =>
    mode === "revoke" ? r.status === "approved"
      : mode === "restore" ? r.status === "rejected"
        : r.status === "pending";

  const toggleOne = (id: number) =>
    setPicked((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]));
  const pickable = reqs.filter(selectable);
  const allPicked = pickable.length > 0 && picked.length === pickable.length;
  const toggleAll = () => setPicked(allPicked ? [] : pickable.map((r) => r.id));

  async function bulk(action: "approve" | "reject") {
    if (picked.length === 0) return;
    setBulkBusy(action); setBulkMsg(null);
    try {
      const r = await api.post(`${P}/notifications/bulk-action/`, {
        requests: picked, action, note: bulkNote.trim(),
      });
      const failed = (r.data.results || []).filter((x: any) => !x.ok);
      setBulkMsg({
        ok: failed.length === 0,
        text: `تمّ على ${r.data.done} طلباً` +
          (failed.length
            ? ` · تعذّر على ${failed.length}: ` +
              failed.slice(0, 3).map((x: any) => `#${x.request} (${x.detail})`).join(" · ")
            : ""),
      });
      setPicked([]); setBulkNote("");
      load();
    } catch (e: any) {
      setBulkMsg({ ok: false, text: e?.response?.data?.detail || "فشل تنفيذ الإجراء" });
    } finally { setBulkBusy(""); }
  }

  const set = (k: string, v: string) => setF((o) => ({ ...o, [k]: v }));
  const activeFilters = Object.values(f).filter(Boolean).length;

  return (
    <div style={{ maxWidth: 1340, margin: "0 auto", padding: "18px 16px 40px" }}>
      {/* ===== الفلاتر ===== */}
      <div className="card">
        <div className="card-title">
          <Icon name="wallet" size={16} style={{ color: "var(--primary)" }} /> متابعة الدفع — طلبات إضافة الرصيد
          <span style={{ marginInlineStart: "auto", display: "inline-flex", gap: 6, alignItems: "center" }}>
            {([["all", "#7d8f94", "الكل"], ["pending", "#e8b013", "قيد المراجعة"],
               ["approved", "#35c245", "مقبول"], ["rejected", "#dd4444", "مرفوض"]] as [string, string, string][]).map(([k, c, t]) => (
              <button key={k} title={t} onClick={() => setStatusAndLoad(k)}
                style={{ ...qdot, background: c, outline: status === k ? "2px solid var(--primary)" : "none" }} />
            ))}
            <button onClick={() => setShowFilters((v) => !v)} style={filterToggle}>
              <Icon name="filter" size={13} style={{ marginInlineEnd: 5, verticalAlign: -2 }} />
              فلتر
              {activeFilters > 0 && <span style={fcount}>{activeFilters}</span>}
              <span style={{ marginInlineStart: 5, fontSize: 10 }}>{showFilters ? "▲" : "▼"}</span>
            </button>
          </span>
        </div>
        {showFilters && (
          <div style={fgrid}>
            <Field label="الوكيل">
              <select value={f.dealer} onChange={(e) => set("dealer", e.target.value)} style={inp}>
                <option value="">اختر من فضلك</option>
                {dealers.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
              </select>
            </Field>
            <Field label="طريقة الدفع">
              <select value={f.method} onChange={(e) => set("method", e.target.value)} style={inp}>
                <option value="">اختر من فضلك</option>
                {methods.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
              </select>
            </Field>
            <Field label="بحث باسم الوكيل"><input value={f.q} onChange={(e) => set("q", e.target.value)} style={inp} /></Field>
            <Field label="أقل مبلغ مُضاف"><input type="number" value={f.min} onChange={(e) => set("min", e.target.value)} style={inp} /></Field>
            <Field label="أعلى مبلغ مُضاف"><input type="number" value={f.max} onChange={(e) => set("max", e.target.value)} style={inp} /></Field>
            <Field label="تاريخ الطلب (من / إلى)">
              <div style={{ display: "flex", gap: 6 }}>
                <input type="date" value={f.date_from} onChange={(e) => set("date_from", e.target.value)} style={{ ...inp, flex: 1 }} />
                <input type="date" value={f.date_to} onChange={(e) => set("date_to", e.target.value)} style={{ ...inp, flex: 1 }} />
              </div>
            </Field>
            <div style={{ display: "flex", gap: 8, alignItems: "flex-end", gridColumn: "span 2" }}>
              <button className="btn g" style={{ height: 36, flex: 1 }} onClick={() => load()}>
                <Icon name="filter" size={14} style={{ marginInlineEnd: 5, verticalAlign: -2 }} />فلترة
              </button>
              <button className="btn r" style={{ height: 36, flex: 1 }} onClick={clearFilters}>إزالة الفلتر</button>
            </div>
          </div>
        )}
      </div>

      {/* ===== شريط الإجراءات على المحدَّد ===== */}
      {picked.length > 0 && (
        <div className="card" style={bulkBar}>
          <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
            <b style={{ fontSize: 13.5, whiteSpace: "nowrap" }}>
              محدَّد: <span style={{ color: "var(--primary)" }}>{picked.length}</span>
            </b>
            <input value={bulkNote} onChange={(e) => setBulkNote(e.target.value)}
              placeholder="ملاحظة للوكيل (سبب القبول أو الرفض) — اختيارية"
              style={{ ...inp, flex: "1 1 260px", height: 34 }} />
            {mode !== "revoke" && (
              <button className="btn g" style={{ height: 34 }} disabled={!!bulkBusy}
                onClick={() => bulk("approve")}
                title={mode === "restore"
                  ? "إعادة قبول الطلب — يُضاف المبلغ إلى محفظة الوكيل"
                  : "قبول الطلب — يُضاف المبلغ إلى محفظة الوكيل"}>
                {bulkBusy === "approve" ? "جارٍ..." : mode === "restore" ? "قبول الطلب" : "قبول"}
              </button>
            )}
            {mode !== "restore" && (
              <button className="btn r" style={{ height: 34 }} disabled={!!bulkBusy}
                onClick={() => bulk("reject")}
                title={mode === "revoke"
                  ? "إبطال القبول — يُسحب المبلغ من محفظة الوكيل"
                  : "رفض الطلب — لا يُمسّ رصيد الوكيل"}>
                {bulkBusy === "reject" ? "جارٍ..." : mode === "revoke" ? "إبطال القبول" : "رفض"}
              </button>
            )}
            <button className="btn" style={{ height: 34, background: "#8a999e" }} onClick={() => setPicked([])}>
              إلغاء التحديد
            </button>
          </div>
          <div style={{ fontSize: 12, color: "var(--muted)", marginTop: 8 }}>
            {mode === "revoke" ? (
              <>عكس قرار: هذه طلبات <b>مقبولة</b> — إبطالها <b>يسحب المبلغ</b> من محفظة الوكيل.</>
            ) : mode === "restore" ? (
              <>عكس قرار: هذه طلبات <b>مرفوضة</b> — قبولها <b>يضيف المبلغ</b> إلى محفظة الوكيل.</>
            ) : (
              <>القبول يضيف <b>المبلغ بعد العمولة وبسعر الصرف</b> إلى محفظة الوكيل. الرفض لا يمسّ رصيده.</>
            )}
          </div>
          {bulkMsg && (
            <div style={{
              marginTop: 8, fontSize: 12.5, padding: "7px 10px", borderRadius: 6,
              background: bulkMsg.ok ? "rgba(53,194,69,.10)" : "rgba(221,68,68,.10)",
              color: bulkMsg.ok ? "var(--ok)" : "var(--danger)",
            }}>{bulkMsg.text}</div>
          )}
        </div>
      )}

      {/* ===== الجدول ===== */}
      <div className="card">
        <div className="table-scroll">
          <table className="grid">
            <thead>
              <tr>
                <th>
                  <input type="checkbox" title="تحديد الكل" checked={allPicked}
                    onChange={toggleAll} disabled={pickable.length === 0} />
                </th>
                <th>#</th>
                <th>الوكيل</th>
                <th className="cell-start">طريقة الدفع</th>
                <th>المبلغ المُرسل</th>
                <th>1 {base} =</th>
                <th>العمولة</th>
                <th>المُضاف للمحفظة</th>
                <th>التاريخ</th>
                <th>الحالة</th>
                <th>تفاصيل</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan={11} style={{ padding: 26, color: "var(--muted)" }}>جارٍ التحميل...</td></tr>
              ) : reqs.length === 0 ? (
                <tr><td colSpan={11} style={{ padding: 26, color: "var(--muted)" }}>لا توجد طلبات</td></tr>
              ) : reqs.map((r) => (
                <Fragment key={r.id}>
                  <tr className={[ROW_TONE[r.status] || "", picked.includes(r.id) ? "row-pick" : ""]
                    .filter(Boolean).join(" ")}>
                    <td>{selectable(r) && (
                      <input type="checkbox" checked={picked.includes(r.id)} onChange={() => toggleOne(r.id)} />
                    )}</td>
                    <td className="num" style={{ color: "var(--primary-dark)", fontWeight: 700, cursor: "pointer" }}
                      onClick={() => setExpanded(expanded === r.id ? null : r.id)}>
                      {r.id}
                    </td>
                    <td>{r.dealer_name}<div style={{ fontSize: 11, color: "var(--faint)" }}>{r.dealer_login}</div></td>
                    <td className="cell-start" style={{ fontWeight: 600 }}>{r.method_name || r.account_title || "—"}</td>
                    <td className="num" style={{ fontWeight: 700 }}>{money(r.amount)} {symbolOf(r.currency)}</td>
                    <td className="num" style={{ color: "var(--muted)" }}>
                      {money(r.rate, 4)} {symbolOf(r.currency)}
                    </td>
                    <td className="num" style={{ color: "var(--muted)" }}>{money(r.commission_percent)}%</td>
                    <td className="sell num" style={{ fontWeight: 800 }}>{money(r.credit_amount)}</td>
                    <td style={{ fontSize: 12, color: "var(--muted)" }}>{r.created_at}</td>
                    <td><span className={`stdot ${DOT[r.status] || "wait"}`} title={r.status_label} /></td>
                    <td>
                      <button onClick={() => setExpanded(expanded === r.id ? null : r.id)} title="بيانات الطلب"
                        style={{
                          border: "1px solid var(--border)", background: "var(--surface)",
                          color: "var(--primary)", width: 28, height: 28, borderRadius: 7,
                          display: "inline-flex", alignItems: "center", justifyContent: "center", cursor: "pointer",
                        }}>
                        <Icon name="details" size={14} />
                      </button>
                    </td>
                  </tr>
                  {expanded === r.id && (
                    <tr>
                      <td colSpan={11} className="cell-start" style={{ background: "var(--surface-2)", fontSize: 13, lineHeight: 1.9 }}>
                        <b>بيانات أرسلها الوكيل:</b>{" "}
                        {Object.keys(r.values || {}).length === 0 ? (
                          <span style={{ color: "var(--muted)" }}>— لا حقول —</span>
                        ) : (
                          Object.entries(r.values).map(([k, v]) => (
                            <span key={k} style={{ marginInlineEnd: 14 }}>
                              <span style={{ color: "var(--muted)" }}>{k}:</span>{" "}
                              {isImageValue(v) ? (
                                <a href={v} target="_blank" rel="noreferrer" title="فتح الصورة بحجمها">
                                  <img src={v} alt={k} style={{ height: 64, maxWidth: 120, objectFit: "cover",
                                    borderRadius: 6, border: "1px solid var(--border)", verticalAlign: "middle" }} />
                                </a>
                              ) : <b>{v}</b>}
                            </span>
                          ))
                        )}
                        {r.note && <div><span style={{ color: "var(--muted)" }}>ملاحظة الوكيل:</span> {r.note}</div>}
                        {r.admin_note && (
                          <div><span style={{ color: "var(--muted)" }}>ملاحظتك:</span>{" "}
                            <b style={{ color: "var(--primary-dark)" }}>{r.admin_note}</b></div>
                        )}
                        <div style={{ color: "var(--muted)" }}>
                          الحالة: <b>{r.status_label}</b>
                          {r.decided_at && <> · تاريخ القرار: {r.decided_at}</>}
                          {r.balance_before !== null && (
                            <> · رصيد الوكيل قبل {money(r.balance_before)} → بعد {money(r.balance_after || 0)}</>
                          )}
                        </div>
                      </td>
                    </tr>
                  )}
                </Fragment>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <div style={{ fontSize: 12.5, color: "var(--muted)", fontWeight: 700, marginBottom: 4 }}>{label}</div>
      {children}
    </div>
  );
}

const fgrid: React.CSSProperties = {
  display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: "12px 16px", padding: 16,
};
const inp: React.CSSProperties = { width: "100%", height: 36, borderRadius: 8 };
const qdot: React.CSSProperties = {
  width: 16, height: 16, borderRadius: "50%", border: "1px solid rgba(0,0,0,.15)",
  cursor: "pointer", boxShadow: "inset 0 -2px 3px rgba(0,0,0,.2)",
};
const bulkBar: React.CSSProperties = {
  padding: "12px 14px", marginBottom: 12, borderInlineStart: "4px solid var(--primary)",
};
const filterToggle: React.CSSProperties = {
  marginInlineStart: 10, background: "var(--surface)", border: "1px solid var(--border)",
  borderRadius: 6, color: "var(--text)", fontSize: 12.5, fontWeight: 700,
  padding: "5px 10px", cursor: "pointer", display: "inline-flex", alignItems: "center",
};
const fcount: React.CSSProperties = {
  background: "var(--primary)", color: "#fff", borderRadius: 9, fontSize: 10,
  fontWeight: 800, padding: "1px 6px", marginInlineStart: 5,
};

/** قيمةٌ أرسلها الوكيل وهي صورة (رفعٌ من جهازه، أو رابط صورةٍ قديم) */
function isImageValue(v: string) {
  return /^\/api\/catalog\/img\//.test(v) || /^data:image\//.test(v)
    || /^https?:\/\/\S+\.(png|jpe?g|webp|gif)(\?.*)?$/i.test(v);
}
