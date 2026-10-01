import { useEffect, useState } from "react";
import { api } from "../api";
import Icon from "../components/Icon";
import { symbolOf } from "../currency";

const STATUSES: [string, string][] = [
  ["all", "الكل"], ["success", "ناجح"], ["pending", "قيد الانتظار"],
  ["cancelled", "ملغى"],
];

/**
 * طلبات دكاكين الوكيل الكبير.
 *
 * ليست طلباته هو — هو لا يشحن من الموقع. هذه ما اشتراه دكاكينه منه: بكم دفعوا
 * وكم ربح هو من كل طلب.
 */
export default function AgentOrders() {
  const [rows, setRows] = useState<any[]>([]);
  const [cur, setCur] = useState("");
  const [status, setStatus] = useState("all");
  const [dealer, setDealer] = useState("");
  const [q, setQ] = useState("");
  const [loading, setLoading] = useState(true);

  function load() {
    setLoading(true);
    api.get("/agent/orders/", { params: { status } })
      .then((r) => { setRows(r.data.results || []); setCur(r.data.currency || ""); })
      .finally(() => setLoading(false));
  }
  useEffect(() => load(), [status]);

  /** تتبُّع الطلبات المعلّقة يحتاج تحديثاً دورياً — دقيقة تكفي. */
  useEffect(() => {
    const t = setInterval(load, 60_000);
    return () => clearInterval(t);
  }, [status]);

  const money = (v: string) => Number(v).toLocaleString("en-US", { minimumFractionDigits: 2 });
  const sym = symbolOf(cur);

  const dealers = Array.from(new Set(rows.map((o) => o.dealer_name))).sort();
  const shown = rows.filter((o) => {
    if (dealer && o.dealer_name !== dealer) return false;
    if (!q) return true;
    const hay = `${o.receipt_no} ${o.dealer_name} ${o.product_name} ${o.game_name}`;
    return hay.includes(q);
  });
  const totalProfit = shown.reduce((s, o) => s + Number(o.profit || 0), 0);
  const totalPaid = shown.reduce((s, o) => s + Number(o.sell_price || 0), 0);

  const tone = (s: string) =>
    s === "success" ? "var(--ok)" : s === "cancelled" ? "var(--danger)" : "var(--muted)";

  return (
    <div style={{ maxWidth: 1320, margin: "0 auto", padding: "22px 20px 40px" }}>
      <div className="toolbar">
        <div style={{ position: "relative", flex: 1, minWidth: 200 }}>
          <input placeholder="بحث برقم الإيصال أو الدكان أو الباقة…" value={q}
            onChange={(e) => setQ(e.target.value)}
            style={{ width: "100%", height: 40, paddingInlineStart: 36, borderRadius: 10 }} />
          <span style={{ position: "absolute", insetInlineStart: 11, top: 11, color: "var(--faint)" }}>
            <Icon name="search" size={17} />
          </span>
        </div>
        <div className="segment">
          {STATUSES.map(([k, label]) => (
            <button key={k} className={status === k ? "active" : ""} onClick={() => setStatus(k)}>
              {label}
            </button>
          ))}
        </div>
        <select value={dealer} onChange={(e) => setDealer(e.target.value)}
          style={{ height: 40, borderRadius: 10, minWidth: 150 }}>
          <option value="">كل الدكاكين</option>
          {dealers.map((d) => <option key={d} value={d}>{d}</option>)}
        </select>
        <button className="btn" onClick={load} title="تحديث الآن">
          <Icon name="refresh" size={15} style={{ marginInlineEnd: 5, verticalAlign: -2 }} />تحديث
        </button>
      </div>

      <div className="summary" style={{ marginBottom: 14 }}>
        <div className="stat">
          <div className="label"><Icon name="chart" size={15} style={{ color: "var(--primary)" }} /> عدد الطلبات</div>
          <div className="value num">{shown.length}</div><span className="spark" />
        </div>
        <div className="stat">
          <div className="label"><Icon name="wallet" size={15} style={{ color: "var(--primary)" }} /> دفعوا لي</div>
          <div className="value num">{money(String(totalPaid))} <small style={{ fontSize: 13, color: "var(--faint)" }}>{sym}</small></div>
          <span className="spark" />
        </div>
        <div className="stat">
          <div className="label"><Icon name="dollar" size={15} style={{ color: "var(--primary)" }} /> ربحي منها</div>
          <div className="value num bal-pos">{money(String(totalProfit))} <small style={{ fontSize: 13, color: "var(--faint)" }}>{sym}</small></div>
          <span className="spark" />
        </div>
      </div>

      <div className="card">
        <div className="card-title">
          <Icon name="chart" size={16} style={{ color: "var(--primary)" }} /> متابعة الطلبات
        </div>
        <div className="table-scroll">
          <table className="grid">
            <thead>
              <tr>
                <th>رقم الإيصال</th>
                <th className="cell-start">الدكان</th>
                <th className="cell-start">الباقة</th>
                <th>اللعبة</th>
                <th>دفع لي</th>
                <th>ربحي</th>
                <th>الحالة</th>
                <th>التاريخ</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan={8} style={{ padding: 30, color: "var(--muted)" }}>جارٍ التحميل...</td></tr>
              ) : shown.length === 0 ? (
                <tr><td colSpan={8} style={{ padding: 30, color: "var(--muted)" }}>لا طلبات مطابقة</td></tr>
              ) : shown.map((o) => (
                <tr key={o.id}>
                  <td className="num" style={{ color: "var(--faint)", fontSize: 12.5 }}>{o.receipt_no}</td>
                  <td className="cell-start" style={{ fontWeight: 700 }}>{o.dealer_name}</td>
                  <td className="cell-start">{o.product_name}</td>
                  <td style={{ color: "var(--muted)", fontSize: 13 }}>{o.game_name}</td>
                  <td className="num">{money(o.sell_price)} <small style={{ color: "var(--faint)" }}>{sym}</small></td>
                  <td className="num bal-pos" style={{ fontWeight: 700 }}>{money(o.profit)}</td>
                  <td style={{ color: tone(o.status), fontWeight: 700, fontSize: 12.5 }}>{o.status_label}</td>
                  <td style={{ color: "var(--muted)", fontSize: 12.5 }}>{o.created_at}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
