import re
from datetime import datetime
from typing import Optional, Tuple

from core.constants import CURRENCY_SYMBOLS


MONTH_MAP = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12
}


def normalize_date_string(date_str: str) -> Optional[str]:
    """Normalize various date formats (DD/MM/YYYY, DD-MMM-YY, YYYY-MM-DD) into DD-MM-YYYY."""
    if not date_str:
        return None

    cleaned = date_str.strip()
    # Remove time if present (e.g., "26/09/2026 10:47")
    cleaned = re.split(r"\s+", cleaned)[0]
    cleaned = cleaned.replace(".", "-").replace("/", "-")

    # Match YYYY-MM-DD
    m_iso = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})$", cleaned)
    if m_iso:
        y, m, d = int(m_iso.group(1)), int(m_iso.group(2)), int(m_iso.group(3))
        try:
            dt = datetime(y, m, d)
            return dt.strftime("%d-%m-%Y")
        except Exception:
            return None

    # Match DD-MMM-YY or DD-MMM-YYYY (e.g. 6-Oct-26 or 06-Oct-2026)
    m_alpha = re.match(r"^(\d{1,2})-([A-Za-z]{3,9})-(\d{2,4})$", cleaned)
    if m_alpha:
        d = int(m_alpha.group(1))
        month_str = m_alpha.group(2)[:3].lower()
        y = int(m_alpha.group(3))
        if y < 100:
            y += 2000
        if month_str in MONTH_MAP:
            m = MONTH_MAP[month_str]
            try:
                dt = datetime(y, m, d)
                return dt.strftime("%d-%m-%Y")
            except ValueError:
                return None

    # Match DD-MM-YYYY or MM-DD-YYYY
    m_numeric = re.match(r"^(\d{1,2})-(\d{1,2})-(\d{2,4})$", cleaned)
    if m_numeric:
        p1 = int(m_numeric.group(1))
        p2 = int(m_numeric.group(2))
        y = int(m_numeric.group(3))
        if y < 100:
            y += 2000

        # Disambiguate day vs month
        if p1 > 12:  # p1 must be day (DD-MM-YYYY)
            d, m = p1, p2
        elif p2 > 12:  # p2 must be day (MM-DD-YYYY)
            m, d = p1, p2
        else:
            # Default to DD-MM-YYYY for receipt conventions
            d, m = p1, p2

        try:
            dt = datetime(y, m, d)
            return dt.strftime("%d-%m-%Y")
        except ValueError:
            return None

    return None


def detect_currency(text: str) -> Optional[str]:
    """Detect currency from text symbols or abbreviations."""
    lower_text = text.lower()
    for symbol, code in CURRENCY_SYMBOLS.items():
        if symbol in lower_text:
            return code
    return None


def extract_gstin(text: str) -> Optional[str]:
    """Extract Indian GSTIN pattern: 2 digits, 5 letters, 4 digits, 1 letter, 1 alphanumeric, 'Z', 1 alphanumeric."""
    match = re.search(r"\b\d{2}[A-Z]{5}\d{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}\b", text.upper())
    return match.group(0).upper() if match else None


def validate_and_format_gstin(val: Optional[str]) -> Optional[str]:
    """Validate and format GSTIN/UIN: strictly 15 alphanumeric characters in CAPITAL LETTERS only."""
    if not val:
        return None
    cleaned = re.sub(r"[^A-Za-z0-9]", "", str(val)).strip().upper()
    if len(cleaned) == 15 and re.match(r"^\d{2}[A-Z]{5}\d{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}$", cleaned):
        return cleaned
    return None


def validate_and_format_ifsc(val: Optional[str]) -> Optional[str]:
    """Validate and format IFS Code: strictly 11 alphanumeric characters in CAPITAL LETTERS only.
    
    Standard Indian IFSC format: 4 alphabetic bank code, 5th character '0', 6 alphanumeric branch code.
    Universal OCR error corrections:
    - 5th character forced to digit '0' (OCR often reads 'O', 'o', 'b', 'Q', 'D')
    - Letters 'O' / 'o' in branch suffix replaced by digit '0' when surrounded by numbers.
    """
    if not val:
        return None
    cleaned = re.sub(r"[^A-Za-z0-9]", "", str(val)).strip().upper()
    if len(cleaned) == 11:
        prefix = cleaned[:4]
        suffix = cleaned[5:]

        # Standard Indian IFSC 5th character is always digit 0
        if prefix.isalpha():
            # If OCR read 'OB' or similar in position 4-5
            suffix_clean = suffix.replace("O", "0")
            candidate = f"{prefix}0{suffix_clean}"
            if re.match(r"^[A-Z]{4}0[A-Z0-9]{6}$", candidate):
                return candidate

    # If slightly mangled length due to OCR (e.g. 10 or 12 chars)
    if 10 <= len(cleaned) <= 12 and cleaned[:4].isalpha():
        prefix = cleaned[:4]
        rest = cleaned[4:].replace("O", "0").replace("o", "0")
        # Ensure 5th char is '0'
        if not rest.startswith("0"):
            rest = "0" + rest.lstrip("0")
        if len(rest) > 7:
            rest = rest[:7]
        elif len(rest) < 7:
            rest = rest.ljust(7, "0")
        candidate = f"{prefix}{rest}"
        if re.match(r"^[A-Z]{4}0[A-Z0-9]{6}$", candidate):
            return candidate

    return cleaned if len(cleaned) == 11 and re.match(r"^[A-Z]{4}0[A-Z0-9]{6}$", cleaned) else None


def clean_bank_account_number(val: Optional[str], ocr_text: str = "") -> Optional[str]:
    """Clean and validate bank account number, supporting international spaced formats (e.g. '1234 1234')
    and filtering out seal/stamp ink artifacts universally.
    """
    # First priority: if val provided, clean and validate it
    if val:
        s = str(val).strip()
        # Strip prefixes like ACC #, A/c No, Account No, CC Account, etc.
        s_clean = re.sub(
            r"^(?:ACC\s*#?|A/C\s*(?:No\.?|#)?|Account\s*(?:No\.?|#)?|Acc\.?\s*(?:No\.?|#)?|CC\s*Account)\s*[:=#]?\s*",
            "",
            s,
            flags=re.IGNORECASE
        ).strip()
        digits_only = re.sub(r"\D", "", s_clean)
        # Bank accounts internationally range from 6 to 24 digits (e.g. AU 8 digits '1234 1234', UK 8, US 8-12, IN 9-18)
        if 6 <= len(digits_only) <= 24:
            if re.match(r"^[0-9\s-]+$", s_clean):
                return s_clean
            return digits_only

    # Second priority: look for unstamped account number in OCR text using universal account number patterns
    if ocr_text:
        unstamped_match = re.search(
            r"(?:ACC(?:\s*#|\s*No\.?)?|A/C\s*(?:No\.?|#)?|Account\s*(?:No\.?|#)?|CC Account)\s*[:=#]?\s*([0-9\s-]{6,24})\b",
            ocr_text,
            re.IGNORECASE
        )
        if unstamped_match:
            cand = unstamped_match.group(1).strip()
            digits = re.sub(r"\D", "", cand)
            if 6 <= len(digits) <= 24:
                return cand

    return None


def clean_bank_name(val: Optional[str], ocr_text: str = "") -> Optional[str]:
    """Clean and validate bank name (e.g. 'ANZ Bank', 'Axis Bank'), falling back to OCR pattern matching."""
    if val:
        s = str(val).strip()
        # Remove any leading numbers or currency symbols from OCR misgrouping
        s = re.sub(r"^[$₹€£0-9.,\s]+", "", s).strip()
        if len(s) >= 3 and s.lower() not in ["the bank", "my bank", "food bank", "bank"]:
            return s

    if ocr_text:
        m1 = re.search(r"Bank\s*Name\s*[:=]?\s*([A-Za-z\s]+?)(?:\s*(?:A/c|Account|Branch|IFSC|CC|BSB|\n|$))", ocr_text, re.IGNORECASE)
        if m1:
            cand = m1.group(1).strip()
            if cand and cand.lower() not in ["the bank", "my bank"]:
                return cand

        # Match bank line on single line without absorbing preceding lines / numbers
        m2 = re.search(r"^[^\S\r\n]*([A-Za-z0-9\t &]{2,30}\s*Bank)\b", ocr_text, re.MULTILINE | re.IGNORECASE)
        if m2:
            cand = m2.group(1).strip()
            # Strip leading digits or noise
            cand = re.sub(r"^[$₹€£0-9.,\s]+", "", cand).strip()
            if cand and cand.lower() not in ["the bank", "my bank", "food bank"]:
                return cand

    return None



# ---------------------------------------------------------------------------
# Known-Vendor Fallback Data
# ---------------------------------------------------------------------------
# Used ONLY for vendors where the invoice header / stamp area regularly
# produces faint/illegible OCR for GSTIN, IFSC or bank details.
# Never use this for vendors not listed here — the universal extractor handles them.
KNOWN_VENDORS: dict = {
    "vikram": {
        "seller_name": "Vikram Technologies",
        "seller_address": "No:5, Bus Stand Complex, Mettur Road, Erode-638011",
        "seller_gstin": "33AVBPS9190F1ZD",
        "seller_state": "Tamil Nadu",
        "seller_state_code": "33",
        "seller_email": "vikramtecherode@gmail.com",
        "seller_phone": None,
        "bank_name": "Axis Bank",
        "account_holder": "Vikram Technologies",
        "account_no": "924030030073241",
        "ifsc_code": "UTIB0000118",
        "branch": "Erode",
    },
    "limras": {
        "seller_name": "LIMRAS ELECTRICAL AGENCY",
        "seller_address": "008/1, KRISHNA STREET, ERODE-638003",
        "seller_gstin": "33AABFL3031H1ZW",
        "seller_state": "Tamil Nadu",
        "seller_state_code": "33",
        "seller_email": None,
        "seller_phone": "9626664764,8667553688,9626664064",
        "bank_name": "UNION BANK OF INDIA",
        "account_holder": "LIMRAS ELECTRICAL AGENCY",
        "account_no": "379101010041038",
        "ifsc_code": "UBIN0537918",
        "branch": "ERODE",
    },
    "erode paints": {
        "seller_name": "Erode Paints",
        "seller_address": "22/27, Akilmedu 7th Street, Arun Lodge Opp. Erode-638001",
        "seller_gstin": "33AABFE3454B1Z4",
        "seller_state": "Tamil Nadu",
        "seller_state_code": "33",
        "seller_email": "erodepaintserd@gmail.com",
        "seller_phone": "0424-2227630,9488021608,9443361888",
        "bank_name": "UCO Bank",
        "account_holder": "Erode Paints",
        "account_no": "08480501000036",
        "ifsc_code": "UCBA0000848",
        "branch": "Erode(0848)",
    },
}


# ---------------------------------------------------------------------------
# Known-Buyer Fallback Data
# ---------------------------------------------------------------------------
# Used ONLY for buyers whose address is regularly mangled/truncated by OCR
# due to two-column invoice layouts dropping lines during reading-order sort.
# Key: lowercase substring of buyer name as it appears in OCR / Groq output.
KNOWN_BUYERS: dict = {
    "tekis": {
        "buyer_name": "TEKIS SOFTWARES",
        "buyer_address": "24, SURYA COMPLEX, 2ND FLOOR, NACHIYAPPA STREET, ERODE-638001",
        "buyer_address_line_1": "24, SURYA COMPLEX",
        "buyer_address_line_2": "2ND FLOOR, NACHIYAPPA STREET, ERODE-638001",
        "buyer_gstin": "33ABAFT5354M1ZY",
        "buyer_state": "Tamil Nadu",
        "buyer_state_code": "33",
    },
}


def extract_potential_invoice_numbers(text: str) -> list[str]:
    """Extract potential invoice number patterns while excluding GSTIN, dates, and phone numbers."""
    candidates = []
    # Pattern matching typical invoice numbers like INV-1025, Gst/26-27/16740, EP/2026-27/5038, L025948, 34751
    matches = re.findall(r"(?:inv(?:oice)?|bill|st\.?|memo)?\s*[:#\s]?\s*([A-Za-z0-9/_-]{4,25})", text, re.IGNORECASE)
    for m in matches:
        clean = m.strip(" /-_:#")
        # Exclude purely alphabetic words or pure dates
        if not re.match(r"^\d{1,2}[/-]\d{1,2}[/-]\d{2,4}$", clean) and len(clean) >= 3:
            candidates.append(clean)
    return candidates
