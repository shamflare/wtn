import { useEffect, useState } from "react";
import { api } from "../api";
import Icon from "../components/Icon";
import { money, symbolOf } from "../currency";

interface Line {
  id: number | null; name: string; amount: string; currency: string;
  base: string | null; note: string; source: string;
}
interface Group {
  key: string; label: string; hint: string; auto: boolean; enabled: boolean;
  lines: Line[]; total_base: string; unresolved: number;
}
interface Live {
  base_currency: string;
  rates: Record<string, string>;
  groups: Group[];
  manual: Group;
  by_currency: Record<string, string>;
  totals: { total: string; assets: string; liabilities: string; previous_total: string; profit: string };
  previous: { id: number; taken_at: string; total: string } | null;
  sources: { key: string; label: string; enabled: boolean }[];
  notes: string[];
  currencies: { code: string; label: string }[];
}
interface Snap {
  id: number; kind: string; kind_label: string; taken_at: string; date: string;
  base_currency: string; total: string; assets: string; liabilities: string;
  previous_total: string; profit: string; period_profit: string; daily_count: number;
  orders_profit: string; orders_count: number; note: string; by: string;
}

/**
 * الجرد — لصاحب المتجر، وللوكيل الكبير (`agent`) جرده هو بعملته: رصيده لدى المتجر
 * وحساباته ومحافظ دكاكينه وبنوده اليدوية ولقطاته. بلا مزوّدين ولا مصادر تُبدَّل.
 */
export default function Inventory({ agent }: { agent?: boolean } = {}) {
  const P = agent ? "/agent/inventory" : "/inventory";
  const [d, setD] = useState<Live | null>(null);
  const [snaps, setSnaps] = useState<Snap[]>([]);
  const [busy, setBusy] = useState("");
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [newName, setNewName] = useState("");
  const [tab, setTab] = useState<"all" | "daily" | "monthly">("all");

  function load() {
    api.get(`${P}/live/`).then((r) => setD(r.data))
      .catch((e) => setMsg({ ok: false, text: e?.response?.data?.detail || "تعذّر جلب الجرد" }));
    api.get(`${P}/snapshots/`).then((r) => setSnaps(r.data.results)).catch(() => {});
  }
  useEffect(load, []);

  if (!d) return <div style={{ padding: 30, color: "var(--muted)" }}>جارٍ الحساب...</div>;
  const sym = symbolOf(d.base_currency);
  const profit = Number(d.totals.profit);

  async function call(fn: () => Promise<any>, label: string, done?: string) {
    setBusy(label); setMsg(null);
    try {
      const r = await fn();
      load();
      if (done) setMsg({ ok: true, text: done });
      return r;
    } catch (e: any) {
      setMsg({ ok: false, text: e?.response?.data?.detail || "تعذّرت العملية" });
      return null;
    } finally { setBusy(""); }
  }

  async function refresh() {
    const r = await call(() => api.post(`${P}/refresh/`, {}), "refresh");
    if (r) {
      const { ok_count, fail_count } = r.data;
      setMsg({
        ok: fail_count === 0,
        text: fail_count === 0
          ? `جُلبت أرصدة ${ok_count} مزوّد`
          : `نجح ${ok_count} وفشل ${fail_count} — ` +
            r.data.results.filter((x: any) => !x.ok).map((x: any) => `${x.name}: ${x.note}`).join(" · "),
      });
    }
  }

  async function save(kind: "daily" | "monthly") {
    const label = kind === "daily" ? "الجرد اليومي" : "الجرد الشهري";
    if (!confirm(`حفظ ${label} بالمجموع ${money(d!.totals.total)} ${sym}؟\nاللقطة لا تتغيّر بعد حفظها.`)) return;
    await call(() => api.post(`${P}/snapshots/save/`, { kind }), kind, `حُفظ ${label}`);
  }

  const shownSnaps = snaps.filter((s) => tab === "all" || s.kind === tab);

  return (
    <div style={{ padding: 16, maxWidth: 1240, margin: "0 auto" }}>
      {/* ═══ الرأس والأزرار ═══ */}
      <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap", marginBottom: 14 }}>
        <div>
          <h2 style={{ fontSize: 21, color: "var(--primary-dark)", margin: 0 }}>{agent ? "جردي" : "الجرد النهائي"}</h2>
          <div style={{ fontSize: 12.5, color: "var(--muted)", marginTop: 2 }}>
            {new Date().toLocaleDateString("ar-EG", { day: "numeric", month: "long", year: "numeric" })}
            {d.previous && <> · آخر جرد: {d.previous.taken_at}</>}
          </div>
        </div>
        <div style={{ marginInlineStart: "auto", display: "flex", gap: 8, flexWrap: "wrap" }}>
          {!agent && (
            <button className="btn" onClick={refresh} disabled={!!busy}>
              <Icon name="refresh" size={14} style={ib} />{busy === "refresh" ? "جارٍ الجلب..." : "جلب الأرصدة"}
            </button>
          )}
          <button className="btn g" onClick={() => save("daily")} disabled={!!busy}>
            <Icon name="check" size={14} style={ib} />حفظ الجرد اليومي
          </button>
          <button className="btn" style={{ background: "#7b5cd6" }} onClick={() => save("monthly")} disabled={!!busy}>
            <Icon name="calendar" size={14} style={ib} />جرد شهري
          </button>
        </div>
      </div>

      {msg && (
        <div style={{
          marginBottom: 12, fontSize: 13, padding: "10px 14px", borderRadius: 8, lineHeight: 1.8,
          background: msg.ok ? "rgba(53,194,69,.10)" : "rgba(221,68,68,.10)",
          color: msg.ok ? "var(--ok)" : "var(--danger)",
        }}>{msg.text}</div>
      )}
      {d.notes.map((n, i) => (
        <div key={i} style={warn}><Icon name="warning" size={14} style={ib} />{n}</div>
      ))}

      {/* ═══ المصادر التلقائية ═══ */}
      {d.groups.map((g) => (
        <Panel key={g.key} title={g.label} hint={g.hint} sym={sym} total={g.total_base}
          enabled={g.enabled} accent="var(--primary)"
          toggle={agent ? undefined : () => call(
            () => api.put(`${P}/sources/`, {
              sources: { ...Object.fromEntries(d.sources.map((s) => [s.key, s.enabled])), [g.key]: !g.enabled },
            }), "src")}
          right={<Icon name="api" size={14} style={{ opacity: .8 }} />}
        >
          <LineTable lines={g.lines} sym={sym}
            onRefresh={g.key === "providers"
              ? (id) => call(() => api.post(`${P}/refresh/`, { provider: id }), "one")
              : undefined} />
        </Panel>
      ))}

      {/* ═══ البنود اليدوية ═══ */}
      <Panel title={d.manual.label} hint={d.manual.hint} sym={sym} total={d.manual.total_base}
        enabled accent="#3b4a5a" right={<Icon name="edit" size={14} style={{ opacity: .8 }} />}>
        <LineTable lines={d.manual.lines} sym={sym} currencies={d.currencies}
          onEdit={(id, patch) => call(() => api.post(`${P}/items/${id}/`, patch), "item")}
          onDelete={(id) => {
            if (confirm("حذف هذا البند؟")) call(() => api.delete(`${P}/items/${id}/`), "item");
          }} />
        <div style={{ display: "flex", gap: 8, marginTop: 10 }}>
          <input value={newName} onChange={(e) => setNewName(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter" && newName.trim()) addItem(); }}
            placeholder="اسم البند الجديد…" style={{ flex: 1, height: 38, borderRadius: 8 }} />
          <button className="btn g" disabled={!newName.trim() || !!busy} onClick={addItem}>
            <Icon name="plus" size={14} style={ib} />إضافة
          </button>
        </div>
      </Panel>

      {/* ═══ الملخّص ═══ */}
      <div style={{ ...panel, marginTop: 18 }}>
        <div style={{ ...panelHead, background: "var(--primary)" }}>الملخّص</div>
        <div style={{ padding: 16 }}>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(170px,1fr))", gap: 10 }}>
            {Object.entries(d.by_currency).map(([c, v]) => (
              <Box key={c} label={`مجموع ${c}`} value={`${money(v)} ${symbolOf(c)}`} />
            ))}
            {Object.entries(d.rates).map(([c, v]) => (
              <Box key={`r${c}`} label={`سعر ${c}`} value={`${v}`} faint />
            ))}
            <Box label={agent ? "ما لي" : "الأصول (ما لنا)"} value={`${money(d.totals.assets)} ${sym}`} color="var(--ok)" />
            <Box label={agent ? "ما عليّ" : "الالتزامات (ما علينا)"} value={`${money(d.totals.liabilities)} ${sym}`} color="var(--debt)" />
            <Box label="الجرد السابق" value={`${money(d.totals.previous_total)} ${sym}`} />
            <Box label="المجموع الكلي" value={`${money(d.totals.total)} ${sym}`} strong />
          </div>

          <div style={{
            marginTop: 14, borderRadius: 10, padding: "18px 20px", textAlign: "center",
            background: profit < 0 ? "var(--debt)" : "var(--primary)", color: "#fff",
          }}>
            <div style={{ fontSize: 13, opacity: .9 }}>
              {d.previous ? "الربح منذ الجرد السابق" : "أوّل جرد — لا ربح يُقارَن به بعد"}
            </div>
            <div className="num" style={{ fontSize: 34, fontWeight: 800, lineHeight: 1.3 }}>
              {money(d.totals.profit)} {sym}
            </div>
            {d.previous && (
              <div style={{ fontSize: 12, opacity: .85 }}>
                {money(d.totals.total)} − {money(d.totals.previous_total)} · منذ {d.previous.taken_at}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* ═══ السجلّ ═══ */}
      <div style={{ ...panel, marginTop: 18 }}>
        <div style={{ ...panelHead, display: "flex", alignItems: "center", gap: 10 }}>
          <span>سجلّ الجرد</span>
          <div className="segment" style={{ marginInlineStart: "auto" }}>
            {([["all", "الكل"], ["daily", "يومي"], ["monthly", "شهري"]] as const).map(([k, l]) => (
              <button key={k} className={tab === k ? "active" : ""} onClick={() => setTab(k)}>{l}</button>
            ))}
          </div>
        </div>
        <div className="table-scroll">
          <table className="grid">
            <thead>
              <tr>
                <th>التاريخ</th><th>النوع</th><th>المجموع</th><th>السابق</th><th>الربح</th>
                <th title="ما يقوله دفتر الطلبات عن الفترة نفسها">{agent ? "ربحي من الطلبات" : "ربح الطلبات"}</th>
                <th>حفظه</th><th>إجراءات</th>
              </tr>
            </thead>
            <tbody>
              {shownSnaps.length === 0 ? (
                <tr><td colSpan={8} style={{ padding: 26, color: "var(--muted)" }}>لم يُحفظ جرد بعد</td></tr>
              ) : shownSnaps.map((s) => {
                const p = Number(s.profit);
                return (
                  <tr key={s.id}>
                    <td style={{ fontSize: 12.5 }}>{s.taken_at}</td>
                    <td>
                      <span className="pill" style={s.kind === "monthly" ? { background: "#7b5cd6", color: "#fff" } : {}}>
                        {s.kind_label}
                      </span>
                    </td>
                    <td className="num" style={{ fontWeight: 700 }}>{money(s.total)} {symbolOf(s.base_currency)}</td>
                    <td className="num" style={{ color: "var(--muted)" }}>{money(s.previous_total)}</td>
                    <td className="num" style={{ fontWeight: 800, color: p < 0 ? "var(--debt)" : "var(--ok)" }}>
                      {money(s.profit)}
                      {s.kind === "monthly" && s.daily_count > 0 && (
                        <div style={{ fontSize: 11, color: "var(--muted)", fontWeight: 400 }}>
                          مجموع {s.daily_count} جرد: {money(s.period_profit)}
                        </div>
                      )}
                    </td>
                    <td className="num" style={{ color: "var(--muted)" }}>
                      {money(s.orders_profit)}
                      <div style={{ fontSize: 11, color: "var(--faint)" }}>{s.orders_count} طلب</div>
                    </td>
                    <td style={{ fontSize: 12, color: "var(--muted)" }}>{s.by || "—"}</td>
                    <td>
                      <button className="btn r" style={{ height: 26, fontSize: 11.5 }}
                        onClick={() => {
                          if (confirm("حذف هذا الجرد؟ أرباح الجرود التالية حُسبت عليه.")) {
                            call(() => api.delete(`${P}/snapshots/${s.id}/`), "del");
                          }
                        }}>حذف</button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );

  function addItem() {
    const name = newName.trim();
    if (!name) return;
    setNewName("");
    call(() => api.post(`${P}/items/`, { name }), "item");
  }
}

/* ═════════ مكوّنات ═════════ */

function Panel({ title, hint, sym, total, enabled, accent, right, toggle, children }: {
  title: string; hint: string; sym: string; total: string; enabled: boolean;
  accent: string; right?: React.ReactNode; toggle?: () => void; children: React.ReactNode;
}) {
  return (
    <div style={{ ...panel, marginTop: 14, opacity: enabled ? 1 : .55 }}>
      <div style={{ ...panelHead, background: accent, display: "flex", alignItems: "center", gap: 8 }}>
        {right}
        <span>{title}</span>
        {toggle && (
          <label style={{ fontSize: 11.5, fontWeight: 400, display: "flex", alignItems: "center", gap: 5, cursor: "pointer" }}>
            <input type="checkbox" checked={enabled} onChange={toggle} />
            يدخل الجرد
          </label>
        )}
        <span className="num" style={{ marginInlineStart: "auto", fontWeight: 800 }}>
          {money(total)} {sym}
        </span>
      </div>
      <div style={{ padding: "10px 14px 14px" }}>
        <div style={{ fontSize: 11.5, color: "var(--muted)", marginBottom: 8 }}>{hint}</div>
        {children}
      </div>
    </div>
  );
}

function LineTable({ lines, sym, currencies, onEdit, onDelete, onRefresh }: {
  lines: Line[]; sym: string;
  currencies?: { code: string; label: string }[];
  onEdit?: (id: number, patch: any) => void;
  onDelete?: (id: number) => void;
  onRefresh?: (id: number) => void;
}) {
  if (lines.length === 0) return <div style={{ fontSize: 12.5, color: "var(--faint)" }}>— لا بنود —</div>;
  return (
    <div className="table-scroll">
      <table className="grid">
        <thead>
          <tr>
            <th style={{ width: 34 }}>#</th>
            <th className="cell-start">الاسم</th>
            <th>المبلغ</th>
            <th>العملة</th>
            <th>المحسوب ({sym})</th>
            <th className="cell-start">ملاحظات</th>
            {(onDelete || onRefresh) && <th style={{ width: 70 }}>إجراءات</th>}
          </tr>
        </thead>
        <tbody>
          {lines.map((l, i) => {
            const neg = Number(l.amount) < 0;
            return (
              <tr key={`${l.source}-${l.id}-${i}`}>
                <td style={{ color: "var(--faint)", fontSize: 12 }}>{i + 1}</td>
                <td className="cell-start">
                  {onEdit && l.id ? (
                    <input defaultValue={l.name} style={cellInput}
                      onBlur={(e) => e.target.value !== l.name && onEdit(l.id!, { name: e.target.value })} />
                  ) : <span style={{ fontWeight: 700 }}>{l.name}</span>}
                </td>
                <td>
                  {onEdit && l.id ? (
                    <input defaultValue={l.amount} type="number" step="0.01"
                      style={{ ...cellInput, textAlign: "center", width: 130, direction: "ltr" }}
                      onBlur={(e) => e.target.value !== l.amount && onEdit(l.id!, { amount: e.target.value })} />
                  ) : (
                    <span className="num" style={{ fontWeight: 700, color: neg ? "var(--debt)" : "var(--text)" }}>
                      {money(l.amount)}
                    </span>
                  )}
                </td>
                <td>
                  {onEdit && l.id && currencies ? (
                    <select defaultValue={l.currency} style={{ ...cellInput, width: 92 }}
                      onChange={(e) => onEdit(l.id!, { currency: e.target.value })}>
                      {currencies.map((c) => <option key={c.code} value={c.code}>{c.code}</option>)}
                    </select>
                  ) : <span style={{ fontSize: 12.5 }}>{symbolOf(l.currency)} {l.currency}</span>}
                </td>
                <td className="num" style={{ color: l.base === null ? "var(--danger)" : "var(--muted)" }}>
                  {l.base === null ? "بلا سعر صرف" : `${money(l.base)} ${sym}`}
                </td>
                <td className="cell-start" style={{ fontSize: 11.5, color: "var(--muted)" }}>
                  {onEdit && l.id ? (
                    <input defaultValue={l.note} placeholder="…" style={cellInput}
                      onBlur={(e) => e.target.value !== l.note && onEdit(l.id!, { note: e.target.value })} />
                  ) : l.note}
                </td>
                {(onDelete || onRefresh) && (
                  <td>
                    <div style={{ display: "flex", gap: 4, justifyContent: "center" }}>
                      {onRefresh && l.id && (
                        <button title="جلب رصيد هذا المزوّد" onClick={() => onRefresh(l.id!)} style={iconBtn}>
                          <Icon name="refresh" size={13} />
                        </button>
                      )}
                      {onDelete && l.id && (
                        <button title="حذف البند" onClick={() => onDelete(l.id!)}
                          style={{ ...iconBtn, color: "var(--danger)" }}>
                          <Icon name="trash" size={13} />
                        </button>
                      )}
                    </div>
                  </td>
                )}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function Box({ label, value, color, strong, faint }: {
  label: string; value: string; color?: string; strong?: boolean; faint?: boolean;
}) {
  return (
    <div style={{
      border: `1px solid ${strong ? "var(--ok)" : "var(--border)"}`, borderRadius: 9,
      padding: "10px 13px", background: strong ? "rgba(53,194,69,.07)" : "var(--surface-2)",
      opacity: faint ? .75 : 1,
    }}>
      <div style={{ fontSize: 11.5, color: "var(--muted)" }}>{label}</div>
      <div className="num" style={{ fontSize: strong ? 19 : 16, fontWeight: 800, color: color || "var(--text)" }}>
        {value}
      </div>
    </div>
  );
}

const ib: React.CSSProperties = { marginInlineEnd: 5, verticalAlign: -2 };
const panel: React.CSSProperties = {
  background: "var(--surface)", border: "1px solid var(--border)",
  borderRadius: 10, overflow: "hidden",
};
const panelHead: React.CSSProperties = {
  background: "var(--primary)", color: "#fff", padding: "10px 16px",
  fontSize: 14.5, fontWeight: 700,
};
const cellInput: React.CSSProperties = {
  width: "100%", height: 30, borderRadius: 6, fontSize: 12.5,
  border: "1px solid transparent", background: "transparent", color: "var(--text)",
};
const iconBtn: React.CSSProperties = {
  border: "1px solid var(--border)", background: "var(--surface)", color: "var(--primary)",
  width: 27, height: 27, borderRadius: 7, display: "flex",
  alignItems: "center", justifyContent: "center", cursor: "pointer",
};
const warn: React.CSSProperties = {
  background: "rgba(224,168,0,.12)", border: "1px solid rgba(224,168,0,.45)",
  color: "var(--text)", fontSize: 12.5, padding: "9px 13px", borderRadius: 8,
  marginBottom: 10, lineHeight: 1.8,
};
