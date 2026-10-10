import axios from "axios";

// عميل API — يوجّه الطلبات لـ Django backend
export const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || "http://localhost:8000/api",
});

// إرفاق توكن الدخول تلقائياً
api.interceptors.request.use((config) => {
  const token = localStorage.getItem("access");
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

// جلسةٌ سقطت (تغيّرت كلمة السر · خروج من كل الأجهزة · حساب أو متجر أُوقف):
// تُمسح ويُعاد المستخدم إلى الدخول — بدل صفحاتٍ فارغة وأخطاءٍ متتالية
api.interceptors.response.use(undefined, (err) => {
  const url = String(err?.config?.url || "");
  if (err?.response?.status === 401 && localStorage.getItem("access") && !url.includes("/auth/login/")) {
    localStorage.removeItem("access");
    localStorage.removeItem("refresh");
    if (!window.location.pathname.startsWith("/login")) window.location.assign("/login");
  }
  return Promise.reject(err);
});

export interface Wallet {
  balance: string;
  credit_limit: string;
  currency: string;
  available: string;
}
export interface Tenant {
  id: number;
  name: string;
  subdomain: string;
  theme: string;
  theme_color: string;
  /** عملة دفتر المتجر — كل رقم في لوحة الإدارة معروض بها */
  base_currency?: string;
  /** حجم العرض بالمئة (75–125) — انظر `uiScale.ts` */
  ui_scale?: number;
}
/**
 * هويّة المتجر صاحبِ العنوان المفتوح — تُقرأ قبل الدخول من `GET /storefront/`.
 * `null` تعني الباب العام (`wtn4.com`)، فتظهر صفحة الدخول العامّة.
 */
export interface Storefront {
  name: string;
  short_name: string;
  subdomain: string;
  logo_url: string;
  theme: string;
  theme_color: string;
  font: string;
  tagline?: string;
  login_footer?: string;
  social_links?: Record<string, string>;
  ui_scale?: number;
  /** عملات التسجيل: عملة الموقع أوّلاً ثم ما له سعر صرف */
  currencies?: string[];
}
export interface User {
  id: number;
  login_id: string;
  name: string;
  role: string;
  role_label: string;
  tenant: Tenant | null;
  wallet: Wallet | null;
}
export interface Game {
  id: number;
  name: string;
  image_url: string;
  status: string;
  status_label: string;
  require_player_id: boolean;
  product_count: number;
  dealer_note: string;
  description: string;
  kurulu_sale: boolean;
  toplu_sale: boolean;
  sms_template: string;
  sort_order: number;
  created_at: string;
}
export interface Product {
  id: number;
  game: number;
  game_name: string;
  name: string;
  cost_price: string;
  recommended_price: string;
  profit: string;
  kupur: string;
  status: string;
  status_label: string;
  execution_type: string;
  is_parcali: boolean;
  provider: number | null;
  provider_alt1: number | null;
  provider_alt2: number | null;
  provider_package_id: string;
  description: string;
  sort_order: number;
  created_at: string;
  /** «amount» = بالكمية: الأسعار لكل qty_unit وحدة، والكمية بين qty_min وqty_max */
  sale_type?: "package" | "amount";
  qty_min?: number;
  qty_max?: number;
  qty_unit?: number;
}
export interface GameDetail extends Game {
  products: Product[];
}
export interface Order {
  id: number;
  receipt_no: string;
  dealer_name: string;
  game_name: string;
  product_name: string;
  player_id: string;
  customer_phone: string;
  cost_price: string;
  sell_price: string;
  profit: string;
  status: string;
  status_label: string;
  provider_name: string;
  pin_result: string;
  api_response: string;
  provider_ref: string;
  provider_note: string;
  last_sync_at: string | null;
  // أرقام الوكيل: بكم باع لزبونه وكم ربح (شراؤه هو sell_price أعلاه)
  dealer_sell_price: string;
  dealer_profit: string;
  // ملاحظة المشغّل على الطلب — سبب القبول أو الرفض اليدوي، يراها الوكيل
  dealer_note: string;
  balance_before: string;
  balance_after: string;
  created_at: string;
}
export interface Provider {
  id: number;
  name: string;
  type: string;
  type_label: string;
  status: string;
  status_label: string;
  // الأرقام بعملة المزوّد، ويرافقها مقابلُها بعملة الدفتر (null = هي نفسها،
  // أو لا سعر صرف مضبوط لها)
  currency: string;          // المحفوظ (يُحرَّر في النافذة)
  shown_currency: string;    // المعروض — عملةُ الدفتر لمن لا يسعّر بعملته
  has_own_currency: boolean;
  base_currency: string;
  real_balance: string;
  balance: string;
  debt: string;
  real_balance_base: string | null;
  balance_base: string | null;
  debt_base: string | null;
  loss_guard: boolean;
  auto_update: boolean;
  config: Record<string, string>;
}
export interface Dealer {
  id: number;
  login_id: string;
  /** الرقم التسلسلي داخل المتجر — هو ما يُعرض في عمود «الرقم» */
  dealer_no: number | null;
  name: string;
  balance: string;
  credit_limit: string;
  currency: string;
  /** عملة عرض الوكيل — فارغة تعني عملة الموقع */
  display_currency: string;
  /** عملة الوكيل الفعلية، ورصيده وحدّه بها — ما يُعرض ويُكتب له في لوحة الإدارة */
  own_currency?: string;
  balance_own?: string;
  credit_limit_own?: string;
  status: string;
  country: string;
  group: string;
  shopping: boolean;
  oyun: boolean;
  active: boolean;
  /** حسابٌ قُفل بعد محاولات دخول خاطئة — يفكّه تبديلُ كلمة السرّ */
  is_locked: boolean;
  children_count: number;
  /** وكيل كبير: تحته دكاكين، يُميَّز بنجمة وصفوف تتفرّع منه */
  is_big: boolean;
  role: string;
  parent: number | null;
  parent_name: string;
  /** دكاكين هذا الوكيل الكبير — تُعرض عند فتح صفّه، ولا تقف صفوفاً مستقلّة */
  children?: Dealer[];
  /** رقم واتساب مطبَّعاً بلا + — فارغ يعني أن زرّ الإرسال معطّل لهذا الوكيل */
  whatsapp: string;
  /** موافقته على التحصيل الآلي — عليها يُفلتر الإرسال الجماعي */
  auto_debt_collection: boolean;
}
