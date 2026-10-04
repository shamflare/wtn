"""
استيراد باقات الخطوط من ZNET الرسمي: `servis/paket_listesi.php`.

الرد نصّ مفصول: سطر لكل باقة بصيغة `المشغّل|النوع|المعرّف|الكلفة|الاسم|^`.
يُنشئ الفئات الناقصة ويحدّث الباقات (الكلفة والاسم فقط عند وجودها، حفاظاً على
ما عدّله المالك: الموصى، النوع عام/عرض، الحالة، التوجيه).

مثال:
  python manage.py import_kontor_packages --tenant <subdomain> \
      --base-url http://bayi.alayatl.com --bayi-kodu <kod> --sifre <sifre>
"""
from decimal import Decimal, InvalidOperation

import requests
from django.core.management.base import BaseCommand, CommandError

from core.models import Tenant
from kontor.models import KontorCategory, KontorPackage, LineType, Operator

_OPERATORS = {c.value for c in Operator}
_TYPES = {c.value for c in LineType}
_TYPE_LABEL = dict(LineType.choices)
_OP_LABEL = dict(Operator.choices)


def parse_feed(text: str) -> list[dict]:
    """نصّ `paket_listesi` ⇐ قائمة باقات صالحة. يتجاهل الأسطر المشوّهة."""
    rows = []
    for chunk in (text or "").split("^"):
        chunk = chunk.strip()
        if not chunk:
            continue
        parts = chunk.split("|")
        if len(parts) < 5:
            continue
        op, tur, zid, cost, name = (p.strip() for p in parts[:5])
        if op not in _OPERATORS or tur not in _TYPES or not zid:
            continue
        try:
            cost_val = Decimal(cost.replace(",", "."))
        except (InvalidOperation, AttributeError):
            cost_val = Decimal("0")
        rows.append({"operator": op, "line_type": tur, "znet_id": zid,
                     "cost": cost_val, "name": name})
    return rows


def _looks_like_offer(name: str) -> bool:
    low = (name or "").lower()
    return "fırsat" in low or "firsat" in low or "indirim" in low or "i̇ndirim" in low


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

        url = f"{o['base_url'].rstrip('/')}/servis/paket_listesi.php"
        try:
            resp = requests.get(url, params={"bayi_kodu": o["bayi_kodu"], "sifre": o["sifre"]}, timeout=(5, 30))
        except requests.RequestException as e:
            raise CommandError(f"تعذّر الاتصال بـ ZNET: {e}")
        rows = parse_feed(resp.text)
        if not rows:
            raise CommandError("لا باقات في الرد — تحقّق من bayi_kodu/sifre وتفعيل API وثبات الـ IP.")

        created = updated = 0
        cats: dict[tuple, KontorCategory] = {}
        for r in rows:
            key = (r["operator"], r["line_type"])
            cat = cats.get(key)
            if cat is None and not o["dry_run"]:
                cat, _ = KontorCategory.objects.get_or_create(
                    tenant=tenant, operator=r["operator"], line_type=r["line_type"],
                    defaults={"name": f"{_OP_LABEL[r['operator']]} — {_TYPE_LABEL[r['line_type']]}"},
                )
                cats[key] = cat

            if o["dry_run"]:
                continue

            obj = KontorPackage.objects.filter(
                tenant=tenant, operator=r["operator"], znet_id=r["znet_id"]
            ).first()
            if obj:
                obj.name = r["name"]
                obj.cost_price = r["cost"]
                if obj.category_id is None:
                    obj.category = cat
                obj.save(update_fields=["name", "cost_price", "category", "updated_at"])
                updated += 1
            else:
                KontorPackage.objects.create(
                    tenant=tenant, operator=r["operator"], category=cat,
                    znet_id=r["znet_id"], name=r["name"], cost_price=r["cost"],
                    kind=KontorPackage.Kind.OFFER if _looks_like_offer(r["name"]) else KontorPackage.Kind.GENERAL,
                )
                created += 1

        self.stdout.write(self.style.SUCCESS(
            f"باقات الخطوط: استُلم {len(rows)}"
            + (" (تجربة فقط)" if o["dry_run"] else f" · جديد {created} · محدّث {updated}")
        ))
