import { useEffect, useState } from "react";
import { api } from "../api";
import Icon from "../components/Icon";
import { money, symbolOf } from "../currency";

interface Target {
  id: number; name: string; login_id: string; whatsapp: string;
  balance: string; currency: string;
}
interface Targets {
  eligible: Target[]; no_consent: Target[]; no_number: Target[];
  counts: { eligible: number; no_consent: number; no_number: number };
}

/**
 * تأكيد الإرسال الجماعي — يقول الحقيقة **قبل** الضغط:
 * كم سيصله، ومن استُبعد ولماذا. لا إرسال أعمى.
 */
export default function BulkWhatsAppModal({
  onClose, onSent,
}: { onClose: () => void; onSent: (n: number) => void }) {
  const [t, setT] = useState<Targets | null>(null);
  const [tab, setTab] = useState<"eligible" | "no_consent" | "no_number">("eligible");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [session, setSession] = useState<{ status: string; status_label: string; bot_running: boolean } | null>(null);

  useEffect(() => {
    api.get("/whatsapp/targets/").then((r) => setT(r.data))
      .catch((e) => setErr(e?.response?.data?.detail || "تعذّر الجلب"));
    api.get("/whatsapp/status/").then((r) => setSession(r.data)).catch(() => {});
  }, []);

  async function send() {
    setBusy(true); setErr("");
    try {
      const r = await api.post("/whatsapp/send-bulk/", {});
      onSent(r.data.queued);
    } catch (e: any) {
      setErr(e?.response?.data?.detail || "تعذّر الإرسال");
    } finally { setBusy(false); }
  }

  const rows = t ? t[tab] : [];
  const ready = (t?.counts.eligible || 0) > 0;

  return (
    <div style={ovl} onClick={busy ? undefined : onClose}>
      <div style={box} onClick={(e) => e.stopPropagation()}>
        <div style={head}>
          <span><Icon name="whatsapp" size={16} style={{ marginInlineEnd: 7, verticalAlign: -3 }} />
            إرسال تنبيه الرصيد لكل مدين</span>
          <button type="button" onClick={onClose} style={xBtn}>✕</button>
        </div>

        {!t ? (
          <div style={{ padding: 26, color: "var(--muted)" }}>جارٍ حساب المستهدَفين...</div>
        ) : (
          <div style={{ padding: 16 }}>
            {session && !session.bot_running && (
              <div style={warn}>
                برنامج واتساب لا يعمل الآن. تستطيع الجدولة على أي حال — الرسائل
                تنتظر في الطابور وتنطلق حين يعمل.
              </div>
            )}

            <div style={{ display: "grid", gridTemplateColumns: "repeat(3,1fr)", gap: 10, marginBottom: 14 }}>
              <Stat n={t.counts.eligible} label="سيصلهم التنبيه" color="var(--ok)"
                on={tab === "eligible"} onClick={() => setTab("eligible")} />
              <Stat n={t.counts.no_consent} label="لم يوقّعوا موافقة التحصيل" color="var(--muted)"
                on={tab === "no_consent"} onClick={() => setTab("no_consent")} />
              <Stat n={t.counts.no_number} label="بلا رقم واتساب" color="var(--danger)"
                on={tab === "no_number"} onClick={() => setTab("no_number")} />
            </div>

            <div style={{ maxHeight: 280, overflow: "auto", border: "1px solid var(--border)", borderRadius: 8 }}>
              <table className="grid">
                <thead>
                  <tr><th className="cell-start">الوكيل</th><th>الرصيد</th><th>رقم واتساب</th></tr>
                </thead>
                <tbody>
                  {rows.length === 0 ? (
                    <tr><td colSpan={3} style={{ padding: 22, color: "var(--muted)" }}>لا أحد في هذه القائمة</td></tr>
                  ) : rows.map((d) => (
                    <tr key={d.id}>
                      <td className="cell-start" style={{ fontWeight: 700 }}>
                        {d.name} <span style={{ color: "var(--faint)", fontSize: 11.5 }}>{d.login_id}</span>
                      </td>
                      <td className="num" style={{ color: "var(--debt)", fontWeight: 700 }}>
                        {money(d.balance)} <span style={{ fontSize: 11 }}>{symbolOf(d.currency)}</span>
                      </td>
                      <td style={{ direction: "ltr", fontSize: 12.5, color: d.whatsapp ? "var(--muted)" : "var(--danger)" }}>
                        {d.whatsapp || "— غير مضبوط —"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div style={note}>
              الرصيد أعلاه معروض <b>بعملة كل وكيل</b> — وهو نفسه ما سيصله في رسالته.
              {t.counts.no_consent > 0 && <> · المستبعَدون لعدم الموافقة تُفتح موافقتهم من ⚙ إعدادات الوكيل.</>}
            </div>

            {err && <div style={{ color: "var(--danger)", fontSize: 13, marginTop: 10 }}>{err}</div>}

            <div style={{ display: "flex", gap: 8, marginTop: 16, alignItems: "center" }}>
              <button className="btn g" onClick={send} disabled={busy || !ready}>
                {busy ? "جارٍ الجدولة..." : `إرسال إلى ${t.counts.eligible} وكيل`}
              </button>
              <button className="btn" style={{ background: "#8a999e" }} onClick={onClose} disabled={busy}>إلغاء</button>
              <span style={{ fontSize: 11.5, color: "var(--muted)", marginInlineStart: "auto" }}>
                تُرسَل واحدةً واحدةً بتأخير عشوائي — لا دفعةً واحدة
              </span>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function Stat({ n, label, color, on, onClick }:
  { n: number; label: string; color: string; on: boolean; onClick: () => void }) {
  return (
    <button onClick={onClick} style={{
      border: `1px solid ${on ? color : "var(--border)"}`, borderRadius: 9,
      background: on ? "var(--surface-2)" : "var(--surface)", padding: "10px 12px",
      cursor: "pointer", textAlign: "start",
    }}>
      <div style={{ fontSize: 22, fontWeight: 800, color }}>{n}</div>
      <div style={{ fontSize: 11.5, color: "var(--muted)", marginTop: 2 }}>{label}</div>
    </button>
  );
}

const ovl: React.CSSProperties = {
  position: "fixed", inset: 0, background: "rgba(0,0,0,.45)", zIndex: 80,
  display: "flex", alignItems: "center", justifyContent: "center",
};
const box: React.CSSProperties = {
  background: "var(--surface)", borderRadius: 10, width: 700, maxWidth: "95vw",
  maxHeight: "92vh", overflow: "auto", boxShadow: "0 10px 40px rgba(0,0,0,.3)",
};
const head: React.CSSProperties = {
  background: "var(--primary)", color: "#fff", padding: "11px 16px",
  fontSize: 15, fontWeight: 700, display: "flex", justifyContent: "space-between",
  alignItems: "center", position: "sticky", top: 0, zIndex: 1,
};
const xBtn: React.CSSProperties = {
  background: "none", border: 0, color: "#fff", cursor: "pointer", fontSize: 15,
};
const note: React.CSSProperties = {
  background: "var(--surface-2)", border: "1px solid var(--border)", color: "var(--muted)",
  fontSize: 12, padding: "9px 12px", borderRadius: 6, lineHeight: 1.9, marginTop: 12,
};
const warn: React.CSSProperties = {
  background: "rgba(224,168,0,.12)", border: "1px solid rgba(224,168,0,.45)",
  color: "var(--text)", fontSize: 12.5, padding: "9px 12px", borderRadius: 7,
  marginBottom: 12, lineHeight: 1.8,
};
