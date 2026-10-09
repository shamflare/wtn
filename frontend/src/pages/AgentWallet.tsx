import { useEffect, useState } from "react";
import { api } from "../api";
import DateRange, { rangeText, TODAY, type Dates } from "../components/DateRange";
import Icon from "../components/Icon";
import Pager from "../components/Pager";
import TopUp from "../components/TopUp";
import { money, symbolOf } from "../currency";
import "./store.css";

/**
 * محفظة الوكيل الكبير — رصيده لدى المتجر وحدّه الائتماني وكشف حركاته، وشحن
 * رصيده من المتجر بطرق دفع المتجر (كأي وكيل). كل الأرقام بعملته.
 *
 * والكشف يفتح على اليوم: بيع دكاكينه وشراؤه من المتجر وحوالاته إليهم كلّها هنا.
 */
export default function AgentWallet() {
  const [data, setData] = useState<any>(null);
  const [dates, setDates] = useState<Dates>(TODAY);
  const [kind, setKind] = useState("all");
  const [topup, setTopup] = useState(false);
  const [page, setPage] = useState(1);

  function load() {
    const params: Record<string, string> = { type: kind, page: String(page) };
    if (dates.date_from) params.date_from = dates.date_from;
    if (dates.date_to) params.date_to = dates.date_to;
    api.get("/store/wallet/", { params }).then((r) => setData(r.data)).catch(() => setData({ results: [] }));
  }
  useEffect(() => { load(); }, [dates, kind, page]);

  const sym = symbolOf(data?.currency || "");
  const counts: Record<string, number> = data?.counts || {};
  const types: { key: string; label: string }[] = [{ key: "all", label: "الكل" }, ...(data?.types || [])]
    .filter((t: any) => t.key === "all" || t.key === kind || counts[t.key]);

  return (
    <div style={{ maxWidth: 1320, margin: "0 auto", padding: "22px 20px 40px" }}>
      <div className="summary">
        <Stat icon="wallet" label="رصيدي" value={data ? `${money(data.balance)} ${sym}` : "—"}
          cls={Number(data?.balance) < 0 ? "bal-neg" : "bal-pos"} />
        <Stat icon="dollar" label="المتاح للصرف" value={data ? `${money(data.available)} ${sym}` : "—"} />
        <Stat icon="card" label="الحدّ الائتماني" value={data ? `${money(Math.abs(Number(data.credit_limit)))} ${sym}` : "—"} />
      </div>

      <div style={{ display: "flex", gap: 10, margin: "16px 0", flexWrap: "wrap" }}>
        <button className="btn g" onClick={() => setTopup((v) => !v)}>
          <Icon name="plusCircle" size={16} style={{ marginInlineEnd: 6, verticalAlign: -3 }} />
          {topup ? "إخفاء شحن الرصيد" : "شحن رصيدي من المتجر"}
        </button>
        <span style={{ fontSize: 12.5, color: "var(--muted)", alignSelf: "center" }}>
          رصيدك يُخصم منه سعر المتجر عند كل طلب لدكاكينك، ويُضاف إليه ما يدفعه دكانك لك.
        </span>
      </div>

      {topup && (
        <div className="ag" style={{ borderRadius: 16, padding: 18, marginBottom: 18 }}>
          <TopUp onDone={load} />
        </div>
      )}

      <div className="card">
        <div className="card-title">
          <Icon name="receipt" size={16} style={{ color: "var(--primary)" }} /> كشف حركات محفظتي
        </div>
        <div style={{ padding: "10px 14px", display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
          <DateRange value={dates} onChange={(d) => { setDates(d); setPage(1); }} />
          <span style={{ fontSize: 12.5, color: "var(--muted)" }}>
            الفترة: <b style={{ color: "var(--text)" }}>{rangeText(dates)}</b>
          </span>
        </div>
        <div style={{ padding: "0 14px 10px", display: "flex", gap: 6, flexWrap: "wrap" }}>
          {types.map((t) => (
            <button key={t.key} onClick={() => { setKind(t.key); setPage(1); }}
              style={{ border: "1px solid var(--border)", borderRadius: 999, padding: "4px 12px", cursor: "pointer",
                fontSize: 12.5, background: kind === t.key ? "var(--primary)" : "var(--surface)",
                color: kind === t.key ? "#fff" : "var(--text)" }}>
              {t.label}{counts[t.key] ? ` (${counts[t.key]})` : ""}
            </button>
          ))}
        </div>
        <div className="table-scroll">
          <table className="grid">
            <thead>
              <tr><th>التاريخ</th><th>النوع</th><th>المبلغ</th><th>الرصيد قبل</th><th>الرصيد بعد</th><th className="cell-start">البيان</th></tr>
            </thead>
            <tbody>
              {!data ? (
                <tr><td colSpan={6} style={{ padding: 26, color: "var(--muted)" }}>جارٍ التحميل...</td></tr>
              ) : !data.results?.length ? (
                <tr><td colSpan={6} style={{ padding: 26, color: "var(--muted)" }}>لا حركات في هذه الفترة</td></tr>
              ) : data.results.map((t: any) => (
                <tr key={t.id}>
                  <td style={{ color: "var(--muted)", fontSize: 12.5 }}>{t.created_at}</td>
                  <td style={{ fontSize: 12.5 }}>{t.type_label}</td>
                  <td className={`num ${Number(t.amount) < 0 ? "bal-neg" : "bal-pos"}`} style={{ fontWeight: 700 }}>{money(t.amount)}</td>
                  <td className="num" style={{ color: "var(--muted)" }}>{money(t.balance_before)}</td>
                  <td className="num">{money(t.balance_after)}</td>
                  <td className="cell-start" style={{ fontSize: 12.5, color: "var(--muted)" }}>{t.note}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div style={{ padding: "0 12px" }}><Pager paging={data?.paging} onPage={setPage} /></div>
      </div>
    </div>
  );
}

function Stat({ icon, label, value, cls }: { icon: string; label: string; value: string; cls?: string }) {
  return (
    <div className="stat">
      <div className="label"><Icon name={icon} size={15} style={{ color: "var(--primary)" }} /> {label}</div>
      <div className={`value num ${cls || ""}`}>{value}</div>
      <span className="spark" />
    </div>
  );
}
