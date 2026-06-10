from __future__ import annotations

import csv
import sqlite3
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from db import DB_PATH, SEED_CSV, SOURCE_CSV, SOURCE_XLSX, get_connection


REQUIRED_READY_FIELDS = (
    "term_or_phrase",
    "chinese",
    "example_sentence",
    "translation",
    "source_section",
    "knowledge_source",
)

CSV_ENCODINGS = ("utf-8-sig", "utf-8", "gb18030", "gbk", "big5")


def normalize(value: str | None) -> str:
    if value is None:
        return ""
    if pd.isna(value):
        return ""
    return str(value).strip()


def content_key(row: dict[str, str]) -> str:
    term = normalize(row.get("term_or_phrase")).casefold()
    chinese = normalize(row.get("chinese"))
    return f"{term}::{chinese}"


def review_status(row: dict[str, str]) -> str:
    if all(normalize(row.get(field)) for field in REQUIRED_READY_FIELDS):
        return "ready"
    if normalize(row.get("term_or_phrase")) and normalize(row.get("chinese")):
        return "search_only"
    return "needs_review"


def example_quality(row: dict[str, str], status: str) -> str:
    if status == "ready":
        term = normalize(row.get("term_or_phrase")).lower()
        sentence = normalize(row.get("example_sentence")).lower()
        return "ready" if term and term in sentence else "needs_review"
    return status


def infer_source_type(row: dict[str, str]) -> str:
    source = f"{row.get('knowledge_source', '')} {row.get('source_section', '')}".lower()
    if "annual" in source or "model accounts" in source:
        return "annual_report"
    if "ifrs" in source or "ias" in source or "standard" in source:
        return "standard"
    if "audit" in source:
        return "audit"
    return "reference"


def execute_schema(conn: sqlite3.Connection) -> None:
    conn.executescript((ROOT / "schema.sql").read_text(encoding="utf-8"))
    ensure_columns(conn)


def ensure_columns(conn: sqlite3.Connection) -> None:
    columns = {row[1] for row in conn.execute("PRAGMA table_info(terms)").fetchall()}
    if "content_key" not in columns:
        conn.execute("ALTER TABLE terms ADD COLUMN content_key TEXT")
    if "definition_cn" not in columns:
        conn.execute("ALTER TABLE terms ADD COLUMN definition_cn TEXT")
    conn.execute(
        """
        UPDATE terms
        SET content_key = lower(trim(term_or_phrase)) || '::' || trim(chinese)
        WHERE content_key IS NULL OR content_key = ''
        """
    )
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_terms_content_key ON terms(content_key)")


def reset_runtime_tables(conn: sqlite3.Connection) -> None:
    for table in (
        "attempt_logs",
        "user_progress",
        "local_users",
        "content_reviews",
        "term_theme_map",
        "themes",
        "examples",
        "terms",
        "source_documents",
    ):
        conn.execute(f"DELETE FROM {table}")


def reset_content_tables(conn: sqlite3.Connection) -> None:
    for table in ("term_theme_map", "themes", "examples", "terms", "source_documents"):
        conn.execute(f"DELETE FROM {table}")


def read_csv_rows(path: Path) -> tuple[list[dict[str, str]], str]:
    last_error: UnicodeDecodeError | None = None
    for encoding in CSV_ENCODINGS:
        try:
            with path.open(newline="", encoding=encoding) as fh:
                return list(csv.DictReader(fh)), encoding
        except UnicodeDecodeError as exc:
            last_error = exc
    raise UnicodeDecodeError(
        last_error.encoding if last_error else "unknown",
        last_error.object if last_error else b"",
        last_error.start if last_error else 0,
        last_error.end if last_error else 1,
        "CSV encoding is not supported. Please save the file as UTF-8 or GB18030.",
    )


def load_source_rows(source_path: Path | None = None) -> tuple[list[dict[str, str]], Path]:
    path = source_path
    if path is None:
        for candidate in (SOURCE_XLSX, SEED_CSV, SOURCE_CSV):
            if candidate.exists():
                path = candidate
                break
    if path is None:
        raise FileNotFoundError(
            "No source file found. Expected one of: "
            f"{SOURCE_XLSX}, {SEED_CSV}, {SOURCE_CSV}"
        )
    if not path.exists():
        raise FileNotFoundError(f"Source file not found: {path}")
    if path.suffix.lower() in {".xlsx", ".xlsm", ".xls"}:
        df = pd.read_excel(path, sheet_name="Extract")
        return df.to_dict(orient="records"), path
    rows, _encoding = read_csv_rows(path)
    return rows, path


def import_terms(source_path: Path | None = None, reset: bool = True) -> dict[str, int]:
    rows, used_path = load_source_rows(source_path)

    conn = get_connection()
    execute_schema(conn)
    if reset:
        reset_runtime_tables(conn)
    else:
        reset_content_tables(conn)

    counts = {"terms": 0, "examples": 0, "ready": 0, "search_only": 0, "needs_review": 0}
    categories: dict[str, int] = {}
    for row in rows:
        status = review_status(row)
        counts[status] += 1
        term_values = {
            "content_key": content_key(row),
            "term_or_phrase": normalize(row.get("term_or_phrase")),
            "common_abbreviation": normalize(row.get("common_abbreviation")),
            "type": normalize(row.get("type")),
            "chinese": normalize(row.get("chinese")),
            "category": normalize(row.get("category")),
            "scenario": normalize(row.get("scenario")),
            "definition_en": normalize(row.get("definition_en")),
            "definition_cn": normalize(row.get("definition_cn")),
            "difficulty": normalize(row.get("difficulty")),
            "standard_classification": normalize(row.get("standard_classification")),
            "business_domain": normalize(row.get("business_domain")),
            "term_frequency_level": normalize(row.get("term_frequency_level")),
            "business_scenario": normalize(row.get("business_scenario")),
            "knowledge_source": normalize(row.get("knowledge_source")),
            "source_section": normalize(row.get("source_section")),
            "review_status": status,
        }
        cur = conn.execute(
            """
            INSERT INTO terms (
                content_key, term_or_phrase, common_abbreviation, type, chinese, category, scenario,
                definition_en, definition_cn, difficulty, standard_classification, business_domain,
                term_frequency_level, business_scenario, knowledge_source, source_section,
                review_status
            ) VALUES (
                :content_key, :term_or_phrase, :common_abbreviation, :type, :chinese, :category, :scenario,
                :definition_en, :definition_cn, :difficulty, :standard_classification, :business_domain,
                :term_frequency_level, :business_scenario, :knowledge_source, :source_section,
                :review_status
            )
            """,
            term_values,
        )
        term_id = cur.lastrowid
        counts["terms"] += 1

        quality = example_quality(row, status)
        conn.execute(
            """
            INSERT INTO examples (
                term_id, example_sentence, translation, source_section, source_type,
                source_file, source_line, quality_status
            ) VALUES (?, ?, ?, ?, ?, ?, NULL, ?)
            """,
            (
                term_id,
                normalize(row.get("example_sentence")),
                normalize(row.get("translation")),
                normalize(row.get("source_section")),
                infer_source_type(row),
                normalize(row.get("knowledge_source")),
                quality,
            ),
        )
        counts["examples"] += 1

        source_file = normalize(row.get("knowledge_source")) or "Unspecified source"
        conn.execute(
            """
            INSERT OR IGNORE INTO source_documents
            (source_file, source_type, source_title, notes)
            VALUES (?, ?, ?, ?)
            """,
            (source_file, infer_source_type(row), source_file, f"Imported from {used_path.name}"),
        )

        category = normalize(row.get("category")) or "General"
        categories[category] = categories.get(category, 0) + (1 if status == "ready" else 0)

    build_themes(conn, categories)
    conn.commit()
    conn.close()
    counts["source"] = str(used_path)
    return counts


def term_values_from_row(row: dict[str, str], status: str) -> dict[str, str]:
    return {
        "content_key": content_key(row),
        "term_or_phrase": normalize(row.get("term_or_phrase")),
        "common_abbreviation": normalize(row.get("common_abbreviation")),
        "type": normalize(row.get("type")),
        "chinese": normalize(row.get("chinese")),
        "category": normalize(row.get("category")),
        "scenario": normalize(row.get("scenario")),
        "definition_en": normalize(row.get("definition_en")),
        "definition_cn": normalize(row.get("definition_cn")),
        "difficulty": normalize(row.get("difficulty")),
        "standard_classification": normalize(row.get("standard_classification")),
        "business_domain": normalize(row.get("business_domain")),
        "term_frequency_level": normalize(row.get("term_frequency_level")),
        "business_scenario": normalize(row.get("business_scenario")),
        "knowledge_source": normalize(row.get("knowledge_source")),
        "source_section": normalize(row.get("source_section")),
        "review_status": status,
    }


def insert_example(conn: sqlite3.Connection, term_id: int, row: dict[str, str], status: str) -> None:
    conn.execute(
        """
        INSERT INTO examples (
            term_id, example_sentence, translation, source_section, source_type,
            source_file, source_line, quality_status
        ) VALUES (?, ?, ?, ?, ?, ?, NULL, ?)
        """,
        (
            term_id,
            normalize(row.get("example_sentence")),
            normalize(row.get("translation")),
            normalize(row.get("source_section")),
            infer_source_type(row),
            normalize(row.get("knowledge_source")),
            example_quality(row, status),
        ),
    )


def upsert_terms(source_path: Path | None = None) -> dict[str, int | str]:
    rows, used_path = load_source_rows(source_path)
    conn = get_connection()
    execute_schema(conn)

    existing = {
        row["content_key"]: row["term_id"]
        for row in conn.execute("SELECT term_id, content_key FROM terms WHERE content_key IS NOT NULL AND content_key != ''")
    }
    incoming_keys = {content_key(row) for row in rows if content_key(row)}
    deleted_keys = set(existing) - incoming_keys
    if deleted_keys:
        placeholders = ",".join("?" for _ in deleted_keys)
        conn.execute(f"DELETE FROM terms WHERE content_key IN ({placeholders})", tuple(deleted_keys))

    conn.execute("DELETE FROM examples")
    conn.execute("DELETE FROM term_theme_map")
    conn.execute("DELETE FROM themes")
    conn.execute("DELETE FROM source_documents")

    counts: dict[str, int | str] = {
        "terms": 0,
        "examples": 0,
        "ready": 0,
        "search_only": 0,
        "needs_review": 0,
        "inserted": 0,
        "updated": 0,
        "deleted": len(deleted_keys),
        "preserved": 0,
    }
    categories: dict[str, int] = {}
    for row in rows:
        key = content_key(row)
        if not key:
            continue
        status = review_status(row)
        counts[status] = int(counts[status]) + 1
        values = term_values_from_row(row, status)
        term_id = existing.get(key)
        if term_id and key not in deleted_keys:
            conn.execute(
                """
                UPDATE terms SET
                    term_or_phrase = :term_or_phrase,
                    common_abbreviation = :common_abbreviation,
                    type = :type,
                    chinese = :chinese,
                    category = :category,
                    scenario = :scenario,
                    definition_en = :definition_en,
                    definition_cn = :definition_cn,
                    difficulty = :difficulty,
                    standard_classification = :standard_classification,
                    business_domain = :business_domain,
                    term_frequency_level = :term_frequency_level,
                    business_scenario = :business_scenario,
                    knowledge_source = :knowledge_source,
                    source_section = :source_section,
                    review_status = :review_status
                WHERE term_id = :term_id
                """,
                {**values, "term_id": term_id},
            )
            counts["updated"] = int(counts["updated"]) + 1
            counts["preserved"] = int(counts["preserved"]) + 1
        else:
            cur = conn.execute(
                """
                INSERT INTO terms (
                    content_key, term_or_phrase, common_abbreviation, type, chinese, category, scenario,
                    definition_en, definition_cn, difficulty, standard_classification, business_domain,
                    term_frequency_level, business_scenario, knowledge_source, source_section,
                    review_status
                ) VALUES (
                    :content_key, :term_or_phrase, :common_abbreviation, :type, :chinese, :category, :scenario,
                    :definition_en, :definition_cn, :difficulty, :standard_classification, :business_domain,
                    :term_frequency_level, :business_scenario, :knowledge_source, :source_section,
                    :review_status
                )
                """,
                values,
            )
            term_id = cur.lastrowid
            counts["inserted"] = int(counts["inserted"]) + 1

        insert_example(conn, int(term_id), row, status)
        counts["examples"] = int(counts["examples"]) + 1
        counts["terms"] = int(counts["terms"]) + 1

        source_file = normalize(row.get("knowledge_source")) or "Unspecified source"
        conn.execute(
            """
            INSERT OR IGNORE INTO source_documents
            (source_file, source_type, source_title, notes)
            VALUES (?, ?, ?, ?)
            """,
            (source_file, infer_source_type(row), source_file, f"Imported from {used_path.name}"),
        )
        category = normalize(row.get("category")) or "General"
        categories[category] = categories.get(category, 0) + (1 if status == "ready" else 0)

    build_themes(conn, categories)
    conn.commit()
    conn.close()
    counts["source"] = str(used_path)
    return counts


def build_themes(conn: sqlite3.Connection, categories: dict[str, int]) -> None:
    for order, (category, ready_count) in enumerate(sorted(categories.items()), start=1):
        is_visible = 1 if ready_count >= 20 else 0
        cur = conn.execute(
            """
            INSERT INTO themes
            (theme_name, display_name_cn, display_name_en, is_visible, sort_order)
            VALUES (?, ?, ?, ?, ?)
            """,
            (category, category, category, is_visible, order),
        )
        theme_id = cur.lastrowid
        conn.execute(
            """
            INSERT OR IGNORE INTO term_theme_map (term_id, theme_id)
            SELECT term_id, ? FROM terms WHERE COALESCE(category, 'General') = ?
            """,
            (theme_id, category),
        )


if __name__ == "__main__":
    result = import_terms()
    print(f"SQLite database: {DB_PATH}")
    print(result)
