"""
MongoDB Atlas Data API client for xs-elrond.

Replaces the pymongo driver with HTTPS calls to the Atlas Data API
(port 443), allowing the CCR cloud environment to reach MongoDB
without IP-based network restrictions.

Required env vars:
    ATLAS_DATA_API_URL  — e.g. https://us-east-1.aws.data.mongodb-api.com
                          /app/data-xxxxx/endpoint/data/v1
    ATLAS_API_KEY       — Data API key with read/write on XSDashboard
    MONGO_DB            — database name (default: XSDashboard)
    ATLAS_DATA_SOURCE   — Atlas cluster name (default: Cluster0)

The public interface mirrors the subset of pymongo used by xs-elrond:
    get_collection(name)  → DataAPICollection
    collection.find_one(filter)
    collection.find(filter).sort([...]).limit(n)
    collection.insert_one(doc)       → InsertResult  (.inserted_id)
    collection.update_one(filter, update, upsert=False)
    collection.count_documents(filter)
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

import requests
from bson import ObjectId
from dotenv import load_dotenv

load_dotenv()

# ── Collection name constants (shared with xs-strider) ────────────────────────
ELROND_TASKS     = "elrond_tasks"
ELROND_POLICY    = "elrond_policy"
ELROND_AUDIT_LOG = "elrond_audit_log"
STRIDER_INBOX    = "strider_inbox"
STRIDER_OUTBOX   = "strider_outbox"
STRIDER_DIGESTS  = "strider_digests"


# ── EJSON serialization ───────────────────────────────────────────────────────

def _to_ejson(obj: Any) -> Any:
    """Recursively convert Python objects → Atlas Data API EJSON."""
    if isinstance(obj, ObjectId):
        return {"$oid": str(obj)}
    if isinstance(obj, datetime):
        ts_ms = int(obj.timestamp() * 1000)
        return {"$date": {"$numberLong": str(ts_ms)}}
    if isinstance(obj, dict):
        return {k: _to_ejson(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_to_ejson(v) for v in obj]
    return obj


def _from_ejson(obj: Any) -> Any:
    """Recursively convert Atlas Data API EJSON → Python objects."""
    if isinstance(obj, dict):
        if "$oid" in obj and len(obj) == 1:
            return ObjectId(obj["$oid"])
        if "$date" in obj and len(obj) == 1:
            date_val = obj["$date"]
            if isinstance(date_val, str):
                return datetime.fromisoformat(date_val.replace("Z", "+00:00"))
            if isinstance(date_val, dict) and "$numberLong" in date_val:
                return datetime.fromtimestamp(
                    int(date_val["$numberLong"]) / 1000, tz=timezone.utc
                )
        return {k: _from_ejson(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_from_ejson(v) for v in obj]
    return obj


def _sort_to_ejson(sort_spec: list[tuple] | dict | None) -> dict | None:
    """Convert pymongo sort spec to Atlas Data API sort object."""
    if not sort_spec:
        return None
    if isinstance(sort_spec, dict):
        return sort_spec
    # pymongo list-of-tuples: [("field", 1), ("other", -1)]
    return {field: direction for field, direction in sort_spec}


# ── Result objects ─────────────────────────────────────────────────────────────

class InsertResult:
    def __init__(self, inserted_id: ObjectId):
        self.inserted_id = inserted_id


class UpdateResult:
    def __init__(self, matched: int, modified: int, upserted_id: ObjectId | None = None):
        self.matched_count  = matched
        self.modified_count = modified
        self.upserted_id    = upserted_id


# ── Cursor ─────────────────────────────────────────────────────────────────────

class DataAPICursor:
    """Lazy cursor returned by DataAPICollection.find()."""

    def __init__(self, collection: "DataAPICollection", filter: dict):
        self._coll   = collection
        self._filter = filter
        self._sort   = None
        self._limit  = 0   # 0 = no limit

    def sort(self, sort_spec: list[tuple] | dict) -> "DataAPICursor":
        self._sort = _sort_to_ejson(sort_spec)
        return self

    def limit(self, n: int) -> "DataAPICursor":
        self._limit = n
        return self

    def __iter__(self):
        body: dict[str, Any] = {
            "dataSource": self._coll._data_source,
            "database":   self._coll._database,
            "collection": self._coll._name,
            "filter":     _to_ejson(self._filter),
        }
        if self._sort:
            body["sort"] = self._sort
        if self._limit:
            body["limit"] = self._limit

        data = self._coll._post("find", body)
        for doc in (data.get("documents") or []):
            yield _from_ejson(doc)

    def __len__(self) -> int:
        return sum(1 for _ in self)


# ── Collection ─────────────────────────────────────────────────────────────────

class DataAPICollection:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        data_source: str,
        database: str,
        name: str,
    ):
        self._base_url    = base_url.rstrip("/")
        self._api_key     = api_key
        self._data_source = data_source
        self._database    = database
        self._name        = name

    def _post(self, action: str, body: dict) -> dict:
        url = f"{self._base_url}/action/{action}"
        resp = requests.post(
            url,
            headers={
                "api-key":      self._api_key,
                "Content-Type": "application/json",
            },
            json=body,
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()

    def _base_body(self) -> dict:
        return {
            "dataSource": self._data_source,
            "database":   self._database,
            "collection": self._name,
        }

    def find_one(self, filter: dict | None = None, projection: dict | None = None) -> dict | None:
        body = {**self._base_body(), "filter": _to_ejson(filter or {})}
        if projection:
            body["projection"] = projection
        data = self._post("findOne", body)
        doc = data.get("document")
        return _from_ejson(doc) if doc else None

    def find(self, filter: dict | None = None) -> DataAPICursor:
        return DataAPICursor(self, filter or {})

    def insert_one(self, document: dict) -> InsertResult:
        body = {**self._base_body(), "document": _to_ejson(document)}
        data = self._post("insertOne", body)
        return InsertResult(ObjectId(data["insertedId"]["$oid"]))

    def update_one(self, filter: dict, update: dict, upsert: bool = False) -> UpdateResult:
        body = {
            **self._base_body(),
            "filter": _to_ejson(filter),
            "update": _to_ejson(update),
            "upsert": upsert,
        }
        data = self._post("updateOne", body)
        upserted_id = None
        if data.get("upsertedId"):
            upserted_id = ObjectId(data["upsertedId"]["$oid"])
        return UpdateResult(
            matched  = data.get("matchedCount", 0),
            modified = data.get("modifiedCount", 0),
            upserted_id = upserted_id,
        )

    def count_documents(self, filter: dict | None = None) -> int:
        # Data API doesn't have a count action — use aggregate with $count
        body = {
            **self._base_body(),
            "pipeline": [
                {"$match": _to_ejson(filter or {})},
                {"$count": "n"},
            ],
        }
        data = self._post("aggregate", body)
        docs = data.get("documents") or []
        return docs[0]["n"] if docs else 0


# ── Database proxy ─────────────────────────────────────────────────────────────

class DataAPIDatabase:
    def __init__(self, base_url: str, api_key: str, data_source: str, database: str):
        self._base_url    = base_url
        self._api_key     = api_key
        self._data_source = data_source
        self._database    = database

    def __getitem__(self, collection_name: str) -> DataAPICollection:
        return DataAPICollection(
            self._base_url, self._api_key,
            self._data_source, self._database, collection_name,
        )


# ── Public interface ───────────────────────────────────────────────────────────

def get_db(db_name: str | None = None) -> DataAPIDatabase:
    base_url    = os.environ["ATLAS_DATA_API_URL"]
    api_key     = os.environ["ATLAS_API_KEY"]
    data_source = os.environ.get("ATLAS_DATA_SOURCE", "Cluster0")
    database    = db_name or os.environ.get("MONGO_DB", "XSDashboard")
    return DataAPIDatabase(base_url, api_key, data_source, database)


def get_collection(name: str, db_name: str | None = None) -> DataAPICollection:
    return get_db(db_name)[name]
