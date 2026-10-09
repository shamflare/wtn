import { Fragment, useEffect, useState } from "react";
import { api } from "../api";
import Icon from "../components/Icon";
import ScrollTop from "../components/ScrollTop";
import DateRange, { rangeText, TODAY } from "../components/DateRange";
import { empty, input, money, OpBadge, OPERATORS, pageTitle, pageWrap } from "./kontorUi";

interface Order {
  id: number; gsm: string; operator: string; dealer: string; dealer_id: number;
  package_name: string; znet_id: string; cost_price: string; sell_price: string; profit: string;
  status: string; status_label: string; provider: string; note: string; trace?: string; tekil: string;
  balance_before: string; balance_after: string; created_at: string; updated_at: string;
}
interface Summary { counts: Record<string, number>; total: number; sales: string; profit: string }

// كرات الحالة السريعة — بألوان طلبات الألعاب نفسها
const DOTS: [string, string, string][] = [
  ["", "#7d8f94", "الكل"], ["processing", "#3b82f6", "قيد التنفيذ"], ["success", "#35c245", "ناجح"],
  ["failed", "#dd4444", "فشل"], ["refunded", "#8a999e", "مُسترجَع"],
];
const ROW_TONE: Record<string, string> = { pending: "row-wait", processing: "row-sent" };
// تفتح على طلبات اليوم — والفترة تُغيَّر من شريط التاريخ
const EMPTY = { operator: "", dealer: "", q: "", ...TODAY };

export default function KontorOrders() {
  const [rows, setRows] = useState<Order[]>([]);
  const [sum, setSum] = useState<Summary | null>(null);
  const [st, setSt] = useState("");
  const [f, setF] = useState({ ...EMPTY });
  const [dealers, setDealers] = useState<{ id: number; name: string }[]>([]);
  const [loading, setLoading] = useState(true);
  const [open, setOpen] = useState<number | null>(null);
  const [lastSync, setLastSync] = useState("");

  async function load(status = st, filters = f) {
    const params: Record<string, string> = {};
    if (status) params.status = status;
    Object.entries(filters).forEach(([k, v]) => { if (v) params[k] = v; });
    const r = await api.get("/kontor/orders/", { params });
    setRows(r.data.results); setSum(r.data.summary);
    setLastSync(new Date().toLocaleTimeString("en-GB"));
  }
  useEffect(() => {
    load().catch(() => {}).finally(() => setLoading(false));
    api.get("/kontor/dealer-settings/").then((r) => setDealers(r.data.dealers)).catch(() => {});
  }, []);

  // ما دام طلب «قيد التنفيذ» ظاهراً نعيد القراءة بصمت — المتابعة عند ZNET تجري في الخادم كل دقيقة
  const live = rows.some((o) => o.status === "processing" || o.status === "pending");
  useEffect(() => {
    if (!live) return;
    const t = setInterval(() => load().catch(() => {}), 10000);
    return () => clearInterval(t);
  }, [live, st, f]);

  const set = (k: keyof typeof EMPTY, v: string) => setF((o) => ({ ...o, [k]: v }));
  const pickStatus = (s: string) => { setSt(s); load(s).catch(() => {}); };
  const apply = () => load().catch(() => {});
  const clear = () => { setF({ ...EMPTY }); setSt(""); load("", { ...EMPTY }).catch(() => {}); };
  const c = sum?.counts || {};

  return (
    <div style={pageWrap}>
      <ScrollTop />
      <h2 style={pageTitle}><Icon name="receipt" size={20} /> طلبات شحن الخطوط</h2>

      <div className="summary">
        <Stat label="كل الطلبات" value={String(sum?.total ?? 0)} icon="receipt" />
        <Stat label="ناجحة" value={String(c.success ?? 0)} icon="check" tone="var(--ok)"
          sub={`${(c.failed ?? 0) + (c.refunded ?? 0)} فاشلة/مُسترجَعة · ${c.processing ?? 0} قيد التنفيذ`} />
        <Stat label="مبيعات ناجحة" value={money(sum?.sales ?? 0)} icon="dollar" />
        <Stat label="الربح" value={money(sum?.profit ?? 0)} icon="chart" tone="var(--ok)" />
      </div>

      <div className="card">
        <div className="card-title">
          <Icon name="filter" size={16} style={{ color: "var(--primary)" }} /> الفلترة
          {live && <span className="pill on" style={{ fontWeight: 600 }}>متابعة حيّة · {lastSync}</span>}
          <span style={{ marginInlineStart: "auto", display: "inline-flex", gap: 6, alignItems: "center" }}>
            {DOTS.map(([k, col, t]) => (
              <button key={k} title={`${t}${k ? ` (${c[k] ?? 0})` : ""}`} onClick={() => pickStatus(k)}
                style={{ ...qdot, background: col, outline: st === k ? "2px solid var(--primary)" : "none" }} />
            ))}
          </span>
        </div>
        <div style={{ padding: "10px 14px", borderBottom: "1px solid var(--border)", display: "flex",
          gap: 12, alignItems: "center", flexWrap: "wrap" }}>
          <DateRange value={f} onChange={(d) => { const next = { ...f, ...d }; setF(next); load(st, next).catch(() => {}); }} />
          <span style={{ fontSize: 12.5, color: "var(--muted)" }}>
            المعروض: <b style={{ color: "var(--text)" }}>{rangeText(f)}</b>
          </span>
        </div>
        <div style={fgrid}>
          <select value={f.operator} onChange={(e) => set("operator", e.target.value)} style={input}>
            <option value="">كل الشركات</option>
            {OPERATORS.map((o) => <option key={o.code} value={o.code}>{o.label}</option>)}
          </select>
          <select value={f.dealer} onChange={(e) => set("dealer", e.target.value)} style={input}>
            <option value="">كل الوكلاء</option>
            {dealers.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
          </select>
          <input value={f.q} onChange={(e) => set("q", e.target.value)} placeholder="رقم الخط أو الباقة أو المرجع"
            onKeyDown={(e) => e.key === "Enter" && apply()} style={input} />
          <div style={{ display: "flex", gap: 6 }}>
            <button className="btn g" onClick={apply} style={{ flex: 1 }}><Icon name="search" size={14} /> بحث</button>
            <button className="btn" onClick={clear} title="مسح الفلاتر">مسح</button>
          </div>
        </div>
      </div>

      <div className="card"><div className="table-scroll">
        <table className="grid">
          <thead>
            <tr>
              <th>#</th><th>الحالة</th><th>الرقم</th><th className="cell-start">الباقة</th><th>الوكيل</th>
              <th>الكلفة</th><th>البيع</th><th>الربح</th><th>التاريخ</th><th style={{ width: 40 }}></th>
            </tr>
          </thead>
          <tbody>
            {loading && <tr><td colSpan={10} style={empty}>جارٍ التحميل...</td></tr>}
            {!loading && rows.length === 0 && <tr><td colSpan={10} style={empty}>لا طلبات.</td></tr>}
            {rows.map((o) => (
              <Fragment key={o.id}>
                <tr className={ROW_TONE[o.status] || ""} style={{ cursor: "pointer" }} onClick={() => setOpen(open === o.id ? null : o.id)}>
                  <td className="num" style={{ color: "var(--muted)" }}>{o.id}</td>
                  <td><StatusMark o={o} /></td>
                  <td>
                    <span style={{ display: "inline-flex", alignItems: "center", gap: 7, direction: "ltr", fontWeight: 700 }} className="num">
                      <OpBadge code={o.operator} size={20} /> {o.gsm}
                    </span>
                  </td>
                  <td className="cell-start">
                    <div style={{ fontWeight: 600 }}>{o.package_name}</div>
                    <div style={{ fontSize: 11, color: "var(--muted)" }}>{o.znet_id}</div>
                  </td>
                  <td>{o.dealer}</td>
                  <td className="num buy">{money(o.cost_price)}</td>
                  <td className="num sell">{money(o.sell_price)}</td>
                  <td className="num profit">{o.status === "success" ? money(o.profit) : <span style={{ color: "var(--faint)" }}>—</span>}</td>
                  <td className="num" style={{ fontSize: 12.5 }}>{o.created_at}</td>
                  <td style={{ color: "var(--muted)", fontSize: 11 }}>{open === o.id ? "▲" : "▼"}</td>
                </tr>
                {open === o.id && (
                  <tr><td colSpan={10} style={{ background: "var(--row-alt)", textAlign: "start", padding: "12px 18px" }}>
                    <div style={detailGrid}>
                      <Info k="رد المزوّد" v={o.note || "—"} wide />
                      {o.trace && <Info k="مسار المحاولات" v={o.trace} wide />}
                      <Info k="المزوّد" v={o.provider || "—"} />
                      <Info k="مرجعنا لدى ZNET" v={o.tekil || "—"} mono />
                      <Info k="رصيد الوكيل قبل ⇐ بعد" v={`${money(o.balance_before)} ⇐ ${money(o.balance_after)}`} mono />
                      <Info k="آخر تحديث" v={o.updated_at} mono />
                    </div>
                  </td></tr>
                )}
              </Fragment>
            ))}
          </tbody>
        </table>
      </div></div>
    </div>
  );
}

function StatusMark({ o }: { o: Order }) {
  const spin = o.status === "processing" || o.status === "pending";
  const color = { success: "var(--ok)", failed: "var(--danger)", refunded: "var(--muted)" }[o.status] || "var(--info)";
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 6, fontWeight: 700, fontSize: 12.5, color }}>
      {spin ? <span className={`stspin${o.status === "processing" ? " proc" : ""}`} />
        : <span className={`stdot ${o.status === "success" ? "ok" : o.status === "failed" ? "err" : "wait"}`}
            style={o.status === "refunded" ? { background: "#8a999e" } : undefined} />}
      {o.status_label}
    </span>
  );
}

function Info({ k, v, mono, wide }: { k: string; v: string; mono?: boolean; wide?: boolean }) {
  return (
    <div style={wide ? { gridColumn: "1 / -1" } : undefined}>
      <div style={{ fontSize: 11.5, color: "var(--muted)", marginBottom: 2 }}>{k}</div>
      <div className={mono ? "num" : ""} style={{ fontWeight: 600, whiteSpace: "normal", wordBreak: "break-word" }}>{v}</div>
    </div>
  );
}

function Stat({ label, value, icon, tone, sub }: { label: string; value: string; icon: string; tone?: string; sub?: string }) {
  return (
    <div className="stat">
      <div className="label"><Icon name={icon} size={14} /> {label}</div>
      <div className="value num" style={tone ? { color: tone } : undefined}>{value}</div>
      {sub && <div style={{ fontSize: 11.5, color: "var(--faint)", marginTop: 2 }}>{sub}</div>}
      <div className="spark" />
    </div>
  );
}

const qdot: React.CSSProperties = {
  width: 18, height: 18, borderRadius: "50%", border: 0, cursor: "pointer", outlineOffset: 2,
  boxShadow: "inset 0 -2px 3px rgba(0,0,0,.25)",
};
const fgrid: React.CSSProperties = {
  display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(170px, 1fr))", gap: 10, padding: 14,
};
const detailGrid: React.CSSProperties = {
  display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(190px, 1fr))", gap: 12, fontSize: 13,
};
