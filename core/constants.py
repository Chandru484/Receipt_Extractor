ALLOWED_IMAGE_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
    ".bmp"
}

ALLOWED_IMAGE_CONTENT_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/bmp"
}

RECEIPT_OUTPUT_FIELDS = [
    "document_type",
    "vendor_name",
    "invoice_number",
    "invoice_date",
    "customer_name",
    "items",
    "subtotal",
    "tax",
    "grand_total",
    "currency"
]

DOCUMENT_TYPES = ["receipt", "invoice", "unknown"]

CURRENCY_SYMBOLS = {
    "₹": "INR",
    "rs": "INR",
    "rs.": "INR",
    "inr": "INR",
    "$": "USD",
    "usd": "USD",
    "€": "EUR",
    "eur": "EUR",
    "£": "GBP",
    "gbp": "GBP",
    "¥": "JPY",
    "jpy": "JPY",
    "c$": "CAD",
    "cad": "CAD",
    "a$": "AUD",
    "aud": "AUD",
    "aed": "AED",
    "sgd": "SGD"
}
