# Finance English Pro Streamlit MVP

基于 `PRD V1.3 Vibecoding执行版` 生成的本地 Web MVP。首版验证可追溯术语卡片、搜索、测验、收藏复习和学习报告闭环。

## 功能

- SQLite 运行时数据库，不直接把 Excel/CSV 当应用数据库。
- 从 `整理文件/finance_accounting_english_extract.xlsx` 导入术语和例句，CSV 可作为上传更新源。
- 首页主题、搜索、术语详情卡片。
- 英文选中文、中文选英文两类测验，并写入 `attempt_logs`。
- 收藏、学习中、不熟悉、已掌握状态，并写入 `user_progress`。
- 复习页按到期、不熟悉、收藏展示。
- 报告页从真实答题和进度表统计。
- 内部内容质检页支持上传 CSV 合并更新数据库、状态分布、来源缺失检查和状态更新。

## 快速开始

```bash
cd /Users/junwan/AI项目/专业英语学习/finance_english_pro
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python scripts/init_db.py
streamlit run app.py
```

应用首次启动时如果数据库不存在，会优先导入 xlsx；也可以在“内容质检”页上传 CSV 合并更新系统数据库。上传时会按 `term_or_phrase + chinese` 匹配原有术语，未删除术语会保留学习记录、答题记录和收藏状态；只有上传源中删除的术语会同步删除对应状态。

## CSV 上传字段

上传 CSV 至少需要包含以下字段：

```text
term_or_phrase, chinese, definition_en, definition_cn, example_sentence, translation,
source_section, knowledge_source, standard_classification, business_domain,
term_frequency_level, business_scenario
```

## 目录

```text
finance_english_pro/
  app.py
  db.py
  schema.sql
  scripts/init_db.py
  services/
  data/
```

## 固定验收词

建议用以下词验证搜索和学习流：

- performance obligation
- contract asset
- expected credit loss
- audit evidence
