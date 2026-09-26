"""
تجهيز **نسخة عميل** جديدة: متجرٌ واحد وصاحبُه، ومالكُ المنصّة — مرّةً واحدة.

كل عميلٍ يشتري نسخةً مستقلّة بدومينه وخادمه وقاعدته (plan2.md). فالنسخة لا
تُزرع ببذور العرض (`SEED_DEMO=0`)، بل بهذا الأمر وحده:

    docker compose -f deploy/docker-compose.yml exec web \\
        python manage.py provision_instance --store "أهلا كارد" --admin-login 5551234567

كلمات السرّ **عشوائية** إن لم تُعطَ، وتُطبع مرّةً واحدة هنا ولا تُحفظ في أي
ملف: بذورُ العرض بكلماتٍ معروفة (`admin123`) على نسخةٍ مبيعة بابٌ مفتوح.

ويرفض العمل إن وُجد متجرٌ في القاعدة: إعادةُ تشغيله بالخطأ لا تصنع متجراً
ثانياً في نسخةٍ صُمّمت لمتجرٍ واحد.
"""
import secrets
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.models import Tenant, User, Wallet


def _password() -> str:
    # 12 محرفاً بلا ما يلتبس عند النقل باليد (0/O · 1/l/I)
    alphabet = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "".join(secrets.choice(alphabet) for _ in range(12))


class Command(BaseCommand):
    help = "تجهيز نسخة عميل: متجر واحد + صاحبه + مالك المنصّة (مرّة واحدة)"

    def add_arguments(self, parser):
        parser.add_argument("--store", required=True, help="اسم المتجر كما يراه الوكلاء")
        parser.add_argument("--subdomain", default="main",
                            help="معرّف داخلي للمتجر — لا يظهر في الرابط في نسخة العميل")
        parser.add_argument("--currency", default="USD", help="عملة دفتر المتجر (USD · TRY …)")
        parser.add_argument("--admin-login", required=True, help="رقم دخول صاحب المتجر")
        parser.add_argument("--admin-name", default="صاحب المتجر")
        parser.add_argument("--admin-password", default="", help="فارغ ⇒ عشوائية")
        parser.add_argument("--owner-login", default="9990000000", help="رقم دخول مالك المنصّة")
        parser.add_argument("--owner-password", default="", help="فارغ ⇒ عشوائية")

    def handle(self, *args, **o):
        if Tenant.objects.exists():
            raise CommandError("في القاعدة متجرٌ قائم — هذه النسخة مجهّزة من قبل.")
        for login in (o["admin_login"], o["owner_login"]):
            if User.objects.filter(login_id=login).exists():
                raise CommandError(f"رقم الدخول {login} مستعمل.")
        if o["admin_login"] == o["owner_login"]:
            raise CommandError("رقم صاحب المتجر ورقم مالك المنصّة يجب أن يختلفا.")

        admin_pw = o["admin_password"] or _password()
        owner_pw = o["owner_password"] or _password()

        with transaction.atomic():
            tenant = Tenant.objects.create(
                name=o["store"], short_name=o["store"], subdomain=o["subdomain"],
                status=Tenant.Status.ACTIVE, base_currency=o["currency"].upper(),
            )
            admin = User(
                tenant=tenant, role=User.Role.TENANT_ADMIN, login_id=o["admin_login"],
                name=o["admin_name"], status=User.Status.ACTIVE, is_staff=True,
            )
            admin.set_password(admin_pw)
            admin.save()
            Wallet.objects.create(tenant=tenant, user=admin, balance=Decimal("0"))

            owner = User(
                tenant=None, role=User.Role.PLATFORM_OWNER, login_id=o["owner_login"],
                name="مالك المنصّة", status=User.Status.ACTIVE,
                is_staff=True, is_superuser=True,
            )
            owner.set_password(owner_pw)
            owner.save()

        self.stdout.write(self.style.SUCCESS("\n✓ جُهّزت النسخة — احفظ هذه البيانات الآن، لن تُطبع ثانيةً:\n"))
        self.stdout.write(f"  المتجر:         {tenant.name}  ({tenant.base_currency})")
        self.stdout.write(f"  صاحب المتجر:    {admin.login_id}  /  {admin_pw}")
        self.stdout.write(f"  مالك المنصّة:   {owner.login_id}  /  {owner_pw}\n")
