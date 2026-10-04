import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import Icon from "../components/Icon";
import ScrollTop from "../components/ScrollTop";
import { matches } from "../search";
import { empty, input, note, OpBadge, opOf, pageTitle, pageWrap, Switch, Toast } from "./kontorUi";

interface Group { id: number; name: string }
interface OpSetting { group: number | null; can_query: boolean }
interface Dealer { id: number; name: string; login_id: string; operators: Record<string, OpSetting> }

export default function KontorDealers() {
  const [operators, setOperators] = useState<string[]>([]);
  const [groups, setGroups] = useState<Group[]>([]);
  const [dealers, setDealers] = useState<Dealer[]>([]);
  const [loading, setLoading] = useState(true);
  const [q, setQ] = useState("");
  const [toast, setToast] = useState("");

  async function load() {
    const r = await api.get("/kontor/dealer-settings/");
    setOperators(r.data.operators); setGroups(r.data.groups); setDealers(r.data.dealers);
  }
  useEffect(() => { load().catch(() => {}).finally(() => setLoading(false)); }, []);

  function say(t: string) { setToast(t); setTimeout(() => setToast(""), 2500); }

  const shown = useMemo(() => dealers.filter((d) => matches(q, d.name, d.login_id)), [dealers, q]);

  /** حفظ دفعة إعدادات — لوكيل واحد أو لكل المعروضين في عمود شركة. */
  async function save(rows: { dealer: number; operator: string; patch: Partial<OpSetting> }[], msg = "✅ حُفظ") {
    if (!rows.length) return;
    setDealers((ds) => ds.map((d) => {
      const mine = rows.filter((r) => r.dealer === d.id);
      if (!mine.length) return d;
      const ops = { ...d.operators };
      for (const r of mine) ops[r.operator] = { ...ops[r.operator], ...r.patch };
      return { ...d, operators: ops };
    }));
    try {
      await api.patch("/kontor/dealer-settings/", rows.map((r) => ({ dealer: r.dealer, operator: r.operator, ...r.patch })));
      say(msg);
    } catch { say("تعذّر الحفظ"); load().catch(() => {}); }
  }

  function applyColumn(op: string, value: string) {
    if (value === "") return;
    const patch: Partial<OpSetting> = value === "q-on" ? { can_query: true } : value === "q-off" ? { can_query: false }
      : { group: value === "rec" ? null : Number(value) };
    save(shown.map((d) => ({ dealer: d.id, operator: op, patch })), `✅ طُبّق على ${shown.length} وكيل في ${opOf(op).label}`);
  }

  const groupName = (id: number | null) => groups.find((g) => g.id === id)?.name;

  return (
    <div style={pageWrap}>
      <ScrollTop />
      <h2 style={pageTitle}><Icon name="users" size={20} /> إعدادات الوكلاء — الأسعار والاستعلام</h2>

      <div className="toolbar">
        <span style={{ color: "var(--muted)", fontSize: 13 }}>{dealers.length} وكيل</span>
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="بحث عن وكيل بالاسم أو المعرّف..."
          style={{ ...input, width: 260, marginInlineStart: "auto" }} />
      </div>

      <div style={note}>
        لكل وكيل في كل شركة: <b>مجموعة سعره</b> (بلا مجموعة ⇐ يشتري بالسعر الموصى)، و<b>إذن الاستعلام</b> عن
        العروض الخاصة بخطّ الزبون. القائمة أعلى كل عمود تطبّق الاختيار على كل الوكلاء المعروضين دفعة واحدة.
        {groups.length === 0 && <div style={{ color: "var(--danger)", marginTop: 4 }}>لا مجموعات أسعار بعد — أنشئها أولاً في «مجموعات الأسعار».</div>}
      </div>

      {loading ? <div style={{ padding: 30 }}>جارٍ التحميل...</div> : (
        <div className="card"><div className="table-scroll">
          <table className="grid">
            <thead>
              <tr>
                <th className="cell-start">الوكيل</th>
                {operators.map((op) => (
                  <th key={op} style={{ minWidth: 170 }}>
                    <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
                      <OpBadge code={op} size={18} /> {opOf(op).label}
                    </span>
                    <select value="" onChange={(e) => applyColumn(op, e.target.value)} style={colSelect}>
                      <option value="">تطبيق على الكل…</option>
                      <option value="rec">المجموعة: الموصى</option>
                      {groups.map((g) => <option key={g.id} value={g.id}>المجموعة: {g.name}</option>)}
                      <option value="q-on">الاستعلام: مسموح</option>
                      <option value="q-off">الاستعلام: ممنوع</option>
                    </select>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {shown.length === 0 && <tr><td colSpan={1 + operators.length} style={empty}>
                {dealers.length ? `لا وكيل يطابق «${q.trim()}»` : "لا وكلاء بعد."}</td></tr>}
              {shown.map((d) => (
                <tr key={d.id}>
                  <td className="cell-start">
                    <div style={{ fontWeight: 700 }}>{d.name}</div>
                    <div style={{ fontSize: 11.5, color: "var(--muted)" }}>{d.login_id}</div>
                  </td>
                  {operators.map((op) => {
                    const s = d.operators[op];
                    return (
                      <td key={op}>
                        <select value={s.group ?? ""} style={{ ...cellSelect, fontWeight: s.group ? 700 : 400,
                          color: s.group ? "var(--primary-dark)" : "var(--muted)" }}
                          title={s.group ? `مجموعة ${groupName(s.group)}` : "يشتري بالسعر الموصى"}
                          onChange={(e) => save([{ dealer: d.id, operator: op,
                            patch: { group: e.target.value ? Number(e.target.value) : null } }])}>
                          <option value="">— الموصى —</option>
                          {groups.map((g) => <option key={g.id} value={g.id}>{g.name}</option>)}
                        </select>
                        <div style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 6, marginTop: 6, fontSize: 11.5,
                          color: s.can_query ? "var(--ok)" : "var(--faint)" }}>
                          <Switch on={s.can_query} title="استعلام العروض الخاصة"
                            onChange={(v) => save([{ dealer: d.id, operator: op, patch: { can_query: v } }])} />
                          استعلام
                        </div>
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div></div>
      )}
      <Toast text={toast} />
    </div>
  );
}

const colSelect: React.CSSProperties = {
  display: "block", width: "100%", marginTop: 6, height: 26, fontSize: 11.5, fontWeight: 400,
  borderRadius: 6, border: "1px solid var(--border)", background: "var(--surface)", color: "var(--muted)",
};
const cellSelect: React.CSSProperties = {
  width: 140, height: 30, borderRadius: 6, border: "1px solid var(--border)", background: "var(--surface)", padding: "0 6px",
};
