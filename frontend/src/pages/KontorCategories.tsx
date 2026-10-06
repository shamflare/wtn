import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import Icon from "../components/Icon";
import ImageUpload from "../components/ImageUpload";
import ScrollTop from "../components/ScrollTop";
import {
  empty, errText, Field, ib, input, Modal, NewCategoryFields, note, OpBadge, OPERATORS, pageTitle, pageWrap,
  Switch, Toast, type KCategory,
} from "./kontorUi";

/** فئة = شركة + نوع — هي «الكرة» التي يراها الوكيل بعد كشف شركة الرقم. */
type Category = KCategory;

export default function KontorCategories() {
  const [cats, setCats] = useState<Category[]>([]);
  const [loading, setLoading] = useState(true);
  const [toast, setToast] = useState("");
  const [adding, setAdding] = useState(false);

  useEffect(() => {
    api.get("/kontor/categories/").then((r) => setCats(r.data)).catch(() => {}).finally(() => setLoading(false));
  }, []);

  function say(t: string) { setToast(t); setTimeout(() => setToast(""), 2500); }

  async function save(id: number, patch: Partial<Category>) {
    setCats((l) => l.map((c) => (c.id === id ? { ...c, ...patch } : c)));
    try {
      await api.patch("/kontor/categories/", { id, ...patch });
      say("✅ حُفظ");
    } catch { say("تعذّر الحفظ"); }
  }

  /** شعار واحد لكل فئات الشركة — يُغني عن رفعه لكل فئة على حدة. */
  function setLogoAll(operator: string, logo: string) {
    const ids = cats.filter((c) => c.operator === operator).map((c) => c.id);
    setCats((l) => l.map((c) => (ids.includes(c.id) ? { ...c, logo_url: logo } : c)));
    api.patch("/kontor/categories/", ids.map((id) => ({ id, logo_url: logo })))
      .then(() => say("✅ حُفظ الشعار لكل الفئات")).catch(() => say("تعذّر الحفظ"));
  }

  /** نقل الفئة خطوة داخل شركتها — يعيد ترقيم الشركة كلّها فلا تتساوى أرقام الترتيب. */
  function move(c: Category, dir: -1 | 1) {
    const list = cats.filter((x) => x.operator === c.operator).sort(bySort);
    const i = list.findIndex((x) => x.id === c.id), j = i + dir;
    if (j < 0 || j >= list.length) return;
    [list[i], list[j]] = [list[j], list[i]];
    const order = new Map(list.map((x, n) => [x.id, (n + 1) * 10]));
    setCats((l) => l.map((x) => (order.has(x.id) ? { ...x, sort_order: order.get(x.id)! } : x)));
    api.patch("/kontor/categories/", list.map((x) => ({ id: x.id, sort_order: order.get(x.id) })))
      .then(() => say("✅ حُفظ الترتيب")).catch(() => say("تعذّر الحفظ"));
  }

  async function remove(c: Category) {
    if (!confirm(`حذف فئة «${c.name}»؟`)) return;
    try {
      await api.delete("/kontor/categories/", { data: { id: c.id } });
      setCats((l) => l.filter((x) => x.id !== c.id));
      say("🗑 حُذفت الفئة");
    } catch (e: any) { say(e?.response?.data?.detail || "تعذّر الحذف"); }
  }

  const byOp = useMemo(() => OPERATORS.map((o) => ({
    op: o, list: cats.filter((c) => c.operator === o.code).sort(bySort),
  })).filter((g) => g.list.length), [cats]);

  return (
    <div style={pageWrap}>
      <ScrollTop />
      <h2 style={pageTitle}>
        <Icon name="grid" size={20} /> فئات الخطوط
        <button className="btn g" style={{ marginInlineStart: "auto", fontSize: 13.5 }} onClick={() => setAdding(true)}>
          <Icon name="plus" size={15} style={ib} />إضافة فئة
        </button>
      </h2>
      <div style={note}>
        كل فئة مربّعٌ بلون الشركة يراه الوكيل بعد كشف الرقم. الأسماء قصيرة كما في ZNET (Ses · Tam · 3gCep · Wifi · Yds)
        لأن <b>شعار الشركة</b> يدلّ عليها — ارفعه مرّة واحدة بجانب اسم الشركة فيظهر على كل فئاتها.
        باقات العروض تنفصل تلقائياً في مربّع بنجمة (مثل <b>Ses*</b>). رتّبها بالأسهم، والمخفيّة تختفي بكل باقاتها.
      </div>

      {loading ? <div style={{ padding: 30 }}>جارٍ التحميل...</div>
        : byOp.length === 0 ? <div className="card"><div style={empty}>لا فئات — تُنشأ تلقائياً عند «استيراد من ZNET» في صفحة الباقات.</div></div>
        : byOp.map(({ op, list }) => (
          <div key={op.code} className="card">
            <div className="card-title">
              <OpBadge code={op.code} size={24} /> {op.label}
              <span style={{ color: "var(--muted)", fontWeight: 400, fontSize: 13 }}>· {list.length} فئة</span>
              <span style={{ marginInlineStart: "auto", display: "inline-flex", alignItems: "center", gap: 8,
                fontSize: 12, fontWeight: 600, color: "var(--muted)" }}>
                شعار الشركة لكل فئاتها
                <ImageUpload value={list.find((c) => c.logo_url)?.logo_url || ""} size={40}
                  onChange={(v) => setLogoAll(op.code, v)} />
              </span>
            </div>
            <div style={grid}>
              {list.map((c, i) => (
                <div key={c.id} style={{ ...tile, opacity: c.status === "active" ? 1 : 0.55 }}>
                  <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
                    <ImageUpload value={c.logo_url} onChange={(v) => save(c.id, { logo_url: v })} size={56} />
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <input defaultValue={c.name} key={c.name} style={{ ...input, fontWeight: 700 }}
                        onBlur={(e) => { const v = e.target.value.trim(); if (v && v !== c.name) save(c.id, { name: v }); }}
                        onKeyDown={(e) => e.key === "Enter" && (e.target as HTMLInputElement).blur()} />
                      <div style={{ fontSize: 11.5, color: "var(--muted)", marginTop: 4 }}>
                        {c.line_type_label} · {c.package_count} باقة
                        {c.is_custom && <span style={customTag}>مضافة</span>}
                      </div>
                    </div>
                  </div>
                  <div style={tileFoot}>
                    <label style={sw}><Switch on={c.status === "active"} onChange={(v) => save(c.id, { status: v ? "active" : "passive" })} /> ظاهرة</label>
                    <span style={{ marginInlineStart: "auto", display: "inline-flex", gap: 4 }}>
                      {c.package_count === 0 && (
                        <button className="btn r" style={arrow} onClick={() => remove(c)} title="حذف الفئة (فارغة)">
                          <Icon name="trash" size={12} /></button>
                      )}
                      <button className="btn" style={arrow} disabled={i === 0} onClick={() => move(c, -1)} title="أعلى">▲</button>
                      <button className="btn" style={arrow} disabled={i === list.length - 1} onClick={() => move(c, 1)} title="أسفل">▼</button>
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        ))}
      {adding && (
        <AddCategoryModal onClose={() => setAdding(false)}
          onSaved={(c) => { setCats((l) => [...l, c]); setAdding(false); say(`✅ أُضيفت فئة «${c.name}»`); }} />
      )}
      <Toast text={toast} />
    </div>
  );
}

function AddCategoryModal({ onClose, onSaved }: { onClose: () => void; onSaved: (c: Category) => void }) {
  const [op, setOp] = useState<string>(OPERATORS[0].code);
  const [name, setName] = useState("");
  const [lineType, setLineType] = useState("Ses");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  async function save() {
    setBusy(true); setErr("");
    try {
      const r = await api.post("/kontor/categories/", { operator: op, name: name.trim(), line_type: lineType });
      onSaved(r.data);
    } catch (e: any) { setErr(e?.response?.data?.detail || "تعذّرت الإضافة"); }
    finally { setBusy(false); }
  }
  return (
    <Modal title="إضافة فئة" onClose={onClose} width={500} footer={<>
      {err && <span style={errText}>{err}</span>}
      <button className="btn" style={{ marginInlineStart: "auto" }} onClick={onClose}>إلغاء</button>
      <button className="btn g" disabled={busy || !name.trim()} onClick={save}>{busy ? "جارٍ الإضافة..." : "إضافة"}</button>
    </>}>
      <Field label="الشركة">
        <select value={op} onChange={(e) => setOp(e.target.value)} style={input}>
          {OPERATORS.map((o) => <option key={o.code} value={o.code}>{o.label}</option>)}
        </select>
      </Field>
      <NewCategoryFields name={name} lineType={lineType} onName={setName} onLineType={setLineType} />
      <div style={{ fontSize: 12, color: "var(--muted)" }}>
        تظهر الفئة للوكيل كرةً حين تضع فيها باقات (من «إضافة باقة» في صفحة الباقات). تأخذ شعار الشركة تلقائياً،
        وتُحذف وهي فارغة فقط.
      </div>
    </Modal>
  );
}

const customTag: React.CSSProperties = {
  marginInlineStart: 6, fontSize: 10, fontWeight: 700, color: "var(--info)",
  background: "color-mix(in srgb, var(--info) 12%, transparent)", borderRadius: 999, padding: "1px 7px",
};

const bySort = (a: Category, b: Category) => a.sort_order - b.sort_order || a.id - b.id;

const grid: React.CSSProperties = {
  display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(290px, 1fr))", gap: 14, padding: 16,
};
const tile: React.CSSProperties = {
  border: "1px solid var(--border)", borderRadius: 12, padding: 12, background: "var(--surface)",
  boxShadow: "var(--shadow-soft)",
};
const tileFoot: React.CSSProperties = {
  display: "flex", alignItems: "center", gap: 14, marginTop: 12, paddingTop: 10,
  borderTop: "1px dashed var(--border)", fontSize: 12.5,
};
const sw: React.CSSProperties = { display: "inline-flex", alignItems: "center", gap: 6, cursor: "pointer" };
const arrow: React.CSSProperties = { width: 28, height: 26, padding: 0, fontSize: 10 };
