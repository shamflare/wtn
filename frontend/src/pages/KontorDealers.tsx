import { useEffect, useState } from "react";
import { api } from "../api";
import ScrollTop from "../components/ScrollTop";

interface Group { id: number; name: string }
interface OpSetting { group: number | null; can_query: boolean }
interface Dealer { id: number; name: string; login_id: string; operators: Record<string, OpSetting> }

const OP_LABEL: Record<string, string> = {
  Turkcell: "Turkcell", Vodafone: "Vodafone", Avea: "Türk Telekom", Callback: "دولي",
};

export default function KontorDealers() {
  const [operators, setOperators] = useState<string[]>([]);
  const [groups, setGroups] = useState<Group[]>([]);
  const [dealers, setDealers] = useState<Dealer[]>([]);
  const [msg, setMsg] = useState("");

  async function load() {
    const r = await api.get("/kontor/dealer-settings/");
    setOperators(r.data.operators); setGroups(r.data.groups); setDealers(r.data.dealers);
  }
  useEffect(() => { load().catch(() => {}); }, []);

  async function save(dealer: number, operator: string, patch: Partial<OpSetting>) {
    setDealers((ds) => ds.map((d) => d.id === dealer
      ? { ...d, operators: { ...d.operators, [operator]: { ...d.operators[operator], ...patch } } } : d));
    await api.patch("/kontor/dealer-settings/", [{ dealer, operator, ...patch }]);
    setMsg("حُفظ"); setTimeout(() => setMsg(""), 1200);
  }

  return (
    <div style={{ padding: 16 }}>
      <ScrollTop />
      <h2 style={{ fontWeight: 800, fontSize: 20 }}>إعدادات الوكلاء — الأسعار والاستعلام</h2>
      <p style={{ color: "var(--muted)", fontSize: 13 }}>لكل وكيل: مجموعة سعره لكل شركة، وهل يُسمح له باستعلام العروض الخاصة.</p>
      {msg && <div style={{ color: "var(--ok)", fontSize: 13 }}>{msg}</div>}
      {groups.length === 0 && <div style={{ color: "var(--warn)", fontSize: 13 }}>لا مجموعات أسعار بعد — أنشئها أولاً في «مجموعات الأسعار».</div>}

      <div style={{ overflowX: "auto", marginTop: 10 }}>
        <table style={{ borderCollapse: "collapse", fontSize: 13, width: "100%" }}>
          <thead>
            <tr style={{ textAlign: "right", color: "var(--muted)" }}>
              <th style={th}>الوكيل</th>
              {operators.map((op) => <th key={op} style={th}>{OP_LABEL[op] || op}</th>)}
            </tr>
          </thead>
          <tbody>
            {dealers.map((d) => (
              <tr key={d.id} style={{ borderTop: "1px solid var(--border)" }}>
                <td style={td}><div>{d.name}</div><div style={{ fontSize: 11, color: "var(--muted)" }}>{d.login_id}</div></td>
                {operators.map((op) => {
                  const s = d.operators[op];
                  return (
                    <td key={op} style={td}>
                      <select value={s.group ?? ""} onChange={(e) => save(d.id, op, { group: e.target.value ? Number(e.target.value) : null })}
                        style={{ height: 28, maxWidth: 120 }}>
                        <option value="">— موصى —</option>
                        {groups.map((g) => <option key={g.id} value={g.id}>{g.name}</option>)}
                      </select>
                      <label style={{ display: "block", fontSize: 11, marginTop: 2 }}>
                        <input type="checkbox" checked={s.can_query} onChange={(e) => save(d.id, op, { can_query: e.target.checked })} /> استعلام
                      </label>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

const th: React.CSSProperties = { padding: "6px", fontWeight: 700, whiteSpace: "nowrap" };
const td: React.CSSProperties = { padding: "5px 6px", whiteSpace: "nowrap" };
