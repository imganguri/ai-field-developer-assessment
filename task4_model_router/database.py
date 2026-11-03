"""SQLite WAL-backed persistent reservations with atomic sliding-window checks."""
from __future__ import annotations
import hashlib, hmac, os, sqlite3, time, uuid
from contextlib import closing
from pathlib import Path

class RateLimitExceeded(Exception): pass

class UsageDatabase:
    def __init__(self, path: str, limit: int = 50_000, window_seconds: int = 60, clock=time.time):
        self.path, self.limit, self.window, self.clock = path, limit, window_seconds, clock
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.initialize()
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        db.execute("PRAGMA busy_timeout=10000")
        return db
    def initialize(self):
        with closing(self.connect()) as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("CREATE TABLE IF NOT EXISTS reservations (request_id TEXT PRIMARY KEY, tenant_hash TEXT NOT NULL, created_at REAL NOT NULL, reserved INTEGER NOT NULL, actual INTEGER, state TEXT NOT NULL)")
            db.execute("CREATE INDEX IF NOT EXISTS idx_reservation_tenant_time ON reservations(tenant_hash, created_at)")
    def reserve(self, tenant_hash: str, tokens: int, request_id: str | None = None) -> str:
        now, rid = self.clock(), request_id or str(uuid.uuid4())
        db = self.connect()
        try:
            db.execute("BEGIN IMMEDIATE")
            db.execute("DELETE FROM reservations WHERE created_at < ?", (now - self.window,))
            used = db.execute("SELECT COALESCE(SUM(CASE WHEN actual IS NULL THEN reserved ELSE actual END),0) FROM reservations WHERE tenant_hash=? AND created_at > ?", (tenant_hash, now-self.window)).fetchone()[0]
            if used + tokens > self.limit:
                db.rollback(); raise RateLimitExceeded
            db.execute("INSERT INTO reservations(request_id,tenant_hash,created_at,reserved,actual,state) VALUES(?,?,?,?,NULL,'reserved')", (rid, tenant_hash, now, tokens))
            db.commit(); return rid
        finally: db.close()
    def reconcile(self, request_id: str, actual_tokens: int):
        with closing(self.connect()) as db:
            db.execute("UPDATE reservations SET actual=?,state='reconciled' WHERE request_id=?", (actual_tokens, request_id))
    def usage(self, tenant_hash: str) -> int:
        now=self.clock()
        with closing(self.connect()) as db:
            return db.execute("SELECT COALESCE(SUM(CASE WHEN actual IS NULL THEN reserved ELSE actual END),0) FROM reservations WHERE tenant_hash=? AND created_at > ?", (tenant_hash,now-self.window)).fetchone()[0]
    def evict(self) -> int:
        with closing(self.connect()) as db:
            cur=db.execute("DELETE FROM reservations WHERE created_at < ?", (self.clock()-self.window,)); return cur.rowcount

def tenant_identity(api_key: str, secret: str | None = None) -> str:
    key=(secret or os.getenv("TASK4_HASH_SECRET", "local-development-hash-key")).encode()
    return hmac.new(key, api_key.encode(), hashlib.sha256).hexdigest()
