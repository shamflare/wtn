import { Fragment, useEffect, useMemo, useState } from "react";
import { api } from "../api";
import { showPrice } from "../unitPrice";

/**
 * «ربط تلقائي» لعمود مزوّدٍ واحد — معاينةٌ قبل الحفظ.
 *
 * المؤكَّد (من المكتبة برقم المزوّد) والمطابق بثقةٍ عالية محدَّدان مسبقاً؛ المشكوك
 * غير محدَّد ويُعرض سببُ الشكّ بجانبه. لا يُحفظ شيءٌ قبل «اربط المحدَّد»، ولا يُمسّ
 * ربطٌ قائم.
 */
interface Suggestion {
  product: number; product_name: string; game_name: string;
  package: { id: string; name: string; game: string; kupur: string; price: string };
  price_base: string | null; ref_price: string | null;
  confidence: "exact" | "high" | "medium";
  reasons: string[]; warnings?: string[];
  sale_type?: string; qty_unit?: number;
}
interface Unmatched { product: number; product_name: string; game_name: string; why: string }

const CONF = {
  exact: { label: "مؤكَّد", bg: "#dcfce7", fg: "#166534", hint: "رقمها لدى المزوّد من المكتبة — بلا تخمين" },
  high: { label: "ثقة عالية", bg: "#e0f2fe", fg: "#075985", hint: "اللعبة والرقم والوحدة متطابقة والسعر متقارب" },
  medium: { label: "مشكوك — راجعها", bg: "#fef3c7", fg: "#92400e", hint: "شرطٌ ناقص — حدّدها بنفسك إن كانت صحيحة" },
};

export default function AutoLinkModal({ provider, baseSymbol, onClose, onDone }: {
  provider: { id: number; name: string }; baseSymbol: string;
  onClose: () => void; onDone: (linked: number) => void;
}) {
  const [data, setData] = useState<{ suggestions: Suggestion[]; unmatched: Unmatched[]; note?: string } | null>(null);
  const [err, setErr] = useState("");
  const [picked, setPicked] = useState<Set<number>>(new Set());
  const [busy, setBusy] = useState(false);
  const [showUnmatched, setShowUnmatched] = useState(false);

  useEffect(() => {
    api.post("/catalog/auto-link/suggest/", { provider: provider.id })
      .then((r) => {
        setData(r.data);
        setPicked(new Set((r.data.suggestions as Suggestion[])
          .filter((s) => s.confidence !== "medium").map((s) => s.product)));
      })
      .catch((e) => setErr(e?.response?.data?.detail || "تعذّر جلب كتالوج المزوّد"));
  }, [provider.id]);

  const groups = useMemo(() => {
    const m = new Map<string, Suggestion[]>();
    for (const s of data?.suggestions || []) {
      if (!m.has(s.game_name)) m.set(s.game_name, []);
      m.get(s.game_name)!.push(s);
    }
    return [...m.entries()];
  }, [data]);

  const counts = useMemo(() => {
    const s = data?.suggestions || [];
    return {
      exact: s.filter((x) => x.confidence === "exact").length,
      high: s.filter((x) => x.confidence === "high").length,
      medium: s.filter((x) => x.confidence === "medium").length,
    };
  }, [data]);

  function toggle(id: number) {
    setPicked((s) => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n; });
  }
  function pickLevel(level: "all" | "none" | "sure") {
    const s = data?.suggestions || [];
    setPicked(new Set(level === "none" ? [] : s.filter((x) => level === "all" || x.confidence !== "medium").map((x) => x.product)));
  }

  async function apply() {
    const picks = (data?.suggestions || []).filter((s) => picked.has(s.product)).map((s) => ({
      product: s.product, package_id: s.package.id, kupur: s.package.kupur,
      name: s.package.name, price: s.package.price,
    }));
    if (!picks.length) return;
    setBusy(true);
    try {
      const r = await api.post("/catalog/auto-link/apply/", { provider: provider.id, picks });
      onDone(r.data.linked);
    } catch (e: any) {
      setErr(e?.response?.data?.detail || "تعذّر الحفظ");
      setBusy(false);
    }
  }


  return (
    <div style={overlay} onClick={onClose}>
      <div style={modal} onClick={(e) => e.stopPropagation()}>
        <div style={head}>
          <div>
            <b style={{ fontSize: 16 }}>🔗 ربط تلقائي — {provider.name}</b>
            <div style={{ fontSize: 12, opacity: .85 }}>معاينة: لا يُحفظ شيءٌ قبل «اربط المحدَّد»، ولا يُمسّ ربطٌ موجود</div>
          </div>
          <button onClick={onClose} style={xBtn}>✕</button>
        </div>

        <div style={{ padding: 16, overflowY: "auto", flex: 1 }}>
          {err ? <div style={errBox}>{err}</div> : !data ? (
            <div style={{ padding: 40, textAlign: "center", color: "var(--muted)" }}>⏳ جارٍ جلب كتالوج {provider.name} ومطابقته...</div>
          ) : (
            <>
              <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center", marginBottom: 12 }}>
                {(["exact", "high", "medium"] as const).map((k) => counts[k] > 0 && (
                  <span key={k} title={CONF[k].hint} style={{ ...badge, background: CONF[k].bg, color: CONF[k].fg }}>
                    {CONF[k].label}: {counts[k]}
                  </span>
                ))}
                {data.unmatched.length > 0 && (
                  <button type="button" onClick={() => setShowUnmatched((v) => !v)}
                    style={{ ...badge, background: "#fee2e2", color: "#991b1b", border: 0, cursor: "pointer" }}>
                    بلا مطابقة: {data.unmatched.length} {showUnmatched ? "▲" : "▼"}
                  </button>
                )}
                <span style={{ marginInlineStart: "auto", display: "flex", gap: 6 }}>
                  <button type="button" style={miniBtn} onClick={() => pickLevel("sure")}>المؤكَّد فقط</button>
                  <button type="button" style={miniBtn} onClick={() => pickLevel("all")}>الكل</button>
                  <button type="button" style={miniBtn} onClick={() => pickLevel("none")}>لا شيء</button>
                </span>
              </div>
              {data.note && <div style={{ ...warnBox, marginBottom: 10 }}>{data.note}</div>}

              {showUnmatched && (
                <div style={{ ...warnBox, background: "#fef2f2", borderColor: "#fecaca", color: "#7f1d1d", marginBottom: 12 }}>
                  {data.unmatched.map((u) => (
                    <div key={u.product}>• {u.game_name} — {u.product_name}: <span style={{ opacity: .75 }}>{u.why}</span></div>
                  ))}
                  <div style={{ marginTop: 6, opacity: .8 }}>اربطها بيدك من الجدول.</div>
                </div>
              )}

              {groups.length === 0 ? (
                <div style={{ padding: 30, textAlign: "center", color: "var(--muted)" }}>
                  لا اقتراحات — كل الباقات مربوطة بهذا المزوّد، أو لا مطابقة لها في كتالوجه.
                </div>
              ) : (
                <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
                  <thead>
                    <tr style={{ background: "#f1f5f9", color: "#475569" }}>
                      <th style={th}></th>
                      <th style={{ ...th, textAlign: "right" }}>باقتك</th>
                      <th style={{ ...th, textAlign: "right" }}>← لدى {provider.name}</th>
                      <th style={th}>سعره ({baseSymbol})</th>
                      <th style={th}>المرجع</th>
                      <th style={{ ...th, textAlign: "right" }}>الثقة</th>
                    </tr>
                  </thead>
                  <tbody>
                    {groups.map(([game, rows]) => (
                      <Fragment key={game}>
                        <tr><td colSpan={6} style={gameRow}>{game}</td></tr>
                        {rows.map((s) => (
                          <tr key={s.product} onClick={() => toggle(s.product)}
                            style={{ borderTop: "1px solid #eef1f2", cursor: "pointer",
                                     background: picked.has(s.product) ? "#f0fdf4" : undefined }}>
                            <td style={td}><input type="checkbox" checked={picked.has(s.product)} onChange={() => toggle(s.product)}
                              onClick={(e) => e.stopPropagation()} /></td>
                            <td style={{ ...td, textAlign: "right", fontWeight: 700 }}>{s.product_name}</td>
                            <td style={{ ...td, textAlign: "right" }}>
                              {s.package.name}
                              <div style={{ fontSize: 11, color: "var(--muted)" }}>
                                {s.package.game} · <code dir="ltr">{s.package.id}{s.package.kupur ? `/${s.package.kupur}` : ""}</code>
                              </div>
                            </td>
                            <td style={{ ...td, direction: "ltr" }}>{s.price_base == null ? "—" : showPrice(s.price_base, s)}</td>
                            <td style={{ ...td, direction: "ltr", color: "var(--muted)" }}>{s.ref_price == null ? "—" : showPrice(s.ref_price, s)}</td>
                            <td style={{ ...td, textAlign: "right" }}>
                              <span style={{ ...badge, background: CONF[s.confidence].bg, color: CONF[s.confidence].fg }}>
                                {CONF[s.confidence].label}
                              </span>
                              <div style={{ fontSize: 11, color: "#15803d", marginTop: 3 }}>{s.reasons.join(" · ")}</div>
                              {!!s.warnings?.length && (
                                <div style={{ fontSize: 11, color: "#b45309" }}>⚠ {s.warnings.join(" · ")}</div>
                              )}
                            </td>
                          </tr>
                        ))}
                      </Fragment>
                    ))}
                  </tbody>
                </table>
              )}
            </>
          )}
        </div>

        <div style={foot}>
          <span style={{ fontSize: 13, color: "var(--muted)" }}>
            محدَّد {picked.size} من {data?.suggestions.length || 0}
          </span>
          <button className="btn" style={{ background: "#8a999e", marginInlineStart: "auto" }} onClick={onClose}>إلغاء</button>
          <button className="btn g" disabled={!picked.size || busy} onClick={apply}>
            {busy ? "جارٍ الربط..." : `🔗 اربط المحدَّد (${picked.size})`}
          </button>
        </div>
      </div>
    </div>
  );
}

const overlay: React.CSSProperties = { position: "fixed", inset: 0, background: "rgba(0,0,0,.45)", zIndex: 1000, display: "flex", alignItems: "center", justifyContent: "center" };
const modal: React.CSSProperties = { width: "min(1000px, 94vw)", maxHeight: "88vh", background: "#fff", borderRadius: 12, overflow: "hidden", display: "flex", flexDirection: "column", boxShadow: "0 20px 60px rgba(0,0,0,.3)" };
const head: React.CSSProperties = { background: "var(--primary)", color: "#fff", padding: "12px 16px", display: "flex", alignItems: "center", gap: 10 };
const xBtn: React.CSSProperties = { marginInlineStart: "auto", background: "transparent", border: 0, color: "#fff", fontSize: 18, cursor: "pointer" };
const foot: React.CSSProperties = { borderTop: "1px solid var(--border)", padding: "10px 16px", display: "flex", gap: 10, alignItems: "center" };
const th: React.CSSProperties = { padding: "8px 6px", fontWeight: 700, fontSize: 12 };
const td: React.CSSProperties = { padding: "8px 6px", textAlign: "center", verticalAlign: "top" };
const gameRow: React.CSSProperties = { background: "#f5c518", color: "#3a2f00", fontWeight: 800, padding: "6px 10px", textAlign: "right" };
const badge: React.CSSProperties = { display: "inline-block", fontSize: 11.5, fontWeight: 700, padding: "2px 9px", borderRadius: 999, whiteSpace: "nowrap" };
const miniBtn: React.CSSProperties = { fontSize: 12, padding: "4px 10px", borderRadius: 6, border: "1px solid var(--border)", background: "#fff", cursor: "pointer" };
const errBox: React.CSSProperties = { background: "#fdecea", border: "1px solid #f5c6c2", color: "#b0463a", padding: "10px 12px", borderRadius: 6 };
const warnBox: React.CSSProperties = { background: "#fffbeb", border: "1px solid #fde68a", color: "#92400e", padding: "8px 12px", borderRadius: 6, fontSize: 12.5, lineHeight: 1.9 };
