from __future__ import annotations

from datetime import date, timedelta
from uuid import uuid4

import streamlit as st

from db import get_connection, rows_to_dicts


def ensure_progress_columns(conn) -> None:
    columns = {row[1] for row in conn.execute("PRAGMA table_info(user_progress)").fetchall()}
    if "review_stage" not in columns:
        conn.execute("ALTER TABLE user_progress ADD COLUMN review_stage INTEGER NOT NULL DEFAULT 0")
    if "next_attempt_number" not in columns:
        conn.execute("ALTER TABLE user_progress ADD COLUMN next_attempt_number INTEGER")
    conn.execute("UPDATE user_progress SET status = 'new' WHERE status = 'learning'")


def get_local_user_id(device_id: str | None = None) -> int:
    if not device_id:
        if "device_id" not in st.session_state:
            st.session_state.device_id = str(uuid4())
        device_id = st.session_state.device_id
    conn = get_connection()
    conn.execute(
        """
        INSERT INTO local_users (device_id)
        VALUES (?)
        ON CONFLICT(device_id) DO UPDATE SET last_active_at = CURRENT_TIMESTAMP
        """,
        (device_id,),
    )
    user_id = conn.execute(
        "SELECT local_user_id FROM local_users WHERE device_id = ?", (device_id,)
    ).fetchone()[0]
    conn.commit()
    conn.close()
    return user_id


def get_progress(local_user_id: int, term_id: int) -> dict:
    conn = get_connection()
    ensure_progress_columns(conn)
    row = conn.execute(
        "SELECT * FROM user_progress WHERE local_user_id = ? AND term_id = ?",
        (local_user_id, term_id),
    ).fetchone()
    conn.close()
    return dict(row) if row else {"status": "new", "is_favorite": 0}


def upsert_progress(local_user_id: int, term_id: int, status: str | None = None, is_favorite: bool | None = None) -> None:
    conn = get_connection()
    ensure_progress_columns(conn)
    current = conn.execute(
        "SELECT * FROM user_progress WHERE local_user_id = ? AND term_id = ?",
        (local_user_id, term_id),
    ).fetchone()
    current_status = status or (current["status"] if current else "new")
    if current_status == "learning":
        current_status = "new"
    current_favorite = int(is_favorite) if is_favorite is not None else int(current["is_favorite"]) if current else 0
    today = date.today()
    if current_status == "unfamiliar":
        next_review = today + timedelta(days=1)
    elif current_status == "mastered":
        next_review = today + timedelta(days=14)
    else:
        next_review = today + timedelta(days=7)
    conn.execute(
        """
        INSERT INTO user_progress (
            local_user_id, term_id, status, is_favorite, last_review_date, next_review_date, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(local_user_id, term_id) DO UPDATE SET
            status = excluded.status,
            is_favorite = excluded.is_favorite,
            last_review_date = excluded.last_review_date,
            next_review_date = excluded.next_review_date,
            updated_at = CURRENT_TIMESTAMP
        """,
        (local_user_id, term_id, current_status, current_favorite, today.isoformat(), next_review.isoformat()),
    )
    conn.commit()
    conn.close()


def record_attempt(local_user_id: int, term_id: int, question_type: str, selected: str, correct: str, is_correct: bool) -> None:
    conn = get_connection()
    ensure_progress_columns(conn)
    conn.execute(
        """
        INSERT INTO attempt_logs
        (local_user_id, term_id, question_type, selected_answer, correct_answer, is_correct)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (local_user_id, term_id, question_type, selected, correct, int(is_correct)),
    )
    total_attempts = conn.execute(
        "SELECT COUNT(*) FROM attempt_logs WHERE local_user_id = ?", (local_user_id,)
    ).fetchone()[0]
    current = conn.execute(
        "SELECT status, review_stage FROM user_progress WHERE local_user_id = ? AND term_id = ?",
        (local_user_id, term_id),
    ).fetchone()
    current_status = current["status"] if current else "new"
    current_stage = int(current["review_stage"] or 0) if current else 0
    if is_correct and current_status == "unfamiliar" and current_stage == 1:
        next_status = "unfamiliar"
        next_stage = 2
        next_attempt_number = total_attempts + 10
    elif is_correct:
        next_status = "mastered"
        next_stage = 0
        next_attempt_number = None
    else:
        next_status = "unfamiliar"
        next_stage = 1
        next_attempt_number = total_attempts + 10

    counter = "correct_count" if is_correct else "wrong_count"
    conn.execute(
        f"""
        INSERT INTO user_progress (
            local_user_id, term_id, status, last_review_date, next_review_date,
            review_stage, next_attempt_number, {counter}
        )
        VALUES (?, ?, ?, DATE('now'), DATE('now', '+7 days'), ?, ?, 1)
        ON CONFLICT(local_user_id, term_id) DO UPDATE SET
            {counter} = {counter} + 1,
            status = ?,
            last_review_date = DATE('now'),
            next_review_date = DATE('now', '+7 days'),
            review_stage = ?,
            next_attempt_number = ?,
            updated_at = CURRENT_TIMESTAMP
        """,
        (local_user_id, term_id, next_status, next_stage, next_attempt_number, next_status, next_stage, next_attempt_number),
    )
    conn.commit()
    conn.close()


def get_due_reviews(local_user_id: int, mode: str = "due") -> list[dict]:
    conn = get_connection()
    ensure_progress_columns(conn)
    if mode == "favorites":
        where = "p.is_favorite = 1"
    elif mode == "unfamiliar":
        where = "p.status = 'unfamiliar'"
    else:
        where = "(p.next_review_date IS NULL OR p.next_review_date <= DATE('now') OR p.status = 'unfamiliar')"
    rows = conn.execute(
        f"""
        SELECT
            t.*, e.example_sentence, e.translation,
            p.status, p.is_favorite, p.next_review_date, p.correct_count, p.wrong_count
        FROM user_progress p
        JOIN terms t ON t.term_id = p.term_id
        LEFT JOIN examples e ON e.term_id = t.term_id
        WHERE p.local_user_id = ? AND {where}
        ORDER BY p.next_review_date IS NULL DESC, p.next_review_date, t.term_or_phrase
        """,
        (local_user_id,),
    ).fetchall()
    conn.close()
    return rows_to_dicts(rows)
