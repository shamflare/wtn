import { useEffect, useMemo, useState } from "react";
import { api, type Dealer } from "../api";
import WalletModal from "../components/WalletModal";
import DealerCreateModal from "../components/DealerCreateModal";
import DealerSettingsModal from "../components/DealerSettingsModal";
import StatementModal from "../components/StatementModal";
import BulkWhatsAppModal from "../components/BulkWhatsAppModal";
import { downloadCsv } from "../csv";
import Icon from "../components/Icon";
import { symbolOf, useBaseCurrency, useBaseSymbol } from "../currency";

type Filter = "all" | "neg";

export default function Dealers() {
  const cur = useBaseSymbol();
  const base = useBaseCurrency();
  const [dealers, setDealers] = useState<Dealer[]>([]);
  const [q, setQ] = useState("");
  const [filter, setFilter] = useState<Filter>("all");
  const [loading, setLoading] = useState(true);
  const [modal, setModal] = useState<{ dealer: Dealer; action: "topup" | "deduct" } | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [settingsFor, setSettingsFor] = useState<number | null>(null);
  const [statementFor, setStatementFor] = useState<Dealer | null>(null);
  const [bulkOpen, setBulkOpen] = useState(false);
  const [toast, setToast] = useState<{ ok: boolean; text: string } | null>(null);
  /** الجدول الأول للنشطين وحدهم؛ زرّ «إظهار المعطّلين» يقلبه إلى جدول المعطّلين. */
  const [showDisabled, setShowDisabled] = useState(false);
  const [togglingId, setTogglingId] = useState<number | null>(null);
  /** الوكلاء الكبار المفتوحون — صفّ الكبير يطوي دكاكينه تحته. */
  const [expanded, setExpanded] = useState<number[]>([]);

  const toggleExpanded = (id: number) =>
    setExpanded((ids) => ids.includes(id) ? ids.filter((x) => x !== id) : [...ids, id]);

  /**
   * الكرة هي الحالة والزرّ معاً: خضراء تعمل ⇒ اضغطها فيُعطَّل ويغادر الجدول،
   * حمراء ⇒ اضغطها فيعود. لا قوائم ولا نافذة — نقرة واحدة في الاتّجاهين.
   */
  async function toggleActive(d: Dealer) {
    const next = d.active ? "passive" : "active";
    setTogglingId(d.id);
    try {
      await api.post(`/dealers/${d.id}/settings/`, { status: next });
      const flip = (x: Dealer): Dealer => ({
        ...x,
        active: x.id === d.id ? !d.active : x.active,
        status: x.id === d.id ? next : x.status,
        children: x.children?.map(flip),
      });
      setDealers((ds) => ds.map(flip));
      setToast({
        ok: true,
        text: d.active
          ? `عُطِّل «${d.name}» — تجده في «إظهار المعطّلين»`
          : `فُعِّل «${d.name}» — عاد إلى قائمة الوكلاء`,
      });
    } catch (e: any) {
      setToast({ ok: false, text: e?.response?.data?.detail || "تعذّر تغيير الحالة" });
    } finally {
      setTogglingId(null);
    }
  }

  /** إرسال تنبيه الرصيد لوكيل واحد — يقصده المالك بعينه، فلا شرط موافقة. */
  async function notifyOne(d: Dealer) {
    if (!d.whatsapp) {
      setToast({ ok: false, text: `لا رقم واتساب لـ«${d.name}» — أضفه من ⚙ إعدادات الوكيل` });
      return;
    }
    try {
      await api.post("/whatsapp/send/", { dealer_id: d.id });
      setToast({ ok: true, text: `جُدولت رسالة إلى ${d.name} — تتابعها في الإعدادات ← واتساب` });
    } catch (e: any) {
      setToast({ ok: false, text: e?.response?.data?.detail || "تعذّر الإرسال" });
    }
  }

  function load(search = "") {
    setLoading(true);
    api.get("/dealers/", { params: { q: search } })
      .then((r) => setDealers(r.data.results))
      .finally(() => setLoading(false));
  }
  useEffect(() => load(), []);

  function updateBalance(dealerId: number, r: { balance: string; balance_own?: string }) {
    setDealers((ds) => ds.map((d) => (d.id === dealerId
      ? { ...d, balance: r.balance, balance_own: r.balance_own ?? d.balance_own } : d)));
    setModal(null);
  }

  const money = (v: string | number) =>
    Number(v).toLocaleString("en-US", { minimumFractionDigits: 2 });

  // الرصيد واحد موقّع: سالب = مديونية
  const shown = useMemo(() => dealers.filter((d) => {
    if (showDisabled) return !d.active;         // جدول المعطّلين وحدهم
    if (!d.active) return false;                // المعطّل لا يظهر في الجدول الأول
    return filter === "neg" ? Number(d.balance) < 0 : true;
  }), [dealers, filter, showDisabled]);

  const disabledCount = useMemo(
    () => dealers.filter((d) => !d.active).length, [dealers]);

  const stats = useMemo(() => ({
    total: dealers.length,
    active: dealers.filter((d) => d.active).length,
    net: dealers.reduce((s, d) => s + Number(d.balance), 0),
    negative: dealers.filter((d) => Number(d.balance) < 0).length,
  }), [dealers]);

  const balCls = (v: number) => (v < 0 ? "bal-neg" : v > 0 ? "bal-pos" : "bal-zero");

  /** يصدّر ما هو ظاهر بعد البحث والفلترة — لا القائمة كاملةً. */
  function exportExcel() {
    downloadCsv(
      "قائمة-الوكلاء",
      ["رقم الوكيل", "رقم الدخول", "الاسم", "الرصيد", "عملة الدفتر", "عملة الوكيل",
       "الحد الائتماني", "الحالة", "المجموعة", "عدد الدكاكين"],
      shown.map((d) => [
        String(d.dealer_no ?? ""), d.login_id, d.name, d.balance, d.currency, d.display_currency || base,
        d.credit_limit, d.active ? "نشط" : "موقوف", d.group || "", d.children_count,
      ]),
    );
  }

  return (
    <div style={{ maxWidth: 1320, margin: "0 auto", padding: "22px 20px 40px" }}>
      {/* شريط المؤشّرات */}
      <div className="summary">
        <div className="stat">
          <div className="label"><Icon name="users" size={15} style={{ color: "var(--primary)" }} /> إجمالي الوكلاء</div>
          <div className="value num">{stats.total}</div><span className="spark" />
        </div>
        <div className="stat">
          <div className="label"><Icon name="check" size={15} style={{ color: "var(--primary)" }} /> نشطون</div>
          <div className="value num">{stats.active} <small style={{ fontSize: 13, color: "var(--faint)" }}>/ {stats.total}</small></div>
          <span className="spark" />
        </div>
        <div className="stat">
          <div className="label"><Icon name="wallet" size={15} style={{ color: "var(--primary)" }} /> صافي أرصدة الوكلاء</div>
          <div className={`value num ${balCls(stats.net)}`}>{money(stats.net)} <small style={{ fontSize: 13, color: "var(--faint)" }}>{cur}</small></div>
          <span className="spark" />
        </div>
        <div className="stat">
          <div className="label"><Icon name="warning" size={15} style={{ color: "var(--primary)" }} /> وكلاء برصيد سالب</div>
          <div className="value num" style={{ color: "var(--debt)" }}>{stats.negative}</div><span className="spark" />
        </div>
      </div>

      {/* شريط الأدوات */}
      <div className="toolbar">
        <div style={{ position: "relative", flex: 1, minWidth: 220 }}>
          <input placeholder="ابحث باسم الوكيل أو رقمه…" value={q}
            onChange={(e) => setQ(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && load(q)}
            style={{ width: "100%", height: 40, paddingInlineStart: 36, borderRadius: 10 }} />
          <span style={{ position: "absolute", insetInlineStart: 11, top: 11, color: "var(--faint)" }}>
            <Icon name="search" size={17} />
          </span>
        </div>
        {!showDisabled && (
          <div className="segment">
            {([["all", "الكل"], ["neg", "رصيد سالب"]] as [Filter, string][]).map(([k, label]) => (
              <button key={k} className={filter === k ? "active" : ""} onClick={() => setFilter(k)}>{label}</button>
            ))}
          </div>
        )}
        <button className="btn" style={{ background: showDisabled ? "var(--primary)" : "#8a999e" }}
          onClick={() => setShowDisabled((v) => !v)}
          title="المعطّلون لا يظهرون في القائمة الأولى — من هنا تراهم وتعيدهم">
          <Icon name={showDisabled ? "users" : "eye"} size={15} style={ib} />
          {showDisabled ? "العودة إلى النشطين" : `إظهار المعطّلين${disabledCount ? ` (${disabledCount})` : ""}`}
        </button>
        <span style={{ marginInlineStart: "auto", color: "var(--muted)", fontSize: 13 }}>
          العدد: <b style={{ color: "var(--text)" }}>{shown.length}</b>
        </span>
        <button className="btn" onClick={exportExcel} disabled={shown.length === 0}
          title="تصدير الوكلاء الظاهرين بعد البحث والفلترة">
          <Icon name="excel" size={15} style={ib} />تصدير Excel
        </button>
        <button className="btn" style={{ background: "#258a4a" }} onClick={() => setBulkOpen(true)}
          disabled={stats.negative === 0}
          title="تنبيه بالرصيد عبر واتساب لكل مدين وافق على التحصيل الآلي">
          <Icon name="whatsapp" size={15} style={ib} />تنبيه المدينين
        </button>
        <button className="btn g" onClick={() => setCreateOpen(true)}>
          <Icon name="plus" size={15} style={ib} />إضافة وكيل
        </button>
      </div>

      {/* الجدول — النمط المعتمد */}
      <div className="card">
        <div className="card-title">
          <Icon name={showDisabled ? "eye" : "users"} size={16} style={{ color: "var(--primary)" }} />
          {showDisabled ? " الوكلاء المعطّلون — اضغط الكرة الحمراء لإعادته" : " قائمة الوكلاء"}
        </div>
        <div className="table-scroll">
          <table className="grid">
            <thead>
              <tr>
                <th><input type="checkbox" title="تحديد الكل" /></th>
                <th>الرقم</th>
                <th className="cell-start">اسم الوكيل</th>
                <th>الرصيد</th>
                <th title="العملة التي يرى بها الوكيل لوحته">العملة</th>
                <th>الحد الائتماني</th>
                <th>الحالة</th>
                <th>المجموعة</th>
                <th>إجراءات</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan={9} style={{ padding: 30, color: "var(--muted)" }}>جارٍ التحميل...</td></tr>
              ) : shown.length === 0 ? (
                <tr><td colSpan={9} style={{ padding: 30, color: "var(--muted)" }}>
                  {showDisabled ? "لا وكلاء معطّلين" : "لا يوجد وكلاء مطابقون"}
                </td></tr>
              ) : shown.flatMap((d) => {
                const bal = Number(d.balance);
                const open = expanded.includes(d.id);
                const rows = [
                  <tr key={d.id} style={d.is_big && open ? bigOpenRow : undefined}>
                    <td><input type="checkbox" /></td>
                    <td className="num" style={{ color: "var(--faint)", fontSize: 12.5 }}
                      title={`رقم الدخول: ${d.login_id}`}>{d.dealer_no ?? "—"}</td>
                    <td className="cell-start">
                      {d.is_big ? (
                        <button type="button" onClick={() => toggleExpanded(d.id)}
                          title="وكيل كبير — اضغط لعرض دكاكينه"
                          style={{
                            background: "none", border: 0, padding: 0, cursor: "pointer",
                            font: "inherit", fontWeight: 800, color: GOLD_INK,
                            display: "flex", alignItems: "center", gap: 5,
                          }}>
                          <span style={{ fontSize: 11, color: "var(--faint)" }}>{open ? "▾" : "▸"}</span>
                          <span title="وكيل كبير" style={{ color: GOLD }}>★</span>
                          {d.name}
                          <span style={{ color: "var(--faint)", fontSize: 11, fontWeight: 700 }}>
                            ({d.children_count})
                          </span>
                          {d.is_locked && <LockTag />}
                        </button>
                      ) : (
                        <div style={{ fontWeight: 700, display: "flex", alignItems: "center", gap: 5 }}>
                          {d.name}
                          {d.is_locked && <LockTag />}
                        </div>
                      )}
                    </td>
                    <td><OwnMoney d={d} field="balance" base={base} big /></td>
                    <td style={{ fontWeight: 800, fontSize: 15 }}
                      title={d.display_currency || base}>
                      {symbolOf(d.display_currency || base)}
                    </td>
                    <td><OwnMoney d={d} field="credit_limit" base={base} muted /></td>
                    <td>
                      <button type="button" onClick={() => toggleActive(d)}
                        disabled={togglingId === d.id}
                        title={d.active
                          ? "نشط — اضغط لتعطيله (يختفي من هذه القائمة)"
                          : "معطّل — اضغط لإعادته إلى قائمة الوكلاء"}
                        aria-label={d.active ? "تعطيل الوكيل" : "تفعيل الوكيل"}
                        style={{
                          width: 18, height: 18, borderRadius: "50%", padding: 0,
                          border: "2px solid rgba(0,0,0,.12)", cursor: "pointer",
                          background: d.active ? "var(--ok)" : "var(--danger)",
                          opacity: togglingId === d.id ? 0.4 : 1,
                          boxShadow: "0 1px 3px rgba(0,0,0,.25)",
                        }} />
                    </td>
                    <td className="num" style={{ fontWeight: 700, color: "var(--muted)" }}>{d.group || "—"}</td>
                    <td>
                      <div style={{ display: "flex", gap: 4, justifyContent: "center" }}>
                        <IconBtn name="plus" color="var(--ok)" title="شحن رصيد" onClick={() => setModal({ dealer: d, action: "topup" })} />
                        <IconBtn name="minus" color="var(--danger)" title="خصم رصيد" onClick={() => setModal({ dealer: d, action: "deduct" })} />
                        <IconBtn name="whatsapp" color={d.whatsapp ? "#25d366" : "var(--faint)"}
                          title={d.whatsapp ? `تنبيه بالرصيد عبر واتساب — +${d.whatsapp}` : "لا رقم واتساب لهذا الوكيل"}
                          onClick={() => notifyOne(d)} />
                        <IconBtn name="chart" color="var(--primary)" title="كشف حساب"
                          onClick={() => setStatementFor(d)} />
                        <IconBtn name="settings" color="var(--primary-dark)" title="إعدادات الوكيل"
                          onClick={() => setSettingsFor(d.id)} />
                      </div>
                    </td>
                  </tr>,
                ];

                // دكاكين الوكيل الكبير: تُفتح تحته داخل إطار ذهبي، فلا تختلط
                // بالصفوف الأصلية ولا تُقرأ معزولةً عن وكيلها.
                if (d.is_big && open) {
                  rows.push(
                    <tr key={`${d.id}-kids`}>
                      <td colSpan={9} style={{ padding: 0, background: GOLD_BG }}>
                        <div style={goldBox}>
                          <div style={goldHead}>
                            <span style={{ color: GOLD }}>★</span> دكاكين {d.name}
                            <span style={{ color: "var(--muted)", fontWeight: 400 }}>
                              {" "}· رصيد الوكيل الكبير{" "}
                              <b className={`num ${balCls(bal)}`}>
                                {money(d.balance_own ?? bal)} {symbolOf(d.own_currency || d.currency)}
                              </b>
                            </span>
                          </div>
                          {(d.children || []).length === 0 ? (
                            <div style={{ padding: "14px 16px", color: "var(--muted)", fontSize: 13 }}>
                              لا دكاكين تحته بعد — اربط وكيلاً به من ⚙ إعدادات الوكيل.
                            </div>
                          ) : (
                            <table className="grid" style={{ background: "transparent" }}>
                              <thead>
                                <tr>
                                  <th>الرقم</th>
                                  <th className="cell-start">اسم الدكان</th>
                                  <th>الرصيد</th>
                                  <th>الحد الائتماني</th>
                                  <th>الحالة</th>
                                  <th>إجراءات</th>
                                </tr>
                              </thead>
                              <tbody>
                                {(d.children || []).map((c) => (
                                  <tr key={c.id}>
                                    <td className="num" style={{ color: "var(--faint)", fontSize: 12.5 }}
                                      title={`رقم الدخول: ${c.login_id}`}>{c.dealer_no ?? "—"}</td>
                                    <td className="cell-start" style={{ fontWeight: 700 }}>{c.name}</td>
                                    <td><OwnMoney d={c} field="balance" base={base} /></td>
                                    <td><OwnMoney d={c} field="credit_limit" base={base} muted /></td>
                                    <td>
                                      <button type="button" onClick={() => toggleActive(c)}
                                        disabled={togglingId === c.id}
                                        title={c.active ? "نشط — اضغط لتعطيله" : "معطّل — اضغط لتفعيله"}
                                        style={{
                                          width: 16, height: 16, borderRadius: "50%", padding: 0,
                                          border: "2px solid rgba(0,0,0,.12)", cursor: "pointer",
                                          background: c.active ? "var(--ok)" : "var(--danger)",
                                          opacity: togglingId === c.id ? 0.4 : 1,
                                        }} />
                                    </td>
                                    <td>
                                      <div style={{ display: "flex", gap: 4, justifyContent: "center" }}>
                                        <IconBtn name="chart" color="var(--primary)" title="كشف حساب"
                                          onClick={() => setStatementFor(c)} />
                                        <IconBtn name="settings" color="var(--primary-dark)" title="إعدادات الدكان"
                                          onClick={() => setSettingsFor(c.id)} />
                                      </div>
                                    </td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          )}
                        </div>
                      </td>
                    </tr>,
                  );
                }
                return rows;
              })}
            </tbody>
          </table>
        </div>
      </div>

      {modal && (
        <WalletModal dealer={modal.dealer} action={modal.action}
          onClose={() => setModal(null)}
          onDone={(r) => updateBalance(modal.dealer.id, r)} />
      )}

      {createOpen && (
        <DealerCreateModal
          onClose={() => setCreateOpen(false)}
          onDone={() => { setCreateOpen(false); load(q); }} />
      )}

      {settingsFor !== null && (
        <DealerSettingsModal dealerId={settingsFor}
          onClose={() => setSettingsFor(null)}
          onSaved={(text) => { setSettingsFor(null); load(q); setToast({ ok: true, text }); }} />
      )}

      {statementFor && (
        <StatementModal dealerId={statementFor.id} dealerName={statementFor.name}
          onClose={() => setStatementFor(null)} />
      )}

      {bulkOpen && (
        <BulkWhatsAppModal
          onClose={() => setBulkOpen(false)}
          onSent={(n) => {
            setBulkOpen(false);
            setToast({ ok: true, text: `جُدولت ${n} رسالة — تتابع تقدّمها في الإعدادات ← واتساب` });
          }} />
      )}

      {toast && (
        <div onClick={() => setToast(null)} style={{
          position: "fixed", insetInlineStart: 20, bottom: 20, zIndex: 90, cursor: "pointer",
          maxWidth: 420, padding: "11px 15px", borderRadius: 9, fontSize: 13, lineHeight: 1.8,
          boxShadow: "0 6px 24px rgba(0,0,0,.25)",
          background: toast.ok ? "var(--ok)" : "var(--danger)", color: "#fff",
        }}>{toast.text}</div>
      )}
    </div>
  );
}

function IconBtn({ name, color, title, onClick }:
  { name: string; color: string; title: string; onClick?: () => void }) {
  return (
    <button onClick={onClick} title={title} style={{
      border: "1px solid var(--border)", background: "var(--surface)", color,
      width: 30, height: 30, borderRadius: 8, display: "flex",
      alignItems: "center", justifyContent: "center", cursor: "pointer",
    }}>
      <Icon name={name} size={15} />
    </button>
  );
}

const ib: React.CSSProperties = { marginInlineEnd: 5, verticalAlign: -2 };

/* الذهبي للوكيل الكبير: نجمته واسمه وإطار دكاكينه */
/**
 * علامةُ حسابٍ مقفل.
 *
 * كانت حالة القفل تصل لإعدادات الوكيل وحدها، فلا يُعرف المقفول إلا بفتح
 * إعدادات كلٍّ على حدة — أي أن صاحب المتجر ينتظر الوكيل يتّصل ليعرف.
 * ويفكّه تبديلُ كلمة السرّ من ⚙ إعدادات الوكيل.
 */
function LockTag() {
  return (
    <span title="الحساب مقفل بعد محاولات دخول خاطئة — يفكّه تبديل كلمة السر"
      style={{
        background: "#fdecea", color: "var(--danger)", border: "1px solid #f5c6c2",
        fontSize: 10.5, fontWeight: 700, borderRadius: 9, padding: "1px 7px",
        whiteSpace: "nowrap",
      }}>
      🔒 مقفل
    </span>
  );
}

const GOLD = "#e0a800";
const GOLD_INK = "#8a6100";
const GOLD_BG = "rgba(224,168,0,.05)";
const bigOpenRow: React.CSSProperties = { background: GOLD_BG };
const goldBox: React.CSSProperties = {
  border: `2px solid ${GOLD}`, borderRadius: 8, margin: "6px 10px 10px",
  overflow: "hidden", background: "var(--surface)",
};
const goldHead: React.CSSProperties = {
  background: "rgba(224,168,0,.12)", borderBottom: `1px solid ${GOLD}`,
  padding: "8px 12px", fontSize: 13, fontWeight: 800, color: GOLD_INK,
};

/**
 * رصيد الوكيل أو حدّه **بعملته** (ما يراه هو وما تكتبه له)، وتحته ما يعادله
 * بعملة الدفتر إن اختلفتا — فلا يُقرأ «‎-5,000» بلا عملة ولا يُظنّ دولاراً وهو ليرة.
 */
function OwnMoney({ d, field, base, big, muted }: {
  d: Dealer; field: "balance" | "credit_limit"; base: string; big?: boolean; muted?: boolean;
}) {
  const own = d.own_currency || d.currency || base;
  const ownVal = Number((field === "balance" ? d.balance_own : d.credit_limit_own) ?? d[field]);
  const baseVal = Number(d[field]);
  const fmt = (v: number) => v.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const cls = field === "balance" ? (ownVal < 0 ? "bal-neg" : ownVal > 0 ? "bal-pos" : "") : "";
  return (
    <div style={{ lineHeight: 1.35 }}>
      <span className={`num ${cls}`} style={{ fontSize: big ? 14.5 : 14, color: muted ? "var(--muted)" : undefined }}>
        {fmt(ownVal)}
      </span>
      <span style={{ fontSize: 11.5, color: "var(--faint)", marginInlineStart: 3, fontWeight: 700 }}>{symbolOf(own)}</span>
      {own !== base && (
        <div style={{ fontSize: 10.5, color: "var(--faint)" }} dir="rtl">≈ {fmt(baseVal)} {symbolOf(base)}</div>
      )}
    </div>
  );
}
