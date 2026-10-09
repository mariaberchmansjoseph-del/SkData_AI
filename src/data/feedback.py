"""
User feedback collection.
Stores thumbs up/down on SQL agent results.
src/data/feedback.py
"""

import sqlite3
import logging
from datetime import datetime

DB_PATH = "data/processed/skdata.db"
log     = logging.getLogger("Feedback")


def init_feedback_table():
    """Create feedback table if not exists."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS user_feedback (
            id         INTEGER PRIMARY KEY,
            created_at TEXT,
            question   TEXT,
            sql        TEXT,
            rating     TEXT,
            comment    TEXT,
            row_count  INTEGER,
            latency_ms INTEGER
        )
    """)
    conn.commit()
    conn.close()


def save_feedback(
    question:   str,
    sql:        str,
    rating:     str,
    comment:    str = "",
    row_count:  int = 0,
    latency_ms: int = 0,
) -> bool:
    """
    Save user feedback.
    rating: 'positive' or 'negative'
    """
    try:
        init_feedback_table()
        conn = sqlite3.connect(DB_PATH)
        conn.execute("""
            INSERT INTO user_feedback
            (created_at, question, sql, rating,
             comment, row_count, latency_ms)
            VALUES (?,?,?,?,?,?,?)
        """, (
            datetime.now().isoformat(),
            question, sql, rating,
            comment, row_count, latency_ms,
        ))
        conn.commit()
        conn.close()
        log.info(
            f"Feedback saved: {rating} "
            f"for '{question[:40]}'"
        )
        return True
    except Exception as e:
        log.error(f"Feedback save failed: {e}")
        return False


def get_feedback_stats() -> dict:
    """Get overall feedback statistics."""
    try:
        conn = sqlite3.connect(DB_PATH)
        rows = conn.execute("""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN rating='positive'
                    THEN 1 ELSE 0 END) as positive,
                SUM(CASE WHEN rating='negative'
                    THEN 1 ELSE 0 END) as negative
            FROM user_feedback
        """).fetchone()
        conn.close()

        total    = rows[0] or 0
        positive = rows[1] or 0
        negative = rows[2] or 0

        return {
            "total":        total,
            "positive":     positive,
            "negative":     negative,
            "positive_pct": round(
                positive/total*100
            ) if total else 0,
        }
    except Exception:
        return {}


def get_negative_feedback(
    limit: int = 20
) -> list:
    """
    Get recent negative feedback for review.
    These are the questions to improve.
    """
    try:
        conn  = sqlite3.connect(DB_PATH)
        rows  = conn.execute("""
            SELECT created_at, question,
                   sql, comment, row_count
            FROM user_feedback
            WHERE rating = 'negative'
            ORDER BY id DESC
            LIMIT ?
        """, (limit,)).fetchall()
        conn.close()

        return [
            {
                "time":      r[0][:16],
                "question":  r[1],
                "sql":       r[2],
                "comment":   r[3],
                "row_count": r[4],
            }
            for r in rows
        ]
    except Exception:
        return []
