"""
تصحيح العملة: كلفة ZNET كانت تُحفظ بالليرة في cost_price وتُعامَل كأنها بعملة الدفتر.

لكل متجر دفترُه بغير الليرة:
  • provider_cost ⇐ الكلفة الأصلية بالليرة (كما وصلت).
  • cost_price و recommended_price وأسعار المجموعات ÷ سعر صرف الليرة —
    فما كتبه المالك وهو يظنّ الأرقام ليرةً يصير بعملة دفتره بنفس القيمة.
  • قاعدة «مبلغ ثابت» في خلية مرتبطة تُقسَم كذلك؛ والنسبة المئوية لا تتغيّر.
وإن لم يُضبط سعر صرف الليرة: تُصفَّر الأسعار — فيمنع حارس البيع (بلا كلفة) أيّ شراء
حتى يضبط المالك السعر ويعيد الاستيراد. الطلبات السابقة لا تُمسّ: ما خُصم خُصم.
"""
from decimal import Decimal, InvalidOperation

from django.db import migrations, models

CENT = Decimal("0.01")


def _rate(tenant):
    try:
        r = Decimal(str((tenant.exchange_rates or {}).get("TRY", "0")))
    except (InvalidOperation, TypeError):
        return Decimal("0")
    return r if r > 0 else Decimal("0")


def forwards(apps, schema_editor):
    Tenant = apps.get_model("core", "Tenant")
    Package = apps.get_model("kontor", "KontorPackage")
    Price = apps.get_model("kontor", "KontorPackagePrice")

    for tenant in Tenant.objects.filter(kontor_packages__isnull=False).distinct():
        pkgs = Package.objects.filter(tenant=tenant)
        for p in pkgs:
            p.provider_cost = p.cost_price
            p.save(update_fields=["provider_cost"])
        if (tenant.base_currency or "USD") == "TRY":
            print(f"  kontor currency fix [{tenant.subdomain}]: ledger TRY — unchanged")
            continue
        rate = _rate(tenant)
        print(f"  kontor currency fix [{tenant.subdomain}]: ledger {tenant.base_currency} · "
              f"TRY rate {rate or 'MISSING — prices zeroed, sales blocked'} · {pkgs.count()} packages")
        for p in pkgs:
            if rate:
                p.cost_price = (p.provider_cost / rate).quantize(CENT)
                p.recommended_price = (p.recommended_price / rate).quantize(CENT)
            else:
                p.cost_price = Decimal("0")
                p.recommended_price = Decimal("0")
            p.save(update_fields=["cost_price", "recommended_price"])
        for pp in Price.objects.filter(tenant=tenant):
            if not rate:
                pp.delete()
                continue
            pp.price = (pp.price / rate).quantize(CENT)
            if pp.margin_mode == "fixed" and pp.margin_value is not None:
                pp.margin_value = (pp.margin_value / rate).quantize(Decimal("0.0001"))
            pp.save(update_fields=["price", "margin_value"])


class Migration(migrations.Migration):

    dependencies = [
        ("kontor", "0003_kontororder"),
        ("core", "0031_user_status_pending"),
    ]

    operations = [
        migrations.AddField(
            model_name="kontorpackage",
            name="provider_cost",
            field=models.DecimalField(decimal_places=2, default=Decimal("0"), max_digits=12),
        ),
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
