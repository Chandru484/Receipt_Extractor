import re
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


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
            # account holder alias
            if not data.get("account_holder"):
                for k in ["account_holder_name", "ac_holders_name", "ac_holder", "A/c Holder's Name", "holder_name"]:
                    if data.get(k):
                        data["account_holder"] = str(data[k]).strip()
                        break
            # account number alias
            if not data.get("account_no"):
                for k in ["account_number", "ac_no", "A/c No", "A/c No.", "account_num"]:
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

    sl_no: Optional[str] = None
    item_name: Optional[str] = None
    hsn_sac: Optional[str] = None
    quantity: Optional[float] = None
    uom: Optional[str] = None
    unit_price: Optional[float] = None
    rate_incl_tax: Optional[float] = None
    gst_rate: Optional[str] = None
    total_price: Optional[float] = None

    @model_validator(mode="before")
    @classmethod
    def resolve_item_fields(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if data.get("quantity") is None:
                for alt_key in ["qty", "Qty", "quantity", "Quantity"]:
                    if data.get(alt_key) is not None:
                        data["quantity"] = data[alt_key]
                        break

            if "item_name" in data and isinstance(data["item_name"], str):
                data["item_name"] = re.sub(r"\s+\d{1,2}/\d{1,2}/\d{2,4}$", "", data["item_name"]).strip()

        return data

    @field_validator("quantity", "unit_price", "rate_incl_tax", "total_price", mode="before")
    @classmethod
    def validate_numeric(cls, v: Any) -> Optional[float]:
        return clean_numeric_value(v)

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
    buyer_email: Optional[str] = None

    # Backward compatibility alias
    gstin: Optional[str] = None

    # Document details
    invoice_number: Optional[str] = None
    invoice_date: Optional[str] = None
    payment_mode: Optional[str] = None
    salesman: Optional[str] = None
    amount_in_words: Optional[str] = None

    # Line items
    items: List[ReceiptItem] = Field(default_factory=list)

    # Financial totals & tax breakdown
    subtotal: Optional[float] = None
    cgst: Optional[float] = None
    cgst_rate: Optional[str] = None
    sgst: Optional[float] = None
    sgst_rate: Optional[str] = None
    igst: Optional[float] = None
    igst_rate: Optional[str] = None
    rounding_off: Optional[float] = None
    tax: Optional[float] = None
    grand_total: Optional[float] = None
    currency: Optional[str] = None

    # Bank Details
    bank_details: Optional[BankDetails] = None

    # Additional captured fields from receipt
    extra_fields: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("subtotal", "tax", "grand_total", "cgst", "sgst", "igst", "rounding_off", mode="before")
    @classmethod
    def validate_totals(cls, v: Any) -> Optional[float]:
        return clean_numeric_value(v)

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

        # Calculate combined tax if individual components exist and tax is None
        tax_sum = 0.0
        has_tax_component = False
        for comp in [self.cgst, self.sgst, self.igst]:
            if comp is not None:
                tax_sum += comp
                has_tax_component = True
        if self.tax is None and has_tax_component:
            self.tax = round(tax_sum, 2)

        return self


class OCRDiagnostics(BaseModel):
    full_text: str
    lines: List[str] = Field(default_factory=list)
    line_count: int = 0


class ReceiptResponse(BaseModel):
    success: bool = True
    message: str = "Receipt extracted successfully"
    formatted_display: Optional[str] = None
    data: ReceiptData
    ocr: OCRDiagnostics
    document_id: Optional[str] = Field(default=None, description="MongoDB document ID if persisted")
