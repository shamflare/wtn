# deploy — نشر wtn على خادم واحد

> خادم Hetzner **CX23** · Falkenstein · Ubuntu 24.04 · `46.224.47.213`
> النطاق **wtn4.com** عبر Cloudflare (`DNS only` أثناء الإعداد).
>
> **القاعدة على الخادم** (2026-08-23). كانت على Neon فبلغت خطتُه المجانية حدَّ
> نقل البيانات ورفض كلَّ اتصال، فتوقّف الموقع يومين — والسبب بنيويّ: قاعدةٌ في
> أوهايو وخادمٌ في ألمانيا، ونبضٌ كل دقيقة وكل ثلاث ثوانٍ يعبر المحيط.
>
> وحجّةُ إبعادها (ألّا تجتمع هي ونسخُها على قرصٍ واحد) يغلقها **رفعُ النسخة
> خارج الخادم**، لا إبعادُ القاعدة ([info.md §1.5](../info.md)).

---

## ما يعمل على الخادم

| | |
|---|---|
| `db` | PostgreSQL 18 — بلا منفذٍ إلى الإنترنت، يبلغها `web` بالاسم `db` وحده |
| `web` | الموقع كلّه — Django يقدّم الـ API والواجهة من أصل واحد |
| `caddy` | الموجّه: يصنع شهادة HTTPS **ويجدّدها وحده** |
| `bot` | بوت واتساب — كان على جهاز المالك فينام معه |
| `cron` | متابعة الطلبات كل دقيقة · نسخة احتياطية كل ليلة |

---

## نسخة عميل جديدة (دومينه وخادمه)

كل عميل نسخةٌ مستقلّة — الخطّة كاملة في `plan2.md` (في مجلّد ahlacard على جهاز المالك). على خادمٍ جديد يشير إليه الدومين:

```bash
curl -fsSL https://raw.githubusercontent.com/shamflare/wtn/main/deploy/new-server.sh | bash -s -- ahlacard.com
docker compose -f /opt/wtn/deploy/docker-compose.yml exec web   python manage.py provision_instance --store "اسم المتجر" --admin-login 5551234567
```

الأوّل يولّد الأسرار ويضبط المهامّ ويشغّل الموقع (`SEED_DEMO=0`: بلا حسابات تجريبية)،
والثاني يصنع الحسابات بكلمات سرٍّ عشوائية تُطبع مرّةً واحدة.

---

## أوّل مرّة (wtn4.com)

```bash
git clone https://github.com/Lebid15/wtn /opt/wtn
cd /opt/wtn

cp deploy/.env.example deploy/.env
nano deploy/.env          # املأ الأسرار الخمسة
cp deploy/.env.bot.example deploy/.env.bot
nano deploy/.env.bot

docker compose -f deploy/docker-compose.yml up -d --build
```

الشهادة تُصدَر وحدها خلال ثوانٍ من أول طلب. لا خطوة يدوية.

---

## الأسرار

| المفتاح | من أين | إن ضاع |
|---|---|---|
| `SECRET_KEY` | `openssl rand -base64 48` | تُبطَل الجلسات فقط — يُولَّد جديد |
| `POSTGRES_PASSWORD` | `openssl rand -hex 24` (بلا `@` و`:` — تُربك قراءة الرابط) | لا تقلع القاعدة أصلاً |
| `DATABASE_URL` | يُبنى من الكلمة أعلاه: `postgresql://wtn:…@db:5432/wtn?sslmode=disable` | **لا يعمل شيء** |
| `BACKUP_REMOTE` | وجهةُ rsync خارج الخادم — اختياري، وغيابُه يصرخ في السجلّ | النسخة تبقى على قرص القاعدة نفسه |
| `INTERNAL_API_KEY` | `openssl rand -hex 32` | يتوقّف البوت (والواجهة الداخلية تُغلق 503) |
| `BOT_ENCRYPTION_KEY` | `cd bot && npm run keygen` | **تُفقد كل جلسات واتساب** — احتفظ بنسخة خارج الخادم |
| `CF_API_TOKEN` | Cloudflare ← My Profile ← API Tokens ← قالب «Edit zone DNS» | تتوقّف عناوين المتاجر الفرعية وحدها — والموقع الرئيسي يعمل. يُنشأ غيرُه ولا يضيع شيء |

`deploy/.env` و`deploy/.env.bot` **خارج المستودع** (`.gitignore`). صلاحيتهما `600`.

---

## المهامّ المجدولة

```cron
* * * * *  cd /opt/wtn && docker compose -f deploy/docker-compose.yml exec -T web python manage.py sync_orders --quiet
17 3 * * * /opt/wtn/deploy/backup.sh >> /var/log/wtn-backup.log 2>&1
```

> ⚠️ **ولا أحد يقرأ ذلك السجلّ.** فشلت نسختا 22 و23 آب 2026 فيه يومين بلا أن
> ينتبه أحد، والقاعدة مقطوعة والموقع متوقّف. فشلُ نسخةٍ يجب أن **يوقظ** —
> برسالة واتساب أو بريد — لا أن يُكتب في ملفٍّ لا يُفتح.

**الأولى تغلق أقدم دَين في المشروع:** كانت متابعة الطلبات يحرّكها متصفّح
الأدمن المفتوح وحده، فمتى أُغلقت اللوحة تجمّد كل طلبٍ أكّد المزوّد استلامه.
والأمر يحمل قفل ملفّ فلا تتراكب نبضتان.

---

## التحديث

```bash
cd /opt/wtn && git pull && docker compose -f deploy/docker-compose.yml up -d --build
```

الترحيلات تعمل وحدها عند الإقلاع (`backend/start.sh`).

> **بعد كل تحديث تأكّد أن الأثر ظهر على الموقع** لا أن الدفع نجح. بقي فرع
> Render قديماً أياماً فتراكمت خمسة التزامات والموقع يعمل بكودٍ قديم ونحن
> نظنّه محدَّثاً ([info.md §0](../info.md)).

---

## عناوين المتاجر (`islam.wtn4.com`)

**لا تُفتح Cloudflare عند كل متجر جديد.** السجلّ `*.wtn4.com` والشهادة
الشاملة يغطّيان كل اسمٍ لم يُخلق بعد — فإنشاء متجرٍ صار صفّاً في القاعدة،
وعنوانه يعمل في نفس اللحظة.

| | |
|---|---|
| الشهادة | واحدة شاملة، تحقّقُها عبر DNS بـ `CF_API_TOKEN`، يجدّدها Caddy وحده |
| الموجّه | يُبنى من [caddy.Dockerfile](caddy.Dockerfile) — الصورة الرسمية بلا وحدة Cloudflare |
| كتلة المتاجر | في [stores.caddy](stores.caddy) منفصلاً — تُلحق عند الإقلاع **إن وُجد المفتاح** وحده |
| الوسيط | [backend/core/middleware.py](../backend/core/middleware.py) — يستنتج المتجر من `Host` |
| السحابة | تبقى **رمادية** (`DNS only`). البرتقالية تحتاج تحقّقاً من خطة Cloudflare للشهادة الشاملة |

**ثلاثة عناوين ليست متاجر**: `wtn4.com` و`www` و`api` — تبقى الباب العام
ولوحة المنصّة. وعنوانٌ لا متجر له يعطي صفحة «لا متجر بهذا العنوان» لا صفحة
الدخول، ومتجرٌ موقوفٌ يعطي صفحة توقّف.

**فحصُ أن الشهادة صدرت** بعد أول نشر:

```bash
# الموجّه يقول أيَّ الحالين هو فيه عند كل إقلاع:
docker compose -f deploy/docker-compose.yml logs caddy | grep "wtn:"
docker compose -f deploy/docker-compose.yml logs caddy | grep -i "certificate obtained"
curl -sI https://<أي-متجر>.wtn4.com | head -1
```

> **وبلا المفتاح لا يسقط شيء:** الموقع الرئيسي يعمل، وعناوين المتاجر وحدها
> معطّلة. وقد كانت الكتلة داخل `Caddyfile` أوّلاً فأسقطت الموقع كلَّه —
> Caddy يفحص المفتاح عند تحميل الإعداد لا عند إصدار الشهادة.

## شحن الخطوط (kontör) — متغيّرات اختيارية في deploy/.env

خدمة `kontor-session` (متصفّح خفيّ) تكشف الشركة وتجلب العروض الخاصة من لوحة ZNET.
بلا هذه المتغيّرات تبقى الخدمة خاملة والكشف/العروض معطّلين بلطف (باقي الموقع يعمل):

```
KONTOR_BASE_URL=http://bayi.alayatl.com
KONTOR_USER=<رقم جوال الدخول>
KONTOR_PASS=<كلمة سر اللوحة>
KONTOR_SECURITY_IMAGE=D        # حرف صورة المالك الأمنية (A..L)
```

الاستيراد والتنفيذ الرسميان (الباقات/الشحن) يقرآن بيانات مزوّد ZNET من لوحة
«مزوّدو API» (code=znet: base_url/kod/sifre) — لا من هذه المتغيّرات.
