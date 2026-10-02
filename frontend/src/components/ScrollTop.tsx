import { useEffect, useState } from "react";
import Icon from "./Icon";

/** زرّ طائف يعيد إلى أعلى الصفحة — يظهر فقط بعد النزول. */
export default function ScrollTop() {
  const [show, setShow] = useState(false);

  useEffect(() => {
    const onScroll = () => setShow(window.scrollY > 400);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  if (!show) return null;
  return (
    <button type="button" title="إلى الأعلى" aria-label="إلى الأعلى"
      onClick={() => window.scrollTo({ top: 0, behavior: "smooth" })} style={btn}>
      <Icon name="arrowUp" size={22} />
    </button>
  );
}

const btn: React.CSSProperties = {
  position: "fixed", bottom: 28, left: 28, zIndex: 70,
  width: 48, height: 48, borderRadius: "50%", border: "none", cursor: "pointer",
  background: "var(--primary)", color: "#fff",
  display: "flex", alignItems: "center", justifyContent: "center",
  boxShadow: "0 6px 18px rgba(0,0,0,.25)",
};
