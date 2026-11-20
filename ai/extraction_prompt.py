from typing import Any, Dict, List


def build_extraction_messages(ocr_result: Dict[str, Any]) -> List[Dict[str, str]]:
    """Build a compact, highly effective prompt for Groq receipt understanding and extraction."""
    ocr_text = ocr_result.get("full_text", "")

    system_prompt = """You are an expert document extraction system. Extract ALL available information from the receipt/invoice OCR text into a single JSON object.

STANDARD FIELDS TO EXTRACT:
{
  "document_type": "invoice" or "receipt",

  "seller_name": "Business / Shop / Vendor name from header",
  "seller_address": "Full address of seller/vendor (e.g. 'ADD1, ADD2, ADD3, ADD4')",
  "seller_address_line_1": "Primary line of seller address (e.g. 'ADD1')",
  "seller_address_line_2": "Secondary line of seller address (e.g. 'ADD2, ADD3, ADD4')",
  "seller_gstin": "Seller's 15-character GSTIN/Tax ID in CAPITAL LETTERS ONLY",
  "seller_state": "Seller State name",
  "seller_state_code": "Seller State code (e.g. '33')",
  "seller_email": "Seller email if present",
  "seller_phone": "Seller phone / landline if present (e.g. '0421-4325351')",
  "seller_mobile": "Seller mobile number if present (e.g. '7502 444 999')",
  "phone": "Seller phone / landline",
  "mobile": "Seller mobile number",

  "buyer_name": "Buyer / Customer / Bill To name",
  "buyer_address": "Full address of buyer (e.g. 'ADD2, ADD3' or Street/City/Pincode - NEVER include Transport)",
  "buyer_address_line_1": "Primary line of buyer address (e.g. 'ADD2')",
  "buyer_address_line_2": "Secondary line of buyer address (e.g. 'ADD3')",
  "buyer_gstin": "Buyer's 15-character GSTIN/Tax ID in CAPITAL LETTERS ONLY",
  "buyer_state": "Buyer State name",
  "buyer_state_code": "Buyer State code",
  "buyer_phone": "Buyer phone / landline if present",
  "buyer_mobile": "Buyer mobile number if present (e.g. '9894195959')",
  "buyer_email": "Buyer email if present",

  "transport": "Transport company / carrier if present (e.g. 'Sdsd')",
  "despatch_through": "Despatch through if present (e.g. '12345')",
  "eway_bill_no": "E-Way bill number if present (e.g. '123456')",
  "po_number": "PO number if present (e.g. '56789')",
  "dc_number": "DC / Delivery Challan number if present (e.g. '546322')",

  "invoice_number": "Invoice No / Bill No / ST.No / Cash Memo No",
  "receipt_number": "Receipt Number (e.g. '123')",
  "invoice_date": "Date in DD-MM-YYYY format (e.g. '01-01-2023')",
  "date_paid": "Date paid in DD-MM-YYYY format",
  "payment_mode": "Payment mode / method (e.g. 'Cash', 'ACH', 'UPI', 'Credit Card')",
  "salesman": "Salesman / executive name if listed",

  "subtotal": "$19.00",
  "cgst": null,
  "cgst_rate": null,
  "sgst": null,
  "sgst_rate": null,
  "igst": null,
  "igst_rate": null,
  "rounding_off": "$0.00",
  "tax": "$1.12",
  "grand_total": "$20.12",
  "amount_paid": "$20.12",
  "refunded_amount": "$5.00",
  "refunded_on": "2026-09-21",
  "amount_in_words": "Amount in words if present",
  "currency": "USD",

  "bank_details": {
    "bank_name": "Bank Name if present (e.g. 'ANZ Bank', 'Axis Bank')",
    "account_holder": "Account Holder Name",
    "account_no": "Account Number (e.g. '1234 1234' from 'ACC # 1234 1234' or '924030030073241')",
    "ifsc_code": "11-character IFS Code in CAPITAL LETTERS ONLY (e.g. 'UTIB0000118')",
    "branch": "Branch name"
  },

  "items": [
    {
      "page": 1,
      "sl_no": "1",
      "item_name": "Full product description or item name",
      "hsn_sac": "HSN/SAC code if present",
      "quantity": 1.0,
      "uom": "Unit of measure",
      "unit_price": "₹19.00",
      "rate_incl_tax": "₹20.12",
      "discount_percent": "Discount percentage if present in table (e.g. '0.00%', '5%')",
      "gst_rate": null,
      "total_price": "₹19.00"
    }
  ],

  "extra_fields": {
    "<<custom_field_label>>": "<<value>>"
  }
}

CRITICAL RULES:
1. BILL TITLES: "CASH BILL", "CASH", "BILL", "TAX INVOICE", "CASH MEMO", "ESTIMATE" are DOCUMENT TITLES, NOT buyer/seller names.
2. "BILL TO" SECTION IS ALWAYS THE BUYER:
   - "Bill To" or "Billed To" or "Customer" or "Sold To" ALWAYS designates the BUYER / CUSTOMER.
   - Any name, address, and email under "Bill To" belong to the BUYER.
     Example:
       Bill To
       Customer
       Address
       City, State Zipcode
       customer@example.org
     -> buyer_name: "Customer", buyer_address: "Address, City, State Zipcode", buyer_email: "customer@example.org".
   - The company / merchant issuing the bill (e.g. "Example, LLC" or "A GO RAILS", with contact email "support@example.com", phone "(555) 867-5309", address "123 Fake Street, New York City, NY 10012") is the SELLER / VENDOR.
   - NEVER invert Seller and Buyer!
   - NEVER use the word "Zipcode", "State", or "City" as a state name! State names must be actual states (e.g. "NY", "New York", "California").
3. PHONE AND MOBILE SEPARATION (SELLER vs BUYER):
   - A phone or mobile number listed under "Buyer" or "Bill To" (e.g. under "Buyer (Bill To)", or near "Contact Person: SURESH") belongs EXCLUSIVELY to the Buyer ("buyer_phone" or "buyer_mobile")!
   - NEVER copy or assign the Buyer's contact / mobile number to the Seller ("seller_phone", "seller_mobile", or "phone")!
   - If the Seller section has an empty "Contact :" or no phone number, leave "seller_phone", "seller_mobile", and "phone" as null!
   - If a party lists both "Phone" (landline) and "Mobile", extract them into separate fields ("phone"/"seller_phone" and "mobile"/"seller_mobile").
4. ADDRESS LINES (INCLUDING SAMPLE / PLACEHOLDER LABELS LIKE ADD1, ADD2, ADD3, ADD4):
   - Any address lines under the Seller header (e.g. "ADD1", "ADD2", "ADD3", "ADD4") are the SELLER ADDRESS! Extract:
     "seller_address": "ADD1, ADD2, ADD3, ADD4",
     "seller_address_line_1": "ADD1",
     "seller_address_line_2": "ADD2, ADD3, ADD4"
   - Any address lines under the Buyer / Bill To header (e.g. "ADD2", "ADD3") are the BUYER ADDRESS! Extract:
     "buyer_address": "ADD2, ADD3",
     "buyer_address_line_1": "ADD2",
     "buyer_address_line_2": "ADD3"
   - NEVER omit or discard address lines just because they say "ADD1", "ADD2", etc. Always capture them as address lines!
5. TWO-COLUMN INVOICE HEADERS & BUYER ADDRESS CLEANING:
   - Invoices often have two-column headers where Buyer details are on the left, and Transport/Shipping fields (such as "Transport", "Despatch Through", "E-Way Bill No", "Vehicle No") are on the right.
   - OCR often concatenates left and right columns horizontally (e.g. "274/6,SASTHIRI NAGAR Extn., Sdsd").
   - The Buyer Address MUST ONLY contain genuine address text (e.g. "274/6,SASTHIRI NAGAR Extn., KPN COLONY (PO) NEAR G.H., DHARAPURAM ROAD, TIRUPUR - 641608").
   - NEVER leak or include transport names (e.g. "Sdsd"), transport labels, vehicle numbers, or dispatch details into buyer_address or buyer_address_line_1!
   - Put transport into the "transport" field (e.g. "transport": "Sdsd").
6. DO NOT PUT STANDARD VALUES IN EXTRA_FIELDS:
   - If a field is clearly a standard field (receipt_number, invoice_number, invoice_date, date_paid, amount_paid, refunded_amount, refunded_on, seller_email, buyer_email, seller_phone, seller_mobile, phone, mobile, buyer_phone, buyer_mobile, transport, despatch_through, eway_bill_no, etc.), put it in its respective top-level standard field!
   - DO NOT duplicate standard fields into extra_fields!
   - Only place truly unmapped custom fields in extra_fields (e.g. customer_id, order_id, transaction_id, tracking_no, reference_no, etc.).
7. CURRENCY & FINANCIAL PRECISION:
   - All financial amounts ('subtotal', 'tax', 'grand_total', 'amount_paid', 'refunded_amount', 'unit_price', 'rate_incl_tax', 'total_price') must include the currency symbol (e.g. '$', '₹', '€', '£') and exactly two decimal places (e.g. '$93.50', '$85.00', '$8.50', never '93.5' or 93.5).
   - "Total Due" or "Balance Due" or "Amount Due" corresponds to "grand_total".
8. BANK DETAILS (INTERNATIONAL & DOMESTIC):
   - Always extract bank name (e.g. "ANZ Bank"), account number (e.g. "1234 1234" from "ACC # 1234 1234"), and BSB number (e.g. "4321 432" from "BSB # 4321 432") into the "bank_details" object.
   - For account numbers like "ACC # 1234 1234" or "ACC #12341234", strip the "ACC #" prefix and keep the digits/spacing (e.g. "1234 1234" or "12341234").
   - For BSB numbers like "BSB # 4321 432" or "BSB#4321432", strip the "BSB #" prefix and keep the code (e.g. "4321 432").
9. PHONE vs GSTIN: A 10-digit Indian number starting with 6-9 is ALWAYS a phone, never a GSTIN.
10. GSTIN: Must be exactly 15 alphanumeric characters, all CAPITALS.
11. DATES: Always output in DD-MM-YYYY format (e.g. '01-01-2023', '21-09-2026', '01-04-2021'). Never output YYYY-MM-DD.
12. MULTI-PAGE & COMPLETE ITEM EXTRACTION:
   - The document may span multiple pages marked with '--- Page 1 ---', '--- Page 2 ---', etc.
   - You MUST extract EVERY SINGLE product / line item from ALL pages without omitting, grouping, or truncating any rows.
   - Tag each item with its 1-indexed integer 'page' number (e.g. 1, 2) indicating which page it appears on (based on the '--- Page N ---' section). If single page, set 'page': 1.
   - NEVER stop early (e.g. after 10 items). If an invoice has 20, 30, or more items across page 1 and page 2, extract ALL of them (e.g. items 1 to 20).
13. DISCOUNT PERCENTAGE (Dis%):
   - If the items table contains a "Dis%" or "Dis %" or "Discount %" or "Disc %" column, extract the discount percentage into "discount_percent" for each line item (e.g. "0.00%", "5.00%", "10%").
   - Do NOT omit the discount column if it is present in the table.
14. UNIFIED CURRENCY ACROSS MULTI-PAGE DOCUMENTS:
   - If the document is in Indian Rupees (INR / ₹ / Rs), ALL monetary amounts and rates across ALL pages (Page 1, Page 2, Page 3, etc.) must use the "₹" symbol (e.g. "₹145.00", NOT "$145.00")!
15. MISSING FIELDS & NULLS:
   - If a field is not present in the document, set it to null. Do NOT invent or hallucinate values.
16. SELLER UNDEFINED: If no seller/vendor name exists, set seller_name to "Unknown".
17. Return valid JSON only. No markdown fences, no explanatory text."""

    user_prompt = f"""Extract all receipt and party details from this OCR text:

\"\"\"
{ocr_text}
\"\"\"

Remember:
- Dates MUST ALWAYS be in DD-MM-YYYY format (e.g. '01-01-2023').
- Capture sample address lines like 'ADD1', 'ADD2', 'ADD3', 'ADD4' under seller and buyer addresses.
- Buyer's contact number (e.g. near 'Contact Person') belongs to BUYER ('buyer_mobile' / 'buyer_phone'), NEVER to the seller!
- If Seller has no phone number, leave seller_phone as null.
- Extract EVERY SINGLE line item across ALL pages without stopping or truncating (set "page" to the integer page number where each item appears).
- 'Bill To' designates the BUYER details (buyer_name, buyer_address, buyer_email).
- Financial fields must have currency symbol and two decimal places (e.g. '$93.50').
- Extract bank details (bank name, ACC #, BSB #) into bank_details.
- Put standard fields directly into their respective top-level fields — do NOT put them in extra_fields!"""

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ]

