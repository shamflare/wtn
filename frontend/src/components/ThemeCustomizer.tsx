import { useState } from "react";
import { api } from "../api";
import { applyThemeConfig, THEME_DEFAULTS, type ThemeConfig } from "../theme";

interface Props {
  config: ThemeConfig;
  onChange: (cfg: ThemeConfig) => void;  // يُطبّق حياً + يحدّث حالة الأب
  onClose: () => void;
}

const PRIMARIES = [
  { c: "#3a6b73", s: "#2b545b" }, { c: "#2c5f9e", s: "#234c7e" },
  { c: "#c1692a", s: "#9c531f" }, { c: "#6d28d9", s: "#581c9e" },
  { c: "#0f766e", s: "#0b5a54" }, { c: "#b91c1c", s: "#8f1616" },
  { c: "#1f2937", s: "#111827" },
];
const TH_COLORS = [
  { c: "", ink: "", label: "افتراضي" },
  { c: "#3a6b73", ink: "#ffffff" }, { c: "#41565c", ink: "#ffffff" },
  { c: "#0f2b2e", ink: "#ffffff" }, { c: "#f5c518", ink: "#4a3c00" },
];
const ANNOUNCES = ["#3f8f86", "#2c5f9e", "#7c3aed", "#b23a48"];
const FONTS = [
  { label: "Cairo", v: '"Cairo", "Segoe UI", Tahoma, Arial, sans-serif' },
  { label: "Tajawal", v: '"Tajawal", "Segoe UI", Tahoma, Arial, sans-serif' },
  { label: "Segoe", v: '"Segoe UI", Tahoma, Arial, sans-serif' },
];

/** يشتقّ درجة أغمق من اللون (للـ hover والتبويب النشط). */
function darken(hex: string, f = 0.24): string {
  const n = hex.replace("#", "");
  if (n.length !== 6) return hex;
  const d = (i: number) => Math.max(0, Math.round(parseInt(n.slice(i, i + 2), 16) * (1 - f)))
    .toString(16).padStart(2, "0");
  return `#${d(0)}${d(2)}${d(4)}`;
}

/** أبيض أم داكن؟ حسب سطوع الخلفية (ليبقى نص رأس الجدول مقروءاً). */
function inkFor(hex: string): string {
  const n = hex.replace("#", "");
  if (n.length !== 6) return "#ffffff";
  const [r, g, b] = [0, 2, 4].map((i) => parseInt(n.slice(i, i + 2), 16));
  return 0.299 * r + 0.587 * g + 0.114 * b > 160 ? "#1e2b2d" : "#ffffff";
}

/** دائرة "لون مخصّص" — تفتح منتقي ألوان المتصفح الكامل وتبثّ أثناء السحب. */
function ColorPick({ value, selected, onPick }:
  { value: string; selected: boolean; onPick: (v: string) => void }) {
  return (
    <label title="لون مخصّص — اختر أي لون" style={{
      width: 34, height: 34, borderRadius: 9, cursor: "pointer", position: "relative",
      display: "inline-flex", alignItems: "center", justifyContent: "center",
      background: selected
        ? value
        : "conic-gradient(#f44,#fa0,#ff4,#4c4,#4cf,#44f,#c4f,#f44)",
      border: selected ? "2.5px solid var(--text)" : "2px solid var(--border)",
      color: "#fff", fontWeight: 800, fontSize: 15, textShadow: "0 1px 2px rgba(0,0,0,.5)",
    }}>
      +
      <input type="color" value={/^#[0-9a-fA-F]{6}$/.test(value) ? value : "#3a6b73"}
        onInput={(e) => onPick(e.currentTarget.value)}
        style={{ position: "absolute", inset: 0, opacity: 0, cursor: "pointer", width: "100%", height: "100%", border: 0, padding: 0 }} />
    </label>
  );
}

export default function ThemeCustomizer({ config, onChange, onClose }: Props) {
  const [saved, setSaved] = useState<null | "ok" | "err">(null);
  const [busy, setBusy] = useState(false);
  const c = { ...THEME_DEFAULTS, ...config };

  function set(patch: ThemeConfig) {
    const next = { ...config, ...patch };
    applyThemeConfig(next);
    onChange(next);
    setSaved(null);
  }

  async function save() {
    setBusy(true);
    try { await api.put("/settings/theme/", { config }); setSaved("ok"); onClose(); }
    catch { setSaved("err"); }
    finally { setBusy(false); }
  }

  async function reset() {
    set({ ...THEME_DEFAULTS });
    onChange({});
    applyThemeConfig({});
    setBusy(true);
    try { await api.put("/settings/theme/", { config: {} }); setSaved("ok"); }
    catch { setSaved("err"); }
    finally { setBusy(false); }
  }

  return (
    <>
      <div style={overlay} onClick={onClose} />
      <aside style={panel}>
        <div style={head}>
          <span style={{ fontSize: 18 }}>🎨</span>
          <div>
            <b style={{ fontSize: 15 }}>تخصيص المظهر</b>
            <div style={{ opacity: 0.85, fontSize: 11.5 }}>التغييرات تظهر مباشرةً — احفظ لتثبيتها لمتجرك</div>
          </div>
          <button onClick={onClose} style={xBtn}>✕</button>
        </div>

        <div style={body}>
          <Section title="الوضع العام">
            <SegRow
              options={[["light", "☀️ فاتح"], ["dark", "🌙 داكن"]]}
              value={c.mode}
              onPick={(v) => set({ mode: v as "light" | "dark" })}
            />
          </Section>

          <Section title="اللون الأساسي (الهيدر والأزرار)">
            <div style={swRow}>
              {PRIMARIES.map((p) => (
                <Swatch key={p.c} color={p.c} selected={c.primary === p.c}
                  onClick={() => set({ primary: p.c, primary_strong: p.s })} />
              ))}
              <ColorPick value={c.primary} selected={!PRIMARIES.some((p) => p.c === c.primary)}
                onPick={(v) => set({ primary: v, primary_strong: darken(v) })} />
            </div>
          </Section>

          <Section title="لون رأس الجداول">
            <div style={swRow}>
              {TH_COLORS.map((t, i) => (
                <Swatch key={i} color={t.c || "#f6f8f8"} label={t.label} selected={(c.th_bg || "") === t.c}
                  onClick={() => set({ th_bg: t.c, th_ink: t.ink })} />
              ))}
              <ColorPick value={c.th_bg || "#f6f8f8"} selected={!!c.th_bg && !TH_COLORS.some((t) => t.c === c.th_bg)}
                onPick={(v) => set({ th_bg: v, th_ink: inkFor(v) })} />
            </div>
          </Section>

          <Section title="لون شريط الإعلانات">
            <div style={swRow}>
              {ANNOUNCES.map((a) => (
                <Swatch key={a} color={a} selected={c.announce === a} onClick={() => set({ announce: a })} />
              ))}
              <ColorPick value={c.announce} selected={!ANNOUNCES.includes(c.announce)}
                onPick={(v) => set({ announce: v })} />
            </div>
          </Section>

          <Section title="شكل الأزرار">
            <div style={{ display: "flex", gap: 8 }}>
              {([["3px", "مربّع"], ["8px", "مدوّر"], ["999px", "حبّة"]] as [string, string][]).map(([r, label]) => (
                <button key={r} onClick={() => set({ btn_radius: r })}
                  style={{
                    flex: 1, height: 34, border: 0, background: "var(--primary)", color: "#fff",
                    fontSize: 12, cursor: "pointer", borderRadius: r === "999px" ? 999 : Number(r.replace("px", "")),
                    outline: c.btn_radius === r ? "2.5px solid var(--text)" : "none", outlineOffset: 2,
                  }}>{label}</button>
              ))}
            </div>
          </Section>

          <Section title={`استدارة البطاقات والجداول (${c.radius})`}>
            <input type="range" min={0} max={22} value={Number(c.radius)}
              onChange={(e) => set({ radius: e.target.value })}
              style={{ width: "100%", accentColor: "var(--primary)", height: 22, border: 0, padding: 0 }} />
          </Section>

          <Section title="الخط">
            <SegRow options={FONTS.map((f) => [f.v, f.label])} value={c.font} onPick={(v) => set({ font: v })} />
          </Section>

          <Section title="حجم الخط">
            <SegRow options={[["14px", "صغير"], ["16px", "متوسط"], ["17px", "كبير"]]} value={c.fs} onPick={(v) => set({ fs: v })} />
          </Section>

          <Section title="عناصر الواجهة">
            <Toggle label="شريط الإعلانات العلوي" on={c.show_announce} onClick={() => set({ show_announce: !c.show_announce })} />
            <Toggle label="الشريط العاجل المتحرّك" on={c.show_ticker} onClick={() => set({ show_ticker: !c.show_ticker })} />
            <Toggle label="فاصل الصفوف الأخضر" on={c.row_sep} onClick={() => set({ row_sep: !c.row_sep })} />
          </Section>
        </div>

        <div style={foot}>
          <button className="btn g" style={{ flex: 1, height: 38 }} onClick={save} disabled={busy}>
            {busy ? "جارٍ..." : "💾 حفظ التخصيص"}
          </button>
          <button className="btn" style={{ flex: 1, height: 38, background: "#8a999e" }} onClick={reset} disabled={busy}>
            ↺ الافتراضي
          </button>
        </div>
        {saved && (
          <div style={{ padding: "0 16px 12px", fontSize: 12.5, color: saved === "ok" ? "var(--ok)" : "var(--danger)" }}>
            {saved === "ok" ? "✓ حُفظ — سيظهر لكل من يفتح لوحة متجرك" : "تعذّر الحفظ (صاحب المتجر فقط)"}
          </div>
        )}
      </aside>
    </>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div style={{ marginBottom: 18 }}>
      <div style={secTitle}>{title}<span style={secLine} /></div>
      {children}
    </div>
  );
}

function Swatch({ color, selected, label, onClick }:
  { color: string; selected: boolean; label?: string; onClick: () => void }) {
  return (
    <span onClick={onClick} title={label || color} style={{
      width: 34, height: 34, borderRadius: 9, cursor: "pointer", background: color,
      border: selected ? "2.5px solid var(--text)" : "2px solid var(--border)",
      boxShadow: "inset 0 -6px 10px rgba(0,0,0,.15)", display: "inline-block",
    }} />
  );
}

function SegRow({ options, value, onPick }:
  { options: [string, string][]; value: string; onPick: (v: string) => void }) {
  return (
    <div style={{ display: "flex", background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: 10, padding: 3, gap: 2 }}>
      {options.map(([v, label]) => (
        <button key={v} onClick={() => onPick(v)} style={{
          flex: 1, border: 0, background: value === v ? "var(--surface)" : "transparent",
          color: value === v ? "var(--text)" : "var(--muted)", fontWeight: value === v ? 700 : 400,
          fontSize: 12.5, padding: "7px 4px", borderRadius: 7, cursor: "pointer",
          boxShadow: value === v ? "0 1px 2px rgba(0,0,0,.08)" : "none",
        }}>{label}</button>
      ))}
    </div>
  );
}

function Toggle({ label, on, onClick }: { label: string; on: boolean; onClick: () => void }) {
  return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "7px 0", fontSize: 13.5 }}>
      <span>{label}</span>
      <button onClick={onClick} style={{
        width: 40, height: 22, borderRadius: 999, border: 0, cursor: "pointer",
        background: on ? "var(--ok)" : "#c8d4d4", position: "relative", transition: ".15s", padding: 0,
      }}>
        <span style={{
          position: "absolute", top: 3, insetInlineStart: on ? 21 : 3,
          width: 16, height: 16, borderRadius: "50%", background: "#fff", transition: ".15s",
        }} />
      </button>
    </div>
  );
}

const overlay: React.CSSProperties = { position: "fixed", inset: 0, background: "rgba(10,25,25,.35)", zIndex: 90 };
const panel: React.CSSProperties = {
  position: "fixed", top: 0, bottom: 0, insetInlineStart: 0, width: 320, zIndex: 100,
  background: "var(--surface)", borderInlineEnd: "1px solid var(--border)",
  boxShadow: "0 0 40px rgba(0,0,0,.25)", display: "flex", flexDirection: "column",
};
const head: React.CSSProperties = {
  background: "var(--primary)", color: "#fff", padding: "14px 16px",
  display: "flex", alignItems: "center", gap: 9,
};
const xBtn: React.CSSProperties = { marginInlineStart: "auto", background: "transparent", border: 0, color: "#fff", fontSize: 17, cursor: "pointer" };
const body: React.CSSProperties = { flex: 1, overflowY: "auto", padding: "14px 16px" };
const foot: React.CSSProperties = { padding: "12px 16px", borderTop: "1px solid var(--border)", display: "flex", gap: 8 };
const secTitle: React.CSSProperties = {
  fontSize: 12, fontWeight: 800, color: "var(--muted)", letterSpacing: ".05em",
  marginBottom: 9, display: "flex", alignItems: "center", gap: 6,
};
const secLine: React.CSSProperties = { flex: 1, height: 1, background: "var(--border)" };
const swRow: React.CSSProperties = { display: "flex", gap: 8, flexWrap: "wrap" };
