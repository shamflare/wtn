from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("orders", "0005_order_client_uuid_and_more")]
    operations = [migrations.AddField(model_name="order", name="quantity",
                                      field=models.PositiveBigIntegerField(default=1))]
