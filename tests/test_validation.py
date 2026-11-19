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


def test_bank_details_anz_and_bsb_formatting():
    from extraction.field_extractor import clean_bank_account_number, clean_bsb_number, clean_bank_name
    from schemas.receipt_schema import BankDetails, ReceiptData
    from extraction.validation import format_receipt_display, validate_and_reconcile_receipt

    # Test clean_bank_account_number
    assert clean_bank_account_number("ACC # 1234 1234") == "1234 1234"
    assert clean_bank_account_number("ACC #12341234") == "12341234"
    assert clean_bank_account_number(None, "ANZ Bank\nACC # 1234 1234\nBSB # 4321 432") == "1234 1234"

    # Test clean_bsb_number
    assert clean_bsb_number("BSB # 4321 432") == "4321 432"
    assert clean_bsb_number("4321 432") == "4321 432"
    assert clean_bsb_number(None, "ANZ Bank\nACC # 1234 1234\nBSB # 4321 432") == "4321 432"

    # Test clean_bank_name
    assert clean_bank_name("ANZ Bank") == "ANZ Bank"
    assert clean_bank_name(None, "Total Due\n$93.50\nANZ Bank\nACC # 1234 1234") == "ANZ Bank"

    # Test BankDetails alias resolution
    bd = BankDetails(**{"bank": "ANZ Bank", "ACC #": "1234 1234", "BSB #": "4321 432"})
    assert bd.bank_name == "ANZ Bank"
    assert bd.account_no == "1234 1234"
    assert bd.bsb_number == "4321 432"

    # Test full receipt validation & display
    receipt = ReceiptData(
        vendor_name="DEMO - Sliced Invoices",
        invoice_number="INV-3337",
        subtotal="$85.00",
        tax="$8.50",
        grand_total="$93.50",
        currency="USD",
        bank_details=bd
    )
    assert receipt.subtotal == "$85.00"
    assert receipt.tax == "$8.50"
    assert receipt.grand_total == "$93.50"

    val_receipt, _ = validate_and_reconcile_receipt(receipt)
    disp = format_receipt_display(val_receipt)
    assert "Bank Name : ANZ Bank" in disp
    assert "A/c No : 1234 1234" in disp
    assert "BSB No : 4321 432" in disp

