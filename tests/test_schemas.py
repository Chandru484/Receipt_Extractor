import pytest
from schemas.receipt_schema import ReceiptData, ReceiptItem, clean_numeric_value


def test_clean_numeric_value():
    assert clean_numeric_value("1,466.10") == 1466.10
    assert clean_numeric_value("₹350.00") == 350.00
    assert clean_numeric_value("Rs. 254.24") == 254.24
    assert clean_numeric_value("$12.99") == 12.99
    assert clean_numeric_value(100) == 100.0
    assert clean_numeric_value(None) is None
    assert clean_numeric_value("") is None
    assert clean_numeric_value("invalid") is None


def test_receipt_item_validation():
    item = ReceiptItem(
        sl_no="1",
        item_name="  Wireless Mouse  ",
        hsn_sac="84145120",
        quantity="2.0",
        unit_price="₹150.50",
        total_price="301.00"
    )
    assert item.sl_no == "1"
    assert item.item_name == "Wireless Mouse"
    assert item.hsn_sac == "84145120"
    assert item.quantity == 2.0
    assert item.unit_price == 150.50
    assert item.total_price == 301.00


def test_receipt_data_defaults():
    receipt = ReceiptData()
    assert receipt.document_type == "receipt"
    assert receipt.vendor_name is None
    assert receipt.seller is None
    assert receipt.invoice_number is None
    assert receipt.invoice_date is None
    assert receipt.customer_name is None
    assert receipt.buyer is None
    assert receipt.items == []
    assert receipt.subtotal is None
    assert receipt.tax is None
    assert receipt.grand_total is None
    assert receipt.currency is None


def test_receipt_data_extra_allowed():
    # Dynamic receipt fields like salesman and custom metadata are allowed
    receipt = ReceiptData(
        vendor_name="Store",
        salesman="ARSATH",
        custom_field="value"
    )
    assert receipt.vendor_name == "Store"
    assert receipt.salesman == "ARSATH"
    assert receipt.custom_field == "value"


def test_receipt_data_valid_json_dump():
    data = {
        "document_type": "invoice",
        "vendor_name": "Erode Paints",
        "invoice_number": "EP/2026-27/5038",
        "invoice_date": "2026-10-10",
        "customer_name": "Tekis Softwares",
        "items": [
            {
                "sl_no": "1",
                "item_name": "Ap Trac Emul Advnc TA2 10 Lit",
                "hsn_sac": "32091010",
                "quantity": 1.0,
                "unit_price": 1466.10,
                "total_price": 1466.10
            }
        ],
        "subtotal": 1940.68,
        "cgst": 174.66,
        "sgst": 174.66,
        "tax": 349.32,
        "grand_total": 2290.00,
        "currency": "INR"
    }
    receipt = ReceiptData.model_validate(data)
    dumped = receipt.model_dump()
    assert dumped["document_type"] == "invoice"
    assert dumped["vendor_name"] == "Erode Paints"
    assert dumped["seller"] == "Erode Paints"
    assert dumped["buyer"] == "Tekis Softwares"
    assert dumped["cgst"] == 174.66
    assert len(dumped["items"]) == 1
    assert dumped["grand_total"] == 2290.00
