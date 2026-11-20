from extraction.validation import validate_and_reconcile_receipt
from schemas.receipt_schema import ReceiptData, ReceiptItem, remove_none_values


def test_validation_date_normalization():
    receipt = ReceiptData(
        invoice_date="6-Oct-26",
        grand_total=350.00
    )
    validated, diag = validate_and_reconcile_receipt(receipt)
    assert validated.invoice_date == "06-10-2026"


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
    from extraction.field_extractor import clean_bank_account_number, clean_bank_name
    from schemas.receipt_schema import BankDetails, ReceiptData
    from extraction.validation import format_receipt_display, validate_and_reconcile_receipt

    # Test clean_bank_account_number
    assert clean_bank_account_number("ACC # 1234 1234") == "1234 1234"
    assert clean_bank_account_number("ACC #12341234") == "12341234"
    assert clean_bank_account_number(None, "ANZ Bank\nACC # 1234 1234\nBSB # 4321 432") == "1234 1234"

    # Test clean_bank_name
    assert clean_bank_name("ANZ Bank") == "ANZ Bank"
    assert clean_bank_name(None, "Total Due\n$93.50\nANZ Bank\nACC # 1234 1234") == "ANZ Bank"

    bd = BankDetails(bank_name="ANZ Bank", account_no="1234 1234", bsb_number="4321 432")

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


def test_phone_mobile_separation_and_transport_clean():
    from schemas.receipt_schema import ReceiptData, remove_none_values
    from extraction.validation import validate_and_reconcile_receipt, format_receipt_display

    ocr_sample = """
GANAPATHY ELECTRICALS
Phone :0421-4325351
Mobile :7502 444 999
Buyer: MORNING STAAR APPARELS
Transport
274/6,SASTHIRI NAGAR Extn.,
KPN COLONY (PO) NEAR G.H.,
DHARAPURAM ROAD
TIRUPUR - 641608
Mobile:
E-Way Bill No : 123456
"""
    raw = ReceiptData(
        seller_name="GANAPATHY ELECTRICALS",
        buyer_name="MORNING STAAR APPARELS",
        buyer_address="274/6,SASTHIRI NAGAR Extn., Sdsd, KPN COLONY (PO) NEAR G.H., DHARAPURAM ROAD, TIRUPUR - 641608",
        buyer_address_line_1="274/6,SASTHIRI NAGAR Extn., Sdsd",
        buyer_address_line_2="KPN COLONY (PO) NEAR G.H., DHARAPURAM ROAD, TIRUPUR - 641608",
        transport="Sdsd"
    )

    val_receipt, _ = validate_and_reconcile_receipt(raw, ocr_text=ocr_sample)

    assert val_receipt.seller_phone == "0421-4325351"
    assert val_receipt.seller_mobile == "7502 444 999"
    assert val_receipt.phone == "0421-4325351"
    assert val_receipt.mobile == "7502 444 999"

    # Address cleaned of Sdsd
    assert "Sdsd" not in val_receipt.buyer_address
    assert "Sdsd" not in val_receipt.buyer_address_line_1
    assert val_receipt.buyer_address_line_1 == "274/6,SASTHIRI NAGAR Extn."
    assert val_receipt.transport == "Sdsd"

    # Buyer mobile was blank in OCR
    assert val_receipt.buyer_mobile is None

    # Verify remove_none_values removes all null fields
    dumped = val_receipt.model_dump(exclude_none=True)
    clean_json = remove_none_values(dumped)
    assert "buyer_phone" not in clean_json
    assert "buyer_mobile" not in clean_json
    assert "buyer_email" not in clean_json
    assert clean_json["seller_phone"] == "0421-4325351"
    assert clean_json["seller_mobile"] == "7502 444 999"
    assert clean_json["transport"] == "Sdsd"

    # Display formatting check
    disp = format_receipt_display(val_receipt)
    assert "Seller Phone : 0421-4325351" in disp
    assert "Seller Mobile : 7502 444 999" in disp
    assert "Transport : Sdsd" in disp


def test_laurel_technologies_sample_address_and_buyer_phone_isolation():
    raw_ocr = """
    LAUREL TECHNOLOGIES
    ADD1
    ADD2
    ADD3
    ADD4
    GSTIN : 33CACPS9793L1ZV
    State : TamilNadu ,Code : 33
    E-Mail : business.laureltech@gmail.com
    Contact :
    
    Invoice No : 1
    Dated : 1-Jan-2023
    
    Buyer (Bill To)
    AVATAR GRAPHICS
    ADD2
    ADD3
    GSTIN / UIN : 33ANPPB7936C1Z4
    State Name : TamilNadu , Code : 33
    Contact Person : SURESH
    Contact : 9894195959
    
    Sl Description of Goods HSN/SAC Qty Rate Amount
    1 ABC 1234 1.0 Nos 95.24 95.24
    """

    receipt = ReceiptData(
        vendor_name="LAURELTECHNOLOGIES",
        seller_name="LAURELTECHNOLOGIES",
        seller_gstin="33CACPS9793L1ZV",
        seller_state="TamilNadu",
        seller_state_code="33",
        seller_email="business.laureltech@gmail.com",
        customer_name="AVATAR GRAPHICS",
        buyer_name="AVATAR GRAPHICS",
        buyer_gstin="33ANPPB7936C1Z4",
        buyer_state="TamilNadu",
        buyer_state_code="33",
        buyer_mobile="9894195959",
        invoice_number="1",
        invoice_date="1-Jan-2023",
        grand_total=9800.0
    )

    val_receipt, diag = validate_and_reconcile_receipt(receipt, raw_ocr)

    # Date should be normalized to DD-MM-YYYY
    assert val_receipt.invoice_date == "01-01-2023"

    # Seller address with ADD1, ADD2, ADD3, ADD4
    assert val_receipt.seller_address == "ADD1, ADD2, ADD3, ADD4"
    assert val_receipt.seller_address_line_1 == "ADD1"
    assert val_receipt.seller_address_line_2 == "ADD2, ADD3, ADD4"

    # Buyer address with ADD2, ADD3
    assert val_receipt.buyer_address == "ADD2, ADD3"
    assert val_receipt.buyer_address_line_1 == "ADD2"
    assert val_receipt.buyer_address_line_2 == "ADD3"

    # Phone separation: seller has NO phone, buyer has 9894195959
    assert val_receipt.seller_phone is None
    assert val_receipt.seller_mobile is None
    assert val_receipt.phone is None
    assert val_receipt.mobile is None
    assert val_receipt.buyer_mobile == "9894195959"
    assert val_receipt.buyer_phone == "9894195959"

    # Remove none check
    dumped = val_receipt.model_dump(exclude_none=True)
    clean_json = remove_none_values(dumped)
    assert "seller_phone" not in clean_json
    assert "seller_mobile" not in clean_json
    assert "phone" not in clean_json
    assert clean_json["buyer_mobile"] == "9894195959"
    assert clean_json["invoice_date"] == "01-01-2023"
    assert clean_json["seller_address"] == "ADD1, ADD2, ADD3, ADD4"
    assert clean_json["buyer_address"] == "ADD2, ADD3"



