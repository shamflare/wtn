from django.db import migrations


def align(apps, schema_editor):
    """عملة كل محفظة = عملة دفتر متجرها (كانت TRY ثابتة فظهرت أرصدة الدولار بالليرة)."""
    Tenant = apps.get_model("core", "Tenant")
    Wallet = apps.get_model("core", "Wallet")
    n = 0
    for t in Tenant.objects.all():
        n += Wallet.objects.filter(tenant=t).exclude(currency=t.base_currency).update(currency=t.base_currency)
    print(f"  wallets aligned to store currency: {n}")


class Migration(migrations.Migration):
    dependencies = [("core", "0029_tenant_agent_theme")]
    operations = [migrations.RunPython(align, migrations.RunPython.noop)]
