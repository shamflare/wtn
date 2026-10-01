import { useEffect, useState } from "react";
import { api } from "../api";
import Icon from "../components/Icon";
import { money, symbolOf } from "../currency";

interface MField {
  id: number; label: string; kind: string; options: string;
  placeholder: string; required: boolean;
}
interface Method {
  id: number; name: string; subtitle: string; logo_url: string; color: string;
  currency: string; instructions: string; account_box: string; warning: string;
  min_amount: string; max_amount: string; commission_percent: string;
  rate: string; fields_list: MField[];
}
interface Deposit {
  id: number; method_name: string; amount: string; currency: string;
  credit_amount: string; status: string; status_label: string;
  admin_note: string; created_at: string;
}

const STATUS_TONE: Record<string, { bg: string; fg: string }> = {
  pending: { bg: "color-mix(in srgb, var(--warn) 14%, transparent)", fg: "var(--warn)" },
  approved: { bg: "color-mix(in srgb, var(--ok) 14%, transparent)", fg: "var(--ok)" },
  rejected: { bg: "color-mix(in srgb, var(--danger) 14%, transparent)", fg: "var(--danger)" },
};

/* ═════════ القسم: شبكة الطرق · نموذج الطريقة · سجلّ الطلبات ═════════ */
export default function TopUp({ onDone }: { onDone: () => void }) {
  const [methods, setMethods] = useState<Method[]>([]);
  const [walletCurrency, setWalletCurrency] = useState("");
  const [deposits, setDeposits] = useState<Deposit[]>([]);
  const [open, setOpen] = useState<Method | null>(null);
  const [loading, setLoading] = useState(true);

  function loadDeposits() {
    api.get("/payments/store/deposits/").then((r) => setDeposits(r.data.results)).catch(() => {});
  }
  useEffect(() => {
    api.get("/payments/store/methods/")
      .then((r) => { setMethods(r.data.methods); setWalletCurrency(r.data.wallet_currency); })
      .finally(() => setLoading(false));
    loadDeposits();
  }, []);

  if (loading) {
    return (
      <div className="ag-methods">
        {[0, 1, 2, 3].map((i) => <div key={i} className="ag-skel" style={{ height: 170, borderRadius: 22 }} />)}
      </div>
    );
  }

  if (open) {
    return (
      <MethodForm method={open} walletCurrency={walletCurrency}
        onBack={() => setOpen(null)}
        onSent={() => { setOpen(null); loadDeposits(); onDone(); }} />
    );
  }

  return (
    <div>
      {methods.length === 0 ? (
        <div className="ag-empty ag-card">
          لم يفعّل صاحب المتجر أي طريقة دفع بعد — تواصل معه لشحن رصيدك.
        </div>
      ) : (
        <div className="ag-methods">
          {methods.map((m) => (
            <button key={m.id} className="ag-method" onClick={() => setOpen(m)}>
              <span className="ag-method-logo" style={m.logo_url
                ? { backgroundImage: `url(${m.logo_url})`, backgroundColor: "var(--surface-2)" }
                : { background: `linear-gradient(145deg, ${m.color || "#2f6f8f"}, var(--surface))` }}>
                {!m.logo_url && m.name.trim().charAt(0)}
              </span>
              <b>{m.name}</b>
              {m.subtitle && <small>{m.subtitle}</small>}
              <span className="ag-buy-pill">تقديم دفعة</span>
            </button>
          ))}
        </div>
      )}

      {/* سجلّ دفعاتي */}
      <div className="ag-h2">
        <Icon name="receipt" size={18} style={{ color: "var(--primary)" }} />دفعاتي
        {deposits.length > 0 && <span className="more">{deposits.length}</span>}
      </div>
      {deposits.length === 0 ? (
        <div className="ag-empty">لا توجد دفعات بعد</div>
      ) : (
        <div className="ag-list">
          {deposits.map((d) => <DepositRow key={d.id} d={d} />)}
        </div>
      )}
      <p style={{ color: "var(--muted)", fontSize: 12.5, marginTop: 14, lineHeight: 1.9 }}>
        لا يُضاف الرصيد إلى محفظتك إلا بعد موافقة صاحب المتجر على طلبك.
      </p>
    </div>
  );
}

/** دفعةٌ واحدة: سطرٌ مختصر، يُفتح على تفاصيلها */
function DepositRow({ d }: { d: Deposit }) {
  const [open, setOpen] = useState(false);
  const tone = STATUS_TONE[d.status] || { bg: "color-mix(in srgb, var(--muted) 14%, transparent)", fg: "var(--muted)" };
  return (
    <div className={`ag-acc${open ? " open" : ""}`}>
      <button className="ag-acc-head" onClick={() => setOpen((o) => !o)} aria-expanded={open}>
        <b>
          {d.method_name || "—"}
          <span style={{ display: "block", fontSize: 12, color: "var(--muted)", fontWeight: 600 }}>
            <span dir="ltr">{money(d.amount)} {symbolOf(d.currency)}</span> · {d.created_at}
          </span>
        </b>
        <span className="ag-pillst" style={{ background: tone.bg, color: tone.fg }}>{d.status_label}</span>
        <Icon name="chevronDown" size={18} style={{ transition: "transform .2s", transform: open ? "rotate(180deg)" : "none", color: "var(--muted)" }} />
      </button>
      {open && (
        <div className="ag-acc-body">
          <div className="ag-kv"><span>رقم الطلب</span><b dir="ltr">#{d.id}</b></div>
          <div className="ag-kv"><span>المبلغ المُرسل</span><b dir="ltr">{money(d.amount)} {symbolOf(d.currency)}</b></div>
          <div className="ag-kv"><span>المُضاف للمحفظة</span><b style={{ color: "var(--primary)" }}>{money(d.credit_amount)}</b></div>
          <div className="ag-kv"><span>التاريخ</span><b dir="ltr">{d.created_at}</b></div>
          {d.admin_note && <div className="ag-note"><b>ملاحظة الإدارة:</b> {d.admin_note}</div>}
        </div>
      )}
    </div>
  );
}

/* ═════════ نموذج طريقة واحدة ═════════ */
function MethodForm({
  method, walletCurrency, onBack, onSent,
}: { method: Method; walletCurrency: string; onBack: () => void; onSent: () => void }) {
  const [amount, setAmount] = useState("");
  const [vals, setVals] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [copied, setCopied] = useState(false);

  const rate = Number(method.rate || 1);
  const commission = Number(method.commission_percent || 0);
  const credit = (Number(amount || 0) * rate * (100 - commission)) / 100;
  const sym = symbolOf(method.currency);

  function copyAccount() {
    navigator.clipboard?.writeText(method.account_box).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1800);
    }).catch(() => {});
  }

  async function submit() {
    setBusy(true); setMsg(null);
    try {
      await api.post("/payments/store/deposits/create/", {
        method: method.id, amount, values: vals,
      });
      onSent();
    } catch (e: any) {
      setMsg({ ok: false, text: e?.response?.data?.detail || "تعذّر إرسال الطلب" });
    } finally { setBusy(false); }
  }

  return (
    <div style={{ maxWidth: 720, margin: "0 auto" }}>
      <button onClick={onBack} className="ag-back">
        <Icon name="arrowBack" size={15} />رجوع إلى طرق الدفع
      </button>

      <div style={panel}>
        <h3 style={{ fontSize: 22, fontWeight: 800, textAlign: "center", margin: "0 0 16px" }}>
          {method.name}
        </h3>
        {method.subtitle && (
          <div style={{ textAlign: "center", color: "var(--muted)", fontSize: 13, marginTop: -10, marginBottom: 16 }}>
            {method.subtitle}
          </div>
        )}

        {/* الشرح — سطر لكل بند كما كتبه صاحب المتجر */}
        {method.instructions && (
          <div style={instructions}>
            {method.instructions.split("\n").map((line, i) => (
              <div key={i} style={{ minHeight: line.trim() ? undefined : 8 }}>{line}</div>
            ))}
          </div>
        )}

        {/* صندوق الحساب — بضغطة يُنسخ */}
        {method.account_box && (
          <button onClick={copyAccount} style={accountBox} title="اضغط للنسخ">
            {method.account_box}
            <span style={copyHint}>{copied ? "✓ نُسخ" : "نسخ"}</span>
          </button>
        )}

        {method.warning && <div style={warnBox}>{method.warning}</div>}

        {/* الحقول التي بناها صاحب المتجر */}
        {method.fields_list.map((f) => (
          <div key={f.id} style={{ marginBottom: 12 }}>
            <div style={fieldLabel}>{f.label}{f.required && <span style={{ color: "var(--danger)" }}> *</span>}</div>
            {f.kind === "textarea" ? (
              <textarea rows={5} value={vals[f.id] || ""} placeholder={f.placeholder}
                onChange={(e) => setVals((o) => ({ ...o, [f.id]: e.target.value }))}
                style={{ ...darkInp, height: "auto", resize: "vertical" }} />
            ) : f.kind === "select" ? (
              <select value={vals[f.id] || ""} onChange={(e) => setVals((o) => ({ ...o, [f.id]: e.target.value }))}
                style={darkInp}>
                <option value="">— اختر —</option>
                {f.options.split("|").map((o) => o.trim()).filter(Boolean).map((o) => (
                  <option key={o} value={o}>{o}</option>
                ))}
              </select>
            ) : (
              <input type={f.kind === "number" ? "number" : "text"} value={vals[f.id] || ""}
                placeholder={f.placeholder || (f.kind === "image" ? "https://… رابط صورة الإشعار" : "")}
                onChange={(e) => setVals((o) => ({ ...o, [f.id]: e.target.value }))}
                style={{ ...darkInp, ...(f.kind === "image" ? { direction: "ltr", textAlign: "left" } : {}) }} />
            )}
          </div>
        ))}

        {/* المبلغ */}
        <div style={{ marginBottom: 12 }}>
          <div style={fieldLabel}>
            القيمة
            {Number(method.min_amount) > 0 && (
              <span style={{ color: "var(--muted)", fontWeight: 400 }}> — الحد الأدنى {money(method.min_amount)} {sym}</span>
            )}
          </div>
          <div style={{ position: "relative" }}>
            <input type="number" step="0.01" value={amount} onChange={(e) => setAmount(e.target.value)}
              style={{ ...darkInp, paddingInlineEnd: 44 }} placeholder="0" />
            <span style={inpSymbol}>{sym}</span>
          </div>
        </div>

        {/* المحصّلة */}
        <div style={resultBox}>
          <div style={{ fontSize: 12.5, color: "var(--primary)" }}>القيمة التي سيتم إضافتها إلى رصيدك</div>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
            <b style={{ fontSize: 20 }}>{money(credit)}</b>
            <span style={{ fontSize: 15, color: "var(--primary)" }}>{symbolOf(walletCurrency)} {walletCurrency}</span>
          </div>
          <div style={{ fontSize: 11.5, color: "var(--muted)", marginTop: 4 }}>
            1 {sym} = {money(rate, 4)} {symbolOf(walletCurrency)}
            {commission > 0 && <> · العمولة {money(commission)}%</>}
          </div>
        </div>

        {msg && <div style={{ ...warnBox, background: "color-mix(in srgb, var(--danger) 14%, transparent)", color: "var(--danger)" }}>{msg.text}</div>}

        <button onClick={submit} disabled={busy || !amount} style={submitBtn}>
          {busy ? "جارٍ الإرسال..." : "طلب"}
        </button>
      </div>
    </div>
  );
}

/* ═════════ الأنماط ═════════ */
const panel: React.CSSProperties = {
  background: "var(--surface)", color: "var(--text)", borderRadius: 22, padding: "22px 18px",
  border: "1px solid var(--border)", boxShadow: "var(--shadow-soft)",
};
const instructions: React.CSSProperties = {
  fontSize: 13.5, lineHeight: 2, color: "var(--text)", marginBottom: 16, whiteSpace: "pre-wrap",
};
const accountBox: React.CSSProperties = {
  width: "100%", background: "var(--bg)", color: "var(--text)", border: "1px dashed var(--border-strong)",
  borderRadius: 10, padding: "14px 16px", fontSize: 14, textAlign: "center",
  cursor: "pointer", marginBottom: 14, position: "relative", whiteSpace: "pre-wrap",
};
const copyHint: React.CSSProperties = {
  position: "absolute", insetInlineEnd: 10, top: "50%", transform: "translateY(-50%)",
  fontSize: 10.5, color: "var(--primary)", border: "1px solid color-mix(in srgb, var(--primary) 35%, transparent)", borderRadius: 5, padding: "2px 7px",
};
const warnBox: React.CSSProperties = {
  background: "color-mix(in srgb, var(--gold) 12%, transparent)", color: "var(--gold)", borderRadius: 8,
  padding: "9px 12px", fontSize: 12.5, marginBottom: 14, lineHeight: 1.7,
};
const fieldLabel: React.CSSProperties = { fontSize: 13, color: "var(--muted)", marginBottom: 6, fontWeight: 600 };
const darkInp: React.CSSProperties = { width: "100%" };
const inpSymbol: React.CSSProperties = {
  position: "absolute", insetInlineEnd: 16, top: "50%", transform: "translateY(-50%)",
  color: "var(--muted)", fontSize: 15, pointerEvents: "none",
};
const resultBox: React.CSSProperties = {
  background: "color-mix(in srgb, var(--primary) 12%, transparent)", border: "1px solid color-mix(in srgb, var(--primary) 30%, transparent)", borderRadius: 12,
  padding: "12px 16px", marginBottom: 16,
};
const submitBtn: React.CSSProperties = {
  width: "100%", height: 52, borderRadius: 999, border: 0, cursor: "pointer",
  background: "var(--primary)", color: "var(--on-primary)", fontSize: 16, fontWeight: 800,
  boxShadow: "0 10px 26px color-mix(in srgb, var(--primary) 25%, transparent)",
};
