import { useEffect, useState } from "react";
import { api } from "../api";
import { labelOf, symbolOf } from "../currency";

/**
 * معاينة طلب تسجيلٍ ذاتي — ما كتبه الوكيل الجديد وصورتا هويته ومحله.
 *
 * ثلاثة قرارات: **قبول** (ومعه عملته وحدّه الائتماني ومجموعة أسعاره — تُضبط هنا
 * مرّةً بدل فتح إعداداته بعد القبول)، و**رفض** (يُحذف الطلب ويتحرّر رقم دخوله)،
 * و**إلغاء** (تُغلق النافذة ويبقى الطلب معلّقاً حتى تعود إليه).
 */
export interface PendingReg {
  id: number; login_id: string; name: string; country: string; province: string;
  whatsapp: string; id_image: string; shop_image: string; created_at: string;
  /** ما اختاره الوكيل نفسه في التسجيل — فارغ = عملة الموقع */
  display_currency?: string;
}

export default function RegistrationReviewModal({ reg, onClose, onDecided }: {
  reg: PendingReg; onClose: () => void; onDecided: (text: string) => void;
}) {
  const [base, setBase] = useState("USD");
  const [rated, setRated] = useState<string[]>([]);
  const [groups, setGroups] = useState<{ id: number; name: string }[]>([]);
  // ما اختاره الوكيل محدَّدٌ مسبقاً — ولصاحب المتجر تغييره قبل القبول
  const [cur, setCur] = useState(reg.display_currency || "");
  const [limit, setLimit] = useState("0");
  const [group, setGroup] = useState("");
  const [busy, setBusy] = useState<"" | "approve" | "reject">("");
  const [err, setErr] = useState("");
  const [zoom, setZoom] = useState<string | null>(null);

  useEffect(() => {
    api.get("/settings/exchange/").then((r) => {
      setBase(r.data.base_currency || "USD");
      setRated(Object.entries(r.data.exchange_rates || {})
        .filter(([, v]) => Number(v) > 0).map(([c]) => c).sort());
    }).catch(() => {});
    api.get("/catalog/price-groups/").then((r) => setGroups(r.data.results || r.data)).catch(() => {});
  }, []);
  const own = cur || base;

  async function decide(action: "approve" | "reject") {
    if (action === "reject" && !confirm(`رفض طلب «${reg.name}» وحذفه نهائياً؟`)) return;
    setBusy(action); setErr("");
    try {
      await api.post(`/dealers/${reg.id}/registration/`, action === "approve"
        ? { action, display_currency: cur, credit_limit: limit || "0", price_group: group || null }
        : { action });
      onDecided(action === "approve"
        ? `✓ قُبل «${reg.name}» — يدخل الآن برقم ${reg.login_id}`
        : `رُفض طلب «${reg.name}» وحُذف`);
    } catch (e: any) {
      setErr(e?.response?.data?.detail || "تعذّر تنفيذ القرار");
      setBusy("");
    }
  }

  return (
    <div style={overlay} onClick={busy ? undefined : onClose}>
      <div style={modal} onClick={(e) => e.stopPropagation()}>
        <div style={head}>
          <b style={{ fontSize: 16 }}>طلب تسجيل وكيل جديد — {reg.name}</b>
          <span style={{ fontSize: 12, opacity: 0.85, marginInlineStart: 8 }}>{reg.created_at}</span>
          <button onClick={onClose} style={xBtn} disabled={!!busy}>✕</button>
        </div>

        <div style={{ padding: 18, overflowY: "auto" }}>
          <div style={grid2}>
            <Info label="الاسم الكامل" value={reg.name} />
            <Info label="رقم الدخول" value={reg.login_id} ltr />
            <Info label="واتساب" value={reg.whatsapp} ltr
              link={reg.whatsapp ? `https://wa.me/${reg.whatsapp.replace(/[^\d]/g, "")}` : ""} />
            <Info label="الدولة / المدينة" value={[reg.country, reg.province].filter(Boolean).join(" · ") || "—"} />
          </div>

          <div style={{ ...grid2, marginTop: 14 }}>
            <Photo label="صورة الهوية" src={reg.id_image} onZoom={setZoom} />
            <Photo label="صورة المحل" src={reg.shop_image} onZoom={setZoom} />
          </div>

          <div style={section}>عند القبول — تستطيع تعديلها لاحقاً من ⚙ إعداداته</div>
          <div style={grid3}>
            <label style={lbl}>عملة الوكيل {reg.display_currency && <span style={{ color: "#b45309" }}>(اختارها هو)</span>}
              <select value={cur} onChange={(e) => setCur(e.target.value)} style={inp}>
                <option value="">{symbolOf(base)} عملة الموقع ({base})</option>
                {rated.filter((c) => c !== base).map((c) => (
                  <option key={c} value={c}>{symbolOf(c)} {labelOf(c)} ({c})</option>
                ))}
              </select>
            </label>
            <label style={lbl}>الحد الائتماني ({symbolOf(own)})
              <input type="number" max="0" step="0.01" value={limit} onChange={(e) => setLimit(e.target.value)}
                style={{ ...inp, direction: "ltr" }} />
            </label>
            <label style={lbl}>مجموعة الأسعار
              <select value={group} onChange={(e) => setGroup(e.target.value)} style={inp}>
                <option value="">— السعر الموصى —</option>
                {groups.map((g) => <option key={g.id} value={g.id}>{g.name}</option>)}
              </select>
            </label>
          </div>
          {err && <div style={errBox}>{err}</div>}
        </div>

        <div style={foot}>
          <button className="btn g" style={{ minWidth: 120 }} disabled={!!busy} onClick={() => decide("approve")}>
            {busy === "approve" ? "جارٍ..." : "✓ قبول"}
          </button>
          <button className="btn r" style={{ minWidth: 100 }} disabled={!!busy} onClick={() => decide("reject")}>
            {busy === "reject" ? "جارٍ..." : "✕ رفض"}
          </button>
          <button className="btn" style={{ background: "#8a999e", marginInlineStart: "auto" }} disabled={!!busy}
            onClick={onClose} title="يبقى الطلب معلّقاً حتى تعود إليه">
            إلغاء (يبقى معلّقاً)
          </button>
        </div>
      </div>

      {zoom && (
        <div style={{ ...overlay, zIndex: 1100, cursor: "zoom-out" }} onClick={(e) => { e.stopPropagation(); setZoom(null); }}>
          <img src={zoom} alt="" style={{ maxWidth: "92vw", maxHeight: "92vh", borderRadius: 8, background: "#fff" }} />
        </div>
      )}
    </div>
  );
}

function Info({ label, value, ltr, link }: { label: string; value: string; ltr?: boolean; link?: string }) {
  return (
    <div style={{ background: "var(--row-alt)", borderRadius: 8, padding: "8px 12px" }}>
      <div style={{ fontSize: 11.5, color: "var(--muted)" }}>{label}</div>
      {link
        ? <a href={link} target="_blank" rel="noreferrer" style={{ fontWeight: 700, direction: ltr ? "ltr" : undefined, display: "inline-block" }}>{value}</a>
        : <div style={{ fontWeight: 700, direction: ltr ? "ltr" : undefined, textAlign: ltr ? "right" : undefined }}>{value || "—"}</div>}
    </div>
  );
}

function Photo({ label, src, onZoom }: { label: string; src: string; onZoom: (s: string) => void }) {
  return (
    <div>
      <div style={{ fontSize: 12, color: "var(--muted)", marginBottom: 4 }}>{label}</div>
      {src ? (
        <img src={src} alt={label} onClick={() => onZoom(src)} title="اضغط للتكبير"
          style={{ width: "100%", height: 170, objectFit: "contain", background: "#f1f5f9",
                   borderRadius: 8, border: "1px solid var(--border)", cursor: "zoom-in" }} />
      ) : (
        <div style={{ height: 170, borderRadius: 8, border: "1px dashed var(--border)", display: "grid",
                      placeItems: "center", color: "var(--muted)", fontSize: 13 }}>لم يرفعها</div>
      )}
    </div>
  );
}

const overlay: React.CSSProperties = { position: "fixed", inset: 0, background: "rgba(0,0,0,.5)", zIndex: 1000, display: "flex", alignItems: "center", justifyContent: "center" };
const modal: React.CSSProperties = { width: "min(760px, 94vw)", maxHeight: "92vh", background: "#fff", borderRadius: 12, overflow: "hidden", display: "flex", flexDirection: "column", boxShadow: "0 20px 60px rgba(0,0,0,.3)" };
const head: React.CSSProperties = { background: "#b45309", color: "#fff", padding: "12px 16px", display: "flex", alignItems: "center" };
const xBtn: React.CSSProperties = { marginInlineStart: "auto", background: "transparent", border: 0, color: "#fff", fontSize: 18, cursor: "pointer" };
const foot: React.CSSProperties = { borderTop: "1px solid var(--border)", padding: "12px 16px", display: "flex", gap: 10, alignItems: "center" };
const grid2: React.CSSProperties = { display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 };
const grid3: React.CSSProperties = { display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 10 };
const section: React.CSSProperties = { margin: "18px 0 8px", fontWeight: 800, fontSize: 13.5, color: "var(--primary-dark)" };
const lbl: React.CSSProperties = { display: "flex", flexDirection: "column", gap: 4, fontSize: 12, color: "var(--muted)" };
const inp: React.CSSProperties = { width: "100%", height: 36 };
const errBox: React.CSSProperties = { marginTop: 12, background: "#fdecea", border: "1px solid #f5c6c2", color: "#b0463a", padding: "8px 12px", borderRadius: 6, fontSize: 13 };
