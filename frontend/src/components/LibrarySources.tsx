import { Fragment, useEffect, useMemo, useState } from "react";
import { api } from "../api";

/* ═══════════════════════════════════════════════════════════════════════
   لوحة المنصّة ← مصادر المكتبة.

   مزوّدٌ (بركات…) يُقرأ كتالوجه ولا يُشترى منه: يجلب المالك الكتالوج، يختار
   الألعاب، فتُنشأ في المكتبة بباقاتها وأسعارها دفعةً واحدة. ثم «مزامنة» تأخذ
   ما تغيّر عند المزوّد. ورقم كل باقة لديه يُحفظ معها — فصاحب المتجر الذي يملك
   المزوّد نفسه تُربط باقاته تلقائياً عند الاستيراد.
   ═══════════════════════════════════════════════════════════════════════ */

interface Source {
  id: number; name: string; code: string; base_url: string; has_token: boolean;
  currency: string; usd_rate: string; default_margin: string; fingerprint: string;
  games: number; last_synced_at: string | null;
}
interface Pkg {
  ref: string; name: string; price: string; usd: string | null; old_usd: string | null;
  available: boolean; state: "new" | "changed" | "same";
  sale_type?: "package" | "amount"; qty_min?: number; qty_max?: number; qty_unit?: number;
}
interface Group {
  key: string; state: "new" | "existing"; library_id: number | null; library_name: string;
  require_player_id: boolean; packages: Pkg[];
  counts: { new: number; changed: number; same: number; removed: number };
  removed: { ref: string; name: string }[];
}
interface Catalog {
  currency: string; usd_rate: string; total_packages: number; groups: Group[];
  /** ألعابٌ يبيعها المزوّد «بالكمية» فقط (سعرٌ للوحدة) — لا باقات ثابتة تُستورد */
  amount_only?: { key: string; count: number; min: string; max: string }[];
}

type Filter = "all" | "new" | "changes" | "existing";

export default function LibrarySources({ onLibraryChanged }: { onLibraryChanged?: () => void }) {
  const [sources, setSources] = useState<Source[] | null>(null);
  const [adding, setAdding] = useState(false);
  const [editing, setEditing] = useState<Source | null>(null);
  const [browsing, setBrowsing] = useState<Source | null>(null);
  const [toast, setToast] = useState<{ ok: boolean; text: string } | null>(null);
  const [syncing, setSyncing] = useState<number | null>(null);

  function load() { api.get("/platform/library/sources/").then((r) => setSources(r.data)).catch(() => setSources([])); }
  useEffect(load, []);

  function flash(ok: boolean, text: string) {
    setToast({ ok, text });
    setTimeout(() => setToast(null), 6000);
  }

  async function sync(s: Source) {
    if (!s.games) {
      flash(false, "المزامنة تحدّث الألعاب المستوردة من هذا المصدر — ولا شيء مستورد بعد. اختر ألعابك من الكتالوج أولاً ↓");
      setBrowsing(s);
      return;
    }
    setSyncing(s.id);
    try {
      const r = await api.post(`/platform/library/sources/${s.id}/import/`, { sync: true });
      flash(true, summaryText(r.data));
      load(); onLibraryChanged?.();
    } catch (e: any) {
      flash(false, e?.response?.data?.detail || "تعذّرت المزامنة");
    } finally { setSyncing(null); }
  }

  async function remove(s: Source) {
    if (!confirm(`حذف المصدر "${s.name}"؟\nألعاب المكتبة المستوردة منه تبقى كما هي.`)) return;
    await api.delete(`/platform/library/sources/${s.id}/`);
    load();
  }

  if (browsing) {
    return (
      <>
        {toast && <div style={toast.ok ? okBox : errBoxDark}>{toast.text}</div>}
        <CatalogBrowser source={browsing} onBack={() => { setBrowsing(null); load(); }}
          onImported={() => onLibraryChanged?.()} />
      </>
    );
  }

  return (
    <>
      <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 6 }}>
        <h2 style={{ fontSize: 18 }}>مصادر المكتبة</h2>
        <button style={primaryBtn} onClick={() => setAdding(true)}>➕ إضافة مصدر</button>
      </div>
      <p style={{ color: "#94a3b8", fontSize: 13, marginBottom: 16, lineHeight: 1.9 }}>
        مزوّدٌ يُقرأ كتالوجه <b style={{ color: "#e2e8f0" }}>ولا يُشترى منه</b>. اجلب كتالوجه، اختر الألعاب،
        فتُنشأ في المكتبة العالمية بباقاتها وأسعارها دفعةً واحدة. وكل متجرٍ لديه المزوّد نفسه
        تُربط باقاته تلقائياً عند الاستيراد.
      </p>

      {toast && <div style={toast.ok ? okBox : errBoxDark}>{toast.text}</div>}

      {sources === null ? <div style={{ color: "#94a3b8", padding: 20 }}>جارٍ التحميل...</div>
        : sources.length === 0 ? (
          <div style={emptyCard}>
            <div style={{ fontSize: 40 }}>🔌</div>
            <b style={{ fontSize: 16 }}>لا مصادر بعد</b>
            <div style={{ color: "#94a3b8", fontSize: 13 }}>أضف بركات — يمكنك نسخ إعداده من مزوّد أحد المتاجر بضغطة.</div>
            <button style={{ ...primaryBtn, marginTop: 6 }} onClick={() => setAdding(true)}>➕ إضافة مصدر</button>
          </div>
        ) : (
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(340px, 1fr))", gap: 14 }}>
            {sources.map((s) => (
              <div key={s.id} style={card}>
                <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                  <span style={srcIcon}>🔌</span>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <b style={{ fontSize: 16 }}>{s.name}</b>
                    <div style={{ fontSize: 12, color: "#94a3b8", direction: "ltr", textAlign: "right" }}>
                      {s.fingerprint.split(":")[1] || s.base_url || "—"}
                    </div>
                  </div>
                  <span style={pill}>{s.code.toUpperCase()}</span>
                </div>
                <div style={stats}>
                  <Stat label="ألعاب في المكتبة" value={String(s.games)} />
                  <Stat label="العملة" value={s.currency} />
                  <Stat label="سعر الدولار" value={s.currency === "USD" ? "—" : Number(s.usd_rate).toString()} />
                  <Stat label="الهامش" value={`${Number(s.default_margin)}%`} />
                </div>
                <div style={{ fontSize: 12, color: "#64748b", marginTop: 8 }}>
                  آخر مزامنة: {s.last_synced_at || "لم تتمّ بعد"}
                </div>
                <div style={{ display: "flex", gap: 8, marginTop: 12, flexWrap: "wrap" }}>
                  <button style={{ ...primaryBtn, flex: 1 }} onClick={() => setBrowsing(s)}>📥 جلب الكتالوج</button>
                  <button style={{ ...ghostBtn, flex: 1 }} disabled={syncing === s.id} onClick={() => sync(s)}
                    title={s.games ? "يأخذ الباقات الجديدة والأسعار المتغيّرة ويطفئ ما أزاله المزوّد" : "لا ألعاب مستوردة بعد — يفتح الكتالوج"}>
                    {syncing === s.id ? "جارٍ المزامنة..." : "🔄 مزامنة"}
                  </button>
                  <button style={iconBtn} title="الإعدادات" onClick={() => setEditing(s)}>⚙</button>
                  <button style={{ ...iconBtn, color: "#fca5a5" }} title="حذف" onClick={() => remove(s)}>🗑</button>
                </div>
              </div>
            ))}
          </div>
        )}

      {adding && <SourceForm onClose={() => setAdding(false)} onDone={() => { setAdding(false); load(); }} />}
      {editing && <SourceForm source={editing} onClose={() => setEditing(null)} onDone={() => { setEditing(null); load(); }} />}
    </>
  );
}

function summaryText(d: any) {
  const parts = [];
  if (d.games_created) parts.push(`${d.games_created} لعبة جديدة`);
  if (d.packages_added) parts.push(`${d.packages_added} باقة جديدة`);
  if (d.prices_updated) parts.push(`${d.prices_updated} سعر حُدِّث`);
  if (d.packages_disabled) parts.push(`${d.packages_disabled} باقة أُطفئت (أزالها المزوّد)`);
  return parts.length ? `✓ ${parts.join(" · ")}` : "✓ لا جديد — المكتبة مطابقة للمزوّد";
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ background: "#0b1222", borderRadius: 8, padding: "7px 8px", textAlign: "center" }}>
      <div style={{ fontWeight: 800, fontSize: 15 }}>{value}</div>
      <div style={{ fontSize: 10.5, color: "#94a3b8" }}>{label}</div>
    </div>
  );
}

/* ── إضافة / تعديل مصدر ── */
function SourceForm({ source, onClose, onDone }: { source?: Source; onClose: () => void; onDone: () => void }) {
  const [mode, setMode] = useState<"copy" | "manual">(source ? "manual" : "copy");
  const [shopProviders, setShopProviders] = useState<any[] | null>(null);
  const [f, setF] = useState({
    name: source?.name || "", from_provider: "", base_url: source?.base_url || "", api_token: "",
    currency: source?.currency || "TRY", usd_rate: source?.usd_rate ? String(Number(source.usd_rate)) : "",
    default_margin: source?.default_margin ? String(Number(source.default_margin)) : "10",
  });
  const [err, setErr] = useState(""); const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!source) api.get("/platform/library/tenant-providers/").then((r) => setShopProviders(r.data)).catch(() => setShopProviders([]));
  }, [source]);

  const needsRate = f.currency.toUpperCase() !== "USD";

  async function submit(e: React.FormEvent) {
    e.preventDefault(); setErr("");
    if (needsRate && !(Number(f.usd_rate) > 0)) { setErr(`اكتب كم ${f.currency} يساوي دولاراً واحداً`); return; }
    setBusy(true);
    const body: any = { name: f.name, currency: f.currency, usd_rate: needsRate ? f.usd_rate : "1", default_margin: f.default_margin };
    if (mode === "copy" && !source) body.from_provider = f.from_provider;
    else { body.base_url = f.base_url; if (f.api_token) body.api_token = f.api_token; }
    try {
      if (source) await api.patch(`/platform/library/sources/${source.id}/`, body);
      else await api.post("/platform/library/sources/", body);
      onDone();
    } catch (e: any) { setErr(e?.response?.data?.detail || "تعذّر الحفظ"); }
    finally { setBusy(false); }
  }

  return (
    <div style={overlay} onClick={onClose}>
      <form style={{ ...modal, width: 480 }} onClick={(e) => e.stopPropagation()} onSubmit={submit}>
        <div style={modalHead}>{source ? `إعدادات: ${source.name}` : "إضافة مصدر للمكتبة"}</div>
        <div style={{ padding: 20 }}>
          {!source && (
            <div style={seg}>
              <button type="button" onClick={() => setMode("copy")} style={segBtn(mode === "copy")}>📋 نسخ من مزوّد متجر</button>
              <button type="button" onClick={() => setMode("manual")} style={segBtn(mode === "manual")}>✍️ إدخال يدوي</button>
            </div>
          )}

          {mode === "copy" && !source ? (
            <L label="المزوّد (يُنسخ رابطه ومفتاحه وعملته)">
              {shopProviders === null ? <div style={{ color: "#64748b", fontSize: 13 }}>جارٍ التحميل...</div>
                : shopProviders.length === 0 ? <div style={{ color: "#b45309", fontSize: 13 }}>لا مزوّد ZDK لدى أي متجر — استعمل الإدخال اليدوي.</div>
                : (
                  <select style={inp} value={f.from_provider} required
                    onChange={(e) => {
                      const p = shopProviders.find((x) => String(x.id) === e.target.value);
                      setF({ ...f, from_provider: e.target.value, name: f.name || p?.name || "", currency: p?.currency || f.currency });
                    }}>
                    <option value="">— اختر —</option>
                    {shopProviders.map((p) => (
                      <option key={p.id} value={p.id}>{p.name} — {p.tenant} ({p.fingerprint.split(":")[1]})</option>
                    ))}
                  </select>
                )}
            </L>
          ) : (
            <>
              <L label="رابط API"><input style={inp} dir="ltr" value={f.base_url} placeholder="https://api.barakat.store"
                onChange={(e) => setF({ ...f, base_url: e.target.value })} /></L>
              <L label={source?.has_token ? "مفتاح API (اتركه فارغاً لإبقاء الحالي)" : "مفتاح API"}>
                <input style={inp} dir="ltr" type="password" value={f.api_token} required={!source?.has_token}
                  onChange={(e) => setF({ ...f, api_token: e.target.value })} autoComplete="off" />
              </L>
            </>
          )}

          <L label="الاسم"><input style={inp} value={f.name} required onChange={(e) => setF({ ...f, name: e.target.value })} placeholder="بركات" /></L>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 10 }}>
            <L label="عملة المزوّد">
              <select style={inp} value={f.currency} onChange={(e) => setF({ ...f, currency: e.target.value })}>
                {["TRY", "USD", "EUR", "SYP", "SAR", "AED", "IQD"].map((c) => <option key={c}>{c}</option>)}
              </select>
            </L>
            <L label={needsRate ? `كم ${f.currency} = 1$` : "سعر الصرف"}>
              <input style={inp} dir="ltr" type="number" step="0.0001" min="0" disabled={!needsRate}
                value={needsRate ? f.usd_rate : "1"} onChange={(e) => setF({ ...f, usd_rate: e.target.value })} />
            </L>
            <L label="هامش الربح %">
              <input style={inp} dir="ltr" type="number" step="0.5" min="0" value={f.default_margin}
                onChange={(e) => setF({ ...f, default_margin: e.target.value })} />
            </L>
          </div>
          <div style={{ fontSize: 12, color: "#64748b", lineHeight: 1.8 }}>
            أسعار المكتبة بالدولار: تكلفة الباقة = سعر المزوّد ÷ سعر الصرف، والسعر المقترح = التكلفة + الهامش.
          </div>
          {err && <div style={errBox}>{err}</div>}
          <div style={{ display: "flex", gap: 10, marginTop: 14 }}>
            <button className="btn g" style={{ flex: 1, height: 40 }} disabled={busy}>{busy ? "جارٍ..." : "حفظ"}</button>
            <button type="button" className="btn" style={{ height: 40, background: "#8a999e" }} onClick={onClose}>إلغاء</button>
          </div>
        </div>
      </form>
    </div>
  );
}

/* ── الكتالوج: اختيار ومعاينة واستيراد ── */
function CatalogBrowser({ source, onBack, onImported }: { source: Source; onBack: () => void; onImported: () => void }) {
  const [cat, setCat] = useState<Catalog | null>(null);
  const [err, setErr] = useState("");
  const [q, setQ] = useState("");
  const [filter, setFilter] = useState<Filter>("all");
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const [names, setNames] = useState<Record<string, string>>({});
  const [open, setOpen] = useState<string | null>(null);
  const [margin, setMargin] = useState(String(Number(source.default_margin)));
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<{ ok: boolean; text: string } | null>(null);

  function load() {
    setCat(null); setErr("");
    api.get(`/platform/library/sources/${source.id}/catalog/`)
      .then((r) => setCat(r.data))
      .catch((e) => setErr(e?.response?.data?.detail || "تعذّر جلب الكتالوج"));
  }
  useEffect(load, [source.id]);

  const hasChanges = (g: Group) => g.state === "existing" && (g.counts.new + g.counts.changed + g.counts.removed) > 0;
  const shown = useMemo(() => {
    const term = q.trim().toLowerCase();
    return (cat?.groups || []).filter((g) =>
      (!term || g.key.toLowerCase().includes(term) || g.library_name.toLowerCase().includes(term)
        || g.packages.some((p) => p.name.toLowerCase().includes(term)))
      && (filter === "all" || (filter === "new" && g.state === "new")
        || (filter === "existing" && g.state === "existing") || (filter === "changes" && hasChanges(g))));
  }, [cat, q, filter]);

  const counts = useMemo(() => {
    const gs = cat?.groups || [];
    return {
      all: gs.length, new: gs.filter((g) => g.state === "new").length,
      existing: gs.filter((g) => g.state === "existing").length, changes: gs.filter(hasChanges).length,
    };
  }, [cat]);

  const allShownPicked = shown.length > 0 && shown.every((g) => picked.has(g.key));
  function toggleAll() {
    setPicked((s) => {
      const n = new Set(s);
      for (const g of shown) allShownPicked ? n.delete(g.key) : n.add(g.key);
      return n;
    });
  }
  function toggle(k: string) {
    setPicked((s) => { const n = new Set(s); n.has(k) ? n.delete(k) : n.add(k); return n; });
  }

  const m = Number(margin) || 0;
  const withMargin = (usd: string | null) => (usd == null ? "—" : (Number(usd) * (1 + m / 100)).toFixed(2));
  const pickedPackages = (cat?.groups || []).filter((g) => picked.has(g.key)).reduce((n, g) => n + g.packages.length, 0);

  async function doImport() {
    if (!picked.size) return;
    const fresh = (cat?.groups || []).filter((g) => picked.has(g.key) && g.state === "new").length;
    const again = picked.size - fresh;
    if (!confirm(
      `إضافة إلى المكتبة العالمية:\n\n`
      + `• ${picked.size} لعبة (${pickedPackages} باقة)`
      + (fresh ? `\n• ${fresh} جديدة تُنشأ` : "")
      + (again ? `\n• ${again} موجودة تُحدَّث باقاتها وأسعارها` : "")
      + `\n• السعر المقترح = التكلفة + ${m}%\n\nمتابعة؟`)) return;
    setBusy(true); setResult(null);
    try {
      const picks = [...picked].map((key) => ({ key, name: names[key] || undefined }));
      const r = await api.post(`/platform/library/sources/${source.id}/import/`, { picks, margin });
      setResult({ ok: true, text: summaryText(r.data) });
      setPicked(new Set()); setNames({});
      onImported(); load();
    } catch (e: any) {
      setResult({ ok: false, text: e?.response?.data?.detail || "تعذّر الاستيراد" });
    } finally { setBusy(false); }
  }

  return (
    <>
      <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 14, flexWrap: "wrap" }}>
        <button style={ghostBtn} onClick={onBack}>→ المصادر</button>
        <h2 style={{ fontSize: 18 }}>كتالوج {source.name}</h2>
        {cat && <span style={{ color: "#94a3b8", fontSize: 13 }}>{cat.groups.length} لعبة · {cat.total_packages} باقة</span>}
        <button style={{ ...ghostBtn, marginInlineStart: "auto" }} onClick={load}>↻ إعادة الجلب</button>
      </div>

      {err ? <div style={errBoxDark}>{err}</div> : !cat ? (
        <div style={{ ...card, textAlign: "center", padding: 40, color: "#94a3b8" }}>⏳ جارٍ جلب الكتالوج من {source.name}...</div>
      ) : (
        <>
          {/* شريط الأدوات */}
          <div style={{ ...card, display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap", marginBottom: 12, position: "sticky", top: 8, zIndex: 5 }}>
            <input style={{ ...darkInp, width: 230 }} placeholder="🔍 ابحث عن لعبة أو باقة..." value={q} onChange={(e) => setQ(e.target.value)} />
            <div style={{ display: "flex", gap: 6 }}>
              {([["all", "الكل"], ["new", "جديد"], ["changes", "فيه تغييرات"], ["existing", "في المكتبة"]] as [Filter, string][]).map(([k, l]) => (
                <button key={k} onClick={() => setFilter(k)} style={chip(filter === k)}>{l} <b style={{ opacity: .8 }}>{counts[k]}</b></button>
              ))}
            </div>
            <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 13, color: "#cbd5e1" }}>
              الهامش
              <input style={{ ...darkInp, width: 70, textAlign: "center" }} type="number" step="0.5" min="0" dir="ltr"
                value={margin} onChange={(e) => setMargin(e.target.value)} />%
            </label>
            <div style={{ marginInlineStart: "auto", display: "flex", gap: 10, alignItems: "center" }}>
              <span style={{ fontSize: 13, color: "#94a3b8" }}>{picked.size} لعبة · {pickedPackages} باقة</span>
              <button style={{ ...primaryBtn, opacity: picked.size ? 1 : .5 }} disabled={!picked.size || busy} onClick={doImport}>
                {busy ? "جارٍ الإضافة..." : `⬇ إضافة إلى المكتبة (${picked.size})`}
              </button>
            </div>
          </div>

          {result && <div style={result.ok ? okBox : errBoxDark}>{result.text}</div>}
          {!!cat.amount_only?.length && (
            <details style={{ ...hintBox, borderColor: "#b45309", background: "#1c1408" }}>
              <summary style={{ cursor: "pointer" }}>
                ⚖️ <b>{cat.amount_only.length} لعبة يبيعها المزوّد «بالكمية» فقط</b> — سعرٌ للوحدة بلا باقات ثابتة، فلا تُستورد الآن.
                (أقسام «-ZNET» دُمجت مع ألعابها، وما فيه باقاتٌ ظاهرٌ في الجدول)
              </summary>
              <div style={{ marginTop: 8, display: "flex", flexWrap: "wrap", gap: 6 }}>
                {cat.amount_only.map((a) => (
                  <span key={a.key} style={miniPill} title={`الكمية من ${a.min} إلى ${a.max}`}>{a.key}</span>
                ))}
              </div>
            </details>
          )}
          {!picked.size && !result && (
            <div style={hintBox}>
              👇 <b>اختر الألعاب</b> بالخانات ☑ (أو خانة العنوان لتحديد الظاهر كلّه)، عدّل أسماءها إن شئت،
              ثم اضغط <b>«إضافة إلى المكتبة»</b> في الشريط أسفل الشاشة.
            </div>
          )}

          {picked.size > 0 && (
            <div style={actionBar}>
              <div style={{ flex: 1 }}>
                <b style={{ fontSize: 15 }}>✓ اخترت {picked.size} لعبة · {pickedPackages} باقة</b>
                <div style={{ fontSize: 12, color: "#bfdbfe" }}>السعر المقترح = التكلفة + {m}% — تعدّله من الهامش أعلاه</div>
              </div>
              <button style={{ ...ghostBtn, background: "transparent" }} onClick={() => setPicked(new Set())}>إلغاء التحديد</button>
              <button style={{ ...primaryBtn, background: "#16a34a", padding: "11px 22px", fontSize: 15 }} disabled={busy} onClick={doImport}>
                {busy ? "جارٍ الإضافة..." : `⬇ إضافة إلى المكتبة (${picked.size})`}
              </button>
            </div>
          )}

          <div style={{ overflow: "hidden", borderRadius: 10, border: "1px solid #1e293b", marginBottom: picked.size ? 90 : 0 }}>
            <table style={table}>
              <thead>
                <tr>
                  <th style={{ ...th, width: 44 }}><input type="checkbox" checked={allShownPicked} onChange={toggleAll} title="تحديد الظاهر كله" /></th>
                  <th style={{ ...th, textAlign: "right" }}>اللعبة عند المزوّد</th>
                  <th style={{ ...th, textAlign: "right" }}>الاسم في المكتبة</th>
                  <th style={th}>الباقات</th>
                  <th style={th}>الحالة</th>
                  <th style={th}></th>
                </tr>
              </thead>
              <tbody>
                {shown.length === 0 && (
                  <tr><td colSpan={6} style={{ ...td, padding: 24, color: "#64748b" }}>لا نتائج.</td></tr>
                )}
                {shown.map((g) => (
                  <Fragment key={g.key}>
                    <tr style={{ borderTop: "1px solid #1e293b", background: picked.has(g.key) ? "#13213b" : undefined }}>
                      <td style={td}><input type="checkbox" checked={picked.has(g.key)} onChange={() => toggle(g.key)} /></td>
                      <td style={{ ...td, textAlign: "right", fontWeight: 700 }}>
                        {g.key}
                        {g.require_player_id && <span style={{ ...miniPill, marginInlineStart: 6 }}>ID</span>}
                      </td>
                      <td style={{ ...td, textAlign: "right" }}>
                        <input style={{ ...darkInp, width: "100%", height: 32 }}
                          value={names[g.key] ?? (g.library_name || g.key)}
                          onChange={(e) => { setNames({ ...names, [g.key]: e.target.value }); if (!picked.has(g.key)) toggle(g.key); }} />
                      </td>
                      <td style={td}><b style={{ color: "#7dd3fc" }}>{g.packages.length}</b></td>
                      <td style={td}><GroupBadges g={g} /></td>
                      <td style={td}>
                        <button style={linkBtn} onClick={() => setOpen(open === g.key ? null : g.key)}>
                          {open === g.key ? "▲ إخفاء" : "▼ الباقات"}
                        </button>
                      </td>
                    </tr>
                    {open === g.key && (
                      <tr>
                        <td colSpan={6} style={{ padding: "4px 14px 14px", background: "#0b1222" }}>
                          <table style={{ ...table, fontSize: 12.5 }}>
                            <thead>
                              <tr>
                                {["رقمها لديه", "الباقة", `سعره (${cat.currency})`, "التكلفة $", `المقترح $ (+${m}%)`, "الحالة"].map((h) => (
                                  <th key={h} style={{ ...th, background: "transparent", padding: "8px 6px" }}>{h}</th>
                                ))}
                              </tr>
                            </thead>
                            <tbody>
                              {g.packages.map((p) => (
                                <tr key={p.ref} style={{ borderTop: "1px solid #1e293b", opacity: p.available ? 1 : .55 }}>
                                  <td style={{ ...td, padding: 6 }}><code style={{ direction: "ltr" }}>{p.ref}</code></td>
                                  <td style={{ ...td, padding: 6, textAlign: "right" }}>{p.name}{!p.available && " (غير متوفّرة)"}
                                    {p.sale_type === "amount" && (
                                      <div style={{ fontSize: 11, color: "#c4b5fd" }}>
                                        ⚖ بالكمية {Number(p.qty_min).toLocaleString("en-US")}–{Number(p.qty_max).toLocaleString("en-US")} · السعر لكل {Number(p.qty_unit).toLocaleString("en-US")}
                                      </div>
                                    )}
                                  </td>
                                  <td style={{ ...td, padding: 6, direction: "ltr" }}>{p.price}</td>
                                  <td style={{ ...td, padding: 6, direction: "ltr" }}>
                                    {p.usd ?? "—"}
                                    {p.state === "changed" && p.old_usd && (
                                      <span style={{ color: Number(p.usd) > Number(p.old_usd) ? "#fca5a5" : "#86efac", marginInlineStart: 6 }}>
                                        (كان {p.old_usd})
                                      </span>
                                    )}
                                  </td>
                                  <td style={{ ...td, padding: 6, direction: "ltr", fontWeight: 700, color: "#86efac" }}>{withMargin(p.usd)}</td>
                                  <td style={{ ...td, padding: 6 }}><StateBadge state={p.state} /></td>
                                </tr>
                              ))}
                              {g.removed.map((p) => (
                                <tr key={`rm-${p.ref}`} style={{ borderTop: "1px solid #1e293b" }}>
                                  <td style={{ ...td, padding: 6 }}><code style={{ direction: "ltr" }}>{p.ref}</code></td>
                                  <td style={{ ...td, padding: 6, textAlign: "right", textDecoration: "line-through", color: "#94a3b8" }}>{p.name}</td>
                                  <td colSpan={3} style={{ ...td, padding: 6, color: "#94a3b8" }}>أزالها المزوّد — تُطفأ في المكتبة عند الاستيراد/المزامنة</td>
                                  <td style={{ ...td, padding: 6 }}><span style={{ ...miniPill, background: "#7f1d1d", color: "#fecaca" }}>أُزيلت</span></td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </td>
                      </tr>
                    )}
                  </Fragment>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </>
  );
}

function GroupBadges({ g }: { g: Group }) {
  if (g.state === "new") return <span style={{ ...miniPill, background: "#14532d", color: "#bbf7d0" }}>جديد</span>;
  const bits = [];
  if (g.counts.new) bits.push(<span key="n" style={{ ...miniPill, background: "#14532d", color: "#bbf7d0" }}>+{g.counts.new} باقة</span>);
  if (g.counts.changed) bits.push(<span key="c" style={{ ...miniPill, background: "#78350f", color: "#fde68a" }}>{g.counts.changed} سعر تغيّر</span>);
  if (g.counts.removed) bits.push(<span key="r" style={{ ...miniPill, background: "#7f1d1d", color: "#fecaca" }}>أُزيلت {g.counts.removed}</span>);
  return (
    <span style={{ display: "inline-flex", gap: 4, flexWrap: "wrap", justifyContent: "center" }}>
      <span style={{ ...miniPill, background: "#1e3a8a", color: "#bfdbfe" }}>في المكتبة</span>
      {bits.length ? bits : <span style={{ ...miniPill, background: "#1e293b", color: "#94a3b8" }}>مطابق</span>}
    </span>
  );
}

function StateBadge({ state }: { state: Pkg["state"] }) {
  const s = {
    new: { t: "جديدة", bg: "#14532d", fg: "#bbf7d0" },
    changed: { t: "تغيّرت", bg: "#78350f", fg: "#fde68a" },
    same: { t: "مطابقة", bg: "#1e293b", fg: "#94a3b8" },
  }[state];
  return <span style={{ ...miniPill, background: s.bg, color: s.fg }}>{s.t}</span>;
}

function L({ label, children }: { label: string; children: React.ReactNode }) {
  return <div style={{ marginBottom: 10 }}><div style={{ fontSize: 12, color: "#64748b", marginBottom: 4 }}>{label}</div>{children}</div>;
}

const card: React.CSSProperties = { background: "#111a2e", border: "1px solid #1e293b", borderRadius: 12, padding: 16 };
const emptyCard: React.CSSProperties = { ...card, display: "flex", flexDirection: "column", alignItems: "center", gap: 8, padding: 40, textAlign: "center" };
const srcIcon: React.CSSProperties = { width: 42, height: 42, borderRadius: 11, background: "#1e293b", display: "grid", placeItems: "center", fontSize: 21 };
const pill: React.CSSProperties = { fontSize: 11, fontWeight: 800, padding: "3px 9px", borderRadius: 999, background: "#1e3a8a", color: "#bfdbfe" };
const miniPill: React.CSSProperties = { fontSize: 11, fontWeight: 700, padding: "2px 8px", borderRadius: 999, background: "#1e293b", color: "#cbd5e1", whiteSpace: "nowrap" };
const stats: React.CSSProperties = { display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 6, marginTop: 12 };
const primaryBtn: React.CSSProperties = { background: "#2563eb", color: "#fff", border: 0, padding: "8px 14px", borderRadius: 8, cursor: "pointer", fontWeight: 700, fontSize: 13.5 };
const ghostBtn: React.CSSProperties = { background: "#1e293b", color: "#e2e8f0", border: "1px solid #334155", padding: "8px 14px", borderRadius: 8, cursor: "pointer", fontWeight: 700, fontSize: 13.5 };
const iconBtn: React.CSSProperties = { ...ghostBtn, padding: "8px 11px" };
const linkBtn: React.CSSProperties = { background: "transparent", border: 0, color: "#7dd3fc", cursor: "pointer", fontSize: 12.5 };
const chip = (on: boolean): React.CSSProperties => ({
  background: on ? "#2563eb" : "#1e293b", color: on ? "#fff" : "#cbd5e1", border: "1px solid " + (on ? "#2563eb" : "#334155"),
  padding: "5px 11px", borderRadius: 999, cursor: "pointer", fontSize: 12.5,
});
const darkInp: React.CSSProperties = { background: "#0b1222", color: "#e2e8f0", border: "1px solid #334155", borderRadius: 8, height: 36, padding: "0 10px" };
const table: React.CSSProperties = { width: "100%", borderCollapse: "collapse", fontSize: 13.5 };
const th: React.CSSProperties = { background: "#1e293b", color: "#94a3b8", padding: "10px 8px", fontWeight: 600, fontSize: 12.5 };
const td: React.CSSProperties = { padding: "9px 8px", textAlign: "center" };
const hintBox: React.CSSProperties = { background: "#0c1a33", border: "1px dashed #2563eb", color: "#cbd5e1", padding: "10px 14px", borderRadius: 8, marginBottom: 12, fontSize: 13.5, lineHeight: 1.9 };
const actionBar: React.CSSProperties = {
  position: "fixed", bottom: 16, left: "50%", transform: "translateX(-50%)", zIndex: 50,
  width: "min(900px, calc(100vw - 32px))", display: "flex", alignItems: "center", gap: 12,
  background: "#1e3a8a", border: "1px solid #3b82f6", borderRadius: 14, padding: "12px 16px",
  boxShadow: "0 18px 50px rgba(0,0,0,.55)", color: "#fff",
};
const okBox: React.CSSProperties = { background: "#052e16", border: "1px solid #166534", color: "#bbf7d0", padding: "10px 14px", borderRadius: 8, marginBottom: 12, fontSize: 14 };
const errBoxDark: React.CSSProperties = { background: "#450a0a", border: "1px solid #7f1d1d", color: "#fecaca", padding: "10px 14px", borderRadius: 8, marginBottom: 12, fontSize: 14 };
const overlay: React.CSSProperties = { position: "fixed", inset: 0, background: "rgba(0,0,0,.6)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 1000 };
const modal: React.CSSProperties = { background: "#fff", color: "#0f172a", borderRadius: 10, overflow: "hidden" };
const modalHead: React.CSSProperties = { background: "#0f172a", color: "#e2e8f0", padding: "14px 18px", fontWeight: 700, fontSize: 16 };
const inp: React.CSSProperties = { width: "100%", height: 38 };
const errBox: React.CSSProperties = { background: "#fdecea", border: "1px solid #f5c6c2", color: "#b0463a", fontSize: 13, padding: "9px 12px", borderRadius: 5, marginTop: 10 };
const seg: React.CSSProperties = { display: "flex", gap: 4, background: "#f1f5f9", padding: 4, borderRadius: 9, marginBottom: 14 };
const segBtn = (on: boolean): React.CSSProperties => ({
  flex: 1, border: 0, borderRadius: 7, padding: "8px 6px", cursor: "pointer", fontSize: 13,
  background: on ? "#fff" : "transparent", fontWeight: on ? 700 : 400, color: "#0f172a",
  boxShadow: on ? "0 1px 3px rgba(0,0,0,.1)" : "none",
});
