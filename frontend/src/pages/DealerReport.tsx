import { useEffect, useState } from "react";
import { api } from "../api";
import DateRange, { rangeText, TODAY, type Dates } from "../components/DateRange";
import { symbolOf } from "../currency";

interface Row { dealer: string; count: number; sell: string; profit: string }
interface Totals { count: string; sell: string; profit: string }

/**
 * تقرير الأرباح بحسب الوكيل — يفتح على اليوم. وللوكيل الكبير (`agent`) أرباحه هو
 * من كل دكان من دكاكينه، بعملته.
 */
export default function DealerReport({ title, highlight, agent }:
  { title: string; highlight: "profit" | "sell"; agent?: boolean }) {
  const [rows, setRows] = useState<Row[]>([]);
  const [totals, setTotals] = useState<Totals | null>(null);
  const [loading, setLoading] = useState(true);
  const [dates, setDates] = useState<Dates>(TODAY);
  const [cur, setCur] = useState("");

  useEffect(() => {
    setLoading(true);
    const params: Record<string, string> = {};
    if (dates.date_from) params.date_from = dates.date_from;
    if (dates.date_to) params.date_to = dates.date_to;
    api.get(agent ? "/agent/reports/dealers/" : "/orders/reports/dealers/", { params })
      .then((r) => { setRows(r.data.results); setTotals(r.data.totals); setCur(r.data.currency || ""); })
      .finally(() => setLoading(false));
  }, [title, dates, agent]);

  const money = (v: string) => Number(v).toLocaleString("en-US", { minimumFractionDigits: 2 });
  const hi = (col: "profit" | "sell") =>
    col === highlight ? { color: "var(--ok)", fontWeight: 700 } : {};

  return (
    <div style={{ padding: 16 }}>
      <h2 style={{ fontSize: 20, color: "var(--primary-dark)", marginBottom: 12 }}>{title}</h2>
      <div style={{ display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap", background: "#f2f5f6",
        padding: "12px 14px", borderRadius: 6, marginBottom: 12 }}>
        <DateRange value={dates} onChange={setDates} />
        <span style={{ fontSize: 12.5, color: "var(--muted)" }}>
          الفترة المعروضة: <b style={{ color: "var(--text)" }}>{rangeText(dates)}</b>
          {cur && <> · المبالغ بـ<b style={{ color: "var(--text)" }}>{symbolOf(cur)}</b></>}
        </span>
      </div>
      <table style={table}>
        <thead>
          <tr>{[agent ? "الدكان" : "الوكيل", "عدد الطلبات", "إجمالي المبيعات", agent ? "ربحي" : "إجمالي الربح"]
            .map((h) => <th key={h} style={th}>{h}</th>)}</tr>
        </thead>
        <tbody>
          {loading ? (
            <tr><td colSpan={4} style={{ ...td, padding: 24 }}>جارٍ التحميل...</td></tr>
          ) : rows.length === 0 ? (
            <tr><td colSpan={4} style={{ ...td, padding: 24 }}>لا توجد بيانات</td></tr>
          ) : rows.map((r, i) => (
            <tr key={i} style={{ background: i % 2 ? "var(--row-alt)" : "#fff" }}>
              <td style={{ ...td, textAlign: "right", paddingInlineStart: 12, fontWeight: 600 }}>{r.dealer}</td>
              <td style={td}>{r.count}</td>
              <td style={{ ...td, ...hi("sell") }}>{money(r.sell)}</td>
              <td style={{ ...td, ...hi("profit") }}>{money(r.profit)}</td>
            </tr>
          ))}
        </tbody>
        {totals && (
          <tfoot>
            <tr style={{ background: "#f5c518", fontWeight: 700 }}>
              <td style={td}>المجاميع</td>
              <td style={td}>{totals.count}</td>
              <td style={td}>{money(totals.sell)}</td>
              <td style={td}>{money(totals.profit)}</td>
            </tr>
          </tfoot>
        )}
      </table>
      <div style={{ fontSize: 12, color: "var(--muted)", marginTop: 8 }}>* الطلبات الناجحة فقط.</div>
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
