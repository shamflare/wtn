import { useEffect, useState } from "react";
import { api } from "../api";
import Icon from "./Icon";

interface TokenRow {
  allowed: boolean;
  detail?: string;
  token: string;
  created_at: string;
  last_used_at: string;
  calls: number;
}

/**
 * صفحة «API» في لوحة الوكيل — توثيقٌ يقرؤه مبرمج الجهة الخارجية.
 *
 * الأمثلة مكتوبة **بتوكن صاحب الصفحة نفسه** لا بـ `YOUR_TOKEN`: هذا الفرق
 * الصغير هو ما يجعلها تُنسخ وتعمل من أول مرّة بدل أن تُقرأ ثم تُترك.
 */
export default function ApiDocs() {
  const [row, setRow] = useState<TokenRow | null>(null);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [show, setShow] = useState(false);
  const [confirming, setConfirming] = useState(false);
  // قسما التوثيق: الألعاب (عقد ZDK) والموبايل (شحن الخطوط) — المفتاح واحد لهما
  const [kind, setKind] = useState<"games" | "mobile">("games");

  useEffect(() => {
    api.get("/store/api-token/")
      .then((r) => setRow(r.data))
      .catch((e) => setMsg({ ok: false, text: e?.response?.data?.detail || "تعذّر جلب التوكن" }));
  }, []);

  async function regenerate() {
    setBusy(true); setMsg(null);
    try {
      const r = await api.post("/store/api-token/");
      setRow(r.data);
      setShow(true);
      setMsg({ ok: true, text: r.data.detail });
    } catch (e: any) {
      setMsg({ ok: false, text: e?.response?.data?.detail || "تعذّر التوليد" });
    } finally { setBusy(false); setConfirming(false); }
  }

  const base = window.location.origin;
  const token = row?.token || "";
  const masked = token ? `${token.slice(0, 6)}${"•".repeat(26)}${token.slice(-4)}` : "";

  const copy = (text: string, what: string) => {
    navigator.clipboard?.writeText(text);
    setMsg({ ok: true, text: `نُسخ ${what}` });
  };

  if (!row) {
    return <div style={{ padding: 20, color: "var(--muted)" }}>{msg?.text || "جارٍ التحميل..."}</div>;
  }

  // مغلق افتراضياً بقرار صاحب المتجر — شرحٌ هادئ لا صفحة خطأ، فالأمر ليس عطلاً
  if (!row.allowed) {
    return (
      <div style={box}>
        <div style={h}><Icon name="api" size={18} />الربط الخارجي (API)</div>
        <p style={p}>
          {row.detail || "الربط الخارجي غير مفعّل لحسابك."}
        </p>
        <div style={note}>
          الربط الخارجي يتيح لجهةٍ خارج المنصّة أن ترسل طلباتها إلى حسابك برمجياً
          — تُخصم من محفظتك وتُنفَّذ كأنك طلبتها من لوحتك. وهو مغلق افتراضياً؛
          <b> راسل صاحب المتجر من تبويب «الدعم»</b> ليفتحه لك. وحين يفتحه يظهر لك
          هنا مفتاحُ ربطٍ وروابطُ الخدمة وتوثيقٌ كامل تسلّمه لمبرمجهم.
        </div>
      </div>
    );
  }

  return (
    <div style={{ display: "grid", gap: 18 }}>
      {msg && (
        <div style={{
          ...box, borderColor: msg.ok ? "#b6e0c4" : "#f0c2b6",
          background: msg.ok ? "#e7f6ec" : "#fdece7",
          color: msg.ok ? "var(--ok)" : "var(--danger)", fontWeight: 700,
        }}>{msg.text}</div>
      )}

      {/* ——— بيانات الربط: المفتاح والروابط في مكان واحد ——— */}
      <div style={box}>
        <div style={h}><Icon name="api" size={18} />بيانات الربط</div>
        <p style={p}>
          هذا كل ما يحتاجه مبرمج الجهة التي تربط معك: المفتاح، والروابط. سلّمه
          إيّاها كما هي.
        </p>

        <div style={lbl}>مفتاح الربط (api-token)</div>
        <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
          <code style={tokenBox}>{show ? token : masked}</code>
          <button className="btn" style={sm} onClick={() => setShow((s) => !s)}>
            <Icon name="eye" size={14} style={{ marginInlineEnd: 5 }} />{show ? "إخفاء" : "إظهار"}
          </button>
          <button className="btn g" style={sm} onClick={() => copy(token, "المفتاح")}>
            <Icon name="link" size={14} style={{ marginInlineEnd: 5 }} />نسخ
          </button>
        </div>
        <div style={{ ...note, marginTop: 10 }}>
          <b>مفتاحك ثابت لا يتغيّر ولا ينتهي.</b> يبقى كما هو ما دام حسابك قائماً،
          ولا يتبدّل إلا إن ضغطت زرّ التبديل أسفل هذه الصفحة بنفسك. فاضبطه مرّةً
          عند من يربط معك ولا يحتاج مراجعته بعدها.
          <br />
          ومن يملكه يشتري من محفظتك بلا كلمة سر — فلا تضعه في صفحة موقع ولا تطبيق
          جوّال، مكانه خادم الجهة التي تربط معك.
        </div>

        <div style={{ ...lbl, marginTop: 18 }}>عنوان الخدمة</div>
        <div style={{ display: "grid", gap: 8 }}>
          <LinkRow what="عنوان الخدمة (base URL)" url={base} onCopy={copy} />
          <LinkRow what="الاستعلام عن الرصيد" url={`${base}/client/api/profile`} onCopy={copy} />
        </div>
        <div style={{ ...note, marginTop: 12 }}>
          كل نداء — بلا استثناء — يحمل ترويسة <code style={ic}>api-token</code> بالمفتاح أعلاه؛ المفتاح
          <b> لا يوضع في الرابط</b> لأن الروابط تُسجَّل في سجلّات الخوادم فيتسرّب. والمفتاح نفسه
          يعمل للألعاب وللموبايل معاً.
        </div>

        <div style={{ display: "flex", gap: 22, flexWrap: "wrap", marginTop: 16, fontSize: 13 }}>
          <span style={{ color: "var(--muted)" }}>أُنشئ: <b style={dir}>{row.created_at}</b></span>
          <span style={{ color: "var(--muted)" }}>
            آخر استعمال: <b style={dir}>{row.last_used_at || "لم يُستعمل بعد"}</b>
          </span>
          <span style={{ color: "var(--muted)" }}>عدد النداءات: <b style={dir}>{row.calls}</b></span>
        </div>
      </div>

      {/* ——— الألعاب أم الموبايل ——— */}
      <div style={seg}>
        <button style={kind === "games" ? segOn : segBtn} onClick={() => setKind("games")}>
          <Icon name="games" size={16} /> ربط الألعاب
        </button>
        <button style={kind === "mobile" ? segOn : segBtn} onClick={() => setKind("mobile")}>
          <Icon name="phone" size={16} /> ربط الموبايل (شحن الخطوط)
        </button>
      </div>

      {kind === "mobile" ? <MobileDocs base={base} token={token} onCopy={copy} /> : (<>
      {/* ——— روابط الألعاب ——— */}
      <div style={box}>
        <div style={h}><Icon name="games" size={18} />روابط الألعاب — انسخ ما تحتاجه</div>
        <div style={{ display: "grid", gap: 8 }}>
          <LinkRow what="قائمة المنتجات" url={`${base}/client/api/products`} onCopy={copy} />
          <LinkRow
            what="إرسال طلب"
            url={`${base}/client/api/newOrder/{productId}/params?qty=1&order_uuid={UUID}&playerId={ID}`}
            onCopy={copy}
          />
          <LinkRow
            what="استعلام حالة الطلب"
            url={`${base}/client/api/check?orders={رقم الطلب}`}
            onCopy={copy}
          />
          <LinkRow
            what="استعلام بمعرّفك أنت"
            url={`${base}/client/api/check?orders={UUID}&uuid=1`}
            onCopy={copy}
          />
        </div>
        <div style={{ ...note, marginTop: 12 }}>
          ما بين <code style={ic}>{"{ }"}</code> تملؤه أنت.
        </div>
      </div>

      {/* ——— البداية السريعة ——— */}
      <div style={box}>
        <div style={h}><Icon name="link" size={18} />البداية — انسخ وجرّب</div>
        <p style={p}>
          المصادقة بترويسة <code style={ic}>api-token</code> وحدها. لا اسم مستخدم ولا
          كلمة سر. كل الردود JSON.
        </p>
        <Snippet
          label="جرّبه الآن — يعيد رصيدك"
          code={`curl -H "api-token: ${token}" \\\n  ${base}/client/api/profile`}
          onCopy={copy}
        />
        <div style={note}>
          <b>ملاحظة لمن يربط من متجر يعمل ببرمجية ZDK</b> (بركات · أب‑ستور وغيرهما):
          مساراتنا وأسماء حقولنا وترويستنا هي نفسها حرفاً. بدّل عنوان الخدمة
          والمفتاح في إعداداتك — ولا تُعدّل كودك.
        </div>
      </div>

      {/* ——— العناوين الأربعة ——— */}
      <div style={box}>
        <div style={h}><Icon name="excel" size={18} />العناوين الأربعة</div>

        <Endpoint
          n="١" title="الرصيد" method="GET" url={`${base}/client/api/profile`} onCopy={copy}
          desc="رصيدك الحالي وحدّك الائتماني وما تستطيع إنفاقه فعلاً."
          res={`{ "status": "OK",
  "data": { "balance": "500.00", "credit_limit": "0.00",
            "available": "500.00", "currency": "USD",
            "name": "…", "login_id": "…" } }`}
        />

        <Endpoint
          n="٢" title="قائمة المنتجات" method="GET" url={`${base}/client/api/products`} onCopy={copy}
          desc="المنتجات المتاحة لك بأسعار شرائك أنت. المعاملات الاختيارية: products_id=1,2 لمنتجات بعينها · base=1 لردّ مختصر."
          res={`{ "status": "OK",
  "data": [ { "id": 12, "name": "60 UC", "price": "8.00",
              "available": true, "category_name": "PUBG Mobile",
              "params": ["playerId"], "product_type": "package",
              "qty_values": null, "currency": "USD" } ] }`}
        />

        <Endpoint
          n="٣" title="إرسال طلب" method="GET" onCopy={copy}
          url={`${base}/client/api/newOrder/{productId}/params?qty=1&order_uuid={UUID}`}
          desc="المعاملات: qty=1 (مطلوب) · order_uuid=UUIDv4 (مطلوب) · playerId (إن كان المنتج يطلبه، انظر params في القائمة)."
          res={`{ "status": "accept",
  "data": { "order_id": "26073180840", "order_uuid": "…",
            "status": "accept", "price": "8.00",
            "product_id": 12, "product_name": "60 UC",
            "data": { "playerId": "5121…" },
            "pin": "…", "replay_api": ["…"] } }`}
        />

        <Endpoint
          n="٤" title="استعلام الحالة" method="GET" url={`${base}/client/api/check?orders={ids}`} onCopy={copy}
          desc="orders=رقم أو أرقام مفصولة بفواصل (حتى 50). أضف uuid=1 لتستعلم بمعرّفاتك أنت بدل أرقامنا — وهو ما تحتاجه إن ضاع منك الردّ."
          res={`{ "status": "OK",
  "data": [ { "order_id": "26073180840", "status": "accept",
              "price": "8.00", "pin": "…", "replay_api": ["…"] } ] }`}
        />
      </div>

      {/* ——— منع التكرار: الأهمّ ——— */}
      <div style={{ ...box, borderInlineStartWidth: 4, borderInlineStartColor: "var(--danger)" }}>
        <div style={h}><Icon name="warning" size={18} />اقرأ هذا قبل أن تكتب سطراً — منع الشحن المزدوج</div>
        <p style={p}>
          الشبكة تنقطع أحياناً <b>بعد</b> أن نشحن و<b>قبل</b> أن يصلك ردّنا. فتعيد
          المحاولة، فيُشحن اللاعب مرّتين ويُخصم رصيدك مرّتين.
        </p>
        <p style={p}>
          لذلك <code style={ic}>order_uuid</code> مطلوب في كل طلب: ولّد <b>UUIDv4
          واحداً لكل طلبٍ عندك</b>، واحفظه، وأعِد إرساله <b>نفسه</b> عند إعادة
          المحاولة. نحن نضمن أن نفس المعرّف لا يُنشئ طلبين أبداً — يعيد لك الطلب
          الأوّل بحالته الحالية ومعه <code style={ic}>duplicate: true</code>.
        </p>
        <p style={{ ...p, fontWeight: 700 }}>
          الخطأ الشائع: توليد UUID جديد عند كل محاولة. عندها يفقد المعرّف معناه
          ويشتري زبونك مرّتين.
        </p>
        <Snippet
          label="مثال كامل — طلب بمعرّف ثابت"
          code={`UUID=$(uuidgen)   # ولّده مرّة واحدة واحفظه\n\ncurl -H "api-token: ${token}" \\\n  "${base}/client/api/newOrder/12/params?qty=1&order_uuid=$UUID&playerId=5121234567"\n\n# انقطع الاتصال؟ أعد نفس الأمر بنفس \\$UUID — لن يُشحن مرّتين.`}
          onCopy={copy}
        />
      </div>

      {/* ——— الحالات ——— */}
      <div style={box}>
        <div style={h}><Icon name="check" size={18} />الحالات الثلاث</div>
        <table style={tbl}>
          <thead><tr><th style={th}>status</th><th style={th}>المعنى</th><th style={th}>ماذا تفعل</th></tr></thead>
          <tbody>
            <tr>
              <td style={td}><code style={ic}>accept</code></td>
              <td style={td}>نُفّذ الطلب</td>
              <td style={td}>خُذ <code style={ic}>pin</code> إن وُجد. بعض الباقات تُشحن على معرّف اللاعب مباشرةً فلا كود لها — وهذا نجاح صحيح.</td>
            </tr>
            <tr>
              <td style={td}><code style={ic}>wait</code></td>
              <td style={td}>قيد التنفيذ</td>
              <td style={td}>استعلم بـ <code style={ic}>check</code> كل بضع ثوانٍ. <b>لا تُعِد إرسال الطلب</b> — لم يُرفض.</td>
            </tr>
            <tr>
              <td style={td}><code style={ic}>reject</code></td>
              <td style={td}>رُفض</td>
              <td style={td}>المبلغ رُدَّ إلى محفظتك تلقائياً. راجع <code style={ic}>replay_api</code> للسبب.</td>
            </tr>
          </tbody>
        </table>
        <div style={note}>
          الطلب الذي يفشل لدى كل مزوّدينا يبقى <code style={ic}>wait</code> لا
          <code style={ic}> reject</code>، لأنه ينتظر تدخّلاً يدوياً من المتجر وقد
          يُنفَّذ بعد قليل. لا تُعِد إرساله.
        </div>
      </div>

      {/* ——— الأخطاء ——— */}
      <div style={box}>
        <div style={h}><Icon name="warning" size={18} />الأخطاء</div>
        <p style={p}>
          كل خطأ بنفس الشكل: <code style={ic}>{`{"status":"error","code":120,"message":"…"}`}</code>
        </p>
        <table style={tbl}>
          <thead><tr><th style={th}>code</th><th style={th}>المعنى</th></tr></thead>
          <tbody>
            {[
              ["120", "الترويسة api-token غائبة"],
              ["121", "التوكن غير صحيح أو أُبطل بتوليد جديد"],
              ["122", "الحساب موقوف — راجع المتجر"],
              ["100", "الرصيد لا يكفي (بعد احتساب حدّك الائتماني)"],
              ["105", "المنتج غير موجود"],
              ["106", "المنتج غير متاح للبيع الآن"],
              ["107", "order_uuid ناقص أو ليس UUID صالحاً"],
              ["108", "هذا المنتج يطلب playerId ولم تُرسله"],
              ["109", "الكمّيات غير مدعومة — أرسل qty=1"],
              ["110", "رُفض الطلب — الرسالة تشرح السبب"],
            ].map(([c, m]) => (
              <tr key={c}><td style={td}><code style={ic}>{c}</code></td><td style={td}>{m}</td></tr>
            ))}
          </tbody>
        </table>
        <div style={note}>
          حدّ النداءات ٢٤٠ في الدقيقة. تجاوزُه يردّ <code style={ic}>429</code> —
          انتظر ثوانيَ ثم أعد المحاولة.
        </div>
      </div>

      </>)}

      <div style={{ ...box, background: "var(--surface-2)" }}>
        <div style={h}><Icon name="wallet" size={18} />ملاحظتان على المال</div>
        <p style={p}>
          كل الأرقام بعملة العرض المضبوطة لحسابك — تجدها في حقل
          <code style={ic}> currency</code> في كل ردّ. لا تفترضها، اقرأها.
        </p>
        <p style={{ ...p, marginBottom: 0 }}>
          الخصم يقع <b>لحظة إنشاء الطلب</b> لا لحظة نجاحه. والرفض يُعيد المبلغ
          تلقائياً. فالطلب <code style={ic}>wait</code> مالُه محجوز فعلاً.
        </p>
      </div>

      {/* ——— تبديل المفتاح: آخر الصفحة عمداً ——— */}
      <div style={box}>
        <div style={h}><Icon name="refresh" size={18} />تبديل المفتاح — عند التسريب وحده</div>
        <p style={p}>
          مفتاحك ثابت ولا حاجة إلى تبديله أبداً في المجرى العادي. لا تضغط هنا إلا
          إن تسرّب المفتاح أو شككت أن أحداً اطّلع عليه.
        </p>
        {confirming ? (
          <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
            <b style={{ color: "var(--danger)", fontSize: 13 }}>
              المفتاح الحالي يتعطّل فوراً، ويتوقّف كل ربط قائم حتى تعطيهم الجديد. متأكّد؟
            </b>
            <button className="btn" style={{ ...sm, background: "var(--danger)", color: "#fff" }}
              disabled={busy} onClick={regenerate}>نعم، بدّل المفتاح</button>
            <button className="btn" style={sm} onClick={() => setConfirming(false)}>تراجع</button>
          </div>
        ) : (
          <button className="btn" style={sm} onClick={() => setConfirming(true)}>
            <Icon name="refresh" size={14} style={{ marginInlineEnd: 5 }} />تبديل المفتاح
          </button>
        )}
      </div>
    </div>
  );
}

/* ————————————————— توثيق الموبايل (شحن الخطوط) ————————————————— */

/**
 * ربط شحن الخطوط التركية. نفس عقد الألعاب (الترويسة · الأخطاء · order_uuid · الحالات)
 * فمن ربط الألعاب يكمل هنا بدقائق — والفرق أن «المعامل» رقم الخط gsm لا معرّف لاعب.
 */
function MobileDocs({ base, token, onCopy }: {
  base: string; token: string; onCopy: (v: string, w: string) => void;
}) {
  const m = `${base}/client/api/mobile`;
  return (
    <>
      <div style={box}>
        <div style={h}><Icon name="phone" size={18} />روابط الموبايل — انسخ ما تحتاجه</div>
        <p style={p}>
          شحن رصيد وباقات الخطوط التركية: <b>Turkcell · Vodafone · Türk Telekom</b> والدولي.
          نفس المفتاح ونفس شكل الردود والأخطاء الذي في ربط الألعاب — فإن كنت ربطت الألعاب فأنت
          تعرف هذا كلّه تقريباً.
        </p>
        <div style={{ display: "grid", gap: 8 }}>
          <LinkRow what="قائمة الباقات" url={`${m}/packages`} onCopy={onCopy} />
          <LinkRow what="كشف شركة الرقم" url={`${m}/detect?gsm={رقم الخط}`} onCopy={onCopy} />
          <LinkRow what="عروض هذا الرقم" url={`${m}/offers?gsm={رقم الخط}&operator={الشركة}`} onCopy={onCopy} />
          <LinkRow what="إرسال شحنة" url={`${m}/newOrder/{packageId}/params?gsm={رقم الخط}&order_uuid={UUID}`} onCopy={onCopy} />
          <LinkRow what="استعلام حالة الشحنة" url={`${m}/check?orders={رقم الطلب}`} onCopy={onCopy} />
          <LinkRow what="استعلام بمعرّفك أنت" url={`${m}/check?orders={UUID}&uuid=1`} onCopy={onCopy} />
        </div>
        <div style={{ ...note, marginTop: 12 }}>
          <b>رقم الخط (gsm)</b>: عشر خانات تبدأ بـ5 مثل <code style={ic}>5442199992</code>. نقبل أيضاً
          <code style={ic}>05442199992</code> و<code style={ic}>905442199992</code> ونصحّحها بأنفسنا.
          <br />
          <b>packageId</b> هو <b>رقم الربط</b> — الحقل <code style={ic}>id</code> في قائمة الباقات، وهو نفسه
          عمود «رقم الربط» في «موبايل ⟵ قائمة الأسعار» في لوحتك.
        </div>
      </div>

      {/* ——— المسار المعتاد ——— */}
      <div style={box}>
        <div style={h}><Icon name="link" size={18} />المسار المعتاد — ثلاث خطوات</div>
        <ol style={{ ...p, paddingInlineStart: 20, margin: 0 }}>
          <li><b>مرّةً واحدة</b> (أو كل بضع ساعات): اجلب <code style={ic}>packages</code> واحفظ أرقام الربط والأسعار عندك.</li>
          <li>الزبون يكتب رقمه ويختار الشركة والباقة. إن لم تعرف الشركة استعمل <code style={ic}>detect</code>.</li>
          <li>أرسل <code style={ic}>newOrder</code> بالرقم ومعرّف <code style={ic}>order_uuid</code> ثابت، ثم تابع بـ <code style={ic}>check</code> حتى <code style={ic}>accept</code> أو <code style={ic}>reject</code>.</li>
        </ol>
        <Snippet
          label="مثال كامل — شحن باقة لرقم"
          code={`UUID=$(uuidgen)   # ولّده مرّة واحدة لكل شحنة واحفظه\n\ncurl -H "api-token: ${token}" \\\n  "${m}/newOrder/123/params?gsm=5442199992&order_uuid=$UUID"\n\n# ثم كل 5–10 ثوانٍ حتى تنتهي:\ncurl -H "api-token: ${token}" \\\n  "${m}/check?orders=$UUID&uuid=1"`}
          onCopy={onCopy}
        />
        <div style={note}>
          ⚠️ <b>الباقة يجب أن تكون من شركة الرقم نفسه.</b> باقة Turkcell لرقم Vodafone يرفضها
          المشغّل فتصلك <code style={ic}>reject</code> ويعود المبلغ — لكنها رحلة ضائعة. إن لم تكن
          متأكّداً من الشركة (الأرقام تنتقل بين الشركات) فاسأل <code style={ic}>detect</code> أوّلاً.
        </div>
      </div>

      {/* ——— العناوين ——— */}
      <div style={box}>
        <div style={h}><Icon name="excel" size={18} />العناوين الخمسة</div>

        <Endpoint
          n="١" title="قائمة الباقات" method="GET" url={`${m}/packages`} onCopy={onCopy}
          desc="الباقات المتاحة لك بأسعار شرائك أنت (price) والسعر المقترح لبيعها لزبونك (recommended_price). مرتّبة: الشركة، ثم العروض أوّلاً، ثم الأرخص. اختياري: operator=Turkcell · packages_id=1,2 · base=1 لردّ مختصر."
          res={`{ "status": "OK",
  "data": [ { "id": 123, "name": "Fırsat 30GB İndirimli",
              "operator": "Turkcell", "operator_label": "Turkcell",
              "category_name": "Ses*", "line_type": "Ses", "is_offer": true,
              "details": "30 Gün, 1000 Dk, 30 GB",
              "days": 30, "gb": 30, "minutes": 1000,
              "price": "20.69", "recommended_price": "22.00",
              "available": true, "params": ["gsm"], "currency": "USD" } ] }`}
        />

        <Endpoint
          n="٢" title="كشف شركة الرقم" method="GET" url={`${m}/detect?gsm=5442199992`} onCopy={onCopy}
          desc="يسأل المشغّل مباشرةً عن شركة الرقم الآن (يستغرق بضع ثوانٍ). الشركات: Turkcell · Vodafone · Avea (= Türk Telekom) · Callback (دولي)."
          res={`{ "status": "OK",
  "data": { "gsm": "5442199992", "operator": "Turkcell",
            "operator_label": "Turkcell" } }`}
        />

        <Endpoint
          n="٣" title="عروض هذا الرقم" method="GET" url={`${m}/offers?gsm=5442199992&operator=Turkcell`} onCopy={onCopy}
          desc="الباقات المتاحة لهذا الرقم تحديداً الآن — ومنها عروض خاصة بالرقم (is_offer: true) أرخص من العامّة. يحتاج إذن الاستعلام من صاحب المتجر؛ بدونه تصلك 113."
          res={`{ "status": "OK",
  "data": [ { "id": 123, "name": "Fırsat 30GB İndirimli",
              "is_offer": true, "details": "…",
              "days": 30, "gb": 30, "minutes": 1000,
              "price": "20.69", "recommended_price": "22.00",
              "currency": "USD" } ] }`}
        />

        <Endpoint
          n="٤" title="إرسال شحنة" method="GET" onCopy={onCopy}
          url={`${m}/newOrder/{packageId}/params?gsm={رقم الخط}&order_uuid={UUID}`}
          desc="المعاملات: gsm (مطلوب) · order_uuid=UUIDv4 (مطلوب) · dealer_sell_price (اختياري — سعر بيعك لزبونك لتقاريرك؛ فارغ = المقترح). يُخصم السعر من محفظتك لحظة الإنشاء."
          res={`{ "status": "wait",
  "data": { "order_id": "4821", "order_uuid": "…",
            "status": "wait", "package_id": 123,
            "package_name": "Fırsat 30GB İndirimli",
            "operator": "Turkcell", "gsm": "5442199992",
            "price": "20.69", "dealer_sell_price": "22.00",
            "currency": "USD", "replay_api": ["…"] } }`}
        />

        <Endpoint
          n="٥" title="استعلام الحالة" method="GET" url={`${m}/check?orders={ids}`} onCopy={onCopy}
          desc="orders=رقم أو أرقام مفصولة بفواصل (حتى 50). أضف uuid=1 لتستعلم بمعرّفاتك أنت — وهو ما تحتاجه إن انقطع الردّ فلم يصلك رقم الطلب."
          res={`{ "status": "OK",
  "data": [ { "order_id": "4821", "status": "accept",
              "gsm": "5442199992", "price": "20.69",
              "replay_api": ["…"] } ] }`}
        />
      </div>

      {/* ——— الحالات ——— */}
      <div style={box}>
        <div style={h}><Icon name="check" size={18} />الحالات الثلاث</div>
        <table style={tbl}>
          <thead><tr><th style={th}>status</th><th style={th}>المعنى</th><th style={th}>ماذا تفعل</th></tr></thead>
          <tbody>
            <tr>
              <td style={td}><code style={ic}>wait</code></td>
              <td style={td}>أُرسلت إلى المشغّل وتُنفَّذ</td>
              <td style={td}>الحالة الطبيعية بعد الإرسال مباشرةً. استعلم بـ <code style={ic}>check</code> كل 5–10 ثوانٍ. <b>لا تُعِد الإرسال.</b></td>
            </tr>
            <tr>
              <td style={td}><code style={ic}>accept</code></td>
              <td style={td}>وصل الرصيد إلى الخط</td>
              <td style={td}>انتهت الشحنة بنجاح. لا كود هنا — الشحن مباشرةً على الرقم.</td>
            </tr>
            <tr>
              <td style={td}><code style={ic}>reject</code></td>
              <td style={td}>رفضها المشغّل</td>
              <td style={td}>المبلغ رُدَّ إلى محفظتك تلقائياً. السبب في <code style={ic}>replay_api</code> (رقم خاطئ، باقة لا تناسب الخط…).</td>
            </tr>
          </tbody>
        </table>
      </div>

      {/* ——— منع التكرار ——— */}
      <div style={{ ...box, borderInlineStartWidth: 4, borderInlineStartColor: "var(--danger)" }}>
        <div style={h}><Icon name="warning" size={18} />منع الشحن المزدوج — نفس قاعدة الألعاب</div>
        <p style={p}>
          ولّد <b>UUIDv4 واحداً لكل شحنة</b> واحفظه، وأعِد إرساله <b>نفسه</b> إن انقطع الاتصال. نفس
          المعرّف لا يُنشئ شحنتين أبداً: يعيد لك الأولى بحالتها ومعها <code style={ic}>duplicate: true</code>.
          شحنة الخط لا تُسترجع بعد وصولها — فهذه القاعدة هنا أهمّ منها في أيّ مكان.
        </p>
      </div>

      {/* ——— أخطاء الموبايل ——— */}
      <div style={box}>
        <div style={h}><Icon name="warning" size={18} />الأخطاء</div>
        <p style={p}>
          نفس الشكل: <code style={ic}>{`{"status":"error","code":111,"message":"…"}`}</code> — وأخطاء المفتاح
          والرصيد نفسها (120 · 121 · 122 · 100 · 107 · 110).
        </p>
        <table style={tbl}>
          <thead><tr><th style={th}>code</th><th style={th}>المعنى</th></tr></thead>
          <tbody>
            {[
              ["100", "الرصيد لا يكفي (بعد احتساب حدّك الائتماني)"],
              ["105", "رقم الربط (packageId) غير موجود"],
              ["106", "الباقة غير متاحة للبيع الآن"],
              ["107", "order_uuid ناقص أو ليس UUID صالحاً"],
              ["110", "رُفضت الشحنة قبل الإرسال — الرسالة تشرح السبب (مثل باقة غير مسعّرة)"],
              ["111", "رقم الخط غير صحيح — 10 خانات تبدأ بـ5"],
              ["112", "الشركة غير صحيحة — Turkcell · Vodafone · Avea · Callback"],
              ["113", "استعلام العروض غير مسموح لحسابك على هذه الشركة — راسل صاحب المتجر"],
              ["114", "الاستعلام الحيّ من المشغّل متعذّر مؤقتاً — أعد المحاولة بعد قليل (HTTP 502)"],
              ["115", "تعذّر كشف شركة هذا الرقم"],
            ].map(([c, t]) => (
              <tr key={c}><td style={td}><code style={ic}>{c}</code></td><td style={td}>{t}</td></tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

/* ————————————————— أجزاء العرض ————————————————— */

/** سطر رابط: ما هو، ثم الرابط كاملاً بزرّ نسخ. */
function LinkRow({ what, url, onCopy }: {
  what: string; url: string; onCopy: (v: string, w: string) => void;
}) {
  return (
    <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
      <span style={{ fontSize: 12.5, fontWeight: 700, minWidth: 150 }}>{what}</span>
      <code style={tokenBox}>{url}</code>
      <button className="btn" style={sm} onClick={() => onCopy(url, "الرابط")}>نسخ</button>
    </div>
  );
}

function Snippet({ label, code, onCopy }: {
  label: string; code: string; onCopy: (v: string, w: string) => void;
}) {
  return (
    <div style={{ margin: "12px 0" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div style={lbl}>{label}</div>
        <button className="btn" style={{ ...sm, height: 26 }} onClick={() => onCopy(code, "الأمر")}>نسخ</button>
      </div>
      <pre style={pre}>{code}</pre>
    </div>
  );
}

function Endpoint({ n, title, method, url, desc, res, onCopy }: {
  n: string; title: string; method: string; url: string; desc: string; res: string;
  onCopy: (v: string, w: string) => void;
}) {
  return (
    <div style={{ borderTop: "1px solid var(--border)", paddingTop: 14, marginTop: 14 }}>
      <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
        <b style={{ fontSize: 14 }}>{n}. {title}</b>
        <span style={badge}>{method}</span>
      </div>
      <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap", margin: "8px 0" }}>
        <code style={tokenBox}>{url}</code>
        <button className="btn" style={sm} onClick={() => onCopy(url, "الرابط")}>نسخ</button>
      </div>
      <p style={{ ...p, margin: "8px 0" }}>{desc}</p>
      <pre style={pre}>{res}</pre>
    </div>
  );
}

/* ————————————————— الأنماط ————————————————— */

const box: React.CSSProperties = {
  background: "var(--surface)", border: "1px solid var(--border)",
  borderRadius: 10, padding: 18,
};
const h: React.CSSProperties = {
  fontWeight: 800, fontSize: 15, color: "var(--primary-dark)",
  display: "flex", alignItems: "center", gap: 8, marginBottom: 12,
};
const p: React.CSSProperties = {
  fontSize: 13.5, lineHeight: 1.9, color: "var(--text)", margin: "0 0 10px",
};
const lbl: React.CSSProperties = {
  fontSize: 12, fontWeight: 700, color: "var(--muted)", marginBottom: 5,
};
const dir: React.CSSProperties = { direction: "ltr", display: "inline-block", fontFamily: "monospace" };
const tokenBox: React.CSSProperties = {
  direction: "ltr", fontFamily: "monospace", fontSize: 13,
  background: "var(--surface-2)", border: "1px solid var(--border)",
  borderRadius: 7, padding: "9px 11px", overflowX: "auto", whiteSpace: "nowrap",
  flex: "1 1 340px", minWidth: 0,
};
const pre: React.CSSProperties = {
  direction: "ltr", textAlign: "left", fontFamily: "monospace", fontSize: 12.5,
  background: "#1f2a30", color: "#dfe9ee", borderRadius: 8, padding: "12px 14px",
  overflowX: "auto", margin: "6px 0 0", lineHeight: 1.7,
};
const ic: React.CSSProperties = {
  direction: "ltr", display: "inline-block", fontFamily: "monospace",
  background: "var(--surface-2)", borderRadius: 5, padding: "1px 6px", fontSize: 12.5,
};
const sm: React.CSSProperties = { height: 32, padding: "0 12px", fontSize: 13 };
const badge: React.CSSProperties = {
  background: "var(--primary)", color: "#fff", borderRadius: 5,
  padding: "2px 8px", fontSize: 11, fontWeight: 800, direction: "ltr",
};
const note: React.CSSProperties = {
  background: "var(--surface-2)", borderRadius: 8, padding: "10px 12px",
  fontSize: 12.5, lineHeight: 1.9, color: "var(--muted)", marginTop: 12,
};
const tbl: React.CSSProperties = { width: "100%", borderCollapse: "collapse", fontSize: 13 };
const th: React.CSSProperties = {
  textAlign: "start", padding: "8px 10px", borderBottom: "2px solid var(--border)",
  color: "var(--muted)", fontSize: 12,
};
const td: React.CSSProperties = {
  padding: "9px 10px", borderBottom: "1px solid var(--border)", lineHeight: 1.8,
};
const seg: React.CSSProperties = {
  display: "grid", gridTemplateColumns: "1fr 1fr", gap: 4, padding: 4,
  background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 12,
};
const segBtn: React.CSSProperties = {
  height: 42, border: 0, borderRadius: 9, background: "transparent", color: "var(--muted)",
  font: "inherit", fontWeight: 800, fontSize: 13.5, cursor: "pointer",
  display: "inline-flex", alignItems: "center", justifyContent: "center", gap: 7,
};
const segOn: React.CSSProperties = { ...segBtn, background: "var(--primary)", color: "var(--on-primary, #fff)" };
