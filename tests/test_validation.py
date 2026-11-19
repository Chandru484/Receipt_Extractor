from extraction.validation import validate_and_reconcile_receipt
from schemas.receipt_schema import ReceiptData, ReceiptItem


def test_validation_date_normalization():
    receipt = ReceiptData(
        invoice_date="6-Oct-26",
        grand_total=350.00
    )
    validated, diag = validate_and_reconcile_receipt(receipt)
    assert validated.invoice_date == "2026-10-06"


def test_validation_prevents_tax_double_counting():
    # If subtotal is 296.61 and grand_total is 350.00, actual tax is 53.39
    # If LLM erroneously doubled the tax components (e.g. 106.78)
    receipt = ReceiptData(
        subtotal=296.61,
        tax=106.78,
        grand_total=350.00
    )
    validated, diag = validate_and_reconcile_receipt(receipt)
    # The reconciler should detect the double-count and fix it to ~53.39
    assert validated.tax == 53.39
    assert any("double-counted" in f for f in diag["validation_flags"])


def test_validation_infers_missing_tax():
    receipt = ReceiptData(
        subtotal=500.00,
        tax=None,
        grand_total=590.00
    )
    validated, diag = validate_and_reconcile_receipt(receipt)
    assert validated.tax == 90.00
    assert any("Inferred tax" in f for f in diag["validation_flags"])


def test_validation_items_total_calculation():
    items = [
        ReceiptItem(item_name="Pen", quantity=2.0, unit_price=10.0, total_price=None),
        ReceiptItem(item_name="Book", quantity=1.0, unit_price=50.0, total_price=50.0)
    ]
    receipt = ReceiptData(
        items=items,
        subtotal=70.00,
        tax=0.0,
        grand_total=70.00
    )
    validated, diag = validate_and_reconcile_receipt(receipt)
    assert validated.items[0].total_price == 20.00
    assert diag["calculated_items_sum"] == 70.00
