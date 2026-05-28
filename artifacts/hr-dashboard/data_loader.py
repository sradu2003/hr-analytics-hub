"""
data_loader.py
Handles all file I/O for the HR Analytics Dashboard.
  - Loads real CSV data from   data/raw/
  - Exports filtered snapshots to data/processed/
  - Falls back to synthetic generation when no real data exists
"""
import os
import io
import json
from datetime import datetime

import pandas as pd
import numpy as np

BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
RAW_DIR     = os.path.join(BASE_DIR, "data", "raw")
PROCESSED_DIR = os.path.join(BASE_DIR, "data", "processed")

# ── Schema catalogue ─────────────────────────────────────────────────────────
SOURCES = {
    "employees": {
        "label":    "Employee Master",
        "filename": "employees.csv",
        "required_cols": ["employee_id", "department", "role_type", "region"],
        "date_cols":     ["hire_date"],
        "description":   "One row per employee. Must contain employee_id, department, role_type, region, hire_date.",
    },
    "absences": {
        "label":    "Absence Records",
        "filename": "absences.csv",
        "required_cols": ["employee_id", "absence_date", "absence_days"],
        "date_cols":     ["absence_date"],
        "description":   "One row per absence event. Must contain employee_id, absence_date (YYYY-MM-DD), absence_days.",
    },
    "recruitment": {
        "label":    "Recruitment Pipeline",
        "filename": "recruitment.csv",
        "required_cols": ["requisition_id", "department", "stage", "application_date"],
        "date_cols":     ["application_date", "hire_date"],
        "description":   "One row per candidate. Must contain requisition_id, department, stage, application_date.",
    },
    "vacancies": {
        "label":    "Vacancy Aging",
        "filename": "vacancies.csv",
        "required_cols": ["vacancy_id", "department", "role_type", "days_open"],
        "date_cols":     ["open_date"],
        "description":   "One row per open vacancy. Must contain vacancy_id, department, role_type, days_open.",
    },
    "attrition_history": {
        "label":    "Attrition History",
        "filename": "attrition_history.csv",
        "required_cols": ["month", "attrition_rate"],
        "date_cols":     ["month"],
        "description":   "Monthly attrition rates. Must contain month (YYYY-MM-DD), attrition_rate (%).",
    },
    "capacity_plan": {
        "label":    "Capacity / Workforce Plan",
        "filename": "capacity_plan.csv",
        "required_cols": ["month", "demand_fte", "supply_fte"],
        "date_cols":     ["month"],
        "description":   "Monthly demand vs supply. Must contain month, demand_fte, supply_fte.",
    },
}


def ensure_dirs():
    os.makedirs(RAW_DIR, exist_ok=True)
    os.makedirs(PROCESSED_DIR, exist_ok=True)


def raw_path(name: str) -> str:
    return os.path.join(RAW_DIR, SOURCES[name]["filename"])


def has_raw(name: str) -> bool:
    ensure_dirs()
    return os.path.exists(raw_path(name))


def load_raw(name: str) -> pd.DataFrame | None:
    """Load a CSV from data/raw/. Returns None if file not found or invalid."""
    if not has_raw(name):
        return None
    try:
        date_cols = SOURCES[name].get("date_cols", [])
        df = pd.read_csv(raw_path(name), parse_dates=date_cols)
        # Validate required columns
        missing = [c for c in SOURCES[name]["required_cols"] if c not in df.columns]
        if missing:
            return None          # silently fall back to synthetic
        return df
    except Exception:
        return None


def save_raw(name: str, df: pd.DataFrame):
    """Overwrite data/raw/<name>.csv with df."""
    ensure_dirs()
    df.to_csv(raw_path(name), index=False)


def upload_and_save(name: str, uploaded_file) -> tuple:
    """Parse an uploaded Streamlit file object, validate, save to raw, return (df, message)."""
    ensure_dirs()
    try:
        content = uploaded_file.read()
        date_cols = SOURCES[name].get("date_cols", [])
        df = pd.read_csv(io.BytesIO(content), parse_dates=date_cols)
        missing = [c for c in SOURCES[name]["required_cols"] if c not in df.columns]
        if missing:
            return None, f"Missing required columns: {', '.join(missing)}"
        save_raw(name, df)
        return df, f"Saved {len(df):,} rows to data/raw/{SOURCES[name]['filename']}"
    except Exception as e:
        return None, f"Parse error: {e}"


def export_filtered(name: str, df: pd.DataFrame, applied_filters: dict) -> tuple:
    """
    Save a filtered DataFrame to data/processed/ with filter metadata header.
    Returns (filename, absolute_path, csv_bytes).
    """
    ensure_dirs()
    ts       = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{name}_{ts}.csv"
    path     = os.path.join(PROCESSED_DIR, filename)

    # Build metadata header
    meta = ["# HR Analytics — Filtered Export",
            f"# Source  : {name}",
            f"# Generated: {datetime.now().isoformat()}",
            f"# Rows    : {len(df)}"]
    for k, v in applied_filters.items():
        meta.append(f"# Filter {k}: {v}")

    csv_buf = io.StringIO()
    for line in meta:
        csv_buf.write(line + "\n")
    df.to_csv(csv_buf, index=False)
    csv_bytes = csv_buf.getvalue().encode()

    # Also persist to disk
    with open(path, "wb") as f:
        f.write(csv_bytes)

    return filename, path, csv_bytes


def list_raw_files() -> list:
    ensure_dirs()
    files = []
    for key, meta in SOURCES.items():
        fname = meta["filename"]
        fpath = os.path.join(RAW_DIR, fname)
        exists = os.path.exists(fpath)
        info   = {"key": key, "label": meta["label"], "filename": fname,
                  "exists": exists, "rows": None, "size_kb": None, "modified": None}
        if exists:
            try:
                with open(fpath) as fp:
                    rows = sum(1 for _ in fp) - 1
                info["rows"]     = rows
                info["size_kb"]  = f"{os.path.getsize(fpath)/1024:.1f}"
                info["modified"] = datetime.fromtimestamp(
                    os.path.getmtime(fpath)).strftime("%Y-%m-%d %H:%M")
            except Exception:
                pass
        files.append(info)
    return files


def list_processed_files() -> list:
    ensure_dirs()
    files = []
    for fname in sorted(os.listdir(PROCESSED_DIR), reverse=True):
        if not fname.endswith(".csv"):
            continue
        fpath = os.path.join(PROCESSED_DIR, fname)
        files.append({
            "filename": fname,
            "size_kb":  f"{os.path.getsize(fpath)/1024:.1f}",
            "modified": datetime.fromtimestamp(
                os.path.getmtime(fpath)).strftime("%Y-%m-%d %H:%M"),
            "path":     fpath,
        })
    return files


def read_processed_bytes(path: str) -> bytes:
    with open(path, "rb") as f:
        return f.read()


def apply_temporal_filter(df: pd.DataFrame, col: str,
                           start: "pd.Timestamp | None",
                           end:   "pd.Timestamp | None") -> pd.DataFrame:
    """Filter df where df[col] is between start and end (inclusive)."""
    if col not in df.columns:
        return df
    if pd.api.types.is_datetime64_any_dtype(df[col]):
        if start is not None:
            df = df[df[col] >= pd.Timestamp(start)]
        if end is not None:
            df = df[df[col] <= pd.Timestamp(end)]
    return df


def get_active_filters(sel_depts, sel_regions, sel_roles, sel_manager,
                        hire_start, hire_end, report_start, report_end) -> dict:
    """Build a human-readable filter dict for export metadata."""
    return {
        "departments":    ", ".join(sel_depts)  if sel_depts  else "All",
        "regions":        ", ".join(sel_regions) if sel_regions else "All",
        "roles":          ", ".join(sel_roles)   if sel_roles   else "All",
        "manager":        sel_manager,
        "hire_date_from": str(hire_start) if hire_start else "—",
        "hire_date_to":   str(hire_end)   if hire_end   else "—",
        "report_from":    str(report_start) if report_start else "—",
        "report_to":      str(report_end)   if report_end   else "—",
    }
