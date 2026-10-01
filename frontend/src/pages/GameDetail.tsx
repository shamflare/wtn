import { useEffect, useState } from "react";
import { editValue, fmtPrecise, showPrice, toBlock } from "../unitPrice";
import { useNavigate, useParams } from "react-router-dom";
import { api, type GameDetail as GameDetailType, type Product, type Provider } from "../api";
import Icon from "../components/Icon";

/** باقة في المكتبة العالمية لم تُضَف بعد إلى هذه اللعبة. */
type LibPkg = {
  kupur: string;
  name: string;
  suggested_cost: string;
  suggested_price: string;
  sale_type?: string; qty_min?: number; qty_max?: number; qty_unit?: number;
};

export default function GameDetail() {
  const { id } = useParams();
  const nav = useNavigate();
  const [game, setGame] = useState<GameDetailType | null>(null);
  const [providers, setProviders] = useState<Provider[]>([]);
  const [saving, setSaving] = useState(false);
  const [savedMsg, setSavedMsg] = useState("");
  const [newP, setNewP] = useState({ name: "", cost_price: "", recommended_price: "", kupur: "" });
  // أرقام الربط المتاحة من المكتبة العالمية (ما لم يُؤخَذ بعد) + هل اللعبة أصلاً منها
  const [libPkgs, setLibPkgs] = useState<LibPkg[]>([]);
  const [libLinked, setLibLinked] = useState(false);
  const [libGames, setLibGames] = useState<{ id: number; name: string; packages: number }[]>([]);
  const [linkTo, setLinkTo] = useState("");
  const [addErr, setAddErr] = useState("");
  // نافذة تعديل الباقة: "edit" بيانات المنتج · "routing" المزوّدون + رقم الربط
  const [editing, setEditing] = useState<{ product: Product; mode: "edit" | "routing" } | null>(null);

  function load() {
    api.get(`/catalog/games/${id}/`).then((r) => setGame(r.data));
    // تُقرأ مع كل تحميل: إضافةُ باقة تسحب رقمها من القائمة، وحذفُها يعيده
    api.get(`/catalog/games/${id}/library-packages/`)
      .then((r) => {
        setLibPkgs(r.data.results || []);
        setLibLinked(!!r.data.linked);
        setLibGames(r.data.library_games || []);
      })
      .catch(() => { setLibPkgs([]); setLibLinked(false); setLibGames([]); });
  }
  useEffect(() => { load(); }, [id]);
  useEffect(() => {
    api.get("/providers/", { params: { status: "active" } }).then((r) => setProviders(r.data));
  }, []);

  if (!game) return <div style={{ padding: 30 }}>جارٍ التحميل...</div>;

  function set<K extends keyof GameDetailType>(k: K, v: GameDetailType[K]) {
    setGame((g) => (g ? { ...g, [k]: v } : g));
  }

  async function saveGame() {
    setSaving(true);
    setSavedMsg("");
    try {
      await api.patch(`/catalog/games/${id}/`, {
        name: game!.name, dealer_note: game!.dealer_note, description: game!.description,
        status: game!.status, kurulu_sale: game!.kurulu_sale, toplu_sale: game!.toplu_sale,
        require_player_id: game!.require_player_id, sms_template: game!.sms_template,
      });
      setSavedMsg("تم الحفظ ✅");
    } finally {
      setSaving(false);
    }
  }

  /** ربط اللعبة بنظيرتها في المكتبة — بعده تنفتح قائمة أرقام الربط. */
  async function linkLibrary() {
    if (!linkTo) return;
    setAddErr("");
    try {
      const r = await api.post(`/catalog/games/${id}/link-library/`, {
        library_game: Number(linkTo),
      });
      setLinkTo("");
      if (r.data?.adopted) {
        alert(`رُبطت اللعبة، ونالت ${r.data.adopted} باقة عندك أرقامَها من المكتبة بمطابقة الاسم.`);
      }
      load();
    } catch (e: any) {
      setAddErr(e?.response?.data?.detail || "تعذّر الربط");
    }
  }

  /** اختيار رقم ربط يملأ الاسم والسعرين من قيم المكتبة — وكلّها قابلة للتعديل قبل الحفظ. */
  function pickKupur(kupur: string) {
    const lib = libPkgs.find((p) => p.kupur === kupur);
    setAddErr("");
    setNewP(lib
      ? { kupur, name: lib.name,
          cost_price: editValue(lib.suggested_cost, lib), recommended_price: editValue(lib.suggested_price, lib) }
      : { ...newP, kupur });
  }

  // الرقم المختار من المكتبة «بالكمية»؟ فالأسعار في النموذج لكل كتلة
  const pickedLib = libPkgs.find((p) => p.kupur === newP.kupur);
  const amountUnit = pickedLib?.sale_type === "amount" ? pickedLib.qty_unit : 0;

  async function addProduct(e: React.FormEvent) {
    e.preventDefault();
    if (!newP.name) return;
    setAddErr("");
    // نوع الباقة وحدودها من المكتبة: «بالكمية» تبقى بالكمية بحجم كتلتها نفسه
    const lib = libPkgs.find((p) => p.kupur === newP.kupur);
    try {
      await api.post("/catalog/products/", {
        game: game!.id, name: newP.name,
        // بالكمية: ما كُتب سعرُ وحدة ⇐ يُحفظ لكل كتلة
        cost_price: toBlock(newP.cost_price || "0", lib), recommended_price: toBlock(newP.recommended_price || "0", lib),
        kupur: newP.kupur,
        ...(lib?.sale_type === "amount" ? {
          sale_type: "amount", qty_min: lib.qty_min, qty_max: lib.qty_max, qty_unit: lib.qty_unit,
        } : {}),
      });
      setNewP({ name: "", cost_price: "", recommended_price: "", kupur: "" });
      load();
    } catch (e: any) {
      const d = e?.response?.data;
      setAddErr(d?.kupur?.[0] || d?.detail || "تعذّرت الإضافة — تحقّق من القيم");
    }
  }

  /** تحرير خلية في الجدول: يحفظ فوراً ويعيد الربح المحسوب من الخادم. */
  async function patchProduct(pid: number, body: Record<string, string>) {
    const r = await api.patch(`/catalog/products/${pid}/`, body);
    setGame((g) => g
      ? { ...g, products: g.products.map((p) => (p.id === pid ? { ...p, ...r.data } : p)) }
      : g);
  }

  async function deleteProduct(p: Product) {
    if (!confirm(`حذف الباقة «${p.name}»؟ يعود رقم ربطها ${p.kupur || "—"} إلى قائمة المكتبة.`)) return;
    await api.delete(`/catalog/products/${p.id}/`);
    load();
  }


  return (
    <div style={{ padding: 16 }}>
      {/* شريط العنوان */}
      <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 14 }}>
        <button className="btn" style={{ background: "#8a999e" }} onClick={() => nav("/oyunpin")}>
          ← رجوع
        </button>
        <h2 style={{ fontSize: 20, color: "var(--primary-dark)" }}>تفاصيل اللعبة: {game.name}</h2>
      </div>

      {/* ===== القسم 1: تعديل تفاصيل اللعبة ===== */}
      <div style={panel}>
        <div style={panelHead}>تعديل تفاصيل اللعبة</div>
        <div style={{ padding: 18 }}>
          <Row label="اسم اللعبة">
            <input style={inp} value={game.name} onChange={(e) => set("name", e.target.value)} />
          </Row>
          <Row label="ملاحظة للوكيل">
            <input style={inp} value={game.dealer_note} onChange={(e) => set("dealer_note", e.target.value)} />
          </Row>
          <Row label="وصف اللعبة">
            <textarea style={{ ...inp, height: 70, paddingTop: 6 }}
              value={game.description} onChange={(e) => set("description", e.target.value)} />
          </Row>
          <Row label="حالة اللعبة">
            <select value={game.status} onChange={(e) => set("status", e.target.value)}>
              <option value="active">نشط</option>
              <option value="passive">معطّل</option>
            </select>
          </Row>
          <Row label="البيع بالحزم">
            <Toggle on={game.kurulu_sale} onChange={(v) => set("kurulu_sale", v)} />
          </Row>
          <Row label="البيع بالكمية">
            <Toggle on={game.toplu_sale} onChange={(v) => set("toplu_sale", v)} />
          </Row>
          <Row label="إجبار معرّف اللاعب">
            <Toggle on={game.require_player_id} onChange={(v) => set("require_player_id", v)} />
          </Row>
          <Row label="قالب SMS">
            <textarea style={{ ...inp, height: 54, paddingTop: 6 }}
              value={game.sms_template} onChange={(e) => set("sms_template", e.target.value)}
              placeholder="نص SMS يُرسل بعد التنفيذ (اختياري)" />
          </Row>
          <div style={{ display: "flex", alignItems: "center", gap: 12, marginTop: 8 }}>
            <button className="btn g" onClick={saveGame} disabled={saving}>
              {saving ? "جارٍ الحفظ..." : "حفظ التعديلات"}
            </button>
            {savedMsg && <span style={{ color: "var(--ok)", fontSize: 14 }}>{savedMsg}</span>}
          </div>
        </div>
      </div>

      {/* ===== القسم 2: عمليات المنتجات ===== */}
      <div style={{ ...panel, marginTop: 20 }}>
        <div style={panelHead}>عمليات المنتجات</div>
        <div style={{ padding: 18 }}>
          {libLinked ? (
            <>
              {/* نموذج إضافة منتج — يبدأ برقم الربط لأنه يملأ ما بعده */}
              <form onSubmit={addProduct} style={{ display: "flex", gap: 10, alignItems: "end", flexWrap: "wrap", marginBottom: 6 }}>
                <Field label="رقم الربط">
                  <select style={{ width: 230 }} value={newP.kupur}
                    disabled={libPkgs.length === 0}
                    onChange={(e) => pickKupur(e.target.value)}>
                    <option value="">
                      {libPkgs.length === 0 ? "— لا أرقام متاحة —" : "— اختر من المكتبة —"}
                    </option>
                    {libPkgs.map((p) => (
                      <option key={p.kupur} value={p.kupur}>
                        {p.kupur} — {p.name}{p.sale_type === "amount" ? " (بالكمية)" : ""}
                      </option>
                    ))}
                  </select>
                </Field>
                <Field label="اسم المنتج">
                  <input style={{ width: 180 }} value={newP.name}
                    onChange={(e) => setNewP({ ...newP, name: e.target.value })} />
                </Field>
                <Field label={amountUnit ? "تكلفة الوحدة" : "التكلفة"}>
                  <input style={{ width: 110 }} type="number" step="any" value={newP.cost_price}
                    onChange={(e) => setNewP({ ...newP, cost_price: e.target.value })} />
                </Field>
                <Field label={amountUnit ? "سعر الوحدة الموصى" : "السعر الموصى"}>
                  <input style={{ width: 110 }} type="number" step="any" value={newP.recommended_price}
                    onChange={(e) => setNewP({ ...newP, recommended_price: e.target.value })} />
                </Field>
                <button className="btn g" style={{ height: 32 }} disabled={!newP.kupur}>
                  <Icon name="plus" size={14} style={{ marginInlineEnd: 4 }} />إضافة
                </button>
              </form>

              <div style={{ ...hint, marginBottom: 16 }}>
                {libPkgs.length === 0
                  ? "كل أرقام ربط هذه اللعبة في المكتبة العالمية مُضافة عندك. احذف باقةً ليعود رقمها إلى القائمة، أو أضف باقةً جديدة في المكتبة."
                  : `أرقام الربط من المكتبة العالمية حصراً — ${libPkgs.length} رقماً متاحاً. الاختيار يملأ الاسم والسعرين تلقائياً، وكلّها قابلة للتعديل بعد الإضافة إلا رقم الربط.`}
              </div>
            </>
          ) : (
            /* لا نظير لهذه اللعبة في المكتبة: يُختار مرّةً واحدة، ولا كتابة يدوية */
            <div style={{ ...hint, marginBottom: 16, display: "flex", gap: 10,
              alignItems: "center", flexWrap: "wrap" }}>
              <span>
                هذه اللعبة غير مرتبطة بالمكتبة العالمية، وأرقام الربط تأتي منها حصراً.
                اربطها بنظيرتها لتظهر لك أرقامها:
              </span>
              <select style={{ width: 240 }} value={linkTo} onChange={(e) => setLinkTo(e.target.value)}>
                <option value="">— اختر لعبة من المكتبة —</option>
                {libGames.map((g) => (
                  <option key={g.id} value={g.id}>{g.name} ({g.packages} باقة)</option>
                ))}
              </select>
              <button type="button" className="btn g" style={{ height: 32 }}
                disabled={!linkTo} onClick={linkLibrary}>
                <Icon name="link" size={14} style={{ marginInlineEnd: 4 }} />ربط
              </button>
              {libGames.length === 0 && (
                <span style={{ color: "var(--debt)" }}>
                  لا ألعاب في المكتبة بعد — يضيفها مالك المنصّة من لوحته.
                </span>
              )}
            </div>
          )}
          {addErr && <div style={{ color: "var(--debt)", fontSize: 13, marginBottom: 10 }}>{addErr}</div>}

          {/* جدول المنتجات */}
          <table style={table}>
            <thead>
              <tr>
                {["المنتج", "التكلفة", "الموصى", "الربح", "رقم الربط", "المزوّد",
                  "الحالة", "Parçalı", "التاريخ", "إجراء"].map((h) => (
                  <th key={h} style={th}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {game.products.length === 0 ? (
                <tr><td colSpan={10} style={{ ...td, padding: 24 }}>لا توجد منتجات — أضف أول منتج بالأعلى</td></tr>
              ) : (
                game.products.map((p: Product, i) => (
                  <tr key={p.id} style={{ background: i % 2 ? "var(--row-alt)" : "#fff" }}>
                    <td style={{ ...td, textAlign: "right", paddingInlineStart: 12, fontWeight: 600 }}>
                      <CellEdit value={p.name} width={140} align="right"
                        onSave={(v) => patchProduct(p.id, { name: v })} />
                      {p.sale_type === "amount" && (
                        <div style={amountTag} title="يكتب الوكيل كميته بين الحدّين — والسعران لكل كتلة">
                          ⚖ بالكمية · {fmtQty(p.qty_min)}–{fmtQty(p.qty_max)}
                        </div>
                      )}
                    </td>
                    <td style={td}>
                      <CellEdit value={editValue(p.cost_price, p)} width={78} numeric
                        format={(v) => fmtPrecise(Number(v))}
                        onSave={(v) => patchProduct(p.id, { cost_price: toBlock(v || "0", p) })} />
                      {p.sale_type === "amount" && <div style={perUnit}>للوحدة</div>}
                    </td>
                    <td style={td}>
                      <CellEdit value={editValue(p.recommended_price, p)} width={78} numeric
                        format={(v) => fmtPrecise(Number(v))}
                        onSave={(v) => patchProduct(p.id, { recommended_price: toBlock(v || "0", p) })} />
                      {p.sale_type === "amount" && <div style={perUnit}>للوحدة</div>}
                    </td>
                    <td style={{ ...td, color: Number(p.profit) < 0 ? "var(--debt)" : "var(--ok)", fontWeight: 600 }}>
                      {showPrice(p.profit, p)}
                    </td>
                    <td style={td} title="رقم الربط ثابت — مصدره المكتبة العالمية">
                      {p.kupur
                        ? <code style={linkCode}>{p.kupur}</code>
                        : <span style={{ color: "var(--debt)", fontSize: 12 }}>بلا رقم ⚠</span>}
                    </td>
                    <td style={{ ...td, fontSize: 13 }}>
                      {providers.find((v) => v.id === p.provider)?.name
                        || <span style={{ color: "var(--muted)" }}>غير موجَّه</span>}
                    </td>
                    <td style={td}>{p.status_label}</td>
                    <td style={td}>{p.is_parcali ? "نعم" : "لا"}</td>
                    <td style={{ ...td, color: "var(--muted)", fontSize: 13 }}>{(p as any).created_at}</td>
                    <td style={td}>
                      <div style={{ display: "flex", gap: 4, justifyContent: "center" }}>
                        <button type="button" title="تعديل بيانات الباقة" style={iconBtn}
                          onClick={() => setEditing({ product: p, mode: "edit" })}>
                          <Icon name="edit" size={15} color="var(--primary)" />
                        </button>
                        <button type="button" title="التوجيه إلى المزوّدين" style={iconBtn}
                          onClick={() => setEditing({ product: p, mode: "routing" })}>
                          <Icon name="settings" size={15} />
                        </button>
                        <button type="button" title="حذف الباقة" style={iconBtn}
                          onClick={() => deleteProduct(p)}>
                          <Icon name="trash" size={15} color="var(--debt)" />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {editing && (
        <ProductModal
          product={editing.product}
          mode={editing.mode}
          providers={providers}
          onClose={() => setEditing(null)}
          onSaved={() => { setEditing(null); load(); }}
        />
      )}
    </div>
  );
}

/**
 * خلية قابلة للتحرير داخل الجدول — اضغطها فتصير حقلاً، وتُحفظ عند الخروج أو Enter.
 *
 * الاسم والتكلفة والسعر الموصى يملكها صاحب المتجر، فتُحرَّر من مكانها بلا نافذة.
 * رقم الربط ليس منها: مصدره المكتبة العالمية وهو جسر ثابت، فيُعرض نصّاً فقط.
 */
function CellEdit({
  value, width, numeric, align, format, onSave,
}: {
  value: string;
  width: number;
  numeric?: boolean;
  align?: "right" | "center";
  format?: (v: string) => string;
  onSave: (v: string) => Promise<void>;
}) {
  const [open, setOpen] = useState(false);
  const [v, setV] = useState(value);
  const [busy, setBusy] = useState(false);

  useEffect(() => { setV(value); }, [value]);

  async function commit() {
    setOpen(false);
    const next = v.trim();
    if (next === value.trim()) return;
    setBusy(true);
    try {
      await onSave(next);
    } catch {
      setV(value);   // فشل الحفظ ⇒ ترتدّ الخلية لقيمتها المحفوظة
    } finally {
      setBusy(false);
    }
  }

  if (!open) {
    return (
      <button type="button" onClick={() => setOpen(true)} disabled={busy}
        title="اضغط للتعديل"
        style={{
          background: "none", border: 0, borderBottom: "1px dashed var(--border)",
          padding: "2px 4px", cursor: "text", font: "inherit", color: "inherit",
          width, textAlign: align || "center", opacity: busy ? 0.5 : 1,
        }}>
        {busy ? "…" : (format ? format(value) : value) || "—"}
      </button>
    );
  }
  return (
    <input autoFocus value={v} style={{ width }} dir={numeric ? "ltr" : undefined}
      type={numeric ? "number" : "text"} step={numeric ? "any" : undefined}
      onChange={(e) => setV(e.target.value)}
      onBlur={commit}
      onKeyDown={(e) => {
        if (e.key === "Enter") commit();
        if (e.key === "Escape") { setV(value); setOpen(false); }
      }} />
  );
}

/** نافذة الباقة: تعديل البيانات · أو ضبط التوجيه ورقم الربط لدى المزوّد. */
function ProductModal({
  product, mode, providers, onClose, onSaved,
}: {
  product: Product;
  mode: "edit" | "routing";
  providers: Provider[];
  onClose: () => void;
  onSaved: () => void;
}) {
  const [f, setF] = useState({
    name: product.name,
    // بالكمية: يُعرض ويُكتب سعر الوحدة، ويُحفظ لكل كتلة
    cost_price: editValue(product.cost_price, product),
    recommended_price: editValue(product.recommended_price, product),
    kupur: product.kupur,
    status: product.status,
    is_parcali: product.is_parcali,
    execution_type: product.execution_type,
    description: product.description,
    provider_package_id: product.provider_package_id,
    provider: product.provider,
    provider_alt1: product.provider_alt1,
    provider_alt2: product.provider_alt2,
    qty_min: String(product.qty_min ?? 1),
    qty_max: String(product.qty_max ?? 1),
  });
  const [busy, setBusy] = useState(false);
  const isAmount = product.sale_type === "amount";
  const [err, setErr] = useState("");

  const upd = (k: keyof typeof f, v: any) => setF((s) => ({ ...s, [k]: v }));

  async function save() {
    setBusy(true);
    setErr("");
    // كل نافذة ترسل حقولها فقط — لئلا تدهس نافذةٌ حقولَ الأخرى
    const body: any = mode === "edit"
      ? {
          // بلا kupur — رقم الربط جسر ثابت يأتي من المكتبة العالمية
          name: f.name, cost_price: toBlock(f.cost_price || "0", product),
          recommended_price: toBlock(f.recommended_price || "0", product),
          status: f.status, is_parcali: f.is_parcali,
          execution_type: f.execution_type, description: f.description,
          ...(isAmount ? { qty_min: Number(f.qty_min) || 1, qty_max: Number(f.qty_max) || 1 } : {}),
        }
      : {
          provider_package_id: f.provider_package_id.trim(),
          provider: f.provider || null,
          provider_alt1: f.provider_alt1 || null,
          provider_alt2: f.provider_alt2 || null,
        };
    if (isAmount && Number(f.qty_min) > Number(f.qty_max)) {
      setErr("أقل كمية يجب ألا تتجاوز أكبر كمية");
      setBusy(false);
      return;
    }
    try {
      await api.patch(`/catalog/products/${product.id}/`, body);
      onSaved();
    } catch (e: any) {
      setErr(e?.response?.data?.detail || "تعذّر الحفظ — تحقّق من القيم");
      setBusy(false);
    }
  }

  return (
    <div style={overlay} onClick={onClose}>
      <div style={modal} onClick={(e) => e.stopPropagation()}>
        <div style={panelHead}>
          {mode === "edit" ? "تعديل الباقة" : "التوجيه إلى المزوّدين"} — {product.game_name} / {product.name}
        </div>
        <div style={{ padding: 18, display: "grid", gap: 12 }}>
          {mode === "edit" ? (
            <>
              <Field label="اسم الباقة">
                <input style={mInp} value={f.name} onChange={(e) => upd("name", e.target.value)} />
              </Field>
              <div style={{ display: "flex", gap: 10 }}>
                <Field label={isAmount ? "تكلفة الوحدة" : "التكلفة"}>
                  <input style={{ ...mInp, width: 120 }} type="number" step="any"
                    value={f.cost_price} onChange={(e) => upd("cost_price", e.target.value)} />
                </Field>
                <Field label={isAmount ? "سعر الوحدة الموصى" : "السعر الموصى"}>
                  <input style={{ ...mInp, width: 120 }} type="number" step="any"
                    value={f.recommended_price} onChange={(e) => upd("recommended_price", e.target.value)} />
                </Field>
                <Field label="رقم الربط (ثابت)">
                  <div style={{ ...mInp, width: 110, padding: "6px 8px", direction: "ltr",
                    background: "var(--row-alt)", border: "1px solid var(--border)",
                    borderRadius: 4, color: "var(--muted)", fontSize: 13 }}
                    title="مصدره المكتبة العالمية — لا يُعدَّل">
                    {f.kupur || "—"}
                  </div>
                </Field>
              </div>
              <div style={{ display: "flex", gap: 10 }}>
                <Field label="الحالة">
                  <select style={{ ...mInp, width: 180 }} value={f.status}
                    onChange={(e) => upd("status", e.target.value)}>
                    <option value="active">نشط</option>
                    <option value="passive">معطّل</option>
                    <option value="sale_paused">بيع موقوف مؤقتاً</option>
                  </select>
                </Field>
                <Field label="نوع التنفيذ">
                  <select style={{ ...mInp, width: 180 }} value={f.execution_type}
                    onChange={(e) => upd("execution_type", e.target.value)}>
                    <option value="auto">تلقائي</option>
                    <option value="manual">يدوي</option>
                  </select>
                </Field>
                <Field label="Parçalı">
                  <Toggle on={f.is_parcali} onChange={(v) => upd("is_parcali", v)} />
                </Field>
              </div>
              <Field label="الوصف">
                <input style={mInp} value={f.description}
                  onChange={(e) => upd("description", e.target.value)} />
              </Field>
              {isAmount && (
                <>
                  <div style={{ display: "flex", gap: 10, alignItems: "end" }}>
                    <Field label="أقل كمية">
                      <input style={{ ...mInp, width: 140 }} type="number" min={1} dir="ltr"
                        value={f.qty_min} onChange={(e) => upd("qty_min", e.target.value)} />
                    </Field>
                    <Field label="أكبر كمية">
                      <input style={{ ...mInp, width: 140 }} type="number" min={1} dir="ltr"
                        value={f.qty_max} onChange={(e) => upd("qty_max", e.target.value)} />
                    </Field>
                  </div>
                  <div style={hint}>
                    ⚖ باقة بالكمية: السعران أعلاه <b>للوحدة الواحدة</b> (مثل 0.03)، ويكتب الوكيل كميته بين
                    الحدّين فيُحسب ما يدفعه = سعر الوحدة × الكمية. ضيّق الحدّين إن شئت، ولا توسّعهما أبعد
                    ممّا يقبله المزوّد.
                  </div>
                </>
              )}
            </>
          ) : (
            <>
              <Field label="معرّف الباقة لدى المزوّد">
                <input style={mInp} value={f.provider_package_id} dir="ltr"
                  placeholder="مثال: 1547"
                  onChange={(e) => upd("provider_package_id", e.target.value)} />
              </Field>
              <div style={hint}>
                لا تخلطه برقم الربط: رقم الربط ({product.kupur || "—"}) جسرك أنت،
                مصدره المكتبة العالمية وواحد لكل باقة. أمّا هذا فرقم الباقة **في دفاتر
                المزوّد** ويختلف من مزوّد لآخر — يُرسَل كـ <code>package_id</code>،
                وبدونه لا يعرف المزوّد أيّ باقة تقصد. للأرقام لكل مزوّد على حدة
                استخدم صفحة «ربط الباقات».
              </div>
              <ProviderPick label="API القابلة للإرسال (الرئيسي)" providers={providers}
                value={f.provider} onChange={(v) => upd("provider", v)} />
              <ProviderPick label="API 1 (بديل أول)" providers={providers}
                value={f.provider_alt1} onChange={(v) => upd("provider_alt1", v)} />
              <ProviderPick label="API 2 (بديل ثانٍ)" providers={providers}
                value={f.provider_alt2} onChange={(v) => upd("provider_alt2", v)} />
              {f.execution_type !== "auto" && (
                <div style={{ ...hint, color: "var(--debt)" }}>
                  ⚠ تنفيذ هذه الباقة <b>يدوي</b> — لن تُرسَل آلياً للمزوّد مهما ضبطت التوجيه.
                  غيّره من زر التعديل ✏ إلى «تلقائي».
                </div>
              )}
            </>
          )}

          {err && <div style={{ color: "var(--debt)", fontSize: 13 }}>{err}</div>}
          <div style={{ display: "flex", gap: 8, marginTop: 4 }}>
            <button className="btn g" onClick={save} disabled={busy}>
              {busy ? "جارٍ الحفظ..." : "حفظ"}
            </button>
            <button className="btn" style={{ background: "#8a999e" }} onClick={onClose}>إلغاء</button>
          </div>
        </div>
      </div>
    </div>
  );
}

function ProviderPick({
  label, providers, value, onChange,
}: {
  label: string;
  providers: Provider[];
  value: number | null;
  onChange: (v: number | null) => void;
}) {
  return (
    <Field label={label}>
      <select style={mInp} value={value ?? ""}
        onChange={(e) => onChange(e.target.value ? Number(e.target.value) : null)}>
        <option value="">— بديل مغلق —</option>
        {providers.map((v) => (
          <option key={v.id} value={v.id}>{v.name} ({v.type_label})</option>
        ))}
      </select>
    </Field>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div style={{ display: "flex", alignItems: "start", gap: 14, marginBottom: 12 }}>
      <div style={{ width: 150, textAlign: "left", color: "var(--muted)", fontSize: 14, paddingTop: 7 }}>
        {label} :
      </div>
      <div style={{ flex: 1 }}>{children}</div>
    </div>
  );
}
function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <div style={{ fontSize: 12, color: "var(--muted)", marginBottom: 4 }}>{label}</div>
      {children}
    </div>
  );
}
function Toggle({ on, onChange }: { on: boolean; onChange: (v: boolean) => void }) {
  return (
    <button type="button" onClick={() => onChange(!on)}
      style={{
        border: 0, borderRadius: 4, padding: "6px 16px", color: "#fff", fontSize: 13,
        background: on ? "var(--ok)" : "#8a999e",
      }}>
      {on ? "نشط" : "معطّل"}
    </button>
  );
}

const panel: React.CSSProperties = {
  background: "#fff",
  border: "1px solid var(--border)",
  borderRadius: 8,
  overflow: "hidden",
};
const panelHead: React.CSSProperties = {
  background: "var(--primary)",
  color: "#fff",
  padding: "10px 18px",
  fontSize: 15,
  fontWeight: 700,
};
const inp: React.CSSProperties = { width: "100%", maxWidth: 460 };
const iconBtn: React.CSSProperties = {
  background: "none", border: 0, padding: 2, cursor: "pointer",
  color: "var(--muted)", display: "inline-flex", alignItems: "center",
};
const linkCode: React.CSSProperties = {
  background: "var(--row-alt)", border: "1px solid var(--border)", borderRadius: 4,
  padding: "2px 7px", fontSize: 12.5, direction: "ltr", display: "inline-block",
};
const overlay: React.CSSProperties = {
  position: "fixed", inset: 0, background: "rgba(0,0,0,.45)",
  display: "flex", alignItems: "center", justifyContent: "center", zIndex: 60,
};
const modal: React.CSSProperties = {
  background: "#fff", borderRadius: 8, width: 560, maxWidth: "94vw",
  maxHeight: "90vh", overflow: "auto", boxShadow: "0 10px 40px rgba(0,0,0,.3)",
};
const mInp: React.CSSProperties = { width: "100%" };
const hint: React.CSSProperties = {
  fontSize: 12.5, color: "var(--muted)", lineHeight: 1.7,
  background: "var(--row-alt)", border: "1px solid var(--border)",
  borderRadius: 6, padding: "8px 10px",
};
const table: React.CSSProperties = {
  width: "100%", borderCollapse: "collapse", background: "var(--surface)", fontSize: 13.5,
};
const th: React.CSSProperties = {
  background: "var(--th-bg)", color: "var(--th-ink)", padding: "11px 10px",
  textAlign: "center", fontWeight: 800, fontSize: 12.5, whiteSpace: "nowrap",
  border: "1px solid var(--border)", borderTop: 0,
};
const td: React.CSSProperties = {
  padding: 10, textAlign: "center", whiteSpace: "nowrap", verticalAlign: "middle",
  background: "var(--surface)", border: "1px solid var(--border)",
  borderBottom: "3px solid var(--row-sep)",
};

/** 100000 ⇐ «100,000» */
function fmtQty(n?: number) {
  return Number(n || 0).toLocaleString("en-US");
}
const amountTag: React.CSSProperties = {
  fontSize: 11, fontWeight: 700, color: "#7c3aed", marginTop: 2,
};
const perUnit: React.CSSProperties = { fontSize: 10.5, color: "var(--muted)" };
