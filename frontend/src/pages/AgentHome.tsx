import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import Icon from "../components/Icon";
import { symbolOf } from "../currency";

/**
 * رئيسية الوكيل الكبير.
 *
 * لا يشحن من هنا — يدير دكاكينه. صفٌّ لماله (رصيده وما يتاح له وأرصدة دكاكينه)
 * وصفٌّ ليومه (طلبات دكاكينه الناجحة اليوم ومبيعاته وربحه — ألعاباً وموبايل).
 */
export default function AgentHome() {
  const [s, setS] = useState<any>(null);
  const [dealers, setDealers] = useState<any[]>([]);

  useEffect(() => {
    api.get("/agent/summary/").then((r) => setS(r.data));
    api.get("/agent/dealers/").then((r) => setDealers(r.data.results || []));
  }, []);

  const money = (v: string | number) =>
    Number(v).toLocaleString("en-US", { minimumFractionDigits: 2 });
  const balCls = (v: number) => (v < 0 ? "bal-neg" : v > 0 ? "bal-pos" : "bal-zero");

  if (!s) return <div style={{ padding: 30 }}>جارٍ التحميل...</div>;
  const cur = symbolOf(s.currency || "");
  const debtors = dealers.filter((d) => Number(d.balance) < 0);

  return (
    <div style={{ maxWidth: 1320, margin: "0 auto", padding: "22px 20px 40px" }}>
      <div className="summary">
        <Stat icon="wallet" label="رصيدي" value={`${money(s.balance)} ${cur}`}
          cls={balCls(Number(s.balance))} />
        <Stat icon="dollar" label="المتاح للصرف" value={`${money(s.available)} ${cur}`} />
        <Stat icon="users" label="دكاكيني" value={s.dealers} />
        <Stat icon="wallet" label="أرصدة دكاكيني" value={`${money(s.dealers_balance)} ${cur}`} />
      </div>
      <div className="summary" style={{ marginTop: 12 }}>
        <Stat icon="chart" label="طلبات اليوم (الناجحة)" value={s.today.orders} />
        <Stat icon="cart" label="مبيعات اليوم" value={`${money(s.today.sales)} ${cur}`} />
        <Stat icon="dollar" label="ربح اليوم" value={`${money(s.today.profit)} ${cur}`} cls="bal-pos" />
        <Stat icon="chart" label="ربحي منذ البداية" value={`${money(s.profit)} ${cur}`} cls="bal-pos" />
      </div>

      {s.deposits_pending > 0 && (
        <Link to="/bigagent/payments" className="card" style={{ display: "block", marginTop: 14, padding: "12px 16px",
          fontSize: 13.5, color: "var(--text)", textDecoration: "none" }}>
          <Icon name="card" size={15} style={{ color: "#b45309", marginInlineEnd: 6, verticalAlign: -2 }} />
          <b>{s.deposits_pending}</b> إيداع من دكاكينك بانتظار قرارك — <span style={{ color: "var(--primary)" }}>متابعة الدفع ←</span>
        </Link>
      )}

      <div className="card" style={{ marginTop: 18 }}>
        <div className="card-title" style={{ justifyContent: "space-between" }}>
          <span>
            <Icon name="users" size={16} style={{ color: "var(--primary)", marginInlineEnd: 6 }} />
            دكاكيني
          </span>
          <Link to="/bigagent/dealers" style={{ fontSize: 13, color: "var(--primary)" }}>
            إدارة الدكاكين ←
          </Link>
        </div>
        <div className="table-scroll">
          <table className="grid">
            <thead>
              <tr><th>الرقم</th><th className="cell-start">الاسم</th><th>الرصيد</th><th>الحالة</th></tr>
            </thead>
            <tbody>
              {dealers.length === 0 ? (
                <tr><td colSpan={4} style={{ padding: 26, color: "var(--muted)" }}>
                  لا دكاكين بعد — أضف أوّل دكان من «الوكلاء ← قائمة الوكلاء».
                </td></tr>
              ) : dealers.slice(0, 8).map((d) => (
                <tr key={d.id}>
                  <td className="num" style={{ color: "var(--faint)", fontSize: 12.5 }}>{d.login_id}</td>
                  <td className="cell-start" style={{ fontWeight: 700 }}>{d.name}</td>
                  <td className={`num ${balCls(Number(d.balance))}`}>{money(d.balance)} {cur}</td>
                  <td>
                    <span style={{
                      display: "inline-block", width: 14, height: 14, borderRadius: "50%",
                      border: "2px solid rgba(0,0,0,.12)",
                      background: d.status === "active" ? "var(--ok)" : "var(--danger)",
                    }} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {debtors.length > 0 && (
        <div className="card" style={{ marginTop: 16 }}>
          <div className="card-title">
            <Icon name="warning" size={16} style={{ color: "var(--danger)" }} />
            {" "}دكاكين برصيد سالب ({debtors.length})
          </div>
          <div style={{ padding: "12px 16px", fontSize: 13.5, lineHeight: 2 }}>
            {debtors.map((d) => (
              <span key={d.id} style={{ marginInlineEnd: 16 }}>
                {d.name} <b className="num bal-neg">{money(d.balance)} {cur}</b>
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function Stat({ icon, label, value, cls }:
  { icon: string; label: string; value: any; cls?: string }) {
  return (
    <div className="stat">
      <div className="label">
        <Icon name={icon} size={15} style={{ color: "var(--primary)" }} /> {label}
      </div>
      <div className={`value num ${cls || ""}`}>{value}</div>
      <span className="spark" />
    </div>
  );
}
