"""Audit Trail — tracks every issue found, fix generated, and change applied.

This is the "paper trail" that shows exactly what we found, what we fixed,
and what the before/after looks like. Every customer gets a full audit trail
with their fix delivery.
"""

import json
import time
import sqlite3
from dataclasses import dataclass, field, asdict
from typing import Optional
from pathlib import Path

DB_PATH = Path(__file__).parent.parent.parent / "data" / "boostrank_fixes.db"


def _get_db():
    """Get database connection with row factory."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_audit_trail():
    """Create audit trail tables if they don't exist."""
    conn = _get_db()
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS fix_audit_trail (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_token TEXT NOT NULL,
                url TEXT NOT NULL,
                step TEXT NOT NULL,
                category TEXT,
                severity TEXT,
                issue TEXT,
                evidence TEXT,
                element TEXT,
                before_value TEXT,
                after_value TEXT,
                fix_code TEXT,
                platform TEXT,
                notes TEXT,
                created_at REAL NOT NULL DEFAULT (strftime('%s','now'))
            );

            CREATE TABLE IF NOT EXISTS fix_score_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_token TEXT NOT NULL,
                url TEXT NOT NULL,
                score_before INTEGER NOT NULL,
                score_after INTEGER,
                scores_before_json TEXT,
                scores_after_json TEXT,
                issue_count_before INTEGER,
                issue_count_after INTEGER,
                created_at REAL NOT NULL DEFAULT (strftime('%s','now'))
            );

            CREATE TABLE IF NOT EXISTS fix_delivery_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_token TEXT NOT NULL,
                url TEXT NOT NULL,
                delivery_method TEXT NOT NULL,
                delivery_target TEXT,
                delivery_status TEXT NOT NULL,
                delivery_content_json TEXT,
                delivered_at REAL,
                created_at REAL NOT NULL DEFAULT (strftime('%s','now'))
            );

            CREATE INDEX IF NOT EXISTS idx_trail_order ON fix_audit_trail(order_token);
            CREATE INDEX IF NOT EXISTS idx_trail_step ON fix_audit_trail(step);
            CREATE INDEX IF NOT EXISTS idx_score_order ON fix_score_history(order_token);
            CREATE INDEX IF NOT EXISTS idx_delivery_order ON fix_delivery_log(order_token);
        """)
        conn.commit()
    finally:
        conn.close()


class AuditTrail:
    """Tracks the complete audit → fix → delivery lifecycle for an order."""

    def __init__(self, order_token: str, url: str):
        self.order_token = order_token
        self.url = url

    def log_audit_started(self, seo_score: int, scores: dict, platform: str):
        """Log that the audit has begun."""
        conn = _get_db()
        try:
            conn.execute(
                "INSERT INTO fix_audit_trail (order_token, url, step, category, notes, platform, created_at) "
                "VALUES (?, ?, 'audit_started', 'overview', ?, ?, strftime('%s','now'))",
                (self.order_token, self.url,
                 f"Audit started. Score: {seo_score}/100. Platform: {platform}.",
                 platform),
            )
            conn.commit()
        finally:
            conn.close()

    def log_issue_found(self, category: str, severity: str, issue: str,
                        evidence: str, element: str, before_value: str = ""):
        """Log an issue found during audit."""
        conn = _get_db()
        try:
            conn.execute(
                "INSERT INTO fix_audit_trail (order_token, url, step, category, severity, issue, evidence, element, before_value, created_at) "
                "VALUES (?, ?, 'issue_found', ?, ?, ?, ?, ?, ?, strftime('%s','now'))",
                (self.order_token, self.url, category, severity, issue,
                 evidence, element, before_value),
            )
            conn.commit()
        finally:
            conn.close()

    def log_fix_generated(self, category: str, severity: str, issue: str, element: str,
                          before_value: str, after_value: str, fix_code: str,
                          platform: str = ""):
        """Log a fix that was generated for an issue."""
        conn = _get_db()
        try:
            conn.execute(
                "INSERT INTO fix_audit_trail (order_token, url, step, category, severity, issue, element, before_value, after_value, fix_code, platform, notes, created_at) "
                "VALUES (?, ?, 'fix_generated', ?, ?, ?, ?, ?, ?, ?, ?, ?, strftime('%s','now'))",
                (self.order_token, self.url, category, severity, issue, element,
                 before_value, after_value, fix_code, platform,
                 f"Fix generated for {element}")
            )
            conn.commit()
        finally:
            conn.close()

    def log_fix_delivered(self, delivery_method: str, delivery_target: str,
                          delivery_content: dict):
        """Log that the fix package was delivered."""
        conn = _get_db()
        try:
            conn.execute(
                "INSERT INTO fix_delivery_log (order_token, url, delivery_method, delivery_target, delivery_status, delivery_content_json, delivered_at, created_at) "
                "VALUES (?, ?, ?, ?, 'sent', ?, strftime('%s','now'), strftime('%s','now'))",
                (self.order_token, self.url, delivery_method, delivery_target,
                 json.dumps(delivery_content)),
            )
            conn.execute(
                "INSERT INTO fix_audit_trail (order_token, url, step, notes, created_at) "
                "VALUES (?, ?, 'fix_delivered', ?, strftime('%s','now'))",
                (self.order_token, self.url,
                 f"Fix package delivered via {delivery_method} to {delivery_target}"),
            )
            conn.commit()
        finally:
            conn.close()

    def log_score_change(self, score_before: int, score_after: int,
                         scores_before: dict, scores_after: dict,
                         issue_count_before: int, issue_count_after: int):
        """Log the before/after SEO score change."""
        conn = _get_db()
        try:
            conn.execute(
                "INSERT INTO fix_score_history (order_token, url, score_before, score_after, scores_before_json, scores_after_json, issue_count_before, issue_count_after, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, strftime('%s','now'))",
                (self.order_token, self.url, score_before, score_after,
                 json.dumps(scores_before), json.dumps(scores_after),
                 issue_count_before, issue_count_after),
            )
            conn.commit()
        finally:
            conn.close()

    def get_trail(self) -> list:
        """Get the full audit trail for this order."""
        conn = _get_db()
        try:
            rows = conn.execute(
                "SELECT * FROM fix_audit_trail WHERE order_token = ? ORDER BY created_at",
                (self.order_token,),
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    def get_score_history(self) -> list:
        """Get score history for this order."""
        conn = _get_db()
        try:
            rows = conn.execute(
                "SELECT * FROM fix_score_history WHERE order_token = ? ORDER BY created_at",
                (self.order_token,),
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    def get_delivery_log(self) -> list:
        """Get delivery log for this order."""
        conn = _get_db()
        try:
            rows = conn.execute(
                "SELECT * FROM fix_delivery_log WHERE order_token = ? ORDER BY created_at",
                (self.order_token,),
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    def generate_report(self) -> dict:
        """Generate a complete audit trail report for customer delivery."""
        trail = self.get_trail()
        scores = self.get_score_history()
        deliveries = self.get_delivery_log()

        issues_found = [t for t in trail if t["step"] == "issue_found"]
        fixes_generated = [t for t in trail if t["step"] == "fix_generated"]
        audit_started = [t for t in trail if t["step"] == "audit_started"]
        fix_delivered = [t for t in trail if t["step"] == "fix_delivered"]

        before_after = []
        for fix in fixes_generated:
            matching_issue = next(
                (i for i in issues_found
                 if i["category"] == fix["category"] and i["element"] == fix["element"]),
                None
            )
            before_after.append({
                "category": fix["category"],
                "element": fix["element"],
                "issue": fix["issue"],
                "before": fix.get("before_value") or (matching_issue.get("before_value", "") if matching_issue else ""),
                "after": fix.get("after_value", ""),
                "fix_code": fix.get("fix_code", ""),
                "severity": matching_issue.get("severity", "medium") if matching_issue else "medium",
            })

        return {
            "order_token": self.order_token,
            "url": self.url,
            "audit_started": audit_started[0]["notes"] if audit_started else "",
            "total_issues_found": len(issues_found),
            "total_fixes_generated": len(fixes_generated),
            "issues_found": [
                {
                    "category": i["category"],
                    "severity": i["severity"],
                    "issue": i["issue"],
                    "evidence": i["evidence"],
                    "element": i["element"],
                }
                for i in issues_found
            ],
            "before_after": before_after,
            "score_change": scores[0] if scores else None,
            "delivered_via": deliveries[0]["delivery_method"] if deliveries else None,
            "delivered_at": deliveries[0]["delivered_at"] if deliveries else None,
        }


# Initialize on import
init_audit_trail()