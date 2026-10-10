"""
تسعير الوكيل الكبير لدكاكينه — مصفوفة كمصفوفة صاحب المتجر، للألعاب والخطوط.

الصفوف باقات (مجمّعة باللعبة، أو بالشركة والفئة للخطوط)، والأعمدة مجموعاته.
كل خلية إمّا **مرتبطة بقاعدة** (تكلفته + نسبة أو مبلغ) فتتبع تكلفته كلّما غيّر
المتجر سعره، وإمّا رقمٌ يدويّ. والتسعير الجماعي يكتب القاعدة لا الرقم وحده.

`section=games|mobile` يختار القسم. كل مبلغ داخلٌ وخارجٌ بعملة عرض الوكيل.
"""
from decimal import Decimal, InvalidOperation

from django.db import transaction
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from catalog.models import AgentPriceGroup, AgentProductPrice, Product
from catalog.services import agent_row_price, price_from_margin, rounds
from core import currency
from kontor import reporting as kr
from kontor.models import AgentKontorPrice, KontorPackage
from kontor.services import store_price as kontor_store_price
from orders.services import resolve_store_price

from .views import AGENT


def _section(request):
    return "mobile" if (request.query_params.get("section") or request.data.get("section")) == "mobile" \
        else "games"


def _items(agent, section):
    """(باقة، تكلفة الوكيل، عنوان مجموعتها، هل تُقرَّب) — بالترتيب المعروض."""
    from orders.pricebook import GamePrices, MobilePrices
    if section == "mobile":
        book = MobilePrices(agent)
        pkgs = (KontorPackage.objects.filter(tenant=agent.tenant, status=KontorPackage.Status.ACTIVE)
                .select_related("category")
                .order_by("operator", "category__sort_order", "category_id", "sort_order", "id"))
        for p in pkgs:
            head = f"{kr.OP_LABEL.get(p.operator, p.operator)} · {p.category.name if p.category else '—'}"
            yield p, book.store_price(p), head, True
        return
    book = GamePrices(agent)
    prods = (Product.objects.filter(tenant=agent.tenant, status=Product.Status.ACTIVE)
             .select_related("game").order_by("game__sort_order", "game_id", "sort_order"))
    for p in prods:
        yield p, book.store_price(p), p.game.name, rounds(p, True)


def _rows_model(section):
    return (AgentKontorPrice, "package") if section == "mobile" else (AgentProductPrice, "product")


@api_view(["GET"])
@permission_classes(AGENT)
def price_matrix_view(request):
    agent = request.user
    section = _section(request)
    groups = list(AgentPriceGroup.objects.filter(agent=agent).order_by("id"))
    Model, fk = _rows_model(section)
    explicit = {(getattr(r, f"{fk}_id"), r.group_id): r for r in Model.objects.filter(group__agent=agent)}
    show = lambda v: str(currency.to_display(agent, v))  # noqa: E731

    blocks, cur = [], None
    for p, cost, head, round_ok in _items(agent, section):
        if cur is None or cur["name"] != head:
            cur = {"name": head, "products": []}
            blocks.append(cur)
        cells = {}
        for g in groups:
            r = explicit.get((p.id, g.id))
            cells[g.id] = None if r is None else {
                "price": show(agent_row_price(r, cost, round_ok)),
                "margin": ({"mode": r.margin_mode,
                            "value": str(r.margin_value if r.margin_mode == "percent"
                                         else currency.to_display(agent, r.margin_value)),
                            "round": r.margin_round}
                           if r.margin_mode and r.margin_value is not None else None),
            }
        # «الموصى» سعر بيع الزبون الذي يقترحه صاحب المتجر — للعرض وحده هنا
        row = {"id": p.id, "name": p.name, "cost": show(cost), "prices": cells,
               "recommended": show(p.recommended_price or 0)}
        if section == "games":
            row.update(sale_type=p.sale_type, qty_unit=p.qty_unit)
        else:
            row.update(operator=p.operator, link_code=p.link_code, znet_id=p.znet_id,
                       category=p.category.name if p.category else "")
        cur["products"].append(row)
    return Response({
        "section": section,
        "groups": [{"id": g.id, "name": g.name, "dealers": g.dealers.count()} for g in groups],
        "blocks": blocks,
        "currency": currency.display_currency(agent),
    })


def _item(agent, section, pk):
    if section == "mobile":
        p = KontorPackage.objects.filter(pk=pk, tenant=agent.tenant).first()
        return p, (kontor_store_price(agent, p) if p else None)
    p = Product.objects.filter(pk=pk, tenant=agent.tenant).first()
    return p, (resolve_store_price(agent, p) if p else None)


@api_view(["POST"])
@permission_classes(AGENT)
def set_price_view(request):
    """
    خلية واحدة يدوياً: {section, group, product, price}. فارغ ⇐ تُحذف فيبيع بتكلفته.
    الكتابة اليدوية تفكّ ارتباط الخلية بقاعدتها.
    """
    agent = request.user
    section = _section(request)
    group = AgentPriceGroup.objects.filter(pk=request.data.get("group"), agent=agent).first()
    if group is None:
        return Response({"detail": "المجموعة غير موجودة"}, status=404)
    item, cost = _item(agent, section, request.data.get("product"))
    if item is None:
        return Response({"detail": "الباقة غير موجودة"}, status=404)
    Model, fk = _rows_model(section)
    raw = request.data.get("price")
    if raw in (None, ""):
        Model.objects.filter(group=group, **{fk: item}).delete()
        return Response({"product": item.id, "price": None})
    try:
        price = currency.from_display(agent, Decimal(str(raw).replace(",", ".")))
    except (InvalidOperation, TypeError, ValueError):
        return Response({"detail": "سعر غير صحيح"}, status=400)
    if price < cost:
        return Response({"detail": f"السعر أقلّ من تكلفتك ({currency.fmt(agent, cost)})"}, status=400)
    Model.objects.update_or_create(
        group=group, **{fk: item},
        defaults={"tenant": agent.tenant, "price": price,
                  "margin_mode": "", "margin_value": None, "margin_round": False},
    )
    return Response({"product": item.id, "price": str(currency.to_display(agent, price))})


@api_view(["POST"])
@permission_classes(AGENT)
def bulk_price_view(request):
    """
    تسعير جماعي: {section, groups: [ids], products: [ids] | فارغ = الكل,
    mode: percent|fixed, value, round}. السعر = **تكلفته** + الهامش، مرتبطاً بها.
    الهامش الثابت بعملة عرضه. وتكرار العملية بالقيمة نفسها يعطي النتيجة نفسها.
    """
    agent = request.user
    section = _section(request)
    ids = [int(g) for g in (request.data.get("groups") or []) if str(g).isdigit()]
    groups = list(AgentPriceGroup.objects.filter(agent=agent, id__in=ids))
    if not groups:
        return Response({"detail": "اختر مجموعة واحدة على الأقل"}, status=400)
    mode = request.data.get("mode")
    if mode not in ("percent", "fixed"):
        return Response({"detail": "نوع الهامش غير صحيح"}, status=400)
    try:
        value = Decimal(str(request.data.get("value")).replace(",", "."))
    except (InvalidOperation, TypeError, ValueError):
        return Response({"detail": "القيمة غير صحيحة"}, status=400)
    if value < 0:
        return Response({"detail": "الهامش لا يكون سالباً — لا بيع تحت تكلفتك"}, status=400)
    stored = value if mode == "percent" else currency.from_display(agent, value)
    round_up = request.data.get("round") is True

    wanted = {int(x) for x in (request.data.get("products") or []) if str(x).isdigit()}
    picked = [(p, cost, r) for p, cost, _h, r in _items(agent, section) if not wanted or p.id in wanted]
    if not picked:
        return Response({"detail": "لم تُحدَّد أي باقة"}, status=400)

    Model, fk = _rows_model(section)
    done, zero = 0, []
    with transaction.atomic():
        for p, cost, round_ok in picked:
            price = price_from_margin(cost, mode, stored, round_ok and round_up, currency.LEDGER)
            if price is None:
                zero.append(p.name)
                continue
            for g in groups:
                Model.objects.update_or_create(
                    group=g, **{fk: p},
                    defaults={"tenant": agent.tenant, "price": price, "margin_mode": mode,
                              "margin_value": stored, "margin_round": round_up},
                )
            done += 1
    return Response({"updated": done, "groups": [g.name for g in groups], "skipped_zero_cost": zero})


@api_view(["POST"])
@permission_classes(AGENT)
def clear_prices_view(request):
    """إزالة أسعار باقاتٍ من مجموعات ⇐ تعود إلى تكلفته. {section, groups, products | فارغ = الكل}."""
    agent = request.user
    section = _section(request)
    Model, fk = _rows_model(section)
    qs = Model.objects.filter(group__agent=agent, group_id__in=request.data.get("groups") or [])
    if request.data.get("products"):
        qs = qs.filter(**{f"{fk}_id__in": request.data["products"]})
    n, _ = qs.delete()
    return Response({"deleted": n})
