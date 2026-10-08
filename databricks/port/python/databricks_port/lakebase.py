"""App-owned PostgreSQL state with renewable Databricks OAuth credentials."""

import os
import re
import secrets
import threading
import time
from contextlib import contextmanager
from functools import lru_cache

import psycopg2
from databricks.sdk import WorkspaceClient
from psycopg2 import sql

_credential = None
_credential_until = 0
_credential_lock = threading.Lock()


@lru_cache
def workspace():
    return WorkspaceClient()


def schema_name():
    name = os.environ["OPENCONTRACTS_SCHEMA"]
    if not re.fullmatch(r"[a-z][a-z0-9_]{0,62}", name):
        raise ValueError("OPENCONTRACTS_SCHEMA must be a PostgreSQL identifier")
    return name


def password():
    global _credential, _credential_until
    with _credential_lock:
        if _credential is None or time.monotonic() >= _credential_until:
            value = workspace().postgres.generate_database_credential(
                endpoint=os.environ["LAKEBASE_ENDPOINT"]
            )
            seconds = min(1800, value.expire_time.seconds - time.time() - 60)
            if not value.token or seconds <= 0:
                raise RuntimeError("Lakebase credential has no usable lifetime")
            _credential, _credential_until = value.token, time.monotonic() + seconds
        return _credential


def connection_params():
    return {
        "host": os.environ["PGHOST"],
        "dbname": os.environ["PGDATABASE"],
        "port": os.environ.get("PGPORT", "5432"),
        "user": os.environ.get("PGUSER") or workspace().config.client_id,
        "password": password(),
        "sslmode": "require",
        "connect_timeout": 30,
        "options": f"-c search_path={schema_name()},public",
    }


@contextmanager
def connect():
    database = psycopg2.connect(**connection_params())
    try:
        with database:
            yield database
    finally:
        database.close()


def bootstrap():
    """Create only this app's schema and preserve its signing key on redeploy."""
    with connect() as db, db.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (schema_name(),))
        cursor.execute(
            sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(
                sql.Identifier(schema_name())
            )
        )
        cursor.execute(
            "CREATE TABLE IF NOT EXISTS port_meta (key text PRIMARY KEY, value text NOT NULL)"
        )
        cursor.execute(
            "CREATE TABLE IF NOT EXISTS port_blob (name text PRIMARY KEY, content bytea NOT NULL)"
        )
        cursor.execute(
            "CREATE TABLE IF NOT EXISTS port_calls (id bigserial PRIMARY KEY, "
            "endpoint text NOT NULL, started timestamptz NOT NULL DEFAULT now(), "
            "finished timestamptz, http_status integer, usage jsonb)"
        )
        cursor.execute(
            "INSERT INTO port_meta VALUES ('django_secret', %s) ON CONFLICT DO NOTHING",
            (secrets.token_urlsafe(64),),
        )
        cursor.execute("SELECT value FROM port_meta WHERE key='django_secret'")
        os.environ["DJANGO_SECRET_KEY"] = cursor.fetchone()[0]


def begin_call(endpoint):
    with connect() as db, db.cursor() as cursor:
        cursor.execute(
            "INSERT INTO port_calls(endpoint) VALUES (%s) RETURNING id", (endpoint,)
        )
        return cursor.fetchone()[0]


def finish_call(call_id, status, usage):
    import json

    with connect() as db, db.cursor() as cursor:
        cursor.execute(
            "UPDATE port_calls SET finished=now(),http_status=%s,usage=%s WHERE id=%s",
            (status, json.dumps(usage), call_id),
        )
