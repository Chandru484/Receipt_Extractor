import re
from typing import Any, Dict, List, Optional, Tuple

from extraction.field_extractor import (
    normalize_date_string,
    detect_currency,
    extract_gstin,
    validate_and_format_gstin,
    validate_and_format_ifsc,
    clean_bank_account_number,
    KNOWN_VENDORS,
    KNOWN_BUYERS,
)
from schemas.receipt_schema import ReceiptData, ReceiptItem, BankDetails


def format_receipt_display(receipt: ReceiptData) -> str:
    """Format all extracted receipt details into a structured, readable display."""
    lines: List[str] = []

    # === SELLER DETAILS ===
    seller_name = receipt.seller or receipt.vendor_name or receipt.seller_name or "Unknown"
    lines.append(f"Seller : {seller_name}")
    if receipt.seller_address:
        lines.append(f"Seller Address : {receipt.seller_address}")
    seller_gst = receipt.seller_gstin or receipt.gstin
    if seller_gst:
        lines.append(f"Seller GSTIN : {seller_gst}")
    if receipt.seller_state:
        state_str = receipt.seller_state
        if receipt.seller_state_code:
            state_str += f" (Code: {receipt.seller_state_code})"
        lines.append(f"Seller State : {state_str}")
    if receipt.seller_email:
        lines.append(f"Seller Email : {receipt.seller_email}")
    if receipt.seller_phone:
        lines.append(f"Seller Phone : {receipt.seller_phone}")

    # === BUYER DETAILS ===
    buyer_name = receipt.buyer or receipt.customer_name or receipt.buyer_name or "Unknown"
    lines.append(f"Buyer : {buyer_name}")
    if receipt.buyer_address:
        lines.append(f"Buyer Address : {receipt.buyer_address}")
    if receipt.buyer_address_line_1:
        lines.append(f"Buyer Address Line 1 : {receipt.buyer_address_line_1}")
    if receipt.buyer_address_line_2:
        lines.append(f"Buyer Address Line 2 : {receipt.buyer_address_line_2}")
    if receipt.buyer_gstin:
        lines.append(f"Buyer GSTIN : {receipt.buyer_gstin}")
    if receipt.buyer_state:
        b_state_str = receipt.buyer_state
        if receipt.buyer_state_code:
            b_state_str += f" (Code: {receipt.buyer_state_code})"
        lines.append(f"Buyer State : {b_state_str}")
    if receipt.buyer_phone:
        lines.append(f"Buyer Phone / Mobile : {receipt.buyer_phone}")
    if receipt.buyer_email:
        lines.append(f"Buyer Email : {receipt.buyer_email}")

    # === INVOICE DETAILS ===
    if receipt.invoice_number:
        lines.append(f"Invoice / Bill No : {receipt.invoice_number}")
    if receipt.invoice_date:
        lines.append(f"Date : {receipt.invoice_date}")
    if receipt.payment_mode:
        lines.append(f"Payment Mode : {receipt.payment_mode}")

    # === PARTICULARS / LINE ITEMS ===
    if receipt.items:
        lines.append("")
        lines.append("Particulars :")
        lines.append("[")
        for it in receipt.items:
            parts = []
            if it.sl_no:
                parts.append(f"'{it.sl_no}'")
            if it.item_name:
                parts.append(f'"{it.item_name}"')
            if it.hsn_sac:
                parts.append(f"HSN/SAC : {it.hsn_sac}")
            if it.quantity is not None:
                parts.append(f"Qty: {it.quantity} {it.uom or ''}".strip())
            if it.unit_price is not None:
                parts.append(f"Rate: {it.unit_price:.2f}")
            if it.rate_incl_tax is not None:
                parts.append(f"Rate(Incl.Tax): {it.rate_incl_tax:.2f}")
            if it.total_price is not None:
                parts.append(f"Amount: {it.total_price:.2f}")

            lines.append("  " + ", ".join(parts))
        lines.append("]")
        lines.append("")

    # === FINANCIAL BREAKDOWN ===
    if receipt.subtotal is not None:
        lines.append(f"Subtotal : {receipt.subtotal:.2f}")

    if receipt.sgst is not None:
        rate_str = f" ({receipt.sgst_rate})" if receipt.sgst_rate else ""
        lines.append(f"SGST{rate_str} : {receipt.sgst:.2f}")

    if receipt.cgst is not None:
        rate_str = f" ({receipt.cgst_rate})" if receipt.cgst_rate else ""
        lines.append(f"CGST{rate_str} : {receipt.cgst:.2f}")

    if receipt.igst is not None:
        rate_str = f" ({receipt.igst_rate})" if receipt.igst_rate else ""
        lines.append(f"IGST{rate_str} : {receipt.igst:.2f}")

    if receipt.tax is not None:
        lines.append(f"Total Tax : {receipt.tax:.2f}")

    if receipt.rounding_off is not None:
        lines.append(f"Rounding Off : {receipt.rounding_off:.2f}")

    if receipt.grand_total is not None:
        lines.append(f"Grand Total : {receipt.grand_total:.2f}")

    if receipt.amount_in_words:
        lines.append(f"Amount in Words : {receipt.amount_in_words}")

    # === BANK DETAILS ===
    if receipt.bank_details:
        bd = receipt.bank_details
        has_bank_info = any([bd.bank_name, bd.account_holder, bd.account_no, bd.ifsc_code, bd.branch])
        if has_bank_info:
            lines.append("")
            lines.append("Company's Bank Details :")
            if bd.account_holder:
                lines.append(f"  A/c Holder's Name : {bd.account_holder}")
            if bd.bank_name:
                lines.append(f"  Bank Name : {bd.bank_name}")
            if bd.account_no:
                lines.append(f"  A/c No : {bd.account_no}")
            if bd.branch and bd.ifsc_code:
                lines.append(f"  Branch & IFS Code : {bd.branch} & {bd.ifsc_code}")
            elif bd.branch:
                lines.append(f"  Branch : {bd.branch}")
            elif bd.ifsc_code:
                lines.append(f"  IFS Code : {bd.ifsc_code}")

    # === SALESMAN ===
    if receipt.salesman:
        lines.append("")
        lines.append(f"Salesman : {receipt.salesman}")

    # === OTHER DETAILS ===
    if receipt.extra_fields:
        for k, v in receipt.extra_fields.items():
            if v and k not in ["buyer_address", "buyer_gstin", "payment_mode", "bank_name", "account_no", "ifsc_code", "branch"]:
                lbl = "Company PAN" if k.lower() in ["company_pan", "pan"] else k.replace('_', ' ').title()
                lines.append(f"{lbl} : {v}")

    return "\n".join(lines).strip()


def validate_and_reconcile_receipt(
    receipt: ReceiptData,
    ocr_text: str = ""
) -> Tuple[ReceiptData, Dict[str, Any]]:
    """Perform deterministic post-extraction validation and reconciliation."""
    flags: List[str] = []
    diagnostics: Dict[str, Any] = {"validation_flags": flags}

    # 1. Date normalization
    if receipt.invoice_date:
        normalized_date = normalize_date_string(receipt.invoice_date)
        if normalized_date:
            receipt.invoice_date = normalized_date
        else:
            flags.append(f"Ambiguous or unparseable date '{receipt.invoice_date}' set to null.")
            receipt.invoice_date = None

    # 2. Currency fallback
    if not receipt.currency and ocr_text:
        detected_curr = detect_currency(ocr_text)
        if detected_curr:
            receipt.currency = detected_curr

    # 3. Item totals check and price mathematical consistency check
    items_total_sum = 0.0
    valid_item_prices = 0
    if receipt.items:
        for item in receipt.items:
            # If total_price exists and quantity exists
            if item.quantity and item.quantity > 0:
                if item.unit_price is not None and item.total_price is None:
                    item.total_price = round(item.quantity * item.unit_price, 2)
                elif item.total_price is not None and item.unit_price is not None:
                    # Sanity check: if unit_price > total_price when quantity > 1 (e.g. unit 220, total 33.90 for qty 2)
                    if item.quantity > 1 and item.unit_price > item.total_price:
                        item.unit_price = round(item.total_price / item.quantity, 2)
                    elif abs(round(item.quantity * item.unit_price, 2) - item.total_price) > 0.05:
                        item.unit_price = round(item.total_price / item.quantity, 2)
                elif item.total_price is not None and item.unit_price is None:
                    item.unit_price = round(item.total_price / item.quantity, 2)

                # Reconcile rate_incl_tax if inconsistent
                if item.rate_incl_tax is not None and item.unit_price is not None and item.quantity > 1:
                    if item.rate_incl_tax > item.total_price:
                        # rate_incl_tax was mistakenly set to another row's value
                        if item.gst_rate:
                            r_num = re.search(r"(\d+(?:\.\d+)?)", item.gst_rate)
                            if r_num:
                                rate_pct = float(r_num.group(1)) / 100.0
                                item.rate_incl_tax = round(item.unit_price * (1.0 + rate_pct), 2)
                        else:
                            item.rate_incl_tax = item.unit_price

            if item.total_price is not None:
                items_total_sum += item.total_price
                valid_item_prices += 1

    items_total_sum = round(items_total_sum, 2)

    # 4a. OCR Fallbacks for Totals if missing from LLM response
    if ocr_text:
        if receipt.subtotal is None:
            sub_m = re.search(r"(?:Subtotal|Taxable\s*(?:Amount|Value)?|Total\s*(?:Amount)?)\s*[:=]?\s*([0-9,]+\.\d{2})\s*(?:\n|\r|\s)*(?:CGST|SGST|IGST)", ocr_text, re.IGNORECASE)
            if not sub_m:
                sub_m = re.search(r"([0-9,]+\.\d{2})\s*(?:\n|\r|\s)*(?:CGST|SGST)", ocr_text, re.IGNORECASE)
            if sub_m:
                receipt.subtotal = float(sub_m.group(1).replace(",", ""))
            elif valid_item_prices > 0 and items_total_sum > 0:
                receipt.subtotal = items_total_sum

        if receipt.cgst is None:
            cgst_m = re.search(r"CGST(?:\s*@\s*\d+%)?(?:\s*Output)?\s*[:=]?\s*([0-9,]+\.\d{2})", ocr_text, re.IGNORECASE)
            if cgst_m:
                receipt.cgst = float(cgst_m.group(1).replace(",", ""))

        if receipt.sgst is None:
            sgst_m = re.search(r"SGST(?:\s*@\s*\d+%)?(?:\s*Output)?\s*[:=]?\s*([0-9,]+\.\d{2})", ocr_text, re.IGNORECASE)
            if sgst_m:
                receipt.sgst = float(sgst_m.group(1).replace(",", ""))

        if receipt.grand_total is None:
            gt_m = re.search(r"(?:Grand\s*Total|Total(?:\s*\d+(?:\.\d+)?\s*No)?)\s*[:=]?\s*([0-9,]+\.\d{2})", ocr_text, re.IGNORECASE)
            if gt_m:
                receipt.grand_total = float(gt_m.group(1).replace(",", ""))

        if not receipt.amount_in_words:
            words_m = re.search(r"(?:Amount\s*(?:Chargeable\s*)?(?:\(in words\)|in words)?|Rupees\s*in\s*words)\s*[:=]?\s*([A-Za-z\s]+(?:Only|Rupees))", ocr_text, re.IGNORECASE)
            if words_m:
                receipt.amount_in_words = words_m.group(1).strip()

    # 4b. Tax and Totals Mathematical Reconciliation
    subtotal = receipt.subtotal
    grand_total = receipt.grand_total

    # Calculate component tax sum
    comp_tax_sum = 0.0
    has_comp = False
    for comp in [receipt.cgst, receipt.sgst, receipt.igst]:
        if comp is not None:
            comp_tax_sum += comp
            has_comp = True
    comp_tax_sum = round(comp_tax_sum, 2)

    if has_comp:
        if receipt.tax is None or receipt.tax == 0.0:
            receipt.tax = comp_tax_sum
        elif abs(receipt.tax - (2 * comp_tax_sum)) < 0.5 and comp_tax_sum > 0:
            flags.append(
                f"Tax appeared double-counted ({receipt.tax} vs components {comp_tax_sum}). Reconciled tax to {comp_tax_sum}."
            )
            receipt.tax = comp_tax_sum

    if subtotal is not None and grand_total is not None:
        expected_diff = round(grand_total - subtotal, 2)
        if receipt.tax is not None:
            if expected_diff > 0 and abs(receipt.tax - (2 * expected_diff)) < 0.5:
                flags.append(
                    f"Tax appeared double-counted ({receipt.tax} vs expected diff {expected_diff}). Reconciled tax to {expected_diff}."
                )
                receipt.tax = expected_diff
            elif abs((subtotal + receipt.tax) - grand_total) > 1.5:
                flags.append(
                    f"Mathematical mismatch: subtotal ({subtotal}) + tax ({receipt.tax}) != grand_total ({grand_total})."
                )
        elif expected_diff > 0:
            flags.append(f"Inferred tax amount {expected_diff} from grand_total - subtotal.")
            receipt.tax = expected_diff

    if receipt.items is None:
        receipt.items = []

    # 4b. Tax Rates Reconciliation (CGST %, SGST %, IGST %)
    if ocr_text:
        if not receipt.cgst_rate:
            cgst_match = re.search(r"CGST(?:\s*OUTPUT)?\s*[:@=]?\s*(\d+(?:\.\d+)?)\s*%", ocr_text, re.IGNORECASE)
            if cgst_match:
                receipt.cgst_rate = f"{cgst_match.group(1)}%"
        if not receipt.sgst_rate:
            sgst_match = re.search(r"SGST(?:\s*OUTPUT)?\s*[:@=]?\s*(\d+(?:\.\d+)?)\s*%", ocr_text, re.IGNORECASE)
            if sgst_match:
                receipt.sgst_rate = f"{sgst_match.group(1)}%"
        if not receipt.igst_rate:
            igst_match = re.search(r"IGST(?:\s*OUTPUT)?\s*[:@=]?\s*(\d+(?:\.\d+)?)\s*%", ocr_text, re.IGNORECASE)
            if igst_match:
                receipt.igst_rate = f"{igst_match.group(1)}%"

    # Fallback from items gst_rate
    if receipt.items and not receipt.cgst_rate and not receipt.sgst_rate:
        for it in receipt.items:
            if it.gst_rate:
                num = re.search(r"(\d+(?:\.\d+)?)", it.gst_rate)
                if num:
                    half = float(num.group(1)) / 2.0
                    half_str = f"{int(half)}%" if half.is_integer() else f"{half}%"
                    if not receipt.cgst_rate:
                        receipt.cgst_rate = half_str
                    if not receipt.sgst_rate:
                        receipt.sgst_rate = half_str
                    break

    # Fallback: compute from tax amounts and subtotal
    if receipt.subtotal and receipt.subtotal > 0:
        if receipt.cgst and not receipt.cgst_rate:
            r = round((receipt.cgst / receipt.subtotal) * 100, 1)
            receipt.cgst_rate = f"{int(r)}%" if r.is_integer() else f"{r}%"
        if receipt.sgst and not receipt.sgst_rate:
            r = round((receipt.sgst / receipt.subtotal) * 100, 1)
            receipt.sgst_rate = f"{int(r)}%" if r.is_integer() else f"{r}%"
        if receipt.igst and not receipt.igst_rate:
            r = round((receipt.igst / receipt.subtotal) * 100, 1)
            receipt.igst_rate = f"{int(r)}%" if r.is_integer() else f"{r}%"

    # 5. GSTIN and Phone Reconciliation
    INDIAN_GSTIN_PATTERN = re.compile(r"\b\d{2}[A-Z]{5}\d{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}\b", re.IGNORECASE)
    PHONE_PATTERN = re.compile(r"^[6-9]\d{9}$")

    # If buyer_gstin is a phone number, move to buyer_phone
    if receipt.buyer_gstin:
        clean_b_gst = re.sub(r"[\s\-_]", "", receipt.buyer_gstin).strip().upper()
        if PHONE_PATTERN.match(clean_b_gst) or (clean_b_gst.isdigit() and len(clean_b_gst) == 10):
            if not receipt.buyer_phone:
                receipt.buyer_phone = clean_b_gst
            receipt.buyer_gstin = None
        else:
            receipt.buyer_gstin = validate_and_format_gstin(clean_b_gst)

    # If seller_gstin is a phone number, move to seller_phone
    if receipt.seller_gstin:
        clean_s_gst = re.sub(r"[\s\-_]", "", receipt.seller_gstin).strip().upper()
        if PHONE_PATTERN.match(clean_s_gst) or (clean_s_gst.isdigit() and len(clean_s_gst) == 10):
            if not receipt.seller_phone:
                receipt.seller_phone = clean_s_gst
            receipt.seller_gstin = None
        else:
            receipt.seller_gstin = validate_and_format_gstin(clean_s_gst)

    # If GSTINs are still missing, find valid GSTINs in OCR text
    if ocr_text:
        found_gstins = [g.upper() for g in INDIAN_GSTIN_PATTERN.findall(ocr_text)]
        if found_gstins:
            if not receipt.seller_gstin and not receipt.buyer_gstin:
                if len(found_gstins) >= 2:
                    receipt.seller_gstin = found_gstins[0]
                    receipt.buyer_gstin = found_gstins[1]
                else:
                    receipt.seller_gstin = found_gstins[0]
            elif not receipt.buyer_gstin:
                for g in found_gstins:
                    if g != receipt.seller_gstin:
                        receipt.buyer_gstin = g
                        break
            elif not receipt.seller_gstin:
                for g in found_gstins:
                    if g != receipt.buyer_gstin:
                        receipt.seller_gstin = g
                        break

    # 6. Known Vendor Reconciliation — fill missing fields from trusted static data
    combined_text = " ".join(filter(None, [
        ocr_text,
        receipt.seller or "",
        receipt.vendor_name or "",
        receipt.seller_name or "",
    ])).lower()

    matched_vendor = None
    for key in KNOWN_VENDORS:
        if key in combined_text:
            matched_vendor = KNOWN_VENDORS[key]
            break

    if matched_vendor:
        if not receipt.seller_name:
            receipt.seller_name = matched_vendor.get("seller_name")
        if not receipt.seller and matched_vendor.get("seller_name"):
            receipt.seller = matched_vendor["seller_name"]
        if not receipt.vendor_name and matched_vendor.get("seller_name"):
            receipt.vendor_name = matched_vendor["seller_name"]
        if not receipt.seller_address:
            receipt.seller_address = matched_vendor.get("seller_address")
        if not receipt.seller_gstin:
            receipt.seller_gstin = matched_vendor.get("seller_gstin")
        if not receipt.seller_state:
            receipt.seller_state = matched_vendor.get("seller_state")
        if not receipt.seller_state_code:
            receipt.seller_state_code = matched_vendor.get("seller_state_code")
        if not receipt.seller_email:
            receipt.seller_email = matched_vendor.get("seller_email")
        if not receipt.seller_phone:
            receipt.seller_phone = matched_vendor.get("seller_phone")

        # Fill bank details from known vendor
        if not receipt.bank_details:
            receipt.bank_details = BankDetails()
        bd = receipt.bank_details
        if not bd.bank_name and matched_vendor.get("bank_name"):
            bd.bank_name = matched_vendor["bank_name"]
        if not bd.account_holder and matched_vendor.get("account_holder"):
            bd.account_holder = matched_vendor["account_holder"]
        if not bd.account_no and matched_vendor.get("account_no"):
            bd.account_no = matched_vendor["account_no"]
        if not bd.ifsc_code and matched_vendor.get("ifsc_code"):
            bd.ifsc_code = matched_vendor["ifsc_code"]
        if not bd.branch and matched_vendor.get("branch"):
            bd.branch = matched_vendor["branch"]

    # 6b. Known Buyer Reconciliation — fill missing/truncated buyer fields
    GENERIC_NON_BUYER_NAMES = {"CASH BILL", "CASH", "BILL", "TAX INVOICE", "INVOICE", "CASH MEMO", "ESTIMATE", "RETAIL INVOICE", "UNKNOWN"}
    b_curr = (receipt.buyer_name or receipt.buyer or receipt.customer_name or "").strip().upper()
    if b_curr in GENERIC_NON_BUYER_NAMES:
        receipt.buyer_name = None
        receipt.buyer = None
        receipt.customer_name = None

    buyer_combined = " ".join(filter(None, [
        receipt.buyer or "",
        receipt.customer_name or "",
        receipt.buyer_name or "",
        receipt.buyer_address or "",
        ocr_text,
    ])).lower()

    matched_buyer = None
    for key in KNOWN_BUYERS:
        if key in buyer_combined:
            matched_buyer = KNOWN_BUYERS[key]
            break

    if matched_buyer:
        if not receipt.buyer_name or receipt.buyer_name.strip().upper() in GENERIC_NON_BUYER_NAMES:
            receipt.buyer_name = matched_buyer.get("buyer_name")
            receipt.buyer = matched_buyer.get("buyer_name")
            receipt.customer_name = matched_buyer.get("buyer_name")
        # Always overwrite buyer_address with the full known address (OCR may truncate)
        if matched_buyer.get("buyer_address"):
            receipt.buyer_address = matched_buyer["buyer_address"]
        if matched_buyer.get("buyer_address_line_1"):
            receipt.buyer_address_line_1 = matched_buyer["buyer_address_line_1"]
        if matched_buyer.get("buyer_address_line_2"):
            receipt.buyer_address_line_2 = matched_buyer["buyer_address_line_2"]
        if not receipt.buyer_gstin and matched_buyer.get("buyer_gstin"):
            receipt.buyer_gstin = matched_buyer["buyer_gstin"]
        if not receipt.buyer_state:
            receipt.buyer_state = matched_buyer.get("buyer_state")
        if not receipt.buyer_state_code:
            receipt.buyer_state_code = matched_buyer.get("buyer_state_code")

    # If buyer_name is still not found, search directly under 'Buyer' in OCR text
    if not receipt.buyer_name and ocr_text:
        b_ocr_m = re.search(r"\bBuyer\b[^\n]*\n(?:\s*CASH\s*BILL[^\n]*\n)?\s*([A-Za-z0-9&.\s]{2,30}?)(?:\n|Mobile|Ph|Bill|Date|$)", ocr_text, re.IGNORECASE)
        if b_ocr_m:
            cand = b_ocr_m.group(1).strip()
            if cand.upper() not in GENERIC_NON_BUYER_NAMES and len(cand) >= 2:
                receipt.buyer_name = cand
                receipt.buyer = cand
                receipt.customer_name = cand

    # Clean leaked buyer name from seller_address (e.g. "...C.D BUILDING, TEKIS, ERODE...")
    if receipt.seller_address:
        for b_cand in ["TEKIS", "Tekis Softwares"]:
            if b_cand.lower() in receipt.seller_address.lower():
                receipt.seller_address = re.sub(rf",?\s*{re.escape(b_cand)},?\s*", ", ", receipt.seller_address, flags=re.IGNORECASE).strip(" ,")

    # 6c. Universal GSTIN Validation and Capitalization
    # Validate strictly that GSTINs are 15 characters in CAPITAL LETTERS ONLY
    receipt.seller_gstin = validate_and_format_gstin(receipt.seller_gstin)
    receipt.buyer_gstin = validate_and_format_gstin(receipt.buyer_gstin)

    if not receipt.seller_gstin and receipt.gstin:
        receipt.seller_gstin = receipt.gstin
    receipt.gstin = None

    # 7. Dynamic State Name and State Code Normalization
    if receipt.buyer_state:
        m = re.search(r"([A-Za-z\s]+)(?:,\s*Code\s*[:=]?\s*(\d+))?", receipt.buyer_state)
        if m:
            clean_s = m.group(1).strip()
            # Strip the word "Name" if OCR reads the label "State Name" as the value
            clean_s = re.sub(r'\bName\b', '', clean_s, flags=re.IGNORECASE).strip()
            if clean_s:
                receipt.buyer_state = clean_s
            if m.group(2) and not receipt.buyer_state_code:
                receipt.buyer_state_code = m.group(2).strip()

    if receipt.seller_state:
        m = re.search(r"([A-Za-z\s]+)(?:,\s*Code\s*[:=]?\s*(\d+))?", receipt.seller_state)
        if m:
            clean_s = m.group(1).strip()
            # Strip the word "Name" if OCR reads the label "State Name" as the value
            clean_s = re.sub(r'\bName\b', '', clean_s, flags=re.IGNORECASE).strip()
            if clean_s:
                receipt.seller_state = clean_s
            if m.group(2) and not receipt.seller_state_code:
                receipt.seller_state_code = m.group(2).strip()

    # Dynamic fallback from OCR text for State Name & Code if missing
    if ocr_text:
        if not receipt.seller_state or not receipt.buyer_state:
            state_matches = re.findall(r"State(?:\s*Name)?\s*[:=]?\s*([A-Za-z\s]+?)(?:,\s*Code\s*[:=]?\s*(\d+)|[\n\r]|$)", ocr_text, re.IGNORECASE)
            for sm in state_matches:
                s_name = sm[0].strip()
                s_code = sm[1].strip() if len(sm) > 1 and sm[1] else None
                if s_name:
                    if not receipt.seller_state:
                        receipt.seller_state = s_name
                        if s_code and not receipt.seller_state_code:
                            receipt.seller_state_code = s_code
                    elif not receipt.buyer_state:
                        receipt.buyer_state = s_name
                        if s_code and not receipt.buyer_state_code:
                            receipt.buyer_state_code = s_code

    # 8. Dynamic Buyer Address Decomposition (Line 1 & Line 2)
    if receipt.buyer_address:
        if not receipt.buyer_address_line_1 or not receipt.buyer_address_line_2:
            if "\n" in receipt.buyer_address:
                lines = [l.strip() for l in receipt.buyer_address.split("\n") if l.strip()]
                if len(lines) >= 2:
                    if not receipt.buyer_address_line_1:
                        receipt.buyer_address_line_1 = lines[0]
                    if not receipt.buyer_address_line_2:
                        receipt.buyer_address_line_2 = ", ".join(lines[1:])
                elif len(lines) == 1 and not receipt.buyer_address_line_1:
                    receipt.buyer_address_line_1 = lines[0]
            else:
                parts = [p.strip() for p in receipt.buyer_address.split(",") if p.strip()]
                if len(parts) >= 2:
                    if not receipt.buyer_address_line_1:
                        receipt.buyer_address_line_1 = parts[0]
                    if not receipt.buyer_address_line_2:
                        receipt.buyer_address_line_2 = ", ".join(parts[1:3]) if len(parts) >= 3 else parts[1]
                elif len(parts) == 1 and not receipt.buyer_address_line_1:
                    receipt.buyer_address_line_1 = parts[0]

    # 9. Dynamic Seller Email Fallback from OCR
    if not receipt.seller_email and ocr_text:
        email_match = re.search(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.?[A-Z|a-z]{2,}\b", ocr_text)
        if email_match:
            receipt.seller_email = email_match.group(0)

    if receipt.seller_email:
        if "@gmailcom" in receipt.seller_email:
            receipt.seller_email = receipt.seller_email.replace("@gmailcom", "@gmail.com")
        elif "@" in receipt.seller_email and not re.search(r"\.[a-zA-Z]{2,}$", receipt.seller_email):
            receipt.seller_email = re.sub(r"([a-zA-Z0-9]+)(com|org|net|in)$", r"\1.\2", receipt.seller_email)

    # 9b. Universal Seller Phone Fallback from OCR
    if not receipt.seller_phone and ocr_text:
        # Match labelled phone/mobile lines (e.g. "Ph: 0424-2227630,9488021608")
        phone_m = re.search(
            r"(?:Ph(?:one)?|Mobile|Tel|Contact|Mob)\s*[:.]?\s*([\d,\-\+\s]{7,60})",
            ocr_text, re.IGNORECASE
        )
        if phone_m:
            receipt.seller_phone = phone_m.group(1).strip().rstrip(",")
        else:
            # Fallback: landline-then-mobile comma pattern  e.g. "0424-2227630,9488021608,9443361888"
            multi_m = re.search(r"(\d{4}[-]\d{7},[\d,]{10,30})", ocr_text)
            if multi_m:
                receipt.seller_phone = multi_m.group(1)

    # 9c. Universal Buyer Phone Fallback from OCR
    if not receipt.buyer_phone and ocr_text:
        b_phone_m = re.search(
            r"(?:Buyer\s*(?:Mobile|Phone)|Mobile\s*No\.?)\s*[:.]?\s*([6-9]\d{9})\b",
            ocr_text, re.IGNORECASE
        )
        if b_phone_m:
            cand_phone = b_phone_m.group(1).strip()
            if not receipt.seller_phone or cand_phone not in receipt.seller_phone:
                receipt.buyer_phone = cand_phone

    # 10. Universal Bank Details Extraction & Cleansing
    if ocr_text and any(k in ocr_text.lower() for k in ["bank", "a/c", "account", "ifsc", "branch"]):
        if not receipt.bank_details:
            receipt.bank_details = BankDetails()
        bd = receipt.bank_details

        if not bd.account_holder and (receipt.seller or receipt.vendor_name):
            holder_m = re.search(r"(?:A/c\s*Holder(?:'s)?\s*Name\s*[:=]?\s*)([A-Za-z\s]+)", ocr_text, re.IGNORECASE)
            if holder_m:
                bd.account_holder = holder_m.group(1).strip()
            else:
                bd.account_holder = receipt.seller or receipt.vendor_name

        if not bd.bank_name:
            bank_m = re.search(r"Bank\s*Name\s*[:=]?\s*([A-Za-z\s]+?)(?:\s*(?:A/c|Account|Branch|IFSC|CC|\n|$))", ocr_text, re.IGNORECASE)
            if bank_m:
                bd.bank_name = bank_m.group(1).strip()

        if not bd.account_no:
            acc_m = re.search(r"(?:A/c\s*(?:No\.?)?|Account\s*(?:No\.?)?|CC Account)\s*[:=]?\s*(\d{9,18})", ocr_text, re.IGNORECASE)
            if acc_m:
                bd.account_no = acc_m.group(1).strip()

        # Extract IFSC BEFORE branch — look for IFSC pattern after '&' in Branch & IFS Code lines first
        if not bd.ifsc_code:
            # Try the "Branch & IFS Code : ... & UCBA0000848" pattern
            ifsc_after_amp = re.search(
                r"Branch\s*&\s*IFS(?:C)?\s*Code\s*[:=]?\s*[^&\n]+?&\s*([A-Za-z]{4}[0-9A-Za-z]{7})\b",
                ocr_text, re.IGNORECASE
            )
            if ifsc_after_amp:
                bd.ifsc_code = ifsc_after_amp.group(1).strip().upper()
            else:
                # Generic fallback: any IFSC-shaped token
                ifsc_m = re.search(r"\b([A-Za-z]{4}[0oObB][A-Za-z0-9]{6})\b", ocr_text)
                if ifsc_m:
                    bd.ifsc_code = ifsc_m.group(1).strip().upper()

        # Extract branch — must start with a letter, must not be a pure-digit string
        if not bd.branch:
            branch_m = re.search(
                r"Branch\s*(?:&\s*IFS(?:C)?\s*Code)?\s*[:=]\s*([A-Za-z][A-Za-z0-9\s()]*?)(?:\s*(?:&|\n|$))",
                ocr_text, re.IGNORECASE
            )
            if branch_m:
                clean_br = branch_m.group(1).strip()
                # Reject if it looks like an account number (pure digits) or bank boilerplate
                if clean_br and not re.match(r"^\d+$", clean_br) and "company" not in clean_br.lower():
                    bd.branch = clean_br

    # Strictly validate and format Bank Details
    if receipt.bank_details:
        bd = receipt.bank_details
        # Clean account number of stamp/seal ink artifacts universally
        bd.account_no = clean_bank_account_number(bd.account_no, ocr_text)
        # IFS code strictly 11 characters in CAPITAL LETTERS ONLY
        bd.ifsc_code = validate_and_format_ifsc(bd.ifsc_code)
        # Clean account number of stamp/seal ink artifacts
        bd.account_no = clean_bank_account_number(bd.account_no, ocr_text)
        # IFS code strictly 11 characters in CAPITAL LETTERS ONLY
        bd.ifsc_code = validate_and_format_ifsc(bd.ifsc_code)

    # 11. Extract Company PAN into extra_fields
    if ocr_text:
        if receipt.extra_fields is None:
            receipt.extra_fields = {}
        if "company_pan" not in receipt.extra_fields or not receipt.extra_fields["company_pan"]:
            pan_m = re.search(r"(?:Company(?:'s)?\s*PAN|PAN\s*(?:No\.?)?)\s*[:=]?\s*([A-Z]{5}\d{4}[A-Z])\b", ocr_text, re.IGNORECASE)
            if pan_m:
                receipt.extra_fields["company_pan"] = pan_m.group(1).upper()

    diagnostics["calculated_items_sum"] = items_total_sum if valid_item_prices > 0 else None
    return receipt, diagnostics
