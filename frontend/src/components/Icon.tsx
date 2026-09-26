// نظام أيقونات SVG حديث وواضح (خطّي، يرث لون النص عبر currentColor).
import type { CSSProperties } from "react";

const P: Record<string, string> = {
  home: "M3 11l9-8 9 8M5 10v10h14V10",
  games: "M6 12h4M8 10v4M15 11h.01M18 13h.01M4 8h16a1 1 0 0 1 1 1l-1 7a3 3 0 0 1-5 1l-1-1H9l-1 1a3 3 0 0 1-5-1L2 9a1 1 0 0 1 1-1z",
  settings: "M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM19 12a7 7 0 0 0-.1-1l2-1.6-2-3.4-2.4 1a7 7 0 0 0-1.7-1L14.4 2h-4l-.4 2.5a7 7 0 0 0-1.7 1l-2.4-1-2 3.4L4 11a7 7 0 0 0 0 2l-2 1.6 2 3.4 2.4-1a7 7 0 0 0 1.7 1l.4 2.5h4l.4-2.5a7 7 0 0 0 1.7-1l2.4 1 2-3.4-2-1.6c.1-.3.1-.7.1-1z",
  chart: "M4 20V10M10 20V4M16 20v-7M22 20H2",
  wallet: "M3 7h16a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7zM3 7l2-3h11M17 13h.01",
  bell: "M18 8a6 6 0 1 0-12 0c0 7-3 9-3 9h18s-3-2-3-9M13.7 21a2 2 0 0 1-3.4 0",
  chat: "M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z",
  api: "M9 3v6M9 15v6M4 9h5M4 15h5M14 6l6 6-6 6M20 12H9",
  users: "M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM23 21v-2a4 4 0 0 0-3-3.9M16 3.1a4 4 0 0 1 0 7.8",
  user: "M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2M12 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8z",
  edit: "M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7M18.5 2.5a2.1 2.1 0 0 1 3 3L12 15l-4 1 1-4z",
  trash: "M3 6h18M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6M10 11v6M14 11v6",
  plus: "M12 5v14M5 12h14",
  minus: "M5 12h14",
  card: "M2 7h20v12a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1V7zM2 7l1-3h18l1 3M2 11h20",
  calendar: "M3 5h18v16H3zM3 9h18M8 3v4M16 3v4",
  print: "M6 9V3h12v6M6 18H4a2 2 0 0 1-2-2v-4a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v4a2 2 0 0 1-2 2h-2M6 14h12v7H6z",
  wrench: "M14.7 6.3a4 4 0 0 0 5 5l-9.5 9.4a2 2 0 0 1-3-3z",
  refresh: "M21 12a9 9 0 1 1-3-6.7L21 8M21 3v5h-5",
  sun: "M12 17a5 5 0 1 0 0-10 5 5 0 0 0 0 10zM12 1v2M12 21v2M4.2 4.2l1.4 1.4M18.4 18.4l1.4 1.4M1 12h2M21 12h2M4.2 19.8l1.4-1.4M18.4 5.6l1.4-1.4",
  search: "M11 19a8 8 0 1 0 0-16 8 8 0 0 0 0 16zM21 21l-4.3-4.3",
  // كشف تفصيلي — لأزرار «التفاصيل» في الجداول. المكبّرة تعني «ابحث» لا «اعرض ما جرى»
  details: "M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7zM15 2v5h5M8 12h8M8 16h5",
  logout: "M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9",
  cart: "M3 3h2l2.4 12.4a1 1 0 0 0 1 .8h9.7a1 1 0 0 0 1-.8L23 6H6M9 21a1 1 0 1 0 0-2 1 1 0 0 0 0 2zM19 21a1 1 0 1 0 0-2 1 1 0 0 0 0 2z",
  check: "M20 6L9 17l-5-5",
  x: "M18 6L6 18M6 6l12 12",
  building: "M4 21V4a1 1 0 0 1 1-1h9a1 1 0 0 1 1 1v17M15 8h4a1 1 0 0 1 1 1v12M8 7h2M8 11h2M8 15h2",
  store: "M3 9l1.5-5h15L21 9M3 9v11h18V9M3 9h18M9 20v-6h6v6",
  excel: "M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9zM14 3v6h6M9 13l6 4M15 13l-6 4",
  filter: "M22 3H2l8 9.5V19l4 2v-8.5z",
  warning: "M10.3 3.9L1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0zM12 9v4M12 17h.01",
  flag: "M4 15s1-1 4-1 5 2 8 2 4-1 4-1V3s-1 1-4 1-5-2-8-2-4 1-4 1zM4 22v-7",
  dollar: "M12 1v22M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6",
  // واتساب: فقاعة محادثة وفيها سمّاعة — خطّية لتنسجم مع بقيّة الأيقونات
  whatsapp: "M21 11.5a8.5 8.5 0 0 1-12.6 7.4L3 21l2.2-5.2A8.5 8.5 0 1 1 21 11.5zM9 8.5c-.6 0-1 .5-1 1.1 0 2.4 2 4.4 4.4 4.4.6 0 1.1-.4 1.1-1v-.8l-1.6-.6-.7.8a4 4 0 0 1-1.6-1.6l.8-.7L9.8 8.5z",
  // ربط جهاز — حلقتا سلسلة
  link: "M10 13a5 5 0 0 0 7 0l3-3a5 5 0 0 0-7-7l-1 1M14 11a5 5 0 0 0-7 0l-3 3a5 5 0 0 0 7 7l1-1",
  // إظهار المخفيّ — عين
  eye: "M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7-10-7-10-7zM12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6z",
  // شجرة الوكلاء — أصل تتفرّع منه عقدتان
  tree: "M12 3v5M12 8H6v4M12 8h6v4M4 12h4v4H4zM10 12h4v4h-4zM16 12h4v4h-4z",
  // ——— لوحة الوكيل ———
  grid: "M4 4h6v6H4zM14 4h6v6h-6zM4 14h6v6H4zM14 14h6v6h-6z",
  receipt: "M5 3h14v18l-3-2-2 2-2-2-2 2-2-2-3 2zM9 8h6M9 12h6M9 16h3",
  copy: "M9 9h11v11H9zM5 15H4V4h11v1",
  chevronDown: "M6 9l6 6 6-6",
  arrowBack: "M5 12h14M13 6l6 6-6 6",
  clock: "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM12 7v5l3 2",
  phone: "M22 16.9v3a2 2 0 0 1-2.2 2 19.8 19.8 0 0 1-8.6-3.1 19.5 19.5 0 0 1-6-6A19.8 19.8 0 0 1 2.1 4.2 2 2 0 0 1 4.1 2h3a2 2 0 0 1 2 1.7c.1.9.4 1.8.7 2.7a2 2 0 0 1-.5 2.1L8 9.8a16 16 0 0 0 6 6l1.3-1.3a2 2 0 0 1 2.1-.4c.9.3 1.8.6 2.7.7a2 2 0 0 1 1.7 2z",
  hash: "M4 9h16M4 15h16M10 3L8 21M16 3l-2 18",
  plusCircle: "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM12 8v8M8 12h8",
  download: "M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 10l5 5 5-5M12 15V3",
  bolt: "M13 2L3 14h9l-1 8 10-12h-9z",
  lock: "M5 11h14v10H5zM8 11V7a4 4 0 0 1 8 0v4",
  tag: "M20.6 13.4l-7.2 7.2a2 2 0 0 1-2.8 0L2 12V2h10l8.6 8.6a2 2 0 0 1 0 2.8zM7 7h.01",
  arrowDown: "M12 5v14M5 12l7 7 7-7",
  arrowUp: "M12 19V5M5 12l7-7 7 7",
};

interface Props { name: keyof typeof P | string; size?: number; color?: string; style?: CSSProperties; }

export default function Icon({ name, size = 18, color = "currentColor", style }: Props) {
  const d = P[name] || P.settings;
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none"
      stroke={color} strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round"
      style={{ display: "inline-block", verticalAlign: "middle", ...style }}>
      <path d={d} />
    </svg>
  );
}
