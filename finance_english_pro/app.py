from __future__ import annotations

import hmac
import os
import sys
from pathlib import Path

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

APP_DIR = Path(__file__).resolve().parent
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from scripts.init_db import upsert_terms
from services.admin_service import find_missing_sources, get_quality_summary, update_review_status
from services.content_service import (
    ensure_database,
    get_filter_values,
    get_home_stats,
    get_ready_terms_by_theme,
    get_term_detail,
    get_theme,
    list_themes,
    search_terms,
)
from services.learning_service import create_question
from services.progress_service import get_due_reviews, get_local_user_id, get_progress, record_attempt, upsert_progress
from services.report_service import get_report


DEVICE_QUERY_PARAM = "fep_device_id"


def get_query_param(name: str) -> str:
    value = st.query_params.get(name, "")
    if isinstance(value, list):
        return str(value[0]) if value else ""
    return str(value)


def ensure_device_id() -> str:
    device_id = get_query_param(DEVICE_QUERY_PARAM).strip()
    if device_id:
        return device_id

    components.html(
        f"""
        <script>
        const storageKey = "finance_english_pro_device_id";
        const params = new URLSearchParams(window.parent.location.search);
        let deviceId = window.parent.localStorage.getItem(storageKey);
        if (!deviceId) {{
            if (window.parent.crypto && window.parent.crypto.randomUUID) {{
                deviceId = window.parent.crypto.randomUUID();
            }} else {{
                deviceId = Date.now().toString(36) + "-" + Math.random().toString(36).slice(2);
            }}
            window.parent.localStorage.setItem(storageKey, deviceId);
        }}
        params.set("{DEVICE_QUERY_PARAM}", deviceId);
        const newUrl = window.parent.location.pathname + "?" + params.toString() + window.parent.location.hash;
        window.parent.location.replace(newUrl);
        </script>
        """,
        height=0,
    )
    st.info("正在初始化本机学习记录，请稍候刷新。")
    st.stop()


st.set_page_config(page_title="Finance English Pro", page_icon="FEP", layout="wide")
ensure_database()
USER_ID = get_local_user_id(ensure_device_id())


LIBRARY_SOURCE_MARKERS = ("term library", "术语库", ".xlsx", "rag_terms")
DEFINITION_AREA_CN = {
    "Accounting changes": "会计政策、会计估计变更和差错更正",
    "Borrowing costs": "借款费用",
    "Cash flow": "现金流量",
    "Classification": "分类",
    "Consolidation": "合并财务报表",
    "Current assets": "流动资产",
    "Current liabilities": "流动负债",
    "Financial Instruments": "金融工具",
    "Impairment": "减值",
    "Insurance Contracts": "保险合同",
    "Inventories": "存货",
    "Joint Arrangements": "合营安排",
    "Measurement": "计量",
    "Presentation and Disclosure in Financial Statements": "财务报表列报和披露",
    "Revenue": "收入",
}
UPLOAD_DIR = Path(__file__).resolve().parent / "data" / "uploads"
REQUIRED_UPLOAD_COLUMNS = {
    "term_or_phrase",
    "chinese",
    "definition_en",
    "definition_cn",
    "example_sentence",
    "translation",
    "source_section",
    "knowledge_source",
    "standard_classification",
    "business_domain",
    "term_frequency_level",
    "business_scenario",
}
QUESTION_TYPE_TARGETS = {
    "word_assembly": 0.40,
    "cn_to_en": 0.40,
    "en_to_cn": 0.20,
}
QUESTION_TYPE_ORDER = ("word_assembly", "cn_to_en", "en_to_cn")


def go(page: str, **params) -> None:
    st.session_state.page = page
    st.session_state.params = params
    st.rerun()


def init_nav() -> None:
    st.session_state.setdefault("page", "home")
    st.session_state.setdefault("params", {})


def clear_learning_state() -> None:
    for key in ("question", "question_history", "answer_result", "word_answer_ids", "word_question_key", "question_type_counts"):
        st.session_state.pop(key, None)


def admin_password() -> str:
    return os.environ.get("ADMIN_PASSWORD", "") or os.environ.get("FINANCE_ENGLISH_PRO_ADMIN_PASSWORD", "")


def require_admin() -> bool:
    if st.session_state.get("admin_authenticated"):
        return True

    st.subheader("管理员登录")
    configured_password = admin_password()
    if not configured_password:
        st.warning("后台更新未启用。请在 Streamlit Secrets 中配置 ADMIN_PASSWORD。")
        return False

    with st.form("admin_login"):
        password = st.text_input("管理员密码", type="password")
        submitted = st.form_submit_button("登录")
    if submitted:
        if hmac.compare_digest(password, configured_password):
            st.session_state.admin_authenticated = True
            st.rerun()
        else:
            st.error("密码不正确。")
    return False


def header() -> None:
    st.markdown(
        """
        <style>
        .block-container { padding-top: 3.2rem; }
        div[data-testid="stMetric"] { background: white; border: 1px solid #e2e8f0; border-radius: 8px; padding: 12px; }
        .term-card { background: white; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px; margin-bottom: 10px; }
        .muted { color: #64748b; font-size: 0.92rem; }
        .tag-row { display: flex; flex-wrap: wrap; gap: 6px; margin: 8px 0 14px; }
        .tag {
            display: inline-flex;
            align-items: center;
            border: 1px solid #cbd5e1;
            border-radius: 999px;
            padding: 4px 9px;
            background: #f8fafc;
            color: #334155;
            font-size: 0.82rem;
            line-height: 1.2;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    page = st.session_state.get("page", "home")
    if page != "home":
        if st.button("返回首页"):
            go("home")
        return

    cols = st.columns([3, 1, 1, 1, 1, 1])
    with cols[0]:
        st.title("Finance English Pro")
    nav = [("首页", "home"), ("搜索", "search"), ("学习", "learn"), ("复习", "review"), ("报告", "report")]
    for col, (label, page) in zip(cols[1:], nav):
        with col:
            if st.button(label, width="stretch"):
                go(page)


def render_term_actions(term_id: int) -> None:
    progress = get_progress(USER_ID, term_id)
    fav = bool(progress.get("is_favorite"))
    cols = st.columns([1, 1, 1, 1])
    with cols[0]:
        if st.button("收藏" if not fav else "取消收藏", key=f"fav_{term_id}", width="stretch"):
            upsert_progress(USER_ID, term_id, is_favorite=not fav)
            st.rerun()
    for status, label, col in [("learning", "学习中", cols[1]), ("unfamiliar", "不熟悉", cols[2]), ("mastered", "已掌握", cols[3])]:
        with col:
            if st.button(label, key=f"{status}_{term_id}", width="stretch"):
                upsert_progress(USER_ID, term_id, status=status)
                st.rerun()


def clean_source_parts(*values: str | None) -> list[str]:
    parts: list[str] = []
    for value in values:
        if not value:
            continue
        for part in str(value).replace("；", ";").split(";"):
            text = part.strip()
            if not text:
                continue
            lowered = text.lower()
            if any(marker in lowered for marker in LIBRARY_SOURCE_MARKERS):
                continue
            parts.append(text)
    return parts


def display_source_label(*values: str | None) -> str:
    parts = clean_source_parts(*values)
    return " · ".join(parts)


def definition_cn(definition_en: str | None, category: str | None = None) -> str:
    if not definition_en:
        return "暂无中文解释"
    prefix = "A financial reporting term used in "
    if definition_en.startswith(prefix) and definition_en.endswith("."):
        area = definition_en.removeprefix(prefix).removesuffix(".")
        area_cn = DEFINITION_AREA_CN.get(area, category or area)
        return f"用于{area_cn}相关场景的财务报告术语。"
    if definition_en.startswith("Risks that financial statements are materially misstated."):
        return "财务报表存在重大错报的风险。"
    if definition_en.startswith("Cash and short-term highly liquid investments."):
        return "现金以及短期、高流动性的投资。"
    if definition_en.startswith("Equity in a subsidiary not attributable to the parent."):
        return "子公司中不归属于母公司的权益。"
    return "中文解释待补充。"


def term_caption(term: dict) -> str:
    parts = [term.get("chinese", ""), term.get("review_status", ""), term.get("category", "")]
    if term.get("common_abbreviation"):
        parts.append(f"简称：{term['common_abbreviation']}")
    return " · ".join(part for part in parts if part)


def render_tags(term: dict) -> None:
    tags = [
        ("准则", term.get("standard_classification")),
        ("领域", term.get("business_domain")),
        ("频率", term.get("term_frequency_level")),
        ("业务场景", term.get("business_scenario")),
    ]
    chips = []
    for label, value in tags:
        if value:
            chips.append(f'<span class="tag">{label}: {value}</span>')
    if chips:
        st.markdown(f'<div class="tag-row">{"".join(chips)}</div>', unsafe_allow_html=True)


def render_abbreviation(common_abbreviation: str | None) -> None:
    if common_abbreviation:
        st.write("**常用简写**")
        st.write(common_abbreviation)


def render_definition_block(definition_en: str | None, definition_cn_value: str | None = None, category: str | None = None) -> None:
    st.write("**英文解释**")
    st.write(definition_en or "暂无")
    st.write("**中文解释**")
    st.write(definition_cn_value or definition_cn(definition_en, category))


def render_example_text(example_sentence: str | None, translation: str | None) -> None:
    st.write("**英文例句**")
    st.write(example_sentence or "暂无例句")
    st.write("**例句中文翻译**")
    st.write(translation or "暂无翻译")


def render_example_block(example: dict) -> None:
    with st.container(border=True):
        render_example_text(example.get("example_sentence"), example.get("translation"))
        source_label = display_source_label(example.get("source_file"), example.get("source_section"))
        quality = example.get("quality_status") or example.get("review_status") or ""
        if source_label or quality:
            source_text = f"来源：{source_label}" if source_label else "来源待结构化"
            st.caption(source_text + (f" · {quality}" if quality else ""))


def normalize_answer_text(value: str | None) -> str:
    return " ".join(str(value or "").split()).casefold()


def term_summary_card(term: dict, suffix: str = "") -> None:
    with st.container(border=True):
        cols = st.columns([3, 1, 1])
        with cols[0]:
            st.subheader(term["term_or_phrase"])
            st.caption(term_caption(term))
        with cols[1]:
            st.write(term.get("standard_classification") or "未分类")
        with cols[2]:
            if st.button("打开卡片", key=f"open_{term['term_id']}_{suffix}", width="stretch"):
                go("term", term_id=term["term_id"])
        example = term.get("example_sentence")
        if example:
            st.write("**英文例句**")
            st.write(example)
            st.caption(f"例句中文翻译：{term.get('translation') or '暂无翻译'}")


def home_page() -> None:
    stats = get_home_stats()
    st.caption("可追溯术语卡片 + 简单测验 + 收藏复习，面向审计与财务报告阅读场景。")
    cols = st.columns(4)
    cols[0].metric("术语总数", stats["total_terms"] or 0)
    cols[1].metric("Ready 内容", stats["ready_terms"] or 0)
    cols[2].metric("可见主题", stats["visible_themes"] or 0)
    cols[3].metric("待复核", stats["needs_review_terms"] or 0)

    keyword = st.text_input("搜索英文、中文、准则或领域", placeholder="performance obligation / 合同资产 / IFRS 15 / Audit")
    if keyword:
        go("search", keyword=keyword)

    st.subheader("主题入口")
    themes = list_themes()
    if not themes:
        st.info("暂无满足 20 条 ready 内容的可见主题。")
    for row in themes:
        cols = st.columns([3, 1, 1])
        cols[0].write(f"**{row['display_name_cn']}**")
        cols[1].write(f"{row['ready_count']} ready")
        if cols[2].button("开始", key=f"theme_{row['theme_id']}", width="stretch"):
            go("theme", theme_id=row["theme_id"])


def theme_page() -> None:
    theme_id = int(st.session_state.params["theme_id"])
    theme = get_theme(theme_id)
    if not theme:
        st.error("主题不存在")
        return
    st.subheader(theme["display_name_cn"])
    terms = get_ready_terms_by_theme(theme_id)
    st.caption(f"{len(terms)} 条 ready 术语")
    if st.button("从本主题开始测验"):
        go("learn", theme_id=theme_id)
    for term in terms:
        term_summary_card(term, suffix=f"theme_{theme_id}")


def search_page() -> None:
    params = st.session_state.params
    st.subheader("搜索")
    with st.form("search_form"):
        keyword = st.text_input("关键词", value=params.get("keyword", ""))
        cols = st.columns(4)
        standard = cols[0].selectbox("准则", [""] + get_filter_values("standard_classification"))
        domain = cols[1].selectbox("领域", [""] + get_filter_values("business_domain"))
        difficulty = cols[2].selectbox("难度", [""] + get_filter_values("difficulty"))
        status = cols[3].selectbox("状态", ["", "ready", "search_only", "needs_review", "rejected"])
        submitted = st.form_submit_button("搜索")
    if submitted or keyword or any([standard, domain, difficulty, status]):
        results = search_terms(keyword, standard, domain, difficulty, status)
        st.caption(f"找到 {len(results)} 条结果")
        for term in results:
            term_summary_card(term, suffix="search")


def term_page() -> None:
    term = get_term_detail(int(st.session_state.params["term_id"]))
    if not term:
        st.error("术语不存在")
        return
    st.subheader(term["term_or_phrase"])
    st.caption(term_caption(term))
    render_tags(term)
    render_term_actions(term["term_id"])
    render_abbreviation(term.get("common_abbreviation"))
    render_definition_block(term.get("definition_en"), term.get("definition_cn"), term.get("category"))
    if term["examples"]:
        render_example_text(term["examples"][0].get("example_sentence"), term["examples"][0].get("translation"))
    cols = st.columns(2)
    with cols[0]:
        st.write("**准则 / 领域**")
        st.write(f"{term.get('standard_classification') or '未分类'} / {term.get('business_domain') or '未分类'}")
    with cols[1]:
        st.write("**场景**")
        st.write(term.get("scenario") or term.get("business_scenario") or "暂无")
        source_label = display_source_label(term.get("knowledge_source"), term.get("source_section"))
        if source_label:
            st.write("**来源**")
            st.write(source_label)


def render_answer_detail(question: dict) -> None:
    with st.container(border=True):
        st.subheader(question["term_or_phrase"])
        st.caption(term_caption(question))
        render_tags(question)
        render_abbreviation(question.get("common_abbreviation"))
        render_definition_block(question.get("definition_en"), question.get("definition_cn"), question.get("category"))
        render_example_text(question.get("example_sentence"), question.get("translation"))
        cols = st.columns(2)
        with cols[0]:
            st.write("**准则 / 领域**")
            st.write(f"{question.get('standard_classification') or '未分类'} / {question.get('business_domain') or '未分类'}")
        with cols[1]:
            st.write("**场景**")
            st.write(question.get("scenario") or question.get("business_scenario") or "暂无")


def hydrate_question(question: dict) -> dict:
    if question.get("definition_cn") and question.get("term_frequency_level"):
        return question
    detail = get_term_detail(int(question["term_id"]))
    if not detail:
        return question
    example = detail["examples"][0] if detail.get("examples") else {}
    hydrated = dict(question)
    for key in (
        "definition_cn",
        "common_abbreviation",
        "review_status",
        "standard_classification",
        "business_domain",
        "knowledge_source",
        "term_frequency_level",
        "scenario",
        "business_scenario",
    ):
        hydrated[key] = detail.get(key)
    hydrated["example_sentence"] = example.get("example_sentence")
    hydrated["translation"] = example.get("translation")
    hydrated["source_file"] = example.get("source_file")
    hydrated["source_section"] = example.get("source_section")
    hydrated["quality_status"] = example.get("quality_status")
    return hydrated


def question_key(question: dict) -> str:
    return f"{question.get('term_id')}::{question.get('question_type')}::{question.get('correct_answer')}"


def choose_question_type() -> str:
    counts = st.session_state.setdefault("question_type_counts", {kind: 0 for kind in QUESTION_TYPE_ORDER})
    total = sum(int(counts.get(kind, 0)) for kind in QUESTION_TYPE_ORDER)
    if total == 0:
        return "word_assembly"
    return min(
        QUESTION_TYPE_ORDER,
        key=lambda kind: (int(counts.get(kind, 0)) / QUESTION_TYPE_TARGETS[kind], QUESTION_TYPE_ORDER.index(kind)),
    )


def next_question(theme_id: int | None = None) -> dict | None:
    preferred_type = choose_question_type()
    question = create_question(theme_id, preferred_type=preferred_type)
    if question:
        counts = st.session_state.setdefault("question_type_counts", {kind: 0 for kind in QUESTION_TYPE_ORDER})
        counts[question["question_type"]] = int(counts.get(question["question_type"], 0)) + 1
    return question


def selected_word_answer(question: dict) -> str:
    selected_ids = st.session_state.setdefault("word_answer_ids", [])
    words = []
    for option_id in selected_ids:
        if 0 <= option_id < len(question["options"]):
            words.append(question["options"][option_id])
    return " ".join(words)


def render_word_assembly(question: dict) -> str:
    current_key = question_key(question)
    if st.session_state.get("word_question_key") != current_key:
        st.session_state.word_question_key = current_key
        st.session_state.word_answer_ids = list(question.get("_word_answer_ids") or [])

    answer_text = selected_word_answer(question)
    st.write("**拼接答案**")
    st.code(answer_text or "请按顺序选择下方单词")

    columns = st.columns(4)
    selected_ids = st.session_state.setdefault("word_answer_ids", [])
    disabled = st.session_state.answer_result is not None
    for index, word in enumerate(question["options"]):
        with columns[index % 4]:
            if st.button(word, key=f"word_{current_key}_{index}", disabled=disabled or index in selected_ids, width="stretch"):
                st.session_state.word_answer_ids.append(index)
                st.rerun()

    action_cols = st.columns([1, 5])
    with action_cols[0]:
        if st.button("清空", disabled=disabled or not selected_ids):
            st.session_state.word_answer_ids = []
            st.rerun()
    return selected_word_answer(question)


def go_previous_question() -> None:
    st.session_state.question = st.session_state.question_history.pop()
    st.session_state.answer_result = st.session_state.question.get("_answer_result")
    st.session_state.word_answer_ids = list(st.session_state.question.get("_word_answer_ids") or [])
    st.session_state.word_question_key = question_key(st.session_state.question)
    st.rerun()


def go_next_question(theme_id: int | None = None) -> None:
    if st.session_state.get("question"):
        current = dict(st.session_state.question)
        current["_answer_result"] = st.session_state.get("answer_result")
        current["_word_answer_ids"] = list(st.session_state.get("word_answer_ids", []))
        st.session_state.question_history.append(current)
    st.session_state.question = next_question(theme_id)
    st.session_state.answer_result = None
    st.session_state.word_answer_ids = []
    st.session_state.word_question_key = question_key(st.session_state.question) if st.session_state.question else None
    st.rerun()


def render_learning_footer(theme_id: int | None = None) -> None:
    st.divider()
    nav_cols = st.columns(3)
    if nav_cols[0].button("上一题", disabled=not st.session_state.question_history, width="stretch"):
        go_previous_question()
    if nav_cols[1].button("返回首页", width="stretch"):
        go("home")
    if nav_cols[2].button("下一题", width="stretch"):
        go_next_question(theme_id)


def learn_page() -> None:
    theme_id = st.session_state.params.get("theme_id")
    st.subheader("测验")
    st.session_state.setdefault("question_history", [])
    st.session_state.setdefault("answer_result", None)
    if "question" not in st.session_state or st.session_state.question is None:
        st.session_state.question = next_question(theme_id)
        st.session_state.answer_result = None
        st.session_state.word_answer_ids = []
        st.session_state.word_question_key = question_key(st.session_state.question) if st.session_state.question else None
    question = st.session_state.question
    if not question:
        st.info("ready 内容不足，暂时无法出题。")
        return
    question = hydrate_question(question)
    st.session_state.question = question
    label_map = {
        "en_to_cn": "选择中文含义",
        "cn_to_en": "选择英文术语",
        "word_assembly": "按中文拼接英文词组",
    }
    label = label_map.get(question["question_type"], "测验")
    st.caption(f"{label} · {question['category']}")
    st.header(question["prompt"])
    if question["question_type"] == "word_assembly":
        selected = render_word_assembly(question)
        disabled = not selected or st.session_state.answer_result is not None
    else:
        selected = st.radio("选项", question["options"], index=None)
        disabled = selected is None or st.session_state.answer_result is not None
    if st.button("提交答案", disabled=disabled):
        is_correct = normalize_answer_text(selected) == normalize_answer_text(question["correct_answer"])
        record_attempt(USER_ID, question["term_id"], question["question_type"], selected, question["correct_answer"], is_correct)
        st.session_state.answer_result = {
            "selected": selected,
            "correct_answer": question["correct_answer"],
            "is_correct": is_correct,
        }
        st.rerun()

    result = st.session_state.answer_result
    if result:
        if result["is_correct"]:
            st.success("回答正确")
        else:
            st.error(f"回答错误，正确答案：{result['correct_answer']}")
        st.caption(f"本次选择：{result['selected']}")
        render_answer_detail(question)
    render_learning_footer(theme_id)


def review_page() -> None:
    st.subheader("复习")
    mode = st.segmented_control("范围", ["due", "unfamiliar", "favorites"], default="due", format_func={"due": "到期", "unfamiliar": "不熟悉", "favorites": "收藏"}.get)
    terms = get_due_reviews(USER_ID, mode)
    if not terms:
        st.info("当前没有需要复习的术语。")
        return
    for term in terms:
        term_summary_card(term, suffix=f"review_{mode}")


def report_page() -> None:
    st.subheader("学习报告")
    report = get_report(USER_ID)
    cols = st.columns(4)
    cols[0].metric("今日答题", report["today_attempts"])
    cols[1].metric("今日正确率", f"{report['today_accuracy']}%")
    cols[2].metric("累计答题", report["total_attempts"])
    cols[3].metric("累计正确率", f"{report['accuracy']}%")
    cols = st.columns(4)
    cols[0].metric("跟踪术语", report["tracked_terms"])
    cols[1].metric("收藏", report["favorites"])
    cols[2].metric("不熟悉", report["unfamiliar"])
    cols[3].metric("已掌握", report["mastered"])


def admin_page() -> None:
    if not require_admin():
        return

    st.subheader("内容质检")
    if st.session_state.get("import_result"):
        result = st.session_state.pop("import_result")
        st.success(
            f"数据库已更新：{result['terms']} 条术语，{result['examples']} 条例句，"
            f"{result['ready']} 条 ready。"
        )
        cols = st.columns(4)
        cols[0].metric("新增", result.get("inserted", 0))
        cols[1].metric("更新/保留状态", result.get("updated", 0))
        cols[2].metric("删除", result.get("deleted", 0))
        cols[3].metric("保留学习状态", result.get("preserved", 0))
        st.caption(f"数据源：{result['source']}")

    st.write("上传数据源 CSV")
    st.info("上传后会按术语合并更新内容；未删除术语会保留学习记录、答题记录和收藏状态，只有被删除术语的对应状态会清理。")
    uploaded = st.file_uploader("选择 CSV 文件更新系统数据库", type=["csv"])
    if uploaded is not None:
        preview = pd.read_csv(uploaded, nrows=5)
        uploaded.seek(0)
        missing = sorted(REQUIRED_UPLOAD_COLUMNS - set(preview.columns))
        st.caption(f"检测到 {len(preview.columns)} 个字段")
        st.dataframe(preview, width="stretch")
        if missing:
            st.error("缺少必要字段：" + "、".join(missing))
        else:
            if st.button("用该 CSV 重建数据库", type="primary"):
                UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
                upload_path = UPLOAD_DIR / "uploaded_source.csv"
                upload_path.write_bytes(uploaded.getvalue())
                result = upsert_terms(upload_path)
                clear_learning_state()
                st.session_state.import_result = result
                st.rerun()

    st.divider()
    st.write("状态分布")
    st.dataframe(get_quality_summary(), width="stretch")
    st.write("来源缺失")
    st.dataframe(find_missing_sources(), width="stretch")
    with st.form("review_update"):
        term_id = st.number_input("Term ID", min_value=1, step=1)
        status = st.selectbox("新状态", ["ready", "needs_review", "search_only", "rejected"])
        notes = st.text_input("备注")
        if st.form_submit_button("更新状态"):
            update_review_status(int(term_id), status, notes)
            st.success("已更新")


init_nav()
header()

page = st.session_state.page
if page == "home":
    home_page()
elif page == "theme":
    theme_page()
elif page == "search":
    search_page()
elif page == "term":
    term_page()
elif page == "learn":
    learn_page()
elif page == "review":
    review_page()
elif page == "report":
    report_page()
elif page == "admin":
    admin_page()

with st.sidebar:
    st.write("内部工具")
    if st.session_state.get("admin_authenticated"):
        if st.button("内容质检"):
            go("admin")
        if st.button("退出后台"):
            st.session_state.admin_authenticated = False
            go("home")
    else:
        if st.button("管理员登录"):
            go("admin")
    st.caption("V1.3 MVP：本地单设备统计，不做登录和多端同步。")
