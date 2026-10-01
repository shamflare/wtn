// أسعار الباقة «بالكمية» — تُعرض وتُكتب **للوحدة الواحدة** كما في بركات.
//
// الخادم يخزّنها لكل `qty_unit` وحدة (مثلاً لكل 100,000): خانات الأسعار فيه بمنزلتين
// عشريتين، وسعر الوحدة كسورٌ صغيرة (0.0000609). التخزين بالكتلة لا يُضيع دقّةً:
// 0.03 للوحدة = 3,000.00 لكل 100,000 بالضبط. فهذا الملف وحده يترجم بين الاثنين،
// وكل شاشةٍ تعرض سعر الوحدة وتستقبله، ولا يرى أحدٌ رقم الكتلة.

export interface QtyLike { sale_type?: string; qty_unit?: number }

export const isAmountP = (p?: QtyLike | null) => !!p && p.sale_type === "amount";

/** سعر الكتلة (كما في الخادم) ⇐ سعر الوحدة الواحدة */
export function toUnit(block: string | number | null | undefined, p?: QtyLike | null): number {
  const v = Number(block || 0);
  return isAmountP(p) ? v / (p!.qty_unit || 1) : v;
}

/** سعر الوحدة كما كتبه المستخدم ⇐ سعر الكتلة الذي يحفظه الخادم (منزلتان) */
export function toBlock(input: string | number, p?: QtyLike | null): string {
  const v = Number(String(input).replace(",", ".")) || 0;
  return isAmountP(p) ? (Math.round(v * (p!.qty_unit || 1) * 100) / 100).toFixed(2) : String(input);
}

/** رقمٌ صغير بلا تقريبٍ يمحوه: 0.0000609 لا 0.00 — وما بلغ الواحد فبمنزلتين */
export function fmtPrecise(v: number): string {
  if (!Number.isFinite(v)) return "0";
  const abs = Math.abs(v);
  if (abs >= 1 || abs === 0) return v.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  return v.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 8 });
}

/** السعر للعرض: للوحدة إن كانت الباقة بالكمية، وإلا كما هو بمنزلتين */
export function showPrice(block: string | number | null | undefined, p?: QtyLike | null): string {
  return fmtPrecise(toUnit(block, p));
}

/** قيمة حقل الإدخال عند فتح التعديل: سعر الوحدة كاملاً بلا فواصل آلاف */
export function editValue(block: string | number | null | undefined, p?: QtyLike | null): string {
  if (!isAmountP(p)) return String(block ?? "");
  const v = toUnit(block, p);
  return String(Number(v.toPrecision(12)));
}

/** وسمٌ قصير يُلحق بالسعر */
export const unitSuffix = (p?: QtyLike | null) => (isAmountP(p) ? " / للوحدة" : "");

/**
 * حجم الكتلة الداخلي لباقة كميةٍ تُنشأ يدوياً: أصغر قوّةٍ لعشرة يصير عندها سعر
 * الوحدة **رقماً بمنزلتين بالضبط** ولا يقلّ عن 1 — فـ0.03 ⇐ 100 (3.00)، و0.0000609
 * ⇐ 100,000 (6.09). فلا يضيع من السعر المكتوب شيء.
 */
export function pickUnit(unitPrice: number): number {
  const v = Math.abs(unitPrice);
  if (!v) return 1;
  let unit = 1;
  const exact = (u: number) => Math.abs(v * u - Math.round(v * u * 100) / 100) < 1e-9;
  while ((v * unit < 1 || !exact(unit)) && unit < 1e9) unit *= 10;
  return unit;
}
