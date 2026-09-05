"""Field types shared by more than one schema.

An amount is spelled the same way wherever it appears. A second definition of
"money" would drift from the first, and then a day rate heard from a contact
and a rate quoted on a deal would validate differently while claiming to be the
same kind of number.
"""

from decimal import Decimal
from typing import Annotated

from pydantic import Field, StringConstraints

# ISO 4217, normalised to upper case so "eur" and "EUR" are one currency rather
# than two columns in a report.
Currency = Annotated[str, StringConstraints(to_upper=True, pattern=r"^[A-Za-z]{3}$")]

# 14 digits with 2 after the point — up to 999,999,999,999.99, which is more
# headroom than a solo business needs and still fits Numeric(14, 2).
Money = Annotated[Decimal, Field(ge=0, max_digits=14, decimal_places=2)]
