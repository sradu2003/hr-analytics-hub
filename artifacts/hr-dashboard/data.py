"""
data.py
Synthetic data generation + KPI logic for the HR Analytics Dashboard.
All functions accept explicit `seed` and threshold parameters so they are
fully driven by the JSON config.  Call generate_sample_csvs() once to
populate data/raw/ with realistic template CSVs that users can replace.
"""
import os
import random
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

# Module-level default (overridden at runtime via config)
SEED = 42

DEPARTMENTS = [
    "Grid Operations", "Asset Management", "IT & Digital", "Finance",
    "HR", "Customer Services", "Engineering", "Safety & Compliance",
]
REGIONS    = ["Noord", "Oost", "Zuid", "West", "Centraal"]
ROLE_TYPES = ["Field Technician", "Office Specialist", "Engineer",
               "Manager", "Analyst", "Project Lead"]
MANAGERS   = [f"Manager {chr(65+i)}" for i in range(12)]


# ── Employee master ───────────────────────────────────────────────────────────

def make_employee_master(
    n: int = 620,
    seed: int = SEED,
    risk_high: float = 0.55,
    risk_med:  float = 0.30,
    abs_high:  float = 0.40,
    abs_med:   float = 0.20,
) -> pd.DataFrame:
    np.random.seed(seed)
    random.seed(seed)
    today = datetime.today()

    dept_weights = {
        "Grid Operations": 0.226, "Asset Management": 0.145,
        "IT & Digital":    0.129, "Finance":           0.089,
        "HR":              0.065, "Customer Services": 0.137,
        "Engineering":     0.145, "Safety & Compliance": 0.065,
    }
    dept_sizes = {k: max(1, int(v * n)) for k, v in dept_weights.items()}
    dept_sizes["Grid Operations"] += n - sum(dept_sizes.values())

    rows, eid = [], 1000
    for dept, size in dept_sizes.items():
        for _ in range(size):
            hire_date  = today - timedelta(days=int(np.random.randint(90, 5000)))
            tenure_yrs = (today - hire_date).days / 365
            age        = int(np.random.randint(22, 62))
            salary     = float(np.clip(np.random.normal(55000, 12000), 30000, 120000))
            sal_growth = float(np.random.normal(0.03, 0.02))
            role       = np.random.choice(ROLE_TYPES)
            region     = np.random.choice(REGIONS)
            manager    = np.random.choice(MANAGERS)

            risk = 0.0
            if tenure_yrs < 1:    risk += 0.25
            elif tenure_yrs < 2:  risk += 0.15
            if sal_growth < 0.01: risk += 0.20
            if age < 30:          risk += 0.10
            if dept in ("IT & Digital", "Customer Services"): risk += 0.12
            risk = float(np.clip(risk + np.random.normal(0, 0.08), 0.01, 0.95))

            abs_risk = float(np.clip(
                np.random.beta(2, 6) + (0.10 if dept == "Grid Operations" else 0),
                0.01, 0.90,
            ))

            rows.append({
                "employee_id":          eid,
                "department":           dept,
                "role_type":            role,
                "region":               region,
                "manager":              manager,
                "hire_date":            hire_date.strftime("%Y-%m-%d"),
                "tenure_years":         round(tenure_yrs, 1),
                "age":                  age,
                "salary":               round(salary, 0),
                "salary_growth_pct":    round(sal_growth * 100, 2),
                "attrition_risk_score": round(risk, 3),
                "attrition_risk_label": ("High"   if risk     > risk_high
                                          else "Medium" if risk     > risk_med  else "Low"),
                "absence_risk_score":   round(abs_risk, 3),
                "absence_risk_label":   ("High"   if abs_risk > abs_high
                                          else "Medium" if abs_risk > abs_med   else "Low"),
                "is_active":            bool(np.random.choice([True, False], p=[0.95, 0.05])),
                "performance_score":    int(np.random.choice(
                    [1, 2, 3, 4, 5], p=[0.05, 0.12, 0.38, 0.32, 0.13])),
            })
            eid += 1

    df = pd.DataFrame(rows)
    df["hire_date"] = pd.to_datetime(df["hire_date"])
    return df


def enrich_employees(
    df: pd.DataFrame,
    risk_high: float = 0.55,
    risk_med:  float = 0.30,
    abs_high:  float = 0.40,
    abs_med:   float = 0.20,
) -> pd.DataFrame:
    """
    Add derived columns to a real employee DataFrame if they are missing.
    Expects at minimum: employee_id, department, role_type, region, hire_date.
    """
    df = df.copy()
    today = datetime.today()

    if "hire_date" in df.columns:
        df["hire_date"] = pd.to_datetime(df["hire_date"], errors="coerce")
        df["tenure_years"] = df["hire_date"].apply(
            lambda d: round((today - d).days / 365, 1) if pd.notnull(d) else 0.0
        )

    # Synthesise risk scores when absent
    if "attrition_risk_score" not in df.columns:
        np.random.seed(SEED)
        scores = []
        for _, row in df.iterrows():
            r = 0.0
            t = row.get("tenure_years", 5)
            if t < 1:   r += 0.25
            elif t < 2: r += 0.15
            if row.get("salary_growth_pct", 3) < 1: r += 0.20
            if row.get("age", 35) < 30:              r += 0.10
            if row.get("department", "") in ("IT & Digital", "Customer Services"): r += 0.12
            r = float(np.clip(r + np.random.normal(0, 0.08), 0.01, 0.95))
            scores.append(r)
        df["attrition_risk_score"] = scores

    if "attrition_risk_label" not in df.columns:
        df["attrition_risk_label"] = df["attrition_risk_score"].apply(
            lambda x: "High" if x > risk_high else ("Medium" if x > risk_med else "Low"))

    if "absence_risk_score" not in df.columns:
        np.random.seed(SEED + 1)
        df["absence_risk_score"] = [
            float(np.clip(
                np.random.beta(2, 6) + (0.10 if r.get("department") == "Grid Operations" else 0),
                0.01, 0.90,
            ))
            for _, r in df.iterrows()
        ]

    if "absence_risk_label" not in df.columns:
        df["absence_risk_label"] = df["absence_risk_score"].apply(
            lambda x: "High" if x > abs_high else ("Medium" if x > abs_med else "Low"))

    if "is_active" not in df.columns:
        df["is_active"] = True
    if "performance_score" not in df.columns:
        np.random.seed(SEED + 2)
        df["performance_score"] = np.random.choice([1, 2, 3, 4, 5],
            size=len(df), p=[0.05, 0.12, 0.38, 0.32, 0.13])

    return df


# ── Attrition history ─────────────────────────────────────────────────────────

def make_attrition_history(seed: int = SEED) -> pd.DataFrame:
    np.random.seed(seed)
    months = pd.date_range(end=datetime.today(), periods=18, freq="ME")
    base   = [3.1, 3.3, 3.0, 3.5, 3.8, 4.1, 3.9, 4.3, 4.0,
               3.7, 3.9, 4.2, 4.4, 4.1, 4.5, 4.3, 4.7, 5.0]
    actual    = base[: len(months)]
    predicted = [r + float(np.random.uniform(-0.1, 0.4)) for r in actual]
    return pd.DataFrame({
        "month":          months,
        "attrition_rate": actual,
        "predicted_rate": predicted,
    })


def filter_attrition_history(df: pd.DataFrame,
                               report_start: "pd.Timestamp | None",
                               report_end:   "pd.Timestamp | None") -> pd.DataFrame:
    if report_start is not None:
        df = df[df["month"] >= pd.Timestamp(report_start)]
    if report_end is not None:
        df = df[df["month"] <= pd.Timestamp(report_end)]
    return df


# ── Capacity forecast ─────────────────────────────────────────────────────────

def make_capacity_forecast(months: int = 12) -> pd.DataFrame:
    month_range = pd.date_range(start=datetime.today(), periods=months, freq="ME")
    demand = [625 + i * 6 for i in range(months)]
    supply = [620 - i * 2 for i in range(months)]
    return pd.DataFrame({
        "month":      month_range,
        "demand_fte": demand,
        "supply_fte": supply,
        "gap_fte":    [d - s for d, s in zip(demand, supply)],
    })


# ── Absence heatmap ───────────────────────────────────────────────────────────

def make_absence_heatmap(employees_df: pd.DataFrame,
                          weeks: int = 12,
                          seed:  int = SEED) -> pd.DataFrame:
    np.random.seed(seed)
    week_labels = [f"W{i}" for i in range(1, weeks + 1)]
    rows = []
    for dept in DEPARTMENTS:
        subset    = employees_df[employees_df["department"] == dept]
        base_risk = subset["absence_risk_score"].mean() if len(subset) else 0.20
        for wk in week_labels:
            seasonal = 0.05 if wk in (week_labels[:2] + week_labels[-2:]) else 0
            rows.append({
                "department":      dept,
                "week":            wk,
                "absence_rate_pct": round(
                    (base_risk + seasonal + float(np.random.normal(0, 0.03))) * 100, 1),
            })
    return pd.DataFrame(rows)


# ── Recruitment funnel ────────────────────────────────────────────────────────

def make_recruitment_funnel(df: "pd.DataFrame | None" = None) -> pd.DataFrame:
    """If a real recruitment DataFrame is provided, derive funnel from it."""
    if df is not None and "stage" in df.columns:
        stage_order = ["Applications", "Screened", "Interviewed", "Offer Made", "Hired"]
        counts = []
        for s in stage_order:
            mask = df["stage"].str.strip().str.lower() == s.lower()
            counts.append(int(mask.sum()))
        # Cumulative from top of funnel
        total = df["requisition_id"].nunique() if "requisition_id" in df.columns else len(df)
        counts[0] = max(counts[0], total)
        return pd.DataFrame({"stage": stage_order, "count": counts})

    return pd.DataFrame({
        "stage": ["Applications", "Screened", "Interviewed", "Offer Made", "Hired"],
        "count": [480, 210, 95, 52, 38],
    })


# ── Time-to-hire ─────────────────────────────────────────────────────────────

def make_time_to_hire(df: "pd.DataFrame | None" = None,
                       seed: int = SEED) -> pd.DataFrame:
    """If a real recruitment DataFrame with application_date + hire_date is provided,
    compute actual TTH per month; otherwise return synthetic values."""
    if df is not None and {"application_date", "hire_date"}.issubset(df.columns):
        d = df.copy()
        d["application_date"] = pd.to_datetime(d["application_date"], errors="coerce")
        d["hire_date"]        = pd.to_datetime(d["hire_date"],        errors="coerce")
        d = d.dropna(subset=["application_date", "hire_date"])
        d["tth_days"] = (d["hire_date"] - d["application_date"]).dt.days
        d["month"]    = d["application_date"].dt.to_period("M").dt.to_timestamp()
        agg = d.groupby("month")["tth_days"].mean().reset_index()
        agg.columns = ["month", "avg_days"]
        agg["target_days"] = 40
        return agg.tail(12)

    np.random.seed(seed)
    months = pd.date_range(end=datetime.today(), periods=12, freq="ME")
    return pd.DataFrame({
        "month":       months,
        "avg_days":    [42, 45, 40, 44, 48, 52, 49, 47, 51, 53, 50, 55],
        "target_days": [40] * 12,
    })


# ── Vacancy aging ─────────────────────────────────────────────────────────────

def make_vacancy_aging(df: "pd.DataFrame | None" = None,
                        seed: int = SEED) -> pd.DataFrame:
    if df is not None and "days_open" in df.columns:
        out = df.copy()
        if "status" not in out.columns:
            out["status"] = out["days_open"].apply(
                lambda d: "Critical" if d > 90 else ("At Risk" if d > 60 else "On Track"))
        return out[["department", "role_type", "days_open", "status"]].rename(
            columns={"role_type": "role"})

    np.random.seed(seed)
    rows = []
    for dept in DEPARTMENTS:
        for _ in range(int(np.random.randint(1, 6))):
            d = int(np.random.randint(5, 120))
            rows.append({
                "department": dept,
                "role":       str(np.random.choice(ROLE_TYPES)),
                "days_open":  d,
                "status":     "Critical" if d > 90 else ("At Risk" if d > 60 else "On Track"),
            })
    return pd.DataFrame(rows)


# ── Recommended actions ───────────────────────────────────────────────────────

def make_recommended_actions(employees_df: pd.DataFrame) -> pd.DataFrame:
    np.random.seed(SEED)
    high_risk = (
        employees_df[employees_df["attrition_risk_label"] == "High"]
        .groupby("department").size().sort_values(ascending=False).head(5)
    )
    actions = []
    for dept, count in high_risk.items():
        actions.append({
            "priority":    len(actions) + 1,
            "department":  dept,
            "action_type": "Retention Intervention",
            "description": f"{count} high-risk employees — initiate 1:1 retention dialogue",
            "urgency":     "High" if count > 10 else "Medium",
            "status":      str(np.random.choice(["Open", "In Progress", "Closed"],
                                                 p=[0.5, 0.35, 0.15])),
            "owner":       str(np.random.choice(MANAGERS)),
        })

    cap = make_capacity_forecast()
    for _, row in cap[cap["gap_fte"] > 60].head(2).iterrows():
        actions.append({
            "priority":    len(actions) + 1,
            "department":  "Grid Operations",
            "action_type": "Hiring Required",
            "description": (f"Projected FTE gap of {row['gap_fte']} by "
                            f"{row['month'].strftime('%b %Y')} — start pipeline now"),
            "urgency":     "High",
            "status":      "Open",
            "owner":       str(np.random.choice(MANAGERS)),
        })

    actions.append({
        "priority":    len(actions) + 1,
        "department":  "Engineering",
        "action_type": "Workforce Redistribution",
        "description": "Winter absence peak expected — pre-allocate backup technicians",
        "urgency":     "Medium",
        "status":      "In Progress",
        "owner":       str(np.random.choice(MANAGERS)),
    })
    return pd.DataFrame(actions)


# ── KPIs ──────────────────────────────────────────────────────────────────────

def get_kpis(employees_df: pd.DataFrame) -> dict:
    active    = employees_df[employees_df["is_active"]] if "is_active" in employees_df.columns else employees_df
    total_fte = max(len(active), 1)
    high_risk = len(active[active["attrition_risk_label"] == "High"]) if "attrition_risk_label" in active.columns else 0
    att_pct   = round(high_risk / total_fte * 100, 1)

    cap         = make_capacity_forecast()
    current_gap = int(cap.iloc[0]["gap_fte"])
    gap_pct     = round(current_gap / cap.iloc[0]["demand_fte"] * 100, 1)

    high_abs   = len(active[active["absence_risk_label"] == "High"]) if "absence_risk_label" in active.columns else 0
    avail_pct  = round(high_abs / total_fte * 100, 1)

    return {
        "total_fte":              total_fte,
        "attrition_risk_pct":     att_pct,
        "high_risk_count":        high_risk,
        "workforce_gap_pct":      gap_pct,
        "current_gap_fte":        current_gap,
        "availability_risk_pct":  avail_pct,
        "internal_mobility_rate": 8.4,
        "time_to_hire":           50,
        "avg_attrition_rate":     4.7,
    }


# ── Sample CSV generation ─────────────────────────────────────────────────────

def generate_sample_csvs(seed: int = SEED) -> dict:
    """
    Generate realistic sample CSVs from synthetic data and save them to data/raw/.
    Returns dict of {name: row_count}.
    """
    from data_loader import save_raw, ensure_dirs
    ensure_dirs()
    counts = {}

    # Employees
    emp = make_employee_master(seed=seed)
    save_raw("employees", emp)
    counts["employees"] = len(emp)

    # Absences
    np.random.seed(seed + 10)
    today = datetime.today()
    abs_rows = []
    for _, row in emp.sample(min(200, len(emp)), random_state=seed).iterrows():
        n_events = int(np.random.choice([0, 1, 2, 3], p=[0.5, 0.3, 0.15, 0.05]))
        for _ in range(n_events):
            abs_date = today - timedelta(days=int(np.random.randint(1, 365)))
            abs_rows.append({
                "employee_id":    int(row["employee_id"]),
                "department":     row["department"],
                "region":         row["region"],
                "absence_date":   abs_date.strftime("%Y-%m-%d"),
                "absence_days":   int(np.random.choice([1, 2, 3, 5, 10], p=[0.4, 0.25, 0.2, 0.1, 0.05])),
                "absence_reason": str(np.random.choice(
                    ["Illness", "Family", "Medical", "Other"], p=[0.55, 0.2, 0.15, 0.1])),
            })
    abs_df = pd.DataFrame(abs_rows) if abs_rows else pd.DataFrame(
        columns=["employee_id", "department", "region", "absence_date", "absence_days", "absence_reason"])
    save_raw("absences", abs_df)
    counts["absences"] = len(abs_df)

    # Recruitment
    np.random.seed(seed + 20)
    stages = ["Applications", "Screened", "Interviewed", "Offer Made", "Hired"]
    rec_rows = []
    for i in range(480):
        stage_idx = int(np.random.choice(range(5), p=[0.44, 0.19, 0.18, 0.11, 0.08]))
        app_date  = today - timedelta(days=int(np.random.randint(1, 180)))
        hire_date = (app_date + timedelta(days=int(np.random.randint(20, 80)))
                     if stage_idx == 4 else None)
        rec_rows.append({
            "requisition_id":  f"REQ-{2000+i}",
            "department":      str(np.random.choice(DEPARTMENTS)),
            "role_type":       str(np.random.choice(ROLE_TYPES)),
            "region":          str(np.random.choice(REGIONS)),
            "stage":           stages[stage_idx],
            "application_date": app_date.strftime("%Y-%m-%d"),
            "days_in_stage":   int(np.random.randint(1, 30)),
            "hire_date":       hire_date.strftime("%Y-%m-%d") if hire_date else None,
            "status":          "Closed" if stage_idx == 4 else "Open",
        })
    rec_df = pd.DataFrame(rec_rows)
    save_raw("recruitment", rec_df)
    counts["recruitment"] = len(rec_df)

    # Vacancies
    np.random.seed(seed + 30)
    vac_rows = []
    for i, dept in enumerate(DEPARTMENTS):
        for j in range(int(np.random.randint(1, 6))):
            d = int(np.random.randint(5, 120))
            open_date = today - timedelta(days=d)
            vac_rows.append({
                "vacancy_id":  f"VAC-{3000 + i*10 + j}",
                "department":  dept,
                "role_type":   str(np.random.choice(ROLE_TYPES)),
                "region":      str(np.random.choice(REGIONS)),
                "open_date":   open_date.strftime("%Y-%m-%d"),
                "days_open":   d,
                "target_fte":  int(np.random.randint(1, 5)),
                "status":      "Critical" if d > 90 else ("At Risk" if d > 60 else "On Track"),
            })
    vac_df = pd.DataFrame(vac_rows)
    save_raw("vacancies", vac_df)
    counts["vacancies"] = len(vac_df)

    # Attrition history
    att_df = make_attrition_history(seed=seed)
    att_df["month"] = att_df["month"].dt.strftime("%Y-%m-%d")
    save_raw("attrition_history", att_df)
    counts["attrition_history"] = len(att_df)

    # Capacity plan
    cap_df = make_capacity_forecast(months=24)
    cap_df["month"] = cap_df["month"].dt.strftime("%Y-%m-%d")
    for i, dept in enumerate(DEPARTMENTS):
        weight = [0.226, 0.145, 0.129, 0.089, 0.065, 0.137, 0.145, 0.065][i]
        cap_df[f"demand_{dept.lower().replace(' ', '_').replace('&', 'and')}"] = \
            (cap_df["demand_fte"] * weight).round(0).astype(int)
    save_raw("capacity_plan", cap_df)
    counts["capacity_plan"] = len(cap_df)

    return counts
