# core/business_rules.py
from dataclasses import dataclass

@dataclass(frozen=True)
class BizRule:
    code: str
    name: str
    # serial/barcode (IMEI or SKU) length range allowed in Scan IN / Sell
    serial_min: int
    serial_max: int
    require_imei: bool  # UI wording; validation already covered by length

BUSINESS_TYPES = {
    "phone_sales": BizRule("phone_sales", "Phone sales", 15, 15, True),
    "pharmacy":    BizRule("pharmacy",    "Pharmacy",    12, 13, False),
    "grocery":     BizRule("grocery",     "Grocery",     12, 13, False),
    "clothing":    BizRule("clothing",    "Clothing",    12, 13, False),
    "electronics": BizRule("electronics", "Electronics", 12, 13, False),
    "beauty":      BizRule("beauty",      "Beauty",      12, 13, False),
}

DEFAULT_BIZ_CODE = "phone_sales"

def get_rule(code: str | None):
    return BUSINESS_TYPES.get((code or "").strip() or DEFAULT_BIZ_CODE, BUSINESS_TYPES[DEFAULT_BIZ_CODE])


