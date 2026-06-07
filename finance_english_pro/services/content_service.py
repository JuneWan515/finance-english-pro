from __future__ import annotations

from db import get_connection, rows_to_dicts


def ensure_database() -> None:
    from scripts.init_db import execute_schema, import_terms
    from db import DB_PATH

    if not DB_PATH.exists():
        import_terms()
        return
    conn = get_connection()
    execute_schema(conn)
    total = conn.execute("SELECT COUNT(*) FROM terms").fetchone()[0]
    conn.close()
    if total == 0:
        import_terms()


def get_home_stats() -> dict:
    conn = get_connection()
    row = conn.execute(
        """
        SELECT
            COUNT(*) AS total_terms,
            SUM(review_status = 'ready') AS ready_terms,
            SUM(review_status = 'needs_review') AS needs_review_terms,
            SUM(review_status = 'search_only') AS search_only_terms
        FROM terms
        """
    ).fetchone()
    themes = conn.execute("SELECT COUNT(*) FROM themes WHERE is_visible = 1").fetchone()[0]
    conn.close()
    stats = dict(row)
    stats["visible_themes"] = themes
    return stats


def list_themes() -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT
            th.theme_id, th.display_name_cn, th.display_name_en,
            COUNT(CASE WHEN t.review_status = 'ready' THEN 1 END) AS ready_count
        FROM themes th
        JOIN term_theme_map map ON map.theme_id = th.theme_id
        JOIN terms t ON t.term_id = map.term_id
        WHERE th.is_visible = 1
        GROUP BY th.theme_id
        ORDER BY th.sort_order, th.display_name_en
        """
    ).fetchall()
    conn.close()
    return rows_to_dicts(rows)


def get_theme(theme_id: int) -> dict | None:
    conn = get_connection()
    row = conn.execute("SELECT * FROM themes WHERE theme_id = ?", (theme_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_ready_terms_by_theme(theme_id: int, limit: int = 100) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT t.*, e.example_sentence, e.translation
        FROM terms t
        LEFT JOIN examples e ON e.term_id = t.term_id
        JOIN term_theme_map map ON map.term_id = t.term_id
        WHERE map.theme_id = ? AND t.review_status = 'ready'
        ORDER BY
            CASE t.term_frequency_level
                WHEN 'high' THEN 1
                WHEN 'medium' THEN 2
                WHEN 'low' THEN 3
                ELSE 4
            END,
            t.term_or_phrase
        LIMIT ?
        """,
        (theme_id, limit),
    ).fetchall()
    conn.close()
    return rows_to_dicts(rows)


def search_terms(
    keyword: str = "",
    standard: str = "",
    domain: str = "",
    difficulty: str = "",
    status: str = "",
    limit: int = 80,
) -> list[dict]:
    clauses = []
    params: list[str] = []
    if keyword.strip():
        like = f"%{keyword.strip()}%"
        clauses.append(
            """
            (
                t.term_or_phrase LIKE ? OR t.common_abbreviation LIKE ? OR t.chinese LIKE ?
                OR t.category LIKE ? OR t.scenario LIKE ? OR t.standard_classification LIKE ?
                OR t.business_domain LIKE ? OR t.business_scenario LIKE ?
            )
            """
        )
        params.extend([like] * 8)
    if standard:
        clauses.append("t.standard_classification = ?")
        params.append(standard)
    if domain:
        clauses.append("t.business_domain = ?")
        params.append(domain)
    if difficulty:
        clauses.append("t.difficulty = ?")
        params.append(difficulty)
    if status:
        clauses.append("t.review_status = ?")
        params.append(status)
    where = "WHERE " + " AND ".join(clauses) if clauses else ""
    conn = get_connection()
    rows = conn.execute(
        f"""
        SELECT t.*, e.example_sentence, e.translation
        FROM terms t
        LEFT JOIN examples e ON e.term_id = t.term_id
        {where}
        ORDER BY t.review_status = 'ready' DESC, t.term_or_phrase
        LIMIT ?
        """,
        (*params, limit),
    ).fetchall()
    conn.close()
    return rows_to_dicts(rows)


def get_filter_values(field: str) -> list[str]:
    allowed = {"standard_classification", "business_domain", "difficulty", "review_status"}
    if field not in allowed:
        raise ValueError(f"Unsupported filter field: {field}")
    conn = get_connection()
    rows = conn.execute(
        f"SELECT DISTINCT {field} FROM terms WHERE {field} IS NOT NULL AND {field} != '' ORDER BY {field}"
    ).fetchall()
    conn.close()
    return [row[0] for row in rows]


def get_term_detail(term_id: int) -> dict | None:
    conn = get_connection()
    term = conn.execute("SELECT * FROM terms WHERE term_id = ?", (term_id,)).fetchone()
    if not term:
        conn.close()
        return None
    examples = conn.execute("SELECT * FROM examples WHERE term_id = ?", (term_id,)).fetchall()
    result = dict(term)
    result["examples"] = rows_to_dicts(examples)
    conn.close()
    return result
