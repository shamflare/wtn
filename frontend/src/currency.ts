import { useAuth } from "./auth";

/** العملات المدعومة في طرق الدفع وسعر الصرف العام — مطابقة لـ backend/payments/models.py */
export const CURRENCIES: { code: string; label: string; symbol: string }[] = [
  { code: "TRY", label: "ليرة تركية", symbol: "₺" },
  { code: "USD", label: "دولار أمريكي", symbol: "$" },
  { code: "SYP", label: "ليرة سورية", symbol: "ل.س" },
  { code: "EUR", label: "يورو", symbol: "€" },
  { code: "SAR", label: "ريال سعودي", symbol: "﷼" },
  { code: "AED", label: "درهم إماراتي", symbol: "د.إ" },
  { code: "EGP", label: "جنيه مصري", symbol: "ج.م" },
];

/** عملة طريقة دفع متروكة للوكيل: يختار عند الإيداع العملة التي أرسل بها. */
export const ANY_CURRENCY = "ANY";

export const symbolOf = (code: string) =>
  CURRENCIES.find((c) => c.code === code)?.symbol || code;

export const labelOf = (code: string) =>
  CURRENCIES.find((c) => c.code === code)?.label || code;

export const money = (v: string | number, digits = 2) =>
  Number(v || 0).toLocaleString("en-US", { minimumFractionDigits: digits, maximumFractionDigits: digits });

/**
 * عملة دفتر المتجر كما تصل في `/auth/me/` — تستعملها لوحة الإدارة.
 * لوحة الوكيل لا تستعملها: أرقامه تصل محوَّلةً إلى عملة عرضه ومعها رمزها.
 */
export function useBaseCurrency(): string {
  const { user } = useAuth();
  return user?.tenant?.base_currency || "TRY";
}

/** رمز عملة الدفتر — للإلحاق بأرقام لوحة الإدارة. */
export function useBaseSymbol(): string {
  return symbolOf(useBaseCurrency());
}
