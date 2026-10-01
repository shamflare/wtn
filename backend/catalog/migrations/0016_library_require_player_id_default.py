from django.db import migrations, models


def enable_for_imported(apps, schema_editor):
    """
    ما استُورد من المصادر حُسب «يتطلّب معرّف لاعب» من اسم الحقل لدى المزوّد،
    وبركات يسمّيه «USER ID» لا «player» — فخرجت أغلب الألعاب بلا معرّف. تُصحَّح
    مرّةً هنا؛ وما يغيّره المالك بعدها لا تمسّه المزامنة.
    """
    LibraryGame = apps.get_model("catalog", "LibraryGame")
    LibraryGame.objects.filter(source__isnull=False).update(require_player_id=True)


class Migration(migrations.Migration):
    dependencies = [("catalog", "0015_library_sources")]

    operations = [
        migrations.AlterField(
            model_name="librarygame", name="require_player_id",
            field=models.BooleanField(default=True),
        ),
        migrations.RunPython(enable_for_imported, migrations.RunPython.noop),
    ]
