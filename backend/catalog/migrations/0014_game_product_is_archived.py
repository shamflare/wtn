from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("catalog", "0013_backfill_library_images")]

    operations = [
        migrations.AddField(
            model_name="game", name="is_archived",
            field=models.BooleanField(db_index=True, default=False),
        ),
        migrations.AddField(
            model_name="product", name="is_archived",
            field=models.BooleanField(db_index=True, default=False),
        ),
    ]
