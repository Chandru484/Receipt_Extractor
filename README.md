---
title: Receipt Extractor
emoji: 🧾
colorFrom: purple
colorTo: pink
sdk: gradio
sdk_version: 6.32.0
python_version: '3.12'
app_file: app.py
pinned: false
license: apache-2.0
---

# 🧾 Production Receipt & Invoice Extractor API

An enterprise-ready, open-source receipt and invoice extraction service. It combines **local PaddleOCR 3.x** for high-precision text recognition with **Groq LLM (`qwen/qwen3.8-27b`)** for semantic entity extraction, automated tax and financial reconciliation, and direct persistence to **MongoDB**.

---

## 🌟 Key Features

- **⚡ Fast Local OCR Engine**: Uses lightweight `PP-OCRv6_small_det` and `PP-OCRv6_small_rec` models with bounding-box line sorting for Indian invoices, retail bills, thermal slips, and printed receipts.
- **🧠 Semantic LLM Extraction**: Extracts vendor, buyer, addresses, GSTINs, invoice dates/numbers, line items, taxes, bank details, and company PAN using Groq LLM.
- **🛡️ Primary + Fallback Groq API**: Auto-detects secondary Groq API key and transparently fails over if the primary key reaches rate limits or token limits.
- **💾 Automated MongoDB Persistence**: Extracted JSON responses, structured data, formatted text displays, and OCR metadata are automatically stored in the MongoDB `Receipt_Extraction` collection.
- **🔒 In-Memory Zero-Disk Storage**: Uploaded receipt images are processed completely in RAM; images are never written to disk, ensuring privacy and compliance.
- **📊 Interactive Display & Swagger UI**: Generates a clean human-readable bill summary alongside structured JSON, complete with interactive OpenAPI documentation at `/docs`.

---

## 📋 Prerequisites

- **Python**: Version 3.10, 3.11, or 3.12
- **Groq API Key**: Free API key from [console.groq.com](https://console.groq.com)
- **MongoDB**: Local MongoDB instance (`mongodb://localhost:27017/`) or free cloud [MongoDB Atlas](https://www.mongodb.com/cloud/atlas)

---

## 🚀 Quick Start & Installation

### 1. Clone & Navigate to Project

```bash
cd d:\Task\Receipt_Extractor
```

### 2. Activate Virtual Environment

**Windows (PowerShell):**
```powershell
.\venv\Scripts\Activate.ps1
```

**Windows (Command Prompt):**
```cmd
.\venv\Scripts\activate.bat
```

**Linux / macOS:**
```bash
source venv/bin/activate
```

*(If creating a fresh virtual environment from scratch: `python -m venv venv`)*

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure Environment Variables

Create or update your `.env` file in the root directory:

```env
# Primary Groq API Configuration
GROQ_API_KEY=your_primary_groq_api_key_here
GROQ_MODEL=qwen/qwen3.8-27b

# Fallback Groq API (Auto-fails over if primary hits rate limits)
GROQ_FALLBACK_API_KEY=your_fallback_groq_key_here
GROQ_FALLBACK_MODEL=qwen/qwen3.8-27b

# Image Upload Limit (MB)
MAX_UPLOAD_SIZE_MB=10
OCR_LANGUAGE=en

# MongoDB Configuration
MONGODB_URI=mongodb://localhost:27017/
MONGODB_DB_NAME=receipt_db
MONGODB_COLLECTION=Receipt_Extraction
MONGODB_ENABLED=true
```

---

## 🏃 Running the Server

Start the FastAPI application using Uvicorn:

```bash
uvicorn app.main:app --reload --port 8000
```

To bind to all network interfaces (e.g., accessible from other machines on your LAN):
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Once started:
- **Interactive Swagger Docs**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **Alternative ReDoc UI**: [http://localhost:8000/redoc](http://localhost:8000/redoc)
- **Health Diagnostics**: [http://localhost:8000/health](http://localhost:8000/health)

---

## 📡 API Endpoints

### 1. `POST /extract` — Extract Receipt & Store in MongoDB

Uploads an image file (`JPG`, `PNG`, `WebP`, `BMP`), extracts structured data, formats a human-readable display, and persists the result to MongoDB.

#### Example using `cURL`:
```bash
curl -X POST "http://localhost:8000/extract" \
  -H "accept: application/json" \
  -H "Content-Type: multipart/form-data" \
  -F "file=@sample_receipt.jpg"
```

#### Example using Python (`requests` or `httpx`):
```python
import httpx

with open("sample_receipt.jpg", "rb") as f:
    files = {"file": ("receipt.jpg", f, "image/jpeg")}
    response = httpx.post("http://localhost:8000/extract", files=files, timeout=60.0)

print(response.json())
```

#### Example JSON Response:
```json
{
  "success": true,
  "message": "Receipt extracted successfully",
  "document_id": "6afda18a21b73ff59613e901",
  "formatted_display": "Seller : Erode Paints\nSeller GSTIN : 33AABFE3454B1Z4\nBuyer : Tekis Softwares\nGrand Total : 2290.00\n...",
  "data": {
    "document_type": "invoice",
    "vendor_name": "Erode Paints",
    "seller_name": "Erode Paints",
    "seller_address": "22/27, Akilmedu 7th Street, Arun Lodge Opp. Erode-638001",
    "seller_gstin": "33AABFE3454B1Z4",
    "buyer_name": "Tekis Softwares",
    "buyer_gstin": "33ABAFT5354M1ZY",
    "invoice_number": "EP/2026-27/5038",
    "invoice_date": "2026-10-10",
    "items": [
      {
        "sl_no": "1",
        "item_name": "Ap Trac Emul Advnc TA2 10 Lit",
        "hsn_sac": "32091010",
        "quantity": 1,
        "uom": "No",
        "unit_price": 1466.1,
        "rate_incl_tax": 1730,
        "gst_rate": "18%",
        "total_price": 1466.1
      }
    ],
    "subtotal": 1940.68,
    "cgst": 174.66,
    "sgst": 174.66,
    "tax": 349.32,
    "rounding_off": 0.0,
    "grand_total": 2290.0,
    "currency": "INR",
    "bank_details": {
      "bank_name": "UCO Bank",
      "account_holder": "Erode Paints",
      "account_no": "08480501000036",
      "ifsc_code": "UCBA0000848",
      "branch": "Erode"
    },
    "extra_fields": {
      "company_pan": "AABFE3454B"
    }
  },
  "ocr": {
    "full_text": "...",
    "lines": [...],
    "line_count": 42
  }
}
```

---

### 2. `GET /receipts` — List Stored Receipts

Fetch stored receipt extractions from MongoDB with pagination:

```bash
curl -X GET "http://localhost:8000/receipts?limit=20&skip=0"
```

### 3. `GET /receipts/{receipt_id}` — Get Receipt by MongoDB ID

Retrieve a single stored document by its MongoDB `_id`:

```bash
curl -X GET "http://localhost:8000/receipts/6afda18a21b73ff59613e901"
```

### 4. `GET /health` — Diagnostics & Service Status

Check OCR engine, active Groq model, fallback status, and MongoDB connection:

```bash
curl -X GET "http://localhost:8000/health"
```

---

## 🧪 Running Unit Tests

Run the full automated test suite (34 unit and validation tests):

```powershell
.\venv\Scripts\pytest tests/ -v --ignore=tests/test_api_endpoints.py
```

---

## 🐳 Running with Docker

Build and run using the included multi-platform Dockerfile:

```bash
# Build Docker image
docker build -t receipt-extractor .

# Run Docker container
docker run -p 8000:7860 --env-file .env receipt-extractor
```

Access the API at `http://localhost:8000`.

---

## ☁️ Free Cloud Deployment

For 100% free hosting with sufficient RAM for PaddleOCR:

1. **Database**: Use a free **MongoDB Atlas (M0 Shared Sandbox)** cluster.
2. **API Hosting**: Deploy to **[Hugging Face Spaces](https://huggingface.co/spaces)** (Free 2 vCPU · 16 GB RAM) using the provided `Dockerfile`. (Standard free tiers on Render, Koyeb, and Vercel will encounter Out-Of-Memory or bundle size limits with PaddlePaddle).

---

## 📂 Project Architecture

```text
Receipt_Extractor/
├── ai/
│   ├── extraction_prompt.py     # Prompt engineering & JSON output schema
│   └── groq_client.py           # Primary + fallback Groq client with retry
├── app/
│   └── main.py                  # FastAPI routes & HTTP lifecycle
├── core/
│   ├── config.py                # Pydantic BaseSettings configuration
│   ├── constants.py             # Allowed mime types & currencies
│   └── receipt_extractor.py     # End-to-end extraction pipeline
├── extraction/
│   ├── alias_mapper.py          # Field normalization & aliases
│   ├── field_extractor.py       # Regex fallback heuristics
│   ├── table_extractor.py       # Table parsing logic
│   └── validation.py            # Tax reconciliation & schema validation
├── processing/
│   ├── image_processor.py       # In-memory image preprocessing & resizing
│   └── ocr_engine.py            # PaddleOCR engine with bounding-box sorter
├── schemas/
│   └── receipt_schema.py        # Pydantic ReceiptData, Items, and Response
├── storage/
│   └── mongo_client.py          # Resilient MongoDB client & operations
├── tests/                       # 34 automated unit & validation tests
├── Dockerfile                   # Multi-platform production container
├── requirements.txt             # Pinned Python package dependencies
└── README.md                    # Project documentation
```

---

## 📄 License

This project is licensed under the Apache 2.0 License.
