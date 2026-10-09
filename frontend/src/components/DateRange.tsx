/**
 * فلتر الفترة الموحّد لكل قوائم الطلبات والتقارير — **يبدأ باليوم** دائماً.
 *
 * قرار المالك: صفحة تفتح على تاريخ المتجر كلّه تُقرأ أرقامها على أنها أرقام
 * اليوم، فتضلّل. فكل صفحة طلبات أو تقارير أو أرباح تفتح على «اليوم»، ومن أراد
 * يوماً آخر أو فترة اختارها هنا.
 */

export type Range = "today" | "yesterday" | "week" | "month" | "all" | "custom";
export interface Dates { date_from: string; date_to: string }

/** تاريخ محلّي بصيغة YYYY-MM-DD. لا toISOString: يعطي تاريخ UTC فيقفز اليوم قرب منتصف الليل. */
export const ymd = (d: Date) =>
  `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;

/** حدود الفترة الجاهزة. الأسبوع يبدأ الاثنين. */
export function rangeDates(r: Range): Dates {
  const now = new Date();
  const today = ymd(now);
  if (r === "today") return { date_from: today, date_to: today };
  if (r === "yesterday") {
    const y = new Date(now);
    y.setDate(y.getDate() - 1);
    return { date_from: ymd(y), date_to: ymd(y) };
  }
  if (r === "week") {
    const start = new Date(now);
    start.setDate(start.getDate() - ((start.getDay() + 6) % 7));
    return { date_from: ymd(start), date_to: today };
  }
  if (r === "month") return { date_from: ymd(new Date(now.getFullYear(), now.getMonth(), 1)), date_to: today };
  return { date_from: "", date_to: "" };
}

export const TODAY: Dates = rangeDates("today");

/** أيّ الفترات الجاهزة تطابق هذين التاريخين — وإلا «مخصّص». */
export function rangeOf(d: Dates): Range {
  for (const r of ["today", "yesterday", "week", "month", "all"] as Range[]) {
    const x = rangeDates(r);
    if (x.date_from === d.date_from && x.date_to === d.date_to) return r;
  }
  return "custom";
}

const LABELS: [Range, string][] = [
  ["today", "اليوم"], ["yesterday", "أمس"], ["week", "هذا الأسبوع"],
  ["month", "هذا الشهر"], ["all", "الكل"], ["custom", "تاريخ مخصّص"],
];

/** وصف الفترة المطبّقة بالكلمات — يُعرض فوق الجدول كي لا يُقرأ على غير فترته. */
export function rangeText(d: Dates): string {
  if (d.date_from && d.date_to) return d.date_from === d.date_to ? d.date_from : `${d.date_from} ← ${d.date_to}`;
  if (d.date_from) return `من ${d.date_from}`;
  if (d.date_to) return `حتى ${d.date_to}`;
  return "كل التواريخ";
}

export default function DateRange({ value, onChange, compact }: {
  value: Dates; onChange: (d: Dates) => void; compact?: boolean;
}) {
  const current = rangeOf(value);
  // «مخصّص» يُظهر التاريخين؛ والفترة الجاهزة تكتفي بزرّها
  const showDates = current === "custom";
  return (
    <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
      <div className="segment">
        {LABELS.map(([k, label]) => (
          <button key={k} type="button" className={current === k ? "active" : ""}
            style={compact ? { padding: "0 10px" } : undefined}
            onClick={() => {
              if (k === "custom") onChange({ ...value, date_from: value.date_from || TODAY.date_from, date_to: "" });
              else onChange(rangeDates(k));
            }}>
            {label}
          </button>
        ))}
      </div>
      {showDates && (
        <>
          <input type="date" value={value.date_from} title="من تاريخ"
            onChange={(e) => onChange({ ...value, date_from: e.target.value })} />
          <span style={{ color: "var(--muted)", fontSize: 12 }}>←</span>
          <input type="date" value={value.date_to} title="إلى تاريخ"
            onChange={(e) => onChange({ ...value, date_to: e.target.value })} />
        </>
      )}
    </div>
  );
}
