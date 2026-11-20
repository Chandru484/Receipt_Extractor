import re
from typing import Any, Dict, List, Literal, Optional, Union
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic_core import core_schema


CURRENCY_CODE_TO_SYMBOL = {
    "USD": "$",
    "INR": "₹",
    "EUR": "€",
    "GBP": "£",
    "JPY": "¥",
    "CAD": "C$",
    "AUD": "A$",
    "AED": "AED ",
    "SGD": "S$",
}


class CurrencyValue(str):
    """String representation of a monetary value with currency symbol and 2 decimal places.

    Behaves as a string (e.g. '$93.50') for JSON serialization and user display,
    while supporting numerical equality comparisons (e.g. v == 93.50, v == 93.5)
    and float operations.
    """

    @classmethod
    def __get_pydantic_core_schema__(cls, source_type, handler):
        return core_schema.no_info_after_validator_function(
            cls,
            core_schema.str_schema()
        )

    def __float__(self) -> float:
        cleaned = re.sub(r"[^\d.-]", "", str(self))
        return float(cleaned) if cleaned else 0.0

    def __int__(self) -> int:
        return int(self.__float__())

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, (int, float)):
            try:
                cleaned = re.sub(r"[^\d.-]", "", str(self))
                return abs(float(cleaned) - float(other)) < 1e-4
            except Exception:
                pass
        return super().__eq__(other)

    def __hash__(self) -> int:
        return super().__hash__()

    def __add__(self, other: Any) -> Any:
        if isinstance(other, (int, float, CurrencyValue)):
            return float(self) + float(other)
        return super().__add__(other)

    def __radd__(self, other: Any) -> Any:
        if isinstance(other, (int, float)):
            return float(other) + float(self)
        return super().__radd__(other)

    def __sub__(self, other: Any) -> Any:
        if isinstance(other, (int, float, CurrencyValue)):
            return float(self) - float(other)
        return super().__sub__(other)

    def __rsub__(self, other: Any) -> Any:
        if isinstance(other, (int, float)):
            return float(other) - float(self)
        return super().__rsub__(other)

    def __mul__(self, other: Any) -> Any:
        if isinstance(other, (int, float)):
            return float(self) * float(other)
        return super().__mul__(other)

    def __rmul__(self, other: Any) -> Any:
        if isinstance(other, (int, float)):
            return float(other) * float(self)
        return super().__rmul__(other)

    def __truediv__(self, other: Any) -> Any:
        if isinstance(other, (int, float)):
            return float(self) / float(other)
        return super().__truediv__(other)

    def __gt__(self, other: Any) -> bool:
        if isinstance(other, (int, float, CurrencyValue)):
            return float(self) > float(other)
        return super().__gt__(other)

    def __ge__(self, other: Any) -> bool:
        if isinstance(other, (int, float, CurrencyValue)):
            return float(self) >= float(other)
        return super().__ge__(other)

    def __lt__(self, other: Any) -> bool:
        if isinstance(other, (int, float, CurrencyValue)):
            return float(self) < float(other)
        return super().__lt__(other)

    def __le__(self, other: Any) -> bool:
        if isinstance(other, (int, float, CurrencyValue)):
            return float(self) <= float(other)
        return super().__le__(other)


def format_currency_value(value: Any, default_currency: str = "USD") -> Optional[CurrencyValue]:
    """Format any monetary value to CurrencyValue (e.g. '$93.50', '₹100.00')."""
    if value is None:
        return None
    val_str = str(value).strip()
    if not val_str:
        return None

    # Detect currency symbol
    symbol = None
    for s in ["$", "₹", "€", "£", "¥", "C$", "A$", "AED", "S$"]:
        if s in val_str:
            symbol = s
            break
    if not symbol:
        symbol = CURRENCY_CODE_TO_SYMBOL.get(str(default_currency).upper(), "$")

    cleaned = val_str.replace(",", "")
    cleaned = re.sub(r"(\d+)-(\d{2})\b", r"\1.\2", cleaned)
    match = re.search(r"[-+]?\d+(?:\.\d+)?", cleaned)
    if not match:
        return None
    try:
        num = float(match.group(0))
        return CurrencyValue(f"{symbol}{num:.2f}")
    except ValueError:
        return None


def clean_numeric_value(value: Any) -> Optional[float]:
    """Clean monetary and numeric values from strings containing currency symbols, commas, or units."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return round(float(value), 2)
    if isinstance(value, str):
        cleaned = value.strip().replace(",", "")
        # Convert OCR hyphen in decimals (e.g. 91-00 -> 91.00)
        cleaned = re.sub(r"(\d+)-(\d{2})\b", r"\1.\2", cleaned)
        match = re.search(r"[-+]?\d+(?:\.\d+)?", cleaned)
        if match:
            try:
                return round(float(match.group(0)), 2)
            except ValueError:
                return None
    return None


class PartyDetails(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: Optional[str] = None
    address: Optional[str] = None
    gstin: Optional[str] = None
    state: Optional[str] = None
    state_code: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None


class BankDetails(BaseModel):
    model_config = ConfigDict(extra="allow")

    bank_name: Optional[str] = None
    account_holder: Optional[str] = None
    account_no: Optional[str] = None
    ifsc_code: Optional[str] = None
    branch: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def resolve_bank_aliases(cls, data: Any) -> Any:
        if isinstance(data, dict):
            # bank name alias
            if not data.get("bank_name"):
                for k in ["bank", "bank_name", "bank_title", "Bank"]:
                    if data.get(k):
                        data["bank_name"] = str(data[k]).strip()
                        break
            # account holder alias
            if not data.get("account_holder"):
                for k in ["account_holder_name", "ac_holders_name", "ac_holder", "A/c Holder's Name", "holder_name"]:
                    if data.get(k):
                        data["account_holder"] = str(data[k]).strip()
                        break
            # account number alias
            if not data.get("account_no"):
                for k in ["account_number", "ac_no", "A/c No", "A/c No.", "account_num", "ACC #", "acc_#", "acc", "acc_no", "Account #", "Account No", "acc_num"]:
                    if data.get(k):
                        data["account_no"] = str(data[k]).strip()
                        break
            # ifsc code alias
            if not data.get("ifsc_code"):
                for k in ["ifsc", "ifs_code", "IFS Code", "IFSC Code"]:
                    if data.get(k):
                        data["ifsc_code"] = str(data[k]).strip()
                        break
        return data


class ReceiptItem(BaseModel):
    model_config = ConfigDict(extra="allow")

    page: Optional[int] = Field(default=1, description="Page number where item appears (1-indexed)")
    sl_no: Optional[str] = None
    item_name: Optional[str] = None
    hsn_sac: Optional[str] = None
    quantity: Optional[float] = None
    uom: Optional[str] = None
    unit_price: Optional[CurrencyValue] = None
    rate_incl_tax: Optional[CurrencyValue] = None
    gst_rate: Optional[str] = None
    total_price: Optional[CurrencyValue] = None

    @model_validator(mode="before")
    @classmethod
    def resolve_item_fields(cls, data: Any) -> Any:
        if isinstance(data, dict):
            # Page number resolution
            if data.get("page") is None:
                for alt_key in ["page_no", "page_num", "page_number", "pg", "Page", "Page_No", "Page_Number"]:
                    if data.get(alt_key) is not None:
                        data["page"] = data[alt_key]
                        break
            if data.get("page") is not None:
                try:
                    match = re.search(r"\d+", str(data["page"]))
                    data["page"] = int(match.group(0)) if match else 1
                except Exception:
                    data["page"] = 1
            else:
                data["page"] = 1

            if data.get("quantity") is None:
                for alt_key in ["qty", "Qty", "quantity", "Quantity"]:
                    if data.get(alt_key) is not None:
                        data["quantity"] = data[alt_key]
                        break

            if "item_name" in data and isinstance(data["item_name"], str):
                data["item_name"] = re.sub(r"\s+\d{1,2}/\d{1,2}/\d{2,4}$", "", data["item_name"]).strip()

        return data

    @field_validator("quantity", mode="before")
    @classmethod
    def validate_numeric(cls, v: Any) -> Optional[float]:
        return clean_numeric_value(v)

    @field_validator("unit_price", "rate_incl_tax", "total_price", mode="before")
    @classmethod
    def validate_currency_fields(cls, v: Any) -> Optional[CurrencyValue]:
        return format_currency_value(v)

    @field_validator("item_name", "sl_no", "hsn_sac", "uom", "gst_rate", mode="before")
    @classmethod
    def validate_strings(cls, v: Any) -> Optional[str]:
        if v is None:
            return None
        s = str(v).strip()
        return s if s else None


class ReceiptData(BaseModel):
    model_config = ConfigDict(extra="allow")

    document_type: Literal["receipt", "invoice", "unknown"] = "receipt"

    # Core Vendor / Seller Details
    vendor_name: Optional[str] = None
    seller: Optional[str] = None
    seller_name: Optional[str] = None
    seller_address: Optional[str] = None
    seller_gstin: Optional[str] = None
    seller_state: Optional[str] = None
    seller_state_code: Optional[str] = None
    seller_email: Optional[str] = None
    seller_phone: Optional[str] = None
    seller_mobile: Optional[str] = None
    phone: Optional[str] = None
    mobile: Optional[str] = None

    # Core Buyer / Customer Details
    customer_name: Optional[str] = None
    buyer: Optional[str] = None
    buyer_name: Optional[str] = None
    buyer_address: Optional[str] = None
    buyer_address_line_1: Optional[str] = None
    buyer_address_line_2: Optional[str] = None
    buyer_gstin: Optional[str] = None
    buyer_state: Optional[str] = None
    buyer_state_code: Optional[str] = None
    buyer_phone: Optional[str] = None
    buyer_mobile: Optional[str] = None
    buyer_email: Optional[str] = None

    # Dispatch / Transport / Order details
    transport: Optional[str] = None
    despatch_through: Optional[str] = None
    eway_bill_no: Optional[str] = None
    po_number: Optional[str] = None
    dc_number: Optional[str] = None

    # Backward compatibility alias
    gstin: Optional[str] = None

    # Document details
    invoice_number: Optional[str] = None
    receipt_number: Optional[str] = None
    invoice_date: Optional[str] = None
    date_paid: Optional[str] = None
    payment_mode: Optional[str] = None
    salesman: Optional[str] = None
    amount_in_words: Optional[str] = None

    # Line items
    items: List[ReceiptItem] = Field(default_factory=list)

    # Financial totals & tax breakdown (with currency symbol and 2 decimal places e.g. '$93.50')
    subtotal: Optional[CurrencyValue] = None
    cgst: Optional[CurrencyValue] = None
    cgst_rate: Optional[str] = None
    sgst: Optional[CurrencyValue] = None
    sgst_rate: Optional[str] = None
    igst: Optional[CurrencyValue] = None
    igst_rate: Optional[str] = None
    rounding_off: Optional[CurrencyValue] = None
    tax: Optional[CurrencyValue] = None
    grand_total: Optional[CurrencyValue] = None
    amount_paid: Optional[CurrencyValue] = None
    refunded_amount: Optional[CurrencyValue] = None
    refunded_on: Optional[str] = None
    currency: Optional[str] = None

    # Bank Details
    bank_details: Optional[BankDetails] = None

    # Additional captured fields from receipt
    extra_fields: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("subtotal", "tax", "grand_total", "cgst", "sgst", "igst", "rounding_off", "amount_paid", "refunded_amount", mode="before")
    @classmethod
    def validate_totals(cls, v: Any) -> Optional[CurrencyValue]:
        return format_currency_value(v)

    @model_validator(mode="before")
    @classmethod
    def resolve_party_names(cls, data: Any) -> Any:
        if isinstance(data, dict):
            # seller / vendor resolution
            s_name = data.get("seller_name") or data.get("seller") or data.get("vendor_name")
            if s_name:
                data["vendor_name"] = s_name
                data["seller"] = s_name
                data["seller_name"] = s_name

            # buyer / customer resolution
            b_name = data.get("buyer_name") or data.get("buyer") or data.get("customer_name")
            if b_name:
                data["customer_name"] = b_name
                data["buyer"] = b_name
                data["buyer_name"] = b_name

            # GSTIN resolution
            s_gst = data.get("seller_gstin") or data.get("gstin")
            if s_gst:
                data["seller_gstin"] = s_gst
                data["gstin"] = s_gst

            # Phone and mobile aliases
            s_ph = data.get("seller_phone") or data.get("phone")
            if s_ph:
                data["seller_phone"] = str(s_ph).strip()
                data["phone"] = str(s_ph).strip()

            s_mob = data.get("seller_mobile") or data.get("mobile")
            if s_mob:
                data["seller_mobile"] = str(s_mob).strip()
                data["mobile"] = str(s_mob).strip()

        return data

    @model_validator(mode="after")
    def synchronize_fields(self) -> "ReceiptData":
        # Synchronize seller / vendor_name / seller_name
        s_name = self.seller_name or self.seller or self.vendor_name
        if s_name:
            self.vendor_name = s_name
            self.seller = s_name
            self.seller_name = s_name

        # Synchronize seller_gstin / gstin (do not duplicate in output)
        if not self.seller_gstin and self.gstin:
            self.seller_gstin = self.gstin
        self.gstin = None

        # Synchronize buyer / customer_name / buyer_name
        b_name = self.buyer_name or self.buyer or self.customer_name
        if b_name:
            self.customer_name = b_name
            self.buyer = b_name
            self.buyer_name = b_name

        # Synchronize phone and mobile
        s_ph = self.seller_phone or self.phone
        if s_ph:
            self.seller_phone = s_ph
            self.phone = s_ph

        s_mob = self.seller_mobile or self.mobile
        if s_mob:
            self.seller_mobile = s_mob
            self.mobile = s_mob

        # Clean transport leak from buyer address if present
        if self.transport:
            t_pat = re.escape(self.transport.strip())
            if self.buyer_address:
                self.buyer_address = re.sub(rf",?\s*\b{t_pat}\b,?\s*", ", ", self.buyer_address, flags=re.IGNORECASE).strip(" ,")
                self.buyer_address = re.sub(r",\s*,+", ", ", self.buyer_address).strip(" ,")
            if self.buyer_address_line_1:
                self.buyer_address_line_1 = re.sub(rf",?\s*\b{t_pat}\b,?\s*", ", ", self.buyer_address_line_1, flags=re.IGNORECASE).strip(" ,")
                self.buyer_address_line_1 = re.sub(r",\s*,+", ", ", self.buyer_address_line_1).strip(" ,")
            if self.buyer_address_line_2:
                self.buyer_address_line_2 = re.sub(rf",?\s*\b{t_pat}\b,?\s*", ", ", self.buyer_address_line_2, flags=re.IGNORECASE).strip(" ,")
                self.buyer_address_line_2 = re.sub(r",\s*,+", ", ", self.buyer_address_line_2).strip(" ,")

        # Synchronize buyer address lines universally
        if self.buyer_address:
            # If address contains newlines, split by line
            if "\n" in self.buyer_address:
                addr_lines = [l.strip() for l in self.buyer_address.split("\n") if l.strip()]
                if len(addr_lines) >= 2:
                    if not self.buyer_address_line_1:
                        self.buyer_address_line_1 = addr_lines[0]
                    if not self.buyer_address_line_2:
                        self.buyer_address_line_2 = ", ".join(addr_lines[1:])
            # Otherwise split by comma segments
            elif not self.buyer_address_line_1 or not self.buyer_address_line_2:
                parts = [p.strip() for p in self.buyer_address.split(",") if p.strip()]
                if len(parts) >= 2:
                    if not self.buyer_address_line_1:
                        self.buyer_address_line_1 = parts[0]
                    if not self.buyer_address_line_2:
                        self.buyer_address_line_2 = ", ".join(parts[1:3]) if len(parts) >= 3 else parts[1]

        # Format tax rates with % symbol if numeric string
        if self.cgst_rate:
            s_cgst = str(self.cgst_rate).strip()
            if not s_cgst.endswith("%"):
                self.cgst_rate = f"{s_cgst}%"
        if self.sgst_rate:
            s_sgst = str(self.sgst_rate).strip()
            if not s_sgst.endswith("%"):
                self.sgst_rate = f"{s_sgst}%"
        if self.igst_rate:
            s_igst = str(self.igst_rate).strip()
            if not s_igst.endswith("%"):
                self.igst_rate = f"{s_igst}%"

        # Determine currency symbol from document currency
        curr_sym = CURRENCY_CODE_TO_SYMBOL.get((self.currency or "").upper(), "$")

        # Calculate combined tax if individual components exist and tax is None
        tax_sum = 0.0
        has_tax_component = False
        for comp in [self.cgst, self.sgst, self.igst]:
            if comp is not None:
                tax_sum += float(comp)
                has_tax_component = True
        if self.tax is None and has_tax_component:
            self.tax = format_currency_value(tax_sum, curr_sym)

        # Standardize all financial amounts to CurrencyValue with symbol and 2 decimals (e.g. '$93.50')
        for f in ["subtotal", "tax", "grand_total", "cgst", "sgst", "igst", "rounding_off", "amount_paid", "refunded_amount"]:
            val = getattr(self, f, None)
            if val is not None:
                setattr(self, f, format_currency_value(val, curr_sym))

        for it in self.items:
            if it.unit_price is not None:
                it.unit_price = format_currency_value(it.unit_price, curr_sym)
            if it.rate_incl_tax is not None:
                it.rate_incl_tax = format_currency_value(it.rate_incl_tax, curr_sym)
            if it.total_price is not None:
                it.total_price = format_currency_value(it.total_price, curr_sym)

        # Synchronize invoice_number and receipt_number
        doc_num = self.invoice_number or self.receipt_number
        if doc_num:
            self.invoice_number = doc_num
            self.receipt_number = doc_num

        # Synchronize invoice_date and date_paid
        doc_date = self.invoice_date or self.date_paid
        if doc_date:
            self.invoice_date = doc_date
            self.date_paid = doc_date

        # Clean invalid placeholder words from state fields
        INVALID_STATE_WORDS = {
            "zipcode", "zip", "code", "pin", "pincode", "postal",
            "city", "country", "state", "name", "address", "phone", "email", "total"
        }
        if self.seller_state and self.seller_state.strip().lower() in INVALID_STATE_WORDS:
            self.seller_state = None
        if self.buyer_state and self.buyer_state.strip().lower() in INVALID_STATE_WORDS:
            self.buyer_state = None

        # Standard field mapping: never duplicate known/standard fields in extra_fields
        KNOWN_STANDARD_ALIASES = {
            "receipt_number": "receipt_number",
            "invoice_number": "invoice_number",
            "invoice_no": "invoice_number",
            "bill_no": "invoice_number",
            "bill_number": "invoice_number",
            "receipt_no": "receipt_number",
            "date_paid": "date_paid",
            "invoice_date": "invoice_date",
            "bill_date": "invoice_date",
            "amount_paid": "amount_paid",
            "refunded_amount": "refunded_amount",
            "refund_amount": "refunded_amount",
            "refunded_on": "refunded_on",
            "refund_date": "refunded_on",
            "contact_email": "seller_email",
            "support_email": "seller_email",
            "seller_email": "seller_email",
            "buyer_email": "buyer_email",
            "customer_email": "buyer_email",
            "seller_phone": "seller_phone",
            "buyer_phone": "buyer_phone",
            "customer_name": "customer_name",
            "buyer_name": "buyer_name",
            "seller_name": "seller_name",
            "vendor_name": "vendor_name",
            "subtotal": "subtotal",
            "sub_total": "subtotal",
            "tax": "tax",
            "grand_total": "grand_total",
            "total": "grand_total",
            "total_amount": "grand_total",
            "total_due": "grand_total",
            "balance_due": "grand_total",
            "amount_due": "grand_total",
            "currency": "currency",
            "payment_mode": "payment_mode",
            "payment_method": "payment_mode",
        }

        # Absorb any Pydantic extra fields (from ConfigDict extra="allow") into our extra_fields dict
        pydantic_extras = self.__pydantic_extra__ or {}
        _STANDARD_FIELDS = {
            "document_type", "vendor_name", "seller", "seller_name", "seller_address",
            "seller_gstin", "seller_state", "seller_state_code", "seller_email", "seller_phone",
            "customer_name", "buyer", "buyer_name", "buyer_address", "buyer_address_line_1",
            "buyer_address_line_2", "buyer_gstin", "buyer_state", "buyer_state_code",
            "buyer_phone", "buyer_email", "gstin", "invoice_number", "receipt_number",
            "invoice_date", "date_paid", "payment_mode", "salesman", "amount_in_words",
            "items", "subtotal", "cgst", "cgst_rate", "sgst", "sgst_rate", "igst",
            "igst_rate", "rounding_off", "tax", "grand_total", "amount_paid",
            "refunded_amount", "refunded_on", "currency", "bank_details", "extra_fields"
        }
        if self.extra_fields is None:
            self.extra_fields = {}
        for k, v in pydantic_extras.items():
            if k not in _STANDARD_FIELDS and v is not None and k not in self.extra_fields:
                self.extra_fields[k] = v

        # Absorb any bank details accidentally placed in extra_fields
        if self.extra_fields:
            bank_alias_map = {
                "bank_name": "bank_name",
                "bank": "bank_name",
                "account_no": "account_no",
                "account_number": "account_no",
                "acc": "account_no",
                "acc_no": "account_no",
                "acc_#": "account_no",
                "ifsc": "ifsc_code",
                "ifsc_code": "ifsc_code",
            }
            for k in list(self.extra_fields.keys()):
                k_clean = k.lower().replace(" ", "_")
                if k_clean in bank_alias_map:
                    if not self.bank_details:
                        self.bank_details = BankDetails()
                    target_b = bank_alias_map[k_clean]
                    if getattr(self.bank_details, target_b, None) is None:
                        setattr(self.bank_details, target_b, str(self.extra_fields[k]).strip())
                    self.extra_fields.pop(k, None)

        # If any extra_fields key matches a standard field alias, assign it if empty, and REMOVE it from extra_fields
        keys_to_remove = []
        for k, v in list(self.extra_fields.items()):
            k_lower = k.lower().strip()
            if k_lower in KNOWN_STANDARD_ALIASES:
                target_field = KNOWN_STANDARD_ALIASES[k_lower]
                if getattr(self, target_field, None) is None:
                    # Parse numeric or string properly
                    if target_field in ["amount_paid", "refunded_amount", "subtotal", "tax", "grand_total", "cgst", "sgst", "igst", "rounding_off"]:
                        setattr(self, target_field, format_currency_value(v, curr_sym))
                    else:
                        setattr(self, target_field, str(v).strip())
                keys_to_remove.append(k)

        for k in keys_to_remove:
            self.extra_fields.pop(k, None)

        # Ensure all financial amounts are CurrencyValue with symbol and 2 decimals (e.g. '$93.50')
        for f in ["subtotal", "tax", "grand_total", "cgst", "sgst", "igst", "rounding_off", "amount_paid", "refunded_amount"]:
            val = getattr(self, f, None)
            if val is not None:
                setattr(self, f, format_currency_value(val, curr_sym))

        # Synchronize invoice_number and receipt_number again in case populated from alias
        doc_num = self.invoice_number or self.receipt_number
        if doc_num:
            self.invoice_number = doc_num
            self.receipt_number = doc_num

        doc_date = self.invoice_date or self.date_paid
        if doc_date:
            self.invoice_date = doc_date
            self.date_paid = doc_date

        return self


class OCRDiagnostics(BaseModel):
    full_text: str
    lines: List[str] = Field(default_factory=list)
    line_count: int = 0


class ReceiptResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    success: bool = True
    message: str = "Receipt extracted successfully"
    formatted_display: Optional[str] = None
    data: ReceiptData
    ocr: OCRDiagnostics
    document_id: Optional[str] = Field(default=None, description="MongoDB document ID if persisted")
    is_duplicate: Optional[bool] = Field(default=None, description="True if record already existed in MongoDB")


def remove_none_values(obj: Any) -> Any:
    """Recursively remove keys with None (null) values and empty dicts from dicts and lists."""
    if isinstance(obj, dict):
        cleaned = {}
        for k, v in obj.items():
            if v is not None:
                cleaned_v = remove_none_values(v)
                if cleaned_v is not None:
                    if isinstance(cleaned_v, dict) and not cleaned_v:
                        continue
                    cleaned[k] = cleaned_v
        return cleaned
    elif isinstance(obj, list):
        return [remove_none_values(v) for v in obj]
    return obj
