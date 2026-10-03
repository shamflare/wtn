import { useRef, useState } from "react";
import { api } from "../api";

/**
 * صورةٌ من الجهاز بدل لصق رابط.
 *
 * تُصغَّر في المتصفّح قبل الرفع (أطول ضلعٍ 640px، WEBP): صورة هاتفٍ بأربعة
 * ميغابايت تصير بضع عشرات من الكيلوبايت، فلا تثقل القاعدة ولا جوال الوكيل.
 * والخادم يعيد رابطاً قصيراً ثابتاً (`/api/catalog/img/…`) هو ما يُحفظ في
 * الحقل — فكل ما كان يقرأ `image_url` يبقى كما هو.
 */
const MAX_SIDE = 640;

/**
 * `sharp`: للباركود وما شابه — PNG بلا فقد وحتى 1024px، فضغط WEBP يطمس حوافّ
 * المربعات وقد يعجز الماسح عن قراءتها.
 */
async function shrink(file: File, sharp = false): Promise<Blob> {
  // GIF المتحرّك يفقد حركته على اللوحة — يُرفع كما هو
  if (file.type === "image/gif") return file;
  const maxSide = sharp ? 1024 : MAX_SIDE;
  const url = URL.createObjectURL(file);
  try {
    const img = await new Promise<HTMLImageElement>((ok, bad) => {
      const i = new Image();
      i.onload = () => ok(i);
      i.onerror = () => bad(new Error("bad image"));
      i.src = url;
    });
    const scale = Math.min(1, maxSide / Math.max(img.naturalWidth, img.naturalHeight));
    const canvas = document.createElement("canvas");
    canvas.width = Math.max(1, Math.round(img.naturalWidth * scale));
    canvas.height = Math.max(1, Math.round(img.naturalHeight * scale));
    const ctx = canvas.getContext("2d")!;
    if (sharp) ctx.imageSmoothingEnabled = scale === 1;
    ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
    const blob = await new Promise<Blob | null>((ok) =>
      sharp ? canvas.toBlob(ok, "image/png") : canvas.toBlob(ok, "image/webp", 0.86));
    // متصفّحٌ لا يكتب WEBP يعيد PNG — وهذا مقبولٌ أيضاً
    return blob && blob.size < file.size ? blob : file;
  } finally {
    URL.revokeObjectURL(url);
  }
}

/** يصغّر الصورة ويرفعها ⇐ رابطها القصير الثابت. يرمي رسالة الخادم إن رُفضت. */
export async function uploadImage(file: File): Promise<string> {
  if (!file.type.startsWith("image/")) throw new Error("الملف المختار ليس صورة");
  const blob = await shrink(file);
  const fd = new FormData();
  fd.append("file", blob, file.name);
  try {
    const r = await api.post("/catalog/images/", fd);
    return r.data.url;
  } catch (e: any) {
    throw new Error(e?.response?.data?.detail || "تعذّر رفع الصورة");
  }
}

export default function ImageUpload({ value, onChange, size = 88, sharp = false }: {
  value: string; onChange: (url: string) => void; size?: number;
  /** صورة باركود: بلا ضغط ولا قصّ في المعاينة */
  sharp?: boolean;
}) {
  const input = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [showUrl, setShowUrl] = useState(false);

  async function pick(file: File | undefined) {
    if (!file) return;
    setErr("");
    if (!file.type.startsWith("image/")) { setErr("الملف المختار ليس صورة"); return; }
    setBusy(true);
    try {
      const blob = await shrink(file, sharp);
      const fd = new FormData();
      fd.append("file", blob, file.name);
      const r = await api.post("/catalog/images/", fd);
      onChange(r.data.url);
    } catch (e: any) {
      setErr(e?.response?.data?.detail || "تعذّر رفع الصورة");
    } finally {
      setBusy(false);
      if (input.current) input.current.value = "";
    }
  }

  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
        <div
          onClick={() => !busy && input.current?.click()}
          onDragOver={(e) => e.preventDefault()}
          onDrop={(e) => { e.preventDefault(); pick(e.dataTransfer.files?.[0]); }}
          title="اضغط أو اسحب صورة إلى هنا"
          style={{
            width: size, height: size, borderRadius: 10, flexShrink: 0, cursor: busy ? "wait" : "pointer",
            border: value ? "1px solid #cbd5e1" : "2px dashed #cbd5e1", background: "#f8fafc",
            display: "grid", placeItems: "center", overflow: "hidden", color: "#94a3b8", fontSize: 12, textAlign: "center",
          }}>
          {busy ? "جارٍ الرفع..." : value
            ? <img src={value} alt="" style={{ width: "100%", height: "100%", objectFit: sharp ? "contain" : "cover", background: sharp ? "#fff" : undefined }} />
            : <span>📷<br />لا صورة</span>}
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 6, alignItems: "flex-start" }}>
          <button type="button" className="btn g" style={{ height: 34 }} disabled={busy}
            onClick={() => input.current?.click()}>
            {value ? "تغيير الصورة" : "رفع صورة من الجهاز"}
          </button>
          <div style={{ display: "flex", gap: 10, fontSize: 12 }}>
            {value && (
              <button type="button" onClick={() => onChange("")} disabled={busy}
                style={{ background: "none", border: 0, padding: 0, color: "#b0463a", cursor: "pointer" }}>إزالة</button>
            )}
            <button type="button" onClick={() => setShowUrl((v) => !v)}
              style={{ background: "none", border: 0, padding: 0, color: "#64748b", cursor: "pointer" }}>
              {showUrl ? "إخفاء الرابط" : "أو الصق رابطاً"}
            </button>
          </div>
        </div>
        <input ref={input} type="file" accept="image/png,image/jpeg,image/webp,image/gif" hidden
          onChange={(e) => pick(e.target.files?.[0])} />
      </div>
      {showUrl && (
        <input dir="ltr" value={value} onChange={(e) => onChange(e.target.value.trim())}
          placeholder="https://..." style={{ width: "100%", height: 34, marginTop: 8 }} />
      )}
      {err && <div style={{ color: "#b0463a", fontSize: 12.5, marginTop: 6 }}>{err}</div>}
    </div>
  );
}
