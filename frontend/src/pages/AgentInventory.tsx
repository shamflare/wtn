import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import DateRange, { rangeText, TODAY, type Dates } from "../components/DateRange";
import Icon from "../components/Icon";
import { money, symbolOf } from "../currency";

/**
 * جرد الوكيل الكبير: ما له وما عليه **الآن**، وربحه في الفترة المختارة (اليوم افتراضاً).
 *
 * كل بند موقّع — الموجب له والسالب عليه — فالمجموع صافي رأس ماله مباشرةً:
 * رصيده لدى المتجر + حساباته ونقده − ما قبضه من دكاكينه ولم يقدّم مقابله.
 */
export default function AgentInventory() {
  const [d, setD] = useState<any>(null);
  const [dates, setDates] = useState<Dates>(TODAY);

  useEffect(() => {
    const params: Record<string, string> = {};
    if (dates.date_from) params.date_from = dates.date_from;
    if (dates.date_to) params.date_to = dates.date_to;
    api.get("/agent/inventory/", { params }).then((r) => setD(r.data));
  }, [dates]);

  if (!d) return <div style={{ padding: 30 }}>جارٍ التحميل...</div>;
  const sym = symbolOf(d.currency);
  const tone = (v: string) => (Number(v) < 0 ? "bal-neg" : Number(v) > 0 ? "bal-pos" : "");

  return (
    <div style={{ maxWidth: 1100, margin: "0 auto", padding: "22px 20px 40px" }}>
      <h2 style={{ fontSize: 20, color: "var(--primary-dark)", marginBottom: 12 }}>الجرد — ما لي وما عليّ الآن</h2>

      <div className="summary">
        <Stat icon="chart" label="صافي رأس المال" value={`${money(d.totals.total)} ${sym}`} cls={tone(d.totals.total)} />
        <Stat icon="arrowUp" label="ما لي" value={`${money(d.totals.assets)} ${sym}`} cls="bal-pos" />
        <Stat icon="arrowDown" label="ما عليّ" value={`${money(d.totals.liabilities)} ${sym}`} cls="bal-neg" />
        <Stat icon="dollar" label={`ربحي — ${rangeText(dates)}`} value={`${money(d.totals.profit)} ${sym}`} cls="bal-pos" />
      </div>

      <div style={{ display: "flex", gap: 10, alignItems: "center", margin: "14px 0", flexWrap: "wrap" }}>
        <span style={{ fontSize: 12.5, color: "var(--muted)" }}>فترة الربح:</span>
        <DateRange value={dates} onChange={setDates} />
      </div>

      <div className="card">
        <div className="table-scroll">
          <table className="grid">
            <thead><tr><th className="cell-start">البند</th><th>المبلغ ({sym})</th><th className="cell-start">التفصيل</th></tr></thead>
            <tbody>
              {d.lines.map((l: any) => (
                <tr key={l.key}>
                  <td className="cell-start" style={{ fontWeight: 700 }}>{l.name}</td>
                  <td className={`num ${tone(l.amount)}`} style={{ fontWeight: 800, fontSize: 15 }}>{money(l.amount)}</td>
                  <td className="cell-start" style={{ fontSize: 12.5, color: "var(--muted)", whiteSpace: "normal" }}>{l.note}</td>
                </tr>
              ))}
            </tbody>
            <tfoot>
              <tr style={{ background: "#f5c518", fontWeight: 800 }}>
                <td className="cell-start">الصافي</td>
                <td className="num">{money(d.totals.total)}</td>
                <td></td>
              </tr>
            </tfoot>
          </table>
        </div>
      </div>

      {d.pending_deposits.count > 0 && (
        <div className="card" style={{ marginTop: 14, padding: "12px 16px", fontSize: 13.5 }}>
          <Icon name="warning" size={15} style={{ color: "#b45309", marginInlineEnd: 6, verticalAlign: -2 }} />
          <b>{d.pending_deposits.count}</b> إيداع من دكاكينك بانتظار قرارك بقيمة{" "}
          <b>{money(d.pending_deposits.amount)} {sym}</b> — لا يدخل الجرد قبل قبوله.{" "}
          <Link to="/bigagent/payments" style={{ color: "var(--primary)" }}>متابعة الدفع ←</Link>
        </div>
      )}

      <div style={{ fontSize: 12, color: "var(--muted)", marginTop: 10, lineHeight: 1.8 }}>
        * رصيد الدكان الموجب مالٌ قبضتَه منه ولم يصرفه بعد — فهو عليك ويُطرح. والسالب دَينٌ لك عليه.
        أرصدة «حساباتي» تُحدَّث من صفحة «حساباتي».
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
