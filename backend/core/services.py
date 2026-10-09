"""
منطق المحفظة: شحن/خصم ذرّي (atomic) مع احترام الحد الائتماني.
كل حركة تُسجّل في دفتر الأستاذ (before/after) داخل معاملة قاعدة بيانات واحدة.
"""
from decimal import Decimal

from django.db import transaction

from .models import User, Wallet, WalletTransaction


class WalletError(Exception):
    """خطأ في عملية المحفظة (مثل تجاوز الحد الائتماني)."""


@transaction.atomic
def apply_transaction(
    wallet_id: int,
    amount: Decimal,
    txn_type: str,
    *,
    created_by: User | None = None,
    note: str = "",
    ref_type: str = "",
    ref_id: int | None = None,
    allow_below_limit: bool = False,
    internal: bool = False,
) -> WalletTransaction:
    """
    يطبّق حركة على المحفظة بشكل ذرّي.
    amount موقّع: موجب = زيادة رصيد، سالب = خصم.
    يرفض الخصم إذا نزل الرصيد تحت الحد الائتماني (إلا إذا allow_below_limit).
    """
    # قفل صف المحفظة لمنع سباق التزامن (race condition)
    wallet = Wallet.objects.select_for_update().get(pk=wallet_id)

    before = wallet.balance
    after = before + amount

    # الحد الائتماني: أقصى قيمة سالبة مسموحة (credit_limit ≤ 0)
    if not allow_below_limit and after < wallet.credit_limit:
        # بعملة صاحب المحفظة لا بعملة الدفتر. وعبارة «الحد الائتماني» يتعرّف
        # بها الـ API الخارجي على «رصيد لا يكفي» — فلا تُغيَّر.
        from .currency import fmt
        owner = wallet.user
        raise WalletError(
            f"الرصيد لا يكفي: الرصيد بعد العملية ({fmt(owner, after)}) "
            f"يتجاوز الحد الائتماني ({fmt(owner, wallet.credit_limit)})"
        )

    wallet.balance = after
    wallet.save(update_fields=["balance"])

    return WalletTransaction.objects.create(
        tenant_id=wallet.tenant_id,
        wallet=wallet,
        type=txn_type,
        amount=amount,
        balance_before=before,
        balance_after=after,
        note=note,
        ref_type=ref_type,
        ref_id=ref_id,
        created_by=created_by,
        internal=internal,
    )


def topup(wallet_id: int, amount: Decimal, *, created_by=None, note="") -> WalletTransaction:
    """شحن رصيد يدوي (Finans İşlem +)."""
    if amount <= 0:
        raise WalletError("مبلغ الشحن يجب أن يكون أكبر من صفر")
    return apply_transaction(
        wallet_id, amount, WalletTransaction.Type.MANUAL_CREDIT,
        created_by=created_by, note=note or "شحن يدوي",
    )


def deduct(wallet_id: int, amount: Decimal, *, created_by=None, note="") -> WalletTransaction:
    """خصم رصيد يدوي (Finans İşlem −)."""
    if amount <= 0:
        raise WalletError("مبلغ الخصم يجب أن يكون أكبر من صفر")
    return apply_transaction(
        wallet_id, -amount, WalletTransaction.Type.MANUAL_DEBIT,
        created_by=created_by, note=note or "خصم يدوي",
    )
