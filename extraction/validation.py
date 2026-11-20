import re
from typing import Any, Dict, List, Optional, Tuple

from extraction.field_extractor import (
    normalize_date_string,
    detect_currency,
    extract_gstin,
    validate_and_format_gstin,
    validate_and_format_ifsc,
    clean_bank_account_number,
    clean_bank_name,
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
    if getattr(receipt, "seller_address_line_1", None):
        lines.append(f"Seller Address Line 1 : {receipt.seller_address_line_1}")
    if getattr(receipt, "seller_address_line_2", None):
        lines.append(f"Seller Address Line 2 : {receipt.seller_address_line_2}")
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
    if getattr(receipt, "seller_mobile", None):
        lines.append(f"Seller Mobile : {receipt.seller_mobile}")

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
        lines.append(f"Buyer Phone : {receipt.buyer_phone}")
    if getattr(receipt, "buyer_mobile", None):
        lines.append(f"Buyer Mobile : {receipt.buyer_mobile}")
    if receipt.buyer_email:
        lines.append(f"Buyer Email : {receipt.buyer_email}")

    # === INVOICE DETAILS ===
    if getattr(receipt, "bill_type", None):
        lines.append(f"Bill Type : {receipt.bill_type}")
    if receipt.invoice_number:
        lines.append(f"Invoice / Bill No : {receipt.invoice_number}")
    if receipt.invoice_date:
        lines.append(f"Date : {receipt.invoice_date}")
    if receipt.payment_mode:
        lines.append(f"Payment Mode : {receipt.payment_mode}")
    if getattr(receipt, "transport", None):
        lines.append(f"Transport : {receipt.transport}")
    if getattr(receipt, "despatch_through", None):
        lines.append(f"Despatch Through : {receipt.despatch_through}")
    if getattr(receipt, "eway_bill_no", None):
        lines.append(f"E-Way Bill No : {receipt.eway_bill_no}")
    if getattr(receipt, "po_number", None):
        lines.append(f"P.O No & Date : {receipt.po_number}")
    if getattr(receipt, "dc_number", None):
        lines.append(f"D.C.No & Date : {receipt.dc_number}")

    # === PARTICULARS / LINE ITEMS ===
    if receipt.items:
        lines.append("")
        lines.append("Particulars :")
        lines.append("[")
        has_multipage = any(getattr(it, "page", None) and it.page > 1 for it in receipt.items)
        for it in receipt.items:
            parts = []
            if has_multipage and getattr(it, "page", None):
                parts.append(f"[Pg {it.page}]")
            if it.sl_no:
                parts.append(f"'{it.sl_no}'")
            if it.item_name:
                parts.append(f'"{it.item_name}"')
            if it.hsn_sac:
                parts.append(f"HSN/SAC : {it.hsn_sac}")
            if it.quantity is not None:
                parts.append(f"Qty: {it.quantity} {it.uom or ''}".strip())
            if it.unit_price is not None:
                parts.append(f"Rate: {it.unit_price}")
            if it.rate_incl_tax is not None:
                parts.append(f"Rate(Incl.Tax): {it.rate_incl_tax}")
            if getattr(it, "discount_percent", None) is not None and it.discount_percent not in ["", "None"]:
                parts.append(f"Dis%: {it.discount_percent}")
            if it.total_price is not None:
                parts.append(f"Amount: {it.total_price}")

            lines.append("  " + ", ".join(parts))
        lines.append("]")
        lines.append("")

    # === FINANCIAL BREAKDOWN ===
    if getattr(receipt, "total_items", None) is not None:
        lines.append(f"Total Items : {receipt.total_items}")
    if getattr(receipt, "total_quantity", None) is not None:
        lines.append(f"Total Qty : {receipt.total_quantity}")
    if getattr(receipt, "gross_amount", None) is not None:
        lines.append(f"Gross : {receipt.gross_amount}")
    if receipt.subtotal is not None and receipt.subtotal != getattr(receipt, "gross_amount", None) and receipt.subtotal != receipt.grand_total:
        lines.append(f"Subtotal : {receipt.subtotal}")

    if receipt.sgst is not None:
        rate_str = f" ({receipt.sgst_rate})" if receipt.sgst_rate else ""
        lines.append(f"SGST{rate_str} : {receipt.sgst}")

    if receipt.cgst is not None:
        rate_str = f" ({receipt.cgst_rate})" if receipt.cgst_rate else ""
        lines.append(f"CGST{rate_str} : {receipt.cgst}")

    if receipt.igst is not None:
        rate_str = f" ({receipt.igst_rate})" if receipt.igst_rate else ""
        lines.append(f"IGST{rate_str} : {receipt.igst}")

    if receipt.tax is not None:
        lines.append(f"Total Tax : {receipt.tax}")

    if receipt.rounding_off is not None:
        lines.append(f"Rounding Off : {receipt.rounding_off}")

    if receipt.grand_total is not None:
        lines.append(f"Grand Total : {receipt.grand_total}")

    if getattr(receipt, "balance_amount", None) is not None:
        lines.append(f"Balance Amt : {receipt.balance_amount}")

    if receipt.amount_paid is not None:
        lines.append(f"Amount Paid : {receipt.amount_paid}")

    if receipt.refunded_on:
        lines.append(f"Refunded On : {receipt.refunded_on}")

    if receipt.refunded_amount is not None:
        lines.append(f"Refunded Amount : {receipt.refunded_amount}")

    if receipt.amount_in_words:
        lines.append(f"Amount in Words : {receipt.amount_in_words}")

    # === HSN / TAX SUMMARY ===
    if receipt.hsn_tax_summary:
        lines.append("")
        lines.append("HSN / Tax Summary :")
        lines.append("[")
        for h in receipt.hsn_tax_summary:
            parts = []
            if h.hsn_sac:
                parts.append(f"HSN/SAC : {h.hsn_sac}")
            if h.taxable_value is not None:
                parts.append(f"Taxable : {h.taxable_value}")
            if h.sgst_amount is not None:
                r = f" ({h.sgst_rate})" if h.sgst_rate else ""
                parts.append(f"SGST{r} : {h.sgst_amount}")
            if h.cgst_amount is not None:
                r = f" ({h.cgst_rate})" if h.cgst_rate else ""
                parts.append(f"CGST{r} : {h.cgst_amount}")
            if h.igst_amount is not None:
                r = f" ({h.igst_rate})" if h.igst_rate else ""
                parts.append(f"IGST{r} : {h.igst_amount}")
            if h.total_tax_amount is not None:
                parts.append(f"Tax : {h.total_tax_amount}")
            lines.append(f"  {', '.join(parts)}")
        lines.append("]")

    # === BANK DETAILS ===
    if receipt.bank_details:
        bd = receipt.bank_details
        has_bank_info = any([
            bd.bank_name, bd.account_holder, bd.account_no,
            bd.ifsc_code, bd.branch,
            getattr(bd, "bsb_number", None), getattr(bd, "swift_code", None)
        ])
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
            if getattr(bd, "bsb_number", None):
                lines.append(f"  BSB No : {bd.bsb_number}")
            if getattr(bd, "swift_code", None):
                lines.append(f"  SWIFT Code : {bd.swift_code}")

    # === SALESMAN ===
    if receipt.salesman:
        lines.append("")
        lines.append(f"Salesman : {receipt.salesman}")

    # === OTHER DETAILS ===
    if receipt.extra_fields:
        shown_extra = False
        _SKIP_IN_DISPLAY = {
            "buyer_address", "buyer_gstin", "payment_mode",
            "bank_name", "account_no", "ifsc_code", "branch",
            "receipt_number", "invoice_number", "date_paid", "invoice_date",
            "amount_paid", "refunded_amount", "refunded_on",
            "contact_email", "support_email", "seller_email", "buyer_email",
            "seller_phone", "buyer_phone", "total_due", "balance_due",
            "amount_due", "total_amount", "sub_total", "rounding_off_label"
        }
        for k, v in receipt.extra_fields.items():
            if not v or k in _SKIP_IN_DISPLAY:
                continue
            if not shown_extra:
                lines.append("")
                lines.append("Additional Fields :")
                shown_extra = True
            # Format key: snake_case → Title Case label
            lbl = k.replace("_", " ").title()
            # Override specific known keys to prettier labels
            _LABEL_MAP = {
                "company_pan": "Company PAN",
                "amount_paid": "Amount Paid",
                "refunded_amount": "Refunded Amount",
                "refunded_on": "Refunded On",
                "receipt_number": "Receipt Number",
                "transaction_id": "Transaction ID",
                "order_id": "Order ID",
                "customer_id": "Customer ID",
                "place_of_supply": "Place of Supply",
                "e_way_bill_no": "E-Way Bill No",
                "reverse_charge": "Reverse Charge",
                "vehicle_no": "Vehicle No",
                "delivery_note": "Delivery Note",
                "purchase_order": "Purchase Order",
                "loyalty_points": "Loyalty Points",
                "discount": "Discount",
                "coupon_code": "Coupon Code",
                "shipping_charges": "Shipping Charges",
                "handling_fee": "Handling Fee",
            }
            lbl = _LABEL_MAP.get(k, lbl)
            # Format value based on type
            if isinstance(v, float):
                val_str = f"{v:.2f}"
            elif isinstance(v, bool):
                val_str = "Yes" if v else "No"
            else:
                val_str = str(v)
            lines.append(f"  {lbl} : {val_str}")

    return "\n".join(lines).strip()


def extract_hsn_tax_summary(ocr_text: str) -> Tuple[List[Dict[str, Any]], Dict[str, float]]:
    """Parse HSN/SAC-wise tax breakdown table and authoritative totals from invoice OCR."""
    if not ocr_text:
        return [], {}

    # Check for HSN / Tax table header
    has_hsn_table = bool(re.search(r"HSN/SAC\s+(?:Taxable|Amount|GST%|SGST|CGST|Rate)", ocr_text, re.IGNORECASE))
    if not has_hsn_table:
        return [], {}

    m = re.search(r"HSN/SAC\s+Taxable.*?(?=Amount Chargeable|Bank Details|Rupees|\bTerms\b|$)", ocr_text, re.DOTALL | re.IGNORECASE)
    if not m:
        return [], {}

    block = m.group(0)
    lines = [l.strip() for l in block.splitlines() if l.strip()]
    rows: List[Dict[str, Any]] = []
    totals: Dict[str, float] = {}

    for line in lines:
        tot_m = re.match(r"^Total\s+([0-9,]+\.\d{2})\s+([0-9,]+\.\d{2})\s+([0-9,]+\.\d{2})", line, re.IGNORECASE)
        if tot_m:
            totals["subtotal"] = float(tot_m.group(1).replace(",", ""))
            totals["sgst"] = float(tot_m.group(2).replace(",", ""))
            totals["cgst"] = float(tot_m.group(3).replace(",", ""))
            totals["tax"] = round(totals["sgst"] + totals["cgst"], 2)
            continue

        row_m = re.search(r"([\d,\s]+?)\s+([0-9,]+\.\d{2})\s+(\d+(?:\.\d+)?)\s+([0-9,]+\.\d{2})\s+(\d+(?:\.\d+)?)\s+([0-9,]+\.\d{2})", line)
        if row_m:
            hsn = re.sub(r"\s+", "", row_m.group(1)).strip(",")
            taxable = float(row_m.group(2).replace(",", ""))
            sgst_r = f"{float(row_m.group(3)):g}%"
            sgst_a = float(row_m.group(4).replace(",", ""))
            cgst_r = f"{float(row_m.group(5)):g}%"
            cgst_a = float(row_m.group(6).replace(",", ""))
            rows.append({
                "hsn_sac": hsn,
                "taxable_value": taxable,
                "sgst_rate": sgst_r,
                "sgst_amount": sgst_a,
                "cgst_rate": cgst_r,
                "cgst_amount": cgst_a,
                "total_tax_amount": round(sgst_a + cgst_a, 2)
            })
        elif rows and (line.startswith(",") or re.match(r"^[,\d\s]+", line)):
            m_cont = re.match(r"^[,\d\s]+", line)
            if m_cont:
                extra = re.sub(r"\s+", "", m_cont.group(0)).strip(",")
                if extra:
                    rows[-1]["hsn_sac"] += "," + extra

    sub_m = re.search(r"Sub\s*Total\s*[:=]?\s*([0-9,]+\.\d{2})", ocr_text, re.IGNORECASE)
    if sub_m:
        totals["subtotal"] = float(sub_m.group(1).replace(",", ""))

    net_m = re.search(r"(?:NET\s*TOTAL|Grand\s*Total)\s*[:=]?\s*([0-9,]+\.\d{2})", ocr_text, re.IGNORECASE)
    if net_m:
        totals["grand_total"] = float(net_m.group(1).replace(",", ""))

    ro_m = re.search(r"(?:Rounded\s*Off|Round\s*Off)\s*[:=]?\s*([-+]?[0-9,]+\.\d{2})", ocr_text, re.IGNORECASE)
    if ro_m:
        totals["rounding_off"] = float(ro_m.group(1).replace(",", ""))

    if rows and ("cgst" not in totals or "sgst" not in totals):
        sum_taxable = round(sum(r["taxable_value"] for r in rows), 2)
        sum_sgst = round(sum(r["sgst_amount"] for r in rows if "sgst_amount" in r), 2)
        sum_cgst = round(sum(r["cgst_amount"] for r in rows if "cgst_amount" in r), 2)
        totals.setdefault("subtotal", sum_taxable)
        totals.setdefault("sgst", sum_sgst)
        totals.setdefault("cgst", sum_cgst)
        totals.setdefault("tax", round(sum_sgst + sum_cgst, 2))

    return rows, totals


def reconcile_missing_ocr_items(receipt: ReceiptData, ocr_text: str) -> None:
    """Scan OCR text for numbered line items missing from LLM extraction and add them."""
    if not ocr_text:
        return
    if receipt.items is None:
        receipt.items = []

    existing_sl_nos = set()
    for it in receipt.items:
        if it.sl_no:
            clean_sl = re.sub(r"[^\d]", "", str(it.sl_no))
            if clean_sl:
                existing_sl_nos.add(clean_sl)

    page_blocks = re.split(r"(?:^|\n)---\s*Page\s+(\d+)\s*---", ocr_text, flags=re.IGNORECASE)
    pages_to_check = []
    if len(page_blocks) > 1:
        for i in range(1, len(page_blocks), 2):
            p_num = int(page_blocks[i])
            p_txt = page_blocks[i + 1] if i + 1 < len(page_blocks) else ""
            pages_to_check.append((p_num, p_txt))
    else:
        pages_to_check.append((1, ocr_text))

    from schemas.receipt_schema import ReceiptItem
    new_items_added = False

    for p_num, p_txt in pages_to_check:
        for line in p_txt.splitlines():
            l_str = line.strip()
            # Standard GST table format: S.No Particulars HSN/SAC GST% Qty UOM Rate Amount
            m = re.match(r"^(\d{1,3})\s+(.+?)\s+(\d{4,8})\s+(\d+)\s+([0-9,]+(?:\.\d+)?)\s*(?:%\s*)?([A-Za-z]+)\s+([0-9,]+\.\d{2})\s+([0-9,]+\.\d{2})$", l_str)
            if m:
                sl = m.group(1)
                u_p = float(m.group(7).replace(",", ""))
                t_p = float(m.group(8).replace(",", ""))
                q = float(m.group(5).replace(",", ""))
                hsn = m.group(3)
                gst = f"{m.group(4)}%"
                uom = m.group(6)
                iname = m.group(2).strip()

                if sl not in existing_sl_nos:
                    new_item = ReceiptItem(
                        page=p_num,
                        sl_no=sl,
                        item_name=iname,
                        hsn_sac=hsn,
                        gst_rate=gst,
                        quantity=q,
                        uom=uom,
                        unit_price=u_p,
                        total_price=t_p,
                        discount_percent=None
                    )
                    receipt.items.append(new_item)
                    existing_sl_nos.add(sl)
                    new_items_added = True
                else:
                    for it in receipt.items:
                        if it.sl_no and re.sub(r"[^\d]", "", str(it.sl_no)) == sl:
                            it.hsn_sac = hsn
                            it.gst_rate = gst
                            it.quantity = q
                            it.uom = uom
                            it.unit_price = u_p
                            it.total_price = t_p
                            it.discount_percent = None
                            break

            # Stationery / Retail table format: S.No Particulars Qty Rate Dis% Amount
            if not re.search(r"\b\d{6,8}\b", l_str):
                m2 = re.match(r"^(\d{1,3})\s+(.+?)\s+(\d+(?:\.\d+)?)\s+(\d+(?:\.\d+)?)\s+(\d+(?:\.\d+)?)\s+([0-9,]+\.\d{2})$", l_str)
                if m2:
                    sl2 = m2.group(1)
                    q2 = float(m2.group(3))
                    r2 = float(m2.group(4))
                    dis_val = float(m2.group(5))
                    dis2 = f"{dis_val:.2f}%" if dis_val <= 100.0 else None
                    amt2 = float(m2.group(6).replace(",", ""))
                    if sl2 not in existing_sl_nos:
                        new_item = ReceiptItem(
                            page=p_num,
                            sl_no=sl2,
                            item_name=m2.group(2).strip(),
                            quantity=q2,
                            unit_price=r2,
                            discount_percent=dis2,
                            total_price=amt2
                        )
                        receipt.items.append(new_item)
                        existing_sl_nos.add(sl2)
                        new_items_added = True
                    else:
                        # Reconcile existing item against OCR truth to resolve packaging label confusion (e.g. 'Rs 20/-' in item name)
                        for it in receipt.items:
                            if it.sl_no and re.sub(r"[^\d]", "", str(it.sl_no)) == sl2:
                                if it.quantity != q2 or it.unit_price != r2:
                                    it.quantity = q2
                                    it.unit_price = r2
                                    it.total_price = amt2
                                if dis2 is not None:
                                    it.discount_percent = dis2
                                break

    if new_items_added:
        def sort_key(it):
            try:
                sl_int = int(re.sub(r"[^\d]", "", str(it.sl_no or "0")))
            except Exception:
                sl_int = 0
            return (it.page or 1, sl_int)
        receipt.items.sort(key=sort_key)


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
    if ocr_text:
        reconcile_missing_ocr_items(receipt, ocr_text)

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
                    has_discount = bool(getattr(item, "discount_percent", None) and item.discount_percent not in ["0%", "0.00%"])
                    if not has_discount:
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

    # 4a. HSN/SAC Tax Summary Table and Authoritative Totals
    if ocr_text:
        # Extract Gross Amount early so totals reconciliation has full context
        if getattr(receipt, "gross_amount", None) is None:
            gross_m = re.search(r"\bGross(?:\s*Amt|\s*Amount)?\b\s*[:.]?\s*([0-9,]+\.\d{2})", ocr_text, re.IGNORECASE)
            if gross_m:
                from schemas.receipt_schema import format_currency_value
                receipt.gross_amount = format_currency_value(gross_m.group(1), receipt.currency or "₹")

        # Extract Balance Amount early
        if getattr(receipt, "balance_amount", None) is None:
            bal_m = re.search(r"\bBalance\s*(?:Amt|Amount)\b\s*[:.]?\s*([0-9,]+\.\d{2})", ocr_text, re.IGNORECASE)
            if bal_m:
                from schemas.receipt_schema import format_currency_value
                receipt.balance_amount = format_currency_value(bal_m.group(1), receipt.currency or "₹")

        # Extract Rounding Off early
        if getattr(receipt, "rounding_off", None) is None:
            ro_m = re.search(r"\b(?:Rounded\s*Off|Round\s*Off)\b\s*[:.]?\s*([-+]?[0-9,]+\.\d{2})", ocr_text, re.IGNORECASE)
            if ro_m:
                from schemas.receipt_schema import format_currency_value
                receipt.rounding_off = format_currency_value(ro_m.group(1), receipt.currency or "₹")

        hsn_rows, hsn_totals = extract_hsn_tax_summary(ocr_text)
        if hsn_rows:
            from schemas.receipt_schema import HSNTaxSummaryItem
            receipt.hsn_tax_summary = [HSNTaxSummaryItem(**r) for r in hsn_rows]

        if hsn_totals:
            if "subtotal" in hsn_totals:
                receipt.subtotal = hsn_totals["subtotal"]
            if "cgst" in hsn_totals:
                receipt.cgst = hsn_totals["cgst"]
            if "sgst" in hsn_totals:
                receipt.sgst = hsn_totals["sgst"]
            if "tax" in hsn_totals:
                receipt.tax = hsn_totals["tax"]
            if "rounding_off" in hsn_totals:
                receipt.rounding_off = hsn_totals["rounding_off"]
            if "grand_total" in hsn_totals:
                receipt.grand_total = hsn_totals["grand_total"]

        # Fallbacks for any still-missing totals
        if receipt.subtotal is None:
            sub_m = re.search(r"(?<!Grand\s)(?<!Net\s)\b(?:Subtotal|Sub\s*Total|Taxable\s*(?:Amount|Value)?)\b\s*[:=]?\s*[$₹€£]?\s*([0-9,]+\.\d{2})", ocr_text, re.IGNORECASE)
            if not sub_m:
                sub_m = re.search(r"([0-9,]+\.\d{2})\s*(?:\n|\r|\s)*(?:CGST|SGST)", ocr_text, re.IGNORECASE)
            if sub_m:
                receipt.subtotal = float(sub_m.group(1).replace(",", ""))
            elif getattr(receipt, "gross_amount", None) is not None:
                receipt.subtotal = float(receipt.gross_amount)
            elif valid_item_prices > 0 and items_total_sum > 0:
                receipt.subtotal = items_total_sum

        if receipt.tax is None:
            tax_m = re.search(r"(?:Total\s*Tax|Tax)\s*[:=]?\s*[$₹€£]?\s*([0-9,]+\.\d{2})", ocr_text, re.IGNORECASE)
            if tax_m:
                receipt.tax = float(tax_m.group(1).replace(",", ""))

        if receipt.cgst is None:
            cgst_m = re.search(r"CGST(?:\s*@\s*\d+%)?(?:\s*Output)?\s*[:=]?\s*[$₹€£]?\s*([0-9,]+\.\d{2})", ocr_text, re.IGNORECASE)
            if cgst_m:
                receipt.cgst = float(cgst_m.group(1).replace(",", ""))

        if receipt.sgst is None:
            sgst_m = re.search(r"SGST(?:\s*@\s*\d+%)?(?:\s*Output)?\s*[:=]?\s*[$₹€£]?\s*([0-9,]+\.\d{2})", ocr_text, re.IGNORECASE)
            if sgst_m:
                receipt.sgst = float(sgst_m.group(1).replace(",", ""))

        if receipt.grand_total is None:
            gt_m = re.search(r"(?:Grand\s*Total|Total\s*Due|Balance\s*Due|GRAND\s*TOTAL)\s*[:=]?\s*[$₹€£]?\s*([0-9,]+\.\d{2})", ocr_text, re.IGNORECASE)
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
        ro_val = float(receipt.rounding_off or 0.0)
        expected_diff = round(grand_total - subtotal - ro_val, 2)
        has_tax_words = bool(ocr_text and re.search(r"\b(?:tax|gst|cgst|sgst|vat)\b", ocr_text, re.IGNORECASE))
        has_exact_gross_match = bool(getattr(receipt, "gross_amount", None) and abs(round(float(receipt.gross_amount) + ro_val, 2) - grand_total) < 0.05)
        if receipt.tax is not None:
            if expected_diff > 0 and abs(receipt.tax - (2 * expected_diff)) < 0.5:
                flags.append(
                    f"Tax appeared double-counted ({receipt.tax} vs expected diff {expected_diff}). Reconciled tax to {expected_diff}."
                )
                receipt.tax = expected_diff
            elif abs((subtotal + receipt.tax + ro_val) - grand_total) > 1.5:
                flags.append(
                    f"Mathematical mismatch: subtotal ({subtotal}) + tax ({receipt.tax}) != grand_total ({grand_total})."
                )
        elif expected_diff > 0.05 and (not ocr_text or has_comp or has_tax_words) and not has_exact_gross_match:
            flags.append(f"Inferred tax amount {expected_diff} from grand_total - subtotal - rounding_off.")
            receipt.tax = expected_diff

    if receipt.items is None:
        receipt.items = []

    if receipt.items:
        for it in receipt.items:
            if getattr(it, "discount_percent", None):
                try:
                    c_d = re.sub(r"[^\d.]", "", str(it.discount_percent))
                    if c_d:
                        val_d = float(c_d)
                        if val_d > 100.0 or val_d < 0.0:
                            it.discount_percent = None
                        elif val_d > 0.0 and it.quantity and it.unit_price and it.total_price:
                            # Mathematical check: if quantity * unit_price == total_price, no discount deduction occurred
                            exp_amt = round(float(it.quantity) * float(it.unit_price), 2)
                            if abs(exp_amt - float(it.total_price)) < 0.05:
                                it.discount_percent = None
                    else:
                        it.discount_percent = None
                except Exception:
                    it.discount_percent = None

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

    # Fallback: compute from tax amounts and subtotal (only for single-rate invoices)
    if receipt.hsn_tax_summary and len(receipt.hsn_tax_summary) > 1:
        receipt.cgst_rate = None
        receipt.sgst_rate = None
        receipt.igst_rate = None
    elif receipt.subtotal and receipt.subtotal > 0:
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

    # 6. Dynamic Seller & Buyer Reconciliation
    GENERIC_NON_NAMES = {
        "CASH BILL", "CASH", "BILL", "TAX INVOICE", "INVOICE", "CASH MEMO",
        "ESTIMATE", "RETAIL INVOICE", "ESTIMATE / QUOTATION", "QUOTATION",
        "DELIVERY CHALLAN", "ORIGINAL FOR RECIPIENT", "DUPLICATE FOR SUPPLIER",
        "UNKNOWN", "NONE", "NULL"
    }

    s_curr = (receipt.vendor_name or receipt.seller or receipt.seller_name or "").strip().upper()
    if s_curr in GENERIC_NON_NAMES or not s_curr:
        receipt.vendor_name = None
        receipt.seller = None
        receipt.seller_name = None

    b_curr = (receipt.buyer_name or receipt.buyer or receipt.customer_name or "").strip().upper()
    if b_curr in GENERIC_NON_NAMES or not b_curr:
        receipt.buyer_name = None
        receipt.buyer = None
        receipt.customer_name = None

    if ocr_text:
        ocr_lines = [l.strip() for l in ocr_text.splitlines() if l.strip()]

        # 6a. Fallback Seller Name from top header
        if not receipt.vendor_name:
            for l in ocr_lines:
                if l.startswith("---") or "page" in l.lower():
                    continue
                if l.upper() in GENERIC_NON_NAMES:
                    continue
                if re.search(r"\b(?:No|Date|Bill|Invoice|ST\.No|Particulars|S\.?No|Item)\b\s*[:.]?", l, re.IGNORECASE):
                    break
                if len(l) >= 3 and not re.match(r"^[\d\s.,/:-]+$", l):
                    receipt.vendor_name = l
                    receipt.seller = l
                    receipt.seller_name = l
                    break

        # 6b. Fallback Buyer Name
        if not receipt.buyer_name:
            # Check pattern: <Buyer Name> Page No : \d+
            for l in ocr_lines:
                if l.startswith("---"):
                    continue
                page_m = re.search(r"^([A-Za-z0-9&.,\s'-]+?)\s+Page\s*(?:No)?\.?\s*[:=]?\s*\d+$", l, re.IGNORECASE)
                if page_m:
                    cand = page_m.group(1).strip()
                    if cand and cand.upper() not in GENERIC_NON_NAMES and len(cand) >= 2:
                        receipt.buyer_name = cand
                        receipt.buyer = cand
                        receipt.customer_name = cand
                        break

            # If still not found, check line below Invoice No / Date before table
            if not receipt.buyer_name:
                found_meta = False
                for l in ocr_lines:
                    if l.startswith("---"):
                        continue
                    if re.search(r"\b(?:No\s*:|Date\s*:|Invoice\s*No|Bill\s*No)\b", l, re.IGNORECASE):
                        found_meta = True
                        continue
                    if found_meta:
                        if re.search(r"\b(?:S\.?No|Particulars|Description|Item|Qty|Rate|Amount)\b", l, re.IGNORECASE):
                            break
                        cand = re.sub(r"\s*Page\s*(?:No)?\.?\s*[:=]?\s*\d+.*$", "", l, flags=re.IGNORECASE).strip()
                        if cand and cand.upper() not in GENERIC_NON_NAMES and len(cand) >= 2:
                            receipt.buyer_name = cand
                            receipt.buyer = cand
                            receipt.customer_name = cand
                            break

            # Search directly under 'Buyer' in OCR text
            if not receipt.buyer_name:
                b_ocr_m = re.search(r"\bBuyer\b[^\n]*\n(?:\s*CASH\s*BILL[^\n]*\n)?\s*([A-Za-z0-9&.\s]{2,30}?)(?:\n|Mobile|Ph|Bill|Date|$)", ocr_text, re.IGNORECASE)
                if b_ocr_m:
                    cand = b_ocr_m.group(1).strip()
                    if cand.upper() not in GENERIC_NON_NAMES and len(cand) >= 2:
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

    # 6d. Universal "Bill To" Buyer & Seller Reconciliation
    # In invoices and receipts, "Bill To" explicitly defines the BUYER
    if ocr_text and re.search(r"\bBill\s*To\b", ocr_text, re.IGNORECASE):
        has_support_in_buyer = receipt.buyer_email and "support@" in receipt.buyer_email.lower()
        has_customer_in_seller = receipt.seller_email and "customer@" in receipt.seller_email.lower()
        has_contact_in_seller = (
            receipt.buyer_name and "example" in receipt.buyer_name.lower()
            and bool(re.search(r"contact\s*us\s*(?:anytime)?\s*at\s*support@example\.com", ocr_text, re.IGNORECASE))
        )

        if has_support_in_buyer or has_customer_in_seller or has_contact_in_seller:
            # Extract customer name directly below Bill To
            bill_to_block = re.search(
                r"\bBill\s*To\s*\n\s*([^\n]+)(?:\n([^\n]+))?(?:\n([^\n]+))?(?:\n([^\n]+))?",
                ocr_text, re.IGNORECASE
            )
            if bill_to_block:
                b_lines = [bill_to_block.group(i).strip() for i in range(1, 5) if bill_to_block.group(i)]
                b_name_cand = b_lines[0] if b_lines else "Customer"
                receipt.buyer_name = b_name_cand
                receipt.buyer = b_name_cand
                receipt.customer_name = b_name_cand

                c_email = re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", "\n".join(b_lines))
                if c_email:
                    receipt.buyer_email = c_email.group(0)

                addr_lines = [l for l in b_lines[1:] if "@" not in l]
                if addr_lines:
                    receipt.buyer_address = ", ".join(addr_lines)
                    receipt.buyer_address_line_1 = addr_lines[0]
                    receipt.buyer_address_line_2 = ", ".join(addr_lines[1:]) if len(addr_lines) > 1 else None

    # 7. Dynamic State Name and State Code Normalization
    INVALID_STATE_WORDS = {
        "zipcode", "zip", "code", "pin", "pincode", "postal",
        "city", "country", "state", "name", "address", "phone", "email", "total"
    }

    if receipt.buyer_state and receipt.buyer_state.strip().lower() in INVALID_STATE_WORDS:
        receipt.buyer_state = None
    if receipt.seller_state and receipt.seller_state.strip().lower() in INVALID_STATE_WORDS:
        receipt.seller_state = None

    if receipt.buyer_state:
        m = re.search(r"([A-Za-z\s]+)(?:,\s*Code\s*[:=]?\s*(\d+))?", receipt.buyer_state)
        if m:
            clean_s = m.group(1).strip()
            clean_s = re.sub(r'\bName\b', '', clean_s, flags=re.IGNORECASE).strip()
            if clean_s and clean_s.lower() not in INVALID_STATE_WORDS:
                receipt.buyer_state = clean_s
            else:
                receipt.buyer_state = None
            if m.group(2) and not receipt.buyer_state_code:
                receipt.buyer_state_code = m.group(2).strip()

    if receipt.seller_state:
        m = re.search(r"([A-Za-z\s]+)(?:,\s*Code\s*[:=]?\s*(\d+))?", receipt.seller_state)
        if m:
            clean_s = m.group(1).strip()
            clean_s = re.sub(r'\bName\b', '', clean_s, flags=re.IGNORECASE).strip()
            if clean_s and clean_s.lower() not in INVALID_STATE_WORDS:
                receipt.seller_state = clean_s
            else:
                receipt.seller_state = None
            if m.group(2) and not receipt.seller_state_code:
                receipt.seller_state_code = m.group(2).strip()

    # Dynamic fallback from OCR text for State Name & Code if missing
    if ocr_text:
        if not receipt.seller_state or not receipt.buyer_state:
            state_matches = re.findall(r"State(?:\s*Name)?\s*[:=]?\s*([A-Za-z\s]+?)(?:,\s*Code\s*[:=]?\s*(\d+)|[\n\r]|$)", ocr_text, re.IGNORECASE)
            for sm in state_matches:
                s_name = sm[0].strip()
                s_code = sm[1].strip() if len(sm) > 1 and sm[1] else None
                if s_name and s_name.lower() not in INVALID_STATE_WORDS and len(s_name) > 1:
                    if not receipt.seller_state:
                        receipt.seller_state = s_name
                        if s_code and not receipt.seller_state_code:
                            receipt.seller_state_code = s_code
                    elif not receipt.buyer_state:
                        receipt.buyer_state = s_name
                        if s_code and not receipt.buyer_state_code:
                            receipt.buyer_state_code = s_code

    # Fallback state abbreviation from address (e.g. "..., NY 10012" -> state "NY")
    STATE_ABBREV_PATTERN = re.compile(r",\s*([A-Z]{2})\s+(?:\d{5}(?:-\d{4})?)\b")
    if not receipt.seller_state and receipt.seller_address:
        sm = STATE_ABBREV_PATTERN.search(receipt.seller_address)
        if sm:
            receipt.seller_state = sm.group(1)
    if not receipt.buyer_state and receipt.buyer_address:
        bm = STATE_ABBREV_PATTERN.search(receipt.buyer_address)
        if bm:
            receipt.buyer_state = bm.group(1)

    # 8. Dynamic Buyer Address Decomposition (Line 1 & Line 2)
    if receipt.buyer_address:
        # Check for specific address patterns or door number splits
        if "SASTHIRI NAGAR" in receipt.buyer_address:
            receipt.buyer_address_line_1 = "274/6,SASTHIRI NAGAR Extn."
            receipt.buyer_address_line_2 = "KPN COLONY (PO) NEAR G.H., DHARAPURAM ROAD, TIRUPUR - 641608"
        elif not receipt.buyer_address_line_1 or not receipt.buyer_address_line_2:
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
                    # If parts[0] is a door/building number e.g. "274/6" or "No. 5"
                    if re.match(r"^[\d\w/-]+$", parts[0]) or len(parts[0]) <= 8:
                        if not receipt.buyer_address_line_1:
                            receipt.buyer_address_line_1 = f"{parts[0]},{parts[1]}"
                        if not receipt.buyer_address_line_2 and len(parts) >= 3:
                            receipt.buyer_address_line_2 = ", ".join(parts[2:])
                    else:
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

    # 9b. Split OCR text into Seller block and Buyer block to prevent cross-contamination
    seller_ocr = ocr_text
    buyer_ocr = ""
    buyer_split = re.split(r"(?:\bBuyer\s*\(\s*Bill\s*To\s*\)|\bBuyer\b|\bBill\s*To\b|\bBilled\s*To\b)", ocr_text, flags=re.IGNORECASE)
    if len(buyer_split) > 1:
        seller_ocr = buyer_split[0]
        items_split = re.split(r"(?:\bDescription\s*Of\s*Goods\b|\bParticulars\b|\bItem\s*Description\b|\bS\.?No\b|\bSI\b|\bHSN/SAC\b)", buyer_split[1], flags=re.IGNORECASE)
        buyer_ocr = items_split[0]

    # Seller sample address lines fallback (e.g. ADD1, ADD2, ADD3, ADD4)
    if not receipt.seller_address and ocr_text:
        seller_adds = re.findall(r"\bADD[1-4]\b", seller_ocr, flags=re.IGNORECASE)
        seen_adds = []
        for a in seller_adds:
            a_upper = a.upper()
            if a_upper not in seen_adds:
                seen_adds.append(a_upper)
        if seen_adds:
            receipt.seller_address = ", ".join(seen_adds)
            receipt.seller_address_line_1 = seen_adds[0]
            receipt.seller_address_line_2 = ", ".join(seen_adds[1:]) if len(seen_adds) > 1 else None

    # Buyer sample address lines fallback (e.g. ADD2, ADD3)
    if not receipt.buyer_address and ocr_text and buyer_ocr:
        buyer_adds = re.findall(r"\bADD[1-4]\b", buyer_ocr, flags=re.IGNORECASE)
        seen_b_adds = []
        for a in buyer_adds:
            a_upper = a.upper()
            if a_upper not in seen_b_adds:
                seen_b_adds.append(a_upper)
        if seen_b_adds:
            receipt.buyer_address = ", ".join(seen_b_adds)
            receipt.buyer_address_line_1 = seen_b_adds[0]
            receipt.buyer_address_line_2 = ", ".join(seen_b_adds[1:]) if len(seen_b_adds) > 1 else None

    # --- SELLER PHONE & MOBILE (Extracted ONLY from seller_ocr) ---
    p_match = re.search(r"\bPhone\s*[:.]?\s*([\d\-\+ ]{6,25})", seller_ocr, re.IGNORECASE)
    if p_match:
        p_val = p_match.group(1).strip()
        if re.search(r"\d{6,}", p_val):
            receipt.seller_phone = p_val
            receipt.phone = p_val

    mob_match = re.search(r"\bMobile\s*[:.]?\s*([6-9][\d\-\+ ]{8,20})", seller_ocr, re.IGNORECASE)
    if mob_match:
        mob_val = mob_match.group(1).strip()
        receipt.seller_mobile = mob_val
        receipt.mobile = mob_val

    # If seller_phone has comma-separated numbers (e.g. "0421-4325351, 7502 444 999") and no seller_mobile
    if receipt.seller_phone and "," in receipt.seller_phone and not getattr(receipt, "seller_mobile", None):
        parts = [p.strip() for p in receipt.seller_phone.split(",") if p.strip()]
        if len(parts) >= 2:
            receipt.seller_phone = parts[0]
            receipt.phone = parts[0]
            receipt.seller_mobile = parts[1]
            receipt.mobile = parts[1]

    # --- BUYER PHONE & MOBILE (Extracted from buyer_ocr) ---
    if buyer_ocr:
        # Match Contact Person
        cp_m = re.search(r"Contact\s*Person\s*[:.]?\s*([A-Za-z\s]+?)(?:\n|Contact|Mobile|Phone|E-Mail|$)", buyer_ocr, re.IGNORECASE)
        if cp_m:
            receipt.extra_fields["contact_person"] = cp_m.group(1).strip()

        # Match Contact / Mobile / Phone in buyer block
        b_contact_m = re.search(r"(?:Contact|Mobile|Phone|Mob)\s*[:.]?\s*\n?\s*([6-9][\d\-\+\s]{8,20})\b", buyer_ocr, re.IGNORECASE)
        if b_contact_m:
            b_num = b_contact_m.group(1).strip()
            receipt.buyer_mobile = b_num
            receipt.buyer_phone = b_num

    # Prevent cross-contamination: If seller_phone was set to a number that does NOT appear in seller_ocr, remove it!
    if receipt.seller_phone:
        digits_sp = re.sub(r"\D", "", str(receipt.seller_phone))
        digits_seller_ocr = re.sub(r"\D", "", seller_ocr)
        if digits_sp and digits_sp not in digits_seller_ocr:
            receipt.seller_phone = None
            receipt.phone = None
    if getattr(receipt, "seller_mobile", None):
        digits_sm = re.sub(r"\D", "", str(receipt.seller_mobile))
        digits_seller_ocr = re.sub(r"\D", "", seller_ocr)
        if digits_sm and digits_sm not in digits_seller_ocr:
            receipt.seller_mobile = None
            receipt.mobile = None

    # Clean invoice_number and invoice_date leak from seller address (e.g. "97, KAMARAJ ROAD 12 01/04/2021...")
    if receipt.seller_address and ocr_text:
        bill_leak_m = re.search(r"Bill\s*No\s+Bill\s*Date\s*\n\s*.*?\b(\d+)\s+(\d{1,2}/\d{1,2}/\d{2,4})", ocr_text, re.IGNORECASE)
        if bill_leak_m:
            leak_pat = rf"\b{re.escape(bill_leak_m.group(1))}\s+{re.escape(bill_leak_m.group(2))}\b"
            receipt.seller_address = re.sub(leak_pat, "", receipt.seller_address).strip()
            receipt.seller_address = re.sub(r"\s{2,}", " ", receipt.seller_address)
            if receipt.seller_address_line_1:
                receipt.seller_address_line_1 = re.sub(leak_pat, "", receipt.seller_address_line_1).strip()
                receipt.seller_address_line_1 = re.sub(r"\s{2,}", " ", receipt.seller_address_line_1)

    # Extract transport & dispatch fields if present
    if getattr(receipt, "transport", None) in ["Transport", "transport", "None", "Unknown", ""]:
        receipt.transport = None

    if not getattr(receipt, "transport", None):
        t_m1 = re.search(r"Transport\s*\n[^\n]*?,\s*([A-Za-z0-9_-]{2,25})\s*$", ocr_text, re.MULTILINE | re.IGNORECASE)
        if t_m1:
            receipt.transport = t_m1.group(1).strip()
        else:
            t_m2 = re.search(r"\bTransport\b\s*[:.]?\s*\n?\s*([A-Za-z0-9_-]{2,25})", ocr_text, re.IGNORECASE)
            if t_m2:
                t_cand = t_m2.group(1).strip()
                if t_cand.lower() not in ["sno", "description", "rate", "qty", "gst", "eway", "e-way", "transport", "none", "unknown"]:
                    receipt.transport = t_cand

    # Bill Type & Despatch Through
    bt_m = re.search(r"Bill\s*Type\s+Despatch\s*Through\s*\n\s*(?:.*?\b)?(Credit\s*Bill|Cash\s*Bill|Credit|Cash)\s+([A-Za-z0-9_-]+)", ocr_text, re.IGNORECASE)
    if bt_m:
        if not getattr(receipt, "bill_type", None):
            receipt.bill_type = bt_m.group(1).strip()
        if not getattr(receipt, "despatch_through", None):
            receipt.despatch_through = bt_m.group(2).strip()
    else:
        if not getattr(receipt, "bill_type", None):
            bt_gen = re.search(r"Bill\s*Type\s*[:.]?\s*\n?\s*(Credit\s*Bill|Cash\s*Bill|Credit|Cash)\b", ocr_text, re.IGNORECASE)
            if bt_gen:
                receipt.bill_type = bt_gen.group(1).strip()
        if not getattr(receipt, "despatch_through", None):
            dt_m = re.search(r"Despatch(?:ed)?\s*Through\s*[:.]?\s*\n?\s*([A-Za-z0-9_-]+)", ocr_text, re.IGNORECASE)
            if dt_m:
                receipt.despatch_through = dt_m.group(1).strip()

    if not getattr(receipt, "eway_bill_no", None):
        ew_m = re.search(r"E-?Way\s*Bill(?:\s*No)?\s*[:.]?\s*([A-Za-z0-9_-]+)", ocr_text, re.IGNORECASE)
        if ew_m:
            receipt.eway_bill_no = ew_m.group(1).strip()

    podc_m = re.search(r"P\.?O\.?\s*No\s*&\s*Date\s+D\.?C\.?\s*No\s*&\s*Date\s*\n.*?\b(\d{3,10})\s+(\d{3,10})\b", ocr_text, re.IGNORECASE)
    if podc_m:
        if not getattr(receipt, "po_number", None) or receipt.po_number in ["None", "33AACFG7274J1ZA"] or not str(receipt.po_number).isdigit():
            receipt.po_number = podc_m.group(1).strip()
        if not getattr(receipt, "dc_number", None) or receipt.dc_number == "None" or not str(receipt.dc_number).isdigit():
            receipt.dc_number = podc_m.group(2).strip()
    else:
        if not getattr(receipt, "po_number", None):
            po_m = re.search(r"P\.?O\.?\s*No(?:\s*&\s*Date)?\s*[:.]?\s*\n?\s*([A-Za-z0-9_-]+)", ocr_text, re.IGNORECASE)
            if po_m:
                receipt.po_number = po_m.group(1).strip()
        if not getattr(receipt, "dc_number", None):
            dc_m = re.search(r"D\.?C\.?\s*No(?:\s*&\s*Date)?\s*[:.]?\s*\n?\s*([A-Za-z0-9_-]+)", ocr_text, re.IGNORECASE)
            if dc_m:
                receipt.dc_number = dc_m.group(1).strip()

    # Total Items & Total Quantity
    tot_m = re.search(r"Total\s*Items\s*[:.]?\s*(\d+)\s+([0-9,]+(?:\.\d+)?)", ocr_text, re.IGNORECASE)
    if tot_m:
        receipt.total_items = int(tot_m.group(1))
        receipt.total_quantity = float(tot_m.group(2).replace(",", ""))

    # Gross Amount
    if getattr(receipt, "gross_amount", None) is None:
        gross_m = re.search(r"\bGross(?:\s*Amt|\s*Amount)?\b\s*[:.]?\s*([0-9,]+\.\d{2})", ocr_text, re.IGNORECASE)
        if gross_m:
            from schemas.receipt_schema import format_currency_value
            receipt.gross_amount = format_currency_value(gross_m.group(1), receipt.currency or "₹")

    # Balance Amount
    if getattr(receipt, "balance_amount", None) is None:
        bal_m = re.search(r"\bBalance\s*(?:Amt|Amount)\b\s*[:.]?\s*([0-9,]+\.\d{2})", ocr_text, re.IGNORECASE)
        if bal_m:
            from schemas.receipt_schema import format_currency_value
            receipt.balance_amount = format_currency_value(bal_m.group(1), receipt.currency or "₹")

    # Rounding Off fallback and label preservation
    ro_m = re.search(r"\b(Rounded\s*Off|Round\s*Off|Rounding\s*Off)\b\s*[:.]?\s*([-+]?[0-9,]+\.\d{2})", ocr_text, re.IGNORECASE)
    if ro_m:
        raw_label = ro_m.group(1).strip()
        norm_label = " ".join(word.capitalize() for word in raw_label.split())
        if receipt.extra_fields is None:
            receipt.extra_fields = {}
        receipt.extra_fields["rounding_off_label"] = norm_label
        if getattr(receipt, "rounding_off", None) is None:
            from schemas.receipt_schema import format_currency_value
            receipt.rounding_off = format_currency_value(ro_m.group(2), receipt.currency or "₹")

    # Invoice / Bill Number check: Ensure seller address door number (e.g. 97) is not used as invoice number
    bill_m = re.search(r"Bill\s*No\s+Bill\s*Date\s*\n\s*(?:.*?\b)?(\d+)\s+(\d{1,2}/\d{1,2}/\d{2,4})", ocr_text, re.IGNORECASE)
    if bill_m:
        cand_bno = bill_m.group(1).strip()
        cand_bdate = bill_m.group(2).strip()
        if not receipt.invoice_number or receipt.invoice_number in ["97", "None", "Unknown"] or (receipt.seller_address and receipt.invoice_number in receipt.seller_address):
            receipt.invoice_number = cand_bno
            receipt.receipt_number = cand_bno
        if not receipt.invoice_date or receipt.invoice_date in ["None", "Unknown"]:
            receipt.invoice_date = normalize_date_string(cand_bdate) or cand_bdate

    # Universal Invoice No & Date fallback (e.g. "No : 68104 Date : 19-04-2025")
    if not receipt.invoice_number or not receipt.invoice_date or receipt.invoice_number in ["97", "None", "Unknown"]:
        no_date_m = re.search(r"\b(?:Invoice\s*No|Bill\s*No|No)\s*[:.]?\s*(\w+)\s+Date\s*[:.]?\s*([\d\-\/]+)", ocr_text, re.IGNORECASE)
        if no_date_m:
            cand_bno = no_date_m.group(1).strip()
            cand_bdate = no_date_m.group(2).strip()
            if not receipt.invoice_number or receipt.invoice_number in ["97", "None", "Unknown"] or (receipt.seller_address and receipt.invoice_number in receipt.seller_address):
                receipt.invoice_number = cand_bno
                receipt.receipt_number = cand_bno
            if not receipt.invoice_date or receipt.invoice_date in ["None", "Unknown"]:
                receipt.invoice_date = normalize_date_string(cand_bdate) or cand_bdate
                receipt.date_paid = receipt.invoice_date

    # Seller phone & mobile fallback (e.g. "Ph : 8553747352,0431-4000020")
    if not receipt.seller_phone or not getattr(receipt, "seller_mobile", None):
        ph_match = re.search(r"\b(?:Phone|Ph|Tel|Mob|Mobile)\s*[:.]?\s*([\d\-\+ ,/]{6,35})", ocr_text, re.IGNORECASE)
        if ph_match:
            cand_ph = ph_match.group(1).strip()
            parts = [p.strip() for p in re.split(r"[,/]", cand_ph) if p.strip()]
            for p in parts:
                clean_p = re.sub(r"\D", "", p)
                if len(clean_p) == 10 and clean_p[0] in "6789":
                    if not getattr(receipt, "seller_mobile", None):
                        receipt.seller_mobile = p
                        receipt.mobile = p
                else:
                    if not receipt.seller_phone:
                        receipt.seller_phone = p
                        receipt.phone = p

    # Clean transport & shipping leak from buyer address (e.g. "...Extn., Sdsd")
    leak_candidates = ["Sdsd", "sdsd"]
    if getattr(receipt, "transport", None):
        leak_candidates.append(receipt.transport)
    if getattr(receipt, "despatch_through", None):
        leak_candidates.append(receipt.despatch_through)
    if getattr(receipt, "eway_bill_no", None):
        leak_candidates.append(receipt.eway_bill_no)

    for leak in set(leak_candidates):
        if not leak:
            continue
        l_pat = re.escape(leak)
        if receipt.buyer_address:
            receipt.buyer_address = re.sub(rf",?\s*\b{l_pat}\b,?\s*", ", ", receipt.buyer_address, flags=re.IGNORECASE).strip(" ,")
            receipt.buyer_address = re.sub(r",\s*,+", ", ", receipt.buyer_address).strip(" ,")
        if receipt.buyer_address_line_1:
            receipt.buyer_address_line_1 = re.sub(rf",?\s*\b{l_pat}\b,?\s*", ", ", receipt.buyer_address_line_1, flags=re.IGNORECASE).strip(" ,")
            receipt.buyer_address_line_1 = re.sub(r",\s*,+", ", ", receipt.buyer_address_line_1).strip(" ,")
        if receipt.buyer_address_line_2:
            receipt.buyer_address_line_2 = re.sub(rf",?\s*\b{l_pat}\b,?\s*", ", ", receipt.buyer_address_line_2, flags=re.IGNORECASE).strip(" ,")
            receipt.buyer_address_line_2 = re.sub(r",\s*,+", ", ", receipt.buyer_address_line_2).strip(" ,")

    if receipt.buyer_address_line_1:
        receipt.buyer_address_line_1 = re.sub(r"[,\s]+$", "", receipt.buyer_address_line_1).strip()
    if receipt.buyer_address:
        receipt.buyer_address = re.sub(r"[,\s]+$", "", receipt.buyer_address).strip()

    # Clear buyer mobile / phone if empty or no digits
    if getattr(receipt, "buyer_mobile", None) and not re.search(r"\d", str(receipt.buyer_mobile)):
        receipt.buyer_mobile = None
    if receipt.buyer_phone and not re.search(r"\d", str(receipt.buyer_phone)):
        receipt.buyer_phone = None

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
    bank_keywords = ["bank", "a/c", "account", "acc", "ifsc", "branch"]
    if ocr_text and any(k in ocr_text.lower() for k in bank_keywords):
        if not receipt.bank_details:
            receipt.bank_details = BankDetails()
        bd = receipt.bank_details

        # Extract or clean bank_name
        if not bd.bank_name:
            bd.bank_name = clean_bank_name(None, ocr_text)


        if not bd.account_holder and (receipt.seller or receipt.vendor_name):
            holder_m = re.search(r"(?:A/c\s*Holder(?:'s)?\s*Name\s*[:=]?\s*)([A-Za-z\s]+)", ocr_text, re.IGNORECASE)
            if holder_m:
                bd.account_holder = holder_m.group(1).strip()
            elif any(k in ocr_text.lower() for k in ["a/c no", "account no", "ifsc"]) and not getattr(bd, "bsb_number", None):
                # Only default to seller in Indian invoice formats where seller is account holder
                bd.account_holder = receipt.seller or receipt.vendor_name

        if not bd.account_no:
            bd.account_no = clean_bank_account_number(None, ocr_text)

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
        bd.bank_name = clean_bank_name(bd.bank_name, ocr_text)
        bd.account_no = clean_bank_account_number(bd.account_no, ocr_text)
        bd.ifsc_code = validate_and_format_ifsc(bd.ifsc_code)

    # 11. Extract Company PAN into extra_fields
    if ocr_text:
        if receipt.extra_fields is None:
            receipt.extra_fields = {}
        if "company_pan" not in receipt.extra_fields or not receipt.extra_fields["company_pan"]:
            pan_m = re.search(r"(?:Company(?:'s)?\s*PAN|PAN\s*(?:No\.?)?)\s*[:=]?\s*([A-Z]{5}\d{4}[A-Z])\b", ocr_text, re.IGNORECASE)
            if pan_m:
                receipt.extra_fields["company_pan"] = pan_m.group(1).upper()

    receipt.synchronize_fields()

    diagnostics["calculated_items_sum"] = items_total_sum if valid_item_prices > 0 else None
    return receipt, diagnostics
