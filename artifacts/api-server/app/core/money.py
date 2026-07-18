"""Shared monetary-field type for Pydantic response schemas.

Usage
-----
from app.core.money import Money

class MyResponse(BaseModel):
    price: Money                    # non-nullable
    discount: Optional[Money]       # nullable

Both variants round to exactly 2 decimal places when serialised to JSON, so
callers always see numbers like 1234.57, never 1234.5678 or "1234.57".
"""
from decimal import Decimal, ROUND_HALF_UP
from typing import Annotated, Optional

from pydantic import PlainSerializer


def _to_2dp(v: Optional[Decimal]) -> Optional[float]:
    """Round a Decimal (or coercible value) to 2 dp; pass None through."""
    if v is None:
        return None
    return float(Decimal(str(v)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


# Annotated type for non-nullable monetary Decimal fields.
Money = Annotated[Decimal, PlainSerializer(_to_2dp, return_type=float)]
