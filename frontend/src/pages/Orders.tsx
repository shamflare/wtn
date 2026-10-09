import { Fragment, useEffect, useState } from "react";
import { api, type Order } from "../api";
import Icon from "../components/Icon";
import { useBaseSymbol } from "../currency";
import DateRange, { rangeText, TODAY } from "../components/DateRange";

// ألوان أيقونات الألعاب (حين لا توجد صورة)
const GCOLORS = ["#101418,#2c343d", "#5b21b6,#8b5cf6", "#b45309,#f59e0b", "#065f46,#10b981", "#9d174d,#ec4899"];
const gcolor = (name: string) => GCOLORS[(name?.charCodeAt(0) || 0) % GCOLORS.length];
const ginitials = (name: string) => (name || "?").split(" ").map((w) => w[0]).join("").slice(0, 2).toUpperCase();

const DOT: Record<string, string> = { pending: "wait", processing: "wait", success: "ok", cancelled: "err", stuck: "err" };

// خلفية الصفّ في لوحة المشغّل — ثلاث حالات حيّة، والمحسوم بلا لون:
//   أصفر  = ينتظر قرارك      · أزرق = عند المزوّد، ليس دورك
//   رملي  = عالق، فشل التوجيه فيحتاج تدخّلك
const ROW_TONE: Record<string, string> = {
  pending: "row-wait", processing: "row-sent", stuck: "row-stuck",
};

interface Opt { id: number; name: string; game?: number }

// القائمة تفتح على طلبات اليوم — والفترة تُغيَّر من شريط التاريخ أعلاها
const EMPTY = { game: "", product: "", dealer: "", provider: "", q: "", phone: "", min: "", max: "", player: "", ...TODAY };

export default function Orders() {
  const cur = useBaseSymbol();
  const [orders, setOrders] = useState<Order[]>([]);
  const [status, setStatus] = useState("all");
  const [f, setF] = useState({ ...EMPTY });
  const [loading, setLoading] = useState(true);
  const [olderOpen, setOlderOpen] = useState(0);
  const [expanded, setExpanded] = useState<number | null>(null);
  // لوحة الفلاتر مطويّة افتراضياً — الجدول هو المقصود، لا نموذج البحث
  const [showFilters, setShowFilters] = useState(false);
  const [games, setGames] = useState<Opt[]>([]);
  const [products, setProducts] = useState<Opt[]>([]);
  const [dealers, setDealers] = useState<Opt[]>([]);
  const [providers, setProviders] = useState<Opt[]>([]);
  // حلقة المراقبة: تتابع الطلبات "قيد التنفيذ" لدى مزوّديها
  const [watch, setWatch] = useState(true);
  const [lastSync, setLastSync] = useState("");
  const [trace, setTrace] = useState<number | null>(null);
  // إجراءات المشغّل الجماعية على الطلبات المحدَّدة (Toplu İşlem)
  const [picked, setPicked] = useState<number[]>([]);
  const [bulkNote, setBulkNote] = useState("");
  const [bulkProvider, setBulkProvider] = useState("");
  const [bulkBusy, setBulkBusy] = useState("");
  const [bulkMsg, setBulkMsg] = useState<{ ok: boolean; text: string } | null>(null);

  function load(st = status, filters = f) {
    setLoading(true);
    const params: any = { status: st };
    Object.entries(filters).forEach(([k, v]) => { if (v) params[k] = v; });
    api.get("/orders/", { params })
      .then((r) => { setOrders(r.data.results); setOlderOpen(r.data.older_open || 0); })
      .finally(() => setLoading(false));
  }

  /** يعيد جلب القائمة بصمت — بلا وميض "جارٍ التحميل". */
  function refreshQuiet() {
    const params: any = { status };
    Object.entries(f).forEach(([k, v]) => { if (v) params[k] = v; });
    api.get("/orders/", { params }).then((r) => setOrders(r.data.results));
  }

  useEffect(() => {
    load();
    api.get("/catalog/games/").then((r) => setGames(r.data.results || r.data));
    api.get("/catalog/products/").then((r) => setProducts((r.data.results || r.data).map((p: any) => ({ id: p.id, name: p.name, game: p.game }))));
    api.get("/dealers/").then((r) => setDealers(r.data.results));
    api.get("/providers/").then((r) => setProviders(r.data.results || r.data));
  }, []);

  // كل 6 ثوانٍ: ما دام هناك طلب "قيد التنفيذ"، اسأل مزوّده عن نتيجته
  const pendingCount = orders.filter((o) => o.status === "processing").length;
  useEffect(() => {
    if (!watch || pendingCount === 0) return;
    const t = setInterval(async () => {
      try {
        const r = await api.post("/orders/sync-pending/", {});
        setLastSync(new Date().toLocaleTimeString("en-GB"));
        if (r.data.changed > 0) refreshQuiet();
      } catch {
        /* تجاهل فشل نبضة واحدة — النبضة التالية تعيد المحاولة */
      }
    }, 6000);
    return () => clearInterval(t);
  }, [watch, pendingCount, status, f]);

  function setStatusAndLoad(st: string) {
    setStatus(st); setPicked([]); setBulkMsg(null); load(st);
  }
  function clearFilters() {
    setF({ ...EMPTY }); setStatus("all"); setPicked([]); load("all", { ...EMPTY });
  }

  /**
   * وضع الإجراءات تابع لفلتر الحالة:
   * • الكرة الخضراء (ناجح)  → عكس قرار: **إبطال** فقط.
   * • الكرة الحمراء (ملغى) → عكس قرار: **قبول** فقط (ويُعاد خصم المبلغ).
   * • غير ذلك → التصرّف بطلب لم يُحسَم: توجيه · إعادة ليدوي · قبول · رفض.
   */
  const mode: "revoke" | "restore" | "open" =
    status === "success" ? "revoke" : status === "cancelled" ? "restore" : "open";

  /**
   * الطلب المحسوم لا يُحدَّد إلا في وضع عكس القرار الموافق لحالته.
   * أمّا «قيد التنفيذ» فيُحدَّد: قد يتأخّر المزوّد أو يعلق، فيسحب المشغّل
   * الطلب من يده ويقبله أو يرفضه أو يعيده يدوياً.
   */
  const selectable = (o: Order) =>
    mode === "revoke" ? o.status === "success"
      : mode === "restore" ? o.status === "cancelled"
        : ["pending", "processing", "stuck"].includes(o.status);

  const toggleOne = (id: number) =>
    setPicked((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]));
  const pickable = orders.filter(selectable);
  const allPicked = pickable.length > 0 && picked.length === pickable.length;
  const toggleAll = () => setPicked(allPicked ? [] : pickable.map((o) => o.id));

  /** إجراء جماعي على المحدَّد: قبول · رفض · توجيه لمزوّد · إعادة إلى يدوي. */
  async function bulk(action: "approve" | "reject" | "dispatch" | "manual") {
    if (picked.length === 0) return;
    if (action === "dispatch" && !bulkProvider) {
      setBulkMsg({ ok: false, text: "اختر مزوّداً من القائمة أولاً" });
      return;
    }
    setBulkBusy(action); setBulkMsg(null);
    try {
      const r = await api.post("/orders/bulk-action/", {
        orders: picked, action, note: bulkNote.trim(),
        ...(action === "dispatch" ? { provider: bulkProvider } : {}),
      });
      const failed = (r.data.results || []).filter((x: any) => !x.ok);
      setBulkMsg({
        ok: failed.length === 0,
        text: `تمّ على ${r.data.done} طلباً` +
          (failed.length
            ? ` · تعذّر على ${failed.length}: ` +
              failed.slice(0, 3).map((x: any) => `${x.receipt_no || x.order} (${x.detail})`).join(" · ")
            : ""),
      });
      setPicked([]); setBulkNote("");
      load();
    } catch (e: any) {
      setBulkMsg({ ok: false, text: e?.response?.data?.detail || "فشل تنفيذ الإجراء" });
    } finally { setBulkBusy(""); }
  }

  const money = (v: string) => Number(v).toLocaleString("en-US", { minimumFractionDigits: 2 });
  const set = (k: string, v: string) => setF((old) => ({ ...old, [k]: v }));
  // عدد الفلاتر المفعّلة — يظهر على الزر فلا تختفي فلترة قائمة عن العين
  const activeFilters = Object.entries(f).filter(([k, v]) => v && !k.startsWith("date_")).length;
  function setDates(d: { date_from: string; date_to: string }) {
    const next = { ...f, ...d };
    setF(next); setPicked([]); load(status, next);
  }
  const shownProducts = f.game ? products.filter((p) => String(p.game) === f.game) : products;

  return (
    <div style={{ maxWidth: 1340, margin: "0 auto", padding: "18px 16px 40px" }}>
      {/* ===== لوحة الفلاتر (بنية المرجع: Oyun-Pin İşlemeleri) ===== */}
      <div className="card">
        <div className="card-title">
          <Icon name="filter" size={16} style={{ color: "var(--primary)" }} /> عمليات Oyun-Pin — متابعة الطلبات
          <WatchBadge on={watch} count={pendingCount} lastSync={lastSync}
            onToggle={() => setWatch((v) => !v)} />
          {/* نقاط الفلترة السريعة بالحالة (مثل المرجع) */}
          <span style={{ marginInlineStart: "auto", display: "inline-flex", gap: 6, alignItems: "center" }}>
            {([["all", "#7d8f94", "الكل"], ["pending", "#e8b013", "قيد الانتظار"], ["success", "#35c245", "ناجح"],
               ["cancelled", "#dd4444", "ملغى"], ["stuck", "#8a5a00", "عالق"]] as [string, string, string][]).map(([k, c, t]) => (
              <button key={k} title={t} onClick={() => setStatusAndLoad(k)}
                style={{ ...qdot, background: c, outline: status === k ? "2px solid var(--primary)" : "none" }} />
            ))}
            <button onClick={() => setShowFilters((v) => !v)} style={filterToggle}
              title={showFilters ? "إخفاء الفلترة" : "إظهار الفلترة"}>
              <Icon name="filter" size={13} style={{ marginInlineEnd: 5, verticalAlign: -2 }} />
              فلتر
              {activeFilters > 0 && <span style={fcount}>{activeFilters}</span>}
              <span style={{ marginInlineStart: 5, fontSize: 10 }}>{showFilters ? "▲" : "▼"}</span>
            </button>
          </span>
        </div>
        {/* الفترة ظاهرة دائماً — القائمة تفتح على اليوم، فلا تُقرأ على أنها كل الطلبات */}
        <div style={{ padding: "10px 14px", borderBottom: "1px solid var(--border)", display: "flex",
          gap: 12, alignItems: "center", flexWrap: "wrap" }}>
          <DateRange value={f} onChange={setDates} />
          <span style={{ fontSize: 12.5, color: "var(--muted)" }}>
            المعروض: <b style={{ color: "var(--text)" }}>{rangeText(f)}</b>
          </span>
          {olderOpen > 0 && (
            <button className="btn" style={{ height: 30, fontSize: 12.5, background: "#b45309" }}
              onClick={() => {
                const next = { ...f, date_from: "", date_to: "" };
                setF(next); setStatus("pending"); setPicked([]); load("pending", next);
              }}>
              <Icon name="warning" size={13} style={{ marginInlineEnd: 5, verticalAlign: -2 }} />
              {olderOpen} طلب معلّق من أيام سابقة — عرضها
            </button>
          )}
        </div>
        {showFilters && (
        <div style={fgrid}>
          <Field label="اللعبة">
            <select value={f.game} onChange={(e) => setF((o) => ({ ...o, game: e.target.value, product: "" }))} style={inp}>
              <option value="">اختر من فضلك</option>
              {games.map((g) => <option key={g.id} value={g.id}>{g.name}</option>)}
            </select>
          </Field>
          <Field label="المنتج">
            <select value={f.product} onChange={(e) => set("product", e.target.value)} style={inp}>
              <option value="">اختر من فضلك</option>
              {shownProducts.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select>
          </Field>
          <Field label="الوكيل">
            <select value={f.dealer} onChange={(e) => set("dealer", e.target.value)} style={inp}>
              <option value="">اختر من فضلك</option>
              {dealers.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
            </select>
          </Field>
          <Field label="API">
            <select value={f.provider} onChange={(e) => set("provider", e.target.value)} style={inp}>
              <option value="">اختر من فضلك</option>
              {providers.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select>
          </Field>
          <Field label="رقم الفيش"><input value={f.q} onChange={(e) => set("q", e.target.value)} style={inp} /></Field>
          <Field label="هاتف المشترك"><input value={f.phone} onChange={(e) => set("phone", e.target.value)} style={inp} /></Field>
          <Field label="أقل مبلغ"><input type="number" value={f.min} onChange={(e) => set("min", e.target.value)} style={inp} /></Field>
          <Field label="أعلى مبلغ"><input type="number" value={f.max} onChange={(e) => set("max", e.target.value)} style={inp} /></Field>
          <Field label="معرّف اللاعب"><input value={f.player} onChange={(e) => set("player", e.target.value)} style={inp} /></Field>
          <div style={{ display: "flex", gap: 8, alignItems: "flex-end", gridColumn: "span 2" }}>
            <button className="btn g" style={{ height: 36, flex: 1 }} onClick={() => load()}>
              <Icon name="filter" size={14} style={{ marginInlineEnd: 5, verticalAlign: -2 }} />فلترة
            </button>
            <button className="btn r" style={{ height: 36, flex: 1 }} onClick={clearFilters}>إزالة الفلتر</button>
          </div>
        </div>
        )}
      </div>

      {/* ===== إجراءات المشغّل على المحدَّد (Toplu İşlem) — تظهر عند التحديد ===== */}
      {picked.length > 0 && (
        <div className="card" style={bulkBar}>
          <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
            <b style={{ fontSize: 13.5, whiteSpace: "nowrap" }}>
              محدَّد: <span style={{ color: "var(--primary)" }}>{picked.length}</span>
            </b>
            <input value={bulkNote} onChange={(e) => setBulkNote(e.target.value)}
              placeholder="ملاحظة للوكيل (سبب القبول أو الرفض) — اختيارية"
              style={{ ...inp, flex: "1 1 260px", height: 34 }} />

            {mode === "open" && (
              <>
                <select value={bulkProvider} onChange={(e) => setBulkProvider(e.target.value)}
                  style={{ ...inp, width: 170, height: 34 }}>
                  <option value="">اختر مزوّداً…</option>
                  {providers.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
                </select>
                <button className="btn" style={bulkBtn("#c1692a")} disabled={!!bulkBusy}
                  onClick={() => bulk("dispatch")} title="إرسال الطلب إلى المزوّد المختار">
                  {bulkBusy === "dispatch" ? "جارٍ التوجيه..." : "توجيه للمزوّد"}
                </button>
                <button className="btn" style={bulkBtn("#7d8f94")} disabled={!!bulkBusy}
                  onClick={() => bulk("manual")} title="فكّ الطلب عن مزوّده وإعادته قيد الانتظار">
                  {bulkBusy === "manual" ? "جارٍ..." : "إعادة إلى يدوي"}
                </button>
              </>
            )}

            {mode !== "revoke" && (
              <button className="btn g" style={{ height: 34 }} disabled={!!bulkBusy}
                onClick={() => bulk("approve")}
                title={mode === "restore"
                  ? "إعادة قبول الطلب — يُعاد خصم المبلغ من محفظة الوكيل"
                  : "تنفيذ يدوي — يصير الطلب ناجحاً"}>
                {bulkBusy === "approve" ? "جارٍ..." : mode === "restore" ? "قبول الطلب" : "قبول"}
              </button>
            )}
            {mode !== "restore" && (
              <button className="btn r" style={{ height: 34 }} disabled={!!bulkBusy}
                onClick={() => bulk("reject")} title="إلغاء واسترجاع المبلغ للوكيل">
                {bulkBusy === "reject" ? "جارٍ..." : mode === "revoke" ? "إبطال الطلب" : "رفض"}
              </button>
            )}
            <button className="btn" style={bulkBtn("#8a999e")} onClick={() => setPicked([])}>
              إلغاء التحديد
            </button>
          </div>
          <div style={{ fontSize: 12, color: "var(--muted)", marginTop: 8 }}>
            {mode === "revoke" ? (
              <>عكس قرار: هذه طلبات <b>ناجحة</b> — إبطالها يسترجع المبلغ لمحفظة الوكيل.</>
            ) : mode === "restore" ? (
              <>عكس قرار: هذه طلبات <b>ملغاة</b> — قبولها <b>يعيد خصم المبلغ</b> من
                محفظة الوكيل، لأن الإلغاء كان قد أرجعه.</>
            ) : (
              <>«توجيه للمزوّد» يعمل على الطلبات <b>قيد الانتظار</b> أو <b>العالقة</b> فقط —
                لأن الطلب <b>قيد التنفيذ</b> موجود لدى مزوّد فعلاً؛ أعِده إلى يدوي أولاً
                ثم وجّهه إلى مزوّد آخر. وأي إجراء تتّخذه على طلب قيد التنفيذ يُخرجه من
                حلقة المراقبة فوراً فلا يعود المزوّد يغيّر حالته.</>
            )}
          </div>
          {bulkMsg && (
            <div style={{
              marginTop: 8, fontSize: 12.5, padding: "7px 10px", borderRadius: 6,
              background: bulkMsg.ok ? "rgba(53,194,69,.10)" : "rgba(221,68,68,.10)",
              color: bulkMsg.ok ? "var(--ok)" : "var(--danger)",
            }}>{bulkMsg.text}</div>
          )}
        </div>
      )}

      {/* ===== الجدول (أعمدة المرجع الـ13 + إجراء) — النمط المعتمد ===== */}
      <div className="card">
        <div className="table-scroll">
          <table className="grid">
            <thead>
              <tr>
                <th>
                  <input type="checkbox" title="تحديد الكل" checked={allPicked}
                    onChange={toggleAll} disabled={pickable.length === 0} />
                </th>
                <th>اللعبة</th>
                <th>رقم الفيش</th>
                <th>الوكيل</th>
                <th className="cell-start">اسم المنتج</th>
                <th>هاتف الزبون / معرّف اللاعب</th>
                <th>الشراء</th>
                <th>البيع</th>
                <th>الربح</th>
                <th>حالة العملية</th>
                <th>طباعة / SMS</th>
                <th>API</th>
                <th>إجراء</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan={13} style={{ padding: 26, color: "var(--muted)" }}>جارٍ التحميل...</td></tr>
              ) : orders.length === 0 ? (
                <tr><td colSpan={13} style={{ padding: 26, color: "var(--muted)" }}>لا توجد طلبات</td></tr>
              ) : orders.map((o) => (
                <Fragment key={o.id}>
                  <tr className={[ROW_TONE[o.status] || "", picked.includes(o.id) ? "row-pick" : ""]
                    .filter(Boolean).join(" ")}>
                    <td>
                      {/* الطلب المحسوم بلا مربّع — إلا في وضع عكس القرار */}
                      {selectable(o) && (
                        <input type="checkbox" checked={picked.includes(o.id)}
                          onChange={() => toggleOne(o.id)} />
                      )}
                    </td>
                    <td><span className="gicon" style={{ background: `linear-gradient(135deg,${gcolor(o.game_name)})` }}>{ginitials(o.game_name)}</span></td>
                    <td className="num" style={{ color: "var(--primary-dark)", fontWeight: 700, cursor: "pointer" }}
                      onClick={() => setExpanded(expanded === o.id ? null : o.id)} title="عرض التفاصيل">
                      {o.receipt_no}
                    </td>
                    <td>{o.dealer_name}</td>
                    <td className="cell-start" style={{ fontWeight: 600 }}>
                      {o.product_name}
                      {(o as any).quantity > 1 && (
                        <span style={{ color: "#7c3aed", fontWeight: 800, marginInlineStart: 4 }} dir="ltr">
                          × {Number((o as any).quantity).toLocaleString("en-US")}
                        </span>
                      )}
                    </td>
                    <td className="num" style={{ lineHeight: 1.35 }}>
                      {o.customer_phone || "—"}<br />
                      <span style={{ color: "var(--faint)" }}>{o.player_id || "—"}</span>
                    </td>
                    <td className="buy num">{money(o.cost_price)} {cur}</td>
                    <td className="sell num">{money(o.sell_price)} {cur}</td>
                    <td className="profit num"
                      style={Number(o.profit) < 0 ? { color: "var(--danger)", fontWeight: 800 } : undefined}
                      title={Number(o.profit) < 0 ? "خسارة — تكلفة المزوّد أعلى من سعر البيع" : undefined}>
                      {money(o.profit)} {cur}
                    </td>
                    <td>
                      {o.status === "pending" || o.status === "processing" ? (
                        <span className={`stspin${o.status === "processing" ? " proc" : ""}`} title={o.status_label} />
                      ) : (
                        <span className={`stdot ${DOT[o.status] || "wait"}`} title={o.status_label} />
                      )}
                    </td>
                    <td>
                      <div style={{ display: "flex", gap: 4, justifyContent: "center" }}>
                        <MiniBtn name="print" title="طباعة" />
                        <MiniBtn name="chat" title="إرسال SMS" />
                      </div>
                    </td>
                    {/* بلا مزوّد = تنفيذ يدوي — أصرح من شرطة تحتمل معنيين */}
                    <td style={{ color: o.provider_name ? "var(--muted)" : "var(--debt)" }}>
                      {o.provider_name || <b>يدوي</b>}
                    </td>
                    <td>
                      <div style={{ display: "flex", gap: 4, justifyContent: "center" }}>
                        {/* القبول والرفض والتوجيه كلّها من شريط الإجراءات بعد
                            التحديد — لا أزرار حاسمة داخل الصفّ تُضغط سهواً. */}
                        <MiniBtn name="details" color="var(--primary)" title="تفاصيل المسار"
                          onClick={() => setTrace(o.id)} />
                      </div>
                    </td>
                  </tr>
                  {expanded === o.id && (
                    <tr>
                      <td colSpan={13} className="cell-start" style={{ background: "var(--surface-2)", fontSize: 13 }}>
                        <b>تفاصيل الطلب:</b>{" "}
                        التاريخ: {o.created_at} · الرصيد قبل: {money(o.balance_before)} → بعد: {money(o.balance_after)}
                        {o.pin_result && <> · <b style={{ color: "var(--ok)" }}>PIN: {o.pin_result}</b></>}
                        {o.api_response && <> · رد النظام: {o.api_response}</>}
                        {o.provider_ref && <> · مرجع المزوّد: <code style={{ direction: "ltr" }}>{o.provider_ref}</code></>}
                        {o.provider_note && (
                          <> · <b style={{ color: "var(--primary)" }}>ملاحظة المزوّد: {o.provider_note}</b></>
                        )}
                        {o.dealer_note && (
                          <> · <b style={{ color: "var(--primary-dark)" }}>ملاحظتك للوكيل: {o.dealer_note}</b></>
                        )}
                        {o.last_sync_at && (
                          <> · آخر استعلام: {new Date(o.last_sync_at).toLocaleString("en-GB")}</>
                        )}
                      </td>
                    </tr>
                  )}
                </Fragment>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {trace !== null && (
        <TraceModal orderId={trace} onClose={() => setTrace(null)} onChanged={refreshQuiet} />
      )}
    </div>
  );
}

/** نافذة "تفاصيل المسار": هل وُجِّهت الباقة؟ لأي مزوّد؟ برقم ربط أي؟ وبأي ردّ؟ */
function TraceModal({
  orderId, onClose, onChanged,
}: { orderId: number; onClose: () => void; onChanged: () => void }) {
  const [data, setData] = useState<any>(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  function load() {
    api.get(`/orders/${orderId}/trace/`)
      .then((r) => setData(r.data))
      .catch((e) => setErr(e?.response?.data?.detail || "تعذّر جلب التفاصيل"));
  }
  useEffect(load, [orderId]);

  async function syncNow() {
    setBusy(true);
    try {
      await api.post(`/orders/${orderId}/sync/`, {});
      load();
      onChanged();
    } finally {
      setBusy(false);
    }
  }

  const o = data?.order;
  const ok = data?.routing_summary === "موجَّهة وجاهزة";

  return (
    <div style={ovl} onClick={onClose}>
      <div style={box} onClick={(e) => e.stopPropagation()}>
        <div style={boxHead}>
          تفاصيل المسار {o ? `— فيش ${o.receipt_no}` : ""}
          <button type="button" onClick={onClose} style={xBtn}>✕</button>
        </div>

        {err ? (
          <div style={{ padding: 20, color: "var(--danger)" }}>{err}</div>
        ) : !data ? (
          <div style={{ padding: 20, color: "var(--muted)" }}>جارٍ التحميل...</div>
        ) : (
          <div style={{ padding: 16, display: "grid", gap: 14 }}>
            {/* خلاصة التوجيه */}
            <div style={{
              padding: "9px 12px", borderRadius: 6, fontSize: 13, fontWeight: 700,
              background: ok ? "rgba(53,194,69,.10)" : "rgba(221,68,68,.10)",
              color: ok ? "var(--ok)" : "var(--danger)",
              border: `1px solid ${ok ? "rgba(53,194,69,.35)" : "rgba(221,68,68,.35)"}`,
            }}>
              {ok ? "✅" : "⚠"} {data.routing_summary}
            </div>

            <Grid2>
              <Cell k="الباقة" v={`${data.product.game} / ${data.product.name}`} />
              <Cell k="نوع التنفيذ" v={data.product.execution_type === "auto" ? "تلقائي" : "يدوي"} />
              <Cell k="الحالة" v={o.status_label} />
              <Cell k="المزوّد المستخدم" v={o.provider_name || "—"} />
              <Cell k="معرّف اللاعب" v={o.player_id || "—"} />
              <Cell k="المرجع لدى المزوّد" v={o.provider_ref || "—"} mono />
            </Grid2>

            {/* سلسلة التوجيه */}
            <div>
              <div style={ttl}>سلسلة التوجيه</div>
              <table className="grid" style={{ fontSize: 12.5 }}>
                <thead>
                  <tr><th>الخانة</th><th>المزوّد</th><th>رقم الربط</th><th>Küpür</th><th>الحالة</th></tr>
                </thead>
                <tbody>
                  {data.chain.map((c: any) => (
                    <tr key={c.slot} style={c.used ? { background: "rgba(53,194,69,.08)" } : undefined}>
                      <td>{c.slot}</td>
                      <td>{c.provider_name}</td>
                      <td style={{ direction: "ltr" }}>
                        {c.package_id ? <code>{c.package_id}</code> : "—"}
                        {c.package_name && (
                          <div style={{ fontSize: 11, color: "var(--muted)" }}>{c.package_name}</div>
                        )}
                      </td>
                      <td style={{ direction: "ltr" }}>{c.extra?.kupur || "—"}</td>
                      <td>
                        {!c.provider ? <span style={{ color: "var(--muted)" }}>مغلق</span>
                          : c.used ? <b style={{ color: "var(--ok)" }}>استُخدم</b>
                          : c.linked ? <span style={{ color: "var(--ok)" }}>مربوط</span>
                          : <span style={{ color: "var(--danger)" }}>بلا رقم ربط ⚠</span>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* ردّ المزوّد */}
            <div>
              <div style={ttl}>ردّ المزوّد</div>
              <pre style={pre}>{o.provider_note || "— لا ردّ مسجَّل —"}</pre>
              <div style={{ fontSize: 12.5, marginTop: 6 }}>
                <b>رد النظام:</b> {o.api_response || "—"}
              </div>
              {o.pin_result && (
                <div style={{ fontSize: 13, marginTop: 4, color: "var(--ok)" }}>
                  <b>PIN:</b> <code style={{ direction: "ltr" }}>{o.pin_result}</code>
                </div>
              )}
              <div style={{ fontSize: 12, color: "var(--muted)", marginTop: 6 }}>
                آخر استعلام: {o.last_sync_at ? new Date(o.last_sync_at).toLocaleString("en-GB") : "لم يُستعلَم بعد"}
                {" · "}الرصيد قبل {o.balance_before} → بعد {o.balance_after}
              </div>
            </div>

            <div style={{ display: "flex", gap: 8 }}>
              <button className="btn g" onClick={syncNow} disabled={busy}>
                {busy ? "جارٍ الاستعلام..." : "استعلم من المزوّد الآن"}
              </button>
              <button className="btn" style={{ background: "#8a999e" }} onClick={onClose}>إغلاق</button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

const Grid2 = ({ children }: { children: React.ReactNode }) => (
  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "8px 18px" }}>{children}</div>
);
const Cell = ({ k, v, mono }: { k: string; v: string; mono?: boolean }) => (
  <div style={{ fontSize: 12.5 }}>
    <span style={{ color: "var(--muted)" }}>{k}: </span>
    <b style={mono ? { direction: "ltr", display: "inline-block" } : undefined}>{v}</b>
  </div>
);

const ovl: React.CSSProperties = {
  position: "fixed", inset: 0, background: "rgba(0,0,0,.45)", zIndex: 70,
  display: "flex", alignItems: "center", justifyContent: "center",
};
const box: React.CSSProperties = {
  background: "#fff", borderRadius: 8, width: 700, maxWidth: "94vw",
  maxHeight: "90vh", overflow: "auto", boxShadow: "0 10px 40px rgba(0,0,0,.3)",
};
const boxHead: React.CSSProperties = {
  background: "var(--primary)", color: "#fff", padding: "10px 16px",
  fontSize: 15, fontWeight: 700, display: "flex", justifyContent: "space-between",
};
const xBtn: React.CSSProperties = {
  background: "none", border: 0, color: "#fff", cursor: "pointer", fontSize: 15,
};
const ttl: React.CSSProperties = {
  fontSize: 12.5, fontWeight: 800, color: "var(--muted)", marginBottom: 6,
};
const pre: React.CSSProperties = {
  background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: 6,
  padding: "8px 10px", fontSize: 12.5, direction: "ltr", textAlign: "left",
  whiteSpace: "pre-wrap", wordBreak: "break-all", margin: 0,
};

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <div style={{ fontSize: 12.5, color: "var(--muted)", fontWeight: 700, marginBottom: 4 }}>{label}</div>
      {children}
    </div>
  );
}

function MiniBtn({ name, title, color = "var(--muted)", onClick }:
  { name: string; title: string; color?: string; onClick?: () => void }) {
  return (
    <button onClick={onClick} title={title} style={{
      border: "1px solid var(--border)", background: "var(--surface)", color,
      width: 28, height: 28, borderRadius: 7, display: "inline-flex",
      alignItems: "center", justifyContent: "center", cursor: "pointer",
    }}>
      <Icon name={name} size={14} />
    </button>
  );
}

const fgrid: React.CSSProperties = {
  display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: "12px 16px", padding: 16,
};
const inp: React.CSSProperties = { width: "100%", height: 36, borderRadius: 8 };
const qdot: React.CSSProperties = {
  width: 16, height: 16, borderRadius: "50%", border: "1px solid rgba(0,0,0,.15)",
  cursor: "pointer", boxShadow: "inset 0 -2px 3px rgba(0,0,0,.2)",
};
const bulkBar: React.CSSProperties = {
  padding: "12px 14px", marginBottom: 12,
  borderInlineStart: "4px solid var(--primary)",
};
const bulkBtn = (bg: string): React.CSSProperties => ({ height: 34, background: bg });
const filterToggle: React.CSSProperties = {
  marginInlineStart: 10, background: "var(--surface)", border: "1px solid var(--border)",
  borderRadius: 6, color: "var(--text)", fontSize: 12.5, fontWeight: 700,
  padding: "5px 10px", cursor: "pointer", display: "inline-flex", alignItems: "center",
};
const fcount: React.CSSProperties = {
  background: "var(--primary)", color: "#fff", borderRadius: 9, fontSize: 10,
  fontWeight: 800, padding: "1px 6px", marginInlineStart: 5,
};


/** مؤشّر حلقة المراقبة: عدد الطلبات المتابَعة وآخر نبضة، مع مفتاح إيقاف. */
function WatchBadge({
  on, count, lastSync, onToggle,
}: { on: boolean; count: number; lastSync: string; onToggle: () => void }) {
  const active = on && count > 0;
  return (
    <button type="button" onClick={onToggle} title="متابعة الطلبات قيد التنفيذ لدى المزوّد كل 6 ثوانٍ"
      style={{
        display: "inline-flex", alignItems: "center", gap: 6, cursor: "pointer",
        border: "1px solid var(--border)", borderRadius: 20, padding: "3px 10px",
        fontSize: 12, background: active ? "rgba(0,150,80,.10)" : "transparent",
        color: active ? "var(--ok)" : "var(--muted)", marginInlineStart: 10,
      }}>
      <span style={{
        width: 8, height: 8, borderRadius: "50%",
        background: active ? "var(--ok)" : "#bbb",
        animation: active ? "pulse 1.4s ease-in-out infinite" : "none",
      }} />
      {!on ? "المراقبة موقوفة" : count === 0 ? "المراقبة جاهزة" : `يراقب ${count} طلباً`}
      {active && lastSync && <span style={{ opacity: 0.7 }}>· {lastSync}</span>}
    </button>
  );
}
