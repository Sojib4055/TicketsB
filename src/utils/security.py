from __future__ import annotations

from src.config import settings


def payment_summary() -> dict[str, str]:
    return {
        "payment_method_alias": settings.payment_method_alias,
        "card_last4": settings.card_last4,
        "billing_zip": settings.billing_zip,
    }
