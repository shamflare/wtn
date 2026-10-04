"""
استيراد باقات الخطوط من ZNET الرسمي: `servis/paket_listesi.php`.

مثال:
  python manage.py import_kontor_packages --tenant <subdomain> \
      --base-url http://bayi.alayatl.com --bayi-kodu <kod> --sifre <sifre>
"""
import requests
from django.core.management.base import BaseCommand, CommandError

from core.models import Tenant
from kontor.services import import_from_znet


class Command(BaseCommand):
    help = "استيراد باقات الخطوط التركية من ZNET (paket_listesi.php)"

    def add_arguments(self, parser):
        parser.add_argument("--tenant", required=True, help="subdomain المتجر")
        parser.add_argument("--base-url", required=True, help="مثل http://bayi.alayatl.com")
        parser.add_argument("--bayi-kodu", required=True)
        parser.add_argument("--sifre", required=True)
        parser.add_argument("--dry-run", action="store_true", help="اعرض فقط دون حفظ")

    def handle(self, *args, **o):
        tenant = Tenant.objects.filter(subdomain=o["tenant"]).first()
        if not tenant:
            raise CommandError(f"لا متجر بالـ subdomain: {o['tenant']}")
        try:
            res = import_from_znet(
                tenant, o["base_url"], o["bayi_kodu"], o["sifre"], dry_run=o["dry_run"])
        except requests.RequestException as e:
            raise CommandError(f"تعذّر الاتصال بـ ZNET: {e}")
        except ValueError as e:
            raise CommandError(str(e))

        self.stdout.write(self.style.SUCCESS(
            f"باقات الخطوط: استُلم {res['received']}"
            + (" (تجربة فقط)" if o["dry_run"] else f" · جديد {res['created']} · محدّث {res['updated']}")
        ))
