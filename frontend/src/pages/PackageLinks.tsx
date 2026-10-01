import { Fragment, useEffect, useMemo, useRef, useState } from "react";
import { api, type Product, type Provider } from "../api";
import Icon from "../components/Icon";
import AutoLinkModal from "../components/AutoLinkModal";
import { useBaseSymbol } from "../currency";

/** باقة لدى المزوّد كما يعيدها الكتالوج. */
type ProviderPackage = {
  id: string;
  name: string;
  game: string;
  kupur: string;
  price: string;
  available_count?: number;
};

/** ربط محفوظ: (منتج × مزوّد) → رقم الربط. */
type Link = {
  product: number;
  provider: number;
  package_id: string;
  package_name: string;
  extra: Record<string, any>;
};

const key = (product: number, provider: number) => `${product}:${provider}`;

/**
 * ربط الباقات — باقاتنا في الصفوف، ومزوّدونا في الأعمدة.
 * كل مزوّد يسمّي الباقة كما يشاء؛ رقم الربط هو صلة الوصل، ولذلك يُحفظ
 * رقم مستقلّ لكل (باقة × مزوّد).
 */
export default function PackageLinks() {
  const [products, setProducts] = useState<Product[]>([]);
  const [providers, setProviders] = useState<Provider[]>([]);
  const [links, setLinks] = useState<Map<string, Link>>(new Map());
  const [loading, setLoading] = useState(true);
  const [q, setQ] = useState("");
  const [open, setOpen] = useState<{ product: Product; provider: Provider } | null>(null);
  const [toast, setToast] = useState("");
  // «ربط تلقائي» لعمود مزوّد: معاينةٌ ثم حفظ ما يوافق عليه صاحب المتجر
  const [autoFor, setAutoFor] = useState<Provider | null>(null);
  const baseSymbol = useBaseSymbol();

  async function reloadLinks() {
    const lk = await api.get("/catalog/product-links/");
    setLinks(new Map((lk.data as Link[]).map((l) => [key(l.product, l.provider), l])));
  }

  // كتالوج كل مزوّد يُجلب مرّة واحدة ويُخزَّن
  const [catalog, setCatalog] = useState<Map<number, ProviderPackage[]>>(new Map());
  const [catalogErr, setCatalogErr] = useState<Map<number, string>>(new Map());
  const [fetching, setFetching] = useState<number | null>(null);

  useEffect(() => {
    Promise.all([
      api.get("/catalog/products/"),
      api.get("/providers/", { params: { status: "active" } }),
      api.get("/catalog/product-links/"),
    ])
      .then(([pr, pv, lk]) => {
        setProducts(pr.data);
        setProviders(pv.data);
        setLinks(new Map((lk.data as Link[]).map((l) => [key(l.product, l.provider), l])));
      })
      .finally(() => setLoading(false));
  }, []);

  // المزوّدون الآليون فقط — المنفّذ اليدوي لا يُربط
  const cols = useMemo(
    () => providers.filter((p) => p.type !== "loader"),
    [providers],
  );

  const grouped = useMemo(() => {
    const term = q.trim();
    const rows = term
      ? products.filter((p) => p.name.includes(term) || p.game_name.includes(term))
      : products;
    const map = new Map<string, Product[]>();
    for (const p of rows) {
      if (!map.has(p.game_name)) map.set(p.game_name, []);
      map.get(p.game_name)!.push(p);
    }
    return [...map.entries()];
  }, [products, q]);

  const linked = links.size;
  const needed = products.length * cols.length;

  async function loadCatalog(provider: Provider, force = false) {
    if (!force && catalog.has(provider.id)) return;
    setFetching(provider.id);
    try {
      const r = await api.get(`/providers/${provider.id}/packages/`);
      setCatalog((m) => new Map(m).set(provider.id, r.data.packages));
      setCatalogErr((m) => {
        const n = new Map(m);
        n.delete(provider.id);
        return n;
      });
    } catch (e: any) {
      setCatalogErr((m) =>
        new Map(m).set(provider.id, e?.response?.data?.detail || "تعذّر جلب باقات المزوّد"),
      );
    } finally {
      setFetching(null);
    }
  }

  async function saveLink(product: Product, provider: Provider, pkg: ProviderPackage) {
    const r = await api.post("/catalog/product-links/", {
      product: product.id,
      provider: provider.id,
      package_id: pkg.id,
      package_name: pkg.name,
      // نحفظ سعر المزوّد وقت الربط — يعتمده "منع البيع بخسارة" قبل الإرسال
      extra: {
        ...(pkg.kupur ? { kupur: pkg.kupur } : {}),
        ...(pkg.price ? { price: pkg.price } : {}),
      },
    });
    setLinks((m) => new Map(m).set(key(product.id, provider.id), r.data));
    setOpen(null);
    setToast(`✅ ${product.name} ← ${provider.name}: ${pkg.id}`);
    setTimeout(() => setToast(""), 3500);
  }

  async function saveManual(product: Product, provider: Provider, value: string, kupur: string) {
    const r = await api.post("/catalog/product-links/", {
      product: product.id,
      provider: provider.id,
      package_id: value,
      package_name: "(يدوي)",
      extra: kupur ? { kupur } : {},
    });
    setLinks((m) => new Map(m).set(key(product.id, provider.id), r.data));
    setOpen(null);
    setToast(`✅ ${product.name} ← ${provider.name}: ${value}`);
    setTimeout(() => setToast(""), 3500);
  }

  async function unlink(product: Product, provider: Provider) {
    await api.delete("/catalog/product-links/", {
      data: { product: product.id, provider: provider.id },
    });
    setLinks((m) => {
      const n = new Map(m);
      n.delete(key(product.id, provider.id));
      return n;
    });
    setOpen(null);
  }

  if (loading) return <div style={{ padding: 30 }}>جارٍ التحميل...</div>;

  const autoModal = autoFor && (
    <AutoLinkModal provider={autoFor} baseSymbol={baseSymbol} onClose={() => setAutoFor(null)}
      onDone={(n) => {
        setAutoFor(null);
        reloadLinks();
        setToast(n ? `🔗 رُبطت ${n} باقة بـ«${autoFor.name}» وضُبط توجيهها` : "لم يُربط شيء");
        setTimeout(() => setToast(""), 5000);
      }} />
  );

  return (
    <div style={{ maxWidth: 1340, margin: "0 auto", padding: "18px 16px 40px" }}>
      <div className="card">
        <div className="card-title">
          ربط الباقات
          <span style={{ fontWeight: 400, fontSize: 12, color: "var(--muted)" }}>
            ** كل مزوّد يسمّي الباقة كما يشاء — رقم الربط هو صلة الوصل
          </span>
          <div style={{ marginInlineStart: "auto", display: "flex", gap: 10, alignItems: "center" }}>
            <span style={{ fontSize: 12.5, color: linked === needed ? "var(--ok)" : "var(--debt)" }}>
              مربوط {linked} من {needed}
            </span>
            <input placeholder="بحث عن باقة..." value={q} onChange={(e) => setQ(e.target.value)}
              style={{ width: 200 }} />
          </div>
        </div>

        {cols.length === 0 ? (
          <div style={{ padding: 24, color: "var(--muted)" }}>
            لا مزوّدين بعد — أضِف مزوّداً من «مزوّدو API» ليظهر عموده هنا.
          </div>
        ) : (
          <div style={{ overflowX: "auto" }}>
            <table className="grid">
              <thead>
                <tr>
                  <th style={{ minWidth: 190, textAlign: "right" }}>الباقة</th>
                  <th style={{ minWidth: 90 }}>Küpür</th>
                  {cols.map((v) => (
                    <th key={v.id} style={{ minWidth: 190 }}>
                      {v.name}
                      <div style={{ fontWeight: 400, fontSize: 11, opacity: 0.8 }}>{v.type_label}</div>
                      <button type="button" onClick={() => setAutoFor(v)}
                        title={`يقترح ربط الباقات غير المربوطة بـ«${v.name}» — تراجعها قبل الحفظ`}
                        style={{ marginTop: 5, fontSize: 11.5, fontWeight: 700, padding: "3px 10px", borderRadius: 999,
                                 border: "1px solid rgba(255,255,255,.45)", background: "rgba(255,255,255,.14)",
                                 color: "inherit", cursor: "pointer" }}>
                        🔗 ربط تلقائي
                      </button>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {grouped.map(([gameName, rows]) => (
                  <Fragment key={gameName}>
                    <tr>
                      <td colSpan={cols.length + 2} style={gameHead}>{gameName}</td>
                    </tr>
                    {rows.map((p) => (
                      <tr key={p.id}>
                        <td style={{ textAlign: "right", paddingInlineStart: 12, fontWeight: 600 }}>
                          {p.name}
                        </td>
                        <td style={{ color: "var(--muted)" }}>{p.kupur || "—"}</td>
                        {cols.map((v) => {
                          const link = links.get(key(p.id, v.id));
                          return (
                            <td key={v.id} style={{ position: "relative" }}>
                              <button type="button" style={link ? cellLinked : cellEmpty}
                                onClick={() => {
                                  setOpen({ product: p, provider: v });
                                  loadCatalog(v);
                                }}>
                                {link ? (
                                  <>
                                    {link.extra?.auto && <span title="رُبطت تلقائياً من المكتبة — اضغط لتغييرها">🔗</span>}
                                    <code style={{ direction: "ltr" }}>{link.package_id}</code>
                                    {link.extra?.kupur && (
                                      <code style={{ direction: "ltr", opacity: 0.75 }}>
                                        /{link.extra.kupur}
                                      </code>
                                    )}
                                    <span style={{ fontSize: 11, opacity: 0.75, maxWidth: 78,
                                      overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                                      {link.package_name}
                                    </span>
                                    {link.extra?.price && (
                                      <span
                                        title={Number(link.extra.price) > Number(p.recommended_price)
                                          ? `تكلفة المزوّد ${link.extra.price} أعلى من سعر بيعك ${p.recommended_price} — بيع بخسارة`
                                          : `تكلفة المزوّد ${link.extra.price}`}
                                        style={{
                                          fontSize: 11, fontWeight: 700, direction: "ltr",
                                          color: Number(link.extra.price) > Number(p.recommended_price)
                                            ? "var(--danger)" : "var(--ok)",
                                        }}>
                                        {Number(link.extra.price) > Number(p.recommended_price) ? "⚠ " : ""}
                                        {link.extra.price}
                                      </span>
                                    )}
                                  </>
                                ) : (
                                  <>
                                    <Icon name="plus" size={12} />
                                    ربط
                                  </>
                                )}
                              </button>

                              {open?.product.id === p.id && open?.provider.id === v.id && (
                                <PackagePicker
                                  provider={v}
                                  product={p}
                                  packages={catalog.get(v.id) || []}
                                  error={catalogErr.get(v.id) || ""}
                                  loading={fetching === v.id}
                                  current={link || null}
                                  onRefresh={() => loadCatalog(v, true)}
                                  onPick={(pkg) => saveLink(p, v, pkg)}
                                  onManual={(val, kupur) => saveManual(p, v, val, kupur)}
                                  onUnlink={() => unlink(p, v)}
                                  onClose={() => setOpen(null)}
                                />
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
        )}
      </div>

      {toast && <div style={toastBox}>{toast}</div>}
      {autoModal}
    </div>
  );
}

/** قائمة منسدلة ببحث: باقات المزوّد مع أرقام ربطها. */
function PackagePicker({
  provider, product, packages, error, loading, current,
  onRefresh, onPick, onManual, onUnlink, onClose,
}: {
  provider: Provider;
  product: Product;
  packages: ProviderPackage[];
  error: string;
  loading: boolean;
  current: Link | null;
  onRefresh: () => void;
  onPick: (p: ProviderPackage) => void;
  onManual: (packageId: string, kupur: string) => void;
  onUnlink: () => void;
  onClose: () => void;
}) {
  const [term, setTerm] = useState("");
  const [manual, setManual] = useState(current?.package_id || "");
  const [manualKupur, setManualKupur] = useState(current?.extra?.kupur || "");
  const box = useRef<HTMLDivElement>(null);

  // إغلاق بالنقر خارج القائمة أو بمفتاح Esc
  useEffect(() => {
    const onDown = (e: MouseEvent) => {
      if (box.current && !box.current.contains(e.target as Node)) onClose();
    };
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [onClose]);

  const shown = useMemo(() => {
    const t = term.trim().toLowerCase();
    if (!t) return packages.slice(0, 300);
    return packages
      .filter((p) =>
        p.name.toLowerCase().includes(t) ||
        p.game.toLowerCase().includes(t) ||
        p.id.includes(t) ||
        (p.kupur || "").includes(t))
      .slice(0, 300);
  }, [packages, term]);

  return (
    <div ref={box} style={dropdown} onClick={(e) => e.stopPropagation()}>
      <div style={ddHead}>
        <span>{provider.name} — باقات المزوّد</span>
        <button type="button" style={ddX} onClick={onClose}>✕</button>
      </div>
      <div style={{ padding: "8px 10px", fontSize: 11.5, color: "var(--muted)" }}>
        اربط <b>{product.name}</b> بباقتها لدى هذا المزوّد
      </div>

      <div style={{ padding: "0 10px 8px" }}>
        <input autoFocus placeholder="ابحث بالاسم أو رقم الربط..." value={term}
          onChange={(e) => setTerm(e.target.value)} style={{ width: "100%" }} />
      </div>

      <div style={{ maxHeight: 260, overflowY: "auto", borderTop: "1px solid var(--border)" }}>
        {loading ? (
          <div style={ddMsg}>جارٍ جلب باقات المزوّد...</div>
        ) : error ? (
          <div style={{ ...ddMsg, color: "var(--debt)" }}>
            {error}
            <div style={{ marginTop: 6 }}>
              <button type="button" className="btn" style={{ height: 26, fontSize: 12 }}
                onClick={onRefresh}>إعادة المحاولة</button>
            </div>
          </div>
        ) : shown.length === 0 ? (
          <div style={ddMsg}>لا نتائج مطابقة</div>
        ) : (
          shown.map((pkg, i) => (
            <button key={`${pkg.id}-${i}`} type="button" style={ddRow} onClick={() => onPick(pkg)}>
              <code style={{ direction: "ltr", fontWeight: 700, color: "var(--primary)" }}>
                {pkg.id}{pkg.kupur ? `/${pkg.kupur}` : ""}
              </code>
              <span style={{ flex: 1, textAlign: "right" }}>
                {pkg.name}
                {pkg.game && <span style={{ color: "var(--muted)", fontSize: 11 }}> · {pkg.game}</span>}
              </span>
              {pkg.price && <span style={{ color: "var(--ok)", fontSize: 12 }}>{pkg.price}</span>}
              {pkg.available_count !== undefined && (
                <span style={{ color: "var(--muted)", fontSize: 11 }}>({pkg.available_count})</span>
              )}
            </button>
          ))
        )}
      </div>

      {/* إدخال يدوي — حين لا يوفّر المزوّد كتالوجاً */}
      <div style={{ borderTop: "1px solid var(--border)", padding: 10, display: "grid", gap: 6 }}>
        <div style={{ fontSize: 11.5, color: "var(--muted)" }}>أو أدخل رقم الربط يدوياً</div>
        <div style={{ display: "flex", gap: 6 }}>
          <input placeholder="رقم الربط" value={manual} dir="ltr" style={{ flex: 1 }}
            onChange={(e) => setManual(e.target.value)} />
          <input placeholder="Küpür (اختياري)" value={manualKupur} dir="ltr" style={{ width: 110 }}
            onChange={(e) => setManualKupur(e.target.value)} />
        </div>
        <div style={{ display: "flex", gap: 6 }}>
          <button type="button" className="btn g" style={{ height: 28, fontSize: 12.5 }}
            disabled={!manual.trim()}
            onClick={() => onManual(manual.trim(), manualKupur.trim())}>حفظ</button>
          {current && (
            <button type="button" className="btn" style={{ height: 28, fontSize: 12.5, background: "var(--debt)" }}
              onClick={onUnlink}>فكّ الربط</button>
          )}
          <button type="button" className="btn" style={{ height: 28, fontSize: 12.5, background: "#8a999e" }}
            onClick={onRefresh}>تحديث الكتالوج</button>
        </div>
      </div>
    </div>
  );
}

const gameHead: React.CSSProperties = {
  background: "var(--accent, #f5c518)", color: "#3a2f00", textAlign: "right",
  fontWeight: 800, padding: "7px 12px", fontSize: 13,
};
const cellBase: React.CSSProperties = {
  display: "inline-flex", alignItems: "center", gap: 5, justifyContent: "center",
  border: "1px solid var(--border)", borderRadius: 5, padding: "4px 8px",
  fontSize: 12.5, cursor: "pointer", minWidth: 92, background: "#fff",
};
const cellEmpty: React.CSSProperties = { ...cellBase, color: "var(--muted)", borderStyle: "dashed" };
const cellLinked: React.CSSProperties = {
  ...cellBase, color: "var(--ink, #222)", background: "var(--row-alt)", fontWeight: 600,
};
const dropdown: React.CSSProperties = {
  position: "absolute", top: "calc(100% + 4px)", insetInlineStart: 0, zIndex: 40,
  width: 360, background: "#fff", border: "1px solid var(--border)", borderRadius: 8,
  boxShadow: "0 8px 28px rgba(0,0,0,.22)", textAlign: "right",
};
const ddHead: React.CSSProperties = {
  background: "var(--primary)", color: "#fff", padding: "7px 10px", fontSize: 13,
  fontWeight: 700, display: "flex", alignItems: "center", justifyContent: "space-between",
  borderRadius: "7px 7px 0 0",
};
const ddX: React.CSSProperties = {
  background: "none", border: 0, color: "#fff", cursor: "pointer", fontSize: 14, padding: 0,
};
const ddRow: React.CSSProperties = {
  display: "flex", alignItems: "center", gap: 8, width: "100%", textAlign: "right",
  padding: "7px 10px", background: "none", border: 0,
  borderBottom: "1px solid var(--border)", cursor: "pointer", fontSize: 12.5,
};
const ddMsg: React.CSSProperties = { padding: "14px 12px", fontSize: 12.5, color: "var(--muted)" };
const toastBox: React.CSSProperties = {
  position: "fixed", insetInlineEnd: 18, bottom: 18, zIndex: 80,
  background: "var(--ok)", color: "#fff", padding: "10px 16px", borderRadius: 6,
  fontSize: 13, boxShadow: "0 6px 20px rgba(0,0,0,.25)",
};
