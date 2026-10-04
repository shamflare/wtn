"""
1) سعر بيع الوكيل لزبونه وربحه على طلب الخط (كالألعاب).
2) أسماء الفئات القصيرة كما في ZNET (Ses · Tam · 3gCep · Wifi · Yds…) بدل
   «Turkcell — باقات» — ولا يُمسّ إلا الاسم التلقائي القديم؛ ما سمّاه المالك يبقى.
"""
from decimal import Decimal

from django.db import migrations, models

OP_LABEL = {"Turkcell": "Turkcell", "Vodafone": "Vodafone", "Avea": "Türk Telekom",
            "Callback": "دولي (Callback)"}
TYPE_LABEL = {"Tam": "رصيد ليرة (TL)", "Ses": "باقات", "Sms": "رسائل", "3gCep": "إنترنت",
              "3gPc": "إنترنت واي‑فاي / PC", "Yds": "دولي", "BimCell": "BiP (BimCell)",
              "Mtn": "MTN سوري", "Syriatel": "Syriatel سوري"}
SHORT_NAME = {"Tam": "Tam", "Ses": "Ses", "Sms": "Sms", "3gCep": "3gCep", "3gPc": "Wifi",
              "Yds": "Yds", "BimCell": "BiP", "Mtn": "MTN", "Syriatel": "Syriatel"}


def _norm(s):
    # الشرطة غير المنكسرة في «واي‑فاي» قد تُحفظ بأيّ صورة — نقارن بلا شَرطات
    return (s or "").replace("‑", "-").replace("-", "").replace(" ", "")


def rename(apps, schema_editor):
    Category = apps.get_model("kontor", "KontorCategory")
    for c in Category.objects.all():
        auto = f"{OP_LABEL.get(c.operator, c.operator)} — {TYPE_LABEL.get(c.line_type, c.line_type)}"
        if _norm(c.name) == _norm(auto) and c.line_type in SHORT_NAME:
            c.name = SHORT_NAME[c.line_type]
            c.save(update_fields=["name"])


class Migration(migrations.Migration):

    dependencies = [("kontor", "0004_provider_cost_to_base_currency")]

    operations = [
        migrations.AddField(
            model_name="kontororder", name="dealer_sell_price",
            field=models.DecimalField(decimal_places=2, default=Decimal("0"), max_digits=12),
        ),
        migrations.AddField(
            model_name="kontororder", name="dealer_profit",
            field=models.DecimalField(decimal_places=2, default=Decimal("0"), max_digits=12),
        ),
        migrations.RunPython(rename, migrations.RunPython.noop),
    ]
