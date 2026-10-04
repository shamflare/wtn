import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import Icon from "../components/Icon";
import ImageUpload from "../components/ImageUpload";
import ScrollTop from "../components/ScrollTop";
import { empty, input, note, OpBadge, OPERATORS, pageTitle, pageWrap, Switch, Toast } from "./kontorUi";

/** فئة = شركة + نوع — هي «الكرة» التي يراها الوكيل بعد كشف شركة الرقم. */
interface Category {
  id: number; operator: string; operator_label: string;
  line_type: string; line_type_label: string;
  name: string; logo_url: string; is_query: boolean;
  status: "active" | "passive"; sort_order: number; package_count: number;
}

export default function KontorCategories() {
  const [cats, setCats] = useState<Category[]>([]);
  const [loading, setLoading] = useState(true);
  const [toast, setToast] = useState("");

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

  const byOp = useMemo(() => OPERATORS.map((o) => ({
    op: o, list: cats.filter((c) => c.operator === o.code).sort(bySort),
  })).filter((g) => g.list.length), [cats]);

  return (
    <div style={pageWrap}>
      <ScrollTop />
      <h2 style={pageTitle}><Icon name="grid" size={20} /> فئات الخطوط</h2>
      <div style={note}>
        كل فئة هي <b>كرة</b> يراها الوكيل بجانب حقل الرقم بعد كشف الشركة. سمِّها كما تريد أن يقرأها وكلاؤك،
        وأضف شعاراً، ورتّبها بالأسهم — بهذا الترتيب تظهر للوكيل. الفئة المخفيّة تختفي بكل باقاتها.
      </div>

      {loading ? <div style={{ padding: 30 }}>جارٍ التحميل...</div>
        : byOp.length === 0 ? <div className="card"><div style={empty}>لا فئات — تُنشأ تلقائياً عند «استيراد من ZNET» في صفحة الباقات.</div></div>
        : byOp.map(({ op, list }) => (
          <div key={op.code} className="card">
            <div className="card-title">
              <OpBadge code={op.code} size={24} /> {op.label}
              <span style={{ color: "var(--muted)", fontWeight: 400, fontSize: 13 }}>· {list.length} فئة</span>
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
                      </div>
                    </div>
                  </div>
                  <div style={tileFoot}>
                    <label style={sw}><Switch on={c.status === "active"} onChange={(v) => save(c.id, { status: v ? "active" : "passive" })} /> ظاهرة</label>
                    <span style={{ marginInlineStart: "auto", display: "inline-flex", gap: 4 }}>
                      <button className="btn" style={arrow} disabled={i === 0} onClick={() => move(c, -1)} title="أعلى">▲</button>
                      <button className="btn" style={arrow} disabled={i === list.length - 1} onClick={() => move(c, 1)} title="أسفل">▼</button>
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        ))}
      <Toast text={toast} />
    </div>
  );
}

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
