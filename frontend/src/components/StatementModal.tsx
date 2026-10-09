import { useEffect, useState } from "react";
import { api } from "../api";
import Icon from "../components/Icon";
import { downloadCsv } from "../csv";
import { money, symbolOf } from "../currency";
import DateRange, { type Dates } from "./DateRange";
import Pager, { type Paging } from "./Pager";

interface Txn {
  id: number; type: string; type_label: string; internal?: boolean;
  amount: string; balance_after: string; note: string; created_at: string;
}
interface Data {
  dealer: { id: number; name: string; balance: string; currency?: string; is_big?: boolean;
            balance_own?: string; own_currency?: string };
  currency?: string;
  types?: { key: string; label: string }[];
  totals: { count: number; in: string; out: string };
  paging: Paging;
  results: Txn[];
}

// الحركات الرافعة للرصيد خضراء والخافضة حمراء — كما في لوحة الوكيل
const TYPE_COLOR: Record<string, string> = {
  topup: "var(--ok)", manual_credit: "var(--ok)", refund: "var(--ok)",
  order_debit: "var(--danger)", manual_debit: "var(--danger)", adjustment: "#3b82f6",
};
const ALL: Dates = { date_from: "", date_to: "" };

/**
 * كشف حساب محفظة — لصاحب المتجر (كشف وكيله)، وللوكيل الكبير (`url`) كشف دكانه.
 *
 * الفلاتر والصفحات من الخادم (20 صفّاً). ومحفظة الوكيل الكبير تُفتح على حركاته مع
 * **المتجر** وحدها؛ وزرّ «حركاته مع دكاكينه» يعرض ما بينه وبينهم — للاطّلاع فقط.
 */
export default function StatementModal({
  dealerId, dealerName, onClose, url,
}: { dealerId: number; dealerName: string; onClose: () => void; url?: string }) {
  const [data, setData] = useState<Data | null>(null);
  const [err, setErr] = useState("");
  const [dir, setDir] = useState("all");
  const [type, setType] = useState("all");
  const [dates, setDates] = useState<Dates>(ALL);
  const [scope, setScope] = useState<"store" | "agent">("store");
  const [page, setPage] = useState(1);
  const endpoint = url || `/dealers/${dealerId}/transactions/`;

  function params(extra: Record<string, any> = {}) {
    const p: Record<string, any> = { page, dir, type, scope, ...extra };
    if (dates.date_from) p.date_from = dates.date_from;
    if (dates.date_to) p.date_to = dates.date_to;
    return p;
  }
  useEffect(() => {
    api.get(endpoint, { params: params() })
      .then((r) => setData(r.data))
      .catch((e) => setErr(e?.response?.data?.detail || "تعذّر جلب كشف الحساب"));
  }, [endpoint, page, dir, type, dates, scope]);
  // تغيير الفلتر يعيد إلى الصفحة الأولى
  function reset<T>(set: (v: T) => void) {
    return (v: T) => { set(v); setPage(1); };
  }

  const rows = data?.results || [];
  const cur = symbolOf(data?.dealer.currency || data?.currency || "");

  /** التصدير يشمل كل ما طابق الفلتر — لا الصفحة الظاهرة وحدها. */
  async function exportCsv() {
    const all: Txn[] = [];
    for (let p = 1; ; p++) {
      const r = await api.get(endpoint, { params: params({ page: p, page_size: 100 }) });
      all.push(...r.data.results);
      if (p >= r.data.paging.pages) break;
    }
    downloadCsv(
      `كشف-حساب-${dealerName}`,
      ["التاريخ", "النوع", "المبلغ", "الرصيد بعدها", "ملاحظة"],
      all.map((t) => [t.created_at, t.type_label, t.amount, t.balance_after, t.note]),
    );
  }

  return (
    <div style={ovl} onClick={onClose}>
      <div style={box} onClick={(e) => e.stopPropagation()}>
        <div style={head}>
          <span>كشف حساب — {dealerName}</span>
          <button type="button" onClick={onClose} style={xBtn}>✕</button>
        </div>

        {err ? (
          <div style={{ padding: 24, color: "var(--danger)" }}>{err}</div>
        ) : !data ? (
          <div style={{ padding: 24, color: "var(--muted)" }}>جارٍ التحميل...</div>
        ) : (
          <div style={{ padding: 16 }}>
            <div style={statRow}>
              <Stat label="الرصيد الحالي" value={`${money(data.dealer.balance)} ${cur}`}
                sub={data.dealer.own_currency && data.dealer.own_currency !== data.dealer.currency
                  ? `${money(data.dealer.balance_own || 0)} ${symbolOf(data.dealer.own_currency)}` : undefined}
                tone={Number(data.dealer.balance) < 0 ? "var(--danger)" : "var(--ok)"} />
              <Stat label="مجموع الوارد" value={`${money(data.totals.in)} ${cur}`} tone="var(--ok)" />
              <Stat label="مجموع الصادر" value={`${money(data.totals.out)} ${cur}`} tone="var(--danger)" />
              <Stat label="عدد الحركات" value={String(data.totals.count)} tone="var(--text)" />
            </div>

            {data.dealer.is_big && (
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 12, flexWrap: "wrap" }}>
                <div className="segment">
                  <button className={scope === "store" ? "active" : ""} onClick={() => reset(setScope)("store")}>
                    حركاته مع المتجر
                  </button>
                  <button className={scope === "agent" ? "active" : ""} onClick={() => reset(setScope)("agent")}>
                    حركاته مع دكاكينه
                  </button>
                </div>
                <span style={{ fontSize: 12, color: "var(--muted)" }}>
                  {scope === "store"
                    ? "ما بينك وبين الوكيل الكبير وحده."
                    : "للاطّلاع فقط: بيعه لدكاكينه وحوالاته إليهم وإيداعاتهم عنده — دفترٌ بينه وبينهم."}
                </span>
              </div>
            )}

            <div style={{ display: "flex", gap: 8, alignItems: "center", margin: "12px 0 10px", flexWrap: "wrap" }}>
              <DateRange value={dates} onChange={reset(setDates)} compact />
              <div className="segment">
                {([["all", "الكل"], ["in", "وارد"], ["out", "صادر"]] as [string, string][]).map(([k, l]) => (
                  <button key={k} className={dir === k ? "active" : ""} onClick={() => reset(setDir)(k)}>{l}</button>
                ))}
              </div>
              <select value={type} onChange={(e) => reset(setType)(e.target.value)} style={{ height: 32 }}>
                <option value="all">كل الأنواع</option>
                {(data.types || []).map((t) => <option key={t.key} value={t.key}>{t.label}</option>)}
              </select>
              <button className="btn" style={{ height: 32, marginInlineStart: "auto" }}
                onClick={exportCsv} disabled={rows.length === 0}>
                <Icon name="excel" size={14} style={{ marginInlineEnd: 5, verticalAlign: -2 }} />
                تصدير Excel
              </button>
              <button className="btn" style={{ height: 32, background: "#8a999e" }}
                onClick={() => window.print()}>
                <Icon name="print" size={14} style={{ marginInlineEnd: 5, verticalAlign: -2 }} />
                طباعة
              </button>
            </div>

            <div className="table-scroll">
              <table className="grid">
                <thead>
                  <tr>
                    <th>التاريخ</th>
                    <th>النوع</th>
                    <th>المبلغ</th>
                    <th>الرصيد بعدها</th>
                    <th className="cell-start">ملاحظة</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.length === 0 ? (
                    <tr><td colSpan={5} style={{ padding: 24, color: "var(--muted)" }}>لا توجد حركات</td></tr>
                  ) : rows.map((t) => (
                    <tr key={t.id}>
                      <td style={{ fontSize: 12, color: "var(--muted)", whiteSpace: "nowrap" }}>{t.created_at}</td>
                      <td style={{ color: TYPE_COLOR[t.type] || "var(--text)", fontWeight: 700 }}>{t.type_label}</td>
                      <td className="num" style={{
                        color: Number(t.amount) < 0 ? "var(--danger)" : "var(--ok)", fontWeight: 700,
                      }}>{money(t.amount)}</td>
                      <td className="num">{money(t.balance_after)}</td>
                      <td className="cell-start" style={{ color: "var(--muted)", fontSize: 12.5 }}>{t.note || "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <Pager paging={data.paging} onPage={setPage} />
            <div style={{ fontSize: 12, color: "var(--muted)", marginTop: 4 }}>
              {data.dealer.currency
                ? <>الأرقام بعملة دفتر المتجر ({data.dealer.currency}).</>
                : <>الأرقام بعملتك ({data.currency}).</>}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function Stat({ label, value, tone, sub }: { label: string; value: string; tone: string; sub?: string }) {
  return (
    <div style={statCard}>
      <div style={{ fontSize: 11.5, color: "var(--muted)", fontWeight: 700 }}>{label}</div>
      <div style={{ fontSize: 17, fontWeight: 800, color: tone, marginTop: 4 }}>{value}</div>
      {sub && <div style={{ fontSize: 12, color: "var(--muted)", marginTop: 2 }}>{sub}</div>}
    </div>
  );
}

const ovl: React.CSSProperties = {
  position: "fixed", inset: 0, background: "rgba(0,0,0,.45)", zIndex: 80,
  display: "flex", alignItems: "center", justifyContent: "center",
};
const box: React.CSSProperties = {
  background: "var(--surface)", borderRadius: 10, width: 860, maxWidth: "95vw",
  maxHeight: "92vh", overflow: "auto", boxShadow: "0 10px 40px rgba(0,0,0,.3)",
};
const head: React.CSSProperties = {
  background: "var(--primary)", color: "#fff", padding: "11px 16px",
  fontSize: 15, fontWeight: 700, display: "flex", justifyContent: "space-between",
  alignItems: "center", position: "sticky", top: 0, zIndex: 1,
};
const xBtn: React.CSSProperties = {
  background: "none", border: 0, color: "#fff", cursor: "pointer", fontSize: 15,
};
const statRow: React.CSSProperties = {
  display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 10,
};
const statCard: React.CSSProperties = {
  border: "1px solid var(--border)", borderRadius: 8, padding: "10px 12px",
  background: "var(--surface-2)",
};
