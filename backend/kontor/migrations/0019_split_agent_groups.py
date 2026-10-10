"""
فصل مجموعات الوكيل الكبير: كانت المجموعة الواحدة تسعّر الألعاب والرصيد معاً.

كل مجموعةٍ قائمة تبقى مجموعة **ألعاب**. فإن كان لها أسعار رصيد، تُنشأ لها توأمٌ
**رصيد** بالاسم نفسه، وتنتقل إليها أسعار الرصيد، ويوضع فيها كل دكانٍ كان في
الأصل — فلا يتغيّر سعرٌ على أحد يوم الانتقال.
"""
from django.db import migrations


def split(apps, schema_editor):
    Group = apps.get_model("catalog", "AgentPriceGroup")
    KPrice = apps.get_model("kontor", "AgentKontorPrice")
    User = apps.get_model("core", "User")
    for g in Group.objects.filter(section="games"):
        rows = KPrice.objects.filter(group=g)
        if not rows.exists():
            continue
        twin = Group.objects.create(tenant_id=g.tenant_id, agent_id=g.agent_id, name=g.name, section="mobile")
        rows.update(group=twin)
        User.objects.filter(agent_price_group=g).update(agent_kontor_price_group=twin)


class Migration(migrations.Migration):
    dependencies = [
        ("kontor", "0018_manual_flag"),
        ("catalog", "0021_agent_group_sections"),
        ("core", "0035_agent_group_sections"),
    ]
    operations = [migrations.RunPython(split, migrations.RunPython.noop)]
