# clients/history_store.py
from __future__ import annotations
import os, psycopg2
from typing import Optional, List, Dict, Any
from psycopg2.extras import Json, RealDictCursor

def _conn():
    return psycopg2.connect(
        host=os.getenv("DB_HOST"),
        port=os.getenv("DB_PORT"),
        dbname=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
    )

def ensure_history_schema() -> None:
    with _conn() as conn, conn.cursor() as cur:
        cur.execute("""
        CREATE TABLE IF NOT EXISTS events (
          id         BIGSERIAL PRIMARY KEY,
          client_id  TEXT,
          kind       TEXT NOT NULL,
          title      TEXT,
          data       JSONB,
          file_path  TEXT,
          created_at TIMESTAMP DEFAULT NOW()
        );
        CREATE INDEX IF NOT EXISTS events_client_created_idx
          ON events (client_id, created_at DESC);
        """)
        conn.commit()

def save_event(kind: str, title: str, data: Optional[Dict[str, Any]] = None,
               file_path: Optional[str] = None, client_id: Optional[str] = None) -> Dict[str, Any]:
    with _conn() as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO events (client_id, kind, title, data, file_path) VALUES (%s,%s,%s,%s,%s) RETURNING id, created_at",
            (client_id, kind, title, Json(data or {}), file_path),
        )
        eid, created = cur.fetchone()
        conn.commit()
        return {"id": eid, "created_at": created.isoformat()}

def list_events(client_id: str, limit: int = 100) -> List[Dict[str, Any]]:
    with _conn() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("""
            SELECT id, kind, title, created_at,
                   (file_path IS NOT NULL) AS has_file
            FROM events
            WHERE client_id = %s
            ORDER BY created_at DESC
            LIMIT %s
        """, (client_id, limit))
        return [dict(r) for r in cur.fetchall()]

def get_event(event_id: int, client_id: Optional[str]) -> Optional[Dict[str, Any]]:
    with _conn() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("""
            SELECT id, client_id, kind, title, data, file_path, created_at
            FROM events
            WHERE id = %s AND (client_id = %s OR %s IS NULL)
        """, (event_id, client_id, client_id))
        row = cur.fetchone()
        return dict(row) if row else None
