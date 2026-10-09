import { useEffect, useState } from "react";
import { api, type Provider } from "../api";
import Icon from "../components/Icon";
import { symbolOf, useBaseSymbol } from "../currency";

/** رقمٌ مجرّد بلا رمز عملة — الرمز يُلحق بحسب عملة كل مزوّد. */
const num = (v: string | number) =>
  Number(v || 0).toLocaleString("en-US", { minimumFractionDigits: 2 });

export default function Providers() {
  const cur = useBaseSymbol();
  const [providers, setProviders] = useState<Provider[]>([]);
  const [totals, setTotals] = useState<{ real_balance: string; debt: string } | null>(null);
  const [showPassive, setShowPassive] = useState(false);
  const [loading, setLoading] = useState(true);
  const [modal, setModal] = useState<{ edit?: Provider } | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [flash, setFlash] = useState<{ ok: boolean; text: string; lines?: { ok: boolean; text: string }[] } | null>(null);
  const [del, setDel] = useState<Provider | null>(null);
  const [deleting, setDeleting] = useState(false);

  function load() {
    setLoading(true);
    Promise.all([
      api.get("/providers/", { params: showPassive ? { status: "passive" } : {} }),
      api.get("/providers/totals/"),
    ]).then(([p, t]) => { setProviders(p.data); setTotals(t.data); })
      .finally(() => setLoading(false));
  }
  useEffect(() => load(), [showPassive]);

  const money = (v: string) => Number(v).toLocaleString("en-US", { minimumFractionDigits: 2 }) + " " + cur;

  /**
   * مبلغٌ بعملة المزوّد، وتحته مقابله بعملة الدفتر.
   *
   * ZNET يعطي «100» ويعني مئة ليرة — وقراءتها مئة دولار خطأٌ بأربعين ضعفاً.
   * فيُكتب الرقم بعملته صريحةً، ويُكتب تحته المقابل بسعر الصرف المضبوط في
   * «الإعدادات ← أسعار الصرف». والسطر الثاني يغيب إن كانت العملتان واحدة.
   */
  const Amount = ({ value, base, curr, baseCur, danger }: {
    value: string; base: string | null; curr: string; baseCur: string; danger?: boolean;
  }) => (
    <div style={{ lineHeight: 1.5 }}>
      <div style={{ fontWeight: 700, color: danger ? "var(--danger)" : undefined }}>
        {num(value)} {symbolOf(curr)}
      </div>
      {curr !== baseCur && (
        <div style={{ fontSize: 11.5, color: "var(--muted)", marginTop: 1 }} dir="rtl">
          {base === null
            ? `لا سعر صرف لـ${curr}`
            : `≈ ${num(base)} ${symbolOf(baseCur)}`}
        </div>
      )}
    </div>
  );
  const typeColor: Record<string, string> = {
    same_system: "var(--primary)", pool: "#c1692a", card_store: "#33454a", loader: "var(--primary-dark)",
    znet: "#1a7f8c", zdk: "#7a3ba0", barakat: "#7a3ba0", apstore: "#7a3ba0",
  };
  const kindKey = (p: Provider) => (p.config?.code || "").toLowerCase() || p.type;

  /** المبلغ بعملة المزوّد نفسه، ومعه ما يعادله بعملة الدفتر إن اختلفتا */
  function inCurrency(v: string, base: string | null, d: Provider) {
    const own = `${num(v)} ${symbolOf(d.shown_currency)}`;
    return d.shown_currency !== d.base_currency && base !== null
      ? `${own} (≈ ${num(base)} ${symbolOf(d.base_currency)})` : own;
  }

  /** ☀ زرٌّ واحد: أرصدة كل المزوّدين الآليين معاً — والمنفّذ اليدوي لا رصيد له */
  async function refreshAll() {
    const targets = providers.filter((p) => p.type !== "loader");
    if (!targets.length) return;
    setRefreshing(true); setFlash(null);
    const results = await Promise.allSettled(
      targets.map((p) => api.post(`/providers/${p.id}/refresh-balance/`)));
    const fresh = new Map<number, Provider>();
    const lines = results.map((r, i) => {
      const p = targets[i];
      if (r.status === "rejected") {
        return { ok: false, text: `«${p.name}»: ${r.reason?.response?.data?.detail || "فشل جلب الرصيد"}` };
      }
      const d = r.value.data as Provider & { balance_note?: string };
      fresh.set(d.id, d);
      return {
        ok: true,
        text: `«${p.name}»: ${inCurrency(d.real_balance, d.real_balance_base, d)}`
          + (Number(d.debt) > 0 ? ` · الدين ${inCurrency(d.debt, d.debt_base, d)}` : "")
          + (d.balance_note ? ` — ${d.balance_note}` : ""),
      };
    });
    setProviders((list) => list.map((x) => fresh.get(x.id) || x));
    api.get("/providers/totals/").then((t) => setTotals(t.data));
    const failed = lines.filter((l) => !l.ok).length;
    setFlash({
      ok: failed === 0,
      text: failed ? `تمّ تحديث ${lines.length - failed} من ${lines.length} — تعذّر الباقي:` : `☀ تمّ تحديث أرصدة ${lines.length} مزوّد`,
      lines,
    });
    setRefreshing(false);
  }

  async function confirmDelete() {
    if (!del) return;
    setDeleting(true); setFlash(null);
    try {
      await api.delete(`/providers/${del.id}/`);
      setFlash({ ok: true, text: `تم حذف المزوّد «${del.name}»` });
      setDel(null);
      load();
    } catch (e: any) {
      setFlash({ ok: false, text: `«${del.name}»: ${e?.response?.data?.detail || "فشل الحذف"}` });
      setDel(null);
    } finally { setDeleting(false); }
  }

  if (loading) return <div style={{ padding: 30 }}>جارٍ التحميل...</div>;

  return (
    <div style={{ padding: 16 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 14 }}>
        <h2 style={{ fontSize: 20, color: "var(--primary-dark)" }}>مزوّدو API (Oyun Apileri)</h2>
        <button className="btn g" onClick={() => setModal({})}>➕ إضافة مزوّد</button>
        <button className={showPassive ? "btn" : "btn r"} onClick={() => setShowPassive((v) => !v)}>
          {showPassive ? "عرض النشطة" : "⏸ المعطّلة"}
        </button>
        <button className="btn" onClick={refreshAll} disabled={refreshing}
          title="يجلب الرصيد الفعلي والدين من كل المزوّدين دفعةً واحدة"
          style={{ background: "#e8a416", color: "#2b1d00", display: "inline-flex", alignItems: "center", gap: 6 }}>
          <Icon name="sun" size={16} style={refreshing ? { animation: "spin 1.1s linear infinite" } : undefined} />
          {refreshing ? "جارٍ تحديث الأرصدة..." : "تحديث الأرصدة"}
        </button>
      </div>

      {flash && (
        <div style={{
          background: flash.ok ? "#e8f6ec" : "#fdecea",
          border: `1px solid ${flash.ok ? "#bfe3c8" : "#f5c6c2"}`,
          color: flash.ok ? "#1e7a35" : "var(--danger)",
          fontSize: 13, padding: "9px 12px", borderRadius: 6, marginBottom: 12,
        }}>
          {flash.text}
          {flash.lines && (
            <ul style={{ margin: "6px 0 0", paddingInlineStart: 18, lineHeight: 1.9 }}>
              {flash.lines.map((l, i) => (
                <li key={i} style={{ color: l.ok ? "#1e7a35" : "var(--danger)" }}>{l.text}</li>
              ))}
            </ul>
          )}
        </div>
      )}

      <table style={table}>
        <thead>
          <tr>
            <th style={{ ...th, textAlign: "right", paddingInlineStart: 12 }}>اسم المزوّد</th>
            <th style={th}>النوع</th>
            <th style={th}>الحالة</th>
            <th style={th}>طلبات معلّقة</th>
            <th style={th}>الرصيد الفعلي</th>
            <th style={th}>الدين</th>
            <th style={th}>إجراءات</th>
          </tr>
        </thead>
        <tbody>
          {providers.map((p, i) => (
            <tr key={p.id} style={{ background: i % 2 ? "var(--row-alt)" : "#fff" }}>
              <td style={{ ...td, textAlign: "right", paddingInlineStart: 12, fontWeight: 600 }}>{p.name}</td>
              <td style={{ ...td, color: typeColor[kindKey(p)] || typeColor[p.type], fontWeight: 600 }}>{p.type_label}</td>
              <td style={td}>
                <span style={{
                  display: "inline-block", width: 11, height: 11, borderRadius: "50%",
                  background: p.status === "active" ? "var(--ok)" : "var(--danger)",
                }} />
              </td>
              <td style={{ ...td, color: "var(--muted)" }}>0 طلب · 0.00</td>
              <td style={td}>
                <Amount value={p.real_balance} base={p.real_balance_base}
                  curr={p.shown_currency} baseCur={p.base_currency} />
              </td>
              <td style={td}>
                <Amount value={p.debt} base={p.debt_base} danger={Number(p.debt) > 0}
                  curr={p.shown_currency} baseCur={p.base_currency} />
              </td>
              <td style={td}>
                {/* تعديلٌ وحذف لا غير — وتحديث الرصيد زرٌّ واحد أعلى الصفحة لكل المزوّدين.
                    (أيقونتا «card» و«chart» كانتا مرسومتين من التصميم المرجعي بلا وظيفة.) */}
                <div style={{ display: "flex", gap: 6, justifyContent: "center", alignItems: "center" }}>
                  <button onClick={() => setModal({ edit: p })} title="تعديل المزوّد وإعدادات الاتصال"
                    style={{ background: "transparent", border: 0, color: "var(--primary)", cursor: "pointer" }}>
                    <Icon name="edit" size={15} />
                  </button>
                  <button onClick={() => setDel(p)} title="حذف المزوّد"
                    style={{ background: "transparent", border: 0, color: "var(--danger)", cursor: "pointer" }}>
                    <Icon name="trash" size={15} />
                  </button>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
        {totals && (
          <tfoot>
            <tr style={{ background: "#f5c518", fontWeight: 700 }}>
              <td style={{ ...td, textAlign: "right", paddingInlineStart: 12 }} colSpan={4}>المجاميع</td>
              {/* المجموع بعملة الدفتر — الخادم يحوّل كلّ مزوّد بعملته قبل الجمع */}
              <td style={td}>{money(totals.real_balance)}</td>
              <td style={td}>{money(totals.debt)}</td>
              <td style={td}></td>
            </tr>
          </tfoot>
        )}
      </table>

      <div style={note}>
        أنواع المزوّدين: <b>نفس النظام</b> (متجر داخلي على منصّتنا) · <b>متجر بطاقات</b> (ZNET/ZDK خارجي)
        · <b>بنك الأكواد</b> (مخزون داخلي) · <b>منفّذ يدوي</b> (بشري). التوجيه بثلاثة
        مستويات (رئيسي + بديلين) يُربط من صفحة توجيه الباقات.
      </div>

      {modal && (
        <ProviderModal edit={modal.edit}
          onClose={() => setModal(null)}
          onDone={() => { setModal(null); load(); }} />
      )}

      {del && (
        <div style={overlay} onClick={() => setDel(null)}>
          <div style={mbox} onClick={(e) => e.stopPropagation()}>
            <div style={{ ...mhead, background: "var(--danger)" }}>حذف المزوّد</div>
            <div style={{ padding: 20 }}>
              <div style={{ fontSize: 14.5, lineHeight: 1.9 }}>
                هل أنت متأكد من حذف المزوّد <b>«{del.name}»</b>؟
              </div>
              <div style={{ fontSize: 12.5, color: "var(--muted)", marginTop: 8, lineHeight: 1.8 }}>
                المنتجات الموجَّهة إليه لن تُحذف — سيُفكّ ربطها فقط وتعود للتنفيذ
                اليدوي حتى تربطها بمزوّد آخر. سجلّ الطلبات السابقة يبقى كما هو.
              </div>
              <div style={{ display: "flex", gap: 10, marginTop: 18 }}>
                <button className="btn r" style={{ flex: 1, height: 40 }}
                  disabled={deleting} onClick={confirmDelete}>
                  {deleting ? "جارٍ الحذف..." : "نعم، احذف"}
                </button>
                <button type="button" className="btn" style={{ height: 40, background: "#8a999e" }}
                  onClick={() => setDel(null)}>
                  إلغاء
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

/* ===== نموذج إضافة/تعديل مزوّد — حقول ذكية حسب النوع ===== */
type Kind = "pool" | "tenant" | "znet" | "zdk" | "loader";
const KINDS: { k: Kind; label: string; hint: string }[] = [
  { k: "znet", label: "ZNET (خارجي)", hint: "مزوّد تركي — kod/sifre" },
  // النوع هو البرمجية لا اسم المتجر: Barakat وApstore وغيرهما تعمل بـ ZDK
  { k: "zdk", label: "ZDK (خارجي)", hint: "برمجية ZDK — Ap4Stor · Barakat وغيرهما · توكن فقط" },
  { k: "tenant", label: "متجر داخلي (نفس النظام)", hint: "متجر آخر على منصّتنا" },
  { k: "pool", label: "بنك الأكواد (بطاقات)", hint: "مخزون داخلي — تسليم فوري" },
  { k: "loader", label: "منفّذ يدوي", hint: "بلا تنفيذ آلي" },
];

function kindOf(p?: Provider): Kind {
  const code = (p?.config?.code || "").toLowerCase();
  if (code === "znet") return "znet";
  // الكودان القديمان لمتجرين على برمجية ZDK نفسها
  if (code === "zdk" || code === "barakat" || code === "apstore") return "zdk";
  if (p?.type === "pool") return "pool";
  if (p?.type === "same_system") return "tenant";
  if (p?.type === "loader") return "loader";
  return p?.type === "card_store" ? "zdk" : "pool";
}

function ProviderModal({ edit, onClose, onDone }:
  { edit?: Provider; onClose: () => void; onDone: () => void }) {
  const [name, setName] = useState(edit?.name || "");
  const [kind, setKind] = useState<Kind>(kindOf(edit));
  const [status, setStatus] = useState(edit?.status || "active");
  // عملة المزوّد الخارجي — ZNET يسعّر بالليرة، وغيره قد يسعّر بالدولار.
  // كان النظام يفترضها ليرةً للجميع فيقسم سعر المزوّد الدولاري على ~41.
  const [providerCurrency, setProviderCurrency] = useState(edit?.currency || "TRY");
  const [cfg, setCfg] = useState<Record<string, string>>({ ...(edit?.config || {}) });
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  const c = (k: string) => cfg[k] || "";
  const setC = (k: string, v: string) => setCfg((o) => ({ ...o, [k]: v }));

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setErr(""); setBusy(true);
    // اجمع النوع + config حسب الاختيار
    const body: any = { name, status };
    // العملة تخصّ المزوّد الخارجي وحده: البنك والمنفّذ اليدوي بلا أسعار
    // خارجية، والمتجر الداخلي يحوّل بنفسه من دفتر المورّد.
    if (kind === "znet" || kind === "zdk") body.currency = providerCurrency;
    if (kind === "znet") {
      body.type = "card_store";
      body.config = { code: "znet", base_url: c("base_url"), kod: c("kod"), sifre: c("sifre") };
      if (!c("base_url") || !c("kod") || !c("sifre")) { setErr("كل حقول ZNET مطلوبة"); setBusy(false); return; }
    } else if (kind === "zdk") {
      body.type = "card_store";
      // ZDK لا اسم مستخدم فيه ولا كلمة سر — التوكن وحده يعرّف الحساب
      body.config = { code: "zdk", api_token: c("api_token"), base_url: c("base_url").trim() };
      if (!c("api_token")) { setErr("التوكن مطلوب"); setBusy(false); return; }
    } else if (kind === "tenant") {
      body.type = "same_system";
      body.config = { dealer_login: c("dealer_login") };
      if (!c("dealer_login")) { setErr("رقم دخول حسابنا لدى المتجر المورّد مطلوب"); setBusy(false); return; }
    } else if (kind === "pool") {
      body.type = "pool"; body.config = {};
    } else {
      body.type = "loader"; body.config = {};
    }
    try {
      if (edit) await api.patch(`/providers/${edit.id}/`, body);
      else await api.post("/providers/", body);
      onDone();
    } catch (e: any) {
      setErr(e?.response?.data?.detail || "فشل الحفظ");
    } finally { setBusy(false); }
  }

  return (
    <div style={overlay} onClick={onClose}>
      <form style={mbox} onClick={(e) => e.stopPropagation()} onSubmit={submit}>
        <div style={mhead}>{edit ? `إعدادات المزوّد: ${edit.name}` : "إضافة مزوّد"}</div>
        <div style={{ padding: 20 }}>
          <label style={lbl}>اسم المزوّد *</label>
          <input style={inp} value={name} onChange={(e) => setName(e.target.value)} required autoFocus />

          <label style={lbl}>نوع المزوّد *</label>
          <select style={inp} value={kind} onChange={(e) => setKind(e.target.value as Kind)}>
            {KINDS.map((x) => <option key={x.k} value={x.k}>{x.label}</option>)}
          </select>
          <div style={{ fontSize: 12, color: "var(--muted)", margin: "4px 2px 0" }}>
            {KINDS.find((x) => x.k === kind)?.hint}
          </div>

          {(kind === "znet" || kind === "zdk") && (
            <>
              <label style={lbl}>عملة المزوّد *</label>
              <select style={inp} value={providerCurrency}
                onChange={(e) => setProviderCurrency(e.target.value)}>
                <option value="TRY">ل.ت — ليرة تركية</option>
                <option value="USD">$ — دولار</option>
                <option value="EUR">€ — يورو</option>
                <option value="SYP">ل.س — ليرة سورية</option>
              </select>
              <div style={{ fontSize: 12, color: "var(--muted)", marginTop: 4, lineHeight: 1.9 }}>
                العملة التي يسعّر بها هذا المزوّد كتالوجه ويعطي بها رصيده.
                <b> ZNET بالليرة التركية</b> دائماً. وبها تُحوَّل أرقامه إلى عملة
                دفترك بسعر الصرف المضبوط في «الإعدادات ← أسعار الصرف» — فاضبطه
                أوّلاً وإلّا لم تُحسب تكلفة الباقات.
              </div>
            </>
          )}

          {kind === "znet" && (
            <>
              <label style={lbl}>رابط الخدمة (base_url) *</label>
              <input style={inp} dir="ltr" placeholder="https://panel.znet.com.tr" value={c("base_url")} onChange={(e) => setC("base_url", e.target.value)} />
              <label style={lbl}>kod (رقم الجوال) *</label>
              <input style={inp} dir="ltr" autoComplete="off" value={c("kod")} onChange={(e) => setC("kod", e.target.value)} />
              <label style={lbl}>sifre (كلمة السر) *</label>
              <input style={inp} dir="ltr" type="password" autoComplete="new-password" value={c("sifre")} onChange={(e) => setC("sifre", e.target.value)} />
            </>
          )}
          {kind === "zdk" && (
            <>
              <label style={lbl}>التوكن (api-token) *</label>
              <input style={inp} dir="ltr" type="password" autoComplete="new-password" value={c("api_token")} onChange={(e) => setC("api_token", e.target.value)} />
              <div style={{ fontSize: 12, color: "var(--muted)", marginTop: 4 }}>
                ZDK لا يستخدم اسم مستخدم ولا كلمة سر — التوكن وحده يعرّف حسابك.
              </div>
              <label style={lbl}>رابط الخدمة (اختياري)</label>
              <input style={inp} dir="ltr" placeholder="https://api.ap4stor.com (الافتراضي)"
                value={c("base_url")} onChange={(e) => setC("base_url", e.target.value)} />
              <div style={{ fontSize: 12, color: "var(--muted)", marginTop: 4 }}>
                اتركه فارغاً للمتجر الافتراضي. اضبطه فقط إن كان متجرك على مضيف
                آخر يعمل ببرمجية ZDK نفسها.
              </div>
            </>
          )}
          {kind === "tenant" && (
            <>
              <label style={lbl}>رقم دخول حسابنا لدى المتجر المورّد *</label>
              <input style={inp} dir="ltr" placeholder="مثال: alaya_at_supplier" value={c("dealer_login")} onChange={(e) => setC("dealer_login", e.target.value)} />
              <div style={{ fontSize: 12, color: "var(--muted)", marginTop: 4 }}>
                يجب أن يكون لديك حساب وكيل (برصيد) لدى ذلك المتجر. معرّف الباقة على
                منتجاتك = رقم منتج المورّد.
              </div>
            </>
          )}
          {kind === "pool" && (
            <div style={{ fontSize: 12.5, color: "var(--muted)", marginTop: 8 }}>
              بعد الحفظ: أنشئ مجموعة أكواد واربطها بهذا المزوّد من صفحة <b>بنك الأكواد</b>.
            </div>
          )}

          <label style={lbl}>الحالة *</label>
          <select style={inp} value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="active">نشط</option>
            <option value="passive">غير نشط</option>
          </select>

          {err && <div style={errBox}>{err}</div>}
          <div style={{ display: "flex", gap: 10, marginTop: 16 }}>
            <button className="btn g" style={{ flex: 1, height: 40 }} disabled={busy}>
              {busy ? "جارٍ..." : "حفظ"}
            </button>
            <button type="button" className="btn" style={{ height: 40, background: "#8a999e" }} onClick={onClose}>
              إلغاء
            </button>
          </div>
        </div>
      </form>
    </div>
  );
}

const overlay: React.CSSProperties = {
  position: "fixed", inset: 0, background: "rgba(0,0,0,.45)",
  display: "flex", alignItems: "center", justifyContent: "center", zIndex: 1000,
};
const mbox: React.CSSProperties = {
  width: 440, background: "var(--surface)", borderRadius: 10, overflow: "hidden",
  boxShadow: "0 16px 50px rgba(0,0,0,.35)",
};
const mhead: React.CSSProperties = {
  background: "var(--primary)", color: "#fff", padding: "14px 18px", fontWeight: 700, fontSize: 15,
};
const lbl: React.CSSProperties = { display: "block", fontSize: 13, color: "var(--muted)", margin: "13px 2px 5px" };
const inp: React.CSSProperties = { width: "100%", height: 38, borderRadius: 8 };
const errBox: React.CSSProperties = {
  background: "#fdecea", border: "1px solid #f5c6c2", color: "var(--danger)",
  fontSize: 13, padding: "9px 12px", borderRadius: 5, marginTop: 12,
};

const table: React.CSSProperties = {
  width: "100%", borderCollapse: "collapse", background: "var(--surface)", fontSize: 13.5,
};
const th: React.CSSProperties = {
  background: "var(--th-bg)", color: "var(--th-ink)", padding: "11px 10px",
  textAlign: "center", fontWeight: 800, fontSize: 12.5, whiteSpace: "nowrap",
  border: "1px solid var(--border)", borderTop: 0,
};
const td: React.CSSProperties = {
  padding: 10, textAlign: "center", whiteSpace: "nowrap", verticalAlign: "middle",
  background: "var(--surface)", border: "1px solid var(--border)",
  borderBottom: "3px solid var(--row-sep)",
};
const note: React.CSSProperties = {
  background: "#f6f8f9", border: "1px solid #dbe3e5", color: "var(--muted)",
  fontSize: 13, padding: "10px 14px", borderRadius: 6, marginTop: 14, lineHeight: 1.8,
};
