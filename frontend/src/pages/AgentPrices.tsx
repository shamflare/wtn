import { Fragment, useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api";
import Icon from "../components/Icon";
import ProductPicker, { type PickerProduct } from "../components/ProductPicker";
import ScrollTop from "../components/ScrollTop";
import { symbolOf } from "../currency";
import { matches } from "../search";
import { editValue, isAmountP, showPrice, toBlock } from "../unitPrice";

interface Margin { mode: "percent" | "fixed"; value: string; round?: boolean }
interface Cell { price: string; margin: Margin | null }
interface Row { id: number; name: string; cost: string; sale_type?: string; qty_unit?: number; prices: Record<string, Cell | null> }
interface Block { name: string; products: Row[] }
interface Group { id: number; name: string; dealers: number }

function marginLabel(m: Margin): string {
  const v = Number(m.value);
  const n = Number.isInteger(v) ? String(v) : String(Number(v.toFixed(4)));
  return (m.mode === "percent" ? `${n}%` : `+${n}`) + (m.round ? "↑" : "");
}

/**
 * مجموعات أسعار الوكيل الكبير لدكاكينه — مصفوفة كمصفوفة صاحب المتجر.
 *
 * `section` يختار الألعاب أو الموبايل؛ المجموعات نفسها للقسمين (الدكان في مجموعة
 * واحدة عند وكيله). «تكلفتي» ما يدفعه الوكيل للمتجر، والخلية الفارغة = يبيع
 * دكانه بتكلفته (بلا ربح). كل الأرقام بعملة الوكيل.
 */
export default function AgentPrices({ section }: { section: "games" | "mobile" }) {
  const [groups, setGroups] = useState<Group[]>([]);
  const [blocks, setBlocks] = useState<Block[]>([]);
  const [cur, setCur] = useState("");
  const [loading, setLoading] = useState(true);
  // `orig`: قيمة الخلية عند فتحها — حفظٌ بلا تغيير (أو بعد Escape) لا يُرسل شيئاً
  const [editing, setEditing] = useState<{ p: number; g: number; orig: string } | null>(null);
  const [draft, setDraft] = useState("");
  const cancelled = useRef(false);   // Escape: لا يحفظ blur الذي يليه شيئاً
  const [dialog, setDialog] = useState<"bulk" | "delete" | null>(null);
  const [toast, setToast] = useState<{ ok: boolean; text: string } | null>(null);
  const [q, setQ] = useState("");
  const mobile = section === "mobile";

  function load() {
    setLoading(true);
    api.get("/agent/price-matrix/", { params: { section } })
      .then((r) => { setGroups(r.data.groups); setBlocks(r.data.blocks); setCur(r.data.currency || ""); })
      .finally(() => setLoading(false));
  }
  useEffect(() => load(), [section]);

  function say(ok: boolean, text: string) {
    setToast({ ok, text });
    setTimeout(() => setToast(null), 6000);
  }

  const allRows = useMemo(() => blocks.flatMap((b) => b.products.map((p) => ({ ...p, block: b.name }))), [blocks]);
  const picker = useMemo<PickerProduct[]>(() => allRows.map((p) => ({ id: p.id, name: p.name, game_name: p.block })), [allRows]);
  const costOf = useMemo(() => new Map(allRows.map((p) => [p.id, p.cost])), [allRows]);
  const rowOf = (id: number) => allRows.find((p) => p.id === id);

  async function createGroup() {
    const name = prompt("اسم المجموعة الجديدة (مثال: الذهبية):");
    if (!name?.trim()) return;
    try {
      await api.post("/agent/price-groups/", { name: name.trim() });
      load();
    } catch (e: any) { say(false, e?.response?.data?.detail || "تعذّر الإنشاء"); }
  }

  async function saveCell(productId: number, groupId: number) {
    if (cancelled.current) { cancelled.current = false; return; }
    const typed = draft.trim();
    const unchanged = editing?.orig === typed;
    setEditing(null);
    if (unchanged) return;
    const row = rowOf(productId);
    const value = typed === "" ? "" : toBlock(typed, row);
    try {
      await api.post("/agent/set-price/", { section, group: groupId, product: productId, price: value });
      load();
    } catch (e: any) { say(false, e?.response?.data?.detail || "تعذّر الحفظ"); }
  }

  const shown = q.trim()
    ? blocks.map((b) => matches(q, b.name) ? b : { ...b, products: b.products.filter((p) => matches(q, p.name, p.id)) })
      .filter((b) => b.products.length > 0)
    : blocks;
  const sym = symbolOf(cur);

  if (loading) return <div style={{ padding: 30 }}>جارٍ التحميل...</div>;

  return (
    <div style={{ padding: 16 }}>
      <h2 style={{ fontSize: 20, color: "var(--primary-dark)", marginBottom: 12 }}>
        مجموعات الأسعار — {mobile ? "الموبايل" : "الألعاب"}
        <span style={{ fontSize: 13, color: "var(--muted)", fontWeight: 400, marginInlineStart: 8 }}>
          (الأسعار بـ{sym})
        </span>
      </h2>

      <div style={toolbar}>
        <button className="btn g" onClick={createGroup}><Icon name="plus" size={15} style={ib} />إنشاء مجموعة</button>
        <button className="btn" disabled={groups.length === 0} onClick={() => setDialog("bulk")}>
          <Icon name="chart" size={15} style={ib} />تسعير جماعي
        </button>
        <button className="btn r" disabled={groups.length === 0} onClick={() => setDialog("delete")}>
          <Icon name="trash" size={15} style={ib} />حذف مجموعة
        </button>
        <input placeholder={mobile ? "بحث: شركة أو فئة أو باقة..." : "بحث سريع: لعبة أو باقة أو Id..."}
          value={q} onChange={(e) => setQ(e.target.value)} style={{ width: 260, marginInlineStart: "auto" }} />
      </div>
      <div style={note}>
        <b>تكلفتي</b> = ما تدفعه أنت للمتجر. اضغط أي خلية لتسعيرها لدكاكين تلك المجموعة؛ الخلية
        الفارغة (—) تعني أن دكانها يشتري <b>بتكلفتك</b> بلا ربح لك. ضع كل دكان في مجموعته من
        «الوكلاء ← قائمة الوكلاء» — والمجموعة نفسها تسعّر له الألعاب والموبايل معاً.
        <div style={{ marginTop: 6 }}>
          الخلية التي عليها وسم مثل <sup style={{ ...linkTag, position: "static" }}>10%</sup>{" "}
          <b>مرتبطة بتكلفتك</b>: إن غيّر المتجر سعره تبعته تلقائياً. التعديل اليدوي يفكّ الارتباط.
          ولا يُباع شيءٌ تحت تكلفتك أبداً.
        </div>
      </div>

      {groups.length === 0 ? (
        <div className="card" style={{ padding: 30, textAlign: "center", color: "var(--muted)" }}>
          لا مجموعات بعد — أنشئ أوّل مجموعة ثم سعّرها بالتسعير الجماعي.
        </div>
      ) : (
        <div style={{ overflowX: "auto" }}>
          <table style={table}>
            <thead>
              <tr>
                <th style={{ ...th, width: 50 }}>Id</th>
                <th style={{ ...th, textAlign: "right", paddingInlineStart: 12 }}>الباقة</th>
                <th style={th}>تكلفتي</th>
                {groups.map((g) => (
                  <th key={g.id} style={{ ...th, background: "var(--primary)" }}>
                    مجموعة {g.name}
                    <div style={{ fontSize: 10.5, fontWeight: 400, opacity: .85 }}>{g.dealers} دكان</div>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {shown.length === 0 && (
                <tr><td colSpan={3 + groups.length} style={{ ...td, padding: 24 }}>لا شيء يطابق «{q.trim()}»</td></tr>
              )}
              {shown.map((b) => (
                <Fragment key={b.name}>
                  <tr><td colSpan={3 + groups.length} style={groupHead}>{b.name}</td></tr>
                  {b.products.map((p, i) => (
                    <tr key={p.id} style={{ background: i % 2 ? "var(--row-alt)" : "#fff" }}>
                      <td style={{ ...td, color: "var(--muted)" }}>{p.id}</td>
                      <td style={{ ...td, textAlign: "right", paddingInlineStart: 12, fontWeight: 600 }}>
                        {p.name}
                        {isAmountP(p) && <span style={unitTag} title="باقة بالكمية — الأسعار للوحدة الواحدة">⚖ للوحدة</span>}
                      </td>
                      <td style={{ ...td, color: "var(--muted)" }}>{showPrice(p.cost, p)}</td>
                      {groups.map((g) => {
                        const cell = p.prices[g.id];
                        const isEditing = editing?.p === p.id && editing?.g === g.id;
                        const profit = cell ? Number(cell.price) - Number(p.cost) : 0;
                        return (
                          <td key={g.id} style={{ ...td, cursor: "pointer",
                            color: cell ? "var(--primary-dark)" : "var(--faint)", fontWeight: cell ? 700 : 400 }}
                            onClick={() => {
                              if (isEditing) return;
                              cancelled.current = false;
                              const orig = cell ? editValue(cell.price, p) : "";
                              setEditing({ p: p.id, g: g.id, orig }); setDraft(orig);
                            }}
                            title={cell?.margin
                              ? `مرتبطة بتكلفتك: ${marginLabel(cell.margin)} · ربحك ${profit.toFixed(2)} ${sym}`
                              : cell ? `ربحك ${profit.toFixed(2)} ${sym}` : "بتكلفتك — اضغط للتسعير"}>
                            {isEditing ? (
                              <input autoFocus type="number" step="any" value={draft}
                                placeholder="فارغ = بتكلفتي"
                                onChange={(e) => setDraft(e.target.value)}
                                onBlur={() => saveCell(p.id, g.id)}
                                onKeyDown={(e) => {
                                  if (e.key === "Enter") (e.target as HTMLInputElement).blur();
                                  if (e.key === "Escape") { cancelled.current = true; setEditing(null); }
                                }}
                                style={{ width: 90, height: 26 }} />
                            ) : cell ? (
                              <>
                                {showPrice(cell.price, p)}
                                {cell.margin && <sup style={linkTag}>{marginLabel(cell.margin)}</sup>}
                              </>
                            ) : "—"}
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </Fragment>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {dialog === "bulk" && (
        <BulkModal section={section} groups={groups} products={picker} costOf={costOf} sym={sym}
          onClose={() => setDialog(null)}
          onDone={(t) => { setDialog(null); say(true, t); load(); }} />
      )}
      {dialog === "delete" && (
        <DeleteModal groups={groups} onClose={() => setDialog(null)}
          onDone={(t) => { setDialog(null); say(true, t); load(); }} />
      )}

      {toast && (
        <div onClick={() => setToast(null)} style={{ ...toastBox, background: toast.ok ? "#123" : "var(--danger)" }}>
          {toast.text}
        </div>
      )}
      <ScrollTop />
    </div>
  );
}

/** تسعير جماعي: سعر المجموعات المختارة = تكلفتي + هامش، مرتبطاً بها. */
function BulkModal({ section, groups, products, costOf, sym, onClose, onDone }: {
  section: string; groups: Group[]; products: PickerProduct[]; costOf: Map<number, string>; sym: string;
  onClose: () => void; onDone: (t: string) => void;
}) {
  const [picked, setPicked] = useState<number[]>([]);
  const [chosen, setChosen] = useState<number[]>(groups.map((g) => g.id));
  const [mode, setMode] = useState<"percent" | "fixed">("percent");
  const [value, setValue] = useState("");
  const [round, setRound] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  const sample = useMemo(() => {
    const id = picked[0] ?? products[0]?.id;
    const cost = Number(costOf.get(id!) ?? 0);
    const v = Number(value);
    if (!id || !cost || value === "" || Number.isNaN(v)) return null;
    let after = Math.round((mode === "percent" ? cost * (1 + v / 100) : cost + v) * 100) / 100;
    if (round) after = Math.ceil(after * 2) / 2;
    return { name: products.find((p) => p.id === id)?.name ?? "", cost, after };
  }, [picked, products, costOf, mode, value, round]);

  async function apply() {
    setErr(""); setBusy(true);
    try {
      const r = await api.post("/agent/bulk-price/", { section, groups: chosen, products: picked, mode, value, round });
      const skipped = (r.data.skipped_zero_cost || []) as string[];
      onDone(`✅ سُعّرت ${r.data.updated} باقة في ${r.data.groups.join("، ")}` +
        (skipped.length ? ` — وتُركت ${skipped.length} بلا تكلفة` : ""));
    } catch (e: any) {
      setErr(e?.response?.data?.detail || "تعذّر التسعير");
    } finally { setBusy(false); }
  }

  return (
    <div style={overlay} onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div style={box}>
        <div style={head}>تسعير جماعي<button type="button" style={xBtn} onClick={onClose}>✕</button></div>
        <div style={{ padding: 16 }}>
          <Field label="المجموعات">
            <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
              {groups.map((g) => {
                const on = chosen.includes(g.id);
                return (
                  <button key={g.id} type="button" onClick={() => setChosen(on ? chosen.filter((x) => x !== g.id) : [...chosen, g.id])}
                    style={{ ...chip, background: on ? "var(--primary)" : "var(--surface)", color: on ? "#fff" : "var(--text)" }}>
                    {on ? "✓ " : ""}{g.name}
                  </button>
                );
              })}
            </div>
          </Field>
          <Field label="الباقات" hint="بجانب كل باقة تكلفتك — وعليها يُحسب السعر. اتركه فارغاً ليشمل الكل.">
            <ProductPicker products={products} value={picked} onChange={setPicked}
              meta={(id) => <b style={{ direction: "ltr", color: "var(--primary-dark)" }}>{Number(costOf.get(id) ?? 0).toFixed(2)}</b>} />
          </Field>
          <Field label="نوع الهامش">
            <select value={mode} onChange={(e) => setMode(e.target.value as any)} style={input}>
              <option value="percent">نسبة مئوية % من تكلفتي</option>
              <option value="fixed">مبلغ ثابت يُضاف إلى تكلفتي ({sym})</option>
            </select>
          </Field>
          <Field label={mode === "percent" ? "النسبة (%)" : `المبلغ (${sym})`}
            hint="سعر دكانك = تكلفتك + الهامش. الأساس تكلفتك دائماً، فإعادة التطبيق لا تضاعف الزيادة.">
            <input type="number" step="0.01" min="0" value={value} autoFocus onChange={(e) => setValue(e.target.value)}
              style={input} placeholder={mode === "percent" ? "مثال: 5" : "مثال: 10"} />
          </Field>
          <label style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 14, cursor: "pointer" }}>
            <input type="checkbox" checked={round} onChange={(e) => setRound(e.target.checked)} />
            <span><b>تقريب لأعلى إلى أقرب نصف</b> <span style={{ color: "var(--muted)" }}>— لا يمسّ باقات «بالكمية».</span></span>
          </label>
          <div style={preview}>
            {sample && (
              <div style={{ marginBottom: 6 }}>
                مثال — <b>{sample.name}</b>: تكلفتك {sample.cost.toFixed(2)} ⇐ سعر دكانك{" "}
                <b style={{ color: "var(--primary-dark)" }}>{sample.after.toFixed(2)}</b> {sym}
              </div>
            )}
            🔗 الأسعار تبقى <b>مرتبطة</b> بتكلفتك: إن غيّر المتجر سعره عليك أُعيد حساب سعر دكاكينك تلقائياً.
          </div>
        </div>
        <div style={foot}>
          {err && <span style={{ color: "var(--danger)", fontSize: 12.5 }}>{err}</span>}
          <button className="btn" style={{ marginInlineStart: "auto" }} onClick={onClose}>إلغاء</button>
          <button className="btn g" disabled={busy || value === "" || chosen.length === 0} onClick={apply}>
            {busy ? "جارٍ التسعير..." : "تطبيق"}
          </button>
        </div>
      </div>
    </div>
  );
}

function DeleteModal({ groups, onClose, onDone }: {
  groups: Group[]; onClose: () => void; onDone: (t: string) => void;
}) {
  const [id, setId] = useState<number>(groups[0]?.id);
  const [busy, setBusy] = useState(false);
  const g = groups.find((x) => x.id === id);
  async function remove() {
    setBusy(true);
    try {
      await api.delete("/agent/price-groups/", { data: { id } });
      onDone(`🗑 حُذفت مجموعة ${g?.name}`);
    } finally { setBusy(false); }
  }
  return (
    <div style={overlay} onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div style={box}>
        <div style={head}>حذف مجموعة<button type="button" style={xBtn} onClick={onClose}>✕</button></div>
        <div style={{ padding: 16 }}>
          <Field label="المجموعة">
            <select value={id} onChange={(e) => setId(Number(e.target.value))} style={input}>
              {groups.map((x) => <option key={x.id} value={x.id}>مجموعة {x.name} — {x.dealers} دكان</option>)}
            </select>
          </Field>
          <div style={{ ...preview, background: "#fdf3f3", borderColor: "#f0caca", color: "#8a3535" }}>
            تُحذف أسعار المجموعة كلّها (الألعاب والموبايل)
            {!!g?.dealers && <>، و<b>{g.dealers} دكان</b> يصيرون «بلا مجموعة» فيشترون بتكلفتك</>}. لا رجعة في هذا.
          </div>
        </div>
        <div style={foot}>
          <button className="btn" style={{ marginInlineStart: "auto" }} onClick={onClose}>إلغاء</button>
          <button className="btn r" disabled={busy || !id} onClick={remove}>{busy ? "جارٍ الحذف..." : "حذف"}</button>
        </div>
      </div>
    </div>
  );
}

function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <div style={{ marginBottom: 14 }}>
      <label style={{ display: "block", fontSize: 12.5, fontWeight: 700, marginBottom: 5 }}>{label}</label>
      {children}
      {hint && <div style={{ fontSize: 11.5, color: "var(--muted)", marginTop: 4, lineHeight: 1.6 }}>{hint}</div>}
    </div>
  );
}

const ib: React.CSSProperties = { marginInlineEnd: 5 };
const toolbar: React.CSSProperties = { display: "flex", gap: 10, flexWrap: "wrap", marginBottom: 10 };
const note: React.CSSProperties = {
  background: "#f6f8f9", border: "1px solid #dbe3e5", color: "var(--muted)",
  fontSize: 13, padding: "9px 14px", borderRadius: 6, marginBottom: 14, lineHeight: 1.8,
};
const table: React.CSSProperties = { width: "100%", borderCollapse: "collapse", background: "var(--surface)", fontSize: 13.5 };
const th: React.CSSProperties = {
  background: "var(--th-bg)", color: "var(--th-ink)", padding: "11px 10px", textAlign: "center",
  fontWeight: 800, fontSize: 12.5, whiteSpace: "nowrap", border: "1px solid var(--border)", borderTop: 0,
};
const td: React.CSSProperties = {
  padding: 10, textAlign: "center", whiteSpace: "nowrap", verticalAlign: "middle",
  background: "var(--surface)", border: "1px solid var(--border)", borderBottom: "3px solid var(--row-sep)",
};
const groupHead: React.CSSProperties = {
  background: "#f5c518", color: "#4a3c00", fontWeight: 700, padding: "7px 14px", textAlign: "right", fontSize: 14,
};
const linkTag: React.CSSProperties = {
  position: "relative", top: -1, marginInlineStart: 4, padding: "1px 4px", borderRadius: 4,
  background: "var(--primary)", color: "#fff", fontSize: 9.5, fontWeight: 700, direction: "ltr", verticalAlign: "super",
};
const unitTag: React.CSSProperties = {
  marginInlineStart: 6, fontSize: 10.5, fontWeight: 700, color: "#7c3aed", background: "#ede9fe",
  borderRadius: 999, padding: "1px 7px",
};
const chip: React.CSSProperties = {
  border: "1px solid var(--border)", borderRadius: 999, padding: "5px 12px", cursor: "pointer", fontSize: 13,
};
const overlay: React.CSSProperties = {
  position: "fixed", inset: 0, background: "rgba(0,0,0,.45)", zIndex: 80,
  display: "flex", alignItems: "center", justifyContent: "center",
};
const box: React.CSSProperties = {
  background: "var(--surface)", borderRadius: 10, width: 480, maxWidth: "95vw", maxHeight: "92vh",
  overflow: "auto", boxShadow: "0 10px 40px rgba(0,0,0,.3)",
};
const head: React.CSSProperties = {
  background: "var(--primary)", color: "#fff", padding: "11px 16px", fontWeight: 700, display: "flex", alignItems: "center",
};
const xBtn: React.CSSProperties = {
  marginInlineStart: "auto", background: "none", border: 0, color: "#fff", fontSize: 16, cursor: "pointer",
};
const foot: React.CSSProperties = {
  display: "flex", alignItems: "center", gap: 8, padding: "11px 16px",
  borderTop: "1px solid var(--border)", background: "var(--row-alt)",
};
const input: React.CSSProperties = {
  width: "100%", height: 34, padding: "0 10px", borderRadius: 6, border: "1px solid var(--border)",
  background: "var(--surface)", font: "inherit", fontSize: 13.5,
};
const preview: React.CSSProperties = {
  background: "#f6f8f9", border: "1px solid #dbe3e5", borderRadius: 6, padding: "9px 12px",
  fontSize: 12.5, lineHeight: 1.7, color: "var(--muted)",
};
const toastBox: React.CSSProperties = {
  position: "fixed", insetInlineStart: 18, bottom: 18, zIndex: 90, maxWidth: 460, color: "#fff",
  padding: "11px 16px", borderRadius: 8, fontSize: 13, lineHeight: 1.7, boxShadow: "0 8px 26px rgba(0,0,0,.3)", cursor: "pointer",
};
