import { useEffect, useState } from "react";
import { api } from "../api";
import DateRange, { rangeText, TODAY, type Dates } from "../components/DateRange";
import Icon from "../components/Icon";
import Pager from "../components/Pager";
import { downloadCsv } from "../csv";
import { money, symbolOf } from "../currency";

type Kind = "agents" | "manual" | "deposits" | "debts";

const TITLES: Record<Kind, [string, string]> = {
  agents: ["تقرير الوكلاء الكبار",
    "لكل وكيل كبير: ربحك أنت من طلبات شبكته، وربحه هو، وما يدين به المتجر لشبكته الآن (رصيده + أرصدة دكاكينه)."],
  manual: ["الحركات اليدوية",
    "كل إضافة وخصم وتسوية باليد — مَن نفّذها ولمن ولماذا. أسرع طريقٍ لكشف مالٍ لا طلب ولا إيداع وراءه."],
  deposits: ["تقرير الإيداعات",
    "الإيداعات المقبولة (بتاريخ القبول) لكل حساب وطريقة: كم أُرسل، وكم أُضيف للمحافظ، وكم كانت العمولة."],
  debts: ["عمر الديون",
    "كل من رصيده سالب الآن: منذ متى، ومتى دفع آخر مرّة، وكم استخدم من حدّه الائتماني. الأقدم أوّلاً."],
};

/**
 * تقارير المال لصاحب المتجر — صفحةٌ واحدة بأربعة أنواع (`kind`)، من `core/finance.py`.
 * الأرقام بعملة دفتر المتجر، والفترة تبدأ باليوم (عدا عمر الديون: هو حال الآن).
 */
export default function FinanceReports({ kind }: { kind: Kind }) {
  const [d, setD] = useState<any>(null);
  const [dates, setDates] = useState<Dates>(TODAY);
  const [page, setPage] = useState(1);
  const [type, setType] = useState("");
  const [dealer, setDealer] = useState("");
  const [by, setBy] = useState("");
  const [dealers, setDealers] = useState<{ id: number; name: string }[]>([]);
  const dated = kind !== "debts";

  useEffect(() => { setD(null); setPage(1); }, [kind]);
  useEffect(() => {
    if (kind === "manual") api.get("/dealers/").then((r) => setDealers(r.data.results || [])).catch(() => {});
  }, [kind]);
  useEffect(() => {
    const params: Record<string, string> = { page: String(page) };
    if (dated && dates.date_from) params.date_from = dates.date_from;
    if (dated && dates.date_to) params.date_to = dates.date_to;
    if (type) params.type = type;
    if (dealer) params.dealer = dealer;
    if (by) params.by = by;
    // نوسم النتيجة بنوعها: لا يُرسم تقريرٌ ببيانات تقريرٍ آخر وصلت متأخّرة
    api.get(`/finance/${kind}/`, { params })
      .then((r) => setD({ ...r.data, kind }))
      .catch(() => setD({ kind, results: [], totals: {}, summary: [], buckets: [], paging: null }));
  }, [kind, dates, page, type, dealer, by]);

  const sym = symbolOf(d?.currency || "");
  const [title, hint] = TITLES[kind];
  const reset = <T,>(set: (v: T) => void) => (v: T) => { set(v); setPage(1); };

  function exportCsv() {
    if (!d?.results?.length) return;
    const r = d.results as any[];
    if (kind === "agents") downloadCsv(title, ["الوكيل", "الدكاكين", "الطلبات", "مبيعات المتجر له", "التكلفة", "ربحي", "ربح الوكيل", "رصيده", "أرصدة دكاكينه", "ما يدين به المتجر"],
      r.map((x) => [x.name, x.shops, x.count, x.sell, x.cost, x.profit, x.agent_profit, x.balance, x.shops_balance, x.exposure]));
    if (kind === "manual") downloadCsv(title, ["التاريخ", "الحساب", "النوع", "المبلغ", "الرصيد بعدها", "نفّذها", "ملاحظة"],
      r.map((x) => [x.created_at, x.dealer, x.type_label, x.amount, x.balance_after, x.by, x.note]));
    if (kind === "deposits") downloadCsv(title, ["الحساب", "الطريقة", "العملة", "العدد", "المُرسل", "المُضاف", "العمولة"],
      r.map((x) => [x.account, x.method, x.currency, x.count, x.amount, x.credit, x.commission]));
    if (kind === "debts") downloadCsv(title, ["الوكيل", "الرصيد", "الحد الائتماني", "مستخدم من الحد %", "سالب منذ", "أيام", "آخر دفعة", "واتساب"],
      r.map((x) => [x.name, x.balance, x.credit_limit, x.limit_used, x.since, x.days, x.last_payment, x.whatsapp]));
  }

  return (
    <div style={{ padding: 16, maxWidth: 1340, margin: "0 auto" }}>
      <h2 style={{ fontSize: 20, color: "var(--primary-dark)", marginBottom: 4 }}>{title}</h2>
      <div style={{ fontSize: 12.5, color: "var(--muted)", marginBottom: 12 }}>{hint}</div>

      <div style={bar}>
        {dated && <DateRange value={dates} onChange={reset(setDates)} />}
        {kind === "manual" && (
          <>
            <select value={type} onChange={(e) => reset(setType)(e.target.value)} style={{ height: 34 }}>
              <option value="">كل الأنواع</option>
              {(d?.summary || []).map((s: any) => <option key={s.type} value={s.type}>{s.label}</option>)}
            </select>
            <select value={dealer} onChange={(e) => reset(setDealer)(e.target.value)} style={{ height: 34, maxWidth: 180 }}>
              <option value="">كل الحسابات</option>
              {dealers.map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}
            </select>
            <select value={by} onChange={(e) => reset(setBy)(e.target.value)} style={{ height: 34 }}>
              <option value="">نفّذها: الكل</option>
              {(d?.actors || []).map((a: any) => <option key={a.id} value={a.id}>{a.name}</option>)}
            </select>
          </>
        )}
        <button className="btn g" style={{ marginInlineStart: "auto" }} onClick={exportCsv}>
          <Icon name="excel" size={15} style={{ marginInlineEnd: 5, verticalAlign: -2 }} />تصدير Excel
        </button>
      </div>
      <div style={{ fontSize: 12.5, color: "var(--muted)", margin: "-6px 0 12px" }}>
        {dated ? <>الفترة: <b style={{ color: "var(--text)" }}>{rangeText(dates)}</b> · </> : null}
        المبالغ بعملة الدفتر <b>{sym}</b>
      </div>

      {!d || d.kind !== kind ? <div style={{ padding: 30, color: "var(--muted)" }}>جارٍ التحميل...</div>
        : kind === "agents" ? <Agents d={d} sym={sym} />
        : kind === "manual" ? <Manual d={d} sym={sym} onPage={setPage} />
        : kind === "deposits" ? <Deposits d={d} sym={sym} />
        : <Debts d={d} sym={sym} />}
    </div>
  );
}

function Agents({ d, sym }: { d: any; sym: string }) {
  const t = d.totals;
  return (
    <>
      <div className="summary" style={{ marginBottom: 14 }}>
        <Stat icon="dollar" label="ربحي من الشبكات" value={`${money(t.profit)} ${sym}`} cls="bal-pos" />
        <Stat icon="users" label="ربح الوكلاء الكبار" value={`${money(t.agent_profit)} ${sym}`} />
        <Stat icon="cart" label="مبيعاتي لهم" value={`${money(t.sell)} ${sym}`} />
        <Stat icon="wallet" label="ما يدين به المتجر لشبكاتهم" value={`${money(t.exposure)} ${sym}`}
          cls={Number(t.exposure) < 0 ? "bal-neg" : ""} />
      </div>
      <Table head={["الوكيل الكبير", "الدكاكين", "الطلبات", "مبيعاتي له", "التكلفة", "ربحي", "ربحه", "ما دفعته دكاكينه",
        "رصيده", "أرصدة دكاكينه", "يدين به المتجر"]}
        empty={!d.results.length} cols={11}>
        {d.results.map((r: any) => (
          <tr key={r.id}>
            <td className="cell-start" style={{ fontWeight: 700 }}>{r.name}
              <div style={{ fontSize: 11, color: "var(--faint)", fontWeight: 400 }}>{r.login_id}</div></td>
            <td className="num">{r.shops}</td>
            <td className="num">{r.count}</td>
            <td className="num">{money(r.sell)}</td>
            <td className="num" style={{ color: "var(--muted)" }}>{money(r.cost)}</td>
            <td className="num bal-pos" style={{ fontWeight: 800 }}>{money(r.profit)}</td>
            <td className="num">{money(r.agent_profit)}</td>
            <td className="num" style={{ color: "var(--muted)" }}>{money(r.buyer)}</td>
            <td className={`num ${Number(r.balance) < 0 ? "bal-neg" : ""}`}>{money(r.balance)}</td>
            <td className={`num ${Number(r.shops_balance) < 0 ? "bal-neg" : ""}`}>{money(r.shops_balance)}</td>
            <td className={`num ${Number(r.exposure) < 0 ? "bal-neg" : ""}`} style={{ fontWeight: 800 }}>{money(r.exposure)}</td>
          </tr>
        ))}
      </Table>
      <Note>
        «يدين به المتجر» = رصيد الوكيل الكبير + أرصدة دكاكينه: كلّه مالٌ تستطيع شبكته صرفه عندك. السالب يعني أن
        الشبكة مدينةٌ لك. الطلبات والأرباح للطلبات الناجحة في الفترة (ألعاب + موبايل).
      </Note>
    </>
  );
}

function Manual({ d, sym, onPage }: { d: any; sym: string; onPage: (p: number) => void }) {
  return (
    <>
      <div className="summary" style={{ marginBottom: 14 }}>
        {d.summary.map((s: any) => (
          <Stat key={s.type} icon={s.type === "manual_credit" ? "plus" : s.type === "manual_debit" ? "minus" : "refresh"}
            label={`${s.label} (${s.count})`} value={`${money(s.amount)} ${sym}`}
            cls={Number(s.amount) < 0 ? "bal-neg" : Number(s.amount) > 0 ? "bal-pos" : ""} />
        ))}
        <Stat icon="chart" label="الصافي" value={`${money(d.totals.net)} ${sym}`} />
      </div>
      <Table head={["التاريخ", "الحساب", "النوع", "المبلغ", "الرصيد بعدها", "نفّذها", "الملاحظة"]}
        empty={!d.results.length} cols={7}>
        {d.results.map((r: any) => (
          <tr key={r.id}>
            <td style={{ fontSize: 12.5, color: "var(--muted)" }}>{r.created_at}</td>
            <td className="cell-start" style={{ fontWeight: 700 }}>{r.dealer}{r.is_big && <span style={bigTag}>كبير</span>}</td>
            <td style={{ fontSize: 12.5 }}>{r.type_label}</td>
            <td className={`num ${Number(r.amount) < 0 ? "bal-neg" : "bal-pos"}`} style={{ fontWeight: 800 }}>{money(r.amount)}</td>
            <td className="num" style={{ color: "var(--muted)" }}>{money(r.balance_after)}</td>
            <td style={{ fontSize: 12.5 }}>{r.by}</td>
            <td className="cell-start" style={{ fontSize: 12.5, color: "var(--muted)", whiteSpace: "normal" }}>{r.note || "—"}</td>
          </tr>
        ))}
      </Table>
      <Pager paging={d.paging} onPage={onPage} />
      <Note>
        الإيداعات المقبولة لا تظهر هنا (لها تقريرها)، وإبطال إيداعٍ مقبول يظهر «تسوية». حوالات الوكيل الكبير
        لدكاكينه دفترُه هو فلا تظهر.
      </Note>
    </>
  );
}

function Deposits({ d, sym }: { d: any; sym: string }) {
  const t = d.totals;
  return (
    <>
      <div className="summary" style={{ marginBottom: 14 }}>
        <Stat icon="check" label="إيداعات مقبولة" value={String(t.count)} />
        <Stat icon="wallet" label="أُضيف للمحافظ" value={`${money(t.credit)} ${sym}`} cls="bal-pos" />
        <Stat icon="dollar" label="العمولات" value={`${money(t.commission)} ${sym}`} />
        <Stat icon="clock" label="معلّقة / مرفوضة" value={`${t.pending} / ${t.rejected}`} />
      </div>
      <Table head={["الحساب", "الطريقة", "العملة", "العدد", "المُرسل (بعملته)", `المُضاف (${sym})`, `العمولة (${sym})`]}
        empty={!d.results.length} cols={7}>
        {d.results.map((r: any, i: number) => (
          <tr key={i}>
            <td className="cell-start" style={{ fontWeight: 700 }}>{r.account}</td>
            <td className="cell-start">{r.method}</td>
            <td>{symbolOf(r.currency)} {r.currency}</td>
            <td className="num">{r.count}</td>
            <td className="num">{money(r.amount)}</td>
            <td className="num bal-pos" style={{ fontWeight: 800 }}>{money(r.credit)}</td>
            <td className="num" style={{ color: "var(--muted)" }}>{money(r.commission)}</td>
          </tr>
        ))}
      </Table>
      <Note>العمولة = قيمة المُرسل بعملة الدفتر (بسعر صرف لحظة الإيداع) ناقص ما أُضيف للمحفظة.</Note>
    </>
  );
}

function Debts({ d, sym }: { d: any; sym: string }) {
  return (
    <>
      <div className="summary" style={{ marginBottom: 14 }}>
        {d.buckets.map((b: any) => (
          <Stat key={b.label} icon="clock" label={`${b.label} (${b.count})`} value={`${money(b.amount)} ${sym}`}
            cls={Number(b.amount) < 0 ? "bal-neg" : ""} />
        ))}
      </div>
      <Table head={["الوكيل", "الرصيد", "بعملته", "الحد الائتماني", "من الحد", "سالب منذ", "آخر دفعة", "واتساب"]}
        empty={!d.results.length} cols={8} emptyText="لا ديون — كل الأرصدة صفر أو موجبة">
        {d.results.map((r: any) => (
          <tr key={r.id} className={r.days > 30 ? "row-stuck" : r.days > 7 ? "row-wait" : ""}>
            <td className="cell-start" style={{ fontWeight: 700 }}>{r.name}{r.is_big && <span style={bigTag}>كبير</span>}
              {r.status !== "active" && <span style={{ ...bigTag, background: "#fdecea", color: "var(--danger)" }}>معطّل</span>}
              <div style={{ fontSize: 11, color: "var(--faint)", fontWeight: 400 }}>{r.login_id}</div></td>
            <td className="num bal-neg" style={{ fontWeight: 800 }}>{money(r.balance)}</td>
            <td className="num" style={{ color: "var(--muted)" }}>
              {r.own_currency !== d.currency ? `${money(r.balance_own)} ${symbolOf(r.own_currency)}` : "—"}</td>
            <td className="num" style={{ color: "var(--muted)" }}>{money(r.credit_limit)}</td>
            <td className="num" style={{ fontWeight: 700, color: Number(r.limit_used) >= 90 ? "var(--danger)" : "var(--text)" }}>
              {r.limit_used ? `${r.limit_used}%` : "—"}</td>
            <td style={{ fontSize: 12.5 }}>{r.since}<div style={{ fontSize: 11.5, fontWeight: 800 }}>{r.days} يوم</div></td>
            <td style={{ fontSize: 12.5 }}>{r.last_payment || "لم يدفع"}
              {r.last_payment_days !== null && <div style={{ fontSize: 11.5, color: "var(--muted)" }}>قبل {r.last_payment_days} يوم</div>}</td>
            <td style={{ direction: "ltr", fontSize: 12.5 }}>{r.whatsapp || "—"}</td>
          </tr>
        ))}
      </Table>
      <Note>
        المجموع: <b className="num bal-neg">{money(d.total)} {sym}</b>. «سالب منذ» آخر حركةٍ نزلت بالرصيد تحت الصفر،
        و«آخر دفعة» آخر حركة موجبة ليست استرجاعاً. دكاكين الوكيل الكبير دَينها عليه — في رصيده هنا.
      </Note>
    </>
  );
}

function Table({ head, children, empty, cols, emptyText }: {
  head: string[]; children: React.ReactNode; empty: boolean; cols: number; emptyText?: string;
}) {
  return (
    <div className="card"><div className="table-scroll">
      <table className="grid">
        <thead><tr>{head.map((h, i) => <th key={h} className={i === 0 ? "cell-start" : ""}>{h}</th>)}</tr></thead>
        <tbody>
          {empty ? <tr><td colSpan={cols} style={{ padding: 26, color: "var(--muted)" }}>{emptyText || "لا بيانات في هذه الفترة"}</td></tr>
            : children}
        </tbody>
      </table>
    </div></div>
  );
}
function Stat({ icon, label, value, cls }: { icon: string; label: string; value: string; cls?: string }) {
  return (
    <div className="stat">
      <div className="label"><Icon name={icon} size={15} style={{ color: "var(--primary)" }} /> {label}</div>
      <div className={`value num ${cls || ""}`}>{value}</div>
      <span className="spark" />
    </div>
  );
}
function Note({ children }: { children: React.ReactNode }) {
  return <div style={{ fontSize: 12, color: "var(--muted)", marginTop: 10, lineHeight: 1.8 }}>{children}</div>;
}

const bar: React.CSSProperties = {
  display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap",
  background: "#f2f5f6", padding: "12px 14px", borderRadius: 6, marginBottom: 12,
};
const bigTag: React.CSSProperties = {
  marginInlineStart: 6, fontSize: 10.5, fontWeight: 700, color: "#7c3aed", background: "#ede9fe",
  borderRadius: 999, padding: "1px 7px",
};
