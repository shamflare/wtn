import { useEffect, useState } from "react";
import { api } from "../api";
import { symbolOf } from "../currency";

/**
 * عناصر مشتركة لصفحات «موبايل» (شحن الخطوط) — بنفس لغة تصميم الألعاب:
 * `card` و`toolbar` و`segment` و`table.grid` من theme.css، ونوافذ بالهيكل ذاته.
 */

/** الشركات بترتيب العرض، ولكلٍّ لون علامتها — يميّزها بنظرة في كل الجداول. */
export const OPERATORS = [
  { code: "Turkcell", label: "Turkcell", color: "#f5b800", ink: "#253a7b" },
  { code: "Vodafone", label: "Vodafone", color: "#e60000", ink: "#fff" },
  { code: "Avea", label: "Türk Telekom", color: "#0b4ea2", ink: "#fff" },
  { code: "Callback", label: "دولي", color: "#6b7280", ink: "#fff" },
] as const;

export const opOf = (code: string) => OPERATORS.find((o) => o.code === code) ?? OPERATORS[3];

/** شارة الشركة: دائرة بلونها وحرفها الأول — تُغني عن شعار غير موجود. */
export function OpBadge({ code, size = 22 }: { code: string; size?: number }) {
  const o = opOf(code);
  return (
    <span title={o.label} style={{
      width: size, height: size, borderRadius: "50%", background: o.color, color: o.ink,
      display: "inline-flex", alignItems: "center", justifyContent: "center",
      fontSize: size * 0.48, fontWeight: 900, flex: "none", lineHeight: 1,
      boxShadow: "inset 0 -3px 6px rgba(0,0,0,.18)",
    }}>{o.code === "Callback" ? "🌐" : o.label[0]}</span>
  );
}

/** تبويبات الشركات (segment) مع عدد اختياري بجانب كل شركة. */
export function OperatorTabs({ value, onChange, counts }: {
  value: string; onChange: (code: string) => void; counts?: Record<string, number>;
}) {
  return (
    <div className="segment">
      {OPERATORS.map((o) => (
        <button key={o.code} type="button" className={value === o.code ? "active" : ""}
          onClick={() => onChange(o.code)}
          style={{ display: "inline-flex", alignItems: "center", gap: 7 }}>
          <OpBadge code={o.code} size={18} />
          {o.label}
          {counts && <span style={{ color: "var(--faint)", fontSize: 11.5 }}>{counts[o.code] ?? 0}</span>}
        </button>
      ))}
    </div>
  );
}

/** مفتاح تشغيل/إيقاف صغير. */
export function Switch({ on, onChange, title }: { on: boolean; onChange: (v: boolean) => void; title?: string }) {
  return (
    <button type="button" title={title} onClick={() => onChange(!on)} style={{
      width: 38, height: 21, borderRadius: 999, border: 0, padding: 2, cursor: "pointer",
      background: on ? "var(--ok)" : "#c5cfd1", transition: ".15s", display: "inline-flex",
      justifyContent: on ? "flex-end" : "flex-start", verticalAlign: "middle",
    }}>
      <span style={{ width: 17, height: 17, borderRadius: "50%", background: "#fff",
        boxShadow: "0 1px 3px rgba(0,0,0,.25)" }} />
    </button>
  );
}

/** هيكل نافذة مشترك: غطاء + رأس + جسم + ذيل (كنوافذ مجموعات أسعار الألعاب). */
export function Modal({ title, onClose, children, footer, width = 470 }: {
  title: string; onClose: () => void; children: React.ReactNode; footer: React.ReactNode; width?: number;
}) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);
  return (
    <div style={overlay} onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div style={{ ...box, width }}>
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

export function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <div style={{ marginBottom: 14 }}>
      <label style={{ display: "block", fontSize: 12.5, fontWeight: 700, marginBottom: 5 }}>{label}</label>
      {children}
      {hint && <div style={{ fontSize: 11.5, color: "var(--muted)", marginTop: 4, lineHeight: 1.6 }}>{hint}</div>}
    </div>
  );
}

/**
 * عملة دفتر المتجر وسعر صرف الليرة — كلفة ZNET تصل بالليرة وتُحوَّل بهذا السعر،
 * وكل الأسعار في صفحات الموبايل بعملة الدفتر.
 */
export function useLedger() {
  const [l, setL] = useState<{ base: string; sym: string; tryRate: number | null }>({ base: "", sym: "", tryRate: null });
  useEffect(() => {
    api.get("/settings/exchange/").then((r) => {
      const base = r.data.base_currency || "USD";
      const rate = base === "TRY" ? 1 : Number(r.data.exchange_rates?.TRY || 0);
      setL({ base, sym: symbolOf(base), tryRate: rate > 0 ? rate : 0 });
    }).catch(() => {});
  }, []);
  return l;
}

/** شريط يشرح عملة الأسعار ومصدر التحويل — ويحذّر بالأحمر إن غاب سعر صرف الليرة. */
export function LedgerNote({ ledger }: { ledger: ReturnType<typeof useLedger> }) {
  if (!ledger.base) return null;
  if (ledger.base === "TRY") {
    return <div style={note}>💱 كل الأسعار هنا <b>بالليرة التركية</b> — عملة دفتر متجرك وعملة ZNET معاً، فلا تحويل.</div>;
  }
  if (!ledger.tryRate) {
    return (
      <div style={{ ...note, background: "#fdf3f3", borderColor: "#f0caca", color: "#8a3535" }}>
        ⚠️ <b>لا سعر صرف للّيرة.</b> كلفة ZNET بالليرة ودفتر متجرك بـ{ledger.base} — اضبط سعر TRY في
        «الوكلاء ⟵ أسعار الصرف» ثم أعد الاستيراد. حتى ذلك الحين البيع موقوف تلقائياً حمايةً من الخطأ.
      </div>
    );
  }
  return (
    <div style={note}>
      💱 كل الأسعار هنا بعملة متجرك <b>{ledger.base} ({ledger.sym})</b>. كلفة ZNET تصل بالليرة (تظهر صغيرة تحت
      الكلفة) وتُحوَّل بسعر <b className="num">1{ledger.sym} = {ledger.tryRate} ₺</b> من «أسعار الصرف» —
      وتغيير هذا السعر يعيد حساب الكلف والأسعار المرتبطة بها تلقائياً.
    </div>
  );
}

/** رسالة عائمة أسفل الشاشة تختفي وحدها. */
export function Toast({ text }: { text: string }) {
  if (!text) return null;
  return <div style={toastBox}>{text}</div>;
}

export const money = (v: string | number) =>
  Number(v || 0).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

/* ── أنماط مشتركة ── */
export const pageWrap: React.CSSProperties = { maxWidth: 1340, margin: "0 auto", padding: "18px 16px 40px" };
export const pageTitle: React.CSSProperties = {
  display: "flex", alignItems: "center", gap: 10, fontSize: 20, fontWeight: 800,
  color: "var(--primary-dark)", margin: "0 0 14px",
};
export const input: React.CSSProperties = {
  width: "100%", height: 34, padding: "0 10px", borderRadius: 6,
  border: "1px solid var(--border)", background: "var(--surface)", font: "inherit", fontSize: 13.5,
};
export const note: React.CSSProperties = {
  background: "var(--surface-2)", border: "1px solid var(--border)", color: "var(--muted)",
  fontSize: 13, padding: "9px 14px", borderRadius: 8, marginBottom: 14, lineHeight: 1.7,
};
export const preview: React.CSSProperties = {
  background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: 6,
  padding: "9px 12px", fontSize: 12.5, lineHeight: 1.7, color: "var(--muted)",
};
/** صفّ عنوان الفئة داخل الجدول — نفس شريط الألعاب الأصفر في مجموعات الأسعار. */
export const groupHead: React.CSSProperties = {
  background: "#f5c518", color: "#4a3c00", fontWeight: 700,
  padding: "7px 14px", textAlign: "start", fontSize: 14,
};
export const errText: React.CSSProperties = { color: "var(--danger)", fontSize: 12.5 };
export const ib: React.CSSProperties = { marginInlineEnd: 5 };
export const empty: React.CSSProperties = { padding: 36, textAlign: "center", color: "var(--muted)" };

const overlay: React.CSSProperties = {
  position: "fixed", inset: 0, background: "rgba(0,0,0,.45)", zIndex: 80,
  display: "flex", alignItems: "center", justifyContent: "center",
};
const box: React.CSSProperties = {
  background: "var(--surface)", borderRadius: 10, maxWidth: "95vw",
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
const toastBox: React.CSSProperties = {
  position: "fixed", insetInlineStart: 18, bottom: 18, zIndex: 90, maxWidth: 460,
  background: "#123", color: "#fff", padding: "11px 16px", borderRadius: 8,
  fontSize: 13, lineHeight: 1.7, boxShadow: "0 8px 26px rgba(0,0,0,.3)",
};
