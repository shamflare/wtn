import { createContext, useContext, useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { api, type Storefront } from "../api";
import { applyAgentTheme, cachedAgentTheme, type AgentTheme } from "../agentTheme";
import { SOCIAL_ICONS, SocialGlyph } from "../socialIcons";
import { applyUiScale } from "../uiScale";
import "../pages/store.css";

/* ═══════════════════════════════════════════════════════════════════════
   الباب العام للمتجر — الواجهة والدخول والتسجيل.

   ثلاث صفحاتٍ يراها الزائر قبل أي حساب، فهي للجوال أوّلاً كلوحة الوكيل: عرض
   الجهاز لا عرض لوحة الإدارة الثابت (1366)، وبألوان «تصميم واجهة الوكلاء»
   نفسها — فيرى الوكيل هويّة متجره ذاتها قبل الدخول وبعده.
   ═══════════════════════════════════════════════════════════════════════ */

const StoreCtx = createContext<Storefront | null | undefined>(undefined);
/** هويّة المتجر: `undefined` أثناء التحميل، و`null` على باب المنصّة العام (لا متجر) */
export const useStorefront = () => useContext(StoreCtx);

function useMobileViewport(bg: string) {
  useEffect(() => {
    const vp = document.querySelector('meta[name="viewport"]');
    const prevVp = vp?.getAttribute("content") ?? null;
    vp?.setAttribute("content", "width=device-width, initial-scale=1, viewport-fit=cover");
    let tc = document.querySelector('meta[name="theme-color"]');
    const created = !tc;
    if (!tc) { tc = document.createElement("meta"); tc.setAttribute("name", "theme-color"); document.head.appendChild(tc); }
    const prevTc = tc.getAttribute("content");
    tc.setAttribute("content", bg);
    const prevBg = document.body.style.background;
    document.body.style.background = bg;
    // تكبير لوحة الإدارة (zoom) لا معنى له بعرض الجهاز — يُرفع ما دامت الصفحة العامة مفتوحة
    applyUiScale(100);
    return () => {
      if (vp && prevVp !== null) vp.setAttribute("content", prevVp);
      if (created) tc?.remove(); else if (prevTc !== null) tc?.setAttribute("content", prevTc);
      document.body.style.background = prevBg;
    };
  }, [bg]);
}

export default function PublicShell({ children, narrow }: { children: React.ReactNode; narrow?: boolean }) {
  const [store, setStore] = useState<Storefront | null | undefined>(undefined);
  const [theme, setTheme] = useState<AgentTheme>(() => cachedAgentTheme());
  const loc = useLocation();

  useEffect(() => {
    api.get("/storefront/").then((r) => {
      const s: (Storefront & { agent_theme?: AgentTheme }) | null = r.data.store;
      setStore(s);
      if (s) {
        document.title = s.name;
        setTheme(s.agent_theme || {});
      }
    }).catch(() => setStore(null));
  }, []);
  useEffect(() => { applyAgentTheme(theme); }, [theme]);
  useMobileViewport(theme.bg || "#07090e");

  const name = store?.short_name || store?.name || "متجر الشحن";
  const onLogin = loc.pathname.startsWith("/login");
  const onRegister = loc.pathname.startsWith("/register");

  return (
    <StoreCtx.Provider value={store}>
      <div className="ag ag-public" dir="rtl">
        <header className="ag-top">
          <div className="ag-top-in">
            <Link to="/" className="ag-brand" style={{ color: "inherit", textDecoration: "none" }}>
              {store?.logo_url ? <img src={store.logo_url} alt={name} /> : (
                <>
                  <span className="ag-brand-mark">{name.trim().charAt(0)}</span>
                  <span style={{ minWidth: 0 }}>
                    <div className="ag-brand-name">{name}</div>
                    {store?.tagline && <div className="ag-brand-sub">{store.tagline}</div>}
                  </span>
                </>
              )}
            </Link>
            {store !== null && (
              <div className="ag-pub-actions">
                {!onRegister && <Link to="/register" className="ag-pub-btn ghost">حساب جديد</Link>}
                {!onLogin && <Link to="/login" className="ag-pub-btn">تسجيل الدخول</Link>}
              </div>
            )}
          </div>
        </header>

        <main className="ag-main" style={narrow ? { maxWidth: 460 } : undefined}>
          {children}
        </main>

        <footer className="ag-pub-foot">
          {store?.social_links && (
            <div className="ag-pub-socials">
              {SOCIAL_ICONS.filter((s) => store.social_links?.[s.key]).map((s) => (
                <a key={s.key} href={store.social_links![s.key]} target="_blank" rel="noreferrer" title={s.label}>
                  <SocialGlyph icon={s} size={26} />
                </a>
              ))}
            </div>
          )}
          {store?.login_footer && <div>{store.login_footer}</div>}
        </footer>
      </div>
    </StoreCtx.Provider>
  );
}
