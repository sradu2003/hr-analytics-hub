# HR Analytics Dashboard

A decision-first HR Analytics Streamlit dashboard covering Workforce Stability, Capacity Planning, Availability, and Talent Flow with predictive ML-based risk scoring, real data loading, filtered exports, and a full Settings layer.

## Run & Operate

- `cd artifacts/hr-dashboard && streamlit run app.py --server.port 5000` — run the dashboard
- Python 3.11 + pip packages managed via Replit module system
- Required env: none (uses real CSVs from `data/raw/` when present; falls back to synthetic)
- Config persisted in `artifacts/hr-dashboard/dashboard_config.json` (auto-created on first save)

## Stack

- Python 3.11, Streamlit 1.41, Pandas, NumPy, Plotly, scikit-learn
- pnpm workspaces, Node.js 24, TypeScript 5.9 (monorepo shell)
- API: Express 5 (pre-existing api-server artifact, port 8080)

## Where things live

- `artifacts/hr-dashboard/app.py` — main Streamlit app (7 analytics tabs + Settings tab)
- `artifacts/hr-dashboard/data.py` — synthetic generation + `enrich_employees()` + `generate_sample_csvs()`
- `artifacts/hr-dashboard/data_loader.py` — all file I/O: load/save raw, export filtered, list files
- `artifacts/hr-dashboard/config.py` — JSON config load/save/merge + DEFAULT_CONFIG
- `artifacts/hr-dashboard/data/raw/` — real input CSVs (employees, absences, recruitment, vacancies, attrition_history, capacity_plan)
- `artifacts/hr-dashboard/data/processed/` — timestamped filtered exports with filter metadata header
- `artifacts/hr-dashboard/dashboard_config.json` — runtime config (git-ignored)
- `artifacts/hr-dashboard/.streamlit/config.toml` — server config (port 5000)
- `lib/api-spec/openapi.yaml` — OpenAPI spec (api-server)

## Architecture decisions

- Data loading priority: `data/raw/<name>.csv` → synthetic fallback; `load_raw()` validates required columns before accepting
- `enrich_employees()` adds derived columns (risk scores, tenure, labels) to real employee DataFrames that are missing them
- `generate_sample_csvs()` writes all 6 synthetic CSVs to `data/raw/` so users have realistic templates to replace
- All filtered exports written to `data/processed/` with filter metadata comment header (`# Filter dept: ...`)
- `st.cache_data` keyed on `refresh_key` counter; incrementing it forces a full reload from disk
- Temporal filters (hire date range + reporting period) applied before passing DataFrames to any tab

## Product

- **Executive Overview (A):** KPI tiles, RAG by department, Workforce Health Radar
- **Attrition Risk (B):** Risk distribution, historical vs predicted trend, driver charts, top-20 high-risk
- **Capacity Planning (C):** N-month demand vs supply forecast, FTE gap by role, scenario simulator
- **Availability (D):** Absence risk heatmap (dept × week), seasonal forecast with alert threshold
- **Talent Flow (E):** Recruitment funnel (real or synthetic), time-to-hire trend, vacancy aging table
- **Actions (F):** Model-driven recommended actions, priority list, status tracking
- **Drill-Down (G):** Department, individual employee, and time comparison views
- **Settings (⚙️):** Upload CSVs per source, generate sample CSVs, view/download raw & processed files, parameters, KPI visibility, tab structure, employee exclusions, config JSON load/save/download/upload

## User preferences

- Decision-first layout: Top = decisions, Middle = diagnostics, Bottom = actions
- Brand colors: Blue #003F87, Orange #F07D00
- No emojis in charts; traffic-light RAG indicators for status
- Aligned to 4 core HR domains: Stability, Capacity, Availability, Talent Flow

## Gotchas

- Streamlit runs at port 5000 via the "HR Analytics Dashboard" workflow
- Restart workflow after any `.py` file changes
- `st.cache_data.clear()` + `refresh_key += 1` forces disk reload without page reload artifacts
- `data/raw/` and `data/processed/` must exist; `ensure_dirs()` creates them on first import
- `generate_sample_csvs()` writes to `data/raw/` — calling it again overwrites existing files

## Pointers

- See the `streamlit` skill for server config rules
- See the `pnpm-workspace` skill for workspace structure
