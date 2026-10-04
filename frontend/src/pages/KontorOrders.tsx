import { useEffect, useState } from "react";
import { api } from "../api";
import ScrollTop from "../components/ScrollTop";

interface Order {
  id: number; gsm: string; operator: string; dealer: string;
  package_name: string; znet_id: string; cost_price: string; sell_price: string; profit: string;
  status: string; status_label: string; provider: string; note: string; created_at: string;
}

const ST_COLOR: Record<string, string> = {
  success: "var(--ok)", processing: "var(--info)", pending: "var(--warn)",
  failed: "var(--danger)", refunded: "var(--muted)",
};
const STATUSES = [
  { k: "", l: "الكل" }, { k: "success", l: "ناجح" }, { k: "processing", l: "قيد التنفيذ" },
  { k: "failed", l: "فشل" }, { k: "refunded", l: "مُسترجَع" },
];

export default function KontorOrders() {
  const [rows, setRows] = useState<Order[]>([]);
  const [st, setSt] = useState("");

  async function load() {
    const r = await api.get("/kontor/orders/" + (st ? `?status=${st}` : ""));
    setRows(r.data);
  }
  useEffect(() => { load().catch(() => {}); }, [st]);

  return (
    <div style={{ padding: 16 }}>
      <ScrollTop />
      <h2 style={{ fontWeight: 800, fontSize: 20 }}>طلبات شحن الخطوط</h2>
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap", margin: "10px 0" }}>
        {STATUSES.map((s) => (
          <button key={s.k} className={st === s.k ? "btn g" : "btn"} onClick={() => setSt(s.k)}>{s.l}</button>
        ))}
        <button className="btn" onClick={() => load()} style={{ marginInlineStart: "auto" }}>↻ تحديث</button>
      </div>
      <div style={{ overflowX: "auto" }}>
        <table style={{ borderCollapse: "collapse", fontSize: 12.5, width: "100%" }}>
          <thead>
            <tr style={{ textAlign: "right", color: "var(--muted)" }}>
              <th style={th}>#</th><th style={th}>الرقم</th><th style={th}>الوكيل</th><th style={th}>الباقة</th>
              <th style={th}>الكلفة</th><th style={th}>البيع</th><th style={th}>الربح</th>
              <th style={th}>الحالة</th><th style={th}>المزوّد</th><th style={th}>التاريخ</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((o) => (
              <tr key={o.id} style={{ borderTop: "1px solid var(--border)" }}>
                <td style={td}>{o.id}</td>
                <td style={{ ...td, direction: "ltr" }}>{o.gsm}</td>
                <td style={td}>{o.dealer}</td>
                <td style={td} title={o.note}>{o.package_name}</td>
                <td style={td}>{o.cost_price}</td><td style={td}>{o.sell_price}</td><td style={td}>{o.profit}</td>
                <td style={{ ...td, color: ST_COLOR[o.status], fontWeight: 700 }}>{o.status_label}</td>
                <td style={td}>{o.provider}</td>
                <td style={{ ...td, whiteSpace: "nowrap" }}>{o.created_at}</td>
              </tr>
            ))}
            {rows.length === 0 && <tr><td style={td} colSpan={10}>لا طلبات.</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}

const th: React.CSSProperties = { padding: "6px", fontWeight: 700, whiteSpace: "nowrap" };
const td: React.CSSProperties = { padding: "5px 6px" };
