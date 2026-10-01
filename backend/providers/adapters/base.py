"""إطار محوّلات المزوّدين: نتيجة موحّدة + واجهة أساسية."""
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional


@dataclass
class ExecutionResult:
    """نتيجة موحّدة لتنفيذ طلب لدى مزوّد (تُطبّق على الطلب المحلي)."""
    # الحالة المُطبّقة على الطلب: success | processing | failed
    status: str
    pin: str = ""
    note: str = ""
    external_ref: str = ""            # المرجع لدى المزوّد (للتعقّب لاحقاً)
    cost: Optional[Decimal] = None    # التكلفة الفعلية إن أعادها المزوّد
    # المزوّدون الخارجيون يسعّرون بالليرة فتُحوَّل عند الحدود. أمّا المزوّد
    # الداخلي (متجر على منصّتنا) فيسلّم الرقم **بعملة دفترنا** أصلاً، وتمريره
    # على محوّل الليرة كان يقسمه على ~41 فيظهر الطلب رابحاً وهو خاسر.
    cost_is_base: bool = False
    raw: str = ""                     # الاستجابة الخام (للتدقيق)

    @property
    def ok(self) -> bool:
        return self.status == "success"


@dataclass
class BalanceResult:
    """نتيجة استعلام الرصيد لدى مزوّد."""
    ok: bool
    balance: Optional[Decimal] = None   # الرصيد الفعلي لدى المزوّد
    debt: Optional[Decimal] = None      # الدين (إن أعاده المزوّد)
    note: str = ""
    raw: str = ""


@dataclass
class PackageList:
    """كتالوج باقات المزوّد — لصفحة ربط الباقات."""
    ok: bool
    packages: list = field(default_factory=list)  # [{id, name, game, kupur, price}]
    note: str = ""
    raw: str = ""


class BaseAdapter:
    """واجهة المحوّل: كل مزوّد ينفّذ place_order ويُعيد ExecutionResult."""

    code = "base"
    # يرسل الكمية للمزوّد (باقات «بالكمية»)؟ من لا يدعمها لا تُرسَل إليه أصلاً
    supports_quantity = False

    def place_order(self, order, config: dict, provider=None, depth: int = 0) -> ExecutionResult:  # pragma: no cover
        raise NotImplementedError

    def get_balance(self, config: dict, provider=None) -> BalanceResult:
        """جلب الرصيد الفعلي — المحوّلات الداعمة تعيد تعريفه."""
        return BalanceResult(ok=False, note="هذا النوع لا يدعم جلب الرصيد آلياً")

    def fetch_status(self, order, config: dict, provider=None) -> ExecutionResult:
        """
        استعلام حالة طلب أُرسل سابقاً (حلقة المراقبة).
        يعيد status ∈ {success, processing, failed} + pin + note إن توفّرت.
        `unsupported` يعني أن هذا المزوّد لا يدعم المتابعة فيُترك الطلب كما هو.
        """
        return ExecutionResult(status="unsupported", note="هذا النوع لا يدعم متابعة الحالة")

    def quote(self, order, config: dict, provider=None):
        """
        سعر هذه الباقة لدى هذا المزوّد **الآن**، بعملة دفترنا — أو None.

        لحماية الخسارة قبل أوّل طلب. المزوّد الخارجي يلزمه نداء شبكة فلا يُسأل
        (ترتدّ الحماية إلى السعر المُتعلَّم من طلب سابق)، أمّا الداخلي فسعره
        في قاعدتنا فيُعرف يقيناً وبلا كلفة — فلا داعي لخسارة طلبٍ لنتعلّم.
        """
        return None

    def list_packages(self, config: dict, provider=None) -> "PackageList":
        """
        جلب كتالوج باقات المزوّد (لصفحة "ربط الباقات").
        كل عنصر: {id, name, game, kupur, price} — و`id` هو رقم الربط.
        """
        return PackageList(ok=False, note="هذا النوع لا يدعم جلب قائمة الباقات")

    @staticmethod
    def link_for(order, provider) -> tuple:
        """
        رقم الربط لهذا المنتج لدى **هذا المزوّد بالذات** + بياناته الإضافية.
        يرتدّ إلى `product.provider_package_id` القديم إن لم يوجد ربط مخصّص —
        فلا تنكسر الإعدادات السابقة.
        """
        from catalog.models import ProductLink

        if provider is not None:
            link = ProductLink.objects.filter(
                product=order.product, provider=provider
            ).first()
            if link and link.package_id:
                return link.package_id, dict(link.extra or {})
        return (order.product.provider_package_id or ""), {}

    # أدوات مشتركة لتحليل الاستجابات التركية (pipe-separated)
    @staticmethod
    def split_pipe(text: str) -> list:
        return [p.strip() for p in (text or "").strip().split("|")]
