import { Fragment, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import Icon from "../components/Icon";
import ScrollTop from "../components/ScrollTop";
import { matches } from "../search";
import {
  empty, errText, Field, groupHead, ib, input, Modal, note, OperatorTabs, pageTitle, pageWrap,
  preview, Toast,
} from "./kontorUi";

interface Prov { id: number; name: string; status: string; ready: boolean; currency: string }
interface LinkCell { code: string; cost: string }
interface Row {
  id: number; link_code: string; name: string; znet_id: string; category: string; status: string; kind: string;
  provider: number | null; provider_alt1: number | null; provider_alt2: number | null;
  links: Record<string, LinkCell>;
}
type Slot = "provider" | "provider_alt1" | "provider_alt2";
const SLOTS: { key: Slot; label: string }[] = [
  { key: "provider", label: "المزوّد الرئيسي" },
  { key: "provider_alt1", label: "API 1 (بديل)" },
  { key: "provider_alt2", label: "API 2 (بديل)" },
];

/**
 * توجيه باقات الخطوط — نفس فكرة الألعاب: لكل باقة مزوّد رئيسي وبديلان يُجرَّبان
 * بالترتيب عند الرفض، ولكل مزوّد رقم الباقة **لديه** (اللوحات ترقّم مختلفاً).
 */
export default function KontorRouting() {
  const [op, setOp] = useState("Turkcell");
  const [provs, setProvs] = useState<Prov[]>([]);
  const [rows, setRows] = useState<Row[]>([]);
  const [loading, setLoading] = useState(true);
  const [cat, setCat] = useState("");
  const [q, setQ] = useState("");
  const [picked, setPicked] = useState<number[]>([]);
  const [bulk, setBulk] = useState<Record<Slot, string>>({ provider: "", provider_alt1: "", provider_alt2: "" });
  const [editing, setEditing] = useState<{ row: number; prov: number } | null>(null);
  const [draft, setDraft] = useState("");
  const [autoOpen, setAutoOpen] = useState(false);
  const [toast, setToast] = useState("");

  async function load() {
    const r = await api.get(`/kontor/routing/?operator=${op}`);
    setProvs(r.data.providers); setRows(r.data.rows);
  }
  useEffect(() => { setLoading(true); setPicked([]); setCat(""); load().catch(() => {}).finally(() => setLoading(false)); }, [op]);

  function say(t: string) { setToast(t); setTimeout(() => setToast(""), 5000); }
  const provName = (id: number | null) => provs.find((p) => p.id === id)?.name;

  const cats = useMemo(() => [...new Set(rows.map((r) => r.category || "—"))], [rows]);
  const shown = useMemo(() => rows.filter((r) =>
    (!cat || (r.category || "—") === cat) && (!q || matches(q, r.name, r.link_code, r.znet_id))), [rows, cat, q]);
  const grouped = useMemo(() => {
    const m = new Map<string, Row[]>();
    for (const r of shown) { const k = r.category || "—"; if (!m.has(k)) m.set(k, []); m.get(k)!.push(r); }
    return [...m.entries()];
  }, [shown]);

  async function route(ids: number[], changes: Partial<Record<Slot, number | null>>) {
    setRows((rs) => rs.map((r) => (ids.includes(r.id) ? { ...r, ...changes } : r)));
    try {
      await api.patch("/kontor/routing/", { packages: ids, ...changes });
      say(`✅ وُجّهت ${ids.length} باقة`);
    } catch (e: any) { say(e?.response?.data?.detail || "تعذّر الحفظ"); load().catch(() => {}); }
  }

  function applyBulk() {
    const changes: Partial<Record<Slot, number | null>> = {};
    for (const s of SLOTS) {
      const v = bulk[s.key];
      if (v === "") continue;
      changes[s.key] = v === "none" ? null : Number(v);
    }
    if (!Object.keys(changes).length) return say("اختر مزوّداً واحداً على الأقل");
    route(picked, changes).then(() => setPicked([]));
  }

  async function saveCode(r: Row, provId: number) {
    const v = draft.trim();
    setEditing(null);
    if (v === (r.links[provId]?.code ?? "")) return;
    try {
      if (!v) {
        await api.delete("/kontor/links/", { data: { package: r.id, provider: provId } });
        setRows((rs) => rs.map((x) => {
          if (x.id !== r.id) return x;
          const links = { ...x.links }; delete links[provId]; return { ...x, links };
        }));
        say("فُكّ ربط الباقة بهذا المزوّد");
      } else {
        const res = await api.post("/kontor/links/", { package: r.id, provider: provId, code: v });
        setRows((rs) => rs.map((x) => x.id === r.id
          ? { ...x, links: { ...x.links, [provId]: { code: res.data.code, cost: res.data.cost } } } : x));
        say(`✅ رقم الباقة لدى ${provName(provId)}: ${v}`);
      }
    } catch (e: any) { say(e?.response?.data?.detail || "تعذّر الحفظ"); }
  }

  const toggle = (id: number) => setPicked((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]));
  const toggleMany = (ids: number[]) => {
    const all = ids.every((id) => picked.includes(id));
    setPicked((s) => (all ? s.filter((x) => !ids.includes(x)) : [...new Set([...s, ...ids])]));
  };
  const shownIds = shown.map((r) => r.id);

  return (
    <div style={pageWrap}>
      <ScrollTop />
      <h2 style={pageTitle}>
        <Icon name="api" size={20} /> توجيه الباقات والمزوّدين
        <button className="btn" style={{ marginInlineStart: "auto", fontSize: 13.5 }} onClick={() => setAutoOpen(true)}
          disabled={provs.length < 1}>
          <Icon name="link" size={15} style={ib} />ربط تلقائي من مزوّد
        </button>
      </h2>

      <div style={note}>
        لكل باقة <b>مزوّد رئيسي</b> و<b>بديلان</b>: إن رفض الرئيسي الشحنة صراحةً تُرسَل إلى API 1 ثم API 2 تلقائياً
        — وإن انقطع الردّ بعد الإرسال لا تُعاد إلى بديل بل تُتابَع، كي لا يُشحن الرقم مرّتين. وتحت كل مزوّد
        <b> رقم الباقة لديه</b> (اضغطه لتعديله): لكل لوحة ZNET أرقامها، ولا تُرسَل باقة إلى مزوّد ليست مربوطة عنده.
        <div style={{ marginTop: 6, display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
          <span>مزوّدو الخطوط:</span>
          {provs.length === 0 && <span style={{ color: "var(--danger)" }}>لا مزوّد — </span>}
          {provs.map((p) => (
            <span key={p.id} className={`pill ${p.ready && p.status === "active" ? "on" : "off"}`}
              title={p.ready ? (p.status === "active" ? "جاهز" : "معطّل") : "إعداد ناقص"}>{p.name}</span>
          ))}
          <Link to="/oyunpin/providers" style={{ fontWeight: 700 }}>+ إضافة لوحة ZNET من «مزوّدو API»</Link>
        </div>
      </div>

      <div className="toolbar">
        <OperatorTabs value={op} onChange={setOp} />
        <select value={cat} onChange={(e) => setCat(e.target.value)} style={{ ...input, width: 160 }}>
          <option value="">كل الفئات</option>
          {cats.map((c) => <option key={c} value={c}>{c}</option>)}
        </select>
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="بحث: باقة أو رقم ربط..."
          style={{ ...input, width: 220, marginInlineStart: "auto" }} />
      </div>

      {picked.length > 0 && (
        <div className="toolbar" style={{ background: "var(--primary-tint)", borderColor: "var(--primary)" }}>
          <b>حُدّدت {picked.length} باقة — وجّهها إلى:</b>
          {SLOTS.map((s) => (
            <select key={s.key} value={bulk[s.key]} style={{ ...input, width: 170 }}
              onChange={(e) => setBulk((b) => ({ ...b, [s.key]: e.target.value }))}>
              <option value="">{s.label}: بلا تغيير</option>
              <option value="none">{s.label}: فارغ</option>
              {provs.map((p) => <option key={p.id} value={p.id}>{s.label}: {p.name}</option>)}
            </select>
          ))}
          <button className="btn g" onClick={applyBulk}>تطبيق</button>
          <button className="btn" style={{ marginInlineStart: "auto" }} onClick={() => setPicked([])}>إلغاء التحديد</button>
        </div>
      )}

      {loading ? <div style={{ padding: 30 }}>جارٍ التحميل...</div> : (
        <div className="card"><div className="table-scroll">
          <table className="grid">
            <thead>
              <tr>
                <th style={{ width: 34 }}>
                  <input type="checkbox" checked={shownIds.length > 0 && shownIds.every((id) => picked.includes(id))}
                    onChange={() => toggleMany(shownIds)} />
                </th>
                <th style={{ width: 90 }}>رقم الربط</th>
                <th className="cell-start">الباقة</th>
                {SLOTS.map((s) => <th key={s.key}>{s.label}</th>)}
              </tr>
            </thead>
            <tbody>
              {grouped.length === 0 && <tr><td colSpan={6} style={empty}>لا باقات</td></tr>}
              {grouped.map(([name, list]) => (
                <Fragment key={name}>
                  <tr><td colSpan={6} style={groupHead}>
                    <input type="checkbox" checked={list.every((r) => picked.includes(r.id))}
                      onChange={() => toggleMany(list.map((r) => r.id))} style={{ marginInlineEnd: 8, verticalAlign: -2 }} />
                    {name} <span style={{ fontWeight: 400, opacity: 0.75 }}>· {list.length}</span>
                  </td></tr>
                  {list.map((r) => (
                    <tr key={r.id} className={picked.includes(r.id) ? "row-pick" : ""}
                      style={{ opacity: r.status === "active" ? 1 : 0.55 }}>
                      <td><input type="checkbox" checked={picked.includes(r.id)} onChange={() => toggle(r.id)} /></td>
                      <td className="num" style={{ fontWeight: 700 }}>{r.link_code}</td>
                      <td className="cell-start" style={{ fontWeight: 700 }}>{r.name}</td>
                      {SLOTS.map((s) => {
                        const pid = r[s.key];
                        const link = pid ? r.links[pid] : undefined;
                        const isEd = editing?.row === r.id && editing?.prov === pid;
                        return (
                          <td key={s.key} style={{ minWidth: 150 }}>
                            <select value={pid ?? ""} style={routeSel(!!pid)}
                              onChange={(e) => route([r.id], { [s.key]: e.target.value ? Number(e.target.value) : null })}>
                              <option value="">—</option>
                              {provs.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
                            </select>
                            {pid && (
                              <div style={{ marginTop: 5, fontSize: 11.5 }}>
                                {isEd ? (
                                  <input autoFocus value={draft} dir="ltr" placeholder="فارغ = فكّ الربط"
                                    style={{ width: 110, height: 24, textAlign: "center" }}
                                    onChange={(e) => setDraft(e.target.value)} onBlur={() => saveCode(r, pid)}
                                    onKeyDown={(e) => {
                                      if (e.key === "Enter") saveCode(r, pid);
                                      if (e.key === "Escape") { setEditing(null); }
                                    }} />
                                ) : link ? (
                                  <button type="button" style={codeBtn} title="رقم الباقة لدى هذا المزوّد — اضغط لتعديله"
                                    onClick={() => { setEditing({ row: r.id, prov: pid }); setDraft(link.code); }}>
                                    #{link.code}{Number(link.cost) > 0 && <span style={{ opacity: 0.65 }}> · {link.cost} ₺</span>}
                                  </button>
                                ) : (
                                  <button type="button" style={{ ...codeBtn, color: "var(--danger)", borderColor: "#f0caca" }}
                                    title="لا تُرسَل الباقة إلى مزوّد ليست مربوطة لديه"
                                    onClick={() => { setEditing({ row: r.id, prov: pid }); setDraft(""); }}>
                                    غير مربوطة — اربط
                                  </button>
                                )}
                              </div>
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
        </div></div>
      )}

      {autoOpen && <AutoLinkModal provs={provs} onClose={() => setAutoOpen(false)}
        onDone={(m) => { setAutoOpen(false); say(m); load().catch(() => {}); }} />}
      <Toast text={toast} />
    </div>
  );
}

/** ربط تلقائي: يقرأ باقات لوحة ZNET أخرى ويطابقها مع باقاتنا بالرقم ثم بالاسم. */
function AutoLinkModal({ provs, onClose, onDone }: { provs: Prov[]; onClose: () => void; onDone: (m: string) => void }) {
  const [prov, setProv] = useState<number | "">(provs[0]?.id ?? "");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [rep, setRep] = useState<any>(null);

  async function run() {
    setBusy(true); setErr(""); setRep(null);
    try { setRep((await api.post("/kontor/auto-link/", { provider: prov })).data); }
    catch (e: any) { setErr(e?.response?.data?.detail || "تعذّر الربط"); }
    finally { setBusy(false); }
  }

  return (
    <Modal title="ربط تلقائي من مزوّد" onClose={onClose} width={520} footer={<>
      {err && <span style={errText}>{err}</span>}
      {rep ? (
        <button className="btn g" style={{ marginInlineStart: "auto" }}
          onClick={() => onDone(`✅ رُبطت ${rep.by_id + rep.by_name} باقة لدى ${rep.provider}`)}>تم</button>
      ) : (<>
        <button className="btn" style={{ marginInlineStart: "auto" }} onClick={onClose}>إلغاء</button>
        <button className="btn g" disabled={busy || !prov} onClick={run}>{busy ? "جارٍ القراءة..." : "ابدأ الربط"}</button>
      </>)}
    </>}>
      {rep ? (
        <>
          <div style={{ marginBottom: 10, lineHeight: 1.9 }}>
            من «<b>{rep.provider}</b>» ({rep.received} باقة لديه):<br />
            ✅ رُبطت بالرقم: <b>{rep.by_id}</b> · ✅ بالاسم: <b>{rep.by_name}</b> ·{" "}
            <span style={{ color: rep.unmatched.length ? "var(--danger)" : undefined }}>بلا مطابقة: <b>{rep.unmatched.length}</b></span>
          </div>
          {rep.unmatched.length > 0 && (
            <div style={{ ...preview, maxHeight: 220, overflowY: "auto" }}>
              هذه لم تُربط — اربطها يدوياً بالضغط على «غير مربوطة» في الجدول إن كانت لديه:
              <ul style={{ margin: "6px 0 0", paddingInlineStart: 18 }}>
                {rep.unmatched.map((u: string) => <li key={u}>{u}</li>)}
              </ul>
            </div>
          )}
        </>
      ) : (<>
        <Field label="المزوّد" hint="تُقرأ قائمة باقاته وتُطابَق مع باقاتنا: بنفس رقم ZNET أوّلاً، وإلا بالاسم. لا تُنشأ باقات جديدة ولا يتغيّر التوجيه — يُسجَّل رقم كل باقة لديه وكلفتها فقط.">
          <select value={prov} onChange={(e) => setProv(Number(e.target.value))} style={input}>
            {provs.map((p) => <option key={p.id} value={p.id}>{p.name}{p.ready ? "" : " — إعداد ناقص"}</option>)}
          </select>
        </Field>
        <div style={preview}>بعد الربط وجّه الباقات إليه من الجدول (رئيسياً أو بديلاً) — فردياً أو بتحديد عدّة باقات.</div>
      </>)}
    </Modal>
  );
}

const routeSel = (on: boolean): React.CSSProperties => ({
  width: 140, height: 30, borderRadius: 6, border: "1px solid var(--border)", background: "var(--surface)",
  padding: "0 6px", fontWeight: on ? 700 : 400, color: on ? "var(--primary-dark)" : "var(--faint)",
});
const codeBtn: React.CSSProperties = {
  border: "1px solid var(--border)", background: "var(--surface-2)", borderRadius: 6, padding: "1px 8px",
  fontFamily: "ui-monospace, Consolas, monospace", fontSize: 11.5, cursor: "pointer", direction: "ltr",
};
