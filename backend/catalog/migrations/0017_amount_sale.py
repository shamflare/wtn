from django.db import migrations, models


def fields(model):
    return [
        migrations.AddField(model_name=model, name="sale_type", field=models.CharField(
            choices=[("package", "باقة ثابتة"), ("amount", "بالكمية")], default="package", max_length=8)),
        migrations.AddField(model_name=model, name="qty_min", field=models.PositiveBigIntegerField(default=1)),
        migrations.AddField(model_name=model, name="qty_max", field=models.PositiveBigIntegerField(default=1)),
        migrations.AddField(model_name=model, name="qty_unit", field=models.PositiveBigIntegerField(default=1)),
    ]


class Migration(migrations.Migration):
    dependencies = [("catalog", "0016_library_require_player_id_default")]
    operations = fields("product") + fields("libraryproduct")
