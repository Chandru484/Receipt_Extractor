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

  "hsn_tax_summary": [
    {
      "hsn_sac": "39172390",
      "taxable_value": "₹3026.00",
      "cgst_rate": "2.5%",
      "cgst_amount": "₹75.65",
      "sgst_rate": "2.5%",
      "sgst_amount": "₹75.65",
      "igst_rate": null,
      "igst_amount": null,
      "total_tax_amount": "₹151.30"
    }
  ],

  "extra_fields": {
    "<<custom_field_label>>": "<<value>>"
  }
}

CRITICAL RULES:
1. SELLER / VENDOR IDENTIFICATION:
   - The prominent business, store, or company name in the top header (e.g. "SSS STATIONERY") is the SELLER / VENDOR ("seller_name" / "vendor_name").
   - Document titles like "Estimate / Quotation", "Tax Invoice", "Cash Bill", "Cash Memo", "Estimate", "Quotation" are document types, NOT the seller name.
   - NEVER set seller_name to "Unknown" if a store or business name is present in the top header!
2. BUYER / CUSTOMER IDENTIFICATION:
   - "Bill To" or "Billed To" or "Customer" or "Sold To" or "Buyer" ALWAYS designates the BUYER / CUSTOMER.
   - In invoices without an explicit "Bill To" label, any secondary customer/party name listed before "Page No" or under the invoice number / date (e.g. "Lucky Store" from "Lucky Store Page No : 1") is the BUYER / CUSTOMER ("buyer_name" / "customer_name"). Strip "Page No : X" from the name.
   - NEVER invert Seller and Buyer!
3. PHONE AND MOBILE SEPARATION (SELLER vs BUYER):
   - Contact numbers listed under "Buyer" or "Bill To" belong EXCLUSIVELY to the Buyer ("buyer_phone" or "buyer_mobile")!
   - Contact numbers listed on seller header or invoice footer (e.g. "Ph : 8553747352,0431-4000020") belong to the issuing SELLER (landline "0431-4000020" to "seller_phone"/"phone", mobile "8553747352" to "seller_mobile"/"mobile").
   - If the Seller section has no phone number, leave "seller_phone", "seller_mobile", and "phone" as null.
   - If a party lists both "Phone" (landline) and "Mobile", extract them into separate fields ("phone"/"seller_phone" and "mobile"/"seller_mobile").
4. ADDRESS LINES (INCLUDING SAMPLE / PLACEHOLDER LABELS LIKE ADD1, ADD2, ADD3, ADD4):
   - Address lines under Seller header (e.g. "ADD1", "ADD2", "ADD3", "ADD4") are SELLER ADDRESS.
   - Address lines under Buyer header (e.g. "ADD2", "ADD3") are BUYER ADDRESS.
5. TWO-COLUMN INVOICE HEADERS & BUYER ADDRESS CLEANING:
   - NEVER leak transport names (e.g. "Sdsd"), vehicle numbers, or dispatch details into buyer_address.
   - Put transport into the "transport" field.
6. DO NOT PUT STANDARD VALUES IN EXTRA_FIELDS:
   - Standard fields must go into their respective top-level standard fields.
7. CURRENCY & FINANCIAL PRECISION:
   - All financial amounts must include currency symbol (e.g. '$', '₹') and two decimal places (e.g. '₹93.50').
   - In Indian invoices, ALL monetary amounts across all pages must use '₹'.
8. BANK DETAILS:
   - Extract bank name, account number, IFSC code, branch, or BSB number into "bank_details".
9. PHONE vs GSTIN: 10-digit Indian numbers starting with 6-9 are phones, never GSTINs.
10. GSTIN: Must be exactly 15 alphanumeric characters, all CAPITALS.
11. DATES: Always output in DD-MM-YYYY format (e.g. '01-01-2023', '01-04-2021'). Never output YYYY-MM-DD.
12. MULTI-PAGE & COMPLETE ITEM EXTRACTION:
   - Extract EVERY SINGLE product / line item from ALL pages without omitting or truncating any rows.
   - Items immediately preceding "Continue..." or page boundaries (e.g. items 16, 17) MUST NOT be skipped.
   - In stationery/retail tables with product package labels like "Rs 20/-", "80/-", "120/-" in product names, extract the actual table columns: Qty is the quantity column, Rate is the rate column.
   - Tag each item with its 1-indexed integer 'page' number (e.g. 1, 2).
13. DISCOUNT PERCENTAGE (Dis%):
   - If present in the table, extract into "discount_percent" for each line item (e.g. "0.00%", "5%").
14. HSN/SAC TAX SUMMARY TABLE & COMBINED TOTALS:
   - When an HSN/SAC tax breakdown table is present at the end, extract each combination row into "hsn_tax_summary".
   - Top-level "cgst" and "sgst" must be the TOTAL CGST and TOTAL SGST amounts (from the Total row of the tax table or sum of all rates), NOT an individual rate row!
   - "tax" must be the total tax (Total CGST + Total SGST + Total IGST).
   - "subtotal" is the total taxable amount (e.g. '₹19963.26').
   - "rounding_off" is the round off amount (e.g. '₹-0.20').
   - "grand_total" is the net final payable amount (e.g. '₹22917.00').
15. MISSING FIELDS AS NULL:
   - If a field is not present in the document (such as buyer_address, seller_address, gstin, etc.), specify it as null in the JSON. Do NOT omit missing fields.
16. Return valid JSON only. No markdown fences, no explanatory text."""

    user_prompt = f"""Extract all receipt and party details from this OCR text:

\"\"\"
{ocr_text}
\"\"\"

Produce the valid JSON object adhering strictly to the schema and rules."""

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ]

