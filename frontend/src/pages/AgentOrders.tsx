import { Fragment, useEffect, useState } from "react";
import { api } from "../api";
import DateRange, { rangeText, TODAY, type Dates } from "../components/DateRange";
import Icon from "../components/Icon";
import { money, symbolOf } from "../currency";

const STATUSES: [string, string, string][] = [
  ["all", "#7d8f94", "الكل"], ["pending", "#e8b013", "قيد الانتظار"],
  ["success", "#35c245", "ناجح"], ["cancelled", "#dd4444", "ملغى"],
];
const DOT: Record<string, string> = { pending: "wait", success: "ok", cancelled: "err" };

/**
 * طلبات دكاكين الوكيل الكبير — `kind` يحصرها في الألعاب أو الموبايل.
 *
 * ليست طلباته هو — هو لا يشحن من الموقع. هذه ما اشتراه دكاكينه منه: بكم دفعوا،
 * وبكم اشتراه هو من المتجر، وكم ربح. تفتح على اليوم، والملاحظات (ملاحظة المزوّد
 * وملاحظة الإدارة) في تفاصيل كل طلب.
 */
export default function AgentOrders({ kind }: { kind: "games" | "mobile" }) {
  const [rows, setRows] = useState<any[]>([]);
  const [counts, setCounts] = useState<Record<string, number>>({});
  const [totals, setTotals] = useState<{ sales: string; cost: string; profit: string } | null>(null);
  const [cur, setCur] = useState("");
  const [status, setStatus] = useState("all");
  const [dates, setDates] = useState<Dates>(TODAY);
  const [dealer, setDealer] = useState("");
  const [dealers, setDealers] = useState<{ id: number; name: string }[]>([]);
  const [q, setQ] = useState("");
  const [open, setOpen] = useState<string | number | null>(null);
  const [loading, setLoading] = useState(true);
  const mobile = kind === "mobile";

  function load(silent = false) {
    if (!silent) setLoading(true);
    const params: Record<string, string> = { status, kind };
    if (dates.date_from) params.date_from = dates.date_from;
    if (dates.date_to) params.date_to = dates.date_to;
    if (dealer) params.dealer = dealer;
    if (q.trim()) params.q = q.trim();
    return api.get("/agent/orders/", { params })
      .then((r) => {
        setRows(r.data.results || []); setCounts(r.data.counts || {});
        setTotals(r.data.totals); setCur(r.data.currency || "");
      })
      .finally(() => setLoading(false));
  }
  useEffect(() => { load(); }, [status, dates, dealer, kind]);
  useEffect(() => {
    api.get("/agent/dealers/").then((r) => setDealers(r.data.results || [])).catch(() => {});
  }, []);

  // ما دام طلبٌ ينتظر نتابعه بهدوء حتى تتبدّل حالته
  const waiting = rows.some((o) => o.status === "pending");
  useEffect(() => {
    if (!waiting) return;
    const t = setInterval(() => load(true), 15_000);
    return () => clearInterval(t);
  }, [waiting, status, dates, dealer, q, kind]);

  const sym = symbolOf(cur);

  return (
    <div style={{ maxWidth: 1320, margin: "0 auto", padding: "22px 20px 40px" }}>
      <div className="card" style={{ marginBottom: 14 }}>
        <div className="card-title">
          <Icon name={mobile ? "phone" : "games"} size={16} style={{ color: "var(--primary)" }} />
          {mobile ? "طلبات الموبايل — دكاكيني" : "طلبات الألعاب — دكاكيني"}
          <span style={{ marginInlineStart: "auto", display: "inline-flex", gap: 6, alignItems: "center" }}>
            {STATUSES.map(([k, c, t]) => (
              <button key={k} title={`${t}${counts[k] ? ` — ${counts[k]}` : ""}`} onClick={() => setStatus(k)}
                style={{ ...qdot, background: c, outline: status === k ? "2px solid var(--primary)" : "none" }} />
            ))}
          </span>
        </div>
        <div style={{ padding: "10px 14px", display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
          <DateRange value={dates} onChange={setDates} />
          <select value={dealer} onChange={(e) => setDealer(e.target.value)} style={{ height: 36, minWidth: 150 }}>
            <option value="">كل الدكاكين</option>
            {dealers.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
          </select>
          <form onSubmit={(e) => { e.preventDefault(); load(); }} style={{ display: "flex", gap: 6, flex: 1, minWidth: 220 }}>
            <input placeholder={mobile ? "رقم الخط أو الباقة أو الإيصال…" : "رقم الإيصال أو معرّف اللاعب أو الباقة…"}
              value={q} onChange={(e) => setQ(e.target.value)} style={{ flex: 1, height: 36 }} />
            <button className="btn g" style={{ height: 36 }}><Icon name="search" size={14} /></button>
          </form>
        </div>
        <div style={{ padding: "0 14px 10px", fontSize: 12.5, color: "var(--muted)" }}>
          الفترة: <b style={{ color: "var(--text)" }}>{rangeText(dates)}</b> · المبالغ بـ<b>{sym}</b>
        </div>
      </div>

      <div className="summary" style={{ marginBottom: 14 }}>
        <Stat icon="chart" label="عدد الطلبات" value={String(counts.all || 0)} />
        <Stat icon="wallet" label="مبيعاتي (الناجحة)" value={`${money(totals?.sales || 0)} ${sym}`} />
        <Stat icon="cart" label="تكلفتي من المتجر" value={`${money(totals?.cost || 0)} ${sym}`} />
        <Stat icon="dollar" label="ربحي" value={`${money(totals?.profit || 0)} ${sym}`} cls="bal-pos" />
      </div>

      <div className="card">
        <div className="table-scroll">
          <table className="grid">
            <thead>
              <tr>
                <th>رقم الإيصال</th>
                <th className="cell-start">الدكان</th>
                <th className="cell-start">الباقة</th>
                <th>{mobile ? "الشركة" : "اللعبة"}</th>
                <th>{mobile ? "رقم الخط" : "معرّف اللاعب"}</th>
                <th>دفع لي</th>
                <th>تكلفتي</th>
                <th>ربحي</th>
                <th>الحالة</th>
                <th>التاريخ</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan={11} style={{ padding: 30, color: "var(--muted)" }}>جارٍ التحميل...</td></tr>
              ) : rows.length === 0 ? (
                <tr><td colSpan={11} style={{ padding: 30, color: "var(--muted)" }}>لا طلبات في هذه الفترة</td></tr>
              ) : rows.map((o) => {
                const note = o.provider_note || o.dealer_note;
                return (
                  <Fragment key={o.id}>
                    <tr className={o.status === "pending" ? "row-wait" : ""} style={{ cursor: "pointer" }}
                      onClick={() => setOpen(open === o.id ? null : o.id)}>
                      <td className="num" style={{ color: "var(--faint)", fontSize: 12.5 }}>{o.receipt_no}</td>
                      <td className="cell-start" style={{ fontWeight: 700 }}>{o.dealer_name}</td>
                      <td className="cell-start">
                        {o.product_name}{o.quantity > 1 && <span style={{ color: "var(--muted)" }}> × {o.quantity}</span>}
                        {note && <Icon name="chat" size={13} style={{ color: "var(--primary)", marginInlineStart: 6, verticalAlign: -2 }} />}
                      </td>
                      <td style={{ color: "var(--muted)", fontSize: 13 }}>{o.game_name}</td>
                      <td className="num" style={{ fontSize: 12.5 }}>{o.player_id || "—"}</td>
                      <td className="num sell">{money(o.sell_price)}</td>
                      <td className="num buy" style={{ color: "var(--muted)" }}>{money(o.cost)}</td>
                      <td className="num bal-pos" style={{ fontWeight: 700 }}>
                        {o.status === "success" ? money(o.profit) : <span style={{ color: "var(--faint)" }}>—</span>}
                      </td>
                      <td><span className={`stdot ${DOT[o.status] || "wait"}`} title={o.status_label} /></td>
                      <td style={{ color: "var(--muted)", fontSize: 12.5 }}>{o.created_at}</td>
                      <td style={{ color: "var(--muted)", fontSize: 11 }}>{open === o.id ? "▲" : "▼"}</td>
                    </tr>
                    {open === o.id && (
                      <tr><td colSpan={11} className="cell-start" style={{ background: "var(--row-alt)", lineHeight: 2, fontSize: 13 }}>
                        <div><span style={{ color: "var(--muted)" }}>الحالة:</span> <b>{o.status_label}</b></div>
                        {o.pin_result && <div><span style={{ color: "var(--muted)" }}>الكود:</span> <b style={{ direction: "ltr", display: "inline-block" }}>{o.pin_result}</b></div>}
                        <div><span style={{ color: "var(--muted)" }}>ملاحظة المزوّد:</span> <b>{o.provider_note || "—"}</b></div>
                        {o.dealer_note && <div><span style={{ color: "var(--muted)" }}>ملاحظة الإدارة:</span> <b>{o.dealer_note}</b></div>}
                      </td></tr>
                    )}
                  </Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
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

const qdot: React.CSSProperties = {
  width: 18, height: 18, borderRadius: "50%", border: "2px solid rgba(255,255,255,.7)", cursor: "pointer",
};
