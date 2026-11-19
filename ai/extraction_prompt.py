from typing import Any, Dict, List


def build_extraction_messages(ocr_result: Dict[str, Any]) -> List[Dict[str, str]]:
    """Build a compact, highly effective prompt for Groq receipt understanding and extraction."""
    ocr_text = ocr_result.get("full_text", "")

    system_prompt = """You are an expert document extraction system. Extract ALL available information from the receipt/invoice OCR text into a single JSON object.

STANDARD FIELDS TO EXTRACT:
{
  "document_type": "invoice" or "receipt",

  "seller_name": "Business / Shop / Vendor name from header",
  "seller_address": "Full address of seller/vendor",
  "seller_gstin": "Seller's 15-character GSTIN/Tax ID in CAPITAL LETTERS ONLY",
  "seller_state": "Seller State name",
  "seller_state_code": "Seller State code (e.g. '33')",
  "seller_email": "Seller email if present",
  "seller_phone": "Seller phone / mobile if present",

  "buyer_name": "Buyer / Customer / Bill To name",
  "buyer_address": "Full multi-line address of buyer",
  "buyer_address_line_1": "Primary line of buyer address",
  "buyer_address_line_2": "Secondary line of buyer address",
  "buyer_gstin": "Buyer's 15-character GSTIN/Tax ID in CAPITAL LETTERS ONLY",
  "buyer_state": "Buyer State name",
  "buyer_state_code": "Buyer State code",
  "buyer_phone": "Buyer mobile / phone number",
  "buyer_email": "Buyer email if present",

  "invoice_number": "Invoice No / Bill No / ST.No / Cash Memo No",
  "receipt_number": "Receipt Number (e.g. '123')",
  "invoice_date": "Date in YYYY-MM-DD format",
  "date_paid": "Date paid in YYYY-MM-DD format",
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
    "bsb_number": "BSB Number if present (e.g. '4321 432' from 'BSB # 4321 432')",
    "ifsc_code": "11-character IFS Code in CAPITAL LETTERS ONLY (e.g. 'UTIB0000118')",
    "swift_code": "SWIFT / BIC code if present",
    "branch": "Branch name"
  },

  "items": [
    {
      "sl_no": "1",
      "item_name": "Full product description or item name",
      "hsn_sac": "HSN/SAC code if present",
      "quantity": 1.0,
      "uom": "Unit of measure",
      "unit_price": "$19.00",
      "rate_incl_tax": "$20.12",
      "gst_rate": null,
      "total_price": "$19.00"
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
3. DO NOT PUT STANDARD VALUES IN EXTRA_FIELDS:
   - If a field is clearly a standard field (receipt_number, invoice_number, invoice_date, date_paid, amount_paid, refunded_amount, refunded_on, seller_email, buyer_email, seller_phone, buyer_phone, etc.), put it in its respective top-level standard field!
   - DO NOT duplicate standard fields into extra_fields!
   - Only place truly unmapped custom fields in extra_fields (e.g. customer_id, order_id, transaction_id, tracking_no, reference_no, etc.).
4. CURRENCY & FINANCIAL PRECISION:
   - All financial amounts ('subtotal', 'tax', 'grand_total', 'amount_paid', 'refunded_amount', 'unit_price', 'rate_incl_tax', 'total_price') must include the currency symbol (e.g. '$', '₹', '€', '£') and exactly two decimal places (e.g. '$93.50', '$85.00', '$8.50', never '93.5' or 93.5).
   - "Total Due" or "Balance Due" or "Amount Due" corresponds to "grand_total".
5. BANK DETAILS (INTERNATIONAL & DOMESTIC):
   - Always extract bank name (e.g. "ANZ Bank"), account number (e.g. "1234 1234" from "ACC # 1234 1234"), and BSB number (e.g. "4321 432" from "BSB # 4321 432") into the "bank_details" object.
   - For account numbers like "ACC # 1234 1234" or "ACC #12341234", strip the "ACC #" prefix and keep the digits/spacing (e.g. "1234 1234" or "12341234").
   - For BSB numbers like "BSB # 4321 432" or "BSB#4321432", strip the "BSB #" prefix and keep the code (e.g. "4321 432").
6. PHONE vs GSTIN: A 10-digit Indian number starting with 6-9 is ALWAYS a phone, never a GSTIN.
7. GSTIN: Must be exactly 15 alphanumeric characters, all CAPITALS.
8. DATES: Always output as YYYY-MM-DD.
9. ITEMS: Extract EVERY single line item. Never omit or truncate items.
10. SELLER UNDEFINED: If no seller/vendor name exists, set seller_name to "Unknown".
11. Return valid JSON only. No markdown fences, no explanatory text."""

    user_prompt = f"""Extract all receipt and party details from this OCR text:

\"\"\"
{ocr_text}
\"\"\"

Remember:
- 'Bill To' designates the BUYER details (buyer_name, buyer_address, buyer_email).
- Financial fields must have currency symbol and two decimal places (e.g. '$93.50').
- Extract bank details (bank name, ACC #, BSB #) into bank_details.
- The issuing merchant/company is the SELLER (seller_name, seller_address, seller_phone, seller_email).
- Put standard fields (receipt_number, date_paid, amount_paid, refunded_amount, refunded_on) directly into their respective top-level fields — do NOT put them in extra_fields!
- Only put new/custom fields not covered in the standard schema into extra_fields."""

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ]

