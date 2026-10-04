import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import Icon from "../components/Icon";
import ScrollTop from "../components/ScrollTop";
import { matches } from "../search";

/* باقة خطّ كما يعرضها الخادم */
interface Pkg {
  id: number; operator: string; operator_label: string;
  category: number | null; category_name: string;
  znet_id: string; name: string; details: string;
  days: number; gb: number; minutes: number;
  cost_price: string; recommended_price: string; profit: string;
  kind: "general" | "offer"; kind_label: string;
  status: string; status_label: string;
  sort_order: number;
}
const OPERATORS = [
  { code: "Turkcell", label: "Turkcell" },
  { code: "Vodafone", label: "Vodafone" },
  { code: "Avea", label: "Türk Telekom" },
  { code: "Callback", label: "دولي" },
];

export default function Kontor() {
  const [pkgs, setPkgs] = useState<Pkg[]>([]);
  const [op, setOp] = useState("Turkcell");
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);

  async function load() {
    const p = await api.get("/kontor/packages/");
    setPkgs(p.data);
  }
  useEffect(() => { load().catch(() => {}); }, []);

  const shown = useMemo(
    () => pkgs.filter((p) => p.operator === op && (!q || matches(q, p.name) || p.znet_id.includes(q))),
    [pkgs, op, q]
  );
  const countFor = (code: string) => pkgs.filter((p) => p.operator === code).length;

  async function patch(id: number, body: Partial<Pkg>) {
    // تحديث متفائل
    setPkgs((list) => list.map((p) => (p.id === id ? { ...p, ...body } as Pkg : p)));
    try {
      await api.patch(`/kontor/packages/${id}/`, body);
    } catch {
      load().catch(() => {});
    }
  }

  async function importNow() {
    setBusy(true); setMsg(null);
    try {
      const r = await api.post("/kontor/import/");
      setMsg({ ok: true, text: `تم: استُلم ${r.data.received} · جديد ${r.data.created} · محدّث ${r.data.updated}` });
      await load();
    } catch (e: any) {
      setMsg({ ok: false, text: e?.response?.data?.detail || "تعذّر الاستيراد" });
    } finally { setBusy(false); }
  }

  return (
    <div style={{ padding: 16 }}>
      <ScrollTop />
      <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap", marginBottom: 14 }}>
        <h2 style={{ margin: 0, fontSize: 20, fontWeight: 800 }}>باقات الخطوط</h2>
        <button className="btn g" onClick={importNow} disabled={busy}>
          <Icon name="api" size={15} /> {busy ? "جارٍ الاستيراد..." : "استيراد من ZNET"}
        </button>
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="بحث بالاسم أو المعرّف"
          style={{ height: 34, padding: "0 10px", marginInlineStart: "auto", minWidth: 200 }} />
      </div>

      {msg && (
        <div style={{ marginBottom: 12, padding: "8px 12px", borderRadius: 8, fontSize: 13,
          background: msg.ok ? "color-mix(in srgb, var(--ok) 14%, transparent)" : "color-mix(in srgb, var(--danger) 14%, transparent)",
          color: msg.ok ? "var(--ok)" : "var(--danger)" }}>{msg.text}</div>
      )}

      {/* تبويبات الشركات */}
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 12 }}>
        {OPERATORS.map((o) => (
          <button key={o.code} onClick={() => setOp(o.code)}
            className={op === o.code ? "btn g" : "btn"}>
            {o.label} <span style={{ opacity: 0.7 }}>({countFor(o.code)})</span>
          </button>
        ))}
      </div>

      {pkgs.length === 0 ? (
        <div style={{ padding: 30, textAlign: "center", color: "var(--muted)" }}>
          لا باقات بعد — اضغط «استيراد من ZNET» لجلبها. يتطلّب مزوّد ZNET مُعدّاً في «الألعاب ⟵ مزوّدو API».
        </div>
      ) : (
        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
            <thead>
              <tr style={{ textAlign: "right", color: "var(--muted)", borderBottom: "1px solid var(--border)" }}>
                <th style={th}>المعرّف</th><th style={th}>الفئة</th><th style={th}>الاسم</th>
                <th style={th}>الكلفة</th><th style={th}>الموصى</th><th style={th}>النوع</th><th style={th}>الحالة</th>
              </tr>
            </thead>
            <tbody>
              {shown.map((p) => (
                <tr key={p.id} style={{ borderBottom: "1px solid var(--border)" }}>
                  <td style={td}>{p.znet_id}</td>
                  <td style={{ ...td, color: "var(--muted)" }}>{p.category_name}</td>
                  <td style={td}>{p.name}</td>
                  <td style={{ ...td, whiteSpace: "nowrap" }}>{p.cost_price}</td>
                  <td style={td}>
                    <input defaultValue={p.recommended_price} style={cell}
                      onBlur={(e) => { const v = e.target.value.trim();
                        if (v !== p.recommended_price) patch(p.id, { recommended_price: v }); }} />
                  </td>
                  <td style={td}>
                    <select value={p.kind} onChange={(e) => patch(p.id, { kind: e.target.value as Pkg["kind"] })}
                      style={cell}>
                      <option value="general">عامة</option>
                      <option value="offer">عرض</option>
                    </select>
                  </td>
                  <td style={td}>
                    <select value={p.status} onChange={(e) => patch(p.id, { status: e.target.value })} style={cell}>
                      <option value="active">نشط</option>
                      <option value="passive">معطّل</option>
                      <option value="sale_paused">بيع موقوف</option>
                    </select>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

const th: React.CSSProperties = { padding: "8px 6px", fontWeight: 700 };
const td: React.CSSProperties = { padding: "6px" };
const cell: React.CSSProperties = { width: "100%", minWidth: 90, height: 30, padding: "0 6px" };
