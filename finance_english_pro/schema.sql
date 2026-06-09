CREATE TABLE IF NOT EXISTS terms (
    term_id INTEGER PRIMARY KEY AUTOINCREMENT,
    content_key TEXT,
    term_or_phrase TEXT NOT NULL,
    common_abbreviation TEXT,
    type TEXT,
    chinese TEXT NOT NULL,
    category TEXT,
    scenario TEXT,
    definition_en TEXT,
    definition_cn TEXT,
    difficulty TEXT,
    standard_classification TEXT,
    business_domain TEXT,
    term_frequency_level TEXT,
    business_scenario TEXT,
    knowledge_source TEXT,
    source_section TEXT,
    review_status TEXT NOT NULL DEFAULT 'needs_review',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS examples (
    example_id INTEGER PRIMARY KEY AUTOINCREMENT,
    term_id INTEGER NOT NULL REFERENCES terms(term_id) ON DELETE CASCADE,
    example_sentence TEXT,
    translation TEXT,
    source_section TEXT,
    source_type TEXT,
    source_file TEXT,
    source_line INTEGER,
    quality_status TEXT NOT NULL DEFAULT 'needs_review'
);

CREATE TABLE IF NOT EXISTS themes (
    theme_id INTEGER PRIMARY KEY AUTOINCREMENT,
    theme_name TEXT NOT NULL UNIQUE,
    theme_type TEXT NOT NULL DEFAULT 'category',
    display_name_cn TEXT NOT NULL,
    display_name_en TEXT,
    min_ready_terms INTEGER NOT NULL DEFAULT 20,
    is_visible INTEGER NOT NULL DEFAULT 1,
    sort_order INTEGER NOT NULL DEFAULT 100
);

CREATE TABLE IF NOT EXISTS term_theme_map (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    term_id INTEGER NOT NULL REFERENCES terms(term_id) ON DELETE CASCADE,
    theme_id INTEGER NOT NULL REFERENCES themes(theme_id) ON DELETE CASCADE,
    UNIQUE(term_id, theme_id)
);

CREATE TABLE IF NOT EXISTS content_reviews (
    review_id INTEGER PRIMARY KEY AUTOINCREMENT,
    content_type TEXT NOT NULL,
    content_id INTEGER NOT NULL,
    review_status TEXT NOT NULL,
    review_notes TEXT,
    reviewer TEXT,
    reviewed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS local_users (
    local_user_id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_active_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS user_progress (
    progress_id INTEGER PRIMARY KEY AUTOINCREMENT,
    local_user_id INTEGER NOT NULL REFERENCES local_users(local_user_id) ON DELETE CASCADE,
    term_id INTEGER NOT NULL REFERENCES terms(term_id) ON DELETE CASCADE,
    status TEXT NOT NULL DEFAULT 'new',
    is_favorite INTEGER NOT NULL DEFAULT 0,
    last_review_date TEXT,
    next_review_date TEXT,
    correct_count INTEGER NOT NULL DEFAULT 0,
    wrong_count INTEGER NOT NULL DEFAULT 0,
    review_stage INTEGER NOT NULL DEFAULT 0,
    next_attempt_number INTEGER,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(local_user_id, term_id)
);

CREATE TABLE IF NOT EXISTS attempt_logs (
    attempt_id INTEGER PRIMARY KEY AUTOINCREMENT,
    local_user_id INTEGER NOT NULL REFERENCES local_users(local_user_id) ON DELETE CASCADE,
    term_id INTEGER NOT NULL REFERENCES terms(term_id) ON DELETE CASCADE,
    question_type TEXT NOT NULL,
    selected_answer TEXT NOT NULL,
    correct_answer TEXT NOT NULL,
    is_correct INTEGER NOT NULL,
    answered_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS source_documents (
    source_id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_file TEXT NOT NULL UNIQUE,
    source_type TEXT,
    source_title TEXT,
    source_year TEXT,
    source_owner TEXT,
    notes TEXT
);

CREATE INDEX IF NOT EXISTS idx_terms_review ON terms(review_status);
CREATE INDEX IF NOT EXISTS idx_terms_search ON terms(term_or_phrase, chinese, standard_classification, business_domain);
CREATE INDEX IF NOT EXISTS idx_examples_term ON examples(term_id);
CREATE INDEX IF NOT EXISTS idx_attempt_logs_user_date ON attempt_logs(local_user_id, answered_at);
CREATE INDEX IF NOT EXISTS idx_user_progress_user ON user_progress(local_user_id, status, is_favorite, next_review_date);
