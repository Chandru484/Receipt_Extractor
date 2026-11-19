from typing import Any, Dict, List


def build_extraction_messages(ocr_result: Dict[str, Any]) -> List[Dict[str, str]]:
    """Build a compact, highly effective prompt for Groq receipt understanding and extraction."""
    ocr_text = ocr_result.get("full_text", "")

    system_prompt = """You are an expert document extraction system. Extract ALL available information from the receipt/invoice OCR text into a single JSON object.

EXTRACTION SCHEMA & FIELDS:
{
  "document_type": "invoice" or "receipt",

  "seller_name": "Business / Shop / Vendor name from header (e.g. store or company name)",
  "seller_address": "Full address of seller/vendor",
  "seller_gstin": "Seller's 15-character GSTIN/Tax ID in CAPITAL LETTERS ONLY",
  "seller_state": "Seller State name",
  "seller_state_code": "Seller State code (e.g. '33')",
  "seller_email": "Seller email if present",
  "seller_phone": "Seller phone / mobile if present",

  "buyer_name": "Buyer / Customer / Bill To name",
  "buyer_address": "Full multi-line address of buyer",
  "buyer_address_line_1": "Primary line of buyer address (building / premises / plot / street)",
  "buyer_address_line_2": "Secondary line of buyer address (floor / suite / road / area / locality)",
  "buyer_gstin": "Buyer's 15-character GSTIN/Tax ID in CAPITAL LETTERS ONLY",
  "buyer_state": "Buyer State name",
  "buyer_state_code": "Buyer State code",
  "buyer_phone": "Buyer mobile / phone number (10-digit number)",
  "buyer_email": "Buyer email if present",

  "invoice_number": "Invoice No / Bill No / ST.No / Cash Memo No",
  "invoice_date": "Date in YYYY-MM-DD format",
  "payment_mode": "Payment mode / terms (e.g. 'Cash', 'G Pay', 'UPI', 'Credit', 'Card')",
  "salesman": "Salesman / executive name if listed",

  "subtotal": 100.00,
  "cgst": 9.00,
  "cgst_rate": "9%",
  "sgst": 9.00,
  "sgst_rate": "9%",
  "igst": null,
  "igst_rate": null,
  "rounding_off": 0.00,
  "tax": 18.00,
  "grand_total": 118.00,
  "amount_in_words": "Amount in words if present",
  "currency": "INR",

  "bank_details": {
    "bank_name": "Bank Name if present on the document",
    "account_holder": "Account Holder Name",
    "account_no": "Clean bank account number (digits only)",
    "ifsc_code": "11-character alphanumeric IFS Code in CAPITAL LETTERS ONLY",
    "branch": "Branch name"
  },

  "extra_fields": {
    "company_pan": "10-character alphanumeric PAN if present on invoice (e.g. Company's PAN)"
  },

  "items": [
    {
      "sl_no": "1",
      "item_name": "Full product description or item name",
      "hsn_sac": "HSN/SAC code if present",
      "quantity": 1.0,
      "uom": "Unit of measure (e.g. 'No', 'nos', 'kg', 'pcs')",
      "unit_price": 100.00,
      "rate_incl_tax": 118.00,
      "gst_rate": "18%",
      "total_price": 100.00
    }
  ]
}

CRITICAL UNIVERSAL EXTRACTION RULES:
1. UNIVERSAL TAX ID / GSTIN, PHONE & BUYER RULES:
   - "CASH BILL", "CASH", "BILL", "TAX INVOICE", "CASH MEMO", "ESTIMATE" are BILL TITLES or PAYMENT MODES, NEVER a buyer_name or seller_name!
   - If 'Buyer' has a customer name (e.g. 'TEKIS'), extract that name into 'buyer_name'. NEVER set buyer_name to 'CASH BILL'.
   - 'buyer_phone': Look for 'Mobile No', 'Mob', 'Phone' in the Buyer section (e.g. 'Mobile No : 9087043339') and extract it into 'buyer_phone'.
   - An Indian GSTIN MUST be strictly 15 alphanumeric characters in CAPITAL LETTERS ONLY.
   - A 10-digit number (e.g. 10 digits starting with 6, 7, 8, or 9) is ALWAYS a PHONE / MOBILE NUMBER, NEVER a GSTIN. Put it in seller_phone or buyer_phone.
   - Never confuse a phone number with a GSTIN.
2. UNIVERSAL BUYER & SELLER ADDRESS DECOMPOSITION:
   - Capture the complete multi-line address in 'buyer_address' or 'seller_address'.
   - Extract 'buyer_address_line_1' as the primary building/complex/street name.
   - Extract 'buyer_address_line_2' as the secondary floor/street/area/locality name.
3. FINANCIAL TOTALS & TAX BREAKDOWN (GENERATE BEFORE ITEMS):
   - Always extract subtotal, cgst, sgst, tax, grand_total, and amount_in_words.
   - Map CGST, SGST, and IGST components and their percentage rates with '%' (e.g. '9%', '14%', '18%').
   - subtotal + tax = grand_total.
4. UNIVERSAL BANK DETAILS EXTRACTION:
   - 'account_no': Extract the clean bank account number (9 to 18 digits).
   - 'ifsc_code': Must be strictly 11 alphanumeric characters in CAPITAL LETTERS ONLY. 5th character is always digit 0.
5. EXTRA FIELDS:
   - If 'Company's PAN' or 'PAN' is present (e.g. 'Company's PAN : AABFE3454B'), extract it into extra_fields: {"company_pan": "..."}.
6. COMPLETE & ACCURATE ITEM EXTRACTION:
   - Extract EVERY SINGLE product/line item listed in the table (do NOT omit or truncate any item). If there are 4 items (SL No 1, 2, 3, 4), extract all 4 items!
   - For every item, correlate SL No, Item Name, HSN/SAC, Quantity, Unit Price / Rate, Rate (Incl. of Tax), GST Rate, and Total Price / Amount from its table row.
   - Total price for each item must match: total_price = quantity * unit_price (e.g. 2 * 33.90 = 67.80). Never assign rates or amounts from one row to a different row!
7. UNDEFINED SELLER OR BUYER:
   - If the receipt does not define or specify a seller/vendor/store name (e.g. simple cash memos or slips without a store header), set 'seller_name' to "Unknown".
   - If it does not define or specify a buyer/customer name, set 'buyer_name' to "Unknown".
8. Return valid JSON only. No markdown fences, no explanatory text."""

    user_prompt = f"""Extract all receipt and party details from this OCR text:

\"\"\"
{ocr_text}
\"\"\""""

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ]
