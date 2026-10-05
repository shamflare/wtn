import { Fragment, useEffect, useMemo, useState } from "react";
import { api } from "../api";
import Icon from "../components/Icon";
import ScrollTop from "../components/ScrollTop";
import { matches } from "../search";
import {
  empty, Field, groupHead, ib, input, LedgerNote, Modal, money, note, OperatorTabs, OPERATORS, pageTitle,
  pageWrap, Switch, Toast, errText, useLedger,
} from "./kontorUi";

/* باقة خطّ كما يعرضها الخادم */
interface Pkg {
  id: number; operator: string; operator_label: string;
  category: number | null; category_name: string;
  znet_id: string; link_code: string; name: string; provider_name: string; details: string;
  days: number; gb: number; minutes: number;
  provider_cost: string; cost_price: string; recommended_price: string; profit: string;
  kind: "general" | "offer"; kind_label: string;
  status: "active" | "passive" | "sale_paused"; status_label: string;
  sort_order: number;
}

const STATUS = [
  { k: "", l: "كل الحالات" }, { k: "active", l: "نشطة" },
  { k: "passive", l: "معطّلة" }, { k: "sale_paused", l: "بيع موقوف" },
];

export default function Kontor() {
  const [pkgs, setPkgs] = useState<Pkg[]>([]);
  const [loading, setLoading] = useState(true);
  const [op, setOp] = useState("Turkcell");
  const [cat, setCat] = useState("");
  const [st, setSt] = useState("");
  const [kind, setKind] = useState("");
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);
  const [toast, setToast] = useState("");
  const [picked, setPicked] = useState<number[]>([]);
  const [editing, setEditing] = useState<number | null>(null);
  const [editingCode, setEditingCode] = useState<number | null>(null);
  const [codeDraft, setCodeDraft] = useState("");
  const [draft, setDraft] = useState("");
  const [modal, setModal] = useState<Pkg | null>(null);
  const ledger = useLedger();
  const [provs, setProvs] = useState<{ id: number; name: string }[]>([]);
  const [importFrom, setImportFrom] = useState<number | "">("");

  async function load() {
    const p = await api.get("/kontor/packages/");
    setPkgs(p.data);
  }
  useEffect(() => { load().catch(() => {}).finally(() => setLoading(false)); }, []);
  useEffect(() => {
    api.get("/kontor/providers/").then((r) => { setProvs(r.data); setImportFrom(r.data[0]?.id ?? ""); }).catch(() => {});
  }, []);

  function say(t: string) { setToast(t); setTimeout(() => setToast(""), 5000); }
  function switchOp(code: string) { setOp(code); setCat(""); setPicked([]); }

  const opPkgs = useMemo(() => pkgs.filter((p) => p.operator === op), [pkgs, op]);
  const counts = useMemo(
    () => Object.fromEntries(OPERATORS.map((o) => [o.code, pkgs.filter((p) => p.operator === o.code).length])),
    [pkgs],
  );
  const cats = useMemo(() => {
    const m = new Map<string, number>();
    for (const p of opPkgs) m.set(p.category_name || "—", (m.get(p.category_name || "—") ?? 0) + 1);
    return [...m.entries()];
  }, [opPkgs]);

  const shown = useMemo(() => opPkgs.filter((p) =>
    (!cat || (p.category_name || "—") === cat) && (!st || p.status === st) && (!kind || p.kind === kind) &&
    (!q || matches(q, p.name, p.znet_id, p.link_code, p.details))), [opPkgs, cat, st, kind, q]);

  // الباقات مجمّعة تحت فئاتها — كالألعاب تحت أسمائها في مجموعات الأسعار
  const grouped = useMemo(() => {
    const m = new Map<string, Pkg[]>();
    for (const p of shown) {
      const k = p.category_name || "—";
      if (!m.has(k)) m.set(k, []);
      m.get(k)!.push(p);
    }
    return [...m.entries()];
  }, [shown]);

  const stats = useMemo(() => {
    const active = opPkgs.filter((p) => p.status === "active");
    const noRec = opPkgs.filter((p) => Number(p.recommended_price) <= 0).length;
    const priced = active.filter((p) => Number(p.recommended_price) > 0 && Number(p.cost_price) > 0);
    const avg = priced.length
      ? priced.reduce((s, p) => s + (Number(p.recommended_price) / Number(p.cost_price) - 1) * 100, 0) / priced.length
      : 0;
    return { total: opPkgs.length, active: active.length,
      offers: opPkgs.filter((p) => p.kind === "offer").length, noRec, avg };
  }, [opPkgs]);

  async function patch(id: number, body: Partial<Pkg>) {
    setPkgs((list) => list.map((p) => (p.id === id ? { ...p, ...body } as Pkg : p)));
    try {
      const r = await api.patch(`/kontor/packages/${id}/`, body);
      setPkgs((list) => list.map((p) => (p.id === id ? r.data : p)));
    } catch (e: any) {
      say(e?.response?.data?.detail || "تعذّر الحفظ");
      load().catch(() => {});
    }
  }

  /** رقم الربط: يحفظه الخادم إن كان فريداً، وإلا يردّ السبب ويبقى القديم. */
  async function saveCode(p: Pkg) {
    const v = codeDraft.trim();
    setEditingCode(null);
    if (!v || v === p.link_code) return;
    try {
      const r = await api.patch(`/kontor/packages/${p.id}/`, { link_code: v });
      setPkgs((list) => list.map((x) => (x.id === p.id ? r.data : x)));
      say(`✅ رقم الربط صار ${v} — أبلغ من يربط معك بهذه الباقة`);
    } catch (e: any) {
      say(e?.response?.data?.link_code?.[0] || "تعذّر حفظ رقم الربط");
    }
  }

  function saveRec(p: Pkg) {
    const v = draft.trim();
    setEditing(null);
    if (v !== "" && Number(v) !== Number(p.recommended_price)) patch(p.id, { recommended_price: v });
  }

  async function bulk(body: { status?: string; kind?: string }, label: string) {
    if (!picked.length) return;
    try {
      const r = await api.post("/kontor/packages/bulk/", { ids: picked, ...body });
      say(`✅ ${label}: ${r.data.updated} باقة`);
      setPicked([]);
      await load();
    } catch (e: any) { say(e?.response?.data?.detail || "تعذّر التعديل"); }
  }

  async function importNow() {
    setBusy(true);
    try {
      const r = await api.post("/kontor/import/", importFrom ? { provider: importFrom } : {});
      say(`✅ من ${r.data.provider}: استُلم ${r.data.received} · جديد ${r.data.created} · محدّث ${r.data.updated}`);
      await load();
    } catch (e: any) {
      say(e?.response?.data?.detail || "تعذّر الاستيراد");
    } finally { setBusy(false); }
  }

  const toggle = (id: number) => setPicked((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]));
  const toggleMany = (ids: number[]) => {
    const all = ids.every((id) => picked.includes(id));
    setPicked((s) => (all ? s.filter((x) => !ids.includes(x)) : [...new Set([...s, ...ids])]));
  };
  const shownIds = shown.map((p) => p.id);
  const allPicked = shownIds.length > 0 && shownIds.every((id) => picked.includes(id));

  if (loading) return <div style={{ padding: 30 }}>جارٍ التحميل...</div>;

  return (
    <div style={pageWrap}>
      <ScrollTop />
      <h2 style={pageTitle}>
        <Icon name="phone" size={20} /> باقات الخطوط
        {provs.length > 1 && (
          <select value={importFrom} onChange={(e) => setImportFrom(Number(e.target.value))} title="الاستيراد من أيّ لوحة"
            style={{ ...input, width: 170, marginInlineStart: "auto", fontSize: 13 }}>
            {provs.map((p) => <option key={p.id} value={p.id}>من: {p.name}</option>)}
          </select>
        )}
        <button className="btn g" onClick={importNow} disabled={busy}
          style={{ marginInlineStart: provs.length > 1 ? 0 : "auto", fontSize: 13.5 }}>
          <Icon name="refresh" size={15} style={ib} />{busy ? "جارٍ الاستيراد..." : "استيراد من ZNET"}
        </button>
      </h2>

      {pkgs.length === 0 ? (
        <div className="card"><div style={empty}>
          لا باقات بعد — اضغط «استيراد من ZNET» لجلبها. يتطلّب مزوّد ZNET مُعدّاً في «الألعاب ⟵ مزوّدو API».
        </div></div>
      ) : (<>
        <div className="summary">
          <Stat label="باقات الشركة" value={`${stats.active} / ${stats.total}`} sub="نشطة من الكل" icon="grid" />
          <Stat label="عروض" value={String(stats.offers)} sub="باقات مخفّضة (وردية)" icon="tag" />
          <Stat label="بلا سعر موصى" value={String(stats.noRec)} sub="تُباع بصفر إن لم تُسعَّر"
            icon="warning" tone={stats.noRec ? "var(--danger)" : undefined} />
          <Stat label="متوسط الربح الموصى" value={`${stats.avg.toFixed(1)}%`} sub="على الباقات النشطة" icon="chart" />
        </div>

        <div className="toolbar">
          <OperatorTabs value={op} onChange={switchOp} counts={counts} />
          <select value={cat} onChange={(e) => setCat(e.target.value)} style={{ ...input, width: 190 }}>
            <option value="">كل الفئات</option>
            {cats.map(([n, c]) => <option key={n} value={n}>{n} ({c})</option>)}
          </select>
          <select value={st} onChange={(e) => setSt(e.target.value)} style={{ ...input, width: 130 }}>
            {STATUS.map((s) => <option key={s.k} value={s.k}>{s.l}</option>)}
          </select>
          <select value={kind} onChange={(e) => setKind(e.target.value)} style={{ ...input, width: 120 }}>
            <option value="">كل الأنواع</option><option value="general">عامة</option><option value="offer">عروض</option>
          </select>
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="بحث: اسم أو رقم ربط أو تفاصيل..."
            style={{ ...input, width: 230, marginInlineStart: "auto" }} />
        </div>

        <LedgerNote ledger={ledger} />
        <div style={note}>
          <b>رقم الربط</b> هو ما يراه وكلاؤك ويرسلونه في الربط الخارجي — افتراضه رقم الباقة في ZNET
          نفسه (فمن يربط مع ZNET يبقى على أرقامه)، واضغطه لتغييره. وإن اختلف عن رقم ZNET يظهر هذا تحته صغيراً.
          اضغط على <b>السعر الموصى</b> لتعديله — وهو ما يدفعه الوكيل غير المربوط بمجموعة أسعار.
          المفتاح يفعّل الباقة أو يعطّلها، والضغط على <b>النوع</b> يبدّله بين عامة وعرض.
          حدّد عدّة باقات لتعديلها دفعة واحدة. الأسعار الخاصة لكل مجموعة في «مجموعات الأسعار».
        </div>

        {picked.length > 0 && (
          <div className="toolbar" style={{ background: "var(--primary-tint)", borderColor: "var(--primary)" }}>
            <b>حُدّدت {picked.length} باقة:</b>
            <button className="btn g" onClick={() => bulk({ status: "active" }, "فُعّلت")}>تفعيل</button>
            <button className="btn r" onClick={() => bulk({ status: "passive" }, "عُطّلت")}>تعطيل</button>
            <button className="btn" onClick={() => bulk({ status: "sale_paused" }, "أوقف بيعها")}>إيقاف البيع</button>
            <span style={{ width: 1, height: 22, background: "var(--border-strong)" }} />
            <button className="btn" onClick={() => bulk({ kind: "general" }, "صارت عامة")}>عامة</button>
            <button className="btn" onClick={() => bulk({ kind: "offer" }, "صارت عروضاً")}>عرض</button>
            <button className="btn" style={{ marginInlineStart: "auto" }} onClick={() => setPicked([])}>إلغاء التحديد</button>
          </div>
        )}

        <div className="card"><div className="table-scroll">
          <table className="grid">
            <thead>
              <tr>
                <th style={{ width: 34 }}><input type="checkbox" checked={allPicked} onChange={() => toggleMany(shownIds)} /></th>
                <th style={{ width: 96 }} title="الرقم الذي يرسله الوكيل في الربط الخارجي — اضغط لتعديله">رقم الربط</th>
                <th className="cell-start">الباقة</th>
                <th>الكلفة {ledger.sym && `(${ledger.sym})`}</th><th>الموصى {ledger.sym && `(${ledger.sym})`}</th><th>الربح</th>
                <th>النوع</th><th>الحالة</th><th style={{ width: 44 }}></th>
              </tr>
            </thead>
            <tbody>
              {grouped.length === 0 && <tr><td colSpan={9} style={empty}>لا باقات تطابق الفلترة</td></tr>}
              {grouped.map(([name, rows]) => {
                const ids = rows.map((r) => r.id);
                return (
                  <Fragment key={name}>
                    <tr><td colSpan={9} style={groupHead}>
                      <input type="checkbox" checked={ids.every((id) => picked.includes(id))}
                        onChange={() => toggleMany(ids)} style={{ marginInlineEnd: 8, verticalAlign: -2 }} />
                      {name} <span style={{ fontWeight: 400, opacity: 0.75 }}>· {rows.length} باقة</span>
                    </td></tr>
                    {rows.map((p) => {
                      const cost = Number(p.cost_price), rec = Number(p.recommended_price);
                      const pct = cost > 0 && rec > 0 ? ((rec / cost - 1) * 100) : null;
                      return (
                        <tr key={p.id} className={picked.includes(p.id) ? "row-pick" : ""}
                          style={{ opacity: p.status === "active" ? 1 : 0.55 }}>
                          <td><input type="checkbox" checked={picked.includes(p.id)} onChange={() => toggle(p.id)} /></td>
                          <td className="num" style={{ cursor: "pointer" }} title="اضغط لتعديل رقم الربط"
                            onClick={() => { if (editingCode !== p.id) { setEditingCode(p.id); setCodeDraft(p.link_code); } }}>
                            {editingCode === p.id ? (
                              <input autoFocus value={codeDraft} dir="ltr" style={{ width: 80, height: 26, textAlign: "center" }}
                                onChange={(e) => setCodeDraft(e.target.value)} onBlur={() => saveCode(p)}
                                onKeyDown={(e) => {
                                  if (e.key === "Enter") saveCode(p);
                                  if (e.key === "Escape") { setCodeDraft(""); setEditingCode(null); }
                                }} />
                            ) : (<>
                              <code style={codeTag}>{p.link_code || "—"}</code>
                              {p.link_code !== p.znet_id && <div style={{ fontSize: 10.5, color: "var(--faint)", marginTop: 3 }}>ZNET {p.znet_id}</div>}
                            </>)}
                          </td>
                          <td className="cell-start">
                            <div style={{ fontWeight: 700 }}>
                              {p.name}
                              {p.provider_name && p.name !== p.provider_name && (
                                <span title={`اسمها في ZNET: ${p.provider_name}`} style={renamedTag}>معدَّل</span>
                              )}
                            </div>
                            <Specs p={p} />
                          </td>
                          <td className="num">
                            <div className="buy">{money(p.cost_price)}</div>
                            {ledger.base !== "TRY" && Number(p.provider_cost) > 0 &&
                              <div style={{ fontSize: 11, color: "var(--faint)" }}>{money(p.provider_cost)} ₺</div>}
                          </td>
                          <td className="num" style={{ cursor: "pointer", minWidth: 100 }}
                            onClick={() => { if (editing !== p.id) { setEditing(p.id); setDraft(rec ? p.recommended_price : ""); } }}>
                            {editing === p.id ? (
                              <input autoFocus type="number" step="any" value={draft} style={{ width: 86, height: 26 }}
                                onChange={(e) => setDraft(e.target.value)} onBlur={() => saveRec(p)}
                                onKeyDown={(e) => {
                                  if (e.key === "Enter") saveRec(p);
                                  if (e.key === "Escape") { setDraft(""); setEditing(null); }
                                }} />
                            ) : rec > 0
                              ? <b>{money(rec)}</b>
                              : <span style={{ color: "var(--danger)", fontSize: 12 }}>غير مسعّرة</span>}
                          </td>
                          <td className="num">
                            {pct === null ? <span style={{ color: "var(--faint)" }}>—</span> : (
                              <span style={{ color: rec - cost >= 0 ? "var(--ok)" : "var(--danger)", fontWeight: 700 }}>
                                {money(rec - cost)} <small style={{ fontWeight: 400, opacity: 0.8 }}>({pct.toFixed(1)}%)</small>
                              </span>
                            )}
                          </td>
                          <td>
                            <button type="button" onClick={() => patch(p.id, { kind: p.kind === "offer" ? "general" : "offer" })}
                              title="اضغط للتبديل" style={p.kind === "offer" ? kindOffer : kindGeneral}>
                              {p.kind === "offer" ? "عرض" : "عامة"}
                            </button>
                          </td>
                          <td>
                            {p.status === "sale_paused"
                              ? <button type="button" className="pill off" style={{ border: 0, cursor: "pointer" }}
                                  title="اضغط للتفعيل" onClick={() => patch(p.id, { status: "active" })}>بيع موقوف</button>
                              : <Switch on={p.status === "active"} title={p.status_label}
                                  onChange={(v) => patch(p.id, { status: v ? "active" : "passive" })} />}
                          </td>
                          <td>
                            <button type="button" className="btn" style={iconBtn} title="تعديل التفاصيل" onClick={() => setModal(p)}>
                              <Icon name="edit" size={14} />
                            </button>
                          </td>
                        </tr>
                      );
                    })}
                  </Fragment>
                );
              })}
            </tbody>
          </table>
        </div></div>
      </>)}

      {modal && (
        <PackageModal pkg={modal} onClose={() => setModal(null)}
          onSaved={(p) => { setPkgs((l) => l.map((x) => (x.id === p.id ? p : x))); setModal(null); say("✅ حُفظت الباقة"); }} />
      )}
      <Toast text={toast} />
    </div>
  );
}

/** سطر المواصفات تحت اسم الباقة: الأيام والإنترنت والدقائق إن عُرفت، ثم التفاصيل. */
function Specs({ p }: { p: Pkg }) {
  const bits = [
    p.days ? `${p.days} يوم` : "", p.gb ? `${p.gb} GB` : "", p.minutes ? `${p.minutes} دقيقة` : "",
  ].filter(Boolean);
  if (!bits.length && !p.details) return null;
  return (
    <div style={{ fontSize: 11.5, color: "var(--muted)", marginTop: 3, display: "flex", gap: 5, flexWrap: "wrap" }}>
      {bits.map((b) => <span key={b} className="chip" style={{ marginTop: 0 }}>{b}</span>)}
      {p.details && <span>{p.details}</span>}
    </div>
  );
}

function Stat({ label, value, sub, icon, tone }: { label: string; value: string; sub: string; icon: string; tone?: string }) {
  return (
    <div className="stat">
      <div className="label"><Icon name={icon} size={14} /> {label}</div>
      <div className="value num" style={tone ? { color: tone } : undefined}>{value}</div>
      <div style={{ fontSize: 11.5, color: "var(--faint)", marginTop: 2 }}>{sub}</div>
      <div className="spark" />
    </div>
  );
}

/** نافذة تفاصيل الباقة: المواصفات (للفلاتر عند الوكيل) والترتيب والحالة. */
function PackageModal({ pkg, onClose, onSaved }: { pkg: Pkg; onClose: () => void; onSaved: (p: Pkg) => void }) {
  const ledger = useLedger();
  const [f, setF] = useState({
    name: pkg.name, details: pkg.details, days: String(pkg.days || ""), gb: String(pkg.gb || ""),
    minutes: String(pkg.minutes || ""), sort_order: String(pkg.sort_order || ""),
    recommended_price: Number(pkg.recommended_price) ? pkg.recommended_price : "", status: pkg.status,
  });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const set = (k: keyof typeof f, v: string) => setF((o) => ({ ...o, [k]: v }));

  async function save() {
    setBusy(true); setErr("");
    try {
      const r = await api.patch(`/kontor/packages/${pkg.id}/`, {
        name: f.name.trim(), details: f.details, days: Number(f.days) || 0, gb: Number(f.gb) || 0,
        minutes: Number(f.minutes) || 0, sort_order: Number(f.sort_order) || 0,
        recommended_price: f.recommended_price || "0", status: f.status,
      });
      onSaved(r.data);
    } catch (e: any) {
      setErr(e?.response?.data?.detail || "تعذّر الحفظ — تحقّق من القيم");
    } finally { setBusy(false); }
  }

  return (
    <Modal title={`تعديل: ${pkg.name}`} onClose={onClose} width={520} footer={<>
      {err && <span style={errText}>{err}</span>}
      <button className="btn" style={{ marginInlineStart: "auto" }} onClick={onClose}>إلغاء</button>
      <button className="btn g" disabled={busy} onClick={save}>{busy ? "جارٍ الحفظ..." : "حفظ"}</button>
    </>}>
      <div style={{ fontSize: 12.5, color: "var(--muted)", marginBottom: 12 }}>
        {pkg.category_name} · رقم الربط <b className="num">{pkg.link_code}</b> · رقم ZNET <b className="num">{pkg.znet_id}</b> · الكلفة <b className="num">{money(pkg.cost_price)} {ledger.sym}</b>
        {ledger.base !== "TRY" && <> (<span className="num">{money(pkg.provider_cost)} ₺</span> لدى ZNET)</>}
        <div style={{ fontSize: 11.5 }}>الكلفة تأتي من ZNET وتتحدّث مع كل استيراد.</div>
      </div>
      <Field label="اسم الباقة" hint={`الاسم شكليّ تسمّيه كما تشاء — الشحن يعتمد رقم الربط لا الاسم. اسمها في ZNET: «${pkg.provider_name || pkg.name}». الاسم المعدَّل لا يمسّه الاستيراد، واتركه فارغاً ليعود إلى اسم ZNET.`}>
        <div style={{ display: "flex", gap: 6 }}>
          <input value={f.name} onChange={(e) => set("name", e.target.value)} style={input} />
          {pkg.provider_name && f.name !== pkg.provider_name && (
            <button type="button" className="btn" style={{ flex: "none", fontSize: 12 }}
              onClick={() => set("name", pkg.provider_name)}>اسم ZNET</button>
          )}
        </div>
      </Field>
      <Field label="التفاصيل" hint="سطر قصير يراه الوكيل تحت اسم الباقة — مثل: 30 يوم · 10GB · 1000 دقيقة">
        <input value={f.details} onChange={(e) => set("details", e.target.value)} style={input} />
      </Field>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 10 }}>
        <Field label="الأيام"><input type="number" value={f.days} onChange={(e) => set("days", e.target.value)} style={input} /></Field>
        <Field label="الإنترنت (GB)"><input type="number" value={f.gb} onChange={(e) => set("gb", e.target.value)} style={input} /></Field>
        <Field label="الدقائق"><input type="number" value={f.minutes} onChange={(e) => set("minutes", e.target.value)} style={input} /></Field>
      </div>
      <div style={{ fontSize: 11.5, color: "var(--muted)", margin: "-6px 0 14px" }}>
        هذه الأرقام تشغّل فلاتر «المدة/الإنترنت/الدقائق» في متجر الوكيل. اتركها فارغة إن لم تنطبق.
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 10 }}>
        <Field label={`السعر الموصى (${ledger.base || "…"})`}>
          <input type="number" step="any" value={f.recommended_price} onChange={(e) => set("recommended_price", e.target.value)} style={input} />
        </Field>
        <Field label="الترتيب">
          <input type="number" value={f.sort_order} onChange={(e) => set("sort_order", e.target.value)} style={input} />
        </Field>
        <Field label="الحالة">
          <select value={f.status} onChange={(e) => set("status", e.target.value)} style={input}>
            <option value="active">نشطة</option><option value="passive">معطّلة</option><option value="sale_paused">بيع موقوف</option>
          </select>
        </Field>
      </div>
    </Modal>
  );
}

const renamedTag: React.CSSProperties = {
  marginInlineStart: 6, fontSize: 10, fontWeight: 700, color: "var(--info)", background: "color-mix(in srgb, var(--info) 12%, transparent)",
  borderRadius: 999, padding: "1px 7px", verticalAlign: 2,
};
const codeTag: React.CSSProperties = {
  fontFamily: "ui-monospace, Consolas, monospace", fontWeight: 800, fontSize: 12.5, direction: "ltr",
  background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: 6, padding: "2px 8px",
};
const iconBtn: React.CSSProperties = { width: 30, height: 28, padding: 0, display: "inline-flex", alignItems: "center", justifyContent: "center" };
const kindBase: React.CSSProperties = {
  border: 0, cursor: "pointer", fontSize: 11.5, fontWeight: 700, padding: "3px 11px", borderRadius: 999,
};
const kindGeneral: React.CSSProperties = { ...kindBase, background: "#fff4cc", color: "#8a6a00" };
const kindOffer: React.CSSProperties = { ...kindBase, background: "#fde2ef", color: "#b0306e" };
