"""
MongoDB client for xs-elrond.
Thin wrapper — xs-elrond shares the XSDashboard database with xs-strider.
Collection constants duplicated here to avoid a cross-repo import dependency.
"""
from __future__ import annotations

import os

from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.database import Database

load_dotenv()

# ── Collection names (shared with xs-strider) ────────────────────────────────
ELROND_TASKS = "elrond_tasks"
ELROND_POLICY = "elrond_policy"
ELROND_AUDIT_LOG = "elrond_audit_log"
STRIDER_INBOX = "strider_inbox"
STRIDER_OUTBOX = "strider_outbox"
STRIDER_DIGESTS = "strider_digests"

_client: MongoClient | None = None


def get_client() -> MongoClient:
    global _client
    if _client is None:
        uri = os.environ["MONGO_URI"]
        _client = MongoClient(uri)
    return _client


def get_db(db_name: str | None = None) -> Database:
    db_name = db_name or os.environ.get("MONGO_DB", "XSDashboard")
    return get_client()[db_name]


def get_collection(name: str, db_name: str | None = None) -> Collection:
    return get_db(db_name)[name]
