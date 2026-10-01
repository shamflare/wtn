from django.db import migrations


def backfill(apps, schema_editor):
    LibraryGame = apps.get_model("catalog", "LibraryGame")
    Game = apps.get_model("catalog", "Game")
    n = 0
    for lib in LibraryGame.objects.exclude(image_url=""):
        n += Game.objects.filter(master_library_uuid=lib.uuid, image_url="").update(image_url=lib.image_url)
    print(f"
  صور المكتبة: أُكملت {n} لعبة مستوردة")


class Migration(migrations.Migration):
    dependencies = [("catalog", "0012_imageasset")]
    operations = [migrations.RunPython(backfill, migrations.RunPython.noop)]
