from extraction.alias_mapper import match_field_alias
from extraction.field_extractor import (
    normalize_date_string,
    detect_currency,
    extract_gstin,
    extract_potential_invoice_numbers
)


def test_alias_mapper_totals():
    assert match_field_alias("Net Amount") == "grand_total"
    assert match_field_alias("Amount Payable") == "grand_total"
    assert match_field_alias("Grand Total") == "grand_total"
    assert match_field_alias("Total Payable") == "grand_total"
    assert match_field_alias("Sub Total") == "subtotal"
    assert match_field_alias("Taxable Value") == "subtotal"
    assert match_field_alias("CGST") == "tax"
    assert match_field_alias("Total Tax") == "tax"
    assert match_field_alias("Invoice No:") == "invoice_number"
    assert match_field_alias("ST.No") == "invoice_number"
    assert match_field_alias("Buyer (Bill to)") == "customer_name"


def test_normalize_date_string():
    # ISO format to DD-MM-YYYY
    assert normalize_date_string("2026-10-18") == "18-10-2026"
    # DD/MM/YYYY with time
    assert normalize_date_string("26/09/2026 10:47") == "26-09-2026"
    # DD-MMM-YY
    assert normalize_date_string("6-Oct-26") == "06-10-2026"
    assert normalize_date_string("10-Oct-26") == "10-10-2026"
    # DD/MM/YYYY
    assert normalize_date_string("17/10/2026") == "17-10-2026"
    # Invalid
    assert normalize_date_string("invalid_date") is None
    assert normalize_date_string("") is None


def test_detect_currency():
    assert detect_currency("Total: ₹350.00") == "INR"
    assert detect_currency("Amount: Rs. 1779.66") == "INR"
    assert detect_currency("Total: $45.00") == "USD"
    assert detect_currency("Price: 100 EUR") == "EUR"
    assert detect_currency("No currency here") is None


def test_extract_gstin():
    text = "GSTIN/UIN: 33AVBPS9190F1ZD State Name: Tamil Nadu"
    assert extract_gstin(text) == "33AVBPS9190F1ZD"
    assert extract_gstin("No GST here") is None


def test_extract_potential_invoice_numbers():
    text = "Invoice No: Gst/26-27/16740 Dated: 6-Oct-26"
    candidates = extract_potential_invoice_numbers(text)
    assert any("16740" in c for c in candidates)
