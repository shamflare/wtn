import { useEffect, useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import { api } from "../api";
import Icon from "../components/Icon";
import PublicShell, { useStorefront } from "../components/PublicShell";

/**
 * واجهة المتجر للزائر: كل الألعاب والتطبيقات بصورها، بلا أسعارٍ ولا باقات —
 * الأسعار تخصّ كل وكيلٍ بمجموعته. والضغط على أيّ لعبة يقود إلى الدخول.
 */
export default function PublicHome() {
  return (
    <PublicShell>
      <Games />
    </PublicShell>
  );
}

interface PGame { id: number; name: string; image_url: string; description: string }

function hueOf(name: string) {
  let h = 0;
  for (const ch of name || "?") h = (h * 31 + ch.charCodeAt(0)) % 360;
  return `linear-gradient(145deg, hsl(${h} 65% 42%), hsl(${(h + 40) % 360} 60% 22%))`;
}

function Games() {
  const store = useStorefront();
  const nav = useNavigate();
  const [games, setGames] = useState<PGame[] | null>(null);
  const [q, setQ] = useState("");

  useEffect(() => {
    api.get("/storefront/games/").then((r) => setGames(r.data.games)).catch(() => setGames([]));
  }, []);

  // باب المنصّة العام (لا متجر لهذا العنوان) ⇐ الدخول مباشرةً كما كان
  if (store === null) return <Navigate to="/login" replace />;

  const term = q.trim().toLowerCase();
  const shown = (games || []).filter((g) => !term || g.name.toLowerCase().includes(term));
  const goLogin = () => nav("/login", { state: { fromGame: true } });

  return (
    <>
      <section className="ag-pub-hero">
        <h1>{store?.name || "متجر الشحن"}</h1>
        <p>{store?.tagline || "شحن الألعاب والتطبيقات فوراً — سجّل دخولك لترى الأسعار وتبدأ البيع"}</p>
        <div className="ag-pub-hero-actions">
          <button className="btn g" onClick={goLogin}>تسجيل الدخول</button>
          <button className="btn" onClick={() => nav("/register")}>إنشاء حساب وكيل</button>
        </div>
      </section>

      <div className="ag-h2">
        <Icon name="games" size={19} style={{ color: "var(--primary)" }} />الألعاب والتطبيقات
        {games && <span className="more">{games.length} قسم</span>}
      </div>
      <div className="ag-search" style={{ marginBottom: 14 }}>
        <span className="ico"><Icon name="search" size={18} /></span>
        <input placeholder="ابحث عن لعبة أو تطبيق..." value={q} onChange={(e) => setQ(e.target.value)} />
      </div>

      {games === null ? (
        <div className="ag-games">
          {Array.from({ length: 6 }, (_, i) => <div key={i} className="ag-skel" style={{ height: 150 }} />)}
        </div>
      ) : shown.length === 0 ? (
        <div className="ag-empty">{games.length ? "لا نتائج مطابقة" : "لا ألعاب معروضة بعد"}</div>
      ) : (
        <div className="ag-games">
          {shown.map((g) => (
            <button key={g.id} className="ag-game" onClick={goLogin} title="سجّل دخولك لترى الباقات والأسعار">
              {g.image_url
                ? <img className="ag-game-img" src={g.image_url} alt="" loading="lazy" />
                : <span className="ag-game-ph" style={{ background: hueOf(g.name) }}>{g.name.trim().charAt(0)}</span>}
              <div className="ag-game-name">{g.name}</div>
              <div className="ag-game-foot">
                <span className="ag-buy-pill"><Icon name="lock" size={13} />عرض الباقات</span>
              </div>
            </button>
          ))}
        </div>
      )}
    </>
  );
}
