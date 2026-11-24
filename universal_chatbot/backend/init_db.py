import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta

# Add backend directory to sys.path
backend_dir = Path(__file__).resolve().parent
sys.path.insert(0, str(backend_dir.parent.parent))

from pymongo import MongoClient
from universal_chatbot.backend.app.core.config import chatbot_settings

IST = timezone(timedelta(hours=5, minutes=30))
now_ist = datetime.now(IST).strftime("%d-%m-%Y %H:%M:%S")

def initialize_database():
    print(f"Connecting to MongoDB cluster: {chatbot_settings.CHATBOT_MONGODB_URI[:35]}...")
    client = MongoClient(chatbot_settings.CHATBOT_MONGODB_URI, serverSelectionTimeoutMS=8000)
    
    # 1. Ping the cluster
    client.admin.command("ping")
    print("✅ Ping successful! Connected to MongoDB Atlas cluster.")

    # 2. Access the database named 'mongodb'
    db = client["mongodb"]
    print(f"Targeting database: '{db.name}'")

    # 3. Create 'tenants' collection and insert foundational tenant
    tenants_col = db["tenants"]
    tenants_col.replace_one(
        {"tenant_id": "ten_default"},
        {
            "tenant_id": "ten_default",
            "name": "Default Enterprise Organization",
            "admin_email": "admin@universal-chatbot.com",
            "created_at": now_ist,
            "status": "active",
        },
        upsert=True
    )
    print("✅ Created collection 'tenants' and stored default tenant 'ten_default'.")

    # 4. Create 'websites' collection and insert foundational website integration
    websites_col = db["websites"]
    websites_col.replace_one(
        {"website_id": "site_demo"},
        {
            "website_id": "site_demo",
            "tenant_id": "ten_default",
            "name": "Receipt Extractor & Universal Assistant",
            "allowed_domains": ["*"],
            "widget_config": {
                "bot_name": "Universal Assistant",
                "primary_color": "#2563eb",
                "welcome_message_en": "Hello! How can I assist you with your receipts, documents, or questions today?",
                "welcome_message_ta": "வணக்கம்! உங்கள் ரசீதுகள், ஆவணங்கள் அல்லது கேள்விகளுக்கு இன்று நான் எவ்வாறு உதவ முடியும்?",
                "default_language": "en",
                "available_languages": ["en", "ta"],
                "allow_file_uploads": True,
                "allow_voice_input": True,
                "allow_speech_output": True,
                "enable_tawk_to": True,
                "tawk_to_property_id": None,
                "tawk_to_widget_id": None
            },
            "created_at": now_ist,
            "status": "active"
        },
        upsert=True
    )
    print("✅ Created collection 'websites' and stored default website 'site_demo'.")

    # 4b. Create 'app_connections' collection and link host Receipt Extractor DB
    app_conn_col = db["app_connections"]
    app_conn_col.replace_one(
        {"website_id": "site_demo"},
        {
            "website_id": "site_demo",
            "tenant_id": "ten_default",
            "app_name": "Receipt Extractor App",
            "db_type": "mongodb",
            "target_uri": chatbot_settings.CHATBOT_MONGODB_URI,
            "target_db": "receipt_db",
            "allowed_collection": "Receipt_Extraction",
            "allowed_fields": [
                "invoice_number", "vendor_name", "date", "category",
                "total_amount", "currency", "buyer_name", "items"
            ],
            "status": "active",
            "created_at": now_ist,
        },
        upsert=True
    )
    print("✅ Created collection 'app_connections' and linked receipt_db.Receipt_Extraction.")

    # 5. Build indexes on database 'mongodb'
    from universal_chatbot.backend.app.database.indexes import ensure_indexes
    ensure_indexes()
    print("✅ Built indexes across all collections in database 'mongodb'.")

    # 6. Verify and list databases in the cluster
    all_dbs = client.list_database_names()
    print("\n" + "=" * 60)
    print("📋 DATABASES CURRENTLY ON CLUSTER0:")
    for d in all_dbs:
        status_flag = "👈 NEW DATABASE JUST CREATED!" if d == "mongodb" else ""
        print(f"  - {d} {status_flag}")
    print("=" * 60)

    # 7. Print collections inside 'mongodb'
    cols = db.list_collection_names()
    print(f"\n📂 Collections inside database 'mongodb': {cols}")

if __name__ == "__main__":
    initialize_database()
