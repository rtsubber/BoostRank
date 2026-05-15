"""
BoostRank — SQLite Database
User accounts, API keys, audit history, rate limiting.
"""

import sqlite3
import hashlib
import secrets
import time
from pathlib import Path
from contextlib import contextmanager

DB_PATH = Path(__file__).parent.parent / "boostrank.db"


def get_db():
    """Get a database connection."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    # Don't enforce foreign keys — anonymous users have user_id=-1
    # which doesn't reference a real user row
    # conn.execute("PRAGMA foreign_keys=ON")
    return conn


@contextmanager
def db_transaction():
    """Context manager for DB transactions."""
    conn = get_db()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    """Initialize all tables."""
    conn = get_db()
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                name TEXT DEFAULT '',
                tier TEXT NOT NULL DEFAULT 'free' CHECK(tier IN ('free', 'pro', 'business', 'agency')),
                stripe_customer_id TEXT,
                created_at REAL NOT NULL DEFAULT (strftime('%s','now')),
                last_login REAL
            );

            CREATE TABLE IF NOT EXISTS api_keys (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                key_hash TEXT UNIQUE NOT NULL,
                key_prefix TEXT NOT NULL,
                name TEXT DEFAULT 'Default',
                tier TEXT NOT NULL DEFAULT 'free' CHECK(tier IN ('free', 'pro', 'business', 'agency')),
                monthly_limit INTEGER,
                requests_this_month INTEGER DEFAULT 0,
                last_reset REAL,
                created_at REAL NOT NULL DEFAULT (strftime('%s','now')),
                revoked_at REAL
            );

            CREATE TABLE IF NOT EXISTS audit_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER, -- nullable for anonymous (-1)
                api_key_id INTEGER, -- nullable for anonymous (-1)
                url TEXT NOT NULL,
                seo_score INTEGER NOT NULL,
                scores_json TEXT NOT NULL DEFAULT '{}',
                issues_json TEXT NOT NULL DEFAULT '[]',
                page_data_json TEXT NOT NULL DEFAULT '{}',
                source TEXT NOT NULL DEFAULT 'web' CHECK(source IN ('web', 'api', 'compare', 'report')),
                ip_address TEXT,
                user_agent TEXT,
                response_time_ms INTEGER,
                created_at REAL NOT NULL DEFAULT (strftime('%s','now'))
            );

            CREATE TABLE IF NOT EXISTS usage_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key_id TEXT,
                endpoint TEXT NOT NULL,
                url TEXT,
                ip_address TEXT,
                user_agent TEXT,
                status_code INTEGER DEFAULT 200,
                response_time_ms REAL,
                created_at REAL NOT NULL DEFAULT (strftime('%s','now'))
            );

            CREATE TABLE IF NOT EXISTS signups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL,
                tier TEXT NOT NULL DEFAULT 'free',
                ip_address TEXT,
                user_agent TEXT,
                created_at REAL NOT NULL DEFAULT (strftime('%s','now'))
            );

            CREATE TABLE IF NOT EXISTS rate_limits (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                action_type TEXT NOT NULL,
                count INTEGER NOT NULL DEFAULT 1,
                window_start REAL NOT NULL,
                UNIQUE(user_id, action_type, window_start)
            );

            CREATE INDEX IF NOT EXISTS idx_api_keys_hash ON api_keys(key_hash);
            CREATE INDEX IF NOT EXISTS idx_api_keys_prefix ON api_keys(key_prefix);
            CREATE INDEX IF NOT EXISTS idx_audit_history_user ON audit_history(user_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_audit_history_url ON audit_history(url);
            CREATE INDEX IF NOT EXISTS idx_rate_limits_user_action ON rate_limits(user_id, action_type, window_start);
            CREATE INDEX IF NOT EXISTS idx_usage_logs_created ON usage_logs(created_at);
            CREATE INDEX IF NOT EXISTS idx_signups_created ON signups(created_at);
        """)

        # Migrations: add columns to existing tables if they don't exist
        try:
            conn.execute("ALTER TABLE audit_history ADD COLUMN ip_address TEXT")
        except sqlite3.OperationalError:
            pass  # Column already exists
        try:
            conn.execute("ALTER TABLE audit_history ADD COLUMN user_agent TEXT")
        except sqlite3.OperationalError:
            pass
        try:
            conn.execute("ALTER TABLE audit_history ADD COLUMN response_time_ms INTEGER")
        except sqlite3.OperationalError:
            pass
    finally:
        conn.close()


# --- Password hashing (bcrypt) ---

try:
    import bcrypt as _bcrypt
    _HAS_BCRYPT = True
except ImportError:
    _HAS_BCRYPT = False


def hash_password(password: str) -> str:
    """Hash a password with bcrypt (preferred) or SHA-256+salt (fallback)."""
    if _HAS_BCRYPT:
        return _bcrypt.hashpw(password.encode(), _bcrypt.gensalt()).decode()
    # Fallback for environments without bcrypt
    salt = secrets.token_hex(16)
    h = hashlib.sha256(f"{salt}{password}".encode()).hexdigest()
    return f"{salt}${h}"


def verify_password(password: str, stored_hash: str) -> bool:
    """Verify a password against stored hash (bcrypt or legacy SHA-256)."""
    if _HAS_BCRYPT and stored_hash.startswith("$2b$"):
        return _bcrypt.checkpw(password.encode(), stored_hash.encode())
    # Legacy SHA-256+salt format
    salt, h = stored_hash.split("$", 1)
    return hashlib.sha256(f"{salt}{password}".encode()).hexdigest() == h


# --- API key management ---

def generate_api_key(prefix: str = "br") -> tuple[str, str, str]:
    """
    Generate an API key. Returns (raw_key, key_hash, key_prefix).
    The raw key is shown only once; store the hash.
    """
    token = secrets.token_urlsafe(32)
    raw_key = f"{prefix}_{token}"
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    key_prefix = raw_key[:8]  # e.g. "br_abcde"
    return raw_key, key_hash, key_prefix


# --- Rate limiting helpers ---

# Tier definitions
TIER_LIMITS = {
    "free": {
        "audit_per_month": 5,  # 5 free audits per month
        "compare_per_week": 0,
        "reports_per_week": 0,
        "api_per_month": 0,
    },
    "pro": {
        "audit_per_month": 50,
        "compare_per_week": 2,
        "reports_per_week": 1,
        "api_per_month": 0,
    },
    "business": {
        "audit_per_month": -1,  # unlimited
        "compare_per_week": 10,
        "reports_per_week": -1,  # unlimited
        "api_per_month": 1000,
    },
    "agency": {
        "audit_per_month": -1,
        "compare_per_week": -1,
        "reports_per_week": -1,
        "api_per_month": 10000,
    },
}

SECONDS_PER_DAY = 86400
SECONDS_PER_WEEK = 604800
SECONDS_PER_MONTH = 2592000


def check_rate_limit(user_id: int, action_type: str, tier: str) -> tuple[bool, int, int]:
    """
    Check if action is within rate limit.
    Returns (allowed, remaining, reset_in_seconds).
    """
    limits = TIER_LIMITS.get(tier, TIER_LIMITS["free"])

    if action_type == "audit":
        limit = limits["audit_per_month"]
        window = SECONDS_PER_MONTH
    elif action_type == "compare":
        limit = limits["compare_per_week"]
        window = SECONDS_PER_WEEK
    elif action_type == "report":
        limit = limits["reports_per_week"]
        window = SECONDS_PER_WEEK
    elif action_type == "api":
        limit = limits["api_per_month"]
        window = SECONDS_PER_MONTH
    else:
        return False, 0, 0

    # Unlimited
    if limit == -1:
        return True, -1, 0

    now = time.time()
    window_start = now - (now % window)

    conn = get_db()
    try:
        # Count actions in current window
        row = conn.execute(
            "SELECT COALESCE(SUM(count), 0) as total FROM rate_limits "
            "WHERE user_id = ? AND action_type = ? AND window_start >= ?",
            (user_id, action_type, window_start),
        ).fetchone()

        used = row["total"] if row else 0

        if used >= limit:
            return False, 0, int(window - (now % window))

        return True, limit - int(used), int(window - (now % window))
    finally:
        conn.close()


def increment_rate_limit(user_id: int, action_type: str):
    """Record an action for rate limiting."""
    now = time.time()

    if action_type in ("audit",):
        window = SECONDS_PER_DAY
    elif action_type in ("compare", "report"):
        window = SECONDS_PER_WEEK
    else:
        window = SECONDS_PER_MONTH

    window_start = now - (now % window)

    with db_transaction() as conn:
        conn.execute(
            """INSERT INTO rate_limits (user_id, action_type, count, window_start)
               VALUES (?, ?, 1, ?)
               ON CONFLICT(user_id, action_type, window_start)
               DO UPDATE SET count = count + 1""",
            (user_id, action_type, window_start),
        )


# --- Audit history ---

def save_audit(user_id: int | None, api_key_id: int | None, url: str,
               seo_score: int, scores: dict, issues: list, page_data: dict,
               source: str = "web", ip_address: str | None = None,
               user_agent: str | None = None, response_time_ms: int | None = None) -> int:
    """Save an audit to history. Returns audit ID."""
    import json

    conn = get_db()
    try:
        cursor = conn.execute(
            """INSERT INTO audit_history
               (user_id, api_key_id, url, seo_score, scores_json, issues_json, page_data_json, source, ip_address, user_agent, response_time_ms)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (user_id, api_key_id, url, seo_score,
             json.dumps(scores), json.dumps(issues), json.dumps(page_data), source,
             ip_address, user_agent, response_time_ms),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def log_usage(endpoint: str, url: str | None = None, key_id: str | None = None,
              ip_address: str | None = None, user_agent: str | None = None,
              status_code: int = 200, response_time_ms: float | None = None):
    """Log an API call for monitoring."""
    conn = get_db()
    try:
        conn.execute(
            """INSERT INTO usage_logs (key_id, endpoint, url, ip_address, user_agent, status_code, response_time_ms)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (key_id, endpoint, url, ip_address, user_agent, status_code, response_time_ms),
        )
        conn.commit()
    finally:
        conn.close()


def log_signup(email: str, tier: str = "free", ip_address: str | None = None, user_agent: str | None = None):
    """Log a user signup for monitoring."""
    conn = get_db()
    try:
        conn.execute(
            """INSERT INTO signups (email, tier, ip_address, user_agent)
               VALUES (?, ?, ?, ?)""",
            (email, tier, ip_address, user_agent),
        )
        conn.commit()
    finally:
        conn.close()


def get_user_audits(user_id: int, limit: int = 50, offset: int = 0) -> list[dict]:
    """Get audit history for a user."""
    import json

    conn = get_db()
    try:
        rows = conn.execute(
            """SELECT id, url, seo_score, scores_json, source, created_at
               FROM audit_history WHERE user_id = ?
               ORDER BY created_at DESC LIMIT ? OFFSET ?""",
            (user_id, limit, offset),
        ).fetchall()

        results = []
        for r in rows:
            results.append({
                "id": r["id"],
                "url": r["url"],
                "seo_score": r["seo_score"],
                "scores": json.loads(r["scores_json"]),
                "source": r["source"],
                "created_at": r["created_at"],
            })
        return results
    finally:
        conn.close()


def get_audit_by_id(audit_id: int) -> dict | None:
    """Get a full audit record by ID."""
    import json

    conn = get_db()
    try:
        row = conn.execute(
            "SELECT * FROM audit_history WHERE id = ?", (audit_id,)
        ).fetchone()

        if not row:
            return None

        return {
            "id": row["id"],
            "user_id": row["user_id"],
            "url": row["url"],
            "seo_score": row["seo_score"],
            "scores": json.loads(row["scores_json"]),
            "issues": json.loads(row["issues_json"]),
            "page_data": json.loads(row["page_data_json"]),
            "source": row["source"],
            "created_at": row["created_at"],
        }
    finally:
        conn.close()


# Initialize on import
init_db()