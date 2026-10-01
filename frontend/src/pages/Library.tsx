import { useEffect, useState } from "react";
import { api } from "../api";
import Icon from "../components/Icon";

interface LibPkg { name: string; suggested_cost: string; suggested_price: string; kupur: string }
interface LibGame {
  id: number; name: string; image_url: string; description: string;
  require_player_id: boolean; product_count: number; products: LibPkg[]; is_imported: boolean;
  /** مزوّدو متجري الذين تُربط بهم الباقات تلقائياً عند الاستيراد */
  auto_link?: string[];
}

export default function Library() {
  const [games, setGames] = useState<LibGame[]>([]);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [open, setOpen] = useState<number | null>(null);
  const [q, setQ] = useState("");

  function load() {
    setLoading(true);
    api.get("/catalog/library/").then((r) => setGames(r.data.results)).finally(() => setLoading(false));
  }
  useEffect(load, []);

  async function importGame(g: LibGame) {
    setBusyId(g.id); setMsg(null);
    try {
      const r = await api.post(`/catalog/library/${g.id}/import/`);
      const al = r.data.autolink;
      setMsg({ ok: true, text: `تمت إضافة "${g.name}" مع ${r.data.imported_products} باقات إلى متجرك ✓`
        + (al?.linked ? ` · 🔗 رُبطت ${al.linked} باقة تلقائياً بـ ${al.providers.join("، ")} وضُبط توجيهها — جاهزة للبيع` : "") });
      load();
    } catch (e: any) {
      const code = e?.response?.data?.code;
      setMsg({ ok: false, text: code === "already_imported" ? "المنتج مُضاف مسبقاً" : (e?.response?.data?.detail || "فشل الاستيراد") });
    } finally { setBusyId(null); }
  }

  // البحث باسم المنتج — ويطابق أسماء الباقات أيضاً («325 UC» يجد PUBG)
  const term = q.trim().toLowerCase();
  const shown = term
    ? games.filter((g) => g.name.toLowerCase().includes(term)
        || g.products.some((p) => p.name.toLowerCase().includes(term)))
    : games;

  const money = (v: string) => Number(v).toLocaleString("en-US", { minimumFractionDigits: 2 });

  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 6 }}>
        <Icon name="building" size={20} />
        <h2 style={{ fontSize: 18, margin: 0 }}>المكتبة العالمية</h2>
      </div>
      <p style={{ color: "var(--muted)", fontSize: 13, marginBottom: 16 }}>
        منتجات جاهزة أعدّها مزوّد النظام. اضغط "إضافة" لاستيراد المنتج مع كل باقاته إلى متجرك،
        ثم عدّل الأسعار أو احذف ما تشاء بحرّية دون التأثير على المكتبة.
      </p>

      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 14, flexWrap: "wrap" }}>
        <div style={{ position: "relative", width: 340, maxWidth: "100%" }}>
          <span style={{ position: "absolute", insetInlineStart: 11, top: "50%", transform: "translateY(-50%)",
                         color: "var(--muted)", pointerEvents: "none", display: "flex" }}>
            <Icon name="search" size={16} />
          </span>
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="ابحث باسم المنتج أو الباقة..."
            autoFocus style={{ width: "100%", height: 38, paddingInlineStart: 34 }} />
          {q && (
            <button type="button" onClick={() => setQ("")} aria-label="مسح"
              style={{ position: "absolute", insetInlineEnd: 6, top: "50%", transform: "translateY(-50%)",
                       background: "transparent", border: 0, cursor: "pointer", color: "var(--muted)", fontSize: 15 }}>✕</button>
          )}
        </div>
        {!loading && (
          <span style={{ color: "var(--muted)", fontSize: 13 }}>
            {term ? `${shown.length} من ${games.length} منتج` : `${games.length} منتج`}
          </span>
        )}
      </div>

      {msg && (
        <div style={{
          padding: "10px 14px", borderRadius: 6, marginBottom: 14, fontSize: 14,
          background: msg.ok ? "#e7f6ec" : "#fdecea",
          border: `1px solid ${msg.ok ? "#b6e0c4" : "#f5c6c2"}`,
          color: msg.ok ? "var(--ok)" : "var(--danger)",
        }}>{msg.text}</div>
      )}

      {loading ? <div style={{ padding: 24, color: "var(--muted)" }}>جارٍ التحميل...</div> : (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))", gap: 16 }}>
          {shown.map((g) => (
            <div key={g.id} style={card}>
              <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                <div style={thumb}>{g.image_url ? <img src={g.image_url} style={{ width: "100%", height: "100%", objectFit: "cover", borderRadius: 8 }} /> : "🎮"}</div>
                <div style={{ flex: 1 }}>
                  <div style={{ fontWeight: 700 }}>{g.name}</div>
                  <div style={{ fontSize: 12, color: "var(--muted)" }}>{g.product_count} باقة {g.require_player_id ? "· يتطلّب ID" : ""}</div>
                  {!!g.auto_link?.length && (
                    <div title="رقم كل باقة لدى مزوّدك محفوظٌ في المكتبة — تُربط وتُوجَّه وحدها عند الإضافة"
                      style={{ marginTop: 4, display: "inline-block", fontSize: 11.5, fontWeight: 700, padding: "2px 9px",
                               borderRadius: 999, background: "#e7f6ec", color: "#15803d", border: "1px solid #b6e0c4" }}>
                      🔗 تُربط تلقائياً بـ {g.auto_link.join("، ")}
                    </div>
                  )}
                </div>
              </div>

              <button style={{ ...linkish, marginTop: 10 }} onClick={() => setOpen(open === g.id ? null : g.id)}>
                {open === g.id ? "▲ إخفاء الباقات" : "▼ عرض الباقات"}
              </button>
              {open === g.id && (
                <div style={{ marginTop: 8, background: "#f7f9fa", borderRadius: 6, padding: "6px 10px", maxHeight: 150, overflowY: "auto" }}>
                  {g.products.map((p, i) => (
                    <div key={i} style={{ display: "flex", justifyContent: "space-between", gap: 8, fontSize: 12, padding: "3px 0", borderBottom: "1px solid #eef1f2" }}>
                      <span>
                        {p.kupur && (
                          <code style={{ background: "#e8edf0", borderRadius: 3, padding: "1px 5px",
                            marginInlineEnd: 6, direction: "ltr", display: "inline-block" }}
                            title="رقم الربط">{p.kupur}</code>
                        )}
                        {p.name}
                      </span>
                      <b style={{ color: "var(--primary-dark)" }}>{money(p.suggested_price)}</b>
                    </div>
                  ))}
                </div>
              )}

              <button
                className={g.is_imported ? "btn" : "btn g"}
                style={{ width: "100%", height: 38, marginTop: 12, ...(g.is_imported ? { background: "#8a999e" } : {}) }}
                disabled={g.is_imported || busyId === g.id}
                onClick={() => importGame(g)}
              >
                {g.is_imported ? "✓ مُضاف" : busyId === g.id ? "جارٍ الإضافة..." : "➕ إضافة إلى متجري"}
              </button>
            </div>
          ))}
          {shown.length === 0 && (
            <div style={{ color: "var(--muted)", padding: 24 }}>
              {games.length ? `لا منتج يطابق «${q.trim()}».` : "لا منتجات عالمية متاحة حالياً."}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

const card: React.CSSProperties = {
  background: "#fff", borderRadius: 12, padding: 16, boxShadow: "0 2px 8px rgba(0,0,0,.06)",
  border: "1px solid var(--border)",
};
const thumb: React.CSSProperties = {
  width: 48, height: 48, borderRadius: 8, background: "#f2f5f6",
  display: "flex", alignItems: "center", justifyContent: "center", fontSize: 26,
};
const linkish: React.CSSProperties = {
  background: "transparent", border: 0, color: "var(--primary)", fontSize: 13, cursor: "pointer", padding: 0,
};
