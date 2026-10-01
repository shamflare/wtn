import { useEffect, useState } from "react";
import { editValue, isAmountP, showPrice, toBlock } from "../unitPrice";
import { api } from "../api";
import Icon from "../components/Icon";
import { symbolOf } from "../currency";

interface Group { id: number; name: string; dealers: number }
interface Row {
  product: number; name: string; game: string;
  cost: string; price: string; profit: string;
  sale_type?: string; qty_unit?: number;
}

/**
 * مجموعات أسعار الوكيل الكبير لدكاكينه.
 *
 * صاحب المتجر يبيعه بسعر مجموعته عنده، وهو يبيع دكاكينه بمجموعاته هو: مجموعة
 * لكل شريحة، سعر لكل باقة فيها، وكل دكان في مجموعة. الفرق ربحه، ويدخل محفظته
 * لحظة طلب الدكان. والسعر دون تكلفته مرفوض — بيعٌ بخسارة صامتة.
 */
export default function AgentPrices() {
  const [groups, setGroups] = useState<Group[]>([]);
  const [active, setActive] = useState<number | null>(null);
  const [rows, setRows] = useState<Row[]>([]);
  const [cur, setCur] = useState("");
  const [edit, setEdit] = useState<number | null>(null);
  const [draft, setDraft] = useState("");
  const [q, setQ] = useState("");
  const [loading, setLoading] = useState(true);
  const [toast, setToast] = useState<{ ok: boolean; text: string } | null>(null);

  function loadGroups() {
    api.get("/agent/price-groups/").then((r) => {
      setGroups(r.data.results || []);
      setActive((a) => a ?? (r.data.results?.[0]?.id ?? null));
      setLoading(false);
    });
  }
  useEffect(() => loadGroups(), []);

  function loadPrices(id: number) {
    api.get("/agent/price-groups/prices/", { params: { group: id } })
      .then((r) => { setRows(r.data.results || []); setCur(r.data.currency || ""); });
  }
  useEffect(() => { if (active) loadPrices(active); }, [active]);

  async function addGroup() {
    const name = prompt("اسم المجموعة (مثال: ذهبية):");
    if (!name) return;
    try {
      const r = await api.post("/agent/price-groups/", { name });
      loadGroups();
      setActive(r.data.id);
    } catch (e: any) {
      setToast({ ok: false, text: e?.response?.data?.detail || "فشل الإنشاء" });
    }
  }

  async function delGroup(g: Group) {
    if (!confirm(`حذف «${g.name}»؟ دكاكينها (${g.dealers}) تعود بلا مجموعة فتشتري بسعر تكلفتك.`)) return;
    await api.delete("/agent/price-groups/", { data: { id: g.id } });
    setActive(null);
    loadGroups();
  }

  async function savePrice(product: number) {
    try {
      // بالكمية: ما كُتب سعرُ وحدة ⇐ يُحفظ لكل كتلة
      const row = rows.find((r) => r.product === product);
      await api.post("/agent/price-groups/prices/", { group: active, product, price: toBlock(draft, row) });
      setEdit(null);
      if (active) loadPrices(active);
    } catch (e: any) {
      setEdit(null);
      setToast({ ok: false, text: e?.response?.data?.detail || "تعذّر الحفظ" });
    }
  }

  const sym = symbolOf(cur);
  const shown = q ? rows.filter((r) => r.name.includes(q) || r.game.includes(q)) : rows;
  const priced = rows.filter((r) => r.price).length;

  if (loading) return <div style={{ padding: 30 }}>جارٍ التحميل...</div>;

  return (
    <div style={{ maxWidth: 1320, margin: "0 auto", padding: "22px 20px 40px" }}>
      <div className="toolbar">
        <button className="btn g" onClick={addGroup}>
          <Icon name="plus" size={15} style={{ marginInlineEnd: 5, verticalAlign: -2 }} />مجموعة جديدة
        </button>
        {groups.length > 0 && (
          <span style={{ color: "var(--muted)", fontSize: 13 }}>
            مُسعَّر: <b style={{ color: "var(--text)" }}>{priced}</b> من {rows.length} باقة
          </span>
        )}
        <input placeholder="بحث عن باقة…" value={q} onChange={(e) => setQ(e.target.value)}
          style={{ width: 220, height: 40, borderRadius: 10, marginInlineStart: "auto" }} />
      </div>

      {groups.length === 0 ? (
        <div className="card">
          <div className="card-title">
            <Icon name="dollar" size={16} style={{ color: "var(--primary)" }} /> مجموعات الأسعار
          </div>
          <div style={{ padding: 24, color: "var(--muted)", fontSize: 13.5, lineHeight: 2 }}>
            لا مجموعات بعد. أنشئ مجموعة، سعّر فيها الباقات، ثم ضع كل دكان في مجموعته من
            «الوكلاء ← قائمة الوكلاء». الدكان بلا مجموعة يشتري منك بسعر تكلفتك — بلا ربح لك.
          </div>
        </div>
      ) : (
        <>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 14 }}>
            {groups.map((g) => (
              <span key={g.id} onClick={() => setActive(g.id)} style={{
                display: "inline-flex", alignItems: "center", gap: 7,
                border: `1px solid ${active === g.id ? "var(--primary)" : "var(--border)"}`,
                background: active === g.id ? "var(--primary)" : "var(--surface)",
                color: active === g.id ? "#fff" : "var(--text)",
                borderRadius: 20, padding: "6px 14px", fontSize: 13, cursor: "pointer",
              }}>
                {g.name}
                <b style={{ opacity: 0.75, fontSize: 11 }}>{g.dealers} دكان</b>
                <button onClick={(e) => { e.stopPropagation(); delGroup(g); }} title="حذف المجموعة"
                  style={{ background: "none", border: 0, cursor: "pointer", padding: 0,
                    color: active === g.id ? "#fff" : "var(--danger)" }}>✕</button>
              </span>
            ))}
          </div>

          <div className="card">
            <div className="card-title" style={{ justifyContent: "space-between" }}>
              <span>
                <Icon name="dollar" size={16} style={{ color: "var(--primary)", marginInlineEnd: 6 }} />
                أسعار مجموعة «{groups.find((g) => g.id === active)?.name}»
              </span>
              <span style={{ fontSize: 12.5, color: "var(--muted)", fontWeight: 400 }}>
                اضغط السعر لتعديله · الفارق عن تكلفتك ربحك {cur && `· بعملة ${cur}`}
              </span>
            </div>
            <div className="table-scroll">
              <table className="grid">
                <thead>
                  <tr>
                    <th className="cell-start">الباقة</th>
                    <th>اللعبة</th>
                    <th>تكلفتي</th>
                    <th>سعر دكاكيني</th>
                    <th>ربحي</th>
                  </tr>
                </thead>
                <tbody>
                  {shown.length === 0 ? (
                    <tr><td colSpan={5} style={{ padding: 26, color: "var(--muted)" }}>لا باقات مطابقة</td></tr>
                  ) : shown.map((r) => (
                    <tr key={r.product}>
                      <td className="cell-start" style={{ fontWeight: 700 }}>
                        {r.name}
                        {isAmountP(r) && <span style={{ fontSize: 10.5, color: "#7c3aed", marginInlineStart: 6 }}>⚖ للوحدة</span>}
                      </td>
                      <td style={{ color: "var(--muted)", fontSize: 13 }}>{r.game}</td>
                      <td className="num">{showPrice(r.cost, r)} <small style={{ color: "var(--faint)" }}>{sym}</small></td>
                      <td className="num" style={{ cursor: "pointer", fontWeight: 700, color: "var(--primary-dark)" }}
                        onClick={() => { setEdit(r.product); setDraft(editValue(r.price || r.cost, r)); }}>
                        {edit === r.product ? (
                          <input autoFocus type="number" step="any" value={draft}
                            onChange={(e) => setDraft(e.target.value)}
                            onBlur={() => savePrice(r.product)}
                            onKeyDown={(e) => e.key === "Enter" && savePrice(r.product)}
                            style={{ width: 100, height: 28, direction: "ltr" }} />
                        ) : (r.price ? showPrice(r.price, r) : "—")}
                      </td>
                      <td className={`num ${r.profit ? "bal-pos" : ""}`} style={{ fontWeight: 700 }}>
                        {r.profit ? showPrice(r.profit, r) : "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}

      {toast && (
        <div onClick={() => setToast(null)} style={{
          position: "fixed", insetInlineStart: 20, bottom: 20, zIndex: 90, cursor: "pointer",
          maxWidth: 420, padding: "11px 15px", borderRadius: 9, fontSize: 13,
          background: toast.ok ? "var(--ok)" : "var(--danger)", color: "#fff",
          boxShadow: "0 6px 24px rgba(0,0,0,.25)",
        }}>{toast.text}</div>
      )}
    </div>
  );
}
