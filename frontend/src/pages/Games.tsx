import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, type Game } from "../api";
import Icon from "../components/Icon";

export default function Games() {
  const [games, setGames] = useState<Game[]>([]);
  const [loading, setLoading] = useState(true);
  const nav = useNavigate();

  useEffect(() => {
    api.get("/catalog/games/").then((r) => setGames(r.data)).finally(() => setLoading(false));
  }, []);

  if (loading) return <div style={{ padding: 30 }}>جارٍ التحميل...</div>;

  return (
    <div style={{ padding: 16 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 8 }}>
        <h2 style={{ fontSize: 20, color: "var(--primary-dark)" }}>قائمة الألعاب</h2>
        <button className="btn g"><Icon name="plus" size={15} style={{ marginInlineEnd: 5 }} />إضافة لعبة</button>
        <span style={{ color: "var(--muted)", fontSize: 14 }}>({games.length} لعبة)</span>
      </div>
      <div style={hint}>
        ** يمكنك سحب الألعاب وإفلاتها لترتيب طريقة ظهورها لوكلائك.
      </div>

      {/* شبكة بطاقات الألعاب — الضغط ينقل لصفحة التفاصيل */}
      <div style={grid}>
        {games.map((g) => (
          <div key={g.id} style={card}>
            <div style={thumb} onClick={() => nav(`/oyunpin/${g.id}`)}>
              {g.image_url
                ? <img src={g.image_url} alt="" style={{ width: 96, height: 96, objectFit: "cover", borderRadius: 14,
                                                       boxShadow: "0 4px 12px rgba(0,0,0,.15)" }} />
                : "🎮"}
            </div>
            <div
              style={{ fontWeight: 700, marginTop: 10, cursor: "pointer" }}
              onClick={() => nav(`/oyunpin/${g.id}`)}
            >
              {g.name}
            </div>
            <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 4 }}>
              تاريخ الإنشاء: {g.created_at}
            </div>
            <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 2 }}>
              {g.product_count} منتج
            </div>
            <button
              className={g.status === "active" ? "btn r" : "btn g"}
              style={{ marginTop: 10, width: "100%", height: 30 }}
            >
              {g.status === "active" ? "تعطيل" : "تفعيل"}
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}

const hint: React.CSSProperties = {
  background: "#eef4f8",
  border: "1px solid #d5e3ee",
  color: "#3a5a72",
  fontSize: 13,
  padding: "8px 14px",
  borderRadius: 5,
  margin: "6px 0 16px",
};
const grid: React.CSSProperties = {
  display: "grid",
  gridTemplateColumns: "repeat(4, 1fr)",
  gap: 16,
};
const card: React.CSSProperties = {
  background: "var(--surface)",
  border: "1px solid var(--border)",
  borderRadius: "var(--radius)",
  padding: 16,
  textAlign: "center",
  boxShadow: "var(--shadow-soft)",
};
const thumb: React.CSSProperties = {
  height: 120,
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  fontSize: 56,
  background: "#f2f5f6",
  borderRadius: 8,
  overflow: "hidden",
  cursor: "pointer",
};
