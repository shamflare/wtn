import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api";
import { useAuth } from "../auth";

interface TicketRow {
  id: number; subject: string; target_label: string; status: string;
  status_label: string; opener: string; is_mine: boolean;
  last_message: string; last_at: string; unread: number; can_delete?: boolean;
}
interface Msg { id: number; sender: string; is_me: boolean; body: string; created_at: string }
interface Dealer { id: number; name: string; login_id: string }

/**
 * مكوّن التذاكر/الرسائل — API واعٍ بالدور، فيصلح للوكيل وصاحب المتجر والمنصّة.
 * canCreate: يُظهر زر "رسالة جديدة" (للوكيل → الإدارة، لصاحب المتجر → المنصّة).
 */
export default function Tickets({ canCreate = true, title = "الرسائل" }: { canCreate?: boolean; title?: string }) {
  const [rows, setRows] = useState<TicketRow[]>([]);
  const [open, setOpen] = useState<number | null>(null);
  const [showNew, setShowNew] = useState(false);
  const [delFor, setDelFor] = useState<TicketRow | null>(null);

  function load() { api.get("/tickets/").then((r) => setRows(r.data.results)); }
  useEffect(load, []);

  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 14 }}>
        <h2 style={{ fontSize: 18, margin: 0 }}>{title}</h2>
        {canCreate && <button className="btn g" onClick={() => setShowNew(true)}>✉️ رسالة جديدة</button>}
        <span style={{ marginInlineStart: "auto", color: "var(--muted)", fontSize: 14 }}>العدد: {rows.length}</span>
      </div>

      {rows.length === 0 ? (
        <div style={{ color: "var(--muted)", padding: 20 }}>لا رسائل بعد.</div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {rows.map((t) => (
            <div key={t.id} style={ticketCard} onClick={() => setOpen(t.id)}>
              <div style={{ flex: 1 }}>
                <div style={{ fontWeight: 700 }}>
                  {t.subject}
                  {t.unread > 0 && <span style={badge}>{t.unread}</span>}
                </div>
                <div style={{ fontSize: 12, color: "var(--muted)", marginTop: 3 }}>
                  {t.last_message} · {t.opener} · {t.last_at}
                </div>
              </div>
              <span style={{ fontSize: 12, color: t.status === "open" ? "var(--ok)" : "var(--muted)" }}>
                ● {t.status_label}
              </span>
              {t.can_delete && (
                <button type="button" title="حذف المحادثة" aria-label="حذف المحادثة"
                  onClick={(e) => { e.stopPropagation(); setDelFor(t); }}
                  style={delBtn}>🗑</button>
              )}
            </div>
          ))}
        </div>
      )}

      {open !== null && <Thread id={open} onClose={() => { setOpen(null); load(); }} />}
      {showNew && <NewTicket onClose={() => setShowNew(false)} onDone={() => { setShowNew(false); load(); }} />}
      {delFor && (
        <DeleteTicket ticket={delFor} onClose={() => setDelFor(null)}
          onDone={() => { setDelFor(null); load(); }} />
      )}
    </div>
  );
}

function Thread({ id, onClose }: { id: number; onClose: () => void }) {
  const [data, setData] = useState<any>(null);
  const [body, setBody] = useState("");
  const [busy, setBusy] = useState(false);

  function load() { api.get(`/tickets/${id}/`).then((r) => setData(r.data)); }
  useEffect(load, [id]);

  async function send(e: React.FormEvent) {
    e.preventDefault();
    if (!body.trim()) return;
    setBusy(true);
    try { await api.post(`/tickets/${id}/reply/`, { body }); setBody(""); load(); }
    finally { setBusy(false); }
  }
  async function close() { await api.post(`/tickets/${id}/close/`); onClose(); }

  return (
    <div style={overlay} onClick={onClose}>
      <div style={{ ...modal, width: 560, color: "var(--text)" }} onClick={(e) => e.stopPropagation()}>
        <div style={header}>
          <span>{data?.subject || "..."}</span>
          <button onClick={onClose} style={xBtn}>✕</button>
        </div>
        <div style={{ padding: 16, maxHeight: 380, overflowY: "auto", background: "var(--tk-thread, #f7f9fa)" }}>
          {data?.messages?.map((m: Msg) => (
            <div key={m.id} style={{ display: "flex", justifyContent: m.is_me ? "flex-start" : "flex-end", marginBottom: 8 }}>
              <div style={{ ...bubble, ...(m.is_me ? mine : theirs) }}>
                <div style={{ fontSize: 11, opacity: 0.7, marginBottom: 3 }}>{m.sender} · {m.created_at}</div>
                <div style={{ whiteSpace: "pre-wrap" }}>{m.body}</div>
              </div>
            </div>
          ))}
        </div>
        <form onSubmit={send} style={{ display: "flex", gap: 8, padding: 12, borderTop: "1px solid var(--border)" }}>
          <input style={{ flex: 1, height: 40 }} value={body} onChange={(e) => setBody(e.target.value)} placeholder="اكتب رسالة..." />
          <button className="btn g" style={{ height: 40 }} disabled={busy}>إرسال</button>
          {data?.status === "open" && (
            <button type="button" className="btn" style={{ height: 40, background: "#8a999e" }} onClick={close}>إغلاق</button>
          )}
        </form>
      </div>
    </div>
  );
}

function NewTicket({ onClose, onDone }: { onClose: () => void; onDone: () => void }) {
  const { user } = useAuth();
  const isAdmin = user?.role === "tenant_admin";
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  // "platform" = إلى المنصّة (السلوك القديم) · رقمٌ = إلى وكيلٍ بعينه
  const [to, setTo] = useState("platform");
  const [dealers, setDealers] = useState<Dealer[]>([]);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  // قائمة الوكلاء لصاحب المتجر وحده — الوكيل لا يوجّه رسالته
  useEffect(() => {
    if (!isAdmin) return;
    api.get("/dealers/").then((r) => setDealers(r.data.results || [])).catch(() => {});
  }, [isAdmin]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true); setErr("");
    try { await api.post("/tickets/", { subject, body, recipient: to }); onDone(); }
    catch (e: any) { setErr(e?.response?.data?.detail || "فشل الإرسال"); }
    finally { setBusy(false); }
  }

  return (
    <div style={overlay} onClick={onClose}>
      <form style={{ ...modal, width: 460, color: "var(--text)" }} onClick={(e) => e.stopPropagation()} onSubmit={submit}>
        <div style={header}>رسالة جديدة</div>
        <div style={{ padding: 20 }}>
          {isAdmin && (
            <>
              <label style={lbl}>إلى</label>
              <RecipientPicker value={to} onChange={setTo} dealers={dealers} />
              <div style={{ fontSize: 12, color: "var(--muted)", lineHeight: 1.8, marginTop: 5 }}>
                {to === "platform"
                  ? "تصل إلى مالك المنصّة — لا إلى وكلائك."
                  : "تصل إلى هذا الوكيل وحده، ويراها في جرس لوحته."}
              </div>
            </>
          )}
          <label style={lbl}>الموضوع</label>
          <input style={{ width: "100%", height: 38 }} value={subject} onChange={(e) => setSubject(e.target.value)} required autoFocus />
          <label style={lbl}>الرسالة</label>
          <textarea style={{ width: "100%", height: 100, padding: 8 }} value={body} onChange={(e) => setBody(e.target.value)} required />
          {err && <div style={errBox}>{err}</div>}
          <div style={{ display: "flex", gap: 10, marginTop: 14 }}>
            <button className="btn g" style={{ flex: 1, height: 40 }} disabled={busy}>{busy ? "جارٍ..." : "إرسال"}</button>
            <button type="button" className="btn" style={{ height: 40, background: "#8a999e" }} onClick={onClose}>إلغاء</button>
          </div>
        </div>
      </form>
    </div>
  );
}

/** تأكيد المحو — المحادثة تذهب برسائلها كلّها، ولا رجعة. */
function DeleteTicket({ ticket, onClose, onDone }: {
  ticket: TicketRow; onClose: () => void; onDone: () => void;
}) {
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  async function remove() {
    setBusy(true); setErr("");
    try { await api.delete(`/tickets/${ticket.id}/`); onDone(); }
    catch (e: any) { setErr(e?.response?.data?.detail || "تعذّر الحذف"); }
    finally { setBusy(false); }
  }

  return (
    <div style={overlay} onClick={onClose}>
      <div style={{ ...modal, width: 420, color: "var(--text)" }} onClick={(e) => e.stopPropagation()}>
        <div style={{ ...header, background: "var(--danger)" }}>حذف المحادثة</div>
        <div style={{ padding: 20 }}>
          <div style={{ lineHeight: 2 }}>
            ستُحذف <b>«{ticket.subject}»</b> ومعها كل رسائلها — <b>لا رجعة</b>.
          </div>
          <div style={{ fontSize: 12.5, color: "var(--muted)", lineHeight: 1.9, marginTop: 8 }}>
            وتختفي عن الطرف الآخر أيضاً.
          </div>
          {err && <div style={errBox}>{err}</div>}
          <div style={{ display: "flex", gap: 10, marginTop: 16 }}>
            <button className="btn" style={{ flex: 1, height: 40, background: "var(--danger)" }}
              onClick={remove} disabled={busy}>{busy ? "جارٍ..." : "احذف"}</button>
            <button className="btn" style={{ flex: 1, height: 40, background: "#8a999e" }}
              onClick={onClose}>إلغاء</button>
          </div>
        </div>
      </div>
    </div>
  );
}

/**
 * اختيار المخاطَب مع بحثٍ بالاسم أو برقم الدخول.
 *
 * ليس `<select>`: قائمةُ متجرٍ فيها عشرات الوكلاء تُمرَّر بالإصبع بحثاً عن
 * اسم، والمتصفّح لا يبحث في `<option>` إلا بالحرف الأول وبالإنجليزية.
 */
function RecipientPicker({ value, onChange, dealers }: {
  value: string;
  onChange: (v: string) => void;
  dealers: Dealer[];
}) {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const box = useRef<HTMLDivElement>(null);

  const chosen = value === "platform"
    ? "إدارة المنصّة"
    : dealers.find((d) => String(d.id) === value)?.name || "اختر…";

  const found = useMemo(() => {
    const t = q.trim().toLowerCase();
    if (!t) return dealers;
    return dealers.filter((d) =>
      d.name.toLowerCase().includes(t) || d.login_id.toLowerCase().includes(t));
  }, [q, dealers]);

  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      if (box.current && !box.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [open]);

  function pick(v: string) { onChange(v); setOpen(false); setQ(""); }

  return (
    <div ref={box} style={{ position: "relative" }}>
      <button type="button" onClick={() => setOpen((o) => !o)} style={pickerBtn}>
        <span>{chosen}</span>
        <span style={{ opacity: 0.6 }}>▾</span>
      </button>

      {open && (
        <div style={pickerPanel}>
          <input autoFocus value={q} onChange={(e) => setQ(e.target.value)}
            placeholder="ابحث بالاسم أو رقم الدخول…"
            style={{ width: "100%", height: 34, marginBottom: 6 }} />

          <div style={{ maxHeight: 210, overflowY: "auto" }}>
            <div onClick={() => pick("platform")}
              style={{ ...pickerRow, fontWeight: 700 }}>إدارة المنصّة</div>

            {found.length === 0 ? (
              <div style={{ padding: "10px 8px", color: "var(--muted)", fontSize: 13 }}>
                لا وكيل بهذا الاسم.
              </div>
            ) : found.map((d) => (
              <div key={d.id} onClick={() => pick(String(d.id))}
                style={{ ...pickerRow, ...(String(d.id) === value ? pickerActive : {}) }}>
                {d.name}
                <span style={{ color: "var(--muted)", fontSize: 12 }} dir="ltr"> ({d.login_id})</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

const delBtn: React.CSSProperties = {
  background: "transparent", border: 0, cursor: "pointer", fontSize: 15,
  opacity: 0.55, padding: "2px 4px", lineHeight: 1,
};
const pickerBtn: React.CSSProperties = {
  width: "100%", height: 38, background: "var(--surface)", border: "1px solid var(--border)",
  borderRadius: 6, padding: "0 10px", cursor: "pointer", textAlign: "start",
  display: "flex", alignItems: "center", justifyContent: "space-between",
  color: "var(--text)", fontSize: 14, fontFamily: "inherit",
};
const pickerPanel: React.CSSProperties = {
  position: "absolute", top: 42, insetInlineStart: 0, insetInlineEnd: 0, zIndex: 1100,
  background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 8, padding: 8,
  boxShadow: "0 12px 34px rgba(0,0,0,.22)",
};
const pickerRow: React.CSSProperties = {
  padding: "8px 8px", borderRadius: 5, cursor: "pointer", fontSize: 14,
};
const pickerActive: React.CSSProperties = { background: "#e7f6ec" };

const ticketCard: React.CSSProperties = {
  display: "flex", alignItems: "center", gap: 12, background: "var(--surface)",
  border: "1px solid var(--border)", borderRadius: 10, padding: "12px 16px", cursor: "pointer",
};
const badge: React.CSSProperties = {
  background: "var(--danger)", color: "#fff", fontSize: 11, fontWeight: 700,
  borderRadius: 10, padding: "1px 7px", marginInlineStart: 8,
};
const overlay: React.CSSProperties = {
  position: "fixed", inset: 0, background: "rgba(0,0,0,.5)",
  display: "flex", alignItems: "center", justifyContent: "center", zIndex: 1000,
};
const modal: React.CSSProperties = { background: "var(--surface)", borderRadius: 10, overflow: "hidden", boxShadow: "0 16px 50px rgba(0,0,0,.35)" };
const header: React.CSSProperties = {
  background: "var(--primary)", color: "#fff", padding: "14px 18px", fontWeight: 700,
  fontSize: 16, display: "flex", justifyContent: "space-between", alignItems: "center",
};
const xBtn: React.CSSProperties = { background: "transparent", border: 0, color: "#fff", fontSize: 18, cursor: "pointer" };
const bubble: React.CSSProperties = { maxWidth: "75%", borderRadius: 10, padding: "8px 12px", fontSize: 14 };
const mine: React.CSSProperties = { background: "var(--tk-mine, #e7f6ec)", border: "1px solid var(--tk-mine-bd, #b6e0c4)" };
const theirs: React.CSSProperties = { background: "var(--surface)", border: "1px solid var(--border)" };
const lbl: React.CSSProperties = { display: "block", fontSize: 13, color: "var(--muted)", margin: "12px 2px 5px" };
const errBox: React.CSSProperties = {
  background: "#fdecea", border: "1px solid #f5c6c2", color: "var(--danger)",
  fontSize: 13, padding: "9px 12px", borderRadius: 5, marginTop: 12,
};
