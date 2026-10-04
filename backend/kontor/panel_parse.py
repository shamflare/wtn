"""
تحليل مخرجات لوحة ZNET (HTML) إلى بيانات — نقيّ وقابل للاختبار بلا متصفّح.

مصدرا البيانات (انظر mobilecharge.md):
- كشف الشركة: رد `bilgi_api.php?operatoru=bul` — نداءان `gsm_loader('…')`، الأخير هو الشركة.
- العروض: رد `bilgi_api_paketsor.php` — عناصر `urunlist_dis` فيها `yukle_onay(...)` وخلفية
  `#F2CCCC` (وردي) للعرض الخاص بالمشترك.
"""
import re

# ترتيب وسائط yukle_onay (انظر mobilecharge.md §4-ب):
# 0 gsm · 1 operator · 2 tür · 3 معرّف · 4 فئة · 5 اسم · 6 إضافي ·
# 7 سعر معروض · 8 كلفة · 9 ربح · 10 تفاصيل · 11-12 فارغة
_YUKLE = re.compile(r"yukle_onay\((.*?)\);", re.S)
_BLOCK = re.compile(
    r'data-gun="(\d+)"\s+data-gb="(\d+)"\s+data-dk="(\d+)">(.*?)</div>\s*</div>',
    re.S,
)
_GSM_LOADER = re.compile(r"gsm_loader\('([^']+)'")
_BG = re.compile(r"background:#([0-9A-Fa-f]{6})")

PINK = "F2CCCC"  # خلفية العرض الخاص بالمشترك

# أسماء ZNET ⇐ رموز مشغّلينا
OPERATOR_MAP = {"TURKCELL": "Turkcell", "VODAFONE": "Vodafone",
                "AVEA": "Avea", "TELEKOM": "Avea", "CALLBACK": "Callback"}


def parse_operator(detect_html: str) -> str | None:
    """الشركة المكتشفة ⇐ رمزنا (Turkcell/Vodafone/Avea/Callback)، أو None."""
    loaders = _GSM_LOADER.findall(detect_html or "")
    if not loaders:
        return None
    return OPERATOR_MAP.get(loaders[-1].strip().upper())


def _split_args(raw: str) -> list[str]:
    """وسائط yukle_onay ⇐ قائمة نصوص (تزيل الأقواس المفردة والمسافات)."""
    return [a.strip().strip("'") for a in raw.split("','")]


def _norm_id(raw: str) -> str:
    """'476647.00' ⇐ '476647' (ليطابق معرّف paket_listesi)."""
    raw = (raw or "").strip().strip("'")
    try:
        return str(int(float(raw)))
    except (ValueError, TypeError):
        return raw


def parse_offers(offers_html: str) -> list[dict]:
    """
    قائمة باقات العروض، كلٌّ: znet_id · operator · line_type · name · details ·
    cost · shown_price · days/gb/minutes · is_offer (وردي = خاص بالمشترك).
    """
    out = []
    for gun, gb, dk, body in _BLOCK.findall(offers_html or ""):
        m = _YUKLE.search(body)
        if not m:
            continue
        a = _split_args(m.group(1))
        if len(a) < 11:
            continue
        bg = _BG.search(body)
        out.append({
            "znet_id": _norm_id(a[3]),
            "operator": a[1],
            "line_type": a[2],
            "name": a[5],
            "details": a[10],
            "shown_price": a[7],
            "cost": a[8],
            "days": int(gun), "gb": int(gb), "minutes": int(dk),
            "is_offer": bool(bg and bg.group(1).upper() == PINK),
        })
    return out
