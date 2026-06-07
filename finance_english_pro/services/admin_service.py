from __future__ import annotations

from db import get_connection, rows_to_dicts


def get_quality_summary() -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT review_status, COUNT(*) AS count
        FROM terms
        GROUP BY review_status
        ORDER BY count DESC
        """
    ).fetchall()
    conn.close()
    return rows_to_dicts(rows)


def find_missing_sources(limit: int = 100) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT term_id, term_or_phrase, chinese, knowledge_source, source_section, review_status
        FROM terms
        WHERE COALESCE(knowledge_source, '') = '' OR COALESCE(source_section, '') = ''
        ORDER BY review_status, term_or_phrase
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    conn.close()
    return rows_to_dicts(rows)


def update_review_status(term_id: int, status: str, notes: str = "", reviewer: str = "local_admin") -> None:
    conn = get_connection()
    conn.execute("UPDATE terms SET review_status = ? WHERE term_id = ?", (status, term_id))
    conn.execute(
        """
        INSERT INTO content_reviews (content_type, content_id, review_status, review_notes, reviewer)
        VALUES ('term', ?, ?, ?, ?)
        """,
        (term_id, status, notes, reviewer),
    )
    conn.commit()
    conn.close()

