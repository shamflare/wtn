from decimal import Decimal

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("catalog", "0014_game_product_is_archived")]

    operations = [
        migrations.CreateModel(
            name="LibrarySource",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=120)),
                ("code", models.CharField(default="zdk", max_length=20)),
                ("config", models.JSONField(blank=True, default=dict)),
                ("currency", models.CharField(default="USD", max_length=8)),
                ("usd_rate", models.DecimalField(decimal_places=4, default=Decimal("1"), max_digits=14)),
                ("default_margin", models.DecimalField(decimal_places=2, default=Decimal("10"), max_digits=6)),
                ("last_synced_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={"db_table": "library_sources", "ordering": ["id"]},
        ),
        migrations.AddField(
            model_name="librarygame", name="source",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                                    related_name="games", to="catalog.librarysource"),
        ),
        migrations.AddField(
            model_name="librarygame", name="source_key",
            field=models.CharField(blank=True, db_index=True, default="", max_length=200),
        ),
        migrations.AddField(
            model_name="libraryproduct", name="source_ref",
            field=models.CharField(blank=True, db_index=True, default="", max_length=120),
        ),
        migrations.AddField(
            model_name="libraryproduct", name="source_name",
            field=models.CharField(blank=True, default="", max_length=200),
        ),
        migrations.AddField(
            model_name="libraryproduct", name="source_cost",
            field=models.DecimalField(blank=True, decimal_places=4, max_digits=14, null=True),
        ),
    ]
