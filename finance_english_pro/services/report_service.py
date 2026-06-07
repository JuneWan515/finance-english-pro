from __future__ import annotations

from db import get_connection


def get_report(local_user_id: int) -> dict:
    conn = get_connection()
    attempts = conn.execute(
        """
        SELECT
            COUNT(*) AS total_attempts,
            SUM(is_correct) AS correct_attempts,
            COUNT(CASE WHEN DATE(answered_at) = DATE('now') THEN 1 END) AS today_attempts,
            SUM(CASE WHEN DATE(answered_at) = DATE('now') THEN is_correct ELSE 0 END) AS today_correct
        FROM attempt_logs
        WHERE local_user_id = ?
        """,
        (local_user_id,),
    ).fetchone()
    progress = conn.execute(
        """
        SELECT
            COUNT(*) AS tracked_terms,
            SUM(is_favorite) AS favorites,
            SUM(status = 'unfamiliar') AS unfamiliar,
            SUM(status = 'mastered') AS mastered
        FROM user_progress
        WHERE local_user_id = ?
        """,
        (local_user_id,),
    ).fetchone()
    conn.close()
    total = attempts["total_attempts"] or 0
    correct = attempts["correct_attempts"] or 0
    today_total = attempts["today_attempts"] or 0
    today_correct = attempts["today_correct"] or 0
    return {
        "total_attempts": total,
        "accuracy": round(correct / total * 100, 1) if total else 0,
        "today_attempts": today_total,
        "today_accuracy": round(today_correct / today_total * 100, 1) if today_total else 0,
        "tracked_terms": progress["tracked_terms"] or 0,
        "favorites": progress["favorites"] or 0,
        "unfamiliar": progress["unfamiliar"] or 0,
        "mastered": progress["mastered"] or 0,
    }

