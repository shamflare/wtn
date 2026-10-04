import { useEffect, useState } from "react";
import { api } from "../api";
import ScrollTop from "../components/ScrollTop";

interface Group { id: number; name: string; dealer_count?: number }
interface Cell { price: string; linked: boolean; mode: string; value: string; round: boolean }
interface Row {
  id: number; name: string; category: string; znet_id: string;
  cost_price: string; recommended_price: string; prices: Record<string, Cell>;
}

const OPERATORS = [
  { code: "Turkcell", label: "Turkcell" },
  { code: "Vodafone", label: "Vodafone" },
  { code: "Avea", label: "Türk Telekom" },
  { code: "Callback", label: "دولي" },
];

export default function KontorPrices() {
  const [op, setOp] = useState("Turkcell");
  const [groups, setGroups] = useState<Group[]>([]);
  const [rows, setRows] = useState<Row[]>([]);
  const [newGroup, setNewGroup] = useState("");
  const [msg, setMsg] = useState("");

  async function load() {
    const r = await api.get(`/kontor/price-matrix/?operator=${op}`);
    setGroups(r.data.groups); setRows(r.data.rows);
  }
  useEffect(() => { load().catch(() => {}); }, [op]);

  async function addGroup() {
    if (!newGroup.trim()) return;
    await api.post("/kontor/price-groups/", { name: newGroup.trim() });
    setNewGroup(""); load();
  }
  async function delGroup(id: number) {
    if (!window.confirm("حذف المجموعة؟ سيفقد وكلاؤها تسعيرها لهذه الشركة.")) return;
    await api.delete(`/kontor/price-groups/${id}/`); load();
  }

  async function setCell(pkg: number, group: number, price: string) {
    await api.post("/kontor/set-price/", { package: pkg, group, price });
    setRows((rs) => rs.map((r) => r.id === pkg
      ? { ...r, prices: { ...r.prices, [group]: { ...r.prices[group], price, linked: false } } } : r));
  }

  async function bulk(group: number, mode: string, value: string, round: boolean) {
    await api.post("/kontor/bulk-price/", { group, operator: op, mode, value, round });
    setMsg("تم تطبيق القاعدة"); load();
  }
  async function bulkRecommended(group: number) {
    await api.post("/kontor/bulk-price/", { group, operator: op, to_recommended: true });
    setMsg("ضُبطت على السعر الموصى"); load();
  }

  return (
    <div style={{ padding: 16 }}>
      <ScrollTop />
      <h2 style={{ fontWeight: 800, fontSize: 20 }}>مجموعات أسعار الخطوط</h2>

      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", margin: "10px 0", alignItems: "center" }}>
        <input value={newGroup} onChange={(e) => setNewGroup(e.target.value)} placeholder="اسم مجموعة جديدة"
          style={{ height: 32, padding: "0 8px" }} />
        <button className="btn g" onClick={addGroup}>➕ مجموعة</button>
        {groups.map((g) => (
          <span key={g.id} style={{ border: "1px solid var(--border)", borderRadius: 14, padding: "3px 10px", fontSize: 12 }}>
            {g.name} <button onClick={() => delGroup(g.id)} style={{ border: 0, background: "none", color: "var(--danger)", cursor: "pointer" }}>✕</button>
          </span>
        ))}
      </div>

      <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 10 }}>
        {OPERATORS.map((o) => (
          <button key={o.code} className={op === o.code ? "btn g" : "btn"} onClick={() => setOp(o.code)}>{o.label}</button>
        ))}
      </div>
      {msg && <div style={{ color: "var(--ok)", fontSize: 13, marginBottom: 8 }}>{msg}</div>}

      {groups.length === 0 ? (
        <div style={{ color: "var(--muted)", padding: 20 }}>أضف مجموعة أسعار لتبدأ التسعير.</div>
      ) : (
        <div style={{ overflowX: "auto" }}>
          <table style={{ borderCollapse: "collapse", fontSize: 13, width: "100%" }}>
            <thead>
              <tr style={{ textAlign: "right", color: "var(--muted)" }}>
                <th style={th}>الباقة</th><th style={th}>الكلفة</th><th style={th}>الموصى</th>
                {groups.map((g) => <th key={g.id} style={th}>{g.name}</th>)}
              </tr>
              <tr>
                <td style={td} colSpan={3}></td>
                {groups.map((g) => <BulkCell key={g.id} onRule={(m, v, r) => bulk(g.id, m, v, r)} onRec={() => bulkRecommended(g.id)} />)}
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id} style={{ borderTop: "1px solid var(--border)" }}>
                  <td style={td}><div>{r.name}</div><div style={{ fontSize: 11, color: "var(--muted)" }}>{r.category}</div></td>
                  <td style={td}>{r.cost_price}</td>
                  <td style={td}>{r.recommended_price}</td>
                  {groups.map((g) => {
                    const c = r.prices[g.id] || { price: "" } as Cell;
                    return (
                      <td key={g.id} style={td}>
                        <input defaultValue={c.price} key={c.price}
                          onBlur={(e) => { const v = e.target.value.trim(); if (v && v !== c.price) setCell(r.id, g.id, v); }}
                          style={{ width: 80, height: 28, padding: "0 4px",
                            background: c.linked ? "color-mix(in srgb, var(--info) 10%, transparent)" : undefined }} />
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function BulkCell({ onRule, onRec }: { onRule: (mode: string, value: string, round: boolean) => void; onRec: () => void }) {
  const [v, setV] = useState("");
  const [mode, setMode] = useState("percent");
  const [round, setRound] = useState(false);
  return (
    <td style={{ ...td, verticalAlign: "top" }}>
      <div style={{ display: "flex", gap: 2, flexWrap: "wrap", alignItems: "center" }}>
        <input value={v} onChange={(e) => setV(e.target.value)} placeholder="قيمة" style={{ width: 46, height: 26 }} />
        <select value={mode} onChange={(e) => setMode(e.target.value)} style={{ height: 26 }}>
          <option value="percent">%</option><option value="fixed">+</option>
        </select>
        <label style={{ fontSize: 10 }}><input type="checkbox" checked={round} onChange={(e) => setRound(e.target.checked)} />↑</label>
        <button className="btn" style={{ height: 24, fontSize: 11 }} onClick={() => v && onRule(mode, v, round)}>طبّق</button>
        <button className="btn" style={{ height: 24, fontSize: 11 }} onClick={onRec} title="ضبط على السعر الموصى">موصى</button>
      </div>
    </td>
  );
}

const th: React.CSSProperties = { padding: "6px", fontWeight: 700, whiteSpace: "nowrap" };
const td: React.CSSProperties = { padding: "5px 6px", whiteSpace: "nowrap" };
