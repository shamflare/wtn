import { useEffect, useState } from "react";
import SecurityPanel from "../components/SecurityPanel";
import { api } from "../api";
import ImageUpload from "../components/ImageUpload";
import LibrarySources from "../components/LibrarySources";
import { editValue, pickUnit, showPrice, toBlock } from "../unitPrice";
import { useNavigate, useParams } from "react-router-dom";
import { useAuth } from "../auth";
import Tickets from "../components/Tickets";
import CardsEditor from "../components/HomeCards";

interface Tenant {
  id: number; name: string; subdomain: string; status: string;
  theme: string; dealers: number; created_at: string;
  sub_plan: string; sub_plan_label: string; sub_monthly_price: string;
  sub_yearly_price: string; sub_expires_at: string | null;
  sub_active: boolean; sub_days_left: number | null;
  sub_grace_days?: number; sub_enforce?: boolean; sub_state?: string;
  domain?: string; orders?: number; users?: number;
  admin_login_id?: string | null; admin_name?: string | null; admin_locked?: boolean;
}
interface Stats { tenants: number; active: number; dealers: number }
interface LibGame {
  id: number; uuid: string; name: string; image_url: string; description: string;
  require_player_id: boolean; product_count: number; source_name?: string;
}
interface LibProduct {
  id: number; game: number; name: string; suggested_cost: string;
  suggested_price: string; kupur: string;
  sale_type?: string; qty_min?: number; qty_max?: number; qty_unit?: number;
}

/** أربع حالات لا حالتان: «فعّال/غير فعّال» كان يخفي مهلة السماح. */
const SUB_TONE: Record<string, { bg: string; fg: string; label: string }> = {
  ok: { bg: "#e7f6ec", fg: "#14532d", label: "الاشتراك سارٍ" },
  warn: { bg: "#fef3c7", fg: "#78350f", label: "يقارب الانتهاء" },
  grace: { bg: "#ffedd5", fg: "#7c2d12", label: "انتهى — في مهلة السماح" },
  blocked: { bg: "#fee2e2", fg: "#7f1d1d", label: "متوقّف — الشراء ممنوع" },
};

type Tab = "tenants" | "library" | "sources" | "invoices" | "messages" | "announce" | "cards" | "sorgula" | "security";
const TABS: Tab[] = ["tenants", "library", "sources", "invoices", "messages", "announce", "cards", "sorgula", "security"];

export default function Platform({ section: forced }: { section?: Tab } = {}) {
  const { user, logout } = useAuth();
  // كل قسمٍ رابطه (/platform/library …) — فالتحديث يُبقيك حيث كنت، والرابط يُنسخ ويُفتح مباشرةً.
  // و/sorgula رابطٌ قصير يفتح قسم كشف الخطوط مباشرةً.
  const params = useParams();
  const section = forced || params.section;
  const navigate = useNavigate();
  const tab: Tab = (TABS as string[]).includes(section || "") ? (section as Tab) : "tenants";
  const setTab = (t: Tab) => navigate(t === "tenants" ? "/platform" : t === "sorgula" ? "/sorgula" : `/platform/${t}`);

  return (
    <div style={{ minHeight: "100vh", background: "#0f172a", color: "#e2e8f0" }}>
      <div style={header}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <span style={{ fontSize: 24 }}>🏢</span>
          <b style={{ fontSize: 18 }}>لوحة المنصّة</b>
        </div>
        <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
          <span style={{ fontSize: 13, opacity: 0.8 }}>{user?.name}</span>
          <button onClick={logout} style={logoutBtn}>خروج</button>
        </div>
      </div>

      <div style={subnav}>
        <button onClick={() => setTab("tenants")} style={{ ...tabBtn, ...(tab === "tenants" ? tabActive : {}) }}>🏢 المستأجرون</button>
        <button onClick={() => setTab("library")} style={{ ...tabBtn, ...(tab === "library" ? tabActive : {}) }}>🌐 المنتجات العالمية</button>
        <button onClick={() => setTab("sources")} style={{ ...tabBtn, ...(tab === "sources" ? tabActive : {}) }}>🔌 مصادر المكتبة</button>
        <button onClick={() => setTab("invoices")} style={{ ...tabBtn, ...(tab === "invoices" ? tabActive : {}) }}>🧾 الفواتير</button>
        <button onClick={() => setTab("messages")} style={{ ...tabBtn, ...(tab === "messages" ? tabActive : {}) }}>💬 الرسائل</button>
        <button onClick={() => setTab("announce")} style={{ ...tabBtn, ...(tab === "announce" ? tabActive : {}) }}>📢 الإعلان العام</button>
        <button onClick={() => setTab("cards")} style={{ ...tabBtn, ...(tab === "cards" ? tabActive : {}) }}>🗂️ بطاقات المتاجر</button>
        <button onClick={() => setTab("sorgula")} style={{ ...tabBtn, ...(tab === "sorgula" ? tabActive : {}) }}>📱 كشف الخطوط</button>
        <button onClick={() => setTab("security")} style={{ ...tabBtn, ...(tab === "security" ? tabActive : {}) }}>🔐 الأمان</button>
      </div>

      <div style={{ maxWidth: 1150, margin: "0 auto", padding: 24 }}>
        {tab === "tenants" && <TenantsTab />}
        {tab === "library" && <LibraryTab />}
        {tab === "sources" && <LibrarySources />}
        {tab === "invoices" && <BillingTab />}
        {tab === "announce" && <AnnounceTab />}
        {tab === "sorgula" && <SorgulaTab />}
        {tab === "security" && (
          <div style={{ background: "#fff", color: "var(--text)", borderRadius: 12, padding: 20 }}>
            <SecurityPanel />
          </div>
        )}
        {tab === "cards" && (
          <div style={{ background: "#fff", color: "var(--text)", borderRadius: 12, padding: 20 }}>
            <CardsEditor
              audienceLabel="أصحاب المتاجر"
              hint="تظهر في الصفحة الرئيسية لكل صاحب متجر فور دخوله — إعلان ميزة، تنبيه صيانة، أو ما تشاء."
            />
          </div>
        )}
        {tab === "messages" && (
          <div style={{ background: "#fff", borderRadius: 12, padding: 20 }}>
            <Tickets canCreate={false} title="رسائل المتاجر" />
          </div>
        )}
      </div>
    </div>
  );
}

/* ===== المستأجرون ===== */
function TenantsTab() {
  const [tenants, setTenants] = useState<Tenant[]>([]);
  const [stats, setStats] = useState<Stats | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [subFor, setSubFor] = useState<Tenant | null>(null);
  const [editFor, setEditFor] = useState<Tenant | null>(null);
  const [delFor, setDelFor] = useState<Tenant | null>(null);

  function load() {
    api.get("/platform/tenants/").then((r) => { setTenants(r.data.results); setStats(r.data.stats); });
  }
  useEffect(() => load(), []);

  async function toggle(t: Tenant) {
    const action = t.status === "active" ? "suspend" : "activate";
    await api.post(`/platform/tenants/${t.id}/${action}/`, {});
    load();
  }

  return (
    <>
      {stats && (
        <div style={{ display: "flex", gap: 16, marginBottom: 24 }}>
          <StatCard label="المستأجرون" value={stats.tenants} icon="🏢" />
          <StatCard label="النشطون" value={stats.active} icon="✅" />
          <StatCard label="إجمالي الوكلاء" value={stats.dealers} icon="👥" />
        </div>
      )}
      <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 14 }}>
        <h2 style={{ fontSize: 18 }}>المستأجرون</h2>
        <button style={addBtn} onClick={() => setShowCreate(true)}>➕ إضافة مستأجر (بيع نسخة)</button>
      </div>
      <div style={{ overflow: "hidden", borderRadius: 10, border: "1px solid #1e293b" }}>
        <table style={table}>
          <thead>
            <tr>{["#", "الاسم", "النطاق الفرعي", "الوكلاء", "الاشتراك", "الحالة", "إجراء"].map((h) => <th key={h} style={th}>{h}</th>)}</tr>
          </thead>
          <tbody>
            {tenants.map((t) => (
              <tr key={t.id} style={{ borderTop: "1px solid #1e293b" }}>
                <td style={td}>{t.id}</td>
                <td style={{ ...td, fontWeight: 700 }}>{t.name}</td>
                {/* صار عنواناً عاملاً (2026-08-16): شهادةٌ شاملة ووسيطٌ يستنتج
                    المتجر من الرابط. وكان قبلها مُزمَعاً يُعرض رمادياً، لأن
                    ضغطه يعطي خطأ شهادةٍ مبهماً. */}
                <td style={{ ...td, direction: "ltr" }}>
                  <a href={`https://${t.domain || t.subdomain}`} target="_blank" rel="noreferrer"
                     style={{ color: "#7dd3fc" }}>
                    {t.domain || t.subdomain}
                  </a>
                  <div style={{ fontSize: 10.5, color: "#64748b", direction: "rtl", marginTop: 2 }}>
                    {t.status === "suspended"
                      ? "موقوف — العنوان يعرض صفحة توقّف"
                      : "عنوان المتجر · و wtn4.com يبقى مفتوحاً"}
                  </div>
                </td>
                <td style={td}>{t.dealers}</td>
                <td style={td}>
                  {t.sub_active ? (
                    <span style={{ color: "#4ade80", fontSize: 13 }}>
                      {t.sub_plan_label} · {t.sub_days_left}ي
                    </span>
                  ) : (
                    <span style={{ color: "#64748b", fontSize: 13 }}>بلا اشتراك</span>
                  )}
                </td>
                <td style={td}>
                  <span style={{ color: t.status === "active" ? "#4ade80" : "#f87171", fontWeight: 700 }}>
                    ● {t.status === "active" ? "نشط" : "موقوف"}
                  </span>
                </td>
                <td style={{ ...td, whiteSpace: "nowrap" }}>
                  <button style={subBtn} onClick={() => setSubFor(t)}>الاشتراك</button>
                  <button style={{ ...subBtn, background: "#334155" }}
                    onClick={() => setEditFor(t)}>تعديل</button>
                  <button style={{ ...subBtn, background: "#7f1d1d" }}
                    onClick={() => setDelFor(t)}>حذف</button>
                  <button style={t.status === "active" ? suspendBtn : activateBtn} onClick={() => toggle(t)}>
                    {t.status === "active" ? "تعليق" : "تفعيل"}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {showCreate && <CreateTenant onClose={() => setShowCreate(false)} onDone={() => { setShowCreate(false); load(); }} />}
      {editFor && (
        <EditTenant tenant={editFor} onClose={() => setEditFor(null)}
          onDone={() => { setEditFor(null); load(); }} />
      )}
      {delFor && (
        <DeleteTenant tenant={delFor} onClose={() => setDelFor(null)}
          onDone={() => { setDelFor(null); load(); }} />
      )}
      {subFor && <SubscriptionModal tenant={subFor} onClose={() => setSubFor(null)} onDone={() => { setSubFor(null); load(); }} />}
    </>
  );
}

/* ===== المنتجات العالمية (المكتبة) ===== */
function LibraryTab() {
  const [games, setGames] = useState<LibGame[]>([]);
  const [showAdd, setShowAdd] = useState(false);
  const [editing, setEditing] = useState<LibGame | null>(null);
  const [manage, setManage] = useState<LibGame | null>(null);
  const [q, setQ] = useState("");
  const [picked, setPicked] = useState<Set<number>>(new Set());
  const [busy, setBusy] = useState(false);

  function load() { api.get("/platform/library/games/").then((r) => setGames(r.data.results || r.data)); }
  useEffect(() => load(), []);

  async function del(g: LibGame) {
    if (!confirm(`حذف "${g.name}" من المكتبة العالمية؟ (لا يؤثّر على من استوردها)`)) return;
    await api.delete(`/platform/library/games/${g.id}/`);
    setPicked((s) => { const n = new Set(s); n.delete(g.id); return n; });
    load();
  }

  // البحث يضيّق الجدول، و«تحديد الكل» يحدّد الظاهر وحده — فـ«chat» ثم تحديد الكل يكفي
  const term = q.trim().toLowerCase();
  const shown = term
    ? games.filter((g) => g.name.toLowerCase().includes(term) || (g.source_name || "").toLowerCase().includes(term))
    : games;
  const allShown = shown.length > 0 && shown.every((g) => picked.has(g.id));
  function toggleAll() {
    setPicked((s) => {
      const n = new Set(s);
      for (const g of shown) allShown ? n.delete(g.id) : n.add(g.id);
      return n;
    });
  }
  function toggle(id: number) {
    setPicked((s) => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n; });
  }

  async function bulkDelete() {
    const names = games.filter((g) => picked.has(g.id)).map((g) => g.name);
    if (!confirm(`حذف ${names.length} منتج من المكتبة العالمية مع كل باقاتها؟\n\n`
      + names.slice(0, 12).join("، ") + (names.length > 12 ? ` … و${names.length - 12} غيرها` : "")
      + "\n\nلا يؤثّر على المتاجر التي استوردتها.")) return;
    setBusy(true);
    try {
      await api.post("/platform/library/games/bulk-delete/", { ids: [...picked] });
      setPicked(new Set());
      load();
    } catch (e: any) {
      alert(e?.response?.data?.detail || "تعذّر الحذف");
    } finally { setBusy(false); }
  }

  return (
    <>
      <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 6 }}>
        <h2 style={{ fontSize: 18 }}>المنتجات العالمية</h2>
        <button style={addBtn} onClick={() => setShowAdd(true)}>➕ إضافة منتج عالمي</button>
      </div>
      <p style={{ color: "#94a3b8", fontSize: 13, marginBottom: 16 }}>
        منتجات جاهزة مع باقاتها؛ يستوردها أصحاب المتاجر بضغطة، ويعدّلون نسختهم بحرّية دون التأثير هنا.
      </p>
      <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 12, flexWrap: "wrap" }}>
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="🔍 ابحث عن منتج..."
          style={{ width: 260, height: 36, background: "#0b1222", color: "#e2e8f0", border: "1px solid #334155", borderRadius: 8, padding: "0 10px" }} />
        <span style={{ color: "#94a3b8", fontSize: 13 }}>
          {term ? `${shown.length} من ${games.length}` : `${games.length} منتج`}
          {picked.size > 0 && <> · <b style={{ color: "#fecaca" }}>محدّد {picked.size}</b></>}
        </span>
        {picked.size > 0 && (
          <>
            <button style={{ ...suspendBtn, padding: "8px 16px", fontWeight: 700 }} disabled={busy} onClick={bulkDelete}>
              {busy ? "جارٍ الحذف..." : `🗑 حذف المحدّد (${picked.size})`}
            </button>
            <button style={{ background: "transparent", border: "1px solid #334155", color: "#cbd5e1", padding: "7px 12px", borderRadius: 6, cursor: "pointer" }}
              onClick={() => setPicked(new Set())}>إلغاء التحديد</button>
          </>
        )}
      </div>
      <div style={{ overflow: "hidden", borderRadius: 10, border: "1px solid #1e293b" }}>
        <table style={table}>
          <thead>
            <tr>
              <th style={{ ...th, width: 42 }}>
                <input type="checkbox" checked={allShown} onChange={toggleAll} title="تحديد كل الظاهر" />
              </th>
              {["#", "المنتج", "الصورة", "الباقات", "معرّف لاعب", "إجراء"].map((h) => <th key={h} style={th}>{h}</th>)}
            </tr>
          </thead>
          <tbody>
            {shown.length === 0 ? (
              <tr><td colSpan={7} style={{ ...td, color: "#64748b", padding: 24 }}>
                {games.length ? "لا نتائج." : "لا منتجات عالمية بعد — أضف أول منتج."}
              </td></tr>
            ) : shown.map((g) => (
              <tr key={g.id} style={{ borderTop: "1px solid #1e293b", background: picked.has(g.id) ? "#2a1215" : undefined }}>
                <td style={td}><input type="checkbox" checked={picked.has(g.id)} onChange={() => toggle(g.id)} /></td>
                <td style={td}>{g.id}</td>
                <td style={{ ...td, fontWeight: 700, textAlign: "right", paddingInlineStart: 14 }}>
                  {g.name}
                  {g.source_name && (
                    <span title="مستوردة من مصدر — «مزامنة» تحدّث باقاتها وأسعارها" style={{
                      marginInlineStart: 8, fontSize: 11, fontWeight: 700, padding: "2px 8px", borderRadius: 999,
                      background: "#1e3a8a", color: "#bfdbfe" }}>🔌 {g.source_name}</span>
                  )}
                </td>
                <td style={td}>{g.image_url ? <img src={g.image_url} style={{ width: 40, height: 40, borderRadius: 7, objectFit: "cover" }} /> : "—"}</td>
                <td style={td}><b style={{ color: "#7dd3fc" }}>{g.product_count}</b></td>
                <td style={td}>{g.require_player_id ? "✅" : "—"}</td>
                <td style={td}>
                  <button style={editBtn} onClick={() => setEditing(g)}>✏️ تعديل</button>
                  <button style={pkgBtn} onClick={() => setManage(g)}>الباقات</button>
                  <button style={suspendBtn} onClick={() => del(g)}>حذف</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {showAdd && <LibGameForm onClose={() => setShowAdd(false)} onDone={() => { setShowAdd(false); load(); }} />}
      {editing && <LibGameForm game={editing} onClose={() => setEditing(null)} onDone={() => { setEditing(null); load(); }} />}
      {manage && <ManagePackages game={manage} onClose={() => { setManage(null); load(); }} />}
    </>
  );
}

/** إضافة منتج عالمي، أو تعديله إن مُرِّر `game`. التعديل لا يمسّ نسخ من استورده. */
function LibGameForm({ game, onClose, onDone }: { game?: LibGame; onClose: () => void; onDone: () => void }) {
  const [f, setF] = useState({
    name: game?.name || "", image_url: game?.image_url || "",
    // منتجٌ جديد يطلب معرّف اللاعب افتراضاً — يُلغى حيث لا يلزم
    description: game?.description || "", require_player_id: game ? game.require_player_id : true,
  });
  const [err, setErr] = useState(""); const [busy, setBusy] = useState(false);
  async function submit(e: React.FormEvent) {
    e.preventDefault(); setBusy(true); setErr("");
    try {
      if (game) await api.patch(`/platform/library/games/${game.id}/`, f);
      else await api.post("/platform/library/games/", f);
      onDone();
    }
    catch (e: any) { setErr(e?.response?.data?.detail || (game ? "فشل التعديل" : "فشل الإضافة")); }
    finally { setBusy(false); }
  }
  return (
    <div style={overlay} onClick={onClose}>
      <form style={modal} onClick={(e) => e.stopPropagation()} onSubmit={submit}>
        <div style={{ background: "#0f172a", color: "#e2e8f0", padding: "14px 18px", fontWeight: 700, fontSize: 16 }}>
          {game ? `تعديل: ${game.name}` : "إضافة منتج عالمي"}
        </div>
        <div style={{ padding: 20, color: "#0f172a" }}>
          <F label="اسم المنتج"><input style={inp} value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} required autoFocus /></F>
          <F label="الصورة (اختياري)"><ImageUpload value={f.image_url} onChange={(v) => setF({ ...f, image_url: v })} /></F>
          <F label="الوصف (اختياري)"><input style={inp} value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} /></F>
          <label style={{ display: "flex", alignItems: "center", gap: 8, margin: "8px 0", color: "#0f172a", fontSize: 14 }}>
            <input type="checkbox" checked={f.require_player_id} onChange={(e) => setF({ ...f, require_player_id: e.target.checked })} />
            يتطلّب معرّف لاعب (ID)
          </label>
          {err && <div style={errBox}>{err}</div>}
          <div style={{ display: "flex", gap: 10, marginTop: 14 }}>
            <button className="btn g" style={{ flex: 1, height: 40 }} disabled={busy}>{busy ? "جارٍ..." : game ? "حفظ التعديل" : "حفظ"}</button>
            <button type="button" className="btn" style={{ height: 40, background: "#8a999e" }} onClick={onClose}>إلغاء</button>
          </div>
        </div>
      </form>
    </div>
  );
}

function ManagePackages({ game, onClose }: { game: LibGame; onClose: () => void }) {
  const [rows, setRows] = useState<LibProduct[]>([]);
  const blank = { name: "", suggested_cost: "", suggested_price: "", kupur: "",
                  sale_type: "package", qty_min: "", qty_max: "" };
  const [f, setF] = useState(blank);
  const [editId, setEditId] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  function load() { api.get(`/platform/library/products/?game=${game.id}`).then((r) => setRows(r.data.results || r.data)); }
  useEffect(() => load(), []);

  async function add(e: React.FormEvent) {
    e.preventDefault(); setBusy(true); setErr("");
    const amount = f.sale_type === "amount";
    if (amount && !(Number(f.qty_min) >= 1 && Number(f.qty_max) >= Number(f.qty_min))) {
      setErr("حدّا الكمية: الأقل 1 فأكثر، والأكبر لا يقلّ عن الأقل"); setBusy(false); return;
    }
    // بالكمية: السعران المكتوبان للوحدة ⇐ يُحفظان لكل كتلة. الكتلة تُختار عند الإضافة
    // بحيث يُحفظ السعر بالضبط (0.03 ⇐ لكل 100)، وتبقى عند التعديل كما هي.
    const editing = rows.find((r) => r.id === editId);
    const unit = !amount ? 1 : editing?.qty_unit
      || Math.max(pickUnit(Number(f.suggested_cost) || 0), pickUnit(Number(f.suggested_price) || 0));
    const qtyLike = { sale_type: amount ? "amount" : "package", qty_unit: unit };
    const body: Record<string, unknown> = {
      name: f.name,
      suggested_cost: toBlock(f.suggested_cost || "0", qtyLike),
      suggested_price: toBlock(f.suggested_price || "0", qtyLike),
      ...(amount ? { qty_min: Number(f.qty_min), qty_max: Number(f.qty_max) } : {}),
      ...(amount && !editId ? { sale_type: "amount", qty_unit: unit } : {}),
    };
    try {
      // رقم الربط لا يتبدّل بعد الإضافة: عليه تقوم روابط من استورد الباقة
      if (editId) await api.patch(`/platform/library/products/${editId}/`, body);
      else await api.post("/platform/library/products/", { ...body, game: game.id, kupur: f.kupur });
      setF(blank); setEditId(null);
      load();
    } catch (e: any) {
      const d = e?.response?.data;
      const first = d && typeof d === "object" ? Object.values(d)[0] : null;
      setErr(String(Array.isArray(first) ? first[0] : first || "تعذّر الحفظ"));
    } finally { setBusy(false); }
  }
  function startEdit(p: LibProduct) {
    setErr(""); setEditId(p.id);
    setF({ name: p.name, suggested_cost: editValue(p.suggested_cost, p), suggested_price: editValue(p.suggested_price, p),
           kupur: p.kupur, sale_type: p.sale_type || "package",
           qty_min: String(p.qty_min ?? ""), qty_max: String(p.qty_max ?? "") });
  }
  async function del(id: number) { await api.delete(`/platform/library/products/${id}/`); load(); }

  return (
    <div style={overlay} onClick={onClose}>
      {/* النافذة لا تتجاوز الشاشة: الجدول وحده يتمرّر، ونموذج الإضافة ثابتٌ أسفلها */}
      <div style={{ ...modal, width: 760, color: "#0f172a", maxHeight: "92vh", display: "flex", flexDirection: "column" }}
        onClick={(e) => e.stopPropagation()}>
        <div style={{ background: "#0f172a", color: "#e2e8f0", padding: "14px 18px", fontWeight: 700, fontSize: 16, display: "flex", justifyContent: "space-between" }}>
          <span>باقات: {game.name}</span>
          <button onClick={onClose} style={{ background: "transparent", border: 0, color: "#94a3b8", fontSize: 18, cursor: "pointer" }}>✕</button>
        </div>
        <div style={{ padding: 18, display: "flex", flexDirection: "column", minHeight: 0, flex: 1 }}>
          <div style={{ overflowY: "auto", minHeight: 0, flex: 1, border: "1px solid #eef1f2", borderRadius: 6 }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
            <thead>
              <tr>{["الباقة", "التكلفة", "السعر المقترح", "رقم الربط", ""].map((h) => <th key={h} style={{ ...th, background: "#e2e8f0", color: "#475569", position: "sticky", top: 0, zIndex: 1 }}>{h}</th>)}</tr>
            </thead>
            <tbody>
              {rows.length === 0 ? (
                <tr><td colSpan={5} style={{ padding: 16, textAlign: "center", color: "#94a3b8" }}>لا باقات — أضف أدناه.</td></tr>
              ) : rows.map((p) => (
                <tr key={p.id} style={{ borderTop: "1px solid #eef1f2", background: editId === p.id ? "#fef9c3" : undefined }}>
                  <td style={{ padding: "8px", fontWeight: 700 }}>
                    {p.name}
                    {p.sale_type === "amount" && (
                      <div style={{ fontSize: 11, color: "#7c3aed", fontWeight: 700 }}>
                        ⚖ بالكمية {Number(p.qty_min).toLocaleString("en-US")}–{Number(p.qty_max).toLocaleString("en-US")} · السعران للوحدة
                      </div>
                    )}
                  </td>
                  <td style={{ padding: "8px", textAlign: "center", direction: "ltr" }}>{showPrice(p.suggested_cost, p)}</td>
                  <td style={{ padding: "8px", textAlign: "center", direction: "ltr" }}>{showPrice(p.suggested_price, p)}</td>
                  <td style={{ padding: "8px", textAlign: "center" }}>{p.kupur || "—"}</td>
                  <td style={{ padding: "8px", textAlign: "center", whiteSpace: "nowrap" }}>
                    <button style={editBtn} onClick={() => startEdit(p)}>✏️ تعديل</button>
                    <button style={suspendBtn} onClick={() => del(p.id)}>حذف</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          </div>
          <form onSubmit={add} style={{ display: "flex", gap: 8, marginTop: 14, alignItems: "end", flexWrap: "wrap" }}>
            <Field label="النوع">
              <select style={{ ...inp, width: 110 }} value={f.sale_type} disabled={!!editId}
                title={editId ? "النوع لا يتغيّر بعد الإضافة" : undefined}
                onChange={(e) => setF({ ...f, sale_type: e.target.value })}>
                <option value="package">باقة ثابتة</option>
                <option value="amount">بالكمية ⚖</option>
              </select>
            </Field>
            <Field label="الباقة"><input style={{ ...inp, width: 140 }} value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} required /></Field>
            <Field label={f.sale_type === "amount" ? "تكلفة الوحدة" : "التكلفة"}><input style={{ ...inp, width: 100 }} type="number" step="any" dir="ltr" value={f.suggested_cost} onChange={(e) => setF({ ...f, suggested_cost: e.target.value })} /></Field>
            <Field label={f.sale_type === "amount" ? "سعر الوحدة" : "السعر"}><input style={{ ...inp, width: 100 }} type="number" step="any" dir="ltr" value={f.suggested_price} onChange={(e) => setF({ ...f, suggested_price: e.target.value })} /></Field>
            {f.sale_type === "amount" && (
              <>
                <Field label="أقل كمية"><input style={{ ...inp, width: 100 }} type="number" min={1} dir="ltr" value={f.qty_min} onChange={(e) => setF({ ...f, qty_min: e.target.value })} required /></Field>
                <Field label="أكبر كمية"><input style={{ ...inp, width: 110 }} type="number" min={1} dir="ltr" value={f.qty_max} onChange={(e) => setF({ ...f, qty_max: e.target.value })} required /></Field>
              </>
            )}
            <Field label="رقم الربط"><input style={{ ...inp, width: 90, ...(editId ? { background: "#f1f5f9", color: "#64748b" } : {}) }}
              value={f.kupur} onChange={(e) => setF({ ...f, kupur: e.target.value })} required dir="ltr"
              disabled={!!editId} title={editId ? "رقم الربط لا يتغيّر بعد الإضافة" : undefined} /></Field>
            <button className="btn g" style={{ height: 38 }} disabled={busy}>{busy ? "..." : editId ? "💾 حفظ التعديل" : "➕ إضافة"}</button>
            {editId && (
              <button type="button" className="btn" style={{ height: 38, background: "#8a999e" }}
                onClick={() => { setEditId(null); setF(blank); setErr(""); }}>إلغاء</button>
            )}
          </form>
          {err && <div style={errBox}>{err}</div>}
          <div style={{ marginTop: 10, fontSize: 12.5, color: "#64748b", lineHeight: 1.7 }}>
            رقم الربط جسر الباقة: منه تُبنى قائمة الأرقام التي يختار منها أصحاب المتاجر،
            ولا يستطيع أحدهم تغييره بعد الإضافة. اجعله فريداً داخل اللعبة الواحدة.
          </div>
        </div>
      </div>
    </div>
  );
}

/* ===== الإعلان العام (يظهر فوق هيدر لوحات أصحاب المتاجر) ===== */
function AnnounceTab() {
  const [message, setMessage] = useState("");
  const [ticker, setTicker] = useState("");
  const [saved, setSaved] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.get("/platform/announcement/").then((r) => { setMessage(r.data.message); setTicker(r.data.ticker); });
  }, []);

  async function save() {
    setBusy(true); setSaved(false);
    try { await api.put("/platform/announcement/", { message, ticker }); setSaved(true); }
    finally { setBusy(false); }
  }

  return (
    <div style={{ maxWidth: 720 }}>
      <h2 style={{ fontSize: 18, marginBottom: 6 }}>الإعلان العام</h2>
      <p style={{ color: "#94a3b8", fontSize: 13, marginBottom: 18 }}>
        يظهر فوق هيدر لوحات كل أصحاب المتاجر. المساحة محجوزة دائماً — اتركه فارغاً لإخفاء المحتوى دون تحريك الهيدر.
      </p>
      <div style={{ fontSize: 13, color: "#94a3b8", marginBottom: 5 }}>نص التنبيه (الشريط الثابت فوق الهيدر)</div>
      <textarea value={message} onChange={(e) => setMessage(e.target.value)}
        style={{ width: "100%", height: 80, padding: 10, borderRadius: 8, border: "1px solid #334155", background: "#0f172a", color: "#e2e8f0", fontSize: 14 }}
        placeholder="مثال: مرحباً بكم في منصّة WTN — تابعوا التحديثات من هنا." />
      <div style={{ fontSize: 13, color: "#94a3b8", margin: "16px 0 5px" }}>الشريط العاجل المتحرّك (سطر لكل عنصر — يظهر تحت الهيدر)</div>
      <textarea value={ticker} onChange={(e) => setTicker(e.target.value)}
        style={{ width: "100%", height: 100, padding: 10, borderRadius: 8, border: "1px solid #334155", background: "#0f172a", color: "#e2e8f0", fontSize: 14 }}
        placeholder={"صيانة مجدولة يوم الجمعة 02:00–04:00 فجراً.\nحدّثوا أسعار PUBG اليوم."} />
      <div style={{ display: "flex", gap: 10, alignItems: "center", marginTop: 16 }}>
        <button style={addBtn} onClick={save} disabled={busy}>{busy ? "جارٍ الحفظ..." : "حفظ ونشر"}</button>
        {saved && <span style={{ color: "#4ade80", fontSize: 13 }}>✓ نُشر — سيظهر فوراً في لوحات المتاجر</span>}
      </div>
    </div>
  );
}

/* ===== كشف الخطوط (sorgula) ===== */
interface SorgulaCfg {
  base_url: string; username: string; has_password: boolean; security_image: string;
  enabled: boolean; configured: boolean; last_ok_at: string; last_error: string; updated_at: string;
}

/**
 * حساب لوحة ZNET الذي تكشف به **كل المتاجر** شركةَ الرقم وعروضه الخاصة.
 * عامّ للمنصّة لا للمتجر: يُضبط هنا مرّة فيخدم كل نسخة مبيعة.
 */
function SorgulaTab() {
  const [cfg, setCfg] = useState<SorgulaCfg | null>(null);
  const [f, setF] = useState({ base_url: "", username: "", password: "", security_image: "D", enabled: true });
  const [busy, setBusy] = useState<"" | "save" | "test">("");
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [gsm, setGsm] = useState("");
  const [steps, setSteps] = useState<{ ok: boolean; step: string; detail?: string }[] | null>(null);

  function fill(c: SorgulaCfg) {
    setCfg(c);
    setF({ base_url: c.base_url, username: c.username, password: "", security_image: c.security_image || "D", enabled: c.enabled });
  }
  useEffect(() => { api.get("/platform/sorgula/").then((r) => fill(r.data)).catch(() => {}); }, []);
  const set = (k: keyof typeof f, v: any) => setF((o) => ({ ...o, [k]: v }));

  async function save() {
    setBusy("save"); setMsg(null);
    try {
      fill((await api.put("/platform/sorgula/", f)).data);
      setMsg({ ok: true, text: "✓ حُفظ — تستعمله كل المتاجر من الطلب التالي" });
    } catch (e: any) { setMsg({ ok: false, text: e?.response?.data?.detail || "تعذّر الحفظ" }); }
    finally { setBusy(""); }
  }

  async function test() {
    setBusy("test"); setSteps(null); setMsg(null);
    try {
      const r = await api.post("/platform/sorgula/test/", { gsm });
      setSteps(r.data.steps); setCfg(r.data.config);
    } catch (e: any) { setMsg({ ok: false, text: e?.response?.data?.detail || "تعذّر الاختبار" }); }
    finally { setBusy(""); }
  }

  const darkInp: React.CSSProperties = {
    width: "100%", height: 40, padding: "0 12px", borderRadius: 8, border: "1px solid #334155",
    background: "#0f172a", color: "#e2e8f0", fontSize: 14,
  };
  const lbl: React.CSSProperties = { fontSize: 13, color: "#94a3b8", margin: "14px 0 5px" };
  const state = !cfg ? null : !cfg.configured ? ["#78350f", "#fef3c7", "غير مضبوط — تعمل الخدمة على إعداد الخادم القديم إن وُجد"]
    : !cfg.enabled ? ["#7f1d1d", "#fee2e2", "موقوف — لا كشف ولا عروض في كل المتاجر"]
    : cfg.last_error ? ["#7c2d12", "#ffedd5", `آخر محاولة فشلت: ${cfg.last_error}`]
    : ["#14532d", "#e7f6ec", cfg.last_ok_at ? `يعمل — آخر نجاح ${cfg.last_ok_at}` : "مضبوط — لم يُستعمل بعد"];

  return (
    <div style={{ maxWidth: 760 }}>
      <h2 style={{ fontSize: 18, marginBottom: 6 }}>كشف الخطوط والعروض الخاصة</h2>
      <p style={{ color: "#94a3b8", fontSize: 13, lineHeight: 1.9, marginBottom: 14 }}>
        حساب لوحة ZNET الذي يكشف به <b style={{ color: "#e2e8f0" }}>كل متجر على المنصّة</b> شركةَ رقم الزبون
        وعروضه الخاصة (ما لا يعطيه API الرسمي). يُضبط هنا مرّة فيخدم كل النسخ المبيعة — صاحب المتجر لا يحتاج
        حساباً لذلك. أمّا <b style={{ color: "#e2e8f0" }}>الشحن نفسه</b> فيبقى عبر مزوّدي كل متجر (حسابه ورصيده).
      </p>

      {state && (
        <div style={{ background: state[1], color: state[0], borderRadius: 8, padding: "10px 14px", fontSize: 13, fontWeight: 700, marginBottom: 16 }}>
          {state[2]}
        </div>
      )}

      <div style={{ background: "#131c31", border: "1px solid #1e293b", borderRadius: 12, padding: 18 }}>
        <button type="button" onClick={() => set("enabled", !f.enabled)} style={{
          width: "100%", display: "flex", alignItems: "center", gap: 12, padding: "12px 14px", borderRadius: 10,
          cursor: "pointer", textAlign: "start", font: "inherit",
          border: `1px solid ${f.enabled ? "#166534" : "#991b1b"}`,
          background: f.enabled ? "#052e1a" : "#2a0d0d", color: "#e2e8f0",
        }}>
          <span style={{
            width: 46, height: 26, borderRadius: 999, padding: 3, flex: "none", display: "flex",
            justifyContent: f.enabled ? "flex-end" : "flex-start", background: f.enabled ? "#22c55e" : "#64748b",
          }}><span style={{ width: 20, height: 20, borderRadius: "50%", background: "#fff" }} /></span>
          <span>
            <b style={{ color: f.enabled ? "#4ade80" : "#f87171" }}>
              {f.enabled ? "الكشف مفعّل لكل المتاجر" : "الكشف موقوف — لا كشف ولا عروض في أيّ متجر"}
            </b>
            <div style={{ fontSize: 12, color: "#94a3b8", marginTop: 2 }}>
              اضغط للتبديل ثم «حفظ». الإيقاف للطوارئ فقط (مثل تغيير الحساب) — زرّ الاختبار يعمل في الحالتين.
            </div>
          </span>
        </button>

        <div style={lbl}>رابط اللوحة</div>
        <input dir="ltr" value={f.base_url} onChange={(e) => set("base_url", e.target.value)} style={darkInp}
          placeholder="https://bayi.example.com" />
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
          <div>
            <div style={lbl}>اسم المستخدم</div>
            <input dir="ltr" value={f.username} onChange={(e) => set("username", e.target.value)} style={darkInp} autoComplete="off" />
          </div>
          <div>
            <div style={lbl}>كلمة المرور {cfg?.has_password && <span style={{ color: "#4ade80" }}>(محفوظة — اتركها فارغة لإبقائها)</span>}</div>
            <input dir="ltr" type="password" value={f.password} onChange={(e) => set("password", e.target.value)} style={darkInp}
              autoComplete="new-password" placeholder={cfg?.has_password ? "••••••••" : ""} />
          </div>
        </div>
        <div style={lbl}>حرف الصورة الأمنية</div>
        <div style={{ display: "flex", gap: 14, alignItems: "center" }}>
          <input dir="ltr" value={f.security_image} maxLength={10}
            onChange={(e) => set("security_image", e.target.value.toUpperCase().replace(/[^A-Z0-9]/g, ""))}
            style={{ ...darkInp, width: 90, textAlign: "center", fontWeight: 800, fontSize: 18, flex: "none" }} />
          <div style={{ fontSize: 12.5, color: "#94a3b8", lineHeight: 1.8 }}>
            بعد كلمة المرور تعرض لوحة ZNET عدّة صور وتطلب الضغط على الصورة التي اخترتها عند إعداد الحساب.
            كل صورة ملفٌّ اسمه حرف (A.png · B.png · D.png…) — اكتب هنا <b style={{ color: "#e2e8f0" }}>حرف صورتك</b> فقط
            ليضغطها النظام بدلاً منك. لا تعرفه؟ اضغط «اختبر الآن» وسيعرض لك الحروف المتاحة في اللوحة.
          </div>
        </div>
        <div style={{ display: "flex", gap: 10, alignItems: "center", marginTop: 18 }}>
          <button style={addBtn} onClick={save} disabled={busy !== ""}>{busy === "save" ? "جارٍ الحفظ..." : "حفظ"}</button>
          {msg && <span style={{ color: msg.ok ? "#4ade80" : "#f87171", fontSize: 13 }}>{msg.text}</span>}
        </div>
      </div>

      <div style={{ background: "#131c31", border: "1px solid #1e293b", borderRadius: 12, padding: 18, marginTop: 16 }}>
        <b>اختبار حيّ</b>
        <p style={{ color: "#94a3b8", fontSize: 13, margin: "6px 0 10px" }}>
          يدخل باللوحة ويجتاز الصورة الأمنية، ثم — إن كتبت رقماً — يكشف شركته ويعدّ عروضه. الدخول الأوّل يأخذ نصف دقيقة تقريباً.
        </p>
        <div style={{ display: "flex", gap: 10 }}>
          <input dir="ltr" value={gsm} onChange={(e) => setGsm(e.target.value)} placeholder="5XXXXXXXXX (اختياري)"
            style={{ ...darkInp, maxWidth: 240 }} />
          <button style={{ ...addBtn, background: "#0f766e" }} onClick={test} disabled={busy !== ""}>
            {busy === "test" ? "جارٍ الاختبار..." : "اختبر الآن"}
          </button>
        </div>
        {steps && (
          <div style={{ marginTop: 14, display: "grid", gap: 6 }}>
            {steps.map((s, i) => (
              <div key={i} style={{ display: "flex", gap: 10, alignItems: "baseline", fontSize: 13.5 }}>
                <span style={{ color: s.ok ? "#4ade80" : "#f87171", fontWeight: 800 }}>{s.ok ? "✓" : "✗"}</span>
                <span style={{ fontWeight: 700 }}>{s.step}</span>
                {s.detail && <span style={{ color: "#94a3b8" }}>— {s.detail}</span>}
              </div>
            ))}
          </div>
        )}
      </div>

      <SorgulaCache inputStyle={darkInp} />
    </div>
  );
}

/** حفظ الكشف (الكاش): الشركة شهراً والعروض 24 ساعة — وتصفيره كلّه أو لرقمٍ واحد. */
function SorgulaCache({ inputStyle }: { inputStyle: React.CSSProperties }) {
  const [n, setN] = useState<{ operator: number; offers: number } | null>(null);
  const [gsm, setGsm] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const load = () => api.get("/platform/sorgula/cache/").then((r) => setN(r.data)).catch(() => {});
  useEffect(() => { load(); }, []);

  async function clear(kind: "all" | "operator" | "offers") {
    const what = kind === "all" ? "كل الحفظ" : kind === "operator" ? "حفظ كشف الشركات" : "حفظ العروض";
    if (!confirm(`تصفير ${what}${gsm.trim() ? ` للرقم ${gsm.trim()}` : " لكل الأرقام"}؟`)) return;
    setBusy(true); setMsg(null);
    try {
      const r = await api.delete("/platform/sorgula/cache/", { data: { kind, gsm: gsm.trim() } });
      setMsg({ ok: true, text: `✓ مُسح ${r.data.deleted} — الكشف التالي يُجلب من ZNET من جديد` });
      load();
    } catch (e: any) { setMsg({ ok: false, text: e?.response?.data?.detail || "تعذّر المسح" }); }
    finally { setBusy(false); }
  }

  const btn: React.CSSProperties = { ...addBtn, background: "#334155" };
  return (
    <div style={{ background: "#131c31", border: "1px solid #1e293b", borderRadius: 12, padding: 18, marginTop: 16 }}>
      <b>حفظ الكشف (الكاش)</b>
      <p style={{ color: "#94a3b8", fontSize: 13, margin: "6px 0 12px", lineHeight: 1.8 }}>
        كشف <b style={{ color: "#e2e8f0" }}>شركة الرقم</b> يُحفظ شهراً، و<b style={{ color: "#e2e8f0" }}>العروض</b> 24 ساعة —
        فيظهر الكشف المكرّر فوراً بلا سؤال ZNET. صفّره هنا متى شئت؛ اكتب رقماً لتصفيره وحده، أو اتركه فارغاً لكل الأرقام.
      </p>
      <div style={{ display: "flex", gap: 18, marginBottom: 12, fontSize: 13.5 }}>
        <span>📱 شركات محفوظة: <b style={{ color: "#e2e8f0" }}>{n ? n.operator : "…"}</b></span>
        <span>⚡ عروض محفوظة: <b style={{ color: "#e2e8f0" }}>{n ? n.offers : "…"}</b></span>
      </div>
      <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
        <input dir="ltr" value={gsm} onChange={(e) => setGsm(e.target.value)} placeholder="5XXXXXXXXX (اختياري)"
          style={{ ...inputStyle, maxWidth: 220 }} />
        <button style={{ ...addBtn, background: "#b91c1c" }} disabled={busy} onClick={() => clear("all")}>🗑 تصفير كل الحفظ</button>
        <button style={btn} disabled={busy} onClick={() => clear("operator")}>الشركات فقط</button>
        <button style={btn} disabled={busy} onClick={() => clear("offers")}>العروض فقط</button>
      </div>
      {msg && <div style={{ color: msg.ok ? "#4ade80" : "#f87171", fontSize: 13, marginTop: 10 }}>{msg.text}</div>}
    </div>
  );
}

/* ===== الفواتير ===== */
function BillingTab() {
  const [rows, setRows] = useState<any[]>([]);
  const [totals, setTotals] = useState<any>(null);
  const [filter, setFilter] = useState("all");

  function load() {
    const params: any = {};
    if (filter !== "all") params.status = filter;
    api.get("/platform/invoices/", { params }).then((r) => { setRows(r.data.results); setTotals(r.data.totals); });
  }
  useEffect(load, [filter]);

  async function mark(inv: any) {
    const action = inv.status === "paid" ? "unpaid" : "paid";
    await api.post(`/platform/invoices/${inv.id}/${action}/`, {});
    load();
  }

  return (
    <>
      <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 14 }}>
        <h2 style={{ fontSize: 18 }}>فواتير الاشتراكات</h2>
        <select value={filter} onChange={(e) => setFilter(e.target.value)} style={{ height: 34 }}>
          <option value="all">الكل</option>
          <option value="unpaid">غير مدفوعة</option>
          <option value="paid">مدفوعة</option>
        </select>
        {totals && (
          <span style={{ marginInlineStart: "auto", color: "#94a3b8", fontSize: 14 }}>
            {totals.count} فاتورة · غير مدفوعة: {totals.unpaid} · الإجمالي: {totals.total_amount}
          </span>
        )}
      </div>
      <div style={{ overflow: "hidden", borderRadius: 10, border: "1px solid #1e293b" }}>
        <table style={table}>
          <thead>
            <tr>{["#", "المتجر", "الخطة", "المبلغ", "الفترة", "الحالة", "إجراء"].map((h) => <th key={h} style={th}>{h}</th>)}</tr>
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <tr><td colSpan={7} style={{ ...td, color: "#64748b", padding: 24 }}>لا فواتير — تُنشأ عند تفعيل اشتراك.</td></tr>
            ) : rows.map((i) => (
              <tr key={i.id} style={{ borderTop: "1px solid #1e293b" }}>
                <td style={td}>{i.id}</td>
                <td style={{ ...td, fontWeight: 700 }}>{i.tenant_name}</td>
                <td style={td}>{i.plan_label}</td>
                <td style={{ ...td, color: "#7dd3fc", fontWeight: 700 }}>{i.amount}</td>
                <td style={{ ...td, color: "#94a3b8", fontSize: 12, direction: "ltr" }}>{i.period_start} → {i.period_end}</td>
                <td style={td}>
                  <span style={{ color: i.status === "paid" ? "#4ade80" : "#f87171", fontWeight: 700 }}>
                    ● {i.status_label}
                  </span>
                </td>
                <td style={td}>
                  <button style={i.status === "paid" ? suspendBtn : activateBtn} onClick={() => mark(i)}>
                    {i.status === "paid" ? "إلغاء الدفع" : "تعليم مدفوعة"}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

function SubscriptionModal({ tenant, onClose, onDone }: { tenant: Tenant; onClose: () => void; onDone: () => void }) {
  const [monthly, setMonthly] = useState(tenant.sub_monthly_price);
  const [yearly, setYearly] = useState(tenant.sub_yearly_price);
  const t = tenant;
  const [busy, setBusy] = useState("");
  const [grace, setGrace] = useState(String(tenant.sub_grace_days ?? 3));
  const [enforce, setEnforce] = useState(tenant.sub_enforce !== false);
  const [expires, setExpires] = useState(tenant.sub_expires_at || "");

  async function call(body: any, tag: string) {
    setBusy(tag);
    try {
      await api.post(`/platform/tenants/${tenant.id}/subscription/`, body);
      onDone();   // الحفظ ينجح ⇐ تُغلق النافذة وتُحدَّث قائمة المتاجر
    }
    catch (e: any) { alert(e?.response?.data?.detail || "تعذّر الحفظ"); }
    finally { setBusy(""); }
  }

  return (
    <div style={overlay} onClick={onClose}>
      <div style={{ ...modal, width: 460, color: "#0f172a" }} onClick={(e) => e.stopPropagation()}>
        <div style={{ background: "#0f172a", color: "#e2e8f0", padding: "14px 18px", fontWeight: 700, fontSize: 16 }}>
          اشتراك: {tenant.name}
        </div>
        <div style={{ padding: 20 }}>
          <div style={{
            background: SUB_TONE[t.sub_state || "ok"].bg, color: SUB_TONE[t.sub_state || "ok"].fg,
            borderRadius: 8, padding: "12px 14px", marginBottom: 16, fontSize: 14, lineHeight: 1.9,
          }}>
            <b>{SUB_TONE[t.sub_state || "ok"].label}</b>
            {t.sub_expires_at
              ? <> · {t.sub_plan_label} · تنتهي في <b>{t.sub_expires_at}</b>
                  {typeof t.sub_days_left === "number" && (
                    t.sub_days_left >= 0
                      ? <> (متبقٍّ {t.sub_days_left} يوم)</>
                      : <> (مضى {-t.sub_days_left} يوم على الانتهاء)</>
                  )}</>
              : <> · لم يُفعّل اشتراك بعد</>}
            {!t.sub_enforce && (
              <div style={{ fontSize: 12.5, marginTop: 4 }}>
                ⚠ مُعفَى من المنع — لا يتوقّف شراؤه مهما انتهى
              </div>
            )}
          </div>

          <div style={{ fontWeight: 700, marginBottom: 8 }}>أسعار هذا المتجر</div>
          <div style={{ display: "flex", gap: 12, marginBottom: 6 }}>
            <F label="السعر الشهري"><input style={inp} type="number" step="0.01" value={monthly} onChange={(e) => setMonthly(e.target.value)} /></F>
            <F label="السعر السنوي"><input style={inp} type="number" step="0.01" value={yearly} onChange={(e) => setYearly(e.target.value)} /></F>
          </div>
          <button className="btn" style={{ background: "#475569", color: "#fff", height: 36, width: "100%" }}
            disabled={busy === "prices"}
            onClick={() => call({ op: "prices", monthly_price: monthly, yearly_price: yearly }, "prices")}>
            {busy === "prices" ? "..." : "حفظ الأسعار"}
          </button>

          <div style={{ fontWeight: 700, margin: "18px 0 8px" }}>تفعيل / تجديد</div>
          <div style={{ display: "flex", gap: 10 }}>
            <button className="btn g" style={{ flex: 1, height: 40 }} disabled={busy === "monthly"}
              onClick={() => call({ op: "activate", plan: "monthly" }, "monthly")}>
              شهري (+30 يوم)
            </button>
            <button className="btn g" style={{ flex: 1, height: 40 }} disabled={busy === "yearly"}
              onClick={() => call({ op: "activate", plan: "yearly" }, "yearly")}>
              سنوي (+365 يوم)
            </button>
          </div>
          <div style={{ fontWeight: 700, margin: "18px 0 8px" }}>سياسة الانتهاء</div>
          <div style={{ display: "flex", gap: 12, alignItems: "flex-end" }}>
            <F label="أيام السماح">
              <input style={inp} type="number" min="0" max="90" value={grace}
                onChange={(e) => setGrace(e.target.value)} />
            </F>
            <F label="تاريخ الانتهاء (ضبط يدويّ)">
              <input style={inp} type="date" value={expires}
                onChange={(e) => setExpires(e.target.value)} />
            </F>
          </div>
          <label style={{ display: "flex", gap: 8, alignItems: "center", margin: "10px 2px", fontSize: 13, cursor: "pointer" }}>
            <input type="checkbox" checked={!enforce} onChange={(e) => setEnforce(!e.target.checked)} />
            أعفِ هذا المتجر من المنع نهائياً
          </label>
          <div style={{ fontSize: 12, color: "#64748b", lineHeight: 1.9, marginBottom: 10 }}>
            بعد الانتهاء يبقى كل شيء يعمل طوال مهلة السماح، ثم
            <b> يتوقّف الشراء وحده</b> — وتبقى اللوحة والتقارير والمحافظ والدخول.
          </div>
          <button className="btn" style={{ width: "100%", height: 36, background: "#475569", color: "#fff" }}
            disabled={busy === "policy"}
            onClick={async () => {
              await call({ op: "policy", grace_days: grace, enforce }, "policy");
              if (expires !== (t.sub_expires_at || "")) {
                await call({ op: "expires", expires_at: expires }, "policy");
              }
            }}>
            {busy === "policy" ? "..." : "حفظ السياسة"}
          </button>

          <div style={{ display: "flex", gap: 10, marginTop: 16 }}>
            <button className="btn" style={{ flex: 1, height: 38, background: "#7f1d1d", color: "#fecaca" }} disabled={busy === "cancel"}
              onClick={() => call({ op: "cancel" }, "cancel")}>إلغاء الاشتراك</button>
            <button className="btn" style={{ flex: 1, height: 38, background: "#8a999e" }} onClick={onDone}>تم</button>
          </div>
        </div>
      </div>
    </div>
  );
}

function StatCard({ label, value, icon }: { label: string; value: number; icon: string }) {
  return (
    <div style={{ flex: 1, background: "#1e293b", borderRadius: 12, padding: "18px 20px" }}>
      <div style={{ fontSize: 26 }}>{icon}</div>
      <div style={{ fontSize: 30, fontWeight: 800, marginTop: 6 }}>{value}</div>
      <div style={{ color: "#94a3b8", fontSize: 14 }}>{label}</div>
    </div>
  );
}

function CreateTenant({ onClose, onDone }: { onClose: () => void; onDone: () => void }) {
  const [f, setF] = useState({ name: "", subdomain: "", admin_login_id: "", admin_password: "", admin_name: "", theme: "teal" });
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true); setErr("");
    try { await api.post("/platform/tenants/", f); onDone(); }
    catch (e: any) { setErr(e?.response?.data?.detail || "فشل الإنشاء"); }
    finally { setBusy(false); }
  }
  const set = (k: string, v: string) => setF({ ...f, [k]: v });

  return (
    <div style={overlay} onClick={onClose}>
      <form style={modal} onClick={(e) => e.stopPropagation()} onSubmit={submit}>
        <div style={{ background: "#0f172a", padding: "14px 18px", fontWeight: 700, fontSize: 16 }}>
          إضافة مستأجر جديد (بيع نسخة)
        </div>
        <div style={{ padding: 20, color: "#0f172a" }}>
          <F label="اسم المتجر"><input style={inp} value={f.name} onChange={(e) => set("name", e.target.value)} required /></F>
          <F label="النطاق الفرعي"><input style={inp} value={f.subdomain} onChange={(e) => set("subdomain", e.target.value)} placeholder="barakat" required /></F>
          <F label="اسم مدير المتجر"><input style={inp} value={f.admin_name} onChange={(e) => set("admin_name", e.target.value)} /></F>
          <F label="رقم دخول المدير"><input style={inp} value={f.admin_login_id} onChange={(e) => set("admin_login_id", e.target.value)} required /></F>
          <F label="كلمة مرور المدير"><input style={inp} type="text" value={f.admin_password} onChange={(e) => set("admin_password", e.target.value)} required /></F>
          <F label="الثيم">
            <select value={f.theme} onChange={(e) => set("theme", e.target.value)}>
              <option value="teal">أخضر مزرق</option><option value="blue">أزرق</option><option value="orange">برتقالي</option>
            </select>
          </F>
          {err && <div style={errBox}>{err}</div>}
          <div style={{ display: "flex", gap: 10, marginTop: 16 }}>
            <button className="btn g" style={{ flex: 1, height: 40 }} disabled={busy}>{busy ? "جارٍ..." : "إنشاء المستأجر"}</button>
            <button type="button" className="btn" style={{ height: 40, background: "#8a999e" }} onClick={onClose}>إلغاء</button>
          </div>
        </div>
      </form>
    </div>
  );
}

function F({ label, children }: { label: string; children: React.ReactNode }) {
  return <div style={{ marginBottom: 10 }}><div style={{ fontSize: 12, color: "#64748b", marginBottom: 4 }}>{label}</div>{children}</div>;
}
function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return <div><div style={{ fontSize: 11, color: "#64748b", marginBottom: 3 }}>{label}</div>{children}</div>;
}

const header: React.CSSProperties = {
  display: "flex", alignItems: "center", justifyContent: "space-between",
  background: "#1e293b", padding: "14px 24px", borderBottom: "1px solid #334155",
};
const subnav: React.CSSProperties = { display: "flex", gap: 4, background: "#131c31", padding: "0 24px", borderBottom: "1px solid #1e293b" };
const tabBtn: React.CSSProperties = { background: "transparent", border: 0, color: "#94a3b8", padding: "12px 18px", fontSize: 14, cursor: "pointer", borderBottom: "3px solid transparent" };
const tabActive: React.CSSProperties = { color: "#e2e8f0", borderBottom: "3px solid #2563eb", fontWeight: 700 };
const logoutBtn: React.CSSProperties = {
  background: "transparent", border: "1px solid #475569", color: "#e2e8f0", padding: "6px 12px", borderRadius: 5,
};
const table: React.CSSProperties = { width: "100%", borderCollapse: "collapse", background: "#0f172a", fontSize: 14 };
const th: React.CSSProperties = { background: "#1e293b", color: "#94a3b8", padding: "12px 8px", textAlign: "center", fontWeight: 600 };
const td: React.CSSProperties = { padding: "12px 8px", textAlign: "center" };
const addBtn: React.CSSProperties = { background: "#2563eb", color: "#fff", border: 0, padding: "8px 16px", borderRadius: 6, fontWeight: 600, cursor: "pointer" };
const pkgBtn: React.CSSProperties = { background: "#1d4ed8", color: "#dbeafe", border: 0, padding: "5px 12px", borderRadius: 5, marginInlineEnd: 6, cursor: "pointer" };
const subBtn: React.CSSProperties = { background: "#7c3aed", color: "#ede9fe", border: 0, padding: "5px 12px", borderRadius: 5, marginInlineEnd: 6, cursor: "pointer" };
const editBtn: React.CSSProperties = { background: "#a16207", color: "#fef3c7", border: 0, padding: "5px 12px", borderRadius: 5, marginInlineEnd: 6, cursor: "pointer" };
const suspendBtn: React.CSSProperties = { background: "#7f1d1d", color: "#fecaca", border: 0, padding: "5px 12px", borderRadius: 5, cursor: "pointer" };
const activateBtn: React.CSSProperties = { background: "#14532d", color: "#bbf7d0", border: 0, padding: "5px 12px", borderRadius: 5, cursor: "pointer" };
const overlay: React.CSSProperties = { position: "fixed", inset: 0, background: "rgba(0,0,0,.6)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 1000 };
const modal: React.CSSProperties = { width: 420, background: "#fff", color: "#0f172a", borderRadius: 10, overflow: "hidden" };
const inp: React.CSSProperties = { width: "100%", height: 38 };
const errBox: React.CSSProperties = { background: "#fdecea", border: "1px solid #f5c6c2", color: "#b0463a", fontSize: 13, padding: "9px 12px", borderRadius: 5, marginTop: 10 };

/** تعديل اسم المتجر ونطاقه. النطاق **تسمية واحدة** لا عنوان كامل. */
function EditTenant({ tenant, onClose, onDone }: {
  tenant: Tenant; onClose: () => void; onDone: () => void;
}) {
  const [name, setName] = useState(tenant.name);
  const [sub, setSub] = useState(tenant.subdomain);
  const [pw, setPw] = useState("");
  const [showPw, setShowPw] = useState(false);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true); setErr("");
    try {
      // الكلمة الفارغة لا تُرسل أصلاً: «احفظ الاسم» لا يعني «بدّل الكلمة».
      await api.patch(`/platform/tenants/${tenant.id}/`, {
        name, subdomain: sub, ...(pw ? { admin_password: pw } : {}),
      });
      onDone();
    } catch (e: any) {
      setErr(e?.response?.data?.detail || "تعذّر الحفظ");
    } finally { setBusy(false); }
  }

  return (
    <div style={overlay} onClick={onClose}>
      <form style={{ ...modal, width: 420, color: "#0f172a", maxHeight: "90vh", overflowY: "auto" }}
        onClick={(e) => e.stopPropagation()} onSubmit={save}>
        <div style={{ background: "#0f172a", color: "#e2e8f0", padding: "14px 18px", fontWeight: 700 }}>
          تعديل المتجر
        </div>
        <div style={{ padding: 20 }}>
          <F label="اسم المتجر">
            <input style={inp} value={name} onChange={(e) => setName(e.target.value)} required />
          </F>
          <F label="النطاق الفرعي">
            <input style={inp} dir="ltr" value={sub}
              onChange={(e) => setSub(e.target.value)} required />
          </F>
          <div style={{ fontSize: 12, color: "#64748b", lineHeight: 1.9, marginTop: 6 }}>
            تسميةٌ واحدة لا عنوان كامل: اكتب <b>islam</b> لا <b>islam.wtn4.com</b>.
            حروف إنجليزية صغيرة وأرقام وشرطات فقط.
          </div>

          <div style={{ borderTop: "1px solid #e2e8f0", margin: "18px 0 14px" }} />
          <div style={{ fontWeight: 700, marginBottom: 8 }}>حساب صاحب المتجر</div>
          {tenant.admin_login_id ? (
            <>
              <div style={{ fontSize: 13, color: "#334155", marginBottom: 10 }}>
                رقم الدخول:{" "}
                <b dir="ltr" style={{ display: "inline-block" }}>{tenant.admin_login_id}</b>
                {tenant.admin_name ? ` · ${tenant.admin_name}` : ""}
                {tenant.admin_locked && (
                  <span style={{ color: "#b0463a" }}> · الحساب مقفل</span>
                )}
              </div>
              <F label="كلمة سرّ جديدة">
                <input style={inp} dir="ltr" type={showPw ? "text" : "password"}
                  autoComplete="new-password" value={pw}
                  onChange={(e) => setPw(e.target.value)} />
              </F>
              <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12, color: "#64748b", marginTop: 6 }}>
                <input type="checkbox" checked={showPw} onChange={(e) => setShowPw(e.target.checked)} />
                أظهر الكلمة
              </label>
              <div style={{ fontSize: 12, color: "#64748b", lineHeight: 1.9, marginTop: 6 }}>
                اتركها فارغة فلا تتغيّر. الكلمة القديمة لا تُعرَض — مخزَّنةٌ مُعمّاةً.
                والكلمة الجديدة تفتح الحساب إن كان مقفلاً.
              </div>
            </>
          ) : (
            <div style={{ fontSize: 12.5, color: "#b0463a", lineHeight: 1.9 }}>
              لا حساب صاحب متجر لهذا المتجر — لا كلمةَ سرّ تُبدَّل.
            </div>
          )}

          {err && <div style={{ ...errBox, marginTop: 12 }}>{err}</div>}
          <div style={{ display: "flex", gap: 10, marginTop: 18 }}>
            <button className="btn g" style={{ flex: 1, height: 38 }} disabled={busy}>
              {busy ? "..." : "حفظ"}
            </button>
            <button type="button" className="btn" style={{ flex: 1, height: 38, background: "#8a999e" }}
              onClick={onClose}>إلغاء</button>
          </div>
        </div>
      </form>
    </div>
  );
}

/**
 * حذف متجر — يمحو وكلاءه ومحافظهم ودفترهم وطلباتهم وفواتيرهم.
 * فلا يقع إلا بكتابة اسمه حرفاً: زرٌّ يُضغط بالخطأ، واسمٌ لا يُكتب بالخطأ.
 */
function DeleteTenant({ tenant, onClose, onDone }: {
  tenant: Tenant; onClose: () => void; onDone: () => void;
}) {
  const [typed, setTyped] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  async function remove() {
    setBusy(true); setErr("");
    try {
      await api.delete(`/platform/tenants/${tenant.id}/`, { data: { confirm: typed } });
      onDone();
    } catch (e: any) {
      setErr(e?.response?.data?.detail || "تعذّر الحذف");
    } finally { setBusy(false); }
  }

  return (
    <div style={overlay} onClick={onClose}>
      <div style={{ ...modal, width: 460, color: "#0f172a" }} onClick={(e) => e.stopPropagation()}>
        <div style={{ background: "#7f1d1d", color: "#fecaca", padding: "14px 18px", fontWeight: 700 }}>
          حذف «{tenant.name}» — لا رجعة
        </div>
        <div style={{ padding: 20 }}>
          <p style={{ fontSize: 13.5, lineHeight: 1.95, margin: "0 0 12px" }}>
            سيُمحى المتجر ومعه <b>{tenant.users ?? 0} حساباً</b> و
            <b> {tenant.orders ?? 0} طلباً</b>، ومحافظُهم ودفترُ حساباتهم وفواتيرهم.
            <br />
            <b>لا يمكن التراجع، ولا تُستعاد إلا من نسخة احتياطية.</b>
          </p>
          <div style={{ fontSize: 12.5, color: "#64748b", marginBottom: 6 }}>
            اكتب <b style={{ direction: "ltr", display: "inline-block" }}>{tenant.subdomain}</b> للتأكيد:
          </div>
          <input style={inp} dir="ltr" value={typed} onChange={(e) => setTyped(e.target.value)} />
          {err && <div style={{ ...errBox, marginTop: 12 }}>{err}</div>}
          <div style={{ display: "flex", gap: 10, marginTop: 18 }}>
            <button className="btn" disabled={busy || typed !== tenant.subdomain}
              style={{
                flex: 1, height: 38,
                background: typed === tenant.subdomain ? "#b91c1c" : "#cbd5e1",
                color: "#fff",
              }}
              onClick={remove}>{busy ? "..." : "احذف نهائياً"}</button>
            <button className="btn" style={{ flex: 1, height: 38, background: "#8a999e" }}
              onClick={onClose}>إلغاء</button>
          </div>
        </div>
      </div>
    </div>
  );
}
