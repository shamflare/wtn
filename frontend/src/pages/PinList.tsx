import { Fragment, useEffect, useMemo, useState } from "react";
import { api, type Product, type Provider } from "../api";
import AutoRouteModal from "../components/AutoRouteModal";
import Icon from "../components/Icon";
import ScrollTop from "../components/ScrollTop";
import { matches } from "../search";

/** ربط باقة بمزوّد: رقمها لديه + سعرها عنده (يُحفظ في extra.price). */
interface Link {
  product: number; provider: number;
  package_id: string; package_name: string;
  extra: Record<string, string> | null;
}
const EMPTY_F = { q: "", game: "", route: "", provider: "", unlinked: false };

export default function PinList() {
  const [products, setProducts] = useState<Product[]>([]);
  const [providers, setProviders] = useState<Provider[]>([]);
  const [links, setLinks] = useState<Link[]>([]);
  const [f, setF] = useState({ ...EMPTY_F });
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [autoRoute, setAutoRoute] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);

  function loadLinks() {
    return api.get("/catalog/product-links/").then((r) => setLinks(r.data));
  }
  function reload() {
    return Promise.all([
      api.get("/catalog/products/").then((r) => setProducts(r.data)),
      loadLinks(),
    ]);
  }
  useEffect(() => {
    Promise.all([
      api.get("/catalog/products/"),
      api.get("/providers/", { params: { status: "active" } }),
      api.get("/catalog/product-links/"),
    ]).then(([pr, pv, lk]) => { setProducts(pr.data); setProviders(pv.data); setLinks(lk.data); })
      .finally(() => setLoading(false));
  }, []);

  /** ربط (باقة × مزوّد) — مفتاحه الثنائي. */
  const linkOf = (productId: number, providerId: number | null) =>
    providerId ? links.find((l) => l.product === productId && l.provider === providerId) : undefined;

  const games = useMemo(
    () => [...new Set(products.map((p) => p.game_name))],
    [products],
  );

  // تصفية ثم تجميع حسب اللعبة (رؤوس صفراء)
  const grouped = useMemo(() => {
    const shown = products.filter((p) => {
      if (!matches(f.q, p.name, p.game_name, p.kupur)) return false;
      if (f.game && p.game_name !== f.game) return false;
      const manual = p.execution_type === "manual" || !p.provider;
      if (f.route === "manual" && !manual) return false;
      if (f.route === "auto" && manual) return false;
      const chain = [p.provider, p.provider_alt1, p.provider_alt2];
      if (f.provider && !chain.includes(Number(f.provider))) return false;
      if (f.unlinked) {
        const wired = chain.filter(Boolean) as number[];
        // موجَّهة لمزوّد لكن ينقص أحدَهم رقمُ ربط ⇒ أي طلب عليها سيفشل
        if (!wired.length || wired.every((id) => linkOf(p.id, id)?.package_id)) return false;
      }
      return true;
    });
    const map = new Map<string, Product[]>();
    for (const p of shown) {
      if (!map.has(p.game_name)) map.set(p.game_name, []);
      map.get(p.game_name)!.push(p);
    }
    return [...map.entries()];
  }, [products, links, f]);

  const money = (v: string | number) =>
    Number(v).toLocaleString("en-US", { minimumFractionDigits: 2 });
  const set = (k: string, v: any) => setF((o) => ({ ...o, [k]: v }));

  async function patch(id: number, field: string, value: string) {
    const body: any = { [field]: field === "provider_package_id" ? value : (value || null) };
    const r = await api.patch(`/catalog/products/${id}/`, body);
    setProducts((ps) => ps.map((x) => (x.id === id ? { ...x, ...r.data } : x)));
  }

  /**
   * توجيه الباقة الرئيسي: مزوّد بعينه، أو **يدوي**.
   * «يدوي» ⇒ لا إرسال آلي إطلاقاً: يبقى الطلب «قيد الانتظار» بانتظار المشغّل
   * (يشحنه بيده ويقبله، أو يوجّهه لمزوّد من شريط الإجراءات في متابعة الطلبات).
   * والبديلان يُغلقان معه، فلا معنى لسلسلة احتياطية بلا توجيه أصلي.
   */
  async function setMainRoute(id: number, value: string) {
    const body =
      value === "manual"
        ? { execution_type: "manual", provider: null, provider_alt1: null, provider_alt2: null }
        : { execution_type: "auto", provider: Number(value) };
    const r = await api.patch(`/catalog/products/${id}/`, body);
    setProducts((ps) => ps.map((x) => (x.id === id ? { ...x, ...r.data } : x)));
  }

  /** يسأل كل مزوّد عن كتالوجه مرّة واحدة ويحدّث أسعار كل ما رُبط به. */
  async function refreshPrices() {
    setRefreshing(true); setMsg(null);
    try {
      const r = await api.post("/catalog/product-links/refresh-prices/");
      await loadLinks();
      const failed = (r.data.providers || []).filter((x: any) => !x.ok);
      setMsg({
        ok: failed.length === 0,
        text: `حُدِّث ${r.data.updated} سعراً` +
          (failed.length
            ? ` · تعذّر على: ${failed.map((x: any) => `${x.provider} (${x.note})`).join(" · ")}`
            : ""),
      });
    } catch (e: any) {
      setMsg({ ok: false, text: e?.response?.data?.detail || "فشل تحديث الأسعار" });
    } finally { setRefreshing(false); }
  }

  if (loading) return <div style={{ padding: 30 }}>جارٍ التحميل...</div>;

  return (
    <div style={{ maxWidth: 1340, margin: "0 auto", padding: "18px 16px 40px" }}>
      <div className="card">
        <div className="card-title">
          توجيه الباقات (Pin Listesi)
          <span style={{ fontWeight: 400, fontSize: 12, color: "var(--debt)" }}>
            ** اسحب صفّ المنتج وأفلته لترتيب ما يراه وكلاؤك
          </span>
          <div style={{ marginInlineStart: "auto", display: "flex", gap: 8 }}>
            <button className="btn" style={{ height: 32 }}
              onClick={() => setAutoRoute(true)}
              title="يرتّب مزوّدي كل باقة حسب السعر: الأرخص API 1 ثم الأغلى بديلاً">
              <Icon name="chart" size={14} style={{ marginInlineEnd: 5, verticalAlign: -2 }} />
              توجيه تلقائي حسب السعر
            </button>
            <button className="btn g" style={{ height: 32 }}
              onClick={refreshPrices} disabled={refreshing}
              title="يسأل كل مزوّد عن كتالوجه ويحدّث أسعار الباقات المربوطة به">
              <Icon name="refresh" size={14} style={{ marginInlineEnd: 5, verticalAlign: -2 }} />
              {refreshing ? "جارٍ التحديث..." : "تحديث الأسعار"}
            </button>
          </div>
        </div>

        {/* ===== الفلترة ===== */}
        <div style={fbar}>
          <input placeholder="بحث باسم الباقة أو اللعبة..." value={f.q}
            onChange={(e) => set("q", e.target.value)} style={{ ...inp, flex: "1 1 220px" }} />
          <select value={f.game} onChange={(e) => set("game", e.target.value)} style={inp}>
            <option value="">كل الألعاب</option>
            {games.map((g) => <option key={g} value={g}>{g}</option>)}
          </select>
          <select value={f.route} onChange={(e) => set("route", e.target.value)} style={inp}>
            <option value="">كل التوجيهات</option>
            <option value="manual">يدوي فقط</option>
            <option value="auto">موجَّه لمزوّد</option>
          </select>
          <select value={f.provider} onChange={(e) => set("provider", e.target.value)} style={inp}>
            <option value="">كل المزوّدين</option>
            {providers.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
          <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 13, whiteSpace: "nowrap" }}
            title="موجَّهة لمزوّد لكن ينقصها رقم ربط — أي طلب عليها سيفشل">
            <input type="checkbox" checked={f.unlinked}
              onChange={(e) => set("unlinked", e.target.checked)} />
            بلا رقم ربط ⚠
          </label>
          <button className="btn" style={{ height: 34, background: "#8a999e" }}
            onClick={() => setF({ ...EMPTY_F })}>إزالة الفلتر</button>
          <span style={{ color: "var(--muted)", fontSize: 12.5 }}>
            {grouped.reduce((n, [, items]) => n + items.length, 0)} باقة
          </span>
        </div>

        {msg && (
          <div style={{
            margin: "0 16px 12px", fontSize: 12.5, padding: "8px 12px", borderRadius: 6,
            background: msg.ok ? "rgba(53,194,69,.10)" : "rgba(221,68,68,.10)",
            color: msg.ok ? "var(--ok)" : "var(--danger)",
          }}>{msg.text}</div>
        )}

        <div className="table-scroll">
          <table className="grid">
            <thead>
              <tr>
                <th style={{ width: 34 }}><input type="checkbox" title="تحديد الكل" /></th>
                <th style={{ width: 60 }}>ID</th>
                <th className="cell-start">اسم المنتج</th>
                <th>رقم الربط</th>
                <th>سعر الشراء</th>
                <th>الموصى</th>
                <th>API 1</th>
                <th>API 2</th>
                <th>API 3</th>
              </tr>
            </thead>
            <tbody>
              {grouped.length === 0 ? (
                <tr><td colSpan={9} style={{ padding: 26, color: "var(--muted)" }}>
                  لا باقات تطابق الفلترة
                </td></tr>
              ) : grouped.map(([game, items]) => (
                <Fragment key={game}>
                  <tr>
                    <td colSpan={9} style={groupHead}>{game}</td>
                  </tr>
                  {items.map((p) => (
                    <tr key={p.id}>
                      <td><input type="checkbox" /></td>
                      <td className="num" style={{ color: "var(--faint)" }}>{p.id}</td>
                      <td className="cell-start" style={{ fontWeight: 600 }}>
                        {p.status === "active" && <span style={{ color: "var(--ok)" }}>✔ </span>}
                        {p.name}
                      </td>
                      {/* رقم الربط العام لدى مدير النظام — يُستعمل حين لا ربط
                          خاصّ بالمزوّد في صفحة "ربط الباقات" */}
                      <td>
                        <input defaultValue={p.provider_package_id}
                          onBlur={(e) => e.target.value !== p.provider_package_id
                            && patch(p.id, "provider_package_id", e.target.value)}
                          placeholder="—"
                          style={{ width: 110, height: 28, fontSize: 12, borderRadius: 6, textAlign: "center" }} />
                      </td>
                      <td className="buy num">{money(p.cost_price)}</td>
                      <td className="sell num">{money(p.recommended_price)}</td>
                      <td>
                        <MainRouteSelect providers={providers} product={p}
                          onPick={(v) => setMainRoute(p.id, v)} />
                        <LinkInfo link={linkOf(p.id, p.provider)} sell={p.recommended_price} />
                      </td>
                      <td>
                        <ApiSelect providers={providers} value={p.provider_alt1}
                          onPick={(v) => patch(p.id, "provider_alt1", v)} />
                        <LinkInfo link={linkOf(p.id, p.provider_alt1)} sell={p.recommended_price} />
                      </td>
                      <td>
                        <ApiSelect providers={providers} value={p.provider_alt2}
                          onPick={(v) => patch(p.id, "provider_alt2", v)} />
                        <LinkInfo link={linkOf(p.id, p.provider_alt2)} sell={p.recommended_price} />
                      </td>
                    </tr>
                  ))}
                </Fragment>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {autoRoute && (
        <AutoRouteModal onClose={() => setAutoRoute(false)}
          onDone={(text) => {
            setAutoRoute(false);
            setMsg({ ok: true, text });
            reload();
          }} />
      )}

      <div style={note}>
        توجيه بثلاثة مستويات: يُرسل الطلب إلى <b>API 1</b>، وعند فشله — أو عند
        إلغاء المزوّد له بعد قبوله — يُجرَّب <b>API 2</b> ثم <b>API 3</b> تلقائياً.
        المزوّدون تُدارون من قسم <b>مزوّدي API</b>، وأرقام الربط من <b>ربط الباقات</b>.
        <br />
        <b style={{ color: "var(--debt)" }}>يدوي:</b> لا إرسال آلي — يبقى الطلب
        «قيد الانتظار» في متابعة الطلبات، فتشحنه بيدك وتقبله أو ترفضه، أو توجّهه
        إلى مزوّد وقتها من شريط الإجراءات.
      </div>
      <ScrollTop />
    </div>
  );
}

/**
 * رقم الباقة لدى المزوّد وسعرها عنده — تحت اسمه مباشرةً في الخلية نفسها.
 *
 * يُعرض **رقم الباقة** وحده: عند ZNET هو `kupur` (60 · 325) لا `oyun` الذي
 * يرقّم اللعبة كلّها (PUBG = 1) فيتكرّر على كل باقاتها ولا يميّز شيئاً.
 * وعند ZDK رقم واحد لا `kupur` له، فيُعرض كما هو. الإرسال يستعمل الاثنين.
 */
function LinkInfo({ link, sell }: { link?: Link; sell: string }) {
  if (!link) return null;
  const extra = link.extra || {};
  const price = extra.price;
  const loss = price !== undefined && price !== "" && Number(price) > Number(sell);
  return (
    <div style={{ fontSize: 11, marginTop: 3, lineHeight: 1.5 }}>
      <span style={{ color: "var(--muted)" }} dir="ltr" title="رقم الباقة لدى المزوّد">
        ({extra.kupur || link.package_id})
      </span>
      {price ? (
        <b style={{ marginInlineStart: 6, color: loss ? "var(--danger)" : "var(--ok)" }}
          title={loss ? `تكلفته ${price} أعلى من سعر بيعك ${sell} — حماية الخسارة ستتخطّاه` : undefined}>
          {Number(price).toLocaleString("en-US", { minimumFractionDigits: 2 })}{loss ? " ⚠" : ""}
        </b>
      ) : (
        <span style={{ marginInlineStart: 6, color: "var(--faint)" }}>بلا سعر</span>
      )}
    </div>
  );
}

/** التوجيه الرئيسي: «يدوي» أو مزوّد. المصدر الوحيد لحالة الباقة. */
function MainRouteSelect({ providers, product, onPick }:
  { providers: Provider[]; product: Product; onPick: (v: string) => void }) {
  const manual = product.execution_type === "manual" || !product.provider;
  return (
    <select style={{ width: 150, height: 30, ...(manual ? { color: "var(--debt)", fontWeight: 700 } : {}) }}
      value={manual ? "manual" : String(product.provider)}
      onChange={(e) => onPick(e.target.value)}>
      <option value="manual">يدوي (بلا مزوّد)</option>
      {providers.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
    </select>
  );
}

function ApiSelect({ providers, value, onPick }:
  { providers: Provider[]; value: number | null; onPick: (v: string) => void }) {
  return (
    <select style={{ width: 150, height: 30 }} value={value ?? ""} onChange={(e) => onPick(e.target.value)}>
      <option value="">بديل مغلق</option>
      {providers.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
    </select>
  );
}

const fbar: React.CSSProperties = {
  display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap", padding: "12px 16px",
};
const inp: React.CSSProperties = { height: 34, borderRadius: 8, minWidth: 130 };
const groupHead: React.CSSProperties = {
  background: "#f5c518",
  color: "#4a3c00",
  fontWeight: 700,
  padding: "7px 14px",
  textAlign: "right",
  fontSize: 14,
};
const note: React.CSSProperties = {
  background: "#f6f8f9",
  border: "1px solid #dbe3e5",
  color: "var(--muted)",
  fontSize: 13,
  padding: "10px 14px",
  borderRadius: 6,
  marginTop: 14,
};
