from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("core", "0030_wallet_currency_follows_base")]
    operations = [
        migrations.AlterField(
            model_name="user", name="status",
            field=models.CharField(choices=[("active", "نشط"), ("passive", "معطّل"),
                                            ("blacklisted", "قائمة سوداء"),
                                            ("pending", "بانتظار الموافقة")],
                                   default="active", max_length=12),
        ),
    ]
