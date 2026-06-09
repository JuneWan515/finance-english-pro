from __future__ import annotations

import random
import re

from db import get_connection, rows_to_dicts
from services.progress_service import ensure_progress_columns


def split_phrase(term: str | None) -> list[str]:
    if not term:
        return []
    return re.findall(r"[A-Za-z0-9]+(?:[-'][A-Za-z0-9]+)?", term)


def get_question_pool(theme_id: int | None = None, limit: int = 80, local_user_id: int | None = None) -> list[dict]:
    conn = get_connection()
    ensure_progress_columns(conn)
    user_id = local_user_id or -1
    total_attempts = conn.execute(
        "SELECT COUNT(*) FROM attempt_logs WHERE local_user_id = ?", (user_id,)
    ).fetchone()[0]
    if theme_id:
        rows = conn.execute(
            """
            SELECT
                t.term_id, t.term_or_phrase, t.chinese, t.category, t.definition_en,
                t.definition_cn, t.common_abbreviation, t.review_status, t.standard_classification, t.business_domain,
                t.knowledge_source, t.term_frequency_level, t.scenario, t.business_scenario,
                e.example_sentence, e.translation,
                e.source_file, e.source_section, e.quality_status,
                CASE WHEN p.status = 'unfamiliar' AND COALESCE(p.next_attempt_number, 0) <= ? THEN 1 ELSE 0 END AS is_due_review
            FROM terms t
            LEFT JOIN examples e ON e.term_id = t.term_id
            LEFT JOIN user_progress p ON p.term_id = t.term_id AND p.local_user_id = ?
            JOIN term_theme_map map ON map.term_id = t.term_id
            WHERE t.review_status = 'ready' AND map.theme_id = ?
                AND (
                    p.local_user_id IS NULL
                    OR p.status NOT IN ('unfamiliar', 'mastered')
                    OR (p.status = 'unfamiliar' AND COALESCE(p.next_attempt_number, 0) <= ?)
                )
            ORDER BY
                CASE WHEN p.status = 'unfamiliar' AND COALESCE(p.next_attempt_number, 0) <= ? THEN 0 ELSE 1 END,
                RANDOM()
            LIMIT ?
            """,
            (total_attempts, user_id, theme_id, total_attempts, total_attempts, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT
                t.term_id, t.term_or_phrase, t.chinese, t.category, t.definition_en,
                t.definition_cn, t.common_abbreviation, t.review_status, t.standard_classification, t.business_domain,
                t.knowledge_source, t.term_frequency_level, t.scenario, t.business_scenario,
                e.example_sentence, e.translation,
                e.source_file, e.source_section, e.quality_status,
                CASE WHEN p.status = 'unfamiliar' AND COALESCE(p.next_attempt_number, 0) <= ? THEN 1 ELSE 0 END AS is_due_review
            FROM terms t
            LEFT JOIN examples e ON e.term_id = t.term_id
            LEFT JOIN user_progress p ON p.term_id = t.term_id AND p.local_user_id = ?
            WHERE t.review_status = 'ready'
                AND (
                    p.local_user_id IS NULL
                    OR p.status NOT IN ('unfamiliar', 'mastered')
                    OR (p.status = 'unfamiliar' AND COALESCE(p.next_attempt_number, 0) <= ?)
                )
            ORDER BY
                CASE WHEN p.status = 'unfamiliar' AND COALESCE(p.next_attempt_number, 0) <= ? THEN 0 ELSE 1 END,
                RANDOM()
            LIMIT ?
            """,
            (total_attempts, user_id, total_attempts, total_attempts, limit),
        ).fetchall()
    conn.close()
    return rows_to_dicts(rows)


def create_question(theme_id: int | None = None, preferred_type: str | None = None, local_user_id: int | None = None) -> dict | None:
    pool = get_question_pool(theme_id, local_user_id=local_user_id)
    if len(pool) < 4:
        return None
    phrase_pool = [item for item in pool if len(split_phrase(item["term_or_phrase"])) >= 2]
    question_type = preferred_type if preferred_type in {"en_to_cn", "cn_to_en", "word_assembly"} else random.choice(["en_to_cn", "cn_to_en", "word_assembly"])
    due_answer = pool[0] if pool[0].get("is_due_review") else None
    answer = due_answer or (random.choice(phrase_pool) if question_type == "word_assembly" and phrase_pool else pool[0])
    if question_type == "word_assembly" and len(split_phrase(answer["term_or_phrase"])) >= 2:
        correct_words = split_phrase(answer["term_or_phrase"])
        option_count = max(4, len(correct_words))
        correct_word_keys = {word.casefold() for word in correct_words}
        distractor_words: list[str] = []
        for item in pool:
            if item["term_id"] == answer["term_id"]:
                continue
            for word in split_phrase(item["term_or_phrase"]):
                if word.casefold() not in correct_word_keys:
                    distractor_words.append(word)
        unique_distractors = list(dict.fromkeys(distractor_words))
        options = correct_words + random.sample(unique_distractors, k=min(option_count - len(correct_words), len(unique_distractors)))
        random.shuffle(options)
        prompt = answer["chinese"]
        correct_answer = " ".join(correct_words)
    else:
        if question_type == "word_assembly":
            question_type = random.choice(["en_to_cn", "cn_to_en"])
        option_field = "chinese" if question_type == "en_to_cn" else "term_or_phrase"
        prompt_field = "term_or_phrase" if question_type == "en_to_cn" else "chinese"
        distractors = [item[option_field] for item in pool[1:] if item[option_field] != answer[option_field]]
        options = random.sample(distractors, k=min(3, len(distractors))) + [answer[option_field]]
        random.shuffle(options)
        prompt = answer[prompt_field]
        correct_answer = answer[option_field]
    return {
        "term_id": answer["term_id"],
        "question_type": question_type,
        "prompt": prompt,
        "correct_answer": correct_answer,
        "options": options,
        "category": answer["category"],
        "definition_en": answer["definition_en"],
        "definition_cn": answer["definition_cn"],
        "common_abbreviation": answer["common_abbreviation"],
        "term_or_phrase": answer["term_or_phrase"],
        "chinese": answer["chinese"],
        "review_status": answer["review_status"],
        "standard_classification": answer["standard_classification"],
        "business_domain": answer["business_domain"],
        "knowledge_source": answer["knowledge_source"],
        "term_frequency_level": answer["term_frequency_level"],
        "scenario": answer["scenario"],
        "business_scenario": answer["business_scenario"],
        "example_sentence": answer["example_sentence"],
        "translation": answer["translation"],
        "source_file": answer["source_file"],
        "source_section": answer["source_section"],
        "quality_status": answer["quality_status"],
    }
