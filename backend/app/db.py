"""MongoDB access (NoSQL store). Two collections:
  daily    - one doc per (grid cell, year): raw Tmax/precip arrays aligned to Jan 1 (None = gap)
  analyses - computed hazard analysis per (cell, period), with TTL
"""
import os
from pymongo import MongoClient, ASCENDING

_client = None


def _make_client():
    host = (os.getenv("MONGO_HOST") or "").strip()
    user = (os.getenv("MONGO_USER") or "").strip()
    pwd = (os.getenv("MONGO_PASS") or "").strip()
    if host and user and pwd:   # Atlas: credentials passed separately, no URI parsing or encoding issues
        print(f"MONGO mode=split user={user!r} pwd_len={len(pwd)} host={host!r}", flush=True)
        return MongoClient(f"mongodb+srv://{host}/", username=user, password=pwd,
                           authSource="admin", serverSelectionTimeoutMS=8000)
    uri = os.getenv("MONGO_URI", "mongodb://localhost:27017").strip().strip("\"'")
    print("MONGO mode=uri", flush=True)
    return MongoClient(uri, serverSelectionTimeoutMS=8000)


def get_db():
    global _client
    name = os.getenv("MONGO_DB", "climate")
    if _client is None:
        _client = _make_client()
        db = _client[name]
        db.daily.create_index([("cell", ASCENDING), ("year", ASCENDING)], unique=True)
        db.analyses.create_index("key", unique=True)
        db.analyses.create_index("created_at", expireAfterSeconds=60 * 60 * 24 * 30)
    return _client[name]