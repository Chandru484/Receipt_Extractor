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

  "invoice_number": "Invoice No / Bill No / Receipt Number / ST.No / Cash Memo No",
  "invoice_date": "Date in YYYY-MM-DD format",
  "payment_mode": "Payment mode / terms (e.g. 'Cash', 'ACH', 'UPI', 'Credit', 'Card')",
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
    "bank_name": "Bank Name if present",
    "account_holder": "Account Holder Name",
    "account_no": "Clean bank account number (digits only)",
    "ifsc_code": "11-character IFS Code in CAPITAL LETTERS ONLY",
    "branch": "Branch name"
  },

  "items": [
    {
      "sl_no": "1",
      "item_name": "Full product description or item name",
      "hsn_sac": "HSN/SAC code if present",
      "quantity": 1.0,
      "uom": "Unit of measure",
      "unit_price": 100.00,
      "rate_incl_tax": 118.00,
      "gst_rate": "18%",
      "total_price": 100.00
    }
  ],

  "extra_fields": {
    "<<any_field_label_from_document>>": "<<its value>>",
    "IMPORTANT: Put ALL fields found in the document that do NOT fit the standard fields above into this object.",
    "Use the exact label from the document (snake_case), and preserve the value as-is.",
    "Examples of what belongs here: receipt_number, amount_paid, refunded_amount, refunded_on,",
    "  payment_reference, transaction_id, order_id, customer_id, loyalty_points, barcode,",
    "  discount, coupon_code, shipping_charges, handling_fee, company_pan, vat_number,",
    "  place_of_supply, reverse_charge, e_way_bill_no, vehicle_no, delivery_note,",
    "  purchase_order, terms_and_conditions, authorized_signatory, etc."
  }
}

CRITICAL RULES:
1. BILL TITLES: "CASH BILL", "CASH", "BILL", "TAX INVOICE", "CASH MEMO", "ESTIMATE" are DOCUMENT TITLES, NOT buyer/seller names.
2. BUYER: "Bill To", "Customer", "Billed To", "Ship To" sections → buyer_name, buyer_address.
3. PHONE vs GSTIN: A 10-digit Indian number starting with 6-9 is ALWAYS a phone, never a GSTIN.
4. GSTIN: Must be exactly 15 alphanumeric characters, all CAPITALS.
5. DATES: Always output as YYYY-MM-DD.
6. EXTRA FIELDS — MANDATORY: ANY field label that appears in the document that is not in the standard schema MUST be added to extra_fields with its value. Do not silently drop any field. Use snake_case for the key (e.g. "Amount paid" → "amount_paid", "Refunded on" → "refunded_on").
7. NUMERIC FIELDS in extra_fields: If the value is a monetary amount, store it as a number (e.g. 5.00). If it's a date, store as YYYY-MM-DD string. Otherwise store as string.
8. ITEMS: Extract EVERY single line item. Never omit or truncate items.
9. SELLER UNDEFINED: If no seller/vendor name exists, set seller_name to "Unknown".
10. Return valid JSON only. No markdown fences, no explanatory text."""

    user_prompt = f"""Extract all receipt and party details from this OCR text. Put every field found in the document into the JSON — standard fields in their proper place, and any additional/unrecognized fields into extra_fields:

\"\"\"
{ocr_text}
\"\"\"

Remember: extra_fields must capture ALL fields visible in the document that are not in the standard schema (e.g. receipt_number, amount_paid, refunded_on, refunded_amount, transaction details, discounts, etc.)."""

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ]

