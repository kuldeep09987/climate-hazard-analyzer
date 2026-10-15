"""MongoDB access (NoSQL store). Two collections:
  daily    - one doc per (grid cell, year): raw Tmax array aligned to Jan 1 (None = gap)
  analyses - computed hazard analysis per (cell, period), with TTL
"""
import os
from pymongo import MongoClient, ASCENDING

_client = None


def get_db():
    global _client
    name = os.getenv("MONGO_DB", "climate")
    if _client is None:
        _client = MongoClient(os.getenv("MONGO_URI", "mongodb://localhost:27017"),
                              serverSelectionTimeoutMS=4000)
        db = _client[name]
        db.daily.create_index([("cell", ASCENDING), ("year", ASCENDING)], unique=True)
        db.analyses.create_index("key", unique=True)
        db.analyses.create_index("created_at", expireAfterSeconds=60 * 60 * 24 * 30)
    return _client[name]
