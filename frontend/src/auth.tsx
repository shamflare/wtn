import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { api, type User } from "./api";
import { applyUiScale } from "./uiScale";

interface AuthCtx {
  user: User | null;
  loading: boolean;
  login: (loginId: string, password: string, totp?: string) => Promise<LoginResult>;
  logout: () => void;
}
export interface TotpSetup { qr: string; secret: string }
type LoginResult = { ok: true; role: string } | { requireTotp: true } | { setup: TotpSetup }
  | { ok: false; error: string };

// الصفحة الرئيسية لكل دور
export function roleHome(role?: string): string {
  if (role === "platform_owner") return "/platform";
  if (role === "ana_bayi") return "/bigagent";
  if (role === "bayi") return "/store";
  return "/home"; // tenant_admin
}

const Ctx = createContext<AuthCtx>(null!);
export const useAuth = () => useContext(Ctx);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  // استعادة الجلسة عند التحميل
  useEffect(() => {
    const token = localStorage.getItem("access");
    if (!token) return setLoading(false);
    api
      .get("/auth/me/")
      .then((r) => setUser(r.data))
      .catch(() => localStorage.removeItem("access"))
      .finally(() => setLoading(false));
  }, []);

  // تطبيق ثيم وخط وحجم عرض المستأجر على الصفحة
  useEffect(() => {
    const theme = user?.tenant?.theme || "teal";
    document.documentElement.setAttribute("data-theme", theme);
    document.documentElement.setAttribute("data-font", (user?.tenant as any)?.font || "cairo");
    applyUiScale(user?.tenant?.ui_scale);
  }, [user]);

  async function login(loginId: string, password: string, totp?: string): Promise<LoginResult> {
    try {
      const r = await api.post("/auth/login/", { login_id: loginId, password, totp });
      if (r.data.require_totp) return { requireTotp: true };
      // مالك المنصّة بلا تحقق بخطوتين: يُعدّه الآن قبل أي جلسة
      if (r.data.require_totp_setup) return { setup: { qr: r.data.qr, secret: r.data.secret } };
      localStorage.setItem("access", r.data.tokens.access);
      localStorage.setItem("refresh", r.data.tokens.refresh);
      setUser(r.data.user);
      return { ok: true, role: r.data.user.role };
    } catch (e: any) {
      return { ok: false, error: e?.response?.data?.detail || "فشل الاتصال بالخادم" };
    }
  }

  function logout() {
    localStorage.removeItem("access");
    localStorage.removeItem("refresh");
    setUser(null);
  }

  return <Ctx.Provider value={{ user, loading, login, logout }}>{children}</Ctx.Provider>;
}
