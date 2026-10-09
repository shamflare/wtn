/**
 * التنقّل بين صفحات النوافذ المالية — 20 صفّاً للصفحة، والخادم يقطع (core/statement.py).
 * لا يظهر إن كانت الصفحة واحدة.
 */
export interface Paging { page: number; pages: number; count: number; page_size: number }

export default function Pager({ paging, onPage }: { paging?: Paging | null; onPage: (p: number) => void }) {
  if (!paging || paging.pages <= 1) return null;
  const { page, pages, count, page_size } = paging;
  // نافذة أرقام حول الصفحة الحالية — لا عشرات الأزرار
  const nums: number[] = [];
  for (let p = Math.max(1, page - 2); p <= Math.min(pages, page + 2); p++) nums.push(p);
  const from = (page - 1) * page_size + 1;
  const to = Math.min(count, page * page_size);
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 6, padding: "10px 4px", flexWrap: "wrap" }}>
      <span style={{ fontSize: 12.5, color: "var(--muted)", marginInlineEnd: "auto" }}>
        {from}–{to} من {count}
      </span>
      <Btn disabled={page <= 1} onClick={() => onPage(1)}>«</Btn>
      <Btn disabled={page <= 1} onClick={() => onPage(page - 1)}>‹</Btn>
      {nums[0] > 1 && <span style={{ color: "var(--faint)" }}>…</span>}
      {nums.map((p) => <Btn key={p} active={p === page} onClick={() => onPage(p)}>{p}</Btn>)}
      {nums[nums.length - 1] < pages && <span style={{ color: "var(--faint)" }}>…</span>}
      <Btn disabled={page >= pages} onClick={() => onPage(page + 1)}>›</Btn>
      <Btn disabled={page >= pages} onClick={() => onPage(pages)}>»</Btn>
    </div>
  );
}

function Btn({ children, onClick, disabled, active }: {
  children: React.ReactNode; onClick: () => void; disabled?: boolean; active?: boolean;
}) {
  return (
    <button type="button" disabled={disabled} onClick={onClick} style={{
      minWidth: 30, height: 30, padding: "0 8px", borderRadius: 7, cursor: disabled ? "default" : "pointer",
      border: "1px solid var(--border)", fontSize: 13, fontWeight: active ? 800 : 500,
      background: active ? "var(--primary)" : "var(--surface)", color: active ? "#fff" : "var(--text)",
      opacity: disabled ? .4 : 1,
    }}>{children}</button>
  );
}
