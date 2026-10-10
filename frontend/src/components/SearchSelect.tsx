import { useEffect, useMemo, useRef, useState } from "react";
import { matches } from "../search";

export interface SearchOption { id: number | string; name: string; sub?: string }

/**
 * قائمة منسدلة ببحث داخلها — لقوائم الوكلاء الطويلة. «الكل» أوّلها دائماً.
 * البحث بالاسم أو السطر الثانوي (رقم الدخول مثلاً) أو المعرّف.
 */
export default function SearchSelect({ options, value, onChange, allLabel = "الكل", width = 240, placeholder = "ابحث..." }: {
  options: SearchOption[]; value: string; onChange: (v: string) => void;
  allLabel?: string; width?: number; placeholder?: string;
}) {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent) => { if (!box.current?.contains(e.target as Node)) setOpen(false); };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [open]);

  const shown = useMemo(
    () => options.filter((o) => !q.trim() || matches(q, o.name, o.sub, o.id)).slice(0, 200),
    [options, q],
  );
  const current = options.find((o) => String(o.id) === value);
  const pick = (v: string) => { onChange(v); setOpen(false); setQ(""); };

  return (
    <div ref={box} style={{ position: "relative", width }}>
      <button type="button" onClick={() => setOpen((v) => !v)} style={{
        width: "100%", height: 36, borderRadius: 8, border: "1px solid var(--border)", background: "var(--surface)",
        display: "flex", alignItems: "center", gap: 6, padding: "0 10px", cursor: "pointer", color: "var(--text)",
        fontSize: 13.5, textAlign: "start",
      }}>
        <span style={{ flex: 1, overflow: "hidden", whiteSpace: "nowrap", textOverflow: "ellipsis" }}>
          {current ? current.name : allLabel}
        </span>
        <span style={{ fontSize: 10, color: "var(--muted)" }}>▼</span>
      </button>
      {open && (
        <div style={{
          position: "absolute", top: 40, insetInlineStart: 0, width: Math.max(width, 260), zIndex: 60,
          background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 10,
          boxShadow: "0 10px 30px rgba(0,0,0,.18)", overflow: "hidden",
        }}>
          <input autoFocus value={q} onChange={(e) => setQ(e.target.value)} placeholder={placeholder}
            style={{ width: "100%", height: 36, border: 0, borderBottom: "1px solid var(--border)", padding: "0 10px", borderRadius: 0 }} />
          <div style={{ maxHeight: 280, overflowY: "auto" }}>
            <Item active={!value} onClick={() => pick("")}>{allLabel}</Item>
            {shown.map((o) => (
              <Item key={o.id} active={String(o.id) === value} onClick={() => pick(String(o.id))}>
                {o.name}{o.sub && <span style={{ color: "var(--faint)", fontSize: 11.5, marginInlineStart: 6 }}>{o.sub}</span>}
              </Item>
            ))}
            {shown.length === 0 && <div style={{ padding: 12, color: "var(--muted)", fontSize: 13 }}>لا نتائج</div>}
          </div>
        </div>
      )}
    </div>
  );
}

function Item({ children, onClick, active }: { children: React.ReactNode; onClick: () => void; active?: boolean }) {
  return (
    <div onClick={onClick} style={{
      padding: "8px 12px", cursor: "pointer", fontSize: 13.5,
      background: active ? "var(--row-alt)" : undefined, fontWeight: active ? 700 : 400,
    }}
      onMouseEnter={(e) => (e.currentTarget.style.background = "var(--row-alt)")}
      onMouseLeave={(e) => (e.currentTarget.style.background = active ? "var(--row-alt)" : "")}>
      {children}
    </div>
  );
}
