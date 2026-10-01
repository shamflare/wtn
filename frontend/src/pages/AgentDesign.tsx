import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api";
import Icon from "../components/Icon";
import {
  AGENT_THEME_DEFAULTS, AGENT_THEME_GROUPS, AGENT_THEME_PRESETS,
  agentThemeVars, cleanAgentTheme, type AgentTheme, type AgentThemeKey,
} from "../agentTheme";
import "./store.css";

/* ═══════════════════════════════════════════════════════════════════════
   الإعدادات ← تصميم واجهة الوكلاء.

   صاحب المتجر يضبط كل لونٍ تراه وكلاؤه في لوحتهم (/store) على حدة، ويرى
   أثره فوراً في هاتفٍ مصغّر بجانبه. المعاينة ليست رسماً تقريبياً: هي أصناف
   store.css نفسها بالمتغيّرات نفسها، فما يُرى هنا هو ما سيراه الوكيل.
   ═══════════════════════════════════════════════════════════════════════ */

type Screen = "home" | "orders" | "wallet";

export default function AgentDesign() {
  const [theme, setTheme] = useState<AgentTheme | null>(null);
  const saved = useRef<string>("{}");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [screen, setScreen] = useState<Screen>("home");

  useEffect(() => {
    api.get("/settings/agent-theme/").then((r) => {
      const t = cleanAgentTheme(r.data.theme || {});
      saved.current = JSON.stringify(t);
      setTheme(t);
    }).catch(() => setTheme({}));
  }, []);

  const vars = useMemo(() => agentThemeVars(theme || {}), [theme]);
  if (!theme) return <div style={{ padding: 30 }}>جارٍ التحميل...</div>;

  const dirty = JSON.stringify(cleanAgentTheme(theme)) !== saved.current;
  const val = (k: AgentThemeKey) => theme[k] || AGENT_THEME_DEFAULTS[k];

  function set(k: AgentThemeKey, v: string) {
    setMsg(null);
    setTheme((t) => ({ ...(t || {}), [k]: v }));
  }
  function unset(k: AgentThemeKey) {
    setMsg(null);
    setTheme((t) => { const n = { ...(t || {}) }; delete n[k]; return n; });
  }

  async function save(next: AgentTheme = theme!) {
    setBusy(true);
    setMsg(null);
    const clean = cleanAgentTheme(next);
    try {
      await api.put("/settings/agent-theme/", { theme: clean });
      saved.current = JSON.stringify(clean);
      setTheme(clean);
      setMsg({ ok: true, text: "حُفظ ✓ — يراه وكلاؤك عند فتح لوحتهم أو تحديثها" });
    } catch (e: any) {
      setMsg({ ok: false, text: e?.response?.data?.detail || "تعذّر الحفظ" });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div style={{ padding: 16 }}>
      <h2 style={{ fontSize: 20, color: "var(--primary-dark)", marginBottom: 4 }}>تصميم واجهة الوكلاء</h2>
      <div style={{ color: "var(--muted)", fontSize: 13.5, marginBottom: 16 }}>
        ألوان لوحة الوكيل على الجوال — كل لونٍ على حدة. التغيير يظهر في المعاينة فوراً،
        ولا يصل إلى وكلائك إلا بعد الحفظ.
      </div>

      <div style={{ display: "flex", gap: 20, alignItems: "flex-start" }}>
        {/* ── المحرّر ── */}
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={panel}>
            <div style={panelHead}>ثيمات جاهزة</div>
            <div style={{ padding: 14, display: "grid", gridTemplateColumns: "repeat(5, 1fr)", gap: 10 }}>
              {AGENT_THEME_PRESETS.map((p) => {
                const c = { ...AGENT_THEME_DEFAULTS, ...p.theme };
                const on = JSON.stringify(cleanAgentTheme(p.theme)) === JSON.stringify(cleanAgentTheme(theme));
                return (
                  <button key={p.name} type="button" onClick={() => { setMsg(null); setTheme({ ...p.theme }); }}
                    style={{ ...presetCard, borderColor: on ? "var(--primary)" : "var(--border)",
                             boxShadow: on ? "0 0 0 2px var(--primary)" : "none" }}>
                    <div style={{ height: 46, borderRadius: 8, background: c.bg, padding: 6,
                                  display: "flex", gap: 4, alignItems: "flex-end" }}>
                      <span style={{ flex: 2, height: 22, borderRadius: 5, background: c.surface }} />
                      <span style={{ flex: 1, height: 22, borderRadius: 5, background: c.primary }} />
                      <span style={{ flex: 1, height: 22, borderRadius: 5, background: c.gold }} />
                    </div>
                    <div style={{ fontSize: 12.5, fontWeight: 700, marginTop: 6 }}>{p.name}</div>
                  </button>
                );
              })}
            </div>
            <div style={{ padding: "0 14px 12px", fontSize: 12, color: "var(--muted)" }}>
              الثيم الجاهز نقطة بداية — عدّل بعده أي لونٍ تريده من القوائم أدناه.
            </div>
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14, marginTop: 14 }}>
            {AGENT_THEME_GROUPS.map((g) => (
              <div key={g.title} style={panel}>
                <div style={panelHead}>{g.title}</div>
                <div style={{ padding: "6px 14px 10px" }}>
                  {g.fields.map((f) => {
                    const changed = !!theme[f.key] && theme[f.key] !== AGENT_THEME_DEFAULTS[f.key];
                    return (
                      <div key={f.key} style={row}>
                        <label style={{ ...swatch, background: val(f.key) }} title="اختر اللون">
                          <input type="color" value={val(f.key)}
                            onInput={(e) => set(f.key, e.currentTarget.value)}
                            onChange={(e) => set(f.key, e.currentTarget.value)}
                            style={hiddenColor} />
                        </label>
                        <div style={{ flex: 1, minWidth: 0 }}>
                          <div style={{ fontSize: 13.5, fontWeight: 700 }}>{f.label}</div>
                          {f.hint && <div style={{ fontSize: 11.5, color: "var(--muted)" }}>{f.hint}</div>}
                        </div>
                        <HexInput value={val(f.key)} onChange={(v) => set(f.key, v)} />
                        <button type="button" title="إرجاع للافتراضي" onClick={() => unset(f.key)}
                          style={{ ...resetBtn, visibility: changed ? "visible" : "hidden" }}>
                          <Icon name="refresh" size={14} />
                        </button>
                      </div>
                    );
                  })}
                </div>
              </div>
            ))}
          </div>

          <div style={{ ...panel, marginTop: 14, padding: 14, display: "flex", alignItems: "center", gap: 12,
                        position: "sticky", bottom: 10, boxShadow: "0 6px 24px rgba(0,0,0,.12)" }}>
            <button className="btn g" onClick={() => save()} disabled={busy || !dirty}>
              {busy ? "جارٍ الحفظ..." : "حفظ التصميم"}
            </button>
            <button className="btn" style={{ background: "#8a999e" }} disabled={busy}
              onClick={() => { if (confirm("إرجاع كل الألوان إلى التصميم الافتراضي؟")) save({}); }}>
              ↺ التصميم الافتراضي
            </button>
            {dirty && !msg && <span style={{ color: "var(--warn, #b7791f)", fontSize: 13 }}>● تغييرات لم تُحفظ</span>}
            {msg && <span style={{ color: msg.ok ? "var(--ok)" : "var(--danger)", fontSize: 13.5 }}>{msg.text}</span>}
          </div>
        </div>

        {/* ── المعاينة ── */}
        <div style={{ width: 380, flexShrink: 0, position: "sticky", top: 12 }}>
          <div style={{ display: "flex", gap: 6, marginBottom: 10, justifyContent: "center" }}>
            {([["home", "الرئيسية"], ["orders", "الطلبات"], ["wallet", "المحفظة"]] as [Screen, string][]).map(([k, l]) => (
              <button key={k} type="button" onClick={() => setScreen(k)} style={{
                height: 30, padding: "0 14px", borderRadius: 999, fontSize: 13, cursor: "pointer",
                border: `1px solid ${screen === k ? "var(--primary)" : "var(--border-strong)"}`,
                background: screen === k ? "var(--primary)" : "#fff", color: screen === k ? "#fff" : "var(--text)",
              }}>{l}</button>
            ))}
          </div>
          <div style={phone}>
            <div className="ag ag-preview" dir="rtl"
              style={{ ...(vars as React.CSSProperties), colorScheme: vars["--scheme"] as any }}>
              <Preview screen={screen} />
            </div>
          </div>
          <div style={{ textAlign: "center", fontSize: 12, color: "var(--muted)", marginTop: 8 }}>
            معاينة حيّة — بيانات تجريبية
          </div>
        </div>
      </div>
    </div>
  );
}

/** حقل الكود السداسي: يُكتب حرّاً، ولا يُعتمد إلا حين يكتمل لوناً صالحاً. */
function HexInput({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const [draft, setDraft] = useState(value);
  useEffect(() => setDraft(value), [value]);
  return (
    <input dir="ltr" value={draft} maxLength={7} spellCheck={false}
      onChange={(e) => {
        let v = e.target.value.trim();
        if (v && !v.startsWith("#")) v = `#${v}`;
        setDraft(v);
        if (/^#[0-9a-fA-F]{6}$/.test(v)) onChange(v.toLowerCase());
      }}
      onBlur={() => setDraft(value)}
      style={{ width: 86, height: 30, fontFamily: "ui-monospace, Consolas, monospace", fontSize: 12.5,
               textAlign: "center", padding: "0 6px" }} />
  );
}

/* ── شاشات المعاينة: أصناف لوحة الوكيل نفسها ببياناتٍ ثابتة ── */

const GAMES = [
  { n: "PUBG MOBILE", h: 160 }, { n: "FREE FIRE", h: 230 }, { n: "YALLA LUDO", h: 45 },
  { n: "LIKEE", h: 320 }, { n: "JAWAKER", h: 270 }, { n: "AHLAN CHAT", h: 20 },
];
const ph = (h: number) => `linear-gradient(145deg, hsl(${h} 65% 42%), hsl(${(h + 40) % 360} 60% 22%))`;

function Preview({ screen }: { screen: Screen }) {
  return (
    <>
      <header className="ag-top">
        <div className="ag-top-in">
          <div className="ag-brand">
            <span className="ag-brand-mark">م</span>
            <span style={{ minWidth: 0 }}>
              <div className="ag-brand-name">متجري</div>
              <div className="ag-brand-sub">وكيل تجريبي</div>
            </span>
          </div>
          <span className="ag-balance"><span className="cur">$</span>125.50</span>
        </div>
      </header>

      <main className="ag-main">
        {screen === "home" && (
          <>
            <section className="ag-hero">
              <div className="ag-hero-hi">أهلاً أحمد 👋 — رصيدك الحالي</div>
              <div className="ag-hero-amt">125.50<span className="cur">$</span></div>
              <div className="ag-hero-sub">الحدّ الائتماني 500.00 $</div>
              <div className="ag-hero-actions">
                <span className="btn g"><Icon name="plusCircle" size={18} />شحن رصيد</span>
                <span className="btn ghost"><Icon name="receipt" size={18} />طلباتي</span>
              </div>
            </section>
            <div className="ag-stats">
              <div className="ag-stat ok"><div className="v">48</div><div className="l"><Icon name="check" size={13} />طلب ناجح</div></div>
              <div className="ag-stat"><div className="v" style={{ color: "var(--gold)" }}>36.20</div><div className="l"><Icon name="dollar" size={13} />أرباحي $</div></div>
              <div className="ag-stat warn"><div className="v">2</div><div className="l"><Icon name="clock" size={13} />قيد الانتظار</div></div>
            </div>
            <div className="ag-h2"><Icon name="games" size={19} style={{ color: "var(--primary)" }} />الألعاب والتطبيقات<span className="more">6 قسم</span></div>
            <div className="ag-search" style={{ marginBottom: 12 }}>
              <Icon name="search" size={19} style={{ position: "absolute", insetInlineStart: 15, top: "50%", transform: "translateY(-50%)", color: "var(--muted)" }} />
              <input placeholder="ابحث عن لعبة أو باقة..." readOnly />
            </div>
            <div className="ag-games">
              {GAMES.map((g) => (
                <div key={g.n} className="ag-game">
                  <span className="ag-game-ph" style={{ background: ph(g.h) }}>{g.n.charAt(0)}</span>
                  <div className="ag-game-name">{g.n}</div>
                  <div className="ag-game-foot"><span className="ag-buy-pill"><Icon name="cart" size={13} />شراء</span></div>
                </div>
              ))}
            </div>
            <div className="ag-h2"><Icon name="tag" size={18} style={{ color: "var(--gold)" }} />باقة</div>
            <div className="ag-pkg">
              <span className="ag-pkg-ico"><Icon name="bolt" size={20} /></span>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div className="ag-pkg-name">60 UC</div>
                <div className="ag-pkg-price">0.92<small>$</small></div>
              </div>
              <span className="btn">شراء</span>
            </div>
          </>
        )}

        {screen === "orders" && (
          <>
            <h1 className="ag-h1">طلباتي</h1>
            <div className="ag-chips" style={{ margin: "0 0 4px", padding: "2px 0 6px" }}>
              <span className="ag-chip on">الكل<span className="n">4</span></span>
              <span className="ag-chip"><span className="dot" style={{ background: "var(--ok)" }} />ناجح<span className="n">2</span></span>
              <span className="ag-chip"><span className="dot" style={{ background: "var(--warn)" }} />انتظار<span className="n">1</span></span>
            </div>
            <div className="ag-orders">
              {[
                { g: "PUBG MOBILE", p: "325 UC", st: "var(--ok)", l: "ناجح", h: 160, pin: true },
                { g: "FREE FIRE", p: "100 💎", st: "var(--warn)", l: "قيد الانتظار", h: 230 },
                { g: "LIKEE", p: "500 Diamonds", st: "var(--info)", l: "قيد التنفيذ", h: 320 },
                { g: "YALLA LUDO", p: "1000 Gold", st: "var(--danger)", l: "ملغى", h: 45 },
              ].map((o) => (
                <article key={o.g} className="ag-order" style={{ ["--st" as any]: o.st }}>
                  <div className="ag-order-top">
                    <span className="ag-thumb" style={{ background: ph(o.h) }}>{o.g.charAt(0)}</span>
                    <div className="ag-order-title"><b>{o.p}</b><span>{o.g}</span></div>
                    <div className="ag-order-amt"><b>4.60<small>$</small></b><span style={{ color: "var(--primary)" }}>+0.40 ربح</span></div>
                  </div>
                  {o.pin && (
                    <div className="ag-pin"><code>8F3K-22QX-91LA</code><span className="ag-copy"><Icon name="copy" size={13} />نسخ</span></div>
                  )}
                  <div className="ag-order-foot">
                    <span className="ag-status">{o.l}</span>
                    <span className="ag-when">2026-10-01 14:32</span>
                  </div>
                </article>
              ))}
            </div>
          </>
        )}

        {screen === "wallet" && (
          <>
            <h1 className="ag-h1">محفظتي</h1>
            <div className="ag-tiles">
              {[
                ["t-green", "wallet", "125.50", "الرصيد"], ["t-blue", "chart", "48", "الطلبات"],
                ["t-violet", "dollar", "412.00", "المبيعات"], ["t-coral", "arrowUp", "375.80", "المشتريات"],
                ["t-gold", "tag", "36.20", "الأرباح"],
              ].map(([c, i, v, l]) => (
                <div key={c} className={`ag-tile ${c}`}>
                  <span className="ic"><Icon name={i} size={18} /></span>
                  <div><div className="v">{v}<small>$</small></div><div className="l">{l}</div></div>
                </div>
              ))}
            </div>
            <div className="ag-h2"><Icon name="receipt" size={18} style={{ color: "var(--primary)" }} />كشف الحركات</div>
            <div className="ag-list">
              {[[true, "إيداع", "+50.00"], [false, "شراء PUBG 325 UC", "-4.60"]].map(([inflow, t, a]) => {
                const tone = inflow ? "var(--ok)" : "var(--danger)";
                return (
                  <div key={String(t)} className="ag-row">
                    <span className="ag-row-ico" style={{ background: `color-mix(in srgb, ${tone} 10%, transparent)`, color: tone }}>
                      <Icon name={inflow ? "arrowDown" : "arrowUp"} size={19} />
                    </span>
                    <div className="ag-row-main"><b>{t}</b><span>2026-10-01</span></div>
                    <div className="ag-row-end"><b style={{ color: tone }} dir="ltr">{a}</b></div>
                  </div>
                );
              })}
            </div>
            <div className="ag-msg err">مثال رسالة خطأ</div>
          </>
        )}
      </main>

      <nav className="ag-nav">
        <div className="ag-nav-in">
          {([["home", "الرئيسية"], ["search", "الألعاب"], ["receipt", "طلباتي"], ["bell", "الإشعارات"],
             ["wallet", "محفظتي"], ["grid", "المزيد"]] as [string, string][]).map(([i, l], idx) => {
            const on = (screen === "home" && idx === 0) || (screen === "orders" && idx === 2) || (screen === "wallet" && idx === 4);
            return (
              <span key={i} className={`ag-nav-item${on ? " on" : ""}`}>
                <span className="ag-nav-ico"><Icon name={i} size={20} /></span>
                <span>{l}</span>
                {i === "bell" && <span className="ag-badge">3</span>}
              </span>
            );
          })}
        </div>
      </nav>
    </>
  );
}

const panel: React.CSSProperties = {
  background: "#fff", border: "1px solid var(--border)", borderRadius: 8, overflow: "hidden",
};
const panelHead: React.CSSProperties = {
  background: "var(--primary)", color: "#fff", padding: "9px 14px", fontSize: 14.5, fontWeight: 700,
};
const presetCard: React.CSSProperties = {
  background: "#fff", border: "1px solid var(--border)", borderRadius: 10, padding: 7,
  cursor: "pointer", textAlign: "center", color: "var(--text)",
};
const row: React.CSSProperties = {
  display: "flex", alignItems: "center", gap: 10, padding: "8px 0", borderBottom: "1px solid var(--border)",
};
const swatch: React.CSSProperties = {
  width: 34, height: 34, borderRadius: 9, flexShrink: 0, cursor: "pointer", position: "relative",
  border: "1px solid rgba(0,0,0,.18)", boxShadow: "inset 0 0 0 2px rgba(255,255,255,.5)",
};
const hiddenColor: React.CSSProperties = {
  position: "absolute", inset: 0, opacity: 0, cursor: "pointer", width: "100%", height: "100%", border: 0, padding: 0,
};
const resetBtn: React.CSSProperties = {
  width: 28, height: 28, borderRadius: 7, border: "1px solid var(--border)", background: "#fff",
  color: "var(--muted)", cursor: "pointer", display: "grid", placeItems: "center", padding: 0, flexShrink: 0,
};
const phone: React.CSSProperties = {
  width: 380, height: 760, borderRadius: 38, padding: 10, background: "#111",
  boxShadow: "0 20px 60px rgba(0,0,0,.35), inset 0 0 0 2px #333",
};
