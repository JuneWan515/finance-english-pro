from __future__ import annotations

from db import get_connection, rows_to_dicts


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


def get_answered_terms(local_user_id: int, limit: int = 100, today_only: bool = False) -> list[dict]:
    date_filter = "AND DATE(a.answered_at) = DATE('now')" if today_only else ""
    conn = get_connection()
    rows = conn.execute(
        f"""
        SELECT
            a.attempt_id, a.question_type, a.selected_answer, a.correct_answer,
            a.is_correct, a.answered_at,
            t.*, e.example_sentence, e.translation
        FROM attempt_logs a
        JOIN terms t ON t.term_id = a.term_id
        LEFT JOIN examples e ON e.term_id = t.term_id
        WHERE a.local_user_id = ?
        {date_filter}
        ORDER BY a.answered_at DESC, a.attempt_id DESC
        LIMIT ?
        """,
        (local_user_id, limit),
    ).fetchall()
    conn.close()
    return rows_to_dicts(rows)


def get_report_terms(local_user_id: int, mode: str, limit: int = 100) -> list[dict]:
    where_map = {
        "tracked": "1 = 1",
        "favorites": "p.is_favorite = 1",
        "unfamiliar": "p.status = 'unfamiliar'",
        "mastered": "p.status = 'mastered'",
    }
    if mode not in where_map:
        raise ValueError(f"Unsupported report term mode: {mode}")

    conn = get_connection()
    rows = conn.execute(
        f"""
        SELECT
            t.*, e.example_sentence, e.translation,
            p.status, p.is_favorite, p.last_review_date, p.next_review_date,
            p.correct_count, p.wrong_count, p.updated_at
        FROM user_progress p
        JOIN terms t ON t.term_id = p.term_id
        LEFT JOIN examples e ON e.term_id = t.term_id
        WHERE p.local_user_id = ? AND {where_map[mode]}
        ORDER BY p.updated_at DESC, t.term_or_phrase
        LIMIT ?
        """,
        (local_user_id, limit),
    ).fetchall()
    conn.close()
    return rows_to_dicts(rows)
