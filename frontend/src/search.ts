/**
 * بحث سريع موحّد: لا يفرّق بين الحروف الكبيرة والصغيرة (Likee = likee)،
 * ولا بين أشكال الحرف العربي (أ إ آ ا · ة ه · ى ي)، وكل كلمة مكتوبة
 * يجب أن توجد في أحد الحقول — بأي ترتيب.
 */
export function normalize(s: string): string {
  return s
    .replace(/İ/g, "i")
    .toLowerCase()
    .replace(/ı/g, "i")
    .replace(/[أإآ]/g, "ا")
    .replace(/ة/g, "ه")
    .replace(/ى/g, "ي")
    .replace(/[ً-ْ]/g, "");   // التشكيل
}

/** هل تطابق عبارةُ البحث `q` أحد الحقول؟ عبارة فارغة ⇐ نعم. */
export function matches(q: string, ...fields: (string | number | null | undefined)[]): boolean {
  const words = normalize(q).split(/\s+/).filter(Boolean);
  if (!words.length) return true;
  const hay = normalize(fields.filter((f) => f !== null && f !== undefined && f !== "").join(" "));
  return words.every((w) => hay.includes(w));
}
