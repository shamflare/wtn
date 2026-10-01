import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AuthProvider, useAuth, roleHome } from "./auth";
import AdminLayout from "./layout/AdminLayout";
import Login from "./pages/Login";
import Dealers from "./pages/Dealers";
import Exchange from "./pages/Exchange";
import Games from "./pages/Games";
import Library from "./pages/Library";
import Support from "./pages/Support";
import MyInvoices from "./pages/MyInvoices";
import GameDetail from "./pages/GameDetail";
import PackageLinks from "./pages/PackageLinks";
import PinList from "./pages/PinList";
import PriceGroups from "./pages/PriceGroups";
import Providers from "./pages/Providers";
import Orders from "./pages/Orders";
import Pool from "./pages/Pool";
import SiteSettings from "./pages/SiteSettings";
import AgentDesign from "./pages/AgentDesign";
import DealerCards from "./pages/DealerCards";
import Accounts from "./pages/Accounts";
import PaymentMethods from "./pages/PaymentMethods";
import PaymentTracking from "./pages/PaymentTracking";
import Reports from "./pages/Reports";
import Inventory from "./pages/Inventory";
import Store from "./pages/Store";
import Platform from "./pages/Platform";
import Ledger from "./pages/Ledger";
import SmsSettings from "./pages/SmsSettings";
import WhatsAppSettings from "./pages/WhatsAppSettings";
import DealerReport from "./pages/DealerReport";
import AgentHome from "./pages/AgentHome";
import AgentDealers from "./pages/AgentDealers";
import AgentPrices from "./pages/AgentPrices";
import AgentOrders from "./pages/AgentOrders";
import Home from "./pages/Home";

// حارس صلاحيات: يمنع الوصول لغير المصرّح ويوجّه كل دور للوحته
function Guard({ children, roles, bare }:
  { children: React.ReactNode; roles?: string[]; bare?: boolean }) {
  const { user, loading } = useAuth();
  if (loading) return <div style={{ padding: 40, textAlign: "center" }}>جارٍ التحميل...</div>;
  if (!user) return <Navigate to="/login" replace />;
  if (roles && !roles.includes(user.role)) return <Navigate to={roleHome(user.role)} replace />;
  return bare ? <>{children}</> : <AdminLayout>{children}</AdminLayout>;
}

// صفحات لوحة الأدمن → لصاحب المتجر فقط
const Admin = (el: React.ReactNode) => <Guard roles={["tenant_admin"]}>{el}</Guard>;
// لوحة الوكيل الكبير — نفس الهيكل، صلاحياته وحده
const Agent = (el: React.ReactNode) => <Guard roles={["ana_bayi"]}>{el}</Guard>;

function RoleHomeRedirect() {
  const { user, loading } = useAuth();
  if (loading) return null;
  return <Navigate to={user ? roleHome(user.role) : "/login"} replace />;
}

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<Login />} />

          {/* لوحات مستقلة (بحسب الدور) */}
          <Route path="/platform" element={<Guard roles={["platform_owner"]} bare><Platform /></Guard>} />
          {/* لوحة الوكيل الكبير — هيكل لوحة صاحب المتجر نفسه بأقسام ثلاثة */}
          <Route path="/bigagent" element={Agent(<AgentHome />)} />
          <Route path="/bigagent/dealers" element={Agent(<AgentDealers />)} />
          <Route path="/bigagent/price-groups" element={Agent(<AgentPrices />)} />
          <Route path="/bigagent/orders" element={Agent(<AgentOrders />)} />
          {/* متجر الشراء للدكاكين وحدها — الوكيل الكبير يدير ولا يشتري لنفسه */}
          <Route path="/store/*" element={<Guard roles={["bayi"]} bare><Store /></Guard>} />

          {/* الصفحة الرئيسية (صاحب المتجر) */}
          <Route path="/home" element={Admin(<Home />)} />

          {/* OyunPin (صاحب المتجر) */}
          <Route path="/oyunpin" element={Admin(<Games />)} />
          <Route path="/oyunpin/library" element={Admin(<Library />)} />
          <Route path="/oyunpin/pin-list" element={Admin(<PinList />)} />
          <Route path="/oyunpin/package-links" element={Admin(<PackageLinks />)} />
          <Route path="/oyunpin/orders" element={Admin(<Orders />)} />
          <Route path="/oyunpin/price-groups" element={Admin(<PriceGroups />)} />
          <Route path="/oyunpin/pool" element={Admin(<Pool />)} />
          <Route path="/oyunpin/providers" element={Admin(<Providers />)} />
          <Route path="/oyunpin/:id" element={Admin(<GameDetail />)} />

          {/* الوكلاء */}
          <Route path="/dealers" element={Admin(<Dealers />)} />
          <Route path="/ayarlar/payments" element={Admin(<PaymentTracking />)} />
          <Route path="/ayarlar/payment-methods" element={Admin(<PaymentMethods />)} />
          <Route path="/ayarlar/exchange" element={Admin(<Exchange />)} />
          <Route path="/ayarlar/accounts" element={Admin(<Accounts />)} />
          <Route path="/ayarlar/ledger" element={Admin(<Ledger />)} />

          {/* الإعدادات — إعدادات المتجر نفسه */}
          <Route path="/settings/site" element={Admin(<SiteSettings />)} />
          <Route path="/settings/agent-design" element={Admin(<AgentDesign />)} />
          <Route path="/settings/cards" element={Admin(<DealerCards />)} />
          <Route path="/settings/sms" element={Admin(<SmsSettings />)} />
          <Route path="/settings/whatsapp" element={Admin(<WhatsAppSettings />)} />
          <Route path="/settings/support" element={Admin(<Support />)} />
          <Route path="/settings/invoices" element={Admin(<MyInvoices />)} />

          {/* Raporlar */}
          <Route path="/reports" element={Admin(<Reports />)} />
          <Route path="/reports/profits" element={Admin(<DealerReport title="تقرير الأرباح (حسب الوكيل)" highlight="profit" />)} />
          <Route path="/reports/inventory" element={Admin(<Inventory />)} />
          {/* «كشف الوكلاء» كان نفس بيانات «تقرير الأرباح» بعنوان آخر — حلّ محلّه الجرد */}
          <Route path="/reports/dealers" element={<Navigate to="/reports/inventory" replace />} />

          <Route path="*" element={<RoleHomeRedirect />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}
