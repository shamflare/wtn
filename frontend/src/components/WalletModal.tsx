import { useState } from "react";
import { api, type Dealer } from "../api";
import { labelOf, symbolOf } from "../currency";

interface Props {
  dealer: Dealer;
  action: "topup" | "deduct";
  onClose: () => void;
  onDone: (r: { balance: string; balance_own?: string }) => void;
}

export default function WalletModal({ dealer, action, onClose, onDone }: Props) {
  const [amount, setAmount] = useState("");
  const [note, setNote] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const isTopup = action === "topup";
  const own = dealer.own_currency || dealer.currency;
  const title = isTopup ? "شحن رصيد" : "خصم رصيد";
  const color = isTopup ? "var(--ok)" : "var(--danger)";

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      const r = await api.post(`/dealers/${dealer.id}/${action}/`, { amount, note });
      onDone(r.data);
    } catch (e: any) {
      setError(e?.response?.data?.detail || "فشلت العملية");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div style={overlay} onClick={onClose}>
      <form style={modal} onClick={(e) => e.stopPropagation()} onSubmit={submit}>
        <div style={{ ...header, background: color }}>
          {title} — {dealer.name}
        </div>
        <div style={{ padding: 20 }}>
          <div style={{ fontSize: 13, color: "var(--muted)", marginBottom: 14 }}>
            الرصيد الحالي:{" "}
            <b style={{ color: Number(dealer.balance_own ?? dealer.balance) < 0 ? "var(--danger)" : "var(--text)" }}>
              {Number(dealer.balance_own ?? dealer.balance).toLocaleString("en-US", { minimumFractionDigits: 2 })}
            </b>{" "}
            {symbolOf(own)} <span style={{ fontSize: 11.5 }}>({own})</span>
          </div>

          {/* بعملة الوكيل: يقبض صاحب المتجر منه ليراتٍ فيكتب ليرات — والدفتر يُحوَّل وحده */}
          <label style={lbl}>المبلغ بـ{labelOf(own)} ({symbolOf(own)})</label>
          <input
            style={{ width: "100%", height: 38 }}
            type="number"
            step="0.01"
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
            placeholder="0.00"
            autoFocus
          />

          <label style={lbl}>ملاحظة (اختياري)</label>
          <input
            style={{ width: "100%", height: 38 }}
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="سبب العملية..."
          />

          {error && <div style={errBox}>{error}</div>}

          <div style={{ display: "flex", gap: 10, marginTop: 18 }}>
            <button className="btn" style={{ flex: 1, height: 40, background: color }} disabled={busy}>
              {busy ? "جارٍ..." : isTopup ? "➕ شحن" : "➖ خصم"}
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
  position: "fixed",
  inset: 0,
  background: "rgba(0,0,0,.45)",
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  zIndex: 1000,
};
const modal: React.CSSProperties = {
  width: 420,
  background: "#fff",
  borderRadius: 8,
  overflow: "hidden",
  boxShadow: "0 16px 50px rgba(0,0,0,.35)",
};
const header: React.CSSProperties = {
  color: "#fff",
  padding: "14px 20px",
  fontSize: 16,
  fontWeight: 700,
};
const lbl: React.CSSProperties = {
  display: "block",
  fontSize: 13,
  color: "var(--muted)",
  margin: "14px 2px 5px",
};
const errBox: React.CSSProperties = {
  background: "#fdecea",
  border: "1px solid #f5c6c2",
  color: "var(--danger)",
  fontSize: 13,
  padding: "9px 12px",
  borderRadius: 5,
  marginTop: 14,
};
