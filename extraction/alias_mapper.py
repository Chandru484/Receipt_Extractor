import re
from typing import Dict, List, Optional

FIELD_ALIASES: Dict[str, List[str]] = {
    "subtotal": [
        "subtotal",
        "sub total",
        "taxable value",
        "taxable amount",
        "total taxable",
        "taxable amt",
        "gross amount",
        "items total",
        "total before tax"
    ],
    "grand_total": [
        "grand total",
        "net amount",
        "amount payable",
        "total payable",
        "balance due",
        "total amount",
        "amount chargeable",
        "net payable",
        "amt payable",
        "pay amount",
        "invoice total",
        "bill amount",
        "total"
    ],
    "tax": [
        "total tax",
        "tax amount",
        "tax amt",
        "vat",
        "gst",
        "cgst",
        "sgst",
        "igst",
        "utgst",
        "sales tax",
        "total tax amount"
    ],
    "invoice_number": [
        "invoice no",
        "invoice number",
        "inv no",
        "inv #",
        "bill no",
        "bill number",
        "st.no",
        "st no",
        "receipt no",
        "receipt #",
        "memo no",
        "cash bill no",
        "tax invoice no"
    ],
    "invoice_date": [
        "invoice date",
        "dated",
        "date",
        "bill date",
        "txn date",
        "transaction date",
        "order date"
    ],
    "customer_name": [
        "buyer (bill to)",
        "buyer",
        "bill to",
        "billed to",
        "customer name",
        "customer",
        "client name",
        "client",
        "party name"
    ],
    "vendor_name": [
        "seller",
        "vendor",
        "store",
        "shop",
        "dealer",
        "supplier",
        "company"
    ]
}


def normalize_label(label: str) -> str:
    """Normalize label for fuzzy alias matching."""
    label = label.lower().strip()
    label = re.sub(r"[:#\-_./]", " ", label)
    label = re.sub(r"\s+", " ", label).strip()
    return label


def match_field_alias(label: str) -> Optional[str]:
    """Match a text label to its canonical field name."""
    norm = normalize_label(label)
    if not norm:
        return None

    # Step 1: Check exact matches first
    for field, aliases in FIELD_ALIASES.items():
        if norm in aliases:
            return field

    # Step 2: Check boundary word / phrase containment
    # Special guard: Do not let 'sub total' match 'total'
    if "sub" in norm:
        return "subtotal"

    for field, aliases in FIELD_ALIASES.items():
        for alias in aliases:
            if alias == "total":
                continue  # 'total' alone should only match exactly
            if norm.startswith(alias) or norm.endswith(alias):
                return field

    return None


def get_aliases_for_field(field_name: str) -> List[str]:
    """Retrieve all recognized aliases for a target field."""
    return FIELD_ALIASES.get(field_name, [])
