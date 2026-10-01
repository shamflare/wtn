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
export type NotificationItem = Item;
type NotifData = { total: number; messages: number; cards: number; items: Item[] };

/** الإشعارات مع تحديثٍ كل ١٥ ثانية — للجرس وللخانة في الشريط السفلي. */
export function useNotifications() {
  const [data, setData] = useState<NotifData | null>(null);

  function load() {
    api.get("/notifications/").then((r) => setData(r.data)).catch(() => {});
  }

  useEffect(() => {
    load();
    const id = setInterval(load, 15000);
    return () => clearInterval(id);
  }, []);

  /** فتحُ القائمة هو رؤيةُ البطاقات — نعلّمها ثم نعيد التحميل */
  async function markSeen() {
    if (!data?.cards) return;
    await api.post("/my-cards/seen/", {}).catch(() => {});
    load();
  }

  return { data, total: data?.total || 0, markSeen };
}

/** ملخّص العدّ: «٢ رسالة · ١ إعلان» */
export function NotificationSummary({ data }: { data: NotifData | null }) {
  if (!data?.total) return null;
  return (
    <span>
      {data.messages ? `${data.messages} رسالة` : ""}
      {data.messages && data.cards ? " · " : ""}
      {data.cards ? `${data.cards} إعلان` : ""}
    </span>
  );
}

/** قائمة الإشعارات نفسها — داخل لوحة الجرس أو في ورقةٍ سفلية. */
export function NotificationList({ data, onPick }: {
  data: NotifData | null; onPick: (it: Item) => void;
}) {
  if (!data?.items.length) {
    return (
      <div style={{ padding: "30px 16px", color: "var(--muted)", fontSize: 14, textAlign: "center" }}>
        <Icon name="bell" size={28} style={{ display: "block", margin: "0 auto 8px", opacity: 0.5 }} />
        لا جديد.
      </div>
    );
  }
  return (
    <div>
      {data.items.map((it) => (
        <div key={`${it.kind}-${it.id}`} className="ag-bell-row" onClick={() => onPick(it)}>
          <span className="ag-bell-ic" style={it.kind === "message"
            ? { background: "color-mix(in srgb, var(--ok) 12%, transparent)", color: "var(--ok)" }
            : { background: "color-mix(in srgb, var(--gold) 12%, transparent)", color: "var(--gold)" }}>
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
  );
}

export default function NotificationBell({ onOpenItem }: {
  onOpenItem?: (item: Item) => void;
}) {
  const { data, total, markSeen } = useNotifications();
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);

  // النقر خارج اللوحة يغلقها — بدونه تبقى معلّقة فوق ما يريد قراءته
  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      if (box.current && !box.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [open]);

  function toggle() {
    const next = !open;
    setOpen(next);
    if (next) markSeen();
  }

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
            <NotificationSummary data={data} />
          </div>
          <div style={{ maxHeight: "min(420px, 60vh)", overflowY: "auto" }}>
            <NotificationList data={data} onPick={(it) => { setOpen(false); onOpenItem?.(it); }} />
          </div>
        </div>
      )}
    </div>
  );
}
