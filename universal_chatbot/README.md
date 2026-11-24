# Universal AI Chatbot Platform

A standalone, multi-tenant, multilingual (Tamil & English) AI Chatbot platform with RAG document processing, application database retrieval, voice synthesis, and embeddable widget.

---

## 🚀 Quick Start (Running the Chatbot)

### Option 1: 1-Click Launcher (Windows)
Double-click or run from the project root:
```bat
.\run_chatbot.bat
```

### Option 2: Command Line (PowerShell / Terminal)
From the repository root (`D:\Task\Receipt_Extractor`):
```powershell
# Using the existing virtual environment:
.\venv\Scripts\python -m uvicorn universal_chatbot.backend.app.main:app --host 0.0.0.0 --port 8080 --reload
```

---

## 🌐 Access Points & URLs

Once the server is running, open your web browser:

| Description | URL | Notes |
|---|---|---|
| **Interactive Widget Demo** | [http://localhost:8080/demo](http://localhost:8080/demo) | Full demo page simulating external site embedding the chatbot |
| **Interactive Swagger API Docs** | [http://localhost:8080/docs](http://localhost:8080/docs) | Test all chat, document upload, and admin API endpoints |
| **Platform Health Check** | [http://localhost:8080/health](http://localhost:8080/health) | Diagnostics checking MongoDB Atlas connection and AI keys |
| **Widget JavaScript Script** | [http://localhost:8080/widget.js](http://localhost:8080/widget.js) | Embed snippet for any external HTML / React / Vue page |

---

## 💻 How to Embed the Widget on Any Website

Add this single `<script>` tag before the closing `</body>` tag on any webpage:

```html
<!-- Universal AI Chatbot Embed Snippet -->
<script
  src="http://localhost:8080/widget.js"
  data-website-id="site_demo"
  async>
</script>
```

### Features available out-of-the-box in the Widget:
1. **🌐 Language Switcher**: Switch between **English** and **தமிழ் (Tamil)** at any moment.
2. **🎙️ Voice Assistant**: Press the microphone button to speak in Tamil or English; click 🔊 **Listen** to read responses aloud.
3. **📎 Document Upload**: Click the paperclip icon to upload a PDF, TXT, or CSV for instant session-scoped Q&A.
4. **🏢 Application Data**: Queries host application databases (e.g., `receipt_db.Receipt_Extraction`) to answer questions about purchase history, invoices, or records.
5. **🤝 Human Handoff**: Integrates with Tawk.to or escalates to human support agents when requested.

---

## ⚙️ Configuration & API Keys

Environment variables are stored in [`universal_chatbot/backend/.env`](file:///d:/Task/Receipt_Extractor/universal_chatbot/backend/.env):

```env
# AI Provider Keys
CHATBOT_GROQ_API_KEYS=your_groq_api_key_1,your_groq_api_key_2
CHATBOT_GROQ_MODEL=openai/gpt-oss-120b

# Multi-Provider Secondary Fallback (OpenRouter, DeepSeek, Mistral)
CHATBOT_FALLBACK_PROVIDER=openrouter
CHATBOT_FALLBACK_API_KEY=your_openrouter_key

# MongoDB Platform Database
CHATBOT_MONGODB_URI=mongodb+srv://tekis_db_user:Test-123@cluster0.h0zex3e.mongodb.net/?retryWrites=true&w=majority
CHATBOT_MONGODB_DB_NAME=mongodb
```

---

## 🧪 Running Automated Unit Tests

```powershell
cmd /c "set PYTHONPATH=. && .\venv\Scripts\pytest universal_chatbot/backend/tests/"
```
All 13 unit tests verify encryption, multi-provider failover, document chunking, RAG scoring, application database filtering, and API endpoints.
