import os

from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "climate_hazard")

if not MONGO_URI:
    raise ValueError("MONGO_URI is missing from the .env file")

client = MongoClient(
    MONGO_URI,
    serverSelectionTimeoutMS=10000
)

try:
    client.admin.command("ping")

    print("MongoDB Atlas connected successfully!")

    db = client[MONGO_DB_NAME]

    print("Database:", db.name)
    print("Existing collections:", db.list_collection_names())

except Exception as error:
    print("MongoDB Atlas connection failed.")
    print("Error:", error)

finally:
    client.close()