"""
رقم الربط (link_code): ما يراه الوكيل ويرسله في الـ API، ويعدّله المالك.

يُملأ لكل باقة قائمة برقم ZNET نفسه — فمن ربط مع ZNET يبقى على أرقامه. وحين
يتكرّر الرقم بين شركتين (باقات Tam مرقّمة بقيمتها: 100 لكلٍّ منها) تأخذه أوّل
شركة بالترتيب (Turkcell ثم Vodafone ثم Türk Telekom ثم الدولي) والبقية بلاحقة
حرف الشركة: 100 · 100V · 100A.
"""
from django.db import migrations, models

ORDER = ["Turkcell", "Vodafone", "Avea", "Callback"]
SUFFIX = {"Turkcell": "T", "Vodafone": "V", "Avea": "A", "Callback": "C"}


def fill(apps, schema_editor):
    Package = apps.get_model("kontor", "KontorPackage")
    by_tenant: dict[int, set] = {}
    rows = list(Package.objects.all())
    rows.sort(key=lambda p: (p.tenant_id, ORDER.index(p.operator) if p.operator in ORDER else 9, p.id))
    for p in rows:
        taken = by_tenant.setdefault(p.tenant_id, set())
        base = (p.znet_id or "").strip() or str(p.id)
        code = base
        if code in taken:
            code = f"{base}{SUFFIX.get(p.operator, 'X')}"
            n = 2
            while code in taken:
                code = f"{base}{SUFFIX.get(p.operator, 'X')}{n}"
                n += 1
        taken.add(code)
        p.link_code = code
        p.save(update_fields=["link_code"])


class Migration(migrations.Migration):

    dependencies = [("kontor", "0006_client_uuid")]

    operations = [
        migrations.AddField(
            model_name="kontorpackage", name="link_code",
            field=models.CharField(blank=True, db_index=True, default="", max_length=40),
        ),
        migrations.RunPython(fill, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="kontorpackage",
            constraint=models.UniqueConstraint(
                condition=~models.Q(link_code=""), fields=("tenant", "link_code"),
                name="uniq_kontor_link_code"),
        ),
    ]
