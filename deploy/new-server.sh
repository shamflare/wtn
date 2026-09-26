#!/usr/bin/env bash
# تجهيز خادمٍ جديد لنسخة عميل — خادمٌ مستقلّ ودومينٌ مستقلّ وقاعدةٌ مستقلّة (plan2.md).
#
# على خادم Hetzner جديد (Ubuntu 24.04)، بعد أن يشير الدومين إلى عنوانه:
#
#   curl -fsSL https://raw.githubusercontent.com/shamflare/wtn/main/deploy/new-server.sh \
#     | bash -s -- ahlacard.com
#
# أو بوجهة النسخ الاحتياطي خارج الخادم (Hetzner Storage Box) من البداية:
#
#   ... | bash -s -- ahlacard.com u123456-sub1@u123456.your-storagebox.de:backups/
#
# يثبّت Docker، ويجلب الكود، ويولّد **كل الأسرار عشوائياً** (لا يُكتب سرٌّ باليد
# ولا يتكرّر بين عميلين)، ويضبط المهامّ المجدولة، ويشغّل الموقع.
# ولا يصنع الحسابات: تلك خطوةٌ واحدة بعده بـ `provision_instance` (يطبعها في آخره).
#
# وإعادة تشغيله آمنة: لا يمسّ ملفّ أسرارٍ موجوداً — مفتاحٌ جديد لقاعدةٍ قائمة يقطعها.

set -euo pipefail

DOMAIN="${1:?اكتب الدومين: bash new-server.sh ahlacard.com}"
BACKUP_REMOTE="${2:-}"
REPO="https://github.com/shamflare/wtn.git"
DIR="/opt/wtn"

DOMAIN="$(echo "$DOMAIN" | tr 'A-Z' 'a-z' | sed 's#^https\?://##; s#/.*##; s#^www\.##')"
IP="$(curl -fsS4 https://ifconfig.me || hostname -I | awk '{print $1}')"

echo "▸ الدومين: $DOMAIN · الخادم: $IP"

# ── 1. الأدوات ──────────────────────────────────────────────────────────
if ! command -v docker >/dev/null; then
	echo "▸ تثبيت Docker"
	curl -fsSL https://get.docker.com | sh
fi
apt-get install -y -qq git rsync openssl >/dev/null

# ── 2. الكود ────────────────────────────────────────────────────────────
if [ ! -d "$DIR/.git" ]; then
	git clone -q "$REPO" "$DIR"
else
	git -C "$DIR" pull -q
fi
cd "$DIR"

# ── 3. الأسرار — تُولَّد مرّةً ولا تُستبدل ─────────────────────────────
rnd_hex() { openssl rand -hex "$1"; }
INTERNAL_KEY="$(rnd_hex 32)"

if [ ! -f deploy/.env ]; then
	DB_PASS="$(rnd_hex 24)"
	cat > deploy/.env <<EOF
# نسخة عميل: $DOMAIN — وُلّد $(date +%F) بـ deploy/new-server.sh. لا يدخل المستودع.
SECRET_KEY=$(openssl rand -base64 48 | tr -d '\n')

POSTGRES_PASSWORD=$DB_PASS
POSTGRES_USER=wtn
POSTGRES_DB=wtn
DATABASE_URL=postgresql://wtn:$DB_PASS@db:5432/wtn?sslmode=disable

# هويّة هذه النسخة
PLATFORM_DOMAIN=$DOMAIN
SITE_ADDRESSES=$DOMAIN, www.$DOMAIN
ALLOWED_HOSTS=$DOMAIN,www.$DOMAIN,$IP,web,localhost,127.0.0.1
CSRF_TRUSTED_ORIGINS=https://$DOMAIN,https://www.$DOMAIN

# نسخة عميل: لا حسابات تجريبية بكلمات سرٍّ معروفة
SEED_DEMO=0
DEBUG=0

INTERNAL_API_KEY=$INTERNAL_KEY

# عناوين فرعية للمتاجر — لا تلزم نسخةً بمتجرٍ واحد
CF_API_TOKEN=

# النسخة الاحتياطية خارج الخادم (Hetzner Storage Box)
BACKUP_REMOTE=$BACKUP_REMOTE
EOF
	echo "▸ وُلّد deploy/.env"
else
	INTERNAL_KEY="$(grep -o '^INTERNAL_API_KEY=.*' deploy/.env | cut -d= -f2-)"
	echo "▸ deploy/.env موجود — تُرك كما هو"
fi

if [ ! -f deploy/.env.bot ]; then
	cat > deploy/.env.bot <<EOF
SITE_URL=http://web:8000
INTERNAL_API_KEY=$INTERNAL_KEY
# إن ضاع فُقدت جلسات واتساب — احفظ نسخةً منه خارج الخادم
BOT_ENCRYPTION_KEY=$(openssl rand -base64 32 | tr -d '\n')
EOF
	echo "▸ وُلّد deploy/.env.bot"
fi
chmod 600 deploy/.env deploy/.env.bot
chmod +x deploy/backup.sh

# ── 4. المهامّ المجدولة ─────────────────────────────────────────────────
cat > /etc/cron.d/wtn <<'EOF'
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
# متابعة الطلبات قيد التنفيذ كل دقيقة
* * * * * root cd /opt/wtn && docker compose -f deploy/docker-compose.yml exec -T web python manage.py sync_orders --quiet >> /var/log/wtn-sync.log 2>&1
# نسخة احتياطية كل ليلة 03:17
17 3 * * * root bash /opt/wtn/deploy/backup.sh >> /var/log/wtn-backup.log 2>&1
EOF

# مفتاح الخادم للنسخ الخارجي — يُضاف مرّةً إلى Storage Box (plan2.md)
[ -f /root/.ssh/id_ed25519 ] || ssh-keygen -q -t ed25519 -N "" -f /root/.ssh/id_ed25519 -C "wtn-backup@$DOMAIN"

# ── 5. التشغيل ──────────────────────────────────────────────────────────
docker compose -f deploy/docker-compose.yml up -d --build

cat <<EOF

✓ الموقع يعمل: https://$DOMAIN  (الشهادة تُصدَر وحدها عند أول زيارة)

الخطوة التالية — الحسابات، مرّةً واحدة (غيّر الاسم ورقم صاحب المتجر):

  cd /opt/wtn && docker compose -f deploy/docker-compose.yml exec web \\
    python manage.py provision_instance --store "اسم المتجر" --admin-login 5551234567 --currency USD

مفتاح النسخ الاحتياطي لهذا الخادم (يُضاف إلى Storage Box):
$(cat /root/.ssh/id_ed25519.pub)
EOF
