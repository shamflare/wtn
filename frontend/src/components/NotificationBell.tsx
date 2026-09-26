import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import Icon from "./Icon";

interface Item {
  kind: "message" | "card";
  id: number;
  ticket?: number;
  title: string;
  body: string;
  who: string;
  at: string;
}

/**
 * جرس الهيدر: ما لم يُقرأ من الرسائل وما لم يُفتح من البطاقات، في مكانٍ واحد.
 *
 * كان عدّاد الرسائل شارةً على تبويب «الدعم» وحده — تُرى إن نظر الوكيل إلى
 * الشريط، ولا تُرى وهو في صفحةٍ أخرى. والبطاقات لم يكن لها تنبيهٌ أصلاً:
 * تظهر صامتةً في الرئيسية، فمن لا يمرّ بها لا يعرف أن صاحب متجره كتب شيئاً.
 *
 * والفتحُ لا يمسح الرسائل: قراءتها تقع عند فتح المحادثة نفسها، فمسحُها هنا
 * يُخفي ما لم يُقرأ. أمّا البطاقات فالفتح **هو** رؤيتها.
 */
export default function NotificationBell({ onOpenItem }: {
  onOpenItem?: (item: Item) => void;
}) {
  const [data, setData] = useState<{ total: number; messages: number; cards: number; items: Item[] } | null>(null);
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);

  function load() {
    api.get("/notifications/").then((r) => setData(r.data)).catch(() => {});
  }

  useEffect(() => {
    load();
    const id = setInterval(load, 15000);
    return () => clearInterval(id);
  }, []);

  // النقر خارج اللوحة يغلقها — بدونه تبقى معلّقة فوق ما يريد قراءته
  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      if (box.current && !box.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [open]);

  async function toggle() {
    const next = !open;
    setOpen(next);
    if (next && data?.cards) {
      // فتحُ اللوحة هو رؤيةُ البطاقات — نعلّمها ثم نعيد التحميل
      await api.post("/my-cards/seen/", {}).catch(() => {});
      load();
    }
  }

  const total = data?.total || 0;

  return (
    <div ref={box} style={{ position: "relative" }}>
      <button onClick={toggle} className="ag-icon-btn" title="الإشعارات" aria-label="الإشعارات">
        <Icon name="bell" size={19} />
        {total > 0 && <span className="ag-badge">{total > 9 ? "9+" : total}</span>}
      </button>

      {open && (
        <div className="ag-bell-panel">
          <div className="ag-bell-head">
            الإشعارات
            {total > 0 && (
              <span>
                {data?.messages ? `${data.messages} رسالة` : ""}
                {data?.messages && data?.cards ? " · " : ""}
                {data?.cards ? `${data.cards} إعلان` : ""}
              </span>
            )}
          </div>

          {!data?.items.length ? (
            <div style={{ padding: "30px 16px", color: "var(--muted)", fontSize: 14, textAlign: "center" }}>
              <Icon name="bell" size={28} style={{ display: "block", margin: "0 auto 8px", opacity: 0.5 }} />
              لا جديد.
            </div>
          ) : (
            <div style={{ maxHeight: "min(420px, 60vh)", overflowY: "auto" }}>
              {data.items.map((it) => (
                <div key={`${it.kind}-${it.id}`} className="ag-bell-row"
                  onClick={() => { setOpen(false); onOpenItem?.(it); }}>
                  <span className="ag-bell-ic" style={it.kind === "message"
                    ? { background: "rgba(47,226,123,.12)", color: "#2fe27b" }
                    : { background: "rgba(255,194,61,.12)", color: "#ffc23d" }}>
                    <Icon name={it.kind === "message" ? "chat" : "bell"} size={16} />
                  </span>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontWeight: 700, fontSize: 13.5 }}>{it.title}</div>
                    <div style={{ fontSize: 12, color: "var(--muted)", marginTop: 2,
                                  overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                      {it.who ? `${it.who} · ` : ""}{it.body}
                    </div>
                    <div style={{ fontSize: 11, color: "var(--faint)", marginTop: 2 }}>{it.at}</div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
