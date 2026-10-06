import { Fragment, useEffect, useMemo, useState } from "react";
import { api } from "../api";
import Icon from "../components/Icon";
import ProductPicker, { type PickerProduct } from "../components/ProductPicker";
import ScrollTop from "../components/ScrollTop";
import { matches } from "../search";
import {
  empty, errText, Field, groupHead, ib, input, LedgerNote, Modal, money, note, OperatorTabs, opOf, pageTitle,
  pageWrap, preview, ProviderPickModal, Toast, useLedger,
} from "./kontorUi";

interface Group { id: number; name: string; dealer_count?: number }
interface Cell { price: string; linked: boolean; mode: string; value: string; round: boolean }
interface Row {
  id: number; name: string; details: string; category: string; category_id: number | null;
  znet_id: string; link_code: string; kind: string; status: string; provider_cost: string;
  cost_price: string; recommended_price: string; prices: Record<string, Cell>;
}

/** وسم القاعدة كما يُقرأ: «3%» أو «+0.20» — و«↑» إن كانت تقرّب لأعلى. */
function ruleLabel(c: Cell): string {
  const v = Number(c.value);
  const n = Number.isInteger(v) ? String(v) : String(Number(v.toFixed(4)));
  return (c.mode === "percent" ? `${n}%` : `+${n}`) + (c.round ? "↑" : "");
}

// عمود الخلية قيد التحرير: رقم مجموعة، أو عمود الموصى
type Col = number | "rec";

export default function KontorPrices() {
  const [op, setOp] = useState("Turkcell");
  const [groups, setGroups] = useState<Group[]>([]);
  const [rows, setRows] = useState<Row[]>([]);
  const [loading, setLoading] = useState(true);
  const [q, setQ] = useState("");
  const [editing, setEditing] = useState<{ p: number; g: Col } | null>(null);
  const [draft, setDraft] = useState("");
  const [dialog, setDialog] = useState<"new" | "bulk" | "rec" | "delete" | "costs" | null>(null);
  const [toast, setToast] = useState("");
  const ledger = useLedger();

  async function load() {
    const r = await api.get(`/kontor/price-matrix/?operator=${op}`);
    setGroups(r.data.groups); setRows(r.data.rows);
  }
  useEffect(() => { setLoading(true); load().catch(() => {}).finally(() => setLoading(false)); }, [op]);

  function done(message: string) {
    setDialog(null); setToast(message); setTimeout(() => setToast(""), 6000);
    load().catch(() => {});
  }

  const shown = useMemo(
    () => rows.filter((r) => !q.trim() || matches(q, r.name, r.znet_id, r.link_code, r.category)),
    [rows, q],
  );
  const grouped = useMemo(() => {
    const m = new Map<string, Row[]>();
    for (const r of shown) {
      const k = r.category || "—";
      if (!m.has(k)) m.set(k, []);
      m.get(k)!.push(r);
    }
    return [...m.entries()];
  }, [shown]);

  const pickerItems = useMemo<PickerProduct[]>(
    () => rows.map((r) => ({ id: r.id, name: `${r.name} · ${r.link_code}`, game_name: r.category || "—" })),
    [rows],
  );
  const costOf = useMemo(() => new Map(rows.map((r) => [r.id, r.cost_price])), [rows]);

  function startEdit(p: number, g: Col, current: string) {
    if (editing?.p === p && editing?.g === g) return;
    setEditing({ p, g }); setDraft(current);
  }

  async function saveCell(r: Row, g: number) {
    const v = draft.trim();
    setEditing(null);
    if (v === "" || Number(v) === Number(r.prices[g]?.price)) return;
    await api.post("/kontor/set-price/", { package: r.id, group: g, price: v });
    // التعديل اليدوي يفكّ ارتباط الخلية بقاعدتها — كما يفعل الخادم
    setRows((rs) => rs.map((x) => x.id === r.id
      ? { ...x, prices: { ...x.prices, [g]: { price: v, linked: false, mode: "", value: "", round: false } } } : x));
  }

  async function saveRec(r: Row) {
    const v = draft.trim();
    setEditing(null);
    if (v === "" || Number(v) === Number(r.recommended_price)) return;
    await api.patch(`/kontor/packages/${r.id}/`, { recommended_price: v });
    setRows((rs) => rs.map((x) => (x.id === r.id ? { ...x, recommended_price: v } : x)));
  }

  function cellInput(commit: () => void) {
    return (
      <input autoFocus type="number" step="any" value={draft} style={{ width: 84, height: 26 }}
        onChange={(e) => setDraft(e.target.value)} onBlur={commit}
        onKeyDown={(e) => {
          if (e.key === "Enter") commit();
          if (e.key === "Escape") { setDraft(""); setEditing(null); }
        }} />
    );
  }

  /** كلفة الباقات = كلفتها لدى المزوّد المختار؛ غير المربوطة به تُذكر مجمّعة ولا تُمسّ. */
  async function refreshCosts(provider: number) {
    const r = await api.post("/kontor/refresh-costs/", { provider });
    await load();
    const d = r.data as {
      provider: string; updated: number; unchanged: number; skipped_total: number;
      skipped: { operator: string; operator_label: string; category: string; count: number }[];
    };
    return (<>
      <div style={preview}>
        من <b>{d.provider}</b>:
        <div>✅ تغيّرت كلفة <b className="num">{d.updated}</b> باقة{d.updated > 0 && " — وأُعيد حساب الخلايا المرتبطة بها"}.</div>
        <div>= <b className="num">{d.unchanged}</b> باقة كلفتها كما هي.</div>
      </div>
      {d.skipped_total > 0 && (
        <div style={{ ...preview, marginTop: 10, background: "#fff8e6", borderColor: "#f0dca0", color: "#7a5a00" }}>
          ⚠️ <b className="num">{d.skipped_total}</b> باقة <b>لم تُحدَّث</b> — ليست مربوطة بهذا المزوّد أو لم يعد
          رقمها في قائمته، فبقيت كلفتها كما كانت:
          <ul style={{ margin: "6px 0 0", paddingInlineStart: 20 }}>
            {d.skipped.map((s) => (
              <li key={s.operator + s.category}><b className="num">{s.count}</b> باقة من {s.operator_label} نوع <b>{s.category}</b></li>
            ))}
          </ul>
          <div style={{ marginTop: 6 }}>اربطها بأرقامها لدى هذا المزوّد من «التوجيه» إن أردت أن تتبع كلفته.</div>
        </div>
      )}
    </>);
  }

  const cols = 4 + groups.length;

  return (
    <div style={pageWrap}>
      <ScrollTop />
      <h2 style={pageTitle}><Icon name="tag" size={20} /> مجموعات أسعار الخطوط</h2>

      <div className="toolbar">
        <button className="btn g" onClick={() => setDialog("new")}><Icon name="plus" size={15} style={ib} />إنشاء مجموعة</button>
        <button className="btn" onClick={() => setDialog("bulk")} disabled={!groups.length}>
          <Icon name="chart" size={15} style={ib} />تسعير جماعي</button>
        <button className="btn" onClick={() => setDialog("rec")}><Icon name="chart" size={15} style={ib} />تحديد السعر الموصى</button>
        <button className="btn" onClick={() => setDialog("costs")}><Icon name="refresh" size={15} style={ib} />تحديث التكلفة</button>
        <button className="btn r" onClick={() => setDialog("delete")} disabled={!groups.length}>
          <Icon name="trash" size={15} style={ib} />حذف مجموعة</button>
        <input placeholder="بحث سريع: باقة أو فئة أو رقم ربط..." value={q} onChange={(e) => setQ(e.target.value)}
          style={{ ...input, width: 250, marginInlineStart: "auto" }} />
      </div>

      <div style={{ marginBottom: 12 }}><OperatorTabs value={op} onChange={(c) => { setOp(c); setEditing(null); }} /></div>

      <LedgerNote ledger={ledger} />
      <div style={note}>
        اضغط على أي خلية سعر لتعديلها. الخلية <b style={{ color: "var(--primary-dark)" }}>الملوّنة</b> = سعر مخصّص
        للمجموعة، والرمادية = تتبع <b>السعر الموصى</b>. عمود الموصى قابل للتعديل هنا أيضاً.
        <div style={{ marginTop: 4 }}>
          الخلية التي عليها وسم مثل <sup style={{ ...linkTag, position: "static" }}>10%</sup>{" "}
          <b>مرتبطة بالكلفة</b>: يُعاد حسابها تلقائياً مع كل «تحديث التكلفة» يغيّر كلفة ZNET.
          ويُفكّ الارتباط بتسعير جماعي جديد أو بتعديل الخلية بيدك.
        </div>
      </div>

      {loading ? <div style={{ padding: 30 }}>جارٍ التحميل...</div> : (
        <div className="card"><div className="table-scroll">
          <table className="grid">
            <thead>
              <tr>
                <th style={{ width: 80 }}>رقم الربط</th>
                <th className="cell-start">الباقة</th>
                <th>الكلفة {ledger.sym && `(${ledger.sym})`}</th>
                <th>الموصى {ledger.sym && `(${ledger.sym})`}</th>
                {groups.map((g) => (
                  <th key={g.id} style={{ background: "var(--primary)", color: "#fff" }}>
                    مجموعة {g.name}
                    {!!g.dealer_count && <div style={{ fontSize: 10.5, fontWeight: 400, opacity: 0.85 }}>{g.dealer_count} وكيل</div>}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.length === 0 && <tr><td colSpan={cols} style={empty}>لا باقات لـ{opOf(op).label} — استوردها من «الباقات».</td></tr>}
              {rows.length > 0 && grouped.length === 0 && <tr><td colSpan={cols} style={empty}>لا شيء يطابق «{q.trim()}»</td></tr>}
              {grouped.map(([cat, list]) => (
                <Fragment key={cat}>
                  <tr><td colSpan={cols} style={groupHead}>{cat} <span style={{ fontWeight: 400, opacity: 0.75 }}>· {list.length}</span></td></tr>
                  {list.map((r) => (
                    <tr key={r.id} style={{ opacity: r.status === "active" ? 1 : 0.5 }}>
                      <td className="num" style={{ color: "var(--muted)", fontWeight: 700 }}>{r.link_code}</td>
                      <td className="cell-start">
                        <span style={{ fontWeight: 700 }}>{r.name}</span>
                        {r.kind === "offer" && <span style={offerTag}>عرض</span>}
                        {r.status !== "active" && <span style={{ ...offerTag, background: "#eef1f2", color: "var(--muted)" }}>معطّلة</span>}
                      </td>
                      <td className="num">
                        <div className="buy">{money(r.cost_price)}</div>
                        {ledger.base !== "TRY" && Number(r.provider_cost) > 0 &&
                          <div style={{ fontSize: 11, color: "var(--faint)" }}>{money(r.provider_cost)} ₺</div>}
                      </td>
                      <td className="num" style={{ cursor: "pointer" }}
                        onClick={() => startEdit(r.id, "rec", Number(r.recommended_price) ? r.recommended_price : "")}>
                        {editing?.p === r.id && editing?.g === "rec" ? cellInput(() => saveRec(r))
                          : Number(r.recommended_price) > 0 ? <b>{money(r.recommended_price)}</b>
                          : <span style={{ color: "var(--danger)", fontSize: 12 }}>غير مسعّرة</span>}
                      </td>
                      {groups.map((g) => {
                        const c = r.prices[g.id];
                        const custom = !!c?.price;
                        return (
                          <td key={g.id} className="num" style={{ cursor: "pointer",
                            color: custom ? "var(--primary-dark)" : "var(--faint)", fontWeight: custom ? 700 : 400 }}
                            title={c?.linked ? `مرتبطة بالكلفة: ${ruleLabel(c)} — تتبعها كلّما تغيّرت. التعديل اليدوي يفكّ الارتباط.` : undefined}
                            onClick={() => startEdit(r.id, g.id, c?.price || "")}>
                            {editing?.p === r.id && editing?.g === g.id ? cellInput(() => saveCell(r, g.id)) : (<>
                              {money(custom ? c.price : r.recommended_price)}
                              {c?.linked && <sup style={linkTag}>{ruleLabel(c)}</sup>}
                            </>)}
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </Fragment>
              ))}
            </tbody>
          </table>
        </div></div>
      )}

      {dialog === "new" && <NewGroupModal onClose={() => setDialog(null)} onDone={done} />}
      {(dialog === "bulk" || dialog === "rec") && (
        <BulkModal op={op} groups={groups} products={pickerItems} costOf={costOf}
          initial={dialog === "rec" ? "recommended" : undefined}
          onClose={() => setDialog(null)} onDone={done} />
      )}
      {dialog === "delete" && <DeleteGroupModal groups={groups} onClose={() => setDialog(null)} onDone={done} />}
      {dialog === "costs" && (
        <ProviderPickModal title="تحديث التكلفة من ZNET" action="تحديث التكلفة" busyText="جارٍ التحديث..."
          hint={<>اختر مزوّد ZNET الذي تُؤخذ منه الكلفة. تصير كلفة كل باقة <b>كلفتها لدى هذا المزوّد</b> (لكل
            الشركات)، وتتبعها الخلايا المرتبطة بالكلفة. الباقة تُطابَق برقمها لديه — والتي ليست مربوطة به
            لا تُمسّ وتُذكر لك بعد التحديث.</>}
          run={refreshCosts} onClose={() => setDialog(null)} />
      )}
      <Toast text={toast} />
    </div>
  );
}

/* ─────────────────────────── النوافذ ─────────────────────────── */

function NewGroupModal({ onClose, onDone }: { onClose: () => void; onDone: (m: string) => void }) {
  const [name, setName] = useState("");
  const [err, setErr] = useState("");
  async function create() {
    if (!name.trim()) return;
    try {
      await api.post("/kontor/price-groups/", { name: name.trim() });
      onDone(`✅ أُنشئت مجموعة ${name.trim()} — خلاياها تتبع الموصى حتى تسعّرها`);
    } catch (e: any) { setErr(e?.response?.data?.detail || "تعذّر الإنشاء"); }
  }
  return (
    <Modal title="إنشاء مجموعة أسعار" onClose={onClose} footer={<>
      {err && <span style={errText}>{err}</span>}
      <button className="btn" style={{ marginInlineStart: "auto" }} onClick={onClose}>إلغاء</button>
      <button className="btn g" disabled={!name.trim()} onClick={create}>إنشاء</button>
    </>}>
      <Field label="اسم المجموعة" hint="المجموعة مشتركة بين الشركات الأربع، ولكل وكيل مجموعته لكل شركة في «إعدادات الوكلاء».">
        <input autoFocus value={name} onChange={(e) => setName(e.target.value)} style={input}
          onKeyDown={(e) => e.key === "Enter" && create()} placeholder="مثال: VIP، جملة، ذهبي" />
      </Field>
    </Modal>
  );
}

/**
 * تسعير جماعي — سعر مجموعة، أو السعر الموصى، = كلفة كل باقة + هامش، مقرّباً لأعلى
 * إلى أقرب نصف إن طُلب. الأساس الكلفة لا السعر الحالي، فتكرار التطبيق لا يضاعف الزيادة.
 */
function BulkModal({ op, groups, products, costOf, initial, onClose, onDone }: {
  op: string; groups: Group[]; products: PickerProduct[]; costOf: Map<number, string>;
  initial?: "recommended"; onClose: () => void; onDone: (m: string) => void;
}) {
  const [group, setGroup] = useState<number | "recommended">(initial ?? groups[0]?.id ?? "recommended");
  const [picked, setPicked] = useState<number[]>([]);
  const [mode, setMode] = useState<"percent" | "fixed" | "follow">("percent");
  const [value, setValue] = useState("");
  const [round, setRound] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const toRec = group === "recommended";
  const follow = mode === "follow" && !toRec;

  const sample = useMemo(() => {
    const id = picked[0] ?? products[0]?.id;
    const cost = Number(costOf.get(id!) ?? 0);
    const v = Number(value);
    if (!id || !cost || !value || Number.isNaN(v) || follow) return null;
    let after = Math.round((mode === "percent" ? cost * (1 + v / 100) : cost + v) * 100) / 100;
    if (round) after = Math.ceil(after * 2) / 2;
    return { name: products.find((p) => p.id === id)?.name ?? "", cost, after };
  }, [picked, products, costOf, mode, value, round, follow]);

  async function apply() {
    setErr(""); setBusy(true);
    try {
      const r = await api.post("/kontor/bulk-price/", follow
        ? { group, operator: op, packages: picked, to_recommended: true }
        : { group, operator: op, packages: picked, mode, value, round });
      const skipped = (r.data.skipped_zero_cost || []) as string[];
      onDone(`✅ سُعّرت ${r.data.updated} باقة لـ${opOf(op).label} ` +
        (toRec ? "في السعر الموصى" : `في مجموعة ${r.data.group}`) +
        (skipped.length ? ` — وتُركت ${skipped.length} بلا كلفة` : ""));
    } catch (e: any) {
      setErr(e?.response?.data?.detail || "تعذّر التسعير");
    } finally { setBusy(false); }
  }

  return (
    <Modal title={`${toRec ? "تحديد السعر الموصى" : "تسعير جماعي"} — ${opOf(op).label}`} onClose={onClose} footer={<>
      {err && <span style={errText}>{err}</span>}
      <button className="btn" style={{ marginInlineStart: "auto" }} onClick={onClose}>إلغاء</button>
      <button className="btn g" disabled={busy || (!follow && value === "")} onClick={apply}>
        {busy ? "جارٍ التسعير..." : "تطبيق"}
      </button>
    </>}>
      <Field label="أين يُكتب السعر" hint={toRec
        ? "يُكتب في عمود «الموصى» — وكل خلية مجموعة غير مخصّصة (رمادية) تتبعه."
        : "يُكتب في عمود هذه المجموعة وحدها ويصير مخصّصاً."}>
        <select value={group} style={input}
          onChange={(e) => setGroup(e.target.value === "recommended" ? "recommended" : Number(e.target.value))}>
          {groups.map((g) => <option key={g.id} value={g.id}>مجموعة {g.name}</option>)}
          <option value="recommended">السعر الموصى</option>
        </select>
      </Field>

      <Field label="الباقات" hint={`بجانب كل باقة كلفتها — وعليها يُحسب السعر. اتركه فارغاً ليشمل كل باقات ${opOf(op).label}.`}>
        <ProductPicker products={products} value={picked} onChange={setPicked}
          placeholder={`كل باقات ${opOf(op).label}`}
          meta={(id) => {
            const cost = Number(costOf.get(id) ?? 0);
            return cost > 0
              ? <b style={{ direction: "ltr", color: "var(--primary-dark)" }}>{cost.toFixed(2)}</b>
              : <span style={{ color: "var(--danger)" }}>بلا كلفة</span>;
          }} />
      </Field>

      <Field label="طريقة التسعير">
        <select value={mode} onChange={(e) => setMode(e.target.value as any)} style={input}>
          <option value="percent">نسبة مئوية % فوق الكلفة</option>
          <option value="fixed">مبلغ ثابت يُضاف إلى الكلفة (بعملة المتجر)</option>
          {!toRec && <option value="follow">نسخ السعر الموصى كما هو</option>}
        </select>
      </Field>

      {!follow && (<>
        <Field label={mode === "percent" ? "النسبة (%)" : "المبلغ"}
          hint="سعر البيع = الكلفة + الهامش. الأساس الكلفة دائماً، فإعادة التطبيق لا تضاعف الزيادة.">
          <input type="number" step="0.01" value={value} autoFocus style={input}
            onChange={(e) => setValue(e.target.value)} placeholder={mode === "percent" ? "مثال: 5" : "مثال: 3"} />
        </Field>
        <label style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 14, cursor: "pointer" }}>
          <input type="checkbox" checked={round} onChange={(e) => setRound(e.target.checked)} />
          <span><b>تقريب لأعلى إلى أقرب نصف</b>{" "}
            <span style={{ color: "var(--muted)" }}>— مثلاً 148.20 ⇐ 148.50 و 148.60 ⇐ 149</span></span>
        </label>
      </>)}

      <div style={preview}>
        {sample && (
          <div style={{ marginBottom: 6 }}>
            مثال — <b>{sample.name}</b>: كلفتها {sample.cost.toFixed(2)} ⇐ سعرها{" "}
            <b style={{ color: "var(--primary-dark)" }}>{sample.after.toFixed(2)}</b>
          </div>
        )}
        {toRec ? <>✍️ السعر الموصى يُكتب <b>مرّة واحدة</b> ولا يرتبط بالكلفة: إن تغيّرت لاحقاً بقي كما هو حتى تعيد التطبيق.</>
          : follow ? <>📋 تُنسخ قيمة الموصى الحالية إلى خلايا المجموعة كسعر يدوي ثابت.</>
          : <>🔗 الباقات تبقى <b>مرتبطة</b> بهذه القاعدة{round && " وتقريبها"}: كلّما تغيّرت كلفتها في ZNET
            أُعيد حساب سعرها في هذه المجموعة تلقائياً عند «تحديث التكلفة».</>}
      </div>
    </Modal>
  );
}

function DeleteGroupModal({ groups, onClose, onDone }: { groups: Group[]; onClose: () => void; onDone: (m: string) => void }) {
  const [id, setId] = useState<number | "">(groups[0]?.id ?? "");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const chosen = groups.find((g) => g.id === id);
  async function remove() {
    setErr(""); setBusy(true);
    try {
      await api.delete(`/kontor/price-groups/${id}/`);
      onDone(`🗑 حُذفت مجموعة ${chosen?.name}`);
    } catch (e: any) { setErr(e?.response?.data?.detail || "تعذّر الحذف"); }
    finally { setBusy(false); }
  }
  return (
    <Modal title="حذف مجموعة أسعار" onClose={onClose} footer={<>
      {err && <span style={errText}>{err}</span>}
      <button className="btn" style={{ marginInlineStart: "auto" }} onClick={onClose}>إلغاء</button>
      <button className="btn r" disabled={busy || !id} onClick={remove}>{busy ? "جارٍ الحذف..." : "حذف"}</button>
    </>}>
      <Field label="المجموعة">
        <select value={id} onChange={(e) => setId(Number(e.target.value))} style={input}>
          {groups.map((g) => (
            <option key={g.id} value={g.id}>مجموعة {g.name}{g.dealer_count ? ` — ${g.dealer_count} وكيل` : ""}</option>
          ))}
        </select>
      </Field>
      <div style={{ ...preview, background: "#fdf3f3", borderColor: "#f0caca", color: "#8a3535" }}>
        تُحذف المجموعة وأسعارها في <b>كل الشركات</b>.
        {!!chosen?.dealer_count && <> و<b>{chosen.dealer_count} وكيل</b> مربوطون بها يصيرون على <b>السعر الموصى</b> فوراً.</>}
        {" "}لا رجعة في هذا.
      </div>
    </Modal>
  );
}

const linkTag: React.CSSProperties = {
  position: "relative", top: -1, marginInlineStart: 4, padding: "1px 4px",
  borderRadius: 4, background: "var(--primary)", color: "#fff",
  fontSize: 9.5, fontWeight: 700, direction: "ltr", verticalAlign: "super",
};
const offerTag: React.CSSProperties = {
  marginInlineStart: 6, fontSize: 10.5, fontWeight: 700, color: "#b0306e",
  background: "#fde2ef", borderRadius: 999, padding: "1px 8px",
};
