from extraction.alias_mapper import match_field_alias
from extraction.field_extractor import detect_currency, normalize_date_string
from extraction.validation import validate_and_reconcile_receipt
from schemas.receipt_schema import ReceiptData, ReceiptItem


# Synthetic Fixture 1: Supermarket Cash Memo with Net Amount alias
SYNTHETIC_SUPERMARKET_OCR = {
    "full_text": """
    FRESH SUPERMARKET
    123 Market Road, Bangalore - 560001
    Cash Memo No: CM-9082
    Date: 15/08/2026 14:30

    ITEMS PURCHASED:
    Organic Milk 1L       2.00   60.00   120.00
    Whole Wheat Bread     1.00   45.00    45.00
    Alphonso Mango Jam    1.00  110.00   110.00

    Sub Total: 275.00
    CGST 2.5%: 6.88
    SGST 2.5%: 6.88
    Total Tax: 13.76
    Net Amount: 288.76

    Payment: UPI
    Thank you! Visit Again.
    """,
    "lines": [
        {"text": "FRESH SUPERMARKET", "confidence": 0.99},
        {"text": "Cash Memo No: CM-9082", "confidence": 0.98},
        {"text": "Date: 15/08/2026 14:30", "confidence": 0.97},
        {"text": "Net Amount: 288.76", "confidence": 0.99}
    ]
}


# Synthetic Fixture 2: Restaurant Bill with Amount Payable alias
SYNTHETIC_RESTAURANT_OCR = {
    "full_text": """
    SPICE ROUTE RESTAURANT
    Table 04 | Captain: Alex
    Bill #: SR-4451
    Date: 2026-11-10 20:15

    1 Paneer Tikka       240.00   240.00
    2 Butter Naan         40.00    80.00
    1 Dal Makhani        200.00   200.00

    Taxable Amount: 520.00
    GST @ 5%: 26.00
    Amount Payable: 546.00
    """,
    "lines": [
        {"text": "SPICE ROUTE RESTAURANT", "confidence": 0.98},
        {"text": "Bill #: SR-4451", "confidence": 0.95},
        {"text": "Amount Payable: 546.00", "confidence": 0.99}
    ]
}


# Synthetic Fixture 3: Ambiguous / Faded Receipt with Missing Fields
SYNTHETIC_AMBIGUOUS_OCR = {
    "full_text": """
    CORNER CAFE
    Receipt: #99
    Date: Unreadable / Faded

    Coffee               50.00
    Cookie               30.00

    Total: 80.00
    """,
    "lines": [
        {"text": "CORNER CAFE", "confidence": 0.90},
        {"text": "Total: 80.00", "confidence": 0.95}
    ]
}


def test_synthetic_supermarket_mapping():
    assert match_field_alias("Net Amount") == "grand_total"
    assert match_field_alias("Sub Total") == "subtotal"
    assert match_field_alias("Cash Memo No") == "invoice_number"

    # Simulate parsed receipt from fixture
    receipt = ReceiptData(
        document_type="receipt",
        vendor_name="FRESH SUPERMARKET",
        invoice_number="CM-9082",
        invoice_date="15/08/2026",
        items=[
            ReceiptItem(item_name="Organic Milk 1L", quantity=2.0, unit_price=60.0, total_price=120.0),
            ReceiptItem(item_name="Whole Wheat Bread", quantity=1.0, unit_price=45.0, total_price=45.0),
            ReceiptItem(item_name="Alphonso Mango Jam", quantity=1.0, unit_price=110.0, total_price=110.0)
        ],
        subtotal=275.0,
        tax=13.76,
        grand_total=288.76,
        currency="INR"
    )

    validated, diag = validate_and_reconcile_receipt(receipt, SYNTHETIC_SUPERMARKET_OCR["full_text"])
    assert validated.invoice_date == "15-08-2026"
    assert validated.grand_total == 288.76
    assert validated.subtotal == 275.00
    assert validated.tax == 13.76
    assert len(validated.items) == 3


def test_synthetic_restaurant_mapping():
    assert match_field_alias("Amount Payable") == "grand_total"
    assert match_field_alias("Taxable Amount") == "subtotal"

    receipt = ReceiptData(
        document_type="receipt",
        vendor_name="SPICE ROUTE RESTAURANT",
        invoice_number="SR-4451",
        invoice_date="2026-11-10",
        items=[
            ReceiptItem(item_name="Paneer Tikka", quantity=1.0, unit_price=240.0, total_price=240.0),
            ReceiptItem(item_name="Butter Naan", quantity=2.0, unit_price=40.0, total_price=80.0),
            ReceiptItem(item_name="Dal Makhani", quantity=1.0, unit_price=200.0, total_price=200.0)
        ],
        subtotal=520.0,
        tax=26.0,
        grand_total=546.0,
        currency="INR"
    )

    validated, diag = validate_and_reconcile_receipt(receipt, SYNTHETIC_RESTAURANT_OCR["full_text"])
    assert validated.invoice_date == "10-11-2026"
    assert validated.grand_total == 546.0
    assert validated.tax == 26.0
    assert diag["calculated_items_sum"] == 520.0


def test_synthetic_ambiguous_fields():
    # If date is unreadable, it should validate to null
    receipt = ReceiptData(
        document_type="receipt",
        vendor_name="CORNER CAFE",
        invoice_number="#99",
        invoice_date="Unreadable / Faded",
        items=[],
        subtotal=None,
        tax=None,
        grand_total=80.0,
        currency=None
    )

    validated, diag = validate_and_reconcile_receipt(receipt, SYNTHETIC_AMBIGUOUS_OCR["full_text"])
    assert validated.invoice_date is None
    assert validated.customer_name is None
    assert validated.items == []
    assert validated.grand_total == 80.0
