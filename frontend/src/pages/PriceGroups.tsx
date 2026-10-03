import { Fragment, useEffect, useMemo, useState } from "react";
import { editValue, isAmountP, showPrice, toBlock } from "../unitPrice";
import { api, type Provider } from "../api";
import Icon from "../components/Icon";
import ProductPicker, { type PickerProduct } from "../components/ProductPicker";
import ScrollTop from "../components/ScrollTop";
import { matches } from "../search";

/** قاعدة تسعير مرتبطة بالتكلفة — فارغة تعني سعراً يدوياً جامداً. */
interface Margin { mode: "percent" | "fixed"; value: string; round?: boolean }
interface Cell { price: string; custom: boolean; margin: Margin | null }

/** وسم القاعدة كما يُقرأ: «3%» أو «+0.20» — و«↑» إن كانت تقرّب لأعلى. */
function marginLabel(m: Margin): string {
  const v = Number(m.value);
  const n = Number.isInteger(v) ? String(v) : String(Number(v.toFixed(4)));
  return (m.mode === "percent" ? `${n}%` : `+${n}`) + (m.round ? "↑" : "");
}
interface MatrixProduct {
  id: number; name: string; cost_price: string; recommended_price: string;
  sale_type?: string; qty_unit?: number;
  prices: Record<string, Cell>;
}
interface MatrixGame { game_id: number; game_name: string; products: MatrixProduct[] }
interface Group { id: number; name: string; dealer_count?: number }
/** ربط باقة لدى مزوّد — رقمه هناك وآخر سعر معروف له (بعملة الدفتر). */
interface ProviderLink {
  product: number; provider: number; package_id: string;
  extra: Record<string, string>;
}

/**
 * رقم الربط كما يميّز الباقة فعلاً.
 * زينت يرقّم بـ`package_id` **اللعبة**، والباقة داخلها يميّزها `kupur` —
 * فالرقم وحده يتكرّر على كل باقات اللعبة ولا يدلّ على شيء.
 */
function linkCode(l: ProviderLink): string {
  const kupur = l.extra?.kupur;
  return kupur ? `${l.package_id}/${kupur}` : l.package_id;
}

// عمود الخلية قيد التحرير: رقم مجموعة، أو عمودا المنتج نفسه
type Col = number | "cost" | "rec";

export default function PriceGroups() {
  const [groups, setGroups] = useState<Group[]>([]);
  const [games, setGames] = useState<MatrixGame[]>([]);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState<{ p: number; g: Col } | null>(null);
  const [draft, setDraft] = useState("");
  const [dialog, setDialog] = useState<"bulk" | "rec" | "costs" | "delete" | null>(null);
  const [toast, setToast] = useState("");
  const [q, setQ] = useState("");

  function load() {
    setLoading(true);
    api.get("/catalog/price-matrix/")
      .then((r) => { setGroups(r.data.groups); setGames(r.data.games); })
      .finally(() => setLoading(false));
  }
  useEffect(() => load(), []);

  /** الباقات مسطّحةً مع اسم لعبتها — تتشاركها نوافذ التسعير والتكاليف. */
  const allProducts = useMemo<PickerProduct[]>(
    () => games.flatMap((g) => g.products.map((p) => ({
      id: p.id, name: p.name, game_name: g.game_name,
    }))),
    [games],
  );
  const costOf = useMemo(() => {
    const m = new Map<number, string>();
    for (const g of games) for (const p of g.products) m.set(p.id, p.cost_price);
    return m;
  }, [games]);
  /** باقات «بالكمية» — لا يمسّها التقريب لأن سعرها لكتلة لا لوحدة */
  const amountIds = useMemo(
    () => new Set(games.flatMap((g) => g.products).filter(isAmountP).map((p) => p.id)),
    [games],
  );

  function done(message: string) {
    setDialog(null);
    setToast(message);
    setTimeout(() => setToast(""), 6000);
    load();
  }

  async function createGroup() {
    const name = prompt("اسم مجموعة الأسعار الجديدة:");
    if (!name) return;
    await api.post("/catalog/price-groups/", { name });
    load();
  }

  /** الباقة بمعرّفها — لتحويل سعر الوحدة المكتوب إلى سعر الكتلة المخزّن */
  const prodOf = (id: number) => games.flatMap((g) => g.products).find((p) => p.id === id);

  async function saveCell(productId: number, groupId: number) {
    const typed = draft.trim();
    const value = typed === "" ? "" : toBlock(typed, prodOf(productId));
    setEditing(null);
    if (value === "") return;
    await api.post("/catalog/set-price/", { product: productId, price_group: groupId, price: value });
    // تحديث محلي فوري
    setGames((gs) => gs.map((game) => ({
      ...game,
      products: game.products.map((p) =>
        // التعديل اليدوي يفكّ ارتباط الخلية بقاعدة التسعير — كما يفعل الخادم
        p.id === productId
          ? { ...p, prices: { ...p.prices, [groupId]: { price: value, custom: true, margin: null } } }
          : p),
    })));
  }

  /** حفظ التكلفة أو السعر الموصى — نفس حقلَي المنتج المُحرَّرين من باقات المنتجات،
   *  فالتعديل من هنا أو من هناك يصلان إلى السجلّ ذاته. */
  async function saveProductField(productId: number, field: "cost_price" | "recommended_price") {
    const typed = draft.trim();
    const value = typed === "" ? "" : toBlock(typed, prodOf(productId));
    setEditing(null);
    if (value === "") return;
    await api.patch(`/catalog/products/${productId}/`, { [field]: value });

    // تغيّر التكلفة يجرّ معه كل خلية مرتبطة بقاعدة — والخادم هو من يحسبها،
    // فنعيد التحميل بدل أن نخمّن النتيجة هنا ونخالفه.
    if (field === "cost_price") return load();

    setGames((gs) => gs.map((game) => ({
      ...game,
      products: game.products.map((p) => {
        if (p.id !== productId) return p;
        const next = { ...p, [field]: value };
        // السعر الموصى هو افتراضي الخلايا غير المخصّصة — فتتبعه فوراً
        next.prices = Object.fromEntries(
          Object.entries(p.prices).map(([gid, c]) =>
            [gid, c.custom ? c : { ...c, price: value, custom: false }]),
        );
        return next;
      }),
    })));
  }

  function startEdit(productId: number, col: Col, current: string) {
    if (editing?.p === productId && editing?.g === col) return;
    setEditing({ p: productId, g: col });
    setDraft(current);
  }


  /** حقل التحرير المشترك لكل الخلايا. */
  function cellInput(commit: () => void) {
    return (
      <input autoFocus type="number" step="any" value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onBlur={commit}
        onKeyDown={(e) => {
          if (e.key === "Enter") commit();
          // الإلغاء: تفريغ المسودّة يجعل الحفظ (بما فيه onBlur اللاحق) بلا أثر
          if (e.key === "Escape") { setDraft(""); setEditing(null); }
        }}
        style={{ width: 80, height: 26 }} />
    );
  }

  // البحث السريع: اللعبة كلّها إن طابق اسمها، وإلا باقاتها المطابقة وحدها
  const shownGames = q.trim()
    ? games
      .map((g) => matches(q, g.game_name)
        ? g
        : { ...g, products: g.products.filter((p) => matches(q, p.name, p.id)) })
      .filter((g) => g.products.length > 0)
    : games;

  if (loading) return <div style={{ padding: 30 }}>جارٍ التحميل...</div>;

  return (
    <div style={{ padding: 16 }}>
      <h2 style={{ fontSize: 20, color: "var(--primary-dark)", marginBottom: 12 }}>
        مجموعات الأسعار (Fiyat Grupları)
      </h2>

      {/* شريط الأدوات */}
      {/* «تعديل سعر الصرف» أُزيل — مرجع الصرف الوحيد صار «الإعدادات ← أسعار الصرف» */}
      <div style={toolbar}>
        <button className="btn g" onClick={createGroup}><Icon name="plus" size={15} style={ib} />إنشاء مجموعة أسعار</button>
        <button className="btn" onClick={() => setDialog("bulk")}><Icon name="chart" size={15} style={ib} />تسعير جماعي</button>
        <button className="btn" onClick={() => setDialog("rec")}><Icon name="chart" size={15} style={ib} />تحديد السعر الموصى</button>
        <button className="btn" onClick={() => setDialog("costs")}><Icon name="refresh" size={15} style={ib} />تحديث التكاليف</button>
        <button className="btn r" onClick={() => setDialog("delete")}><Icon name="trash" size={15} style={ib} />حذف مجموعة</button>
        <input placeholder="بحث سريع: لعبة أو باقة أو Id..." value={q} onChange={(e) => setQ(e.target.value)}
          style={{ width: 260, marginInlineStart: "auto" }} />
      </div>
      <div style={note}>
        اضغط على أي خلية سعر لتعديلها. الخلية <b style={{ color: "var(--primary-dark)" }}>الملوّنة</b> = سعر
        مخصّص، والرمادية = السعر الموصى (افتراضي). عمودا <b>التكلفة</b> و<b>الموصى</b> قابلان للتعديل هنا
        أيضاً، وهما نفس القيمتين في باقات المنتجات — التعديل من أيّ الجهتين يُحدّث الأخرى.
        <div style={{ marginTop: 6 }}>
          الخلية التي عليها وسم مثل <sup style={{ ...linkTag, position: "static" }}>3%</sup>{" "}
          <b>مرتبطة بالتكلفة</b>: تُعاد حسابها تلقائياً كلّما تغيّرت التكلفة — بتحرير العمود
          أو بـ«تحديث التكاليف». ويُفكّ الارتباط بأمرين: تسعير جماعي جديد يحلّ محلّه،
          أو تعديل الخلية بيدك.
        </div>
      </div>

      <div style={{ overflowX: "auto" }}>
        <table style={table}>
          <thead>
            <tr>
              <th style={{ ...th, width: 50 }}>Id</th>
              <th style={{ ...th, textAlign: "right", paddingInlineStart: 12 }}>المنتج</th>
              <th style={th}>التكلفة</th>
              <th style={th}>الموصى</th>
              {groups.map((g) => (
                <th key={g.id} style={{ ...th, background: "var(--primary)" }}>مجموعة {g.name}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {q.trim() && shownGames.length === 0 && (
              <tr><td colSpan={4 + groups.length} style={{ ...td, padding: 24 }}>لا شيء يطابق «{q.trim()}»</td></tr>
            )}
            {shownGames.map((game) => (
              <Fragment key={game.game_id}>
                <tr><td colSpan={4 + groups.length} style={groupHead}>{game.game_name}</td></tr>
                {game.products.map((p, i) => (
                  <tr key={p.id} style={{ background: i % 2 ? "var(--row-alt)" : "#fff" }}>
                    <td style={{ ...td, color: "var(--muted)" }}>{p.id}</td>
                    <td style={{ ...td, textAlign: "right", paddingInlineStart: 12, fontWeight: 600 }}>
                      {p.name}
                      {isAmountP(p) && <span style={unitTag} title="باقة بالكمية — الأسعار في صفّها للوحدة الواحدة">⚖ للوحدة</span>}
                    </td>
                    <td style={{ ...td, color: "var(--muted)", cursor: "pointer" }}
                      onClick={() => startEdit(p.id, "cost", editValue(p.cost_price, p))}>
                      {editing?.p === p.id && editing?.g === "cost"
                        ? cellInput(() => saveProductField(p.id, "cost_price"))
                        : showPrice(p.cost_price, p)}
                    </td>
                    <td style={{ ...td, cursor: "pointer" }}
                      onClick={() => startEdit(p.id, "rec", editValue(p.recommended_price, p))}>
                      {editing?.p === p.id && editing?.g === "rec"
                        ? cellInput(() => saveProductField(p.id, "recommended_price"))
                        : showPrice(p.recommended_price, p)}
                    </td>
                    {groups.map((g) => {
                      const cell = p.prices[g.id];
                      const isEditing = editing?.p === p.id && editing?.g === g.id;
                      return (
                        <td key={g.id} style={{ ...td, cursor: "pointer",
                          color: cell?.custom ? "var(--primary-dark)" : "var(--muted)",
                          fontWeight: cell?.custom ? 700 : 400 }}
                          onClick={() => startEdit(p.id, g.id, editValue(cell?.price ?? "", p))}
                          title={cell?.margin
                            ? `مرتبطة بالتكلفة: ${marginLabel(cell.margin)} — تتبعها كلّما تغيّرت. التعديل اليدوي يفكّ الارتباط.`
                            : undefined}>
                          {isEditing
                            ? cellInput(() => saveCell(p.id, g.id))
                            : (
                              <>
                                {showPrice(cell?.price ?? "0", p)}
                                {cell?.margin && (
                                  <sup style={linkTag}>{marginLabel(cell.margin)}</sup>
                                )}
                              </>
                            )}
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

      {(dialog === "bulk" || dialog === "rec") && (
        <BulkPriceModal groups={groups} products={allProducts} costOf={costOf} amountIds={amountIds}
          initial={dialog === "rec" ? "recommended" : undefined}
          onClose={() => setDialog(null)} onDone={done} />
      )}
      {dialog === "costs" && (
        <RefreshCostsModal products={allProducts} onClose={() => setDialog(null)} onDone={done} />
      )}
      {dialog === "delete" && (
        <DeleteGroupModal onClose={() => setDialog(null)} onDone={done} />
      )}

      {toast && <div style={toastBox}>{toast}</div>}
      <ScrollTop />
    </div>
  );
}

/* ─────────────────────────── النوافذ ─────────────────────────── */

/** هيكل نافذة مشترك: غطاء + رأس + جسم + ذيل. */
function Modal({ title, onClose, children, footer }: {
  title: string; onClose: () => void;
  children: React.ReactNode; footer: React.ReactNode;
}) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div style={overlay} onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div style={box}>
        <div style={head}>
          {title}
          <button type="button" style={xBtn} onClick={onClose}>✕</button>
        </div>
        <div style={{ padding: 16 }}>{children}</div>
        <div style={foot}>{footer}</div>
      </div>
    </div>
  );
}

function Field({ label, hint, children }: {
  label: string; hint?: string; children: React.ReactNode;
}) {
  return (
    <div style={{ marginBottom: 14 }}>
      <label style={fieldLabel}>{label}</label>
      {children}
      {hint && <div style={fieldHint}>{hint}</div>}
    </div>
  );
}

/**
 * تسعير جماعي — سعر مجموعة أسعار بعينها، أو السعر الموصى، = تكلفة كل باقة + هامش،
 * مقرّباً لأعلى إلى رقم صحيح إن اختار المالك ذلك.
 * الأساس التكلفة لا السعر الحالي، فتكرار التطبيق لا يضاعف الزيادة.
 */
function BulkPriceModal({ groups, products, costOf, amountIds, initial, onClose, onDone }: {
  groups: Group[];
  products: PickerProduct[];
  costOf: Map<number, string>;
  amountIds: Set<number>;
  initial?: "recommended";
  onClose: () => void;
  onDone: (message: string) => void;
}) {
  const [group, setGroup] = useState<number | "recommended">(initial ?? groups[0]?.id ?? "recommended");
  const [picked, setPicked] = useState<number[]>([]);
  const [mode, setMode] = useState<"percent" | "fixed">("percent");
  const [value, setValue] = useState("");
  const [round, setRound] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const toRec = group === "recommended";

  // معاينة على باقة حقيقية — الرقم المجرّد لا يُطمئن، والمثال يُطمئن
  const sample = useMemo(() => {
    const id = picked[0] ?? products[0]?.id;
    const cost = Number(costOf.get(id!) ?? 0);
    const v = Number(value);
    if (!id || !cost || !value || Number.isNaN(v)) return null;
    // التقريب إلى السنت أوّلاً كالخادم — وإلا رفع 1.0000001 إلى 2
    let after = Math.round((mode === "percent" ? cost * (1 + v / 100) : cost + v) * 100) / 100;
    if (round && !amountIds.has(id)) after = Math.ceil(after);
    return { name: products.find((p) => p.id === id)?.name ?? "", cost, after };
  }, [picked, products, costOf, amountIds, mode, value, round]);

  async function apply() {
    setErr("");
    setBusy(true);
    try {
      const r = await api.post("/catalog/bulk-price/", {
        price_group: group, products: picked, mode, value, round,
      });
      const skipped = (r.data.skipped_zero_cost || []) as string[];
      const unrounded = (r.data.not_rounded || []) as string[];
      const list = (xs: string[]) => `${xs.slice(0, 3).join("، ")}${xs.length > 3 ? "…" : ""}`;
      onDone(
        `✅ سُعّرت ${r.data.updated} باقة ${toRec ? "في السعر الموصى" : `في مجموعة ${r.data.group}`}` +
        (skipped.length ? ` — وتُركت ${skipped.length} باقة تكلفتها صفر: ${list(skipped)}` : "") +
        (unrounded.length ? ` — ولم تُقرَّب ${unrounded.length} باقة بالكمية: ${list(unrounded)}` : ""),
      );
    } catch (e: any) {
      setErr(e?.response?.data?.detail || "تعذّر التسعير");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal title={toRec ? "تحديد السعر الموصى" : "تسعير جماعي"} onClose={onClose} footer={
      <>
        {err && <span style={errText}>{err}</span>}
        <button className="btn" style={{ marginInlineStart: "auto" }} onClick={onClose}>إلغاء</button>
        <button className="btn g" disabled={busy || value === ""} onClick={apply}>
          {busy ? "جارٍ التسعير..." : "تطبيق"}
        </button>
      </>
    }>
          <Field label="أين يُكتب السعر" hint={toRec
            ? "يُكتب في عمود «الموصى» — وكل خلية مجموعة غير مخصّصة (رمادية) تتبعه."
            : "السعر يُكتب في عمود هذه المجموعة وحدها ويصير مخصّصاً."}>
            <select value={group}
              onChange={(e) => setGroup(e.target.value === "recommended" ? "recommended" : Number(e.target.value))}
              style={input}>
              {groups.map((g) => <option key={g.id} value={g.id}>مجموعة {g.name}</option>)}
              <option value="recommended">السعر الموصى</option>
            </select>
          </Field>

          <Field label="الباقات" hint="بجانب كل باقة تكلفتها — وعليها يُحسب السعر. اتركه فارغاً ليشمل كل الباقات.">
            <ProductPicker products={products} value={picked} onChange={setPicked}
              meta={(id) => {
                const cost = Number(costOf.get(id) ?? 0);
                return cost > 0
                  ? <b style={{ direction: "ltr", color: "var(--primary-dark)" }}>{cost.toFixed(2)}</b>
                  : <span style={{ color: "var(--danger)" }}>بلا تكلفة</span>;
              }} />
          </Field>

          <Field label="نوع الهامش">
            <select value={mode} onChange={(e) => setMode(e.target.value as any)} style={input}>
              <option value="percent">نسبة مئوية % من التكلفة</option>
              <option value="fixed">مبلغ ثابت يُضاف إلى التكلفة</option>
            </select>
          </Field>

          <Field label={mode === "percent" ? "النسبة (%)" : "المبلغ"}
            hint="سعر البيع = التكلفة + الهامش. الأساس هو التكلفة دائماً، فإعادة التطبيق لا تضاعف الزيادة.">
            <input type="number" step="0.01" value={value} autoFocus
              onChange={(e) => setValue(e.target.value)} style={input}
              placeholder={mode === "percent" ? "مثال: 25" : "مثال: 0.20"} />
          </Field>

          <label style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 14, cursor: "pointer" }}>
            <input type="checkbox" checked={round} onChange={(e) => setRound(e.target.checked)} />
            <span>
              <b>تقريب لأعلى إلى رقم صحيح</b>{" "}
              <span style={{ color: "var(--muted)" }}>— مثلاً 0.94 ⇐ 1 و 1.30 ⇐ 2. لا يمسّ باقات «بالكمية».</span>
            </span>
          </label>

          <div style={preview}>
            {sample && (
              <div style={{ marginBottom: 6 }}>
                مثال — <b>{sample.name}</b>: تكلفتها {sample.cost.toFixed(2)} ⇐ سعرها{" "}
                <b style={{ color: "var(--primary-dark)" }}>{sample.after.toFixed(2)}</b>
              </div>
            )}
            {toRec ? (
              <>
                ✍️ السعر الموصى يُكتب <b>مرّة واحدة</b> ولا يرتبط بالتكلفة: إن تغيّرت
                التكلفة لاحقاً بقي كما هو حتى تعيد تطبيق هذه النافذة أو تعدّله بيدك.
              </>
            ) : (
              <>
                🔗 الباقات المختارة تبقى <b>مرتبطة</b> بهذه القاعدة{round && " وتقريبها"}: كلّما
                تغيّرت تكلفتها أُعيد حساب سعرها في هذه المجموعة تلقائياً. ويُفكّ الارتباط
                بتسعير جماعي جديد عليها، أو بتعديل سعرها يدوياً في الجدول.
              </>
            )}
          </div>
    </Modal>
  );
}

/** تحديث التكاليف — تكلفتنا تصير سعر المزوّد المختار. */
function RefreshCostsModal({ products, onClose, onDone }: {
  products: PickerProduct[];
  onClose: () => void;
  onDone: (message: string) => void;
}) {
  const [providers, setProviders] = useState<Provider[]>([]);
  const [provider, setProvider] = useState<number | "">("");
  const [links, setLinks] = useState<ProviderLink[]>([]);
  const [picked, setPicked] = useState<number[]>([]);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [report, setReport] = useState<any>(null);

  useEffect(() => {
    api.get("/providers/", { params: { status: "active" } }).then((r) => {
      // المنفّذ اليدوي بلا كتالوج — لا تكاليف تُجلب منه
      const rows = (r.data as Provider[]).filter((p) => p.type !== "loader");
      setProviders(rows);
      setProvider(rows[0]?.id ?? "");
    });
    api.get("/catalog/product-links/").then((r) => setLinks(r.data));
  }, []);

  /** ربط الباقة لدى المزوّد المختار — رقمه وسعره كما نعرفهما الآن. */
  const linkOf = useMemo(() => {
    const m = new Map<number, ProviderLink>();
    for (const l of links) if (l.provider === provider) m.set(l.product, l);
    return m;
  }, [links, provider]);

  async function run() {
    setErr("");
    setReport(null);
    setBusy(true);
    try {
      const r = await api.post("/catalog/refresh-costs/", { provider, products: picked });
      setReport(r.data);
    } catch (e: any) {
      setErr(e?.response?.data?.detail || "تعذّر تحديث التكاليف");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal title="تحديث التكاليف من مزوّد" onClose={onClose} footer={
      <>
        {err && <span style={errText}>{err}</span>}
        <button className="btn" style={{ marginInlineStart: "auto" }}
          onClick={() => (report ? onDone(`✅ حُدّثت ${report.updated.length} تكلفة من «${report.provider}»`) : onClose())}>
          {report ? "تم" : "إلغاء"}
        </button>
        {!report && (
          <button className="btn g" disabled={busy || !provider} onClick={run}>
            {busy ? "جارٍ الجلب..." : "تحديث"}
          </button>
        )}
      </>
    }>
      {report ? (
        <>
          <div style={{ marginBottom: 10 }}>
            من «<b>{report.provider}</b>» — حُدّثت <b>{report.updated.length}</b> تكلفة
            بعملة الدفتر ({report.currency}).
          </div>
          <div style={{ maxHeight: 300, overflowY: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
              <tbody>
                {report.updated.map((u: any, i: number) => (
                  <tr key={i} style={{ borderBottom: "1px solid var(--border)" }}>
                    <td style={{ padding: "5px 8px", textAlign: "right" }}>{u.name}</td>
                    <td style={{ padding: "5px 8px", color: "var(--muted)", direction: "ltr" }}>
                      {u.before} ⇐ <b style={{ color: "var(--primary-dark)" }}>{u.after}</b>
                    </td>
                  </tr>
                ))}
                {report.skipped.map((s: any, i: number) => (
                  <tr key={`s${i}`} style={{ borderBottom: "1px solid var(--border)", opacity: 0.65 }}>
                    <td style={{ padding: "5px 8px", textAlign: "right" }}>{s.name}</td>
                    <td style={{ padding: "5px 8px", fontSize: 12 }}>تُخُطّيت — {s.note}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      ) : providers.length === 0 ? (
        <div style={{ color: "var(--muted)" }}>لا مزوّدين آليين — أضِف مزوّداً من «مزوّدو API».</div>
      ) : (
        <>
          <Field label="المزوّد" hint="تصير تكلفة الباقة عندنا هي سعرها لديه.">
            <select value={provider} onChange={(e) => setProvider(Number(e.target.value))} style={input}>
              {providers.map((p) => (
                <option key={p.id} value={p.id}>{p.name} — {p.type_label}</option>
              ))}
            </select>
          </Field>

          <Field label="الباقات"
            hint="بجانب كل باقة رقم ربطها لدى المزوّد وآخر سعر معروف له. اتركه فارغاً ليشمل كل الباقات المربوطة.">
            <ProductPicker products={products} value={picked} onChange={setPicked}
              placeholder="كل الباقات المربوطة"
              meta={(id) => {
                const link = linkOf.get(id);
                if (!link) return <span style={{ color: "var(--muted)" }}>غير مربوطة</span>;
                return (
                  <>
                    <code style={{ direction: "ltr", color: "var(--muted)" }}>{linkCode(link)}</code>
                    <b style={{ direction: "ltr", color: link.extra?.price ? "var(--primary-dark)" : "var(--muted)" }}>
                      {link.extra?.price ?? "—"}
                    </b>
                  </>
                );
              }} />
          </Field>

          <div style={preview}>
            الباقة <b>غير المربوطة</b> بهذا المزوّد تُتخطّى — اربطها من «ربط الباقات» أولاً.
            وأسعار المزوّدين بالليرة التركية، وتُحوَّل إلى عملة الدفتر بسعر
            «الإعدادات ← أسعار الصرف» قبل الحفظ.
          </div>
        </>
      )}
    </Modal>
  );
}

/** حذف مجموعة أسعار — وكلاؤها ينتقلون إلى «بلا مجموعة» فيشترون بالسعر الموصى. */
function DeleteGroupModal({ onClose, onDone }: {
  onClose: () => void;
  onDone: (message: string) => void;
}) {
  const [rows, setRows] = useState<Group[]>([]);
  const [id, setId] = useState<number | "">("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  useEffect(() => {
    api.get("/catalog/price-groups/").then((r) => {
      setRows(r.data);
      setId(r.data[0]?.id ?? "");
    });
  }, []);

  const chosen = rows.find((g) => g.id === id);

  async function remove() {
    setErr("");
    setBusy(true);
    try {
      await api.delete(`/catalog/price-groups/${id}/`);
      onDone(`🗑 حُذفت مجموعة ${chosen?.name}`);
    } catch (e: any) {
      setErr(e?.response?.data?.detail || "تعذّر الحذف");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal title="حذف مجموعة أسعار" onClose={onClose} footer={
      <>
        {err && <span style={errText}>{err}</span>}
        <button className="btn" style={{ marginInlineStart: "auto" }} onClick={onClose}>إلغاء</button>
        <button className="btn r" disabled={busy || !id} onClick={remove}>
          {busy ? "جارٍ الحذف..." : "حذف"}
        </button>
      </>
    }>
      {rows.length === 0 ? (
        <div style={{ color: "var(--muted)" }}>لا مجموعات أسعار.</div>
      ) : (
        <>
          <Field label="المجموعة">
            <select value={id} onChange={(e) => setId(Number(e.target.value))} style={input}>
              {rows.map((g) => (
                <option key={g.id} value={g.id}>
                  مجموعة {g.name}{g.dealer_count ? ` — ${g.dealer_count} وكيل` : ""}
                </option>
              ))}
            </select>
          </Field>

          <div style={{ ...preview, background: "#fdf3f3", borderColor: "#f0caca", color: "#8a3535" }}>
            يُحذف عمود المجموعة وأسعارها المخصّصة كلّها.
            {!!chosen?.dealer_count && (
              <>
                {" "}و<b>{chosen.dealer_count} وكيل</b> ينتقلون إلى «بلا مجموعة»،
                فيصيرون على <b>السعر الموصى</b> فوراً.
              </>
            )}
            {" "}لا رجعة في هذا.
          </div>
        </>
      )}
    </Modal>
  );
}

const ib: React.CSSProperties = { marginInlineEnd: 5 };
const toolbar: React.CSSProperties = {
  display: "flex", gap: 10, flexWrap: "wrap", marginBottom: 10,
};
const note: React.CSSProperties = {
  background: "#f6f8f9", border: "1px solid #dbe3e5", color: "var(--muted)",
  fontSize: 13, padding: "9px 14px", borderRadius: 6, marginBottom: 14,
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
const groupHead: React.CSSProperties = {
  background: "#f5c518", color: "#4a3c00", fontWeight: 700,
  padding: "7px 14px", textAlign: "right", fontSize: 14,
};
const linkTag: React.CSSProperties = {
  position: "relative", top: -1, marginInlineStart: 4, padding: "1px 4px",
  borderRadius: 4, background: "var(--primary)", color: "#fff",
  fontSize: 9.5, fontWeight: 700, direction: "ltr", verticalAlign: "super",
};
const overlay: React.CSSProperties = {
  position: "fixed", inset: 0, background: "rgba(0,0,0,.45)", zIndex: 80,
  display: "flex", alignItems: "center", justifyContent: "center",
};
const box: React.CSSProperties = {
  background: "var(--surface)", borderRadius: 10, width: 470, maxWidth: "95vw",
  maxHeight: "92vh", overflow: "auto", boxShadow: "0 10px 40px rgba(0,0,0,.3)",
};
const head: React.CSSProperties = {
  background: "var(--primary)", color: "#fff", padding: "11px 16px",
  fontWeight: 700, display: "flex", alignItems: "center",
};
const xBtn: React.CSSProperties = {
  marginInlineStart: "auto", background: "none", border: 0, color: "#fff",
  fontSize: 16, cursor: "pointer", lineHeight: 1,
};
const foot: React.CSSProperties = {
  display: "flex", alignItems: "center", gap: 8, padding: "11px 16px",
  borderTop: "1px solid var(--border)", background: "var(--row-alt)",
};
const input: React.CSSProperties = {
  width: "100%", height: 34, padding: "0 10px", borderRadius: 6,
  border: "1px solid var(--border)", background: "var(--surface)",
  font: "inherit", fontSize: 13.5,
};
const fieldLabel: React.CSSProperties = {
  display: "block", fontSize: 12.5, fontWeight: 700, marginBottom: 5,
};
const fieldHint: React.CSSProperties = {
  fontSize: 11.5, color: "var(--muted)", marginTop: 4, lineHeight: 1.6,
};
const preview: React.CSSProperties = {
  background: "#f6f8f9", border: "1px solid #dbe3e5", borderRadius: 6,
  padding: "9px 12px", fontSize: 12.5, lineHeight: 1.7, color: "var(--muted)",
};
const errText: React.CSSProperties = { color: "var(--danger)", fontSize: 12.5 };
const toastBox: React.CSSProperties = {
  position: "fixed", insetInlineStart: 18, bottom: 18, zIndex: 90, maxWidth: 460,
  background: "#123", color: "#fff", padding: "11px 16px", borderRadius: 8,
  fontSize: 13, lineHeight: 1.7, boxShadow: "0 8px 26px rgba(0,0,0,.3)",
};
const unitTag: React.CSSProperties = {
  marginInlineStart: 6, fontSize: 10.5, fontWeight: 700, color: "#7c3aed",
  background: "#ede9fe", borderRadius: 999, padding: "1px 7px",
};
