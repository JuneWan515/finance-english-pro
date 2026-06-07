from __future__ import annotations

import random

from db import get_connection, rows_to_dicts


def get_question_pool(theme_id: int | None = None, limit: int = 80) -> list[dict]:
    conn = get_connection()
    if theme_id:
        rows = conn.execute(
            """
            SELECT
                t.term_id, t.term_or_phrase, t.chinese, t.category, t.definition_en,
                t.definition_cn, t.common_abbreviation, t.review_status, t.standard_classification, t.business_domain,
                t.knowledge_source, t.term_frequency_level, t.scenario, t.business_scenario,
                e.example_sentence, e.translation,
                e.source_file, e.source_section, e.quality_status
            FROM terms t
            LEFT JOIN examples e ON e.term_id = t.term_id
            JOIN term_theme_map map ON map.term_id = t.term_id
            WHERE t.review_status = 'ready' AND map.theme_id = ?
            ORDER BY RANDOM()
            LIMIT ?
            """,
            (theme_id, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT
                t.term_id, t.term_or_phrase, t.chinese, t.category, t.definition_en,
                t.definition_cn, t.common_abbreviation, t.review_status, t.standard_classification, t.business_domain,
                t.knowledge_source, t.term_frequency_level, t.scenario, t.business_scenario,
                e.example_sentence, e.translation,
                e.source_file, e.source_section, e.quality_status
            FROM terms t
            LEFT JOIN examples e ON e.term_id = t.term_id
            WHERE t.review_status = 'ready'
            ORDER BY RANDOM()
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    conn.close()
    return rows_to_dicts(rows)


def create_question(theme_id: int | None = None) -> dict | None:
    pool = get_question_pool(theme_id)
    if len(pool) < 4:
        return None
    answer = pool[0]
    question_type = random.choice(["en_to_cn", "cn_to_en"])
    option_field = "chinese" if question_type == "en_to_cn" else "term_or_phrase"
    prompt_field = "term_or_phrase" if question_type == "en_to_cn" else "chinese"
    distractors = [item[option_field] for item in pool[1:] if item[option_field] != answer[option_field]]
    options = random.sample(distractors, k=min(3, len(distractors))) + [answer[option_field]]
    random.shuffle(options)
    return {
        "term_id": answer["term_id"],
        "question_type": question_type,
        "prompt": answer[prompt_field],
        "correct_answer": answer[option_field],
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
