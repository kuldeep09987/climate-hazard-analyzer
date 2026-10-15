"""MongoDB access (NoSQL store). Two collections:
  daily    - one doc per (grid cell, year): raw Tmax/precip arrays aligned to Jan 1 (None = gap)
  analyses - computed hazard analysis per (cell, period), with TTL
"""
import os
from urllib.parse import urlparse
from pymongo import MongoClient, ASCENDING

_client = None


def _uri() -> str:
    # strip stray whitespace/newlines/quotes that sneak in when pasting env vars
    return os.getenv("MONGO_URI", "mongodb://localhost:27017").strip().strip("\"'")


def get_db():
    global _client
    name = os.getenv("MONGO_DB", "climate")
    if _client is None:
        uri = _uri()
        u = urlparse(uri)
        print(f"MONGO user={u.username!r} pwd_len={len(u.password or '')} host={u.hostname!r}", flush=True)
        _client = MongoClient(uri, authSource="admin", serverSelectionTimeoutMS=8000)
        db = _client[name]
        db.daily.create_index([("cell", ASCENDING), ("year", ASCENDING)], unique=True)
        db.analyses.create_index("key", unique=True)
        db.analyses.create_index("created_at", expireAfterSeconds=60 * 60 * 24 * 30)
    return _client[name]