

import os
from pymongo import MongoClient, ASCENDING

_client = None


def get_db():
    global _client

    name = os.getenv("MONGO_DB", "climate_hazard")
    mongo_uri = os.getenv("MONGO_URI")

    if not mongo_uri:
        raise RuntimeError(
            "MONGO_URI is missing. Configure your MongoDB Atlas connection string."
        )

    if _client is None:
        _client = MongoClient(
            mongo_uri,
            serverSelectionTimeoutMS=10000
        )

        # Verify that MongoDB is reachable.
        _client.admin.command("ping")

        db = _client[name]

        # Create required indexes.
        db.daily.create_index(
            [("cell", ASCENDING), ("year", ASCENDING)],
            unique=True
        )

        db.analyses.create_index("key", unique=True)

        db.analyses.create_index(
            "created_at",
            expireAfterSeconds=60 * 60 * 24 * 30
        )

    return _client[name]