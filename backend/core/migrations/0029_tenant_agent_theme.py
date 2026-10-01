from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("core", "0028_tenant_ui_scale")]

    operations = [
        migrations.AddField(
            model_name="tenant",
            name="agent_theme",
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
