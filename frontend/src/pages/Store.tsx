import { createContext, useContext, useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useLocation, useNavigate } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";
import { money, symbolOf } from "../currency";
import { downloadCsv } from "../csv";
import Icon from "../components/Icon";
import { NotificationList, NotificationSummary, useNotifications } from "../components/NotificationBell";
import Tickets from "../components/Tickets";
import ApiDocs from "../components/ApiDocs";
import { CardStrip, type Card } from "../components/HomeCards";
import TopUp from "../components/TopUp";
import { applyThemeConfig } from "../theme";
import { showPrice } from "../unitPrice";
import { AGENT_THEME_DEFAULTS, applyAgentTheme, cachedAgentTheme, type AgentTheme } from "../agentTheme";
import "./store.css";

/* ═══════════════════════════════════════════════════════════════════════
   لوحة الوكيل (bayi) — متجره الذي يبيع منه لزبائنه.

   تصميمٌ داكن للجوال أوّلاً، على خلاف لوحة الإدارة الثابتة العرض: الوكيل
   يعمل من هاتفه في دكّانه، فكل قسم هنا يُقرأ بإبهامٍ واحد — تنقّلٌ سفلي،
   وبطاقاتٌ بدل الجداول (الطلب كلّه في بطاقته بلا تمرير أفقي).
   ═══════════════════════════════════════════════════════════════════════ */

interface SProduct {
  id: number; name: string; price: string;
  recommended_price: string; require_player_id: boolean;
  /** «amount» = بالكمية: price وrecommended_price لكل qty_unit وحدة */
  sale_type?: "package" | "amount"; qty_min?: number; qty_max?: number; qty_unit?: number;
}

const isAmount = (p: SProduct) => p.sale_type === "amount";
const fmtQty = (n?: number) => Number(n || 0).toLocaleString("en-US");
/** قيمة كميةٍ من باقةٍ بالكمية: السعر لكل كتلة × الكمية ÷ حجم الكتلة */
const amountOf = (price: string, qty: number, unit?: number) =>
  Math.round(Number(price || 0) * qty / (unit || 1) * 100) / 100;

/** كمياتٌ سريعة مرتّبة بين الحدّين: الحدّ الأدنى ثم أرقامٌ مستديرة */
function quickQtys(min = 1, max = 1): number[] {
  const out = new Set<number>([min]);
  for (const base of [1, 2, 5]) {
    for (let p = 1; p <= 1e9; p *= 10) {
      const v = base * p;
      if (v > min && v <= max) out.add(v);
    }
  }
  return [...out].sort((a, b) => a - b).slice(0, 6);
}
interface SGame {
  id: number; name: string; image_url: string; require_player_id: boolean; products: SProduct[];
  /** وصف اللعبة وملاحظة الوكيل — من «تفاصيل اللعبة» لدى صاحب المتجر */
  description?: string; dealer_note?: string;
}
interface Summary {
  balance: string; credit_limit: string; currency: string;
  orders: number; profit: string; sell: string; pending: number;
  store?: { name: string; short_name: string; logo_url: string };
}

type Tab = "home" | "sell" | "mobile" | "packages" | "orders" | "reports" | "wallet" | "topup" | "api" | "support" | "settings";

// كل قسم له رابطه: /store (الرئيسية) · /store/orders · /store/sell/12 (لعبة) ...
const SECTIONS: Tab[] = ["sell", "mobile", "packages", "orders", "reports", "wallet", "topup", "api", "support", "settings"];
function parsePath(pathname: string): { tab: Tab; gameId: number | null } {
  const [seg, sub] = pathname.replace(/^\/store\/?/, "").split("/");
  const tab = (SECTIONS as string[]).includes(seg) ? (seg as Tab) : "home";
  const gameId = tab === "sell" && sub ? Number(sub) || null : null;
  return { tab, gameId };
}
const pathForTab = (t: Tab) => (t === "home" ? "/store" : `/store/${t}`);

/** أقسام «المزيد» — لا تتّسع لها ستّ خانات في الشريط السفلي */
const MORE_TABS: Tab[] = ["mobile", "topup", "packages", "reports", "support", "settings", "api"];

/**
 * لون الحالة بمنظور الوكيل: انتظار · تنفيذ · نجاح · رفض.
 * ولا لون لـ«العالق»: الخادم يرسله إلى الوكيل «قيد الانتظار» (DEALER_STATUS)
 * — فالتعثّر في توجيه صاحب المتجر شأنه، ولا حيلة للوكيل فيه.
 */
const ST_COLOR: Record<string, string> = {
  success: "var(--ok)", pending: "var(--warn)", processing: "var(--info)", cancelled: "var(--danger)",
};
const ST_CHIPS: { key: string; label: string }[] = [
  { key: "all", label: "الكل" },
  { key: "success", label: "ناجح" },
  { key: "pending", label: "قيد الانتظار" },
  { key: "cancelled", label: "ملغى" },
];

/** عملة عرض الوكيل — يحدّدها صاحب المتجر، وتصل أرقامه محوَّلةً إليها. */
const CurrencyCtx = createContext("");
const useCur = () => symbolOf(useContext(CurrencyCtx));
/** كتالوج المتجر — يُجلب مرّةً للبيع، وتستعير الطلباتُ منه صور ألعابها */
const GamesCtx = createContext<SGame[] | null>(null);

/** ربح الوكيل = سعر بيعه لزبونه − سعر شرائه من المتجر. */
const profitOf = (sell: string | number, paid: string | number) =>
  Number(sell || 0) - Number(paid || 0);

/** لونٌ ثابت لكل اسم — لصورةٍ بديلة حين لا صورة للّعبة */
function hueOf(name: string) {
  let h = 0;
  for (const ch of name || "?") h = (h * 31 + ch.charCodeAt(0)) % 360;
  return `linear-gradient(145deg, hsl(${h} 65% 42%), hsl(${(h + 40) % 360} 60% 22%))`;
}

/** نسخٌ إلى الحافظة مع علامة «نُسخ» لثانيتين على المفتاح المنسوخ */
function useCopy(): [string | null, (text: string, key: string) => void] {
  const [done, setDone] = useState<string | null>(null);
  const timer = useRef<number>(0);
  function copy(text: string, key: string) {
    navigator.clipboard?.writeText(text).catch(() => {});
    setDone(key);
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => setDone(null), 1800);
  }
  return [done, copy];
}

export default function Store() {
  const { user, logout } = useAuth();
  const nav = useNavigate();
  const loc = useLocation();
  const { tab, gameId } = parsePath(loc.pathname);
  const goTab = (t: Tab) => { setMore(false); setBell(false); nav(pathForTab(t)); };
  const [summary, setSummary] = useState<Summary | null>(null);
  const [games, setGames] = useState<SGame[] | null>(null);
  const [unread, setUnread] = useState(0);
  const [more, setMore] = useState(false);
  const [bell, setBell] = useState(false);
  const notif = useNotifications();
  // ألوان صاحب المتجر لواجهة الوكيل: المخزّن محلياً فوراً (بلا وميض الافتراضي)، ثم الخادم
  const [agTheme, setAgTheme] = useState<AgentTheme>(() => cachedAgentTheme());
  const pageBg = agTheme.bg || AGENT_THEME_DEFAULTS.bg;

  function loadSummary() {
    api.get("/store/summary/").then((r) => setSummary(r.data)).catch(() => {});
  }
  useEffect(() => {
    loadSummary();
    api.get("/store/catalog/").then((r) => setGames(r.data.games)).catch(() => setGames([]));
    // الخط يرثه الوكيل من تخصيص متجره — والألوان للّوحة الداكنة نفسها
    api.get("/settings/theme/").then((r) => applyThemeConfig(r.data.config || {})).catch(() => {});
    api.get("/settings/agent-theme/").then((r) => setAgTheme(r.data.theme || {})).catch(() => {});
  }, []);
  useEffect(() => { applyAgentTheme(agTheme); }, [agTheme]);

  /* لوحة الإدارة بعرضٍ ثابت (1366) — والوكيل وحده يعمل بعرض جهازه.
     نبدّل وسم viewport ولون شريط المتصفّح ما دامت اللوحة مفتوحة، ونعيدهما عند الخروج. */
  useEffect(() => {
    const vp = document.querySelector('meta[name="viewport"]');
    const prevVp = vp?.getAttribute("content") ?? null;
    vp?.setAttribute("content", "width=device-width, initial-scale=1, viewport-fit=cover");
    let tc = document.querySelector('meta[name="theme-color"]');
    const createdTc = !tc;
    if (!tc) { tc = document.createElement("meta"); tc.setAttribute("name", "theme-color"); document.head.appendChild(tc); }
    const prevTc = tc.getAttribute("content");
    tc.setAttribute("content", pageBg);
    const prevBg = document.body.style.background;
    document.body.style.background = pageBg;
    return () => {
      if (vp && prevVp !== null) vp.setAttribute("content", prevVp);
      if (createdTc) tc?.remove(); else if (prevTc !== null) tc?.setAttribute("content", prevTc);
      document.body.style.background = prevBg;
    };
  }, [pageBg]);

  // عدّاد رسائل الدعم غير المقروءة
  useEffect(() => {
    const poll = () => api.get("/tickets/unread-count/").then((r) => setUnread(r.data.unread)).catch(() => {});
    poll();
    const id = setInterval(poll, 15000);
    return () => clearInterval(id);
  }, [tab]);

  // كل انتقالٍ يبدأ من أعلى الصفحة — لا من حيث توقّف التمرير في القسم السابق
  useEffect(() => { window.scrollTo(0, 0); }, [loc.pathname]);

  const balance = summary?.balance ?? user?.wallet?.balance ?? "0";
  const currency = summary?.currency ?? user?.wallet?.currency ?? "";
  const storeName = summary?.store?.short_name || user?.tenant?.name || "متجر الشحن";
  const logo = summary?.store?.logo_url || "";
  const navOn = (t: Tab) =>
    t === "settings" ? MORE_TABS.includes(tab) : tab === t;

  return (
    <CurrencyCtx.Provider value={currency}>
    <GamesCtx.Provider value={games}>
    <div className="ag" dir="rtl">
      {/* ── الرأس: المتجر · الرصيد · الإشعارات ── */}
      <header className="ag-top">
        <div className="ag-top-in">
          {tab !== "home" && (
            <button className="ag-icon-btn" aria-label="رجوع"
              onClick={() => nav(gameId ? "/store/sell" : "/store")}>
              <Icon name="arrowBack" size={19} />
            </button>
          )}
          <button className="ag-brand" onClick={() => goTab("home")}
            style={{ background: "none", border: 0, color: "inherit", padding: 0, textAlign: "start" }}>
            {logo ? <img src={logo} alt={storeName} /> : (
              <>
                <span className="ag-brand-mark">{storeName.trim().charAt(0)}</span>
                <span style={{ minWidth: 0 }}>
                  <div className="ag-brand-name">{storeName}</div>
                  <div className="ag-brand-sub">{user?.name}</div>
                </span>
              </>
            )}
          </button>
          <button className={`ag-balance${Number(balance) < 0 ? " neg" : ""}`} onClick={() => goTab("wallet")}
            title="رصيدي">
            <span className="cur">{symbolOf(currency)}</span>{money(balance)}
          </button>
        </div>
      </header>

      <main className="ag-main">
        <div key={loc.pathname} className="ag-enter">
          {tab === "home" && (
            <HomeTab summary={summary} onGo={goTab} onGame={(g) => nav(`/store/sell/${g.id}`)} />
          )}
          {tab === "sell" && (
            <SellTab gameId={gameId} onGame={(g) => nav(`/store/sell/${g.id}`)}
              onBought={loadSummary} onFinish={() => goTab("orders")} />
          )}
          {tab === "mobile" && <MobileTab />}
          {tab === "packages" && <PackagesTab />}
          {tab === "orders" && <OrdersTab />}
          {tab === "reports" && <ReportsTab />}
          {tab === "wallet" && <WalletTab summary={summary} onTopUp={() => goTab("topup")} />}
          {tab === "topup" && (
            <>
              <h1 className="ag-h1">إضافة رصيد</h1>
              <TopUp onDone={loadSummary} />
            </>
          )}
          {tab === "support" && <Tickets title="الدعم ومراسلة الإدارة" />}
          {(tab === "settings" || tab === "api") && <SettingsTab initial={tab === "api" ? "api" : "account"} />}
        </div>
      </main>

      {/* ── التنقّل السفلي ── */}
      <nav className="ag-nav" aria-label="التنقّل">
        <div className="ag-nav-in">
          <NavItem icon="home" label="الرئيسية" on={(navOn("home") || navOn("sell")) && !bell} onClick={() => goTab("home")} />
          <NavItem icon="receipt" label="طلباتي" on={navOn("orders") && !bell} onClick={() => goTab("orders")} />
          <NavItem icon="bell" label="الإشعارات" on={bell} badge={notif.total}
            onClick={() => { setMore(false); setBell(true); notif.markSeen(); }} />
          <NavItem icon="wallet" label="محفظتي" on={navOn("wallet") && !bell} onClick={() => goTab("wallet")} />
          <NavItem icon="grid" label="المزيد" on={(navOn("settings") || more) && !bell} badge={unread}
            onClick={() => { setBell(false); setMore(true); }} />
        </div>
      </nav>

      {more && (
        <Sheet title="المزيد" onClose={() => setMore(false)}>
          <div className="ag-menu">
            <MenuBtn icon="plusCircle" label="شحن رصيد" tone="var(--primary)" onClick={() => goTab("topup")} />
            <MenuBtn icon="phone" label="موبايل" tone="var(--info)" onClick={() => goTab("mobile")} />
            <MenuBtn icon="tag" label="قائمة الباقات" tone="var(--gold)" onClick={() => goTab("packages")} />
            <MenuBtn icon="chart" label="تقاريري" tone="var(--info)" onClick={() => goTab("reports")} />
            <MenuBtn icon="chat" label="الدعم" tone="var(--ok)" badge={unread} onClick={() => goTab("support")} />
            <MenuBtn icon="user" label="حسابي" tone="var(--violet)" onClick={() => goTab("settings")} />
            <MenuBtn icon="api" label="الربط الخارجي" tone="var(--cyan)" onClick={() => goTab("api")} />
            <MenuBtn icon="logout" label="خروج آمن" tone="var(--danger)" danger onClick={logout} />
          </div>
        </Sheet>
      )}

      {bell && (
        <Sheet title={<>الإشعارات <NotificationSummary data={notif.data} /></>} onClose={() => setBell(false)}>
          <div className="ag-bell-list">
            <NotificationList data={notif.data}
              onPick={(it) => goTab(it.kind === "message" ? "support" : "home")} />
          </div>
        </Sheet>
      )}
    </div>
    </GamesCtx.Provider>
    </CurrencyCtx.Provider>
  );
}

function NavItem({ icon, label, on, onClick, badge }: {
  icon: string; label: string; on: boolean; onClick: () => void; badge?: number;
}) {
  return (
    <button className={`ag-nav-item${on ? " on" : ""}`} onClick={onClick}
      aria-current={on ? "page" : undefined}>
      <span className="ag-nav-ico"><Icon name={icon} size={20} /></span>
      <span>{label}</span>
      {!!badge && <span className="ag-badge">{badge > 9 ? "9+" : badge}</span>}
    </button>
  );
}

function MenuBtn({ icon, label, tone, onClick, badge, danger }: {
  icon: string; label: string; tone: string; onClick: () => void; badge?: number; danger?: boolean;
}) {
  return (
    <button onClick={onClick} className={danger ? "danger" : undefined}>
      <span className="mi" style={{ background: `color-mix(in srgb, ${tone} 12%, transparent)`, color: tone }}><Icon name={icon} size={21} /></span>
      {label}
      {!!badge && <span className="ag-badge" style={{ top: 8, insetInlineEnd: 8 }}>{badge}</span>}
    </button>
  );
}

/** ورقة سفلية على الجوال · نافذة وسطى على الحاسوب */
function Sheet({ title, onClose, children, locked }: {
  title: React.ReactNode; onClose: () => void; children: React.ReactNode; locked?: boolean;
}) {
  useEffect(() => {
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape" && !locked) onClose(); };
    document.addEventListener("keydown", onKey);
    return () => { document.body.style.overflow = prev; document.removeEventListener("keydown", onKey); };
  }, [locked, onClose]);
  // تُرسم في body لا داخل الصفحة: حاوية المحتوى متحرّكة (animation)، وأيّ transform
  // عليها يحبس position: fixed داخلها فتنزل النافذة تحت الشريط السفلي
  return createPortal(
    <div className="ag ag-portal" dir="rtl">
    <div className="ag-sheet-bg" onClick={locked ? undefined : onClose}>
      <div className="ag-sheet" role="dialog" aria-modal="true" onClick={(e) => e.stopPropagation()}>
        <div className="ag-sheet-grip" />
        <div className="ag-sheet-head">
          <h3>{title}</h3>
          <button className="ag-icon-btn" onClick={onClose} disabled={locked} aria-label="إغلاق">
            <Icon name="x" size={17} />
          </button>
        </div>
        {children}
      </div>
    </div>
    </div>,
    document.body,
  );
}

function Empty({ text, icon = "receipt" }: { text: string; icon?: string }) {
  return (
    <div className="ag-empty">
      <span style={{
        display: "grid", placeItems: "center", width: 72, height: 72, borderRadius: 24,
        margin: "0 auto 12px", background: "var(--surface-2)", color: "var(--faint)",
        border: "1px solid var(--border)",
      }}><Icon name={icon} size={30} /></span>
      {text}
    </div>
  );
}

function Skeleton({ h = 88, n = 4 }: { h?: number; n?: number }) {
  return (
    <div className="ag-list">
      {Array.from({ length: n }, (_, i) => <div key={i} className="ag-skel" style={{ height: h }} />)}
    </div>
  );
}

/** حقل تاريخ بعنوانٍ عائم — فارغُه يعني «كل التواريخ» */
function DateField({ label, value, onChange, min, max }: {
  label: string; value: string; onChange: (v: string) => void; min?: string; max?: string;
}) {
  return (
    <label className={`ag-field${value ? "" : " empty"}`}>
      <span>{label}</span>
      <input type="date" dir="ltr" value={value} min={min || undefined} max={max || undefined}
        onChange={(e) => onChange(e.target.value)} />
      {!value && <i className="ph" style={{ fontStyle: "normal" }}>الكل</i>}
    </label>
  );
}

/** صورة اللعبة أو بديلٌ ملوّن بأوّل حرف */
function GameThumb({ name, img, className = "ag-thumb" }: { name: string; img?: string; className?: string }) {
  const [bad, setBad] = useState(false);
  if (img && !bad) return <img className={className} src={img} alt="" loading="lazy" onError={() => setBad(true)} />;
  return <span className={className} style={{ background: hueOf(name) }}>{(name || "?").trim().charAt(0)}</span>;
}

/* ═════════════════════════ الرئيسية ═════════════════════════ */
function HomeTab({ summary, onGo, onGame }: {
  summary: Summary | null; onGo: (t: Tab) => void; onGame: (g: SGame) => void;
}) {
  // بطاقات يكتبها صاحب المتجر لوكلائه (الإعدادات ← بطاقات الوكلاء)
  const [cards, setCards] = useState<Card[]>([]);
  useEffect(() => {
    api.get("/my-cards/").then((r) => {
      setCards(r.data.results);
      // مرورُه بالصفحة رؤيةٌ لها — فلا يبقى الجرس أحمر لبطاقةٍ قرأها هنا
      if (r.data.results?.length) api.post("/my-cards/seen/", {}).catch(() => {});
    }).catch(() => setCards([]));
  }, []);

  const cur = summary ? symbolOf(summary.currency) : "";

  return (
    <div>
      <CardStrip cards={cards} />


      <div className="ag-stats">
        <button className="ag-stat ok" onClick={() => onGo("orders")}>
          <div className="v">{summary ? summary.orders : "—"}</div>
          <div className="l"><Icon name="check" size={13} />طلب ناجح</div>
        </button>
        <button className="ag-stat" onClick={() => onGo("reports")}>
          <div className="v" style={{ color: "var(--gold)" }}>{summary ? money(summary.profit) : "—"}</div>
          <div className="l"><Icon name="dollar" size={13} />أرباحي {cur}</div>
        </button>
        <button className="ag-stat warn" onClick={() => onGo("orders")}>
          <div className="v">{summary ? summary.pending : "—"}</div>
          <div className="l"><Icon name="clock" size={13} />قيد الانتظار</div>
        </button>
      </div>

      <Catalog onGame={onGame} title />
    </div>
  );
}

/** شبكة الألعاب مع البحث — في الرئيسية وفي «البيع» */
function Catalog({ onGame, title }: { onGame: (g: SGame) => void; title?: boolean }) {
  const games = useContext(GamesCtx);
  const [q, setQ] = useState("");
  const needle = q.trim().toLowerCase();
  const shown = (games || []).filter((g) =>
    !needle || g.name.toLowerCase().includes(needle)
    || g.products.some((p) => p.name.toLowerCase().includes(needle)));

  return (
    <>
      {title && (
        <div className="ag-h2">
          <Icon name="games" size={19} style={{ color: "var(--primary)" }} />الألعاب والتطبيقات
          {games && <span className="more">{games.length} قسم</span>}
        </div>
      )}
      <div className="ag-search" style={{ marginBottom: 14 }}>
        <span className="ico"><Icon name="search" size={19} /></span>
        <input placeholder="ابحث عن لعبة أو باقة..." value={q} onChange={(e) => setQ(e.target.value)} />
        {q && <button className="clear" onClick={() => setQ("")} aria-label="مسح"><Icon name="x" size={15} /></button>}
      </div>
      {games === null ? (
        <div className="ag-games">
          {Array.from({ length: 6 }, (_, i) => <div key={i} className="ag-skel" style={{ aspectRatio: "3 / 4" }} />)}
        </div>
      ) : shown.length === 0 ? (
        <Empty icon="games" text={needle ? "لا نتائج مطابقة لبحثك" : "لا توجد ألعاب متاحة للبيع حالياً"} />
      ) : (
        <div className="ag-games">
          {shown.map((g) => (
            <button key={g.id} className="ag-game" onClick={() => onGame(g)}>
              <GameThumb name={g.name} img={g.image_url} className={g.image_url ? "ag-game-img" : "ag-game-ph"} />
              <div className="ag-game-name">{g.name}</div>
              <div className="ag-game-foot">
                <span className="ag-buy-pill"><Icon name="cart" size={14} />شراء</span>
              </div>
            </button>
          ))}
        </div>
      )}
    </>
  );
}

/* ═════════════════════════ البيع ═════════════════════════ */
function SellTab({ gameId, onGame, onBought, onFinish }: {
  gameId: number | null; onGame: (g: SGame) => void; onBought: () => void; onFinish: () => void;
}) {
  const cur = useCur();
  const games = useContext(GamesCtx);
  const [buy, setBuy] = useState<SProduct | null>(null);
  const active = gameId && games ? games.find((g) => g.id === gameId) || null : null;

  if (!gameId) {
    return (
      <>
        <h1 className="ag-h1">البيع</h1>
        <Catalog onGame={onGame} />
      </>
    );
  }
  if (games === null) return <Skeleton h={76} />;
  if (!active) return <Empty icon="games" text="هذه اللعبة غير متاحة حالياً" />;

  return (
    <div>
      <div className="ag-game-head">
        {active.image_url && <div className="bg" style={{ backgroundImage: `url(${active.image_url})` }} />}
        <GameThumb name={active.name} img={active.image_url} className={active.image_url ? "" : "ph"} />
        <div style={{ minWidth: 0 }}>
          <h2>{active.name}</h2>
          <p>
            {active.products.length} باقة
            {active.require_player_id && <> · يتطلّب معرّف اللاعب</>}
          </p>
          {active.description && <p className="ag-game-desc">{active.description}</p>}
        </div>
      </div>
      {active.dealer_note && (
        <div className="ag-note" style={{ marginTop: 0, marginBottom: 14, display: "flex", gap: 8, alignItems: "flex-start" }}>
          <Icon name="warning" size={16} style={{ flexShrink: 0, marginTop: 3 }} />
          <span><b>ملاحظة:</b> {active.dealer_note}</span>
        </div>
      )}

      {/* الباقات بطاقاتٌ بصورة اللعبة: الاسم والسعر تحتها، وزرّ الشراء بعرض البطاقة */}
      <div className="ag-pcards">
        {active.products.map((p) => (
          <div key={p.id} className="ag-pcard" onClick={() => setBuy(p)}>
            <div className="ag-pcard-img">
              <GameThumb name={active.name} img={active.image_url} className="ag-pcard-pic" />
              {isAmount(p) && <span className="ag-pcard-qty">⚖ بالكمية</span>}
            </div>
            <div className="ag-pcard-body">
              <div className="ag-pcard-row">
                <b className="ag-pcard-name">{p.name}</b>
                <span className="ag-pcard-price" dir="ltr"><small>{cur}</small>{showPrice(p.price, p)}</span>
              </div>
              {isAmount(p) ? (
                <div className="ag-pcard-rec">
                  للوحدة · من {fmtQty(p.qty_min)} إلى {fmtQty(p.qty_max)}
                </div>
              ) : Number(p.recommended_price) > 0 && (
                <div className="ag-pcard-rec">المقترح {money(p.recommended_price)} {cur}</div>
              )}
              <button className="ag-pcard-buy" onClick={(e) => { e.stopPropagation(); setBuy(p); }}>
                شراء<Icon name="cart" size={18} />
              </button>
            </div>
          </div>
        ))}
      </div>

      {buy && (
        <BuyModal product={buy} game={active}
          onClose={() => setBuy(null)} onBought={onBought} onFinish={onFinish} />
      )}
    </div>
  );
}

function BuyModal({ product, game, onClose, onBought, onFinish }: {
  product: SProduct; game: SGame; onClose: () => void; onBought: () => void; onFinish: () => void;
}) {
  const cur = useCur();
  const [playerId, setPlayerId] = useState("");
  const [phone, setPhone] = useState("");
  const [sellPrice, setSellPrice] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const requirePlayer = game.require_player_id;

  // بالكمية: الكمية تحدّد ما يُخصم والسعر المقترح؛ والثابتة كميتها 1
  const amount = isAmount(product);
  const [qtyText, setQtyText] = useState(amount ? String(product.qty_min || "") : "1");
  const qty = Number(qtyText.replace(/[^\d]/g, "")) || 0;
  const qtyErr = !amount ? "" : !qty ? "اكتب الكمية"
    : qty < (product.qty_min || 1) ? `أقل كمية ${fmtQty(product.qty_min)}`
    : qty > (product.qty_max || qty) ? `أكبر كمية ${fmtQty(product.qty_max)}` : "";
  const pay = amount ? amountOf(product.price, qty, product.qty_unit) : Number(product.price);
  const suggested = amount ? amountOf(product.recommended_price, qty, product.qty_unit) : Number(product.recommended_price);
  const profit = profitOf(sellPrice.trim() || suggested, pay);

  /**
   * تأكيد الشراء ⇒ الانتقال **فوراً** إلى «طلباتي».
   * لا شاشة تأكيد وسطى: نتيجة الطلب وكودُه إن وُجد يظهران في بطاقته،
   * فشاشةٌ تعرض ما سيراه بعد ثانية ثمّ تطلب ضغطة أخرى للمتابعة عملٌ زائد.
   */
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (qtyErr) { setErr(qtyErr); return; }
    setBusy(true); setErr("");
    try {
      await api.post("/store/buy/", {
        product: product.id, player_id: playerId, customer_phone: phone,
        // فارغ ⇒ يعتمد الخادم سعر التوصية
        dealer_sell_price: sellPrice.trim(),
        ...(amount ? { quantity: qty } : {}),
      });
      onBought();
      onClose();
      onFinish();
    } catch (e: any) {
      setErr(e?.response?.data?.detail || "فشل الشراء");
      setBusy(false);
    }
  }

  return (
    <Sheet title="تأكيد الشراء" onClose={onClose} locked={busy}>
      <form onSubmit={submit}>
        <div className="ag-row" style={{ background: "var(--surface-2)", marginBottom: 4 }}>
          <GameThumb name={game.name} img={game.image_url} />
          <div className="ag-row-main">
            <b>{product.name}</b>
            <span>{game.name}</span>
          </div>
          <div className="ag-row-end">
            <b style={{ color: "var(--primary)" }}>{showPrice(product.price, product)} <small style={{ color: "var(--gold)", fontSize: 12 }}>{cur}</small></b>
            <span>{amount ? "سعر الوحدة" : "سعر الشراء"}</span>
          </div>
        </div>
        {amount && (
          <>
            <label className="ag-label">
              الكمية * <span style={{ fontWeight: 400 }}>— من {fmtQty(product.qty_min)} إلى {fmtQty(product.qty_max)}</span>
            </label>
            <input value={qtyText} inputMode="numeric" dir="ltr" required autoFocus
              onChange={(e) => setQtyText(e.target.value.replace(/[^\d]/g, ""))}
              style={{ textAlign: "center", fontWeight: 800, fontSize: 20, letterSpacing: 1,
                       borderColor: qtyErr && qtyText ? "var(--danger)" : undefined }} />
            <div className="ag-qty-chips">
              {quickQtys(product.qty_min, product.qty_max).map((v) => (
                <button type="button" key={v} className={`ag-chip${qty === v ? " on" : ""}`}
                  onClick={() => setQtyText(String(v))}>{fmtQty(v)}</button>
              ))}
            </div>
            {qtyErr && qtyText && <div style={{ color: "var(--danger)", fontSize: 12.5, marginTop: 4 }}>{qtyErr}</div>}
          </>
        )}
        {game.dealer_note && (
          <div className="ag-note" style={{ display: "flex", gap: 8, alignItems: "flex-start" }}>
            <Icon name="warning" size={16} style={{ flexShrink: 0, marginTop: 3 }} />
            <span><b>ملاحظة:</b> {game.dealer_note}</span>
          </div>
        )}

        {requirePlayer && (
          <>
            <label className="ag-label">معرّف اللاعب (ID) *</label>
            <input value={playerId} onChange={(e) => setPlayerId(e.target.value)} required autoFocus={!amount}
              inputMode="text" dir="ltr" style={{ textAlign: "center", fontWeight: 700, letterSpacing: 1 }}
              placeholder="مثال: 5121234567" />
          </>
        )}
        <label className="ag-label">رقم هاتف الزبون (اختياري)</label>
        <input value={phone} onChange={(e) => setPhone(e.target.value)} inputMode="tel" dir="ltr"
          style={{ textAlign: "center" }} />
        <label className="ag-label">سعر بيعك للزبون (اختياري)</label>
        <input type="number" step="0.01" min="0" inputMode="decimal" value={sellPrice}
          onChange={(e) => setSellPrice(e.target.value)} style={{ textAlign: "center" }}
          placeholder={`فارغ = السعر المقترح ${money(suggested)}`} />

        <div className="ag-card ag-pad" style={{ marginTop: 14, background: "var(--surface-2)", boxShadow: "none" }}>
          {amount && <div className="ag-kv"><span>الكمية</span><b dir="ltr">{fmtQty(qty)}</b></div>}
          <div className="ag-kv"><span>يُخصم من رصيدك</span><b>{money(pay)} {cur}</b></div>
          <div className="ag-kv">
            <span>ربحك من العملية</span>
            <b style={{ color: profit < 0 ? "var(--danger)" : "var(--primary)" }}>{money(profit)} {cur}</b>
          </div>
        </div>

        {err && <div className="ag-msg err">{err}</div>}
        <button className="btn g ag-cta" disabled={busy || !!qtyErr}>
          {busy ? "جارٍ التنفيذ..." : <><Icon name="check" size={18} />تأكيد الشراء</>}
        </button>
      </form>
    </Sheet>
  );
}

/* ═════════════════════════ قائمة الباقات — قراءةٌ فقط ═════════════════════════ */
function PackagesTab() {
  const [rows, setRows] = useState<any[] | null>(null);
  const [cur, setCur] = useState("");
  const [q, setQ] = useState("");
  const [copied, copy] = useCopy();

  useEffect(() => {
    api.get("/store/packages/").then((r) => { setRows(r.data.results); setCur(r.data.currency); })
      .catch(() => setRows([]));
  }, []);

  const needle = q.trim().toLowerCase();
  const shown = (rows || []).filter((r) => !needle || `${r.game} ${r.name} ${r.id}`.toLowerCase().includes(needle));
  const groups = useMemo(() => {
    const m = new Map<string, any[]>();
    for (const r of shown) m.set(r.game, [...(m.get(r.game) || []), r]);
    return [...m.entries()];
  }, [shown]);

  return (
    <div>
      <h1 className="ag-h1">قائمة الباقات <small>عرضٌ فقط</small></h1>
      <div className="ag-note" style={{ marginTop: 0, marginBottom: 14, background: "var(--surface)", color: "var(--muted)", borderColor: "var(--border)" }}>
        <b style={{ color: "var(--text)" }}>رقم الربط</b> هو رقم الباقة عندنا — تضعه في الربط الخارجي:{" "}
        <code dir="ltr" style={{ fontSize: 12 }}>/client/api/newOrder/&#123;الرقم&#125;/params</code>
      </div>
      <div className="ag-search" style={{ marginBottom: 14 }}>
        <span className="ico"><Icon name="search" size={19} /></span>
        <input placeholder="ابحث بالاسم أو الرقم..." value={q} onChange={(e) => setQ(e.target.value)} />
      </div>

      {rows === null ? <Skeleton h={64} n={6} /> : groups.length === 0 ? (
        <Empty icon="tag" text="لا باقات مطابقة" />
      ) : groups.map(([game, items]) => (
        <div key={game} style={{ marginBottom: 18 }}>
          <div className="ag-h2" style={{ margin: "4px 2px 10px", fontSize: 14.5 }}>
            <Icon name="games" size={17} style={{ color: "var(--gold)" }} />{game}
            <span className="more">{items.length}</span>
          </div>
          <div className="ag-list">
            {items.map((r) => (
              <div key={r.id} className="ag-row">
                <button className={`ag-copy${copied === `p${r.id}` ? " done" : ""}`} title="نسخ رقم الربط"
                  onClick={() => copy(String(r.id), `p${r.id}`)} style={{ fontFamily: "monospace", minWidth: 58 }}>
                  {copied === `p${r.id}` ? <Icon name="check" size={13} /> : "#"}{r.id}
                </button>
                <div className="ag-row-main">
                  <b>{r.name}</b>
                  <span>
                    {r.sale_type === "amount"
                      ? `⚖ بالكمية: ${fmtQty(r.qty_min)}–${fmtQty(r.qty_max)} (qty)`
                      : r.require_player_id ? "يطلب معرّف اللاعب" : "كود / شحن مباشر"}
                  </span>
                </div>
                <div className="ag-row-end">
                  <b style={{ color: "var(--primary)" }}>{showPrice(r.buy_price, r)} {symbolOf(cur)}</b>
                  <span>{r.sale_type === "amount" ? "للوحدة" : `مقترح ${money(r.recommended_price)}`}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

/* ═════════════════════════ طلباتي ═════════════════════════ */
function OrdersTab() {
  const cur = useCur();
  const games = useContext(GamesCtx);
  const [rows, setRows] = useState<any[] | null>(null);
  const [counts, setCounts] = useState<Record<string, number>>({});
  const [total, setTotal] = useState("0");
  const [status, setStatus] = useState("all");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [q, setQ] = useState("");
  const [details, setDetails] = useState<any | null>(null);
  const [copied, copy] = useCopy();

  const imgOf = useMemo(() => {
    const m = new Map<string, string>();
    for (const g of games || []) m.set(g.name, g.image_url);
    return m;
  }, [games]);

  function load(silent = false) {
    if (!silent) setRows(null);
    const params: Record<string, string> = { status };
    if (from) params.date_from = from;
    if (to) params.date_to = to;
    if (q.trim()) params.q = q.trim();
    return api.get("/store/orders/", { params }).then((r) => {
      setRows(r.data.results);
      setCounts(r.data.counts || {});
      setTotal(r.data.total_paid || "0");
    }).catch(() => setRows((old) => old ?? []));
  }
  useEffect(() => { load(); }, [status]);

  // ما دام في القائمة طلبٌ ينتظر، نتابعه بهدوء حتى تتبدّل حالته أمام الوكيل
  const waiting = rows?.some((o) => o.status === "pending" || o.status === "processing");
  useEffect(() => {
    if (!waiting) return;
    const id = setInterval(() => load(true), 8000);
    return () => clearInterval(id);
  }, [waiting, status, from, to, q]);

  function exportCsv() {
    if (!rows?.length) return;
    downloadCsv("طلباتي", ["رقم الفيش", "اللعبة", "الباقة", "معرّف اللاعب", "هاتف الزبون", "الشراء", "البيع", "الربح", "الحالة", "الكود", "التاريخ"],
      rows.map((o) => [o.receipt_no, o.game_name, o.quantity > 1 ? `${o.product_name} × ${o.quantity}` : o.product_name, o.player_id, o.customer_phone,
        o.paid_price, o.dealer_sell_price, o.dealer_profit, o.status_label, o.pin_result, o.created_at]));
  }

  return (
    <div>
      <h1 className="ag-h1">طلباتي</h1>

      <form onSubmit={(e) => { e.preventDefault(); load(); }}>
        <div className="ag-dates">
          <DateField label="من" value={from} max={to} onChange={setFrom} />
          <DateField label="إلى" value={to} min={from} onChange={setTo} />
          <button className="ag-round" aria-label="بحث"><Icon name="search" size={21} /></button>
        </div>
        <div style={{ display: "flex", gap: 10, marginTop: 12 }}>
          <div className="ag-search" style={{ flex: 1 }}>
            <span className="ico"><Icon name="search" size={18} /></span>
            <input placeholder="رقم الفيش، معرّف اللاعب، الهاتف..." value={q} onChange={(e) => setQ(e.target.value)} />
          </div>
          {(from || to || q) && (
            <button type="button" className="ag-round ghost" aria-label="إزالة الفلتر"
              onClick={() => { setFrom(""); setTo(""); setQ(""); setTimeout(() => load(), 0); }}>
              <Icon name="x" size={19} />
            </button>
          )}
        </div>
      </form>

      <div className="ag-chips">
        {ST_CHIPS.map((c) => (
          <button key={c.key} className={`ag-chip${status === c.key ? " on" : ""}`} onClick={() => setStatus(c.key)}>
            {c.key !== "all" && <span className="dot" style={{ background: ST_COLOR[c.key] }} />}
            {c.label}
            <span className="n">{counts[c.key] ?? 0}</span>
          </button>
        ))}
      </div>

      <div className="ag-sumbar">
        <span className="ag-total">الإجمالي: {money(total)} {cur}</span>
        {!!rows?.length && (
          <button className="ag-export" onClick={exportCsv}><Icon name="download" size={16} />تصدير Excel</button>
        )}
      </div>

      {rows === null ? <div style={{ marginTop: 14 }}><Skeleton h={150} n={3} /></div> : rows.length === 0 ? (
        <Empty text={status === "all" && !from && !to && !q ? "لا توجد طلبات بعد — ابدأ البيع من الرئيسية" : "لا طلبات مطابقة"} />
      ) : (
        <div className="ag-orders">
          {rows.map((o) => {
            const st = ST_COLOR[o.status] || "var(--muted)";
            const wait = o.status === "pending" || o.status === "processing";
            const profit = Number(o.dealer_profit);
            return (
              <article key={o.id} className="ag-order" style={{ ["--st" as any]: st }} onClick={() => setDetails(o)}>
                <div className="ag-order-top">
                  <GameThumb name={o.game_name} img={imgOf.get(o.game_name)} />
                  <div className="ag-order-title">
                    <b>{o.product_name}{o.quantity > 1 && <span className="ag-qty-x"> × {fmtQty(o.quantity)}</span>}</b>
                    <span>{o.game_name}</span>
                  </div>
                  <div className="ag-order-amt">
                    <b>{money(o.paid_price)}<small>{cur}</small></b>
                    <span style={{ color: profit < 0 ? "var(--danger)" : "var(--primary)" }}>
                      ربح {profit > 0 ? "+" : ""}{money(o.dealer_profit)}
                    </span>
                  </div>
                </div>

                <div className="ag-order-meta">
                  <div className="ag-meta"><Icon name="hash" size={14} /><b>{o.receipt_no}</b></div>
                  <div className="ag-meta"><Icon name="user" size={14} /><b>{o.player_id || "—"}</b></div>
                  <div className="ag-meta"><Icon name="phone" size={14} /><b>{o.customer_phone || "—"}</b></div>
                  <div className="ag-meta"><Icon name="tag" size={14} /><span>بيع</span><b>{money(o.dealer_sell_price)}</b></div>
                </div>

                {o.pin_result && (
                  <div className="ag-pin" onClick={(e) => e.stopPropagation()}>
                    <code>{o.pin_result}</code>
                    <button className={`ag-copy${copied === `o${o.id}` ? " done" : ""}`}
                      onClick={() => copy(o.pin_result, `o${o.id}`)}>
                      <Icon name={copied === `o${o.id}` ? "check" : "copy"} size={13} />
                      {copied === `o${o.id}` ? "نُسخ" : "نسخ"}
                    </button>
                  </div>
                )}
                {o.dealer_note && <div className="ag-note"><b>ملاحظة الإدارة:</b> {o.dealer_note}</div>}

                <div className="ag-order-foot">
                  <span className="ag-status">
                    {wait ? <span className={`stspin${o.status === "processing" ? " proc" : ""}`} />
                      : <Icon name={o.status === "success" ? "check" : "x"} size={14} />}
                    {o.status_label}
                  </span>
                  <span className="ag-when">{o.created_at}</span>
                </div>
              </article>
            );
          })}
        </div>
      )}
      {details && <OrderDetails order={details} img={imgOf.get(details.game_name)} onClose={() => setDetails(null)} />}
    </div>
  );
}

/* تفاصيل الطلب للوكيل — بياناته هو فقط: زبونه وأسعاره وحالة طلبه. */
function OrderDetails({ order: o, img, onClose }: { order: any; img?: string; onClose: () => void }) {
  return (
    <Sheet title={<>تفاصيل الطلب <span style={{ color: "var(--muted)", fontWeight: 600, fontSize: 13 }} dir="ltr">#{o.receipt_no}</span></>}
      onClose={onClose}>
      <OrderBody order={o} img={img} />
      <button className="btn ag-cta" onClick={onClose}>إغلاق</button>
    </Sheet>
  );
}

/** ما في الطلب: الباقة وحالتها، الكود، الأسعار — في تفاصيل الطلب وتفاصيل حركة المحفظة */
function OrderBody({ order: o, img }: { order: any; img?: string }) {
  const cur = useCur();
  const [copied, copy] = useCopy();
  const st = ST_COLOR[o.status] || "var(--muted)";
  return (
    <>
      <div className="ag-row" style={{ background: "var(--surface-2)", ["--st" as any]: st }}>
        <GameThumb name={o.game_name} img={img} />
        <div className="ag-row-main">
          <b>{o.product_name}{o.quantity > 1 && <span className="ag-qty-x"> × {fmtQty(o.quantity)}</span>}</b>
          <span>{o.game_name}</span>
        </div>
        <span className="ag-status">{o.status_label}</span>
      </div>

      {o.pin_result ? (
        <div className="ag-pin" style={{ marginTop: 12, padding: "12px 12px" }}>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontSize: 11.5, color: "var(--muted)", marginBottom: 2 }}>الكود / PIN</div>
            <code style={{ fontSize: 16 }}>{o.pin_result}</code>
          </div>
          <button className={`ag-copy${copied === "pin" ? " done" : ""}`} onClick={() => copy(o.pin_result, "pin")}>
            <Icon name={copied === "pin" ? "check" : "copy"} size={13} />{copied === "pin" ? "نُسخ" : "نسخ"}
          </button>
        </div>
      ) : o.status === "success" ? (
        <div className="ag-msg ok"><Icon name="check" size={15} /> شُحن مباشرةً إلى حساب اللاعب</div>
      ) : null}

      <div style={{ marginTop: 10 }}>
        <div className="ag-kv"><span>معرّف اللاعب</span><b dir="ltr">{o.player_id || "—"}</b></div>
        <div className="ag-kv"><span>هاتف الزبون</span><b dir="ltr">{o.customer_phone || "—"}</b></div>
        <div className="ag-kv"><span>سعر الشراء</span><b>{money(o.paid_price)} {cur}</b></div>
        <div className="ag-kv"><span>سعر البيع لزبونك</span><b>{money(o.dealer_sell_price)} {cur}</b></div>
        <div className="ag-kv"><span>ربحك</span>
          <b style={{ color: Number(o.dealer_profit) < 0 ? "var(--danger)" : "var(--primary)" }}>{money(o.dealer_profit)} {cur}</b>
        </div>
        <div className="ag-kv"><span>رصيدك قبل ← بعد</span><b dir="ltr">{money(o.balance_before)} → {money(o.balance_after)}</b></div>
        <div className="ag-kv"><span>التاريخ</span><b dir="ltr">{o.created_at}</b></div>
      </div>
      {o.dealer_note && <div className="ag-note"><b>ملاحظة الإدارة:</b> {o.dealer_note}</div>}
      {o.provider_note && (
        <div className="ag-note" style={{ background: "var(--surface-2)", color: "var(--muted)", borderColor: "var(--border)" }}>
          <b style={{ color: "var(--text)" }}>ملاحظة:</b> {o.provider_note}
        </div>
      )}
    </>
  );
}

/* ═════════════════════════ تقاريري ═════════════════════════ */
function ReportsTab() {
  const cur = useCur();
  const [data, setData] = useState<any>(null);
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [inclCancelled, setInclCancelled] = useState(false);

  function load(f = from, t = to, inc = inclCancelled) {
    setData(null);
    const params: any = {};
    if (f) params.date_from = f;
    if (t) params.date_to = t;
    if (inc) params.include_cancelled = 1;
    api.get("/store/report/", { params }).then((r) => setData(r.data)).catch(() => setData({ results: [] }));
  }
  useEffect(() => { load(); }, []);

  const t = data?.totals;
  return (
    <div>
      <h1 className="ag-h1">تقاريري</h1>
      <form onSubmit={(e) => { e.preventDefault(); load(); }}>
        <div className="ag-dates">
          <DateField label="من" value={from} max={to} onChange={setFrom} />
          <DateField label="إلى" value={to} min={from} onChange={setTo} />
          <button className="ag-round" aria-label="تصفية"><Icon name="filter" size={19} /></button>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginTop: 12, flexWrap: "wrap" }}>
          <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13.5, color: "var(--muted)", fontWeight: 600 }}>
            <input type="checkbox" checked={inclCancelled}
              onChange={(e) => { setInclCancelled(e.target.checked); load(from, to, e.target.checked); }} />
            تضمين الملغاة
          </label>
          {(from || to || inclCancelled) && (
            <button type="button" className="btn" style={{ height: 34, marginInlineStart: "auto" }}
              onClick={() => { setFrom(""); setTo(""); setInclCancelled(false); load("", "", false); }}>
              <Icon name="x" size={14} />إزالة الفلتر
            </button>
          )}
        </div>
      </form>

      <div className="ag-tiles" style={{ marginTop: 16 }}>
        <div className="ag-tile t-blue">
          <span className="ic"><Icon name="receipt" size={18} /></span>
          <div><div className="v">{t ? t.count : "—"}</div><div className="l">عدد الطلبات</div></div>
        </div>
        <div className="ag-tile t-coral">
          <span className="ic"><Icon name="cart" size={18} /></span>
          <div><div className="v">{t ? money(t.cost) : "—"}<small>{cur}</small></div><div className="l">مشترياتي</div></div>
        </div>
        <div className="ag-tile t-violet">
          <span className="ic"><Icon name="tag" size={18} /></span>
          <div><div className="v">{t ? money(t.sell) : "—"}<small>{cur}</small></div><div className="l">مبيعاتي</div></div>
        </div>
        <div className="ag-tile t-green">
          <span className="ic"><Icon name="dollar" size={18} /></span>
          <div><div className="v">{t ? money(t.profit) : "—"}<small>{cur}</small></div><div className="l">أرباحي</div></div>
        </div>
      </div>

      <div className="ag-h2">
        <Icon name="chart" size={18} style={{ color: "var(--primary)" }} />حسب الباقة
        {data?.products ? <span className="more">{data.products} باقة</span> : null}
      </div>
      {data === null ? <Skeleton h={70} /> : !data.results?.length ? (
        <Empty icon="chart" text="لا توجد بيانات في هذه الفترة" />
      ) : (
        <div className="ag-list">
          {data.results.map((r: any, i: number) => (
            <div key={i} className="ag-row" style={{ alignItems: "stretch", flexDirection: "column", gap: 10 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <div className="ag-row-main"><b>{r.product}</b><span>{r.game}</span></div>
                <span className="ag-pillst" style={{ background: "color-mix(in srgb, var(--info) 12%, transparent)", color: "var(--info)" }}>× {r.count}</span>
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 8, textAlign: "center" }}>
                <MiniVal label="الشراء" value={money(r.cost)} color="var(--danger)" />
                <MiniVal label="المبيعات" value={money(r.sell)} color="var(--violet)" />
                <MiniVal label="الربح" value={money(r.profit)} color="var(--primary)" />
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
function MiniVal({ label, value, color }: { label: string; value: string; color: string }) {
  return (
    <div style={{ background: "var(--surface-2)", borderRadius: 12, padding: "7px 4px" }}>
      <div style={{ fontSize: 11, color: "var(--muted)" }}>{label}</div>
      <div style={{ fontSize: 14, fontWeight: 800, color, fontVariantNumeric: "tabular-nums" }}>{value}</div>
    </div>
  );
}

/* ═════════════════════════ محفظتي ═════════════════════════ */
function WalletTab({ summary, onTopUp }: { summary: Summary | null; onTopUp: () => void }) {
  const [data, setData] = useState<any>(null);
  const [list, setList] = useState<any[] | null>(null);
  const [kind, setKind] = useState("all");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [open, setOpen] = useState<any | null>(null);

  function load(k = kind, f = from, t = to) {
    setList(null);
    const params: Record<string, string> = { type: k };
    if (f) params.date_from = f;
    if (t) params.date_to = t;
    api.get("/store/wallet/", { params })
      .then((r) => { setData(r.data); setList(r.data.results || []); })
      .catch(() => { setData((d: any) => d ?? { results: [] }); setList([]); });
  }
  useEffect(() => { load(); }, []);
  const counts: Record<string, number> = data?.counts || {};
  const sym = symbolOf(data?.currency || summary?.currency || "");

  return (
    <div>
      <h1 className="ag-h1">المحفظة</h1>
      <div className="ag-tiles">
        <div className="ag-tile t-green">
          <span className="ic"><Icon name="wallet" size={18} /></span>
          <div>
            <div className="v" style={Number(data?.balance) < 0 ? { color: "var(--danger)" } : undefined}>
              {data?.balance !== undefined ? money(data.balance) : "—"}<small>{sym}</small>
            </div>
            <div className="l">رصيدك الحالي</div>
          </div>
        </div>
        <div className="ag-tile t-violet">
          <span className="ic"><Icon name="dollar" size={18} /></span>
          <div><div className="v">{data?.available !== undefined ? money(data.available) : "—"}<small>{sym}</small></div><div className="l">المتاح للصرف</div></div>
        </div>
        <div className="ag-tile t-blue">
          <span className="ic"><Icon name="card" size={18} /></span>
          <div><div className="v">{data?.credit_limit !== undefined ? money(Math.abs(Number(data.credit_limit))) : "—"}<small>{sym}</small></div><div className="l">الحدّ الائتماني</div></div>
        </div>
        <div className="ag-tile t-gold">
          <span className="ic"><Icon name="chart" size={18} /></span>
          <div><div className="v">{summary ? money(summary.profit) : "—"}<small>{sym}</small></div><div className="l">أرباحي</div></div>
        </div>
      </div>

      <button className="btn g ag-cta" style={{ marginTop: 14 }} onClick={onTopUp}>
        <Icon name="plusCircle" size={19} />شحن رصيد
      </button>

      <div className="ag-h2"><Icon name="receipt" size={18} style={{ color: "var(--primary)" }} />كشف الحركات</div>
      <form onSubmit={(e) => { e.preventDefault(); load(); }}>
        <div className="ag-dates">
          <DateField label="من" value={from} max={to} onChange={setFrom} />
          <DateField label="إلى" value={to} min={from} onChange={setTo} />
          {from || to ? (
            <button type="button" className="ag-round ghost" aria-label="إزالة الفلتر"
              onClick={() => { setFrom(""); setTo(""); load(kind, "", ""); }}>
              <Icon name="x" size={19} />
            </button>
          ) : (
            <button className="ag-round" aria-label="بحث"><Icon name="search" size={21} /></button>
          )}
        </div>
      </form>

      <div className="ag-chips">
        {[{ key: "all", label: "الكل" }, ...(data?.types || [])]
          .filter((c: any) => c.key === "all" || kind === c.key || counts[c.key])
          .map((c: any) => (
            <button key={c.key} className={`ag-chip${kind === c.key ? " on" : ""}`}
              onClick={() => { setKind(c.key); load(c.key); }}>
              {c.key !== "all" && <span className="dot" style={{ background: txnTone(c.key) }} />}
              {c.label}<span className="n">{counts[c.key] || 0}</span>
            </button>
          ))}
      </div>

      {list === null ? <div style={{ marginTop: 12 }}><Skeleton h={66} /></div> : !list.length ? (
        <Empty icon="wallet" text={kind === "all" && !from && !to ? "لا توجد حركات بعد" : "لا حركات مطابقة"} />
      ) : (
        <div className="ag-list" style={{ marginTop: 12 }}>
          {list.map((t: any) => {
            const inflow = Number(t.amount) >= 0;
            const tone = inflow ? "var(--ok)" : "var(--danger)";
            return (
              <div key={t.id} className="ag-row ag-row-click" onClick={() => setOpen(t)}>
                <span className="ag-row-ico" style={{ background: `color-mix(in srgb, ${tone} 10%, transparent)`, color: tone }}>
                  <Icon name={inflow ? "arrowDown" : "arrowUp"} size={19} />
                </span>
                <div className="ag-row-main">
                  <b>{t.type_label}</b>
                  <span>{t.order ? `${t.order.game_name} · ${t.order.product_name}` : t.note || t.created_at}</span>
                </div>
                <div className="ag-row-end">
                  <b style={{ color: tone }} dir="ltr">{inflow ? "+" : ""}{money(t.amount)}</b>
                  <span dir="ltr">{t.created_at}</span>
                </div>
                <button className="ag-eye" aria-label="التفاصيل" title="التفاصيل"
                  onClick={(e) => { e.stopPropagation(); setOpen(t); }}>
                  <Icon name="eye" size={17} />
                </button>
              </div>
            );
          })}
        </div>
      )}

      {open && <TxnDetails txn={open} cur={sym} onClose={() => setOpen(null)} />}
    </div>
  );
}

/** لون نوع الحركة: داخلٌ أخضر، خارجٌ أحمر، والتسوية محايدة */
function txnTone(type: string) {
  if (type === "topup" || type === "refund" || type === "manual_credit") return "var(--ok)";
  if (type === "order_debit" || type === "manual_debit") return "var(--danger)";
  return "var(--info)";
}

function TxnDetails({ txn: t, cur, onClose }: { txn: any; cur: string; onClose: () => void }) {
  const games = useContext(GamesCtx);
  const inflow = Number(t.amount) >= 0;
  const img = t.order ? games?.find((g) => g.name === t.order.game_name)?.image_url : undefined;
  return (
    <Sheet title={<>تفاصيل العملية <span style={{ color: "var(--muted)", fontWeight: 600, fontSize: 13 }} dir="ltr">#{t.id}</span></>}
      onClose={onClose}>
      <div style={{ textAlign: "center", padding: "6px 0 12px" }}>
        <div style={{ fontSize: 13, color: "var(--muted)", fontWeight: 700 }}>{t.type_label}</div>
        <div dir="ltr" style={{ fontSize: 30, fontWeight: 800, color: inflow ? "var(--ok)" : "var(--danger)",
                               fontVariantNumeric: "tabular-nums" }}>
          {inflow ? "+" : ""}{money(t.amount)} <small style={{ fontSize: 15, color: "var(--gold)" }}>{cur}</small>
        </div>
      </div>
      <div className="ag-kv"><span>الرصيد قبل</span><b dir="ltr">{money(t.balance_before)} {cur}</b></div>
      <div className="ag-kv"><span>الرصيد بعد</span><b dir="ltr">{money(t.balance_after)} {cur}</b></div>
      <div className="ag-kv"><span>التاريخ</span><b dir="ltr">{t.created_at}</b></div>
      {t.order && <div className="ag-kv"><span>رقم الفيش</span><b dir="ltr">#{t.order.receipt_no}</b></div>}
      {t.note && <div className="ag-note" style={{ background: "var(--surface-2)", color: "var(--text)", borderColor: "var(--border)" }}>
        <b>ملاحظة:</b> {t.note}
      </div>}
      {t.order && (
        <>
          <div className="ag-h2" style={{ margin: "18px 2px 10px" }}>
            <Icon name="receipt" size={17} style={{ color: "var(--primary)" }} />الطلب
          </div>
          <OrderBody order={t.order} img={img} />
        </>
      )}
      <button className="btn ag-cta" onClick={onClose}>إغلاق</button>
    </Sheet>
  );
}

/* ═════════════════════════ حسابي · الربط الخارجي ═════════════════════════
   الربط الخارجي إعدادٌ يُضبط مرّةً ثم يُنسى — فمكانه هنا، ورابط /store/api
   يبقى صالحاً ويفتح على قسمه مباشرةً. */
function SettingsTab({ initial = "account" }: { initial?: "account" | "api" }) {
  const [pane, setPane] = useState<"account" | "api">(initial);
  useEffect(() => { setPane(initial); }, [initial]);

  return (
    <div>
      <h1 className="ag-h1">{pane === "api" ? "الربط الخارجي" : "حسابي"}</h1>
      <div className="ag-seg">
        <button className={pane === "account" ? "on" : ""} onClick={() => setPane("account")}>
          <Icon name="user" size={15} />الحساب
        </button>
        <button className={pane === "api" ? "on" : ""} onClick={() => setPane("api")}>
          <Icon name="api" size={15} />الربط الخارجي (API)
        </button>
      </div>
      {pane === "account" ? <AccountPane /> : <ApiDocs />}
    </div>
  );
}

function AccountPane() {
  const { user, logout } = useAuth();
  const [cur, setCur] = useState("");
  const [nw, setNw] = useState("");
  const [nw2, setNw2] = useState("");
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [copied, copy] = useCopy();

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setMsg(null);
    if (nw !== nw2) { setMsg({ ok: false, text: "كلمتا السر الجديدتان غير متطابقتين" }); return; }
    setBusy(true);
    try {
      await api.post("/store/change-password/", { current_password: cur, new_password: nw });
      setMsg({ ok: true, text: "تم تغيير كلمة السر بنجاح" });
      setCur(""); setNw(""); setNw2("");
    } catch (e: any) {
      setMsg({ ok: false, text: e?.response?.data?.detail || "فشل تغيير كلمة السر" });
    } finally { setBusy(false); }
  }

  return (
    <div style={{ display: "grid", gap: 14, gridTemplateColumns: "repeat(auto-fit, minmax(290px, 1fr))" }}>
      <div className="ag-card ag-pad">
        <div className="ag-profile">
          <span className="ag-avatar">{(user?.name || "?").trim().charAt(0)}</span>
          <div style={{ minWidth: 0 }}>
            <div style={{ fontWeight: 800, fontSize: 17 }}>{user?.name || "—"}</div>
            <div style={{ fontSize: 12.5, color: "var(--muted)" }}>{user?.role_label || "وكيل"} · {user?.tenant?.name}</div>
          </div>
        </div>
        <div style={{ marginTop: 14 }}>
          <div className="ag-kv">
            <span>رقم الدخول</span>
            <b style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <span dir="ltr" style={{ fontFamily: "monospace" }}>{user?.login_id || "—"}</span>
              {user?.login_id && (
                <button className={`ag-copy${copied === "id" ? " done" : ""}`} onClick={() => copy(user.login_id, "id")}>
                  <Icon name={copied === "id" ? "check" : "copy"} size={13} />
                </button>
              )}
            </b>
          </div>
          <div className="ag-kv"><span>المتجر</span><b>{user?.tenant?.name || "—"}</b></div>
        </div>
        <button className="btn" style={{ width: "100%", marginTop: 14, color: "var(--danger)" }} onClick={logout}>
          <Icon name="logout" size={16} />خروج آمن
        </button>
      </div>

      <form onSubmit={submit} className="ag-card ag-pad">
        <div style={{ fontWeight: 800, fontSize: 16, display: "flex", alignItems: "center", gap: 8, color: "var(--gold)" }}>
          <Icon name="lock" size={18} />تغيير كلمة السر
        </div>
        <label className="ag-label">كلمة السر الحالية</label>
        <input type="password" autoComplete="current-password" value={cur} onChange={(e) => setCur(e.target.value)} />
        <label className="ag-label">كلمة السر الجديدة</label>
        <input type="password" autoComplete="new-password" value={nw} onChange={(e) => setNw(e.target.value)} />
        <label className="ag-label">تأكيد كلمة السر الجديدة</label>
        <input type="password" autoComplete="new-password" value={nw2} onChange={(e) => setNw2(e.target.value)} />
        {msg && <div className={`ag-msg ${msg.ok ? "ok" : "err"}`}>{msg.text}</div>}
        <button className="btn ag-cta" disabled={busy || !cur || !nw}
          style={{ background: "var(--gold)", color: "var(--on-gold)" }}>
          {busy ? "جارٍ..." : "حفظ كلمة السر"}
        </button>
      </form>
    </div>
  );
}

/* ═════════════════════════ موبايل (شحن الخطوط) ═════════════════════════ */
interface KPkg {
  id: number; znet_id: string; name: string; details: string;
  days: number; gb: number; minutes: number; kind: string; price: string; is_offer?: boolean;
}
interface KCat { id: number; line_type: string; name: string; logo_url?: string; packages: KPkg[] }

// الشركات بألوان علاماتها — تلوّن شريط الشركة وحافّة البطاقات
const OPS: Record<string, { label: string; color: string; ink: string }> = {
  Turkcell: { label: "Turkcell", color: "#ffc900", ink: "#1f2f6b" },
  Vodafone: { label: "Vodafone", color: "#e60000", ink: "#fff" },
  Avea: { label: "Türk Telekom", color: "#1d6fd6", ink: "#fff" },
  Callback: { label: "دولي", color: "#8b5cf6", ink: "#fff" },
};

/** 5XXXXXXXXX ⇐ 5XX XXX XX XX للعرض */
const fmtGsm = (d: string) => [d.slice(0, 3), d.slice(3, 6), d.slice(6, 8), d.slice(8, 10)].filter(Boolean).join(" ");

/** متغيّر CSS للون الشركة على عنصر. */
const opVars = (color?: string, ink?: string) =>
  (color ? { "--opc": color, ...(ink ? { "--opi": ink } : {}) } : {}) as React.CSSProperties;

function MobileTab() {
  const sym = useCur();
  const [gsm, setGsm] = useState("");
  const [operator, setOperator] = useState("");
  const [cats, setCats] = useState<KCat[]>([]);
  const [activeCat, setActiveCat] = useState<number | "offers" | null>(null);
  const [offers, setOffers] = useState<KPkg[] | null>(null);
  const [busy, setBusy] = useState<"" | "detect" | "offers" | "buy">("");
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [confirm, setConfirm] = useState<KPkg | null>(null);

  const digits = gsm;
  const op = OPS[operator];

  function reset() {
    setOperator(""); setCats([]); setActiveCat(null); setOffers(null); setMsg(null);
  }

  async function detect() {
    if (digits.length < 10) return;
    setBusy("detect"); setMsg(null); setOffers(null);
    try {
      const d = await api.post("/kontor/store/detect/", { gsm: digits });
      setOperator(d.data.operator);
      const p = await api.get(`/kontor/store/packages/?operator=${d.data.operator}`);
      setCats(p.data.categories);
      setActiveCat(p.data.categories[0]?.id ?? null);
    } catch (e: any) {
      reset();
      setMsg({ ok: false, text: e?.response?.data?.detail || "تعذّر كشف الشركة" });
    } finally { setBusy(""); }
  }

  async function showOffers() {
    if (offers) { setActiveCat("offers"); return; }
    setBusy("offers"); setMsg(null);
    try {
      const r = await api.post("/kontor/store/offers/", { gsm: digits, operator });
      setOffers(r.data.offers);
      setActiveCat("offers");
    } catch (e: any) {
      setMsg({ ok: false, text: e?.response?.data?.detail || "تعذّر جلب العروض" });
    } finally { setBusy(""); }
  }

  async function buy(pkg: KPkg) {
    setBusy("buy"); setMsg(null);
    try {
      const r = await api.post("/kontor/store/buy/", { package: pkg.id, gsm: digits });
      const st = r.data.status;
      setMsg({ ok: st !== "failed" && st !== "refunded",
               text: st === "refunded" ? `فشل الشحن وأُعيد المبلغ: ${r.data.note || ""}`
                   : st === "processing" ? `✓ أُرسل شحن «${pkg.name}» إلى ${fmtGsm(digits)} — قيد التنفيذ`
                   : `الحالة: ${r.data.status_label || st}` });
    } catch (e: any) {
      setMsg({ ok: false, text: e?.response?.data?.detail || "تعذّر تنفيذ الطلب" });
    } finally { setBusy(""); setConfirm(null); }
  }

  const list = activeCat === "offers" ? (offers || []) : (cats.find((c) => c.id === activeCat)?.packages || []);

  return (
    <div>
      <h1 className="ag-h1">موبايل <small>شحن الخطوط التركية</small></h1>

      {/* بطاقة الرقم */}
      <div className={`km-num${op ? " has-op" : ""}`} style={opVars(op?.color)}>
        <span className="km-num-ico"><Icon name="phone" size={21} /></span>
        <div className="km-num-field">
          <span className="km-cc" dir="ltr">+90</span>
          <input inputMode="numeric" dir="ltr" value={fmtGsm(digits)} autoComplete="tel"
            onChange={(e) => {
              setGsm(e.target.value.replace(/\D/g, "").replace(/^(90|0)(?=5)/, "").slice(0, 10));
              if (operator) reset();
            }}
            onKeyDown={(e) => { if (e.key === "Enter") detect(); }}
            placeholder="5XX XXX XX XX" />
          {digits && (
            <button type="button" className="km-clear" onClick={() => { setGsm(""); reset(); }} aria-label="مسح">
              <Icon name="x" size={14} />
            </button>
          )}
        </div>
        <button type="button" className="km-go" disabled={digits.length < 10 || busy === "detect"} onClick={detect}>
          {busy === "detect" ? <span className="km-spin" /> : <>كشف <Icon name="search" size={16} /></>}
        </button>
      </div>

      {op && (
        <div className="km-op" style={opVars(op.color, op.ink)}>
          <span className="km-op-badge">{operator === "Callback" ? "🌐" : op.label[0]}</span>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div className="km-op-name">{op.label}</div>
            <div className="km-op-num" dir="ltr">+90 {fmtGsm(digits)}</div>
          </div>
          <button type="button" className={`km-offers${activeCat === "offers" ? " on" : ""}`}
            disabled={busy === "offers"} onClick={showOffers}>
            {busy === "offers" ? <span className="km-spin" /> : <Icon name="bolt" size={15} />}
            عروض الرقم
          </button>
        </div>
      )}

      {msg && <div className={`ag-msg ${msg.ok ? "ok" : "err"}`} style={{ marginBottom: 12 }}>{msg.text}</div>}

      {cats.length > 0 && (
        <div className="ag-chips" style={{ marginBottom: 14 }}>
          {offers && (
            <button className={`ag-chip km-chip-offer${activeCat === "offers" ? " on" : ""}`} onClick={() => setActiveCat("offers")}>
              <Icon name="bolt" size={14} /> عروض خاصة <span className="n">{offers.length}</span>
            </button>
          )}
          {cats.map((c) => (
            <button key={c.id} className={`ag-chip${activeCat === c.id ? " on" : ""}`} onClick={() => setActiveCat(c.id)}>
              {c.logo_url && <img src={c.logo_url} alt="" className="km-chip-logo" />}
              {c.name} <span className="n">{c.packages.length}</span>
            </button>
          ))}
        </div>
      )}

      {activeCat !== null && (list.length === 0
        ? <Empty icon="tag" text={activeCat === "offers" ? "لا عروض خاصة لهذا الرقم" : "لا باقات في هذه الفئة"} />
        : (
          <div className="km-grid">
            {list.map((p) => <PkgCard key={p.id} p={p} sym={sym} color={op?.color} onPick={() => setConfirm(p)} />)}
          </div>
        ))}

      {!operator && !msg && (
        <div className="km-hint">
          <span className="km-hint-ico"><Icon name="phone" size={26} /></span>
          <div>اكتب رقم الخط واضغط «كشف» — نتعرّف على الشركة ونعرض باقاتها بأسعارك.</div>
        </div>
      )}

      {confirm && (
        <Sheet title="تأكيد الشحن" onClose={() => setConfirm(null)} locked={busy === "buy"}>
          <div className="km-confirm" style={opVars(op?.color)}>
            <div className="km-confirm-row"><span>الرقم</span><b dir="ltr">+90 {fmtGsm(digits)}</b></div>
            <div className="km-confirm-row"><span>الشركة</span><b>{op?.label}</b></div>
            <div className="km-confirm-row"><span>الباقة</span><b>{confirm.name}</b></div>
            {confirm.details && <div className="km-confirm-row"><span>التفاصيل</span><b>{confirm.details}</b></div>}
            <Specs p={confirm} />
            <div className="km-confirm-price"><span>المبلغ</span><b>{confirm.price} <small>{sym}</small></b></div>
          </div>
          <button className="btn g ag-cta" disabled={busy === "buy"} onClick={() => buy(confirm)}>
            {busy === "buy" ? "جارٍ الإرسال..." : "تأكيد الشحن"}
          </button>
        </Sheet>
      )}
    </div>
  );
}

/** شرائح المواصفات: الإنترنت والدقائق والأيام إن عُرفت. */
function Specs({ p }: { p: KPkg }) {
  const bits: [string, string][] = [];
  if (p.gb) bits.push(["🌐", `${p.gb} GB`]);
  if (p.minutes) bits.push(["📞", `${p.minutes} دقيقة`]);
  if (p.days) bits.push(["📅", `${p.days} يوم`]);
  if (!bits.length) return null;
  return (
    <div className="km-specs">
      {bits.map(([i, t]) => <span key={t}><i>{i}</i>{t}</span>)}
    </div>
  );
}

/** بطاقة باقة — الضغط عليها كلّها يفتح تأكيد الشحن. */
function PkgCard({ p, sym, color, onPick }: { p: KPkg; sym: string; color?: string; onPick: () => void }) {
  const offer = p.is_offer || p.kind === "offer";
  return (
    <button type="button" className={`km-card${offer ? " offer" : ""}`} onClick={onPick} style={opVars(color)}>
      {offer && <span className="km-ribbon">عرض</span>}
      <div className="km-card-body">
        <div className="km-card-name">{p.name}</div>
        <Specs p={p} />
        {p.details && <div className="km-card-det">{p.details}</div>}
      </div>
      <div className="km-card-price">
        <b>{p.price}</b><small>{sym}</small>
      </div>
    </button>
  );
}
