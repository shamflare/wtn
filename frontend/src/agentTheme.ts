// ألوان واجهة الوكيل (لوحة /store) — يضبطها صاحب المتجر لونًا لونًا.
//
// كل مفتاح هنا يقابل متغيّر CSS على `.ag` في store.css، والقيم الافتراضية هي
// نفسها التي في الملف: متجرٌ لم يخصّص شيئاً يرى التصميم الأصلي حرفياً.
// المشتقّات (الظلال الشفّافة، تدرّجات البلاطات، لون التحديد...) تُحسب في CSS
// بـ color-mix من هذه الأساسيات، فلا يلزم صاحب المتجر أن يضبط خمسين لوناً.

export type AgentThemeKey =
  | "bg" | "surface" | "surface_2" | "surface_3" | "line"
  | "text" | "muted" | "faint"
  | "primary" | "on_primary" | "gold" | "on_gold"
  | "ok" | "warn" | "info" | "danger" | "violet" | "cyan"
  | "header_bg" | "nav_bg" | "nav_ink" | "nav_active"
  | "balance_bg" | "balance_ink" | "balance_cur"
  | "hero_from" | "hero_to" | "hero_glow" | "hero_glow_2" | "hero_ink";

export type AgentTheme = Partial<Record<AgentThemeKey, string>>;

export const AGENT_THEME_DEFAULTS: Record<AgentThemeKey, string> = {
  bg: "#07090e",
  surface: "#10141b",
  surface_2: "#161b24",
  surface_3: "#1d2330",
  line: "#ffffff",
  text: "#eef2f7",
  muted: "#8a94a7",
  faint: "#5c6579",
  primary: "#2fe27b",
  on_primary: "#04210f",
  gold: "#ffc23d",
  on_gold: "#2b1d00",
  ok: "#2fe27b",
  warn: "#ffb020",
  info: "#4da3ff",
  danger: "#ff5d6c",
  violet: "#b18cff",
  cyan: "#22d3ee",
  header_bg: "#07090e",
  nav_bg: "#0a0d13",
  nav_ink: "#8a94a7",
  nav_active: "#2fe27b",
  balance_bg: "#ffffff",
  balance_ink: "#0a7a3a",
  balance_cur: "#d99a00",
  hero_from: "#0f2a1d",
  hero_to: "#0b1020",
  hero_glow: "#5cf29c",
  hero_glow_2: "#4da3ff",
  hero_ink: "#ffffff",
};

const CSS_VAR: Record<AgentThemeKey, string> = {
  bg: "--bg", surface: "--surface", surface_2: "--surface-2", surface_3: "--surface-3",
  line: "--line", text: "--text", muted: "--muted", faint: "--faint",
  primary: "--primary", on_primary: "--on-primary", gold: "--gold", on_gold: "--on-gold",
  ok: "--ok", warn: "--warn", info: "--info", danger: "--danger", violet: "--violet", cyan: "--cyan",
  header_bg: "--header-bg", nav_bg: "--nav-bg", nav_ink: "--nav-ink", nav_active: "--nav-active",
  balance_bg: "--balance-bg", balance_ink: "--balance-ink", balance_cur: "--balance-cur",
  hero_from: "--hero-from", hero_to: "--hero-to", hero_glow: "--hero-glow",
  hero_glow_2: "--hero-glow-2", hero_ink: "--hero-ink",
};

export interface AgentThemeField { key: AgentThemeKey; label: string; hint?: string }
export interface AgentThemeGroup { title: string; fields: AgentThemeField[] }

/** ترتيب لوحة التخصيص — مجموعاتٌ بحسب ما يراه الوكيل لا بحسب أسماء المتغيّرات. */
export const AGENT_THEME_GROUPS: AgentThemeGroup[] = [
  {
    title: "الخلفيات والبطاقات",
    fields: [
      { key: "bg", label: "خلفية الصفحة" },
      { key: "surface", label: "البطاقات", hint: "بطاقات الألعاب والطلبات والقوائم" },
      { key: "surface_2", label: "الحقول والنوافذ", hint: "خانات الكتابة وأزرار القائمة" },
      { key: "surface_3", label: "الأزرار الثانوية والتحويم" },
      { key: "line", label: "الحدود والفواصل", hint: "يُستعمل شفّافاً — أبيض للداكن، أسود للفاتح" },
    ],
  },
  {
    title: "النصوص",
    fields: [
      { key: "text", label: "النص الأساسي" },
      { key: "muted", label: "النص الثانوي", hint: "العناوين الفرعية والتسميات" },
      { key: "faint", label: "النص الخافت", hint: "التواريخ والتلميحات" },
    ],
  },
  {
    title: "الألوان الرئيسية",
    fields: [
      { key: "primary", label: "اللون الأساسي", hint: "الأزرار الرئيسية والأسعار والتحديد" },
      { key: "on_primary", label: "نص فوق اللون الأساسي" },
      { key: "gold", label: "زرّ الشراء ورمز العملة" },
      { key: "on_gold", label: "نص فوق زرّ الشراء" },
    ],
  },
  {
    title: "الحالات والتنبيهات",
    fields: [
      { key: "ok", label: "ناجح / إيداع" },
      { key: "warn", label: "قيد الانتظار" },
      { key: "info", label: "قيد التنفيذ / معلومات" },
      { key: "danger", label: "مرفوض / خطأ / سحب" },
      { key: "violet", label: "لون مميّز ١", hint: "حسابي، بلاطة المبيعات" },
      { key: "cyan", label: "لون مميّز ٢", hint: "الربط الخارجي" },
    ],
  },
  {
    title: "الشريط العلوي والسفلي",
    fields: [
      { key: "header_bg", label: "خلفية الشريط العلوي" },
      { key: "nav_bg", label: "خلفية الشريط السفلي" },
      { key: "nav_ink", label: "أيقونات الشريط السفلي" },
      { key: "nav_active", label: "الأيقونة النشطة" },
      { key: "balance_bg", label: "خلفية زرّ الرصيد" },
      { key: "balance_ink", label: "رقم الرصيد" },
      { key: "balance_cur", label: "رمز العملة في الرصيد" },
    ],
  },
];

/** ثيماتٌ كاملة جاهزة — نقطة بداية يعدّلها صاحب المتجر لوناً لوناً. */
export const AGENT_THEME_PRESETS: { name: string; theme: AgentTheme }[] = [
  { name: "زمرّدي (الافتراضي)", theme: {} },
  {
    name: "ذهبي ليلي",
    theme: {
      bg: "#0b0a07", surface: "#16130c", surface_2: "#1e1a10", surface_3: "#28221a",
      primary: "#f5c518", on_primary: "#2a2000", gold: "#f5c518", on_gold: "#2a2000",
      header_bg: "#0b0a07", nav_bg: "#100e09", nav_active: "#f5c518", nav_ink: "#9a917c",
      muted: "#a39a85", faint: "#6b6453", text: "#f7f3e8",
      balance_ink: "#7a5c00", balance_cur: "#c99500",
      hero_from: "#2e2508", hero_to: "#120f08", hero_glow: "#f5c518", hero_glow_2: "#ff8a3d",
    },
  },
  {
    name: "أزرق ملكي",
    theme: {
      bg: "#060a14", surface: "#0e1424", surface_2: "#141c30", surface_3: "#1b2540",
      primary: "#4d8dff", on_primary: "#ffffff", gold: "#ffc23d",
      header_bg: "#060a14", nav_bg: "#090e1b", nav_active: "#4d8dff", nav_ink: "#8792ab",
      muted: "#8792ab", faint: "#58627a",
      balance_ink: "#1f4fbf",
      hero_from: "#0f1f45", hero_to: "#0a0f22", hero_glow: "#4d8dff", hero_glow_2: "#b18cff",
    },
  },
  {
    name: "بنفسجي",
    theme: {
      bg: "#0a0712", surface: "#141022", surface_2: "#1b152d", surface_3: "#241c3b",
      primary: "#a678ff", on_primary: "#ffffff", gold: "#ffc23d",
      header_bg: "#0a0712", nav_bg: "#0e0a18", nav_active: "#a678ff", nav_ink: "#958aab",
      muted: "#958aab", faint: "#625a75",
      balance_ink: "#6a3fd1",
      hero_from: "#2a1650", hero_to: "#0f0a1f", hero_glow: "#c49bff", hero_glow_2: "#ff7ab8",
    },
  },
  {
    name: "فاتح",
    theme: {
      bg: "#f3f5f8", surface: "#ffffff", surface_2: "#f0f2f6", surface_3: "#e5e9ef",
      line: "#000000", text: "#151a23", muted: "#5d6677", faint: "#97a0b0",
      primary: "#12a150", on_primary: "#ffffff", gold: "#f2b01e", on_gold: "#2b1d00",
      ok: "#12a150", warn: "#d98a00", info: "#2f7de1", danger: "#e0364a", violet: "#7b4fe0", cyan: "#0891b2",
      header_bg: "#ffffff", nav_bg: "#ffffff", nav_ink: "#6b7486", nav_active: "#12a150",
      balance_bg: "#12a150", balance_ink: "#ffffff", balance_cur: "#ffe08a",
      hero_from: "#13a85a", hero_to: "#0b6e8f", hero_glow: "#a8ffcf", hero_glow_2: "#7cc4ff", hero_ink: "#ffffff",
    },
  },
];

const HEX = /^#[0-9a-fA-F]{6}$/;

/** يُسقط ما ليس لوناً صالحاً أو ما يطابق الافتراضي — فيبقى المحفوظ ما غيّره فعلاً. */
export function cleanAgentTheme(t: AgentTheme): AgentTheme {
  const out: AgentTheme = {};
  for (const k of Object.keys(AGENT_THEME_DEFAULTS) as AgentThemeKey[]) {
    const v = t[k];
    if (v && HEX.test(v) && v.toLowerCase() !== AGENT_THEME_DEFAULTS[k]) out[k] = v.toLowerCase();
  }
  return out;
}

/** سطوع اللون (0..255) — لاختيار مخطّط ألوان المتصفّح (التقويم، شريط التمرير). */
export function luminance(hex: string): number {
  const n = hex.replace("#", "");
  if (n.length !== 6) return 0;
  const [r, g, b] = [0, 2, 4].map((i) => parseInt(n.slice(i, i + 2), 16));
  return 0.299 * r + 0.587 * g + 0.114 * b;
}

/** المتغيّرات الكاملة (الافتراضي + المخصّص) — للمعاينة كـ style مباشرة. */
export function agentThemeVars(t: AgentTheme): Record<string, string> {
  const c = { ...AGENT_THEME_DEFAULTS, ...cleanAgentTheme(t) };
  const vars: Record<string, string> = {};
  for (const k of Object.keys(CSS_VAR) as AgentThemeKey[]) vars[CSS_VAR[k]] = c[k];
  vars["--scheme"] = luminance(c.bg) > 140 ? "light" : "dark";
  return vars;
}

const STYLE_ID = "agent-theme";
const CACHE_KEY = "agent-theme";

/**
 * يطبّق الثيم على كل `.ag` في الصفحة (اللوحة ونوافذها المرسومة في body)
 * عبر وسم <style> واحد — المحدّد `.ag.ag` يغلب تعريف store.css.
 */
export function applyAgentTheme(t: AgentTheme) {
  const vars = agentThemeVars(t);
  let el = document.getElementById(STYLE_ID) as HTMLStyleElement | null;
  if (!el) {
    el = document.createElement("style");
    el.id = STYLE_ID;
    document.head.appendChild(el);
  }
  el.textContent = `.ag.ag{${Object.entries(vars).map(([k, v]) => `${k}:${v}`).join(";")};color-scheme:${vars["--scheme"]}}`;
  try { localStorage.setItem(CACHE_KEY, JSON.stringify(cleanAgentTheme(t))); } catch { /* تخزينٌ معطّل */ }
  return vars;
}

/** آخر ثيمٍ رآه هذا المتصفّح — يُطبَّق فوراً فلا يومض التصميم الافتراضي قبل وصول الخادم. */
export function cachedAgentTheme(): AgentTheme {
  try { return JSON.parse(localStorage.getItem(CACHE_KEY) || "{}") || {}; } catch { return {}; }
}

export function removeAgentTheme() {
  document.getElementById(STYLE_ID)?.remove();
}
