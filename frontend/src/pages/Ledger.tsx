import { useEffect, useState } from "react";
import { api } from "../api";
import DateRange, { rangeText, TODAY, type Dates } from "../components/DateRange";
import Pager, { type Paging } from "../components/Pager";
import SearchSelect, { type SearchOption } from "../components/SearchSelect";

interface Txn {
  id: number; dealer_name: string; type: string; type_label: string;
  amount: string; balance_before: string; balance_after: string; note: string; created_at: string;
}
const TYPES = [
  { key: "all", label: "الكل" },
  { key: "topup", label: "شحن" },
  { key: "order_debit", label: "خصم طلب" },
  { key: "refund", label: "استرجاع" },
  { key: "manual_credit", label: "إضافة يدوية" },
  { key: "manual_debit", label: "خصم يدوي" },
];

export default function Ledger() {
  const [txns, setTxns] = useState<Txn[]>([]);
  const [type, setType] = useState("all");
  const [loading, setLoading] = useState(true);
  const [dates, setDates] = useState<Dates>(TODAY);   // يفتح على حركات اليوم
  const [page, setPage] = useState(1);
  const [paging, setPaging] = useState<Paging | null>(null);
  const [dealer, setDealer] = useState("");
  const [dealers, setDealers] = useState<SearchOption[]>([]);

  // الوكلاء ودكاكين الوكلاء الكبار — للبحث في القائمة باسم أو رقم دخول
  useEffect(() => {
    api.get("/dealers/").then((r) => {
      const out: SearchOption[] = [];
      for (const d of r.data.results || []) {
        out.push({ id: d.id, name: d.name, sub: d.login_id });
        for (const c of d.children || []) out.push({ id: c.id, name: `${c.name} — دكان ${d.name}`, sub: c.login_id });
      }
      setDealers(out);
    }).catch(() => {});
  }, []);

  function load() {
    setLoading(true);
    const params: Record<string, string> = { type, page: String(page) };
    if (dealer) params.dealer = dealer;
    if (dates.date_from) params.date_from = dates.date_from;
    if (dates.date_to) params.date_to = dates.date_to;
    api.get("/ledger/", { params })
      .then((r) => { setTxns(r.data.results); setPaging(r.data.paging); })
      .finally(() => setLoading(false));
  }
  useEffect(() => load(), [type, dates, page, dealer]);

  const money = (v: string) => Number(v).toLocaleString("en-US", { minimumFractionDigits: 2 });

  return (
    <div style={{ padding: 16 }}>
      <h2 style={{ fontSize: 20, color: "var(--primary-dark)", marginBottom: 12 }}>
        حركات الحسابات
      </h2>
      <div style={{ display: "flex", gap: 6, marginBottom: 12, flexWrap: "wrap" }}>
        {TYPES.map((t) => (
          <button key={t.key} onClick={() => { setType(t.key); setPage(1); }} className="btn"
            style={{ background: type === t.key ? "var(--primary)" : "#8a999e" }}>{t.label}</button>
        ))}
      </div>
      <div style={{ display: "flex", gap: 10, alignItems: "center", marginBottom: 12, flexWrap: "wrap" }}>
        <DateRange value={dates} onChange={(d) => { setDates(d); setPage(1); }} />
        <SearchSelect options={dealers} value={dealer} allLabel="كل الوكلاء" placeholder="ابحث باسم الوكيل أو رقم دخوله..."
          onChange={(v) => { setDealer(v); setPage(1); }} />
        <span style={{ fontSize: 12.5, color: "var(--muted)" }}>
          المعروض: <b style={{ color: "var(--text)" }}>{rangeText(dates)}</b> · حركات دكاكين الوكلاء الكبار في كشوفهم لا هنا
        </span>
      </div>
      <table style={table}>
        <thead>
          <tr>{["#", "الوكيل", "النوع", "المبلغ", "الرصيد قبل", "الرصيد بعد", "ملاحظة", "التاريخ"]
            .map((h) => <th key={h} style={th}>{h}</th>)}</tr>
        </thead>
        <tbody>
          {loading ? (
            <tr><td colSpan={8} style={{ ...td, padding: 24 }}>جارٍ التحميل...</td></tr>
          ) : txns.length === 0 ? (
            <tr><td colSpan={8} style={{ ...td, padding: 24 }}>لا توجد حركات</td></tr>
          ) : txns.map((t, i) => {
            const neg = Number(t.amount) < 0;
            return (
              <tr key={t.id} style={{ background: i % 2 ? "var(--row-alt)" : "#fff" }}>
                <td style={{ ...td, color: "var(--muted)" }}>{t.id}</td>
                <td style={{ ...td, fontWeight: 600 }}>{t.dealer_name}</td>
                <td style={td}>{t.type_label}</td>
                <td style={{ ...td, fontWeight: 700, color: neg ? "var(--danger)" : "var(--ok)" }}>
                  {neg ? "" : "+"}{money(t.amount)}
                </td>
                <td style={{ ...td, color: "var(--muted)" }}>{money(t.balance_before)}</td>
                <td style={{ ...td, fontWeight: 600 }}>{money(t.balance_after)}</td>
                <td style={{ ...td, fontSize: 13 }}>{t.note || "—"}</td>
                <td style={{ ...td, fontSize: 13, color: "var(--muted)" }}>{t.created_at}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <Pager paging={paging} onPage={setPage} />
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
