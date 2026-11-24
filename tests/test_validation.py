from extraction.validation import validate_and_reconcile_receipt, format_receipt_display
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


def test_dis_percent_and_currency_unification():
    raw_ocr = """
    SSS STATIONERY
    No 68104 Date :19-04-2025
    Lucky Store
    S.No Particulars Qty Rate Dis% Amount
    1 Nova Grip Jar Rs 7/- 2.00 200.00 0.00 400.00
    2 Reynold Brite 1.00 100.00 5.00 95.00
    Gross 495.00
    GRAND TOTAL 495.00
    """

    receipt = ReceiptData(
        vendor_name="SSS STATIONERY",
        currency="₹",
        invoice_number="68104",
        invoice_date="19-04-2025",
        items=[
            ReceiptItem(page=1, sl_no="1", item_name="Nova Grip Jar Rs 7/-", quantity=2.0, unit_price="200.00", total_price="400.00"),
            ReceiptItem(page=2, sl_no="2", item_name="Reynold Brite", quantity=1.0, unit_price="$100.00", discount_percent="5", total_price="$95.00")
        ],
        subtotal="495.00",
        tax="$0.01",
        grand_total="₹495.00"
    )

    val_receipt, diag = validate_and_reconcile_receipt(receipt, raw_ocr)

    # Dis% should be populated and formatted as percentage
    assert val_receipt.items[0].discount_percent == "0.00%"
    assert val_receipt.items[1].discount_percent == "5.00%" or val_receipt.items[1].discount_percent == "5%"

    # Currency must be strictly unified in ₹ (no accidental $)
    assert "₹" in val_receipt.items[0].unit_price
    assert "₹" in val_receipt.items[1].unit_price
    assert "$" not in val_receipt.items[1].unit_price
    assert "$" not in val_receipt.tax

    # Display formatting must show Dis%
    disp = format_receipt_display(val_receipt)
    assert "Dis%: 0.00%" in disp
    assert "Dis%: 5" in disp or "Dis%: 5.00%" in disp
    assert "$" not in disp


def test_hsn_tax_summary_and_combined_totals_reconciliation():
    from extraction.validation import extract_hsn_tax_summary, reconcile_missing_ocr_items

    ocr_text = """
--- Page 1 ---
GANAPATHY ELECTRICALS
97, KAMARAJ ROAD 12 01/04/2021
GSTIN/UIN :33AACFG7274J1ZA
Buyer : MORNING STAAR APPARELS
274/6,SASTHIRI NAGAR Extn., Sdsd
SNo Description Of Goods HSN/SAC GST% Qty Unit Rate Dis % Amount
1 11/2" CPVC (11-5M) (ASH) 39172390 5 2.00 % LTH 1513.00 3026.00
15 11/2" C.COUPLING (ASH) 39172390 18 4.00 % NOS 70.34 281.36
16 0.75*3C FLEX CABLE(E-FAB) 85446090 18 1.00 % MTR 37.70 37.70
17 1000L WHITE SAFE (VECTUS) 39251000 18 1.00 % NOS 10.00 10.00
Continue...

--- Page 2 ---
18 0.5 HP OPENWELL SUB 84137010 12 1.00 % NOS 100.00 100.00
19 100A FIBER 8538 18 1.00 % LTH 350.00 350.00
20 0.5*3C FLEX CABLE 85446090 18 1.00 % MTR 35.00 35.00
Total Items : 20 79.00 Total 19963.26
HSN/SAC Taxable SGST Tax CGST Tax Sub Total 19963.26
Value Rate Amount Rate Amount
39172390 3026.00 2.50 75.65 2.50 75.65
SGST @ 2.5 % 75.65
39172390 ,84137010 5089.28 6.00 305.36 6.00 305.36 CGST @ 2.5 % 75.65
SGST @ 6 % 305.36
8481,39172390 11258.90 9.00 1013.29 9.00 1013.29 CGST @ 6% 305.36
,3920,3824,35061000 SGST @ 9% 1013.29
39172390 589.08 14.00 82.47 14.00 82.47 CGST @ 9% 1013.29
SGST @ 14% 82.47
Total 19963.26 1476.77 1476.77 CGST @ 14% 82.47
Round Off -0.20
Amount Chargeable (in Words) NET TOTAL 22917.00
Rupees Twenty Two Thousand Nine Hundred And Seventeen Only
"""

    # Simulate receipt where LLM missed items 16 & 17 and had incomplete totals
    receipt = ReceiptData(
        seller_name="GANAPATHY ELECTRICALS",
        buyer_name="MORNING STAAR APPARELS",
        currency="₹",
        invoice_number="56789",
        invoice_date="01-04-2021",
        items=[
            ReceiptItem(page=1, sl_no="1", item_name='11/2" CPVC (11-5M) (ASH)', hsn_sac="39172390", quantity=2.0, uom="LTH", unit_price="1513.00", total_price="3026.00"),
            ReceiptItem(page=1, sl_no="15", item_name='11/2" C.COUPLING (ASH)', hsn_sac="39172390", quantity=4.0, uom="NOS", unit_price="70.34", total_price="281.36"),
            ReceiptItem(page=2, sl_no="18", item_name="0.5 HP OPENWELL SUB", hsn_sac="84137010", quantity=1.0, uom="NOS", unit_price="100.00", total_price="100.00"),
            ReceiptItem(page=2, sl_no="19", item_name="100A FIBER", hsn_sac="8538", quantity=1.0, uom="LTH", unit_price="350.00", total_price="350.00"),
            ReceiptItem(page=2, sl_no="20", item_name="0.5*3C FLEX CABLE", hsn_sac="85446090", quantity=1.0, uom="MTR", unit_price="35.00", total_price="35.00"),
        ]
    )

    val_receipt, diag = validate_and_reconcile_receipt(receipt, ocr_text)

    # 1. Missing items 16 and 17 must be recovered and ordered
    sl_nos = [it.sl_no for it in val_receipt.items]
    assert "16" in sl_nos
    assert "17" in sl_nos
    assert len(val_receipt.items) == 7

    # 2. HSN tax summary must be populated with 4 rows
    assert val_receipt.hsn_tax_summary is not None
    assert len(val_receipt.hsn_tax_summary) == 4
    assert val_receipt.hsn_tax_summary[0].hsn_sac == "39172390"
    assert val_receipt.hsn_tax_summary[0].taxable_value == 3026.00
    assert val_receipt.hsn_tax_summary[0].cgst_amount == 75.65
    assert val_receipt.hsn_tax_summary[0].sgst_amount == 75.65

    # Check comma-separated HSN continuation in row 3
    assert "8481" in val_receipt.hsn_tax_summary[2].hsn_sac
    assert "35061000" in val_receipt.hsn_tax_summary[2].hsn_sac
    assert val_receipt.hsn_tax_summary[2].taxable_value == 11258.90

    # 3. Authoritative totals must match the invoice
    assert val_receipt.subtotal == 19963.26
    assert val_receipt.cgst == 1476.77
    assert val_receipt.sgst == 1476.77
    assert val_receipt.tax == 2953.54
    assert val_receipt.rounded_off == -0.20
    assert val_receipt.grand_total == 22917.00

    # 4. Formatted display must include HSN / Tax Summary
    disp = format_receipt_display(val_receipt)
    assert "HSN / Tax Summary :" in disp
    assert "Subtotal : ₹19963.26" in disp
    assert "CGST : ₹1476.77" in disp
    assert "SGST : ₹1476.77" in disp
    assert "Total Tax : ₹2953.54" in disp
    assert "Round Off : ₹-0.20" in disp
    assert "Grand Total : ₹22917.00" in disp


def test_sss_stationery_lucky_store_reconciliation_and_null_preservation():
    raw_ocr = """
--- Page 1 ---
Estimate / Quotation
SSS STATIONERY
No : 68104 Date : 19-04-2025
Lucky Store Page No : 1
S.No Particulars Qty Rate Dis% Amount
1 Nova Grip Jar Rs 7/- 2.00 200.00 0.00 400.00
7 Barfi Topper Jar 2.00 180.00 0.00 360.00
27 C3 Colour Pencil 20/- 1.00 145.00 0.00 145.00
Gross 17870.99
Balance Amt : 17871.00
Rounded Off 0.01
GRAND TOTAL 17871.00
Ph : 8553747352,0431-4000020
"""

    receipt = ReceiptData(
        vendor_name="Unknown",
        customer_name="Unknown",
        invoice_number="68104",
        invoice_date="19-04-2025",
        subtotal="17870.99",
        rounded_off="0.01",
        grand_total="17871.00",
        items=[
            ReceiptItem(page=1, sl_no="1", item_name="Nova Grip Jar", quantity=2.0, unit_price="200.00", total_price="400.00"),
            ReceiptItem(page=1, sl_no="7", item_name="Barfi Topper Jar", quantity=None, unit_price="2.00", total_price="360.00"),
            ReceiptItem(page=1, sl_no="27", item_name="C3 Colour Pencil", quantity=20.0, unit_price="7.25", total_price="145.00")
        ]
    )

    val_receipt, diag = validate_and_reconcile_receipt(receipt, raw_ocr)

    # 1. Seller & Buyer reconciled from OCR
    assert val_receipt.seller_name == "SSS STATIONERY"
    assert val_receipt.buyer_name == "Lucky Store"
    assert val_receipt.vendor_name == "SSS STATIONERY"
    assert val_receipt.customer_name == "Lucky Store"

    # 2. Item 7 quantity and rate fixed, and full product names retained from OCR
    assert val_receipt.items[0].item_name == "Nova Grip Jar Rs 7/-"
    assert val_receipt.items[1].quantity == 2.0
    assert val_receipt.items[1].unit_price == 180.0
    assert val_receipt.items[1].total_price == 360.0

    # 3. Item 27 quantity, rate, and name fixed
    assert val_receipt.items[2].item_name == "C3 Colour Pencil 20/-"
    assert val_receipt.items[2].quantity == 1.0
    assert val_receipt.items[2].unit_price == 145.0
    assert val_receipt.items[2].total_price == 145.0

    # 4. Formatted display has Seller and Buyer
    disp = format_receipt_display(val_receipt)
    assert "Seller : SSS STATIONERY" in disp
    assert "Buyer : Lucky Store" in disp
    assert "Seller : Unknown" not in disp
    assert "Buyer : Unknown" not in disp

    # 5. Null values preserved in JSON model dump (not removed)
    data_dict = val_receipt.model_dump()
    assert data_dict["buyer_name"] == "Lucky Store"
    assert data_dict["seller_name"] == "SSS STATIONERY"
    assert data_dict["buyer_address"] is None
    assert data_dict["seller_address"] is None
    assert data_dict["buyer_gstin"] is None


def test_ganapathy_electricals_exact_fields_and_no_discount_hallucination():
    sample_ocr = """
GANAPATHY ELECTRICALS Bill No Bill Date
97, KAMARAJ ROAD 12 01/04/2021
NEAR OLD BUS STAND 
TIRUPUR - 641604 Bill Type Despatch Through
Phone :0421-4325351 Credit Bill 12345
Mobile :7502 444 999 
ganapathielectricals@gmail.com P.O No & Date D.C.No & Date
GSTIN/UIN :33AACFG7274J1ZA 56789 546322
Buyer : MORNING STAAR APPARELS Transport
274/6,SASTHIRI NAGAR Extn., Sdsd
KPN COLONY (PO) NEAR G.H., 
DHARAPURAM ROAD
TIRUPUR - 641608 Mobile: E-Way Bill No : 123456 GSTIN/UIN :33AAIFM9340B1ZK State : TamilNadu ,Code :33
SNo Description Of Goods HSN/SAC GST% Qty Unit Rate Dis % Amount
1 11/2" CPVC (11-5M) (ASH) 39172390 5 2.00 % LTH 1513.00 3026.00
2 1" CPVC (11-5M) ASH 39172390 12 8.00 % LTH 623.66 4989.28
Total Items : 20 79.00 Total 19963.26
HSN/SAC Taxable SGST Tax CGST Tax Sub Total 19963.26
39172390 3026.00 2.50 75.65 2.50 75.65
Round Off -0.20
Amount Chargeable (in Words) NET TOTAL 22917.00
"""
    raw = ReceiptData(
        seller_name="GANAPATHY ELECTRICALS",
        seller_address="97, KAMARAJ ROAD, NEAR OLD BUS STAND, TIRUPUR - 641604",
        invoice_number="97",  # mistakenly set to door number
        transport="Transport",  # mistakenly set to header label
        items=[
            ReceiptItem(sl_no="1", item_name="11/2\" CPVC (11-5M) (ASH)", discount_percent="1513.00%", quantity=18.0, unit_price="168.11", total_price="3026.00"),
            ReceiptItem(sl_no="2", item_name="1\" CPVC (11-5M) ASH", discount_percent="623.66%", quantity=12.0, unit_price="415.77", total_price="4989.28")
        ]
    )

    val_receipt, _ = validate_and_reconcile_receipt(raw, sample_ocr)

    # 1. Invoice Number reconciled from '97' (door no) to '12' (bill no)
    assert val_receipt.invoice_number == "12"

    # 2. Transport extracted as 'Sdsd' (not 'Transport')
    assert val_receipt.transport == "Sdsd"

    # 3. Bill Type, Despatch Through, PO, DC, E-Way Bill extracted
    assert val_receipt.bill_type == "Credit Bill"
    assert val_receipt.despatch_through == "12345"
    assert val_receipt.po_number == "56789"
    assert val_receipt.dc_number == "546322"
    assert val_receipt.eway_bill_no == "123456"

    # 4. Total Items and Total Quantity
    assert val_receipt.total_items == 20
    assert val_receipt.total_quantity == 79.0

    # 5. Items have NO discount hallucination (1513.00% purged, actual rate and qty restored)
    assert val_receipt.items[0].discount_percent is None
    assert val_receipt.items[0].quantity == 2.0
    assert val_receipt.items[0].unit_price == 1513.00
    assert val_receipt.items[0].total_price == 3026.00

    assert val_receipt.items[1].discount_percent is None
    assert val_receipt.items[1].quantity == 8.0
    assert val_receipt.items[1].unit_price == 623.66
    assert val_receipt.items[1].total_price == 4989.28

    # 6. Formatted display checks
    disp = format_receipt_display(val_receipt)
    assert "Bill Type : Credit Bill" in disp
    assert "Invoice / Bill No : 12" in disp
    assert "Transport : Sdsd" in disp
    assert "Despatch Through : 12345" in disp
    assert "P.O No & Date : 56789" in disp
    assert "D.C.No & Date : 546322" in disp
    assert "E-Way Bill No : 123456" in disp
    assert "Total Items : 20" in disp
    assert "Total Qty : 79.0" in disp
    assert "Dis%:" not in disp  # Must NOT display Dis%: when discount is not present!


def test_stationery_gross_balance_amount_and_valid_discount():
    ocr_text = """
Gross 17870.99
Balance Amt : 17871.00
Rounded Off 0.01
GRAND TOTAL 17871.00
Ph : 8553747352,0431-4000020
"""
    raw = ReceiptData(
        currency="INR",
        seller_name="SSS STATIONERY",
        items=[
            ReceiptItem(sl_no="1", item_name="Stylish X3 Rs 7/-", quantity=2.0, unit_price="22.00", discount_percent="0.00%", total_price="44.01")
        ]
    )

    val_receipt, _ = validate_and_reconcile_receipt(raw, ocr_text)

    assert val_receipt.gross_amount == 17870.99
    assert val_receipt.balance_amount == 17871.00
    assert val_receipt.rounded_off == 0.01
    assert val_receipt.grand_total == 17871.00

    disp = format_receipt_display(val_receipt)
    assert "Gross : ₹17870.99" in disp
    assert "Balance Amt : ₹17871.00" in disp
    assert "Rounded Off : ₹0.01" in disp
    assert "Grand Total : ₹17871.00" in disp
    assert "Dis%: 0.00%" in disp


def test_stationery_phone_and_no_date_header_reconciliation():
    ocr_text = """
Estimate / Quotation
SSS STATIONERY
No : 68104 Date : 19-04-2025
Lucky Store Page No : 1
S.No Particulars Qty Rate Dis% Amount
1 Nova Grip Jar Rs 7/- 2.00 200.00 0.00 400.00
Gross 17870.99
Balance Amt : 17871.00
Rounded Off 0.01
GRAND TOTAL 17871.00
Ph : 8553747352,0431-4000020
"""
    raw = ReceiptData()
    val_receipt, _ = validate_and_reconcile_receipt(raw, ocr_text)
    assert val_receipt.seller == "SSS STATIONERY"
    assert val_receipt.buyer == "Lucky Store"
    assert val_receipt.invoice_number == "68104"
    assert val_receipt.invoice_date == "19-04-2025"
    assert val_receipt.seller_phone == "0431-4000020"
    assert val_receipt.seller_mobile == "8553747352"
    assert val_receipt.gross_amount == 17870.99
    assert val_receipt.balance_amount == 17871.00
    assert val_receipt.rounded_off == 0.01
    assert val_receipt.grand_total == 17871.00
    assert val_receipt.tax is None


def test_no_total_items_hallucination_and_strict_sequential_order():
    ocr_text = """
--- Page 1 ---
Estimate / Quotation
SSS STATIONERY
No : 68104 Date : 19-04-2025
Lucky Store Page No : 1
S.No Particulars Qty Rate Dis% Amount
1 Nova Grip Jar Rs 7/- 2.00 200.00 0.00 400.00
2 Reynold Brite Jar Rs 125/- (25pcs) 1.00 100.00 0.00 100.01

--- Page 2 ---
Lucky Store Page No : 2
S.No Particulars Qty Rate Dis% Amount
27 C3 Colour Pencil 20/- 1.00 145.00 0.00 145.00
28 Ko Colour Pencil 12s 80/- 2.00 58.00 0.00 115.99

--- Page 3 ---
Lucky Store Page No : 3
S.No Particulars Qty Rate Dis% Amount
53 Ry P.M Marker Rs 25/- 20.00 15.00 0.00 300.00
54 Luxor Permanent Marker Rs 20/- 10.00 12.50 0.00 124.99
Gross 17870.99
Balance Amt : 17871.00
Rounded Off 0.01
GRAND TOTAL 17871.00
Ph : 8553747352,0431-4000020
"""
    # Simulate LLM hallucinating total_items=26, total_quantity=136 and misassigning page 1
    raw = ReceiptData(
        total_items=26,
        total_quantity=136.0,
        items=[
            ReceiptItem(page=1, sl_no="1", item_name="Nova Grip Jar", quantity=2.0, unit_price="200.00", total_price="400.00"),
            ReceiptItem(page=1, sl_no="53", item_name="Ry P.M Marker", quantity=20.0, unit_price="15.00", total_price="300.00"),
            ReceiptItem(page=1, sl_no="27", item_name="C3 Colour Pencil", quantity=1.0, unit_price="145.00", total_price="145.00"),
        ]
    )

    val_receipt, _ = validate_and_reconcile_receipt(raw, ocr_text)

    # 1. Total items and total quantity must be None because not in OCR text
    assert val_receipt.total_items is None
    assert val_receipt.total_quantity is None

    # 2. All 6 items must be recovered and strictly ordered 1, 2, 27, 28, 53, 54
    sl_nos = [it.sl_no for it in val_receipt.items]
    assert sl_nos == ["1", "2", "27", "28", "53", "54"]

    # 3. Item physical pages must be accurately synchronized
    pages = [it.page for it in val_receipt.items]
    assert pages == [1, 1, 2, 2, 3, 3]

    disp = format_receipt_display(val_receipt)
    assert "Total Items" not in disp
    assert "Total Qty" not in disp


def test_fmcg_agency_wholesale_reconciliation_and_tax_matrix():
    ocr_sample = """
--- Page 1 ---
TAX INVOICE
BHAIRAVI AGENCY
1/404,Senguttai Thottam,Palladam
GSTIN : 33AAZFB9903G1Z3
To : Annai Store (Pdm) Bill No : 2594
Bill Dt : 07-07-2025
SNO HSN ITEM MRP UNIT TOT.PCS RATE BASIC AMT DIS % DIS AMT GST % GST Amt NETAMT
1 25010010 Tata Salt 1kgx25 Mrp.30 0 Bag 20 660.00 13200.00 0 0.00 0 0.00 13200.00
4 1513 VVD 1Ltr Pouch 900 Ml X20Pouch 0 Box 1 6857.14 6857.14 0 0.00 5 342.86 7200.00
5 1513 VVD 500ml Pouch 450ml X 40 0 Box 1 8380.95 8380.95 0 0.00 5 419.04 8799.99
11 19059040 POPULAR APPALAM RS ;10 0 Nos 80 8.00 640.00 0 0.00 0 0.00 640.00
12 POPULAR APPALAM RS ;10 0 Nos 8 FREE
--- Page 2 ---
TAX INVOICE
16 33074100 Zb Cup Sambrani Box 3 In 1 0 Nos 36 42.86 1542.96 0 0.00 5 77.14 1620.10
24 25010010 Tata Rock Salt 1kg 0 Box 1 1746.00 1746.00 0 0.00 0 0.00 1746.00
TOTAL 468 86740.55 3795.26 90535.81
TAX DETAILS : 
TAX % 2.5% 6% 9% 14% Round Off 0.19
CGST VALUE 1608.34 289.29
SGST VALUE 1608.34 289.29 NETT AMOUNT 90536.00
"""
    # Simulate LLM returning flawed subtotal=0.19, qty=0, rate=5.00, and omitted free item
    raw = ReceiptData(
        seller_name="BHAIRAVI AGENCY",
        buyer_name="Annai Store (Pdm)",
        invoice_number="2594",
        invoice_date="07-07-2025",
        currency="₹",
        subtotal="0.19",
        cgst="1897.63",
        cgst_rate="2.5%",
        sgst="1897.63",
        sgst_rate="2.5%",
        tax="3795.26",
        rounded_off="0.19",
        grand_total="90536.00",
        items=[
            ReceiptItem(page=1, sl_no="4", item_name="VVD 1Ltr Pouch", hsn_sac="1513", quantity=0.0, uom="Box", unit_price="5.00", total_price="7200.00")
        ]
    )

    val_receipt, _ = validate_and_reconcile_receipt(raw, ocr_sample)

    # 1. Subtotal must NOT be 0.19; must be authoritative 86740.55
    assert val_receipt.subtotal == 86740.55
    assert val_receipt.rounded_off == 0.19
    assert val_receipt.grand_total == 90536.00
    assert val_receipt.total_quantity == 468.0

    # 2. Tax reconciliation
    assert val_receipt.cgst == 1897.63
    assert val_receipt.sgst == 1897.63
    assert val_receipt.tax == 3795.26
    assert val_receipt.cgst_rate is None  # Multi-rate breakdown
    assert val_receipt.sgst_rate is None

    # 3. Tax summary matrix breakdown
    assert val_receipt.hsn_tax_summary is not None
    assert len(val_receipt.hsn_tax_summary) == 2
    assert val_receipt.hsn_tax_summary[0].cgst_rate == "2.5%"
    assert val_receipt.hsn_tax_summary[0].cgst_amount == 1608.34
    assert val_receipt.hsn_tax_summary[1].cgst_rate == "6%"
    assert val_receipt.hsn_tax_summary[1].cgst_amount == 289.29

    # 4. Item 4 corrected from qty 0 and rate 5.00
    it4 = next(it for it in val_receipt.items if it.sl_no == "4")
    assert it4.quantity == 1.0
    assert it4.uom == "Box"
    assert it4.unit_price == 6857.14
    assert it4.total_price == 7200.00

    # 5. Free item 12 recovered
    it12 = next(it for it in val_receipt.items if it.sl_no == "12")
    assert it12.quantity == 8.0
    assert it12.unit_price == 0.0
    assert it12.total_price == 0.0

    # 6. Formatted display checks
    disp = format_receipt_display(val_receipt)
    assert "Subtotal : ₹86740.55" in disp
    assert "Total Qty : 468.0" in disp
    assert "Round Off : ₹0.19" in disp
    assert "Grand Total : ₹90536.00" in disp
    assert "Rate : 2.5%" in disp
    assert "Rate : 6%" in disp


def test_stationery_full_product_name_preservation():
    ocr_text = """
Estimate / Quotation
SSS STATIONERY
No : 68104 Date : 21-05-2025
Lucky Store Page No : 1
S.No Particulars Qty Rate Dis% Amount
1 Nova Grip Jar Rs 7/- 2.00 200.00 0.00 400.00
2 Reynold Brite Jar Rs 125/- (25pcs) 1.00 100.00 0.00 100.01
3 Stylish X3 Jar 75pcs Rs 7/- 1.00 360.00 0.00 360.00
4 Paras 6G 50p Jar 5/- 1.00 125.00 0.00 125.00
5 Snappy Jar Rs 7/- 1.00 108.00 0.00 108.01
6 Reynods Pen Rs 10/- 1.00 300.00 0.00 300.00
7 Barfi Topper Jar 2.00 180.00 0.00 360.00
8 Nataraj Eraser Jar Rs 1/- 1.00 80.00 0.00 79.99
9 Fevigum 18ml Jar (25pcs) Rs 5/- 3.00 105.00 0.00 315.01
10 Camlin Water Colour Rs 30/- 20.00 22.00 0.00 440.00
11 Cam Water Colour Rs 20/- 20.00 15.00 0.00 300.00
12 Cam Water Colour Rs 60/- 5.00 47.00 0.00 235.00
13 Cam Water Colour Rs 70/- 3.00 55.00 0.00 164.99
14 Camlin Water Colour Rs 35/- 5.00 26.00 0.00 130.01
15 Camlin WaterColour 24's Rs 110/- 1.00 88.00 0.00 88.00
16 Apsara Platinum Kit Rs 25/- 20.00 19.00 0.00 380.00
17 FlexKwik Rs 60/- 10.00 45.50 0.00 454.99
18 743 Anabond Rs 75/- 10.00 29.50 0.00 295.00
19 Nataraj Colour Pencil Rs 30/- 20.00 22.00 0.00 440.00
20 Ko Colour Pencil 12s 25/- 20.00 17.50 0.00 350.00
21 Ko Colourpencil 10s 15/- 20.00 105.00 0.00 2100.00
22 C3 Color Pencil Rs 40/- 10.00 28.00 0.00 280.01
23 Ko Crayons 13s 35/- 10.00 26.00 0.00 260.00
24 Kores Crayons Rs 15/- 30.00 10.50 0.00 315.01
25 Ko Oil Pastel 12s 50/- 10.00 35.00 0.00 350.00
26 C3 10-Colour Pencil Rs 12/- 3.00 80.00 0.00 240.00
Gross 8738.00
"""
    # Simulate LLM stripping packaging labels like 'Rs 7/-' or '(25pcs)'
    raw = ReceiptData(
        seller_name="SSS STATIONERY",
        buyer_name="Lucky Store",
        items=[
            ReceiptItem(page=1, sl_no="1", item_name="Nova Grip Jar", quantity=2.0, unit_price="200.00", total_price="400.00"),
            ReceiptItem(page=1, sl_no="2", item_name="Reynold Brite Jar", quantity=1.0, unit_price="100.00", total_price="100.01"),
            ReceiptItem(page=1, sl_no="11", item_name="Cam Water Colour", quantity=20.0, unit_price="15.00", total_price="300.00"),
            ReceiptItem(page=1, sl_no="12", item_name="Cam Water Colour", quantity=5.0, unit_price="47.00", total_price="235.00"),
            ReceiptItem(page=1, sl_no="13", item_name="Cam Water Colour", quantity=3.0, unit_price="55.00", total_price="164.99"),
        ]
    )

    val_receipt, _ = validate_and_reconcile_receipt(raw, ocr_text)

    # All 26 items must be present
    assert len(val_receipt.items) == 26

    # Packaging labels must be preserved in full
    items_by_sl = {it.sl_no: it.item_name for it in val_receipt.items}
    assert items_by_sl["1"] == "Nova Grip Jar Rs 7/-"
    assert items_by_sl["2"] == "Reynold Brite Jar Rs 125/- (25pcs)"
    assert items_by_sl["3"] == "Stylish X3 Jar 75pcs Rs 7/-"
    assert items_by_sl["4"] == "Paras 6G 50p Jar 5/-"
    assert items_by_sl["10"] == "Camlin Water Colour Rs 30/-"
    assert items_by_sl["11"] == "Cam Water Colour Rs 20/-"
    assert items_by_sl["12"] == "Cam Water Colour Rs 60/-"
    assert items_by_sl["13"] == "Cam Water Colour Rs 70/-"
    assert items_by_sl["15"] == "Camlin WaterColour 24's Rs 110/-"
    assert items_by_sl["16"] == "Apsara Platinum Kit Rs 25/-"
    assert items_by_sl["20"] == "Ko Colour Pencil 12s 25/-"
    assert items_by_sl["24"] == "Kores Crayons Rs 15/-"
    assert items_by_sl["26"] == "C3 10-Colour Pencil Rs 12/-"








