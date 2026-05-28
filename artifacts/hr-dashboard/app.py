"""
app.py  —  HR Analytics Dashboard
Decision-first, 8-tab Streamlit app.
Data loading priority: data/raw/ CSVs → synthetic fallback
Filtered exports go to data/processed/
"""
import json
import os
from datetime import datetime, timedelta

import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from config import (
    load_config, save_config, config_to_json, config_from_json,
    DEFAULT_CONFIG, CONFIG_PATH,
)
from data import (
    make_employee_master, enrich_employees,
    make_attrition_history, filter_attrition_history,
    make_capacity_forecast, make_absence_heatmap,
    make_recruitment_funnel, make_time_to_hire,
    make_vacancy_aging, make_recommended_actions, get_kpis,
    generate_sample_csvs,
    DEPARTMENTS, REGIONS, ROLE_TYPES, MANAGERS,
)
from data_loader import (
    has_raw, load_raw, save_raw, upload_and_save, export_filtered,
    list_raw_files, list_processed_files, read_processed_bytes,
    apply_temporal_filter, get_active_filters, SOURCES,
)

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="HR Analytics",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Palette ───────────────────────────────────────────────────────────────────
BLUE   = "#003F87"
ORANGE = "#F07D00"
GREEN  = "#2ECC71"
AMBER  = "#F39C12"
RED    = "#E74C3C"
BG     = "#F5F7FA"
FONT   = "Inter, sans-serif"
RAG    = {"Low": GREEN, "Medium": AMBER, "High": RED}
SCOL   = {"Open": RED, "In Progress": AMBER, "Closed": GREEN}

# ── Session-state bootstrap ───────────────────────────────────────────────────
if "cfg" not in st.session_state:
    st.session_state.cfg = load_config()
if "excluded_employees" not in st.session_state:
    st.session_state.excluded_employees = set(
        st.session_state.cfg.get("excluded_employees", []))
if "refresh_key" not in st.session_state:
    st.session_state.refresh_key = 0
if "export_msgs" not in st.session_state:
    st.session_state.export_msgs = {}

cfg  = st.session_state.cfg
p    = cfg["parameters"]
seed = int(p["seed"])
kv   = cfg["kpis"]


# ── Data loading (real → synthetic fallback) ──────────────────────────────────
@st.cache_data(show_spinner="Loading data…")
def load_employees_cached(seed, n, rh, rm, ah, am, _refresh_key):
    raw = load_raw("employees")
    if raw is not None:
        df = enrich_employees(raw, risk_high=rh, risk_med=rm, abs_high=ah, abs_med=am)
        source = "real"
    else:
        df = make_employee_master(n=n, seed=seed, risk_high=rh, risk_med=rm,
                                   abs_high=ah, abs_med=am)
        source = "synthetic"
    return df, source

@st.cache_data(show_spinner=False)
def load_attrition_cached(seed, _refresh_key):
    raw = load_raw("attrition_history")
    if raw is not None and "attrition_rate" in raw.columns:
        raw["month"] = pd.to_datetime(raw["month"], errors="coerce")
        return raw.dropna(subset=["month"]), "real"
    return make_attrition_history(seed=seed), "synthetic"

@st.cache_data(show_spinner=False)
def load_recruitment_cached(_refresh_key):
    return load_raw("recruitment")

@st.cache_data(show_spinner=False)
def load_vacancies_cached(_refresh_key):
    return load_raw("vacancies")

@st.cache_data(show_spinner=False)
def load_capacity_cached(months, _refresh_key):
    raw = load_raw("capacity_plan")
    if raw is not None and {"month", "demand_fte", "supply_fte"}.issubset(raw.columns):
        raw["month"]      = pd.to_datetime(raw["month"], errors="coerce")
        raw["gap_fte"]    = raw["demand_fte"] - raw["supply_fte"]
        return raw.dropna(subset=["month"]).head(months), "real"
    return make_capacity_forecast(months=months), "synthetic"

rk = st.session_state.refresh_key
employees_raw, emp_source = load_employees_cached(
    seed, int(p["n_employees"]),
    p["attrition_risk_high_threshold"], p["attrition_risk_medium_threshold"],
    p["absence_risk_high_threshold"],   p["absence_risk_medium_threshold"],
    rk,
)
attrition_full, att_source = load_attrition_cached(seed, rk)
rec_raw    = load_recruitment_cached(rk)
vac_raw    = load_vacancies_cached(rk)
capacity_full, cap_source  = load_capacity_cached(int(p["forecast_months"]), rk)


# ── Source badge helper ───────────────────────────────────────────────────────
def source_badge(source: str) -> str:
    if source == "real":
        return "🟢 Real data (data/raw)"
    return "🔵 Synthetic data"


# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### ⚡ HR Analytics")

    # ── Categorical filters ──
    st.markdown("## Filters")
    sel_depts   = st.multiselect("Department", DEPARTMENTS, default=DEPARTMENTS)
    sel_regions = st.multiselect("Region",     REGIONS,     default=REGIONS)
    sel_roles   = st.multiselect("Role Type",  ROLE_TYPES,  default=ROLE_TYPES)
    sel_manager = st.selectbox("Manager", ["All"] + MANAGERS)

    st.markdown("---")

    # ── Temporal filters ──
    st.markdown("### Temporal Filters")
    today      = datetime.today().date()
    min_hire   = (datetime.today() - timedelta(days=5000)).date()

    hire_range = st.date_input(
        "Hire Date Range",
        value=(min_hire, today),
        min_value=min_hire,
        max_value=today,
        key="hire_range",
    )
    hire_start = pd.Timestamp(hire_range[0]) if isinstance(hire_range, (list, tuple)) and len(hire_range) >= 1 else None
    hire_end   = pd.Timestamp(hire_range[1]) if isinstance(hire_range, (list, tuple)) and len(hire_range) == 2 else None

    sel_period = st.selectbox("Reporting Period",
        ["Last 6 Months", "Last 12 Months", "Last 18 Months", "YTD", "Custom"])

    if sel_period == "Custom":
        rep_range = st.date_input(
            "Custom Report Range",
            value=((datetime.today() - timedelta(days=365)).date(), today),
            min_value=min_hire, max_value=today, key="rep_range",
        )
        report_start = pd.Timestamp(rep_range[0]) if isinstance(rep_range, (list, tuple)) and len(rep_range) >= 1 else None
        report_end   = pd.Timestamp(rep_range[1]) if isinstance(rep_range, (list, tuple)) and len(rep_range) == 2 else None
    else:
        report_end   = pd.Timestamp(today)
        offset_days  = {"Last 6 Months": 182, "Last 12 Months": 365,
                         "Last 18 Months": 548, "YTD": (datetime.today() - datetime(datetime.today().year, 1, 1)).days}
        report_start = report_end - timedelta(days=offset_days.get(sel_period, 365))

    st.markdown("---")

    # ── Refresh ──
    if st.button("🔄 Refresh All Data", use_container_width=True, type="primary"):
        st.cache_data.clear()
        st.session_state.refresh_key += 1
        st.rerun()

    excl = len(st.session_state.excluded_employees)
    if excl:
        st.warning(f"{excl} employee(s) excluded")
    st.caption(f"Source: {source_badge(emp_source)}")
    st.caption(f"Seed `{seed}` · N `{int(p['n_employees'])}`")
    st.caption(f"Data as of {pd.Timestamp.today().strftime('%d %b %Y')}")


# ── Apply filters to employees ────────────────────────────────────────────────
employees = employees_raw.copy()

# Exclude manually excluded employees
if st.session_state.excluded_employees:
    employees = employees[~employees["employee_id"].isin(st.session_state.excluded_employees)]

# Categorical filters
employees = employees[
    employees["department"].isin(sel_depts) &
    employees["region"].isin(sel_regions) &
    employees["role_type"].isin(sel_roles)
]
if sel_manager != "All":
    employees = employees[employees["manager"] == sel_manager]

# Hire date temporal filter
employees = apply_temporal_filter(employees, "hire_date", hire_start, hire_end)

# ── Filter attrition history to reporting period ──────────────────────────────
attrition_hist = filter_attrition_history(attrition_full.copy(), report_start, report_end)

# ── Derived data ──────────────────────────────────────────────────────────────
kpis       = get_kpis(employees)
absence_hm = make_absence_heatmap(employees, weeks=int(p["absence_forecast_weeks"]), seed=seed)
funnel_df  = make_recruitment_funnel(rec_raw)
tth_df     = make_time_to_hire(rec_raw, seed=seed)
vacancy_df = make_vacancy_aging(vac_raw, seed=seed)
actions_df = make_recommended_actions(employees)
capacity_fc= capacity_full  # already filtered by months param

# ── Active filter dict for exports ───────────────────────────────────────────
active_filters = get_active_filters(
    sel_depts, sel_regions, sel_roles, sel_manager,
    hire_start, hire_end, report_start, report_end,
)


# ── Tab export helper ─────────────────────────────────────────────────────────
def tab_export_toolbar(tab_key: str, df: pd.DataFrame, label: str = "filtered employees"):
    """Renders a compact refresh + export row at the top of a tab."""
    cr, cb, cs = st.columns([5, 1, 2])
    with cb:
        if st.button("🔄 Refresh", key=f"ref_{tab_key}", use_container_width=True):
            st.cache_data.clear()
            st.session_state.refresh_key += 1
            st.rerun()
    with cs:
        if st.button(f"💾 Export {label}", key=f"exp_{tab_key}", use_container_width=True):
            fname, fpath, csv_bytes = export_filtered(tab_key, df, active_filters)
            st.session_state.export_msgs[tab_key] = (fname, csv_bytes)
            st.rerun()

    if tab_key in st.session_state.export_msgs:
        fname, csv_bytes = st.session_state.export_msgs[tab_key]
        dl_col, _ = st.columns([2, 5])
        dl_col.download_button(
            f"⬇ Download {fname}",
            data=csv_bytes,
            file_name=fname,
            mime="text/csv",
            key=f"dl_{tab_key}",
        )
        st.success(f"Saved to `data/processed/{fname}`")


# ── Page header ───────────────────────────────────────────────────────────────
st.markdown("# ⚡ HR Analytics — Integrated Decision Dashboard")
st.markdown(
    f"_Decision-first · Workforce Stability · Capacity · Availability · Talent Flow_ &nbsp; "
    f"| &nbsp; Employees in view: **{len(employees):,}** "
    f"| Report: **{report_start.strftime('%d %b %Y') if report_start else '—'}** → "
    f"**{report_end.strftime('%d %b %Y') if report_end else '—'}**"
)
st.markdown("---")

# ── Tabs ──────────────────────────────────────────────────────────────────────
enabled = [t for t in cfg["dashboard_structure"]["tabs"] if t["enabled"]]
tab_labels = [f"{t['icon']} {t['label']}" for t in enabled] + ["⚙️ Settings"]
all_tabs   = st.tabs(tab_labels)
tab_map    = {t["id"]: all_tabs[i] for i, t in enumerate(enabled)}
tab_settings = all_tabs[-1]


# ═══════════════════════════════════════════════════════════════════════════════
# A. EXECUTIVE OVERVIEW
# ═══════════════════════════════════════════════════════════════════════════════
if "overview" in tab_map:
    with tab_map["overview"]:
        tab_export_toolbar("overview", employees, "employees")
        st.subheader("A · Executive Control Panel — Where do I act now?")
        st.caption(f"Source: {source_badge(emp_source)} · {len(employees):,} employees in view")

        kpi_defs = [
            ("show_total_fte",          "Total Workforce (FTE)",    kpis["total_fte"],              "+12 vs last month",                         False),
            ("show_attrition_risk_pct", "Attrition Risk (6m)",      f"{kpis['attrition_risk_pct']}%", f"+{kpis['high_risk_count']} high-risk",   True),
            ("show_workforce_gap",      "Workforce Gap",            f"{kpis['workforce_gap_pct']}%",  f"{kpis['current_gap_fte']} FTE shortfall", True),
            ("show_availability_risk",  "Availability Risk",        f"{kpis['availability_risk_pct']}%", "↑ 2.1% vs last quarter",               True),
            ("show_time_to_hire",       "Avg. Time-to-Hire",        f"{kpis['time_to_hire']}d",          "+5d vs target",                        True),
        ]
        cols = st.columns(sum(1 for k, *_ in kpi_defs if kv.get(k, True)))
        ci = 0
        for key, label, val, delta, inv in kpi_defs:
            if kv.get(key, True):
                cols[ci].metric(label, val, delta=delta,
                                delta_color="inverse" if inv else "normal")
                ci += 1

        st.markdown("---")
        cl, cr = st.columns([3, 2])
        rh = p["attrition_risk_high_threshold"]; rm = p["attrition_risk_medium_threshold"]
        with cl:
            st.markdown("#### Attrition Risk by Department")
            rd = (employees.groupby("department")["attrition_risk_score"]
                  .mean().reset_index().sort_values("attrition_risk_score", ascending=False))
            rd["rag"] = rd["attrition_risk_score"].apply(
                lambda x: "High" if x > rh else ("Medium" if x > rm else "Low"))
            fig = px.bar(rd, x="attrition_risk_score", y="department", orientation="h",
                         color="rag", color_discrete_map=RAG,
                         labels={"attrition_risk_score": "Avg Risk Score", "department": ""})
            fig.update_layout(height=340, plot_bgcolor=BG, paper_bgcolor="white",
                              font_family=FONT, margin=dict(l=10, r=10, t=10, b=10))
            st.plotly_chart(fig, use_container_width=True)

        with cr:
            st.markdown("#### Workforce Health Radar")
            cats   = ["Stability", "Capacity", "Availability", "Talent Flow", "Engagement"]
            scores = [
                max(0, 100 - kpis["attrition_risk_pct"]    * 3),
                max(0, 100 - kpis["workforce_gap_pct"]     * 4),
                max(0, 100 - kpis["availability_risk_pct"] * 2.5),
                max(0, 100 - (kpis["time_to_hire"] - 30)   * 1.5),
                72,
            ]
            fig2 = go.Figure()
            fig2.add_trace(go.Scatterpolar(r=scores + [scores[0]], theta=cats + [cats[0]],
                                           fill="toself", fillcolor="rgba(0,63,135,0.15)",
                                           line=dict(color=BLUE, width=2), name="Current"))
            fig2.add_trace(go.Scatterpolar(r=[80]*6, theta=cats + [cats[0]],
                                           line=dict(color=GREEN, width=1.5, dash="dash"),
                                           name="Target", mode="lines"))
            fig2.update_layout(polar=dict(radialaxis=dict(range=[0, 100])),
                               height=340, font_family=FONT,
                               margin=dict(l=30, r=30, t=30, b=20))
            st.plotly_chart(fig2, use_container_width=True)

        st.markdown("#### RAG Status — Teams Requiring Intervention")
        ov = employees.groupby("department").agg(
            fte=("employee_id","count"),
            avg_att=("attrition_risk_score","mean"),
            high_risk=("attrition_risk_label", lambda x:(x=="High").sum()),
            avg_abs=("absence_risk_score","mean"),
        ).reset_index()
        np.random.seed(seed)
        ov["gap_fte"]       = ov["department"].map({d: int(np.random.randint(5,25)) for d in DEPARTMENTS})
        ov["Attrition Risk"]= ov["avg_att"].apply(lambda x:"🔴 High" if x>.45 else("🟡 Medium" if x>.28 else "🟢 Low"))
        ov["Absence Risk"]  = ov["avg_abs"].apply(lambda x:"🔴 High" if x>.35 else("🟡 Medium" if x>.20 else "🟢 Low"))
        ov["Capacity Risk"] = ov["gap_fte"].apply(lambda x:"🔴 High" if x>18   else("🟡 Medium" if x>10   else "🟢 Low"))
        st.dataframe(ov[["department","fte","high_risk","Attrition Risk","Absence Risk","Capacity Risk","gap_fte"]].rename(
            columns={"department":"Department","fte":"FTE","high_risk":"High-Risk","gap_fte":"FTE Gap"}),
            use_container_width=True, hide_index=True)


# ═══════════════════════════════════════════════════════════════════════════════
# B. ATTRITION RISK
# ═══════════════════════════════════════════════════════════════════════════════
if "attrition" in tab_map:
    with tab_map["attrition"]:
        tab_export_toolbar("attrition", employees, "employees")
        st.subheader("B · Workforce Risk & Stability")
        st.caption(f"Source: {source_badge(emp_source)} · Reporting: {report_start.strftime('%d %b %Y') if report_start else '—'} → {report_end.strftime('%d %b %Y') if report_end else '—'}")

        m1, m2, m3 = st.columns(3)
        m1.metric("Overall Attrition Rate",  f"{kpis['avg_attrition_rate']}%",  delta="+0.8% MoM",  delta_color="inverse")
        m2.metric("High-Risk Employees",     kpis["high_risk_count"],            delta=f"{kpis['attrition_risk_pct']}% of workforce", delta_color="inverse")
        m3.metric("Internal Mobility Rate",  f"{kpis['internal_mobility_rate']}%", delta="+1.2% YoY")

        st.markdown("---")
        c1, c2 = st.columns(2)

        with c1:
            st.markdown("#### Attrition Risk Distribution")
            rd = employees.groupby(["department","attrition_risk_label"]).size().reset_index(name="count")
            fig = px.bar(rd, x="department", y="count", color="attrition_risk_label",
                         color_discrete_map=RAG, barmode="stack",
                         labels={"count":"Employees","department":"","attrition_risk_label":"Risk"})
            fig.update_xaxes(tickangle=45)
            fig.update_layout(height=360, plot_bgcolor=BG, paper_bgcolor="white",
                              font_family=FONT, margin=dict(l=10,r=10,t=10,b=80))
            st.plotly_chart(fig, use_container_width=True)

        with c2:
            st.markdown("#### Historical vs Predicted Attrition")
            thr = p["attrition_alert_threshold"]
            fig2 = go.Figure()
            fig2.add_trace(go.Scatter(x=attrition_hist["month"], y=attrition_hist["attrition_rate"],
                                      mode="lines+markers", name="Actual",
                                      line=dict(color=BLUE, width=2)))
            fig2.add_trace(go.Scatter(x=attrition_hist["month"], y=attrition_hist["predicted_rate"],
                                      mode="lines+markers", name="Predicted",
                                      line=dict(color=ORANGE, width=2, dash="dash")))
            fig2.add_hline(y=thr, line_dash="dot", line_color=RED,
                           annotation_text=f"Alert {thr}%")
            fig2.update_layout(height=360, plot_bgcolor=BG, paper_bgcolor="white",
                               font_family=FONT, legend=dict(orientation="h",y=1.1),
                               yaxis_title="Attrition Rate (%)",
                               margin=dict(l=10,r=10,t=20,b=20))
            st.plotly_chart(fig2, use_container_width=True)

        st.markdown("#### Key Risk Drivers")
        d3, d4, d5 = st.columns(3)

        with d3:
            st.markdown("**Salary Growth vs Risk**")
            s = employees.sample(min(300, len(employees)), random_state=seed) if len(employees) else employees
            fig3 = px.scatter(s, x="salary_growth_pct", y="attrition_risk_score",
                              color="attrition_risk_label", color_discrete_map=RAG, opacity=0.6,
                              labels={"salary_growth_pct":"Salary Growth (%)","attrition_risk_score":"Risk Score"})
            fig3.update_layout(height=280, showlegend=False, plot_bgcolor=BG,
                               paper_bgcolor="white", font_family=FONT, margin=dict(l=10,r=10,t=10,b=20))
            st.plotly_chart(fig3, use_container_width=True)

        with d4:
            st.markdown("**Tenure vs Risk**")
            tb = pd.cut(employees["tenure_years"], bins=[0,1,2,5,10,30],
                        labels=["<1yr","1-2yr","2-5yr","5-10yr",">10yr"])
            tr = employees.groupby(tb, observed=False)["attrition_risk_score"].mean().reset_index()
            tr.columns = ["band","avg"]
            fig4 = px.bar(tr, x="band", y="avg", color="avg",
                          color_continuous_scale=[GREEN, AMBER, RED],
                          labels={"avg":"Avg Risk","band":"Tenure"})
            fig4.update_layout(height=280, coloraxis_showscale=False, plot_bgcolor=BG,
                               paper_bgcolor="white", font_family=FONT, margin=dict(l=10,r=10,t=10,b=20))
            st.plotly_chart(fig4, use_container_width=True)

        with d5:
            st.markdown("**Top 20 High-Risk Employees**")
            top20 = (employees[employees["attrition_risk_label"]=="High"]
                     .sort_values("attrition_risk_score",ascending=False)
                     .head(20)[["employee_id","department","role_type","tenure_years","attrition_risk_score"]].copy())
            top20["attrition_risk_score"] = top20["attrition_risk_score"].map("{:.2%}".format)
            st.dataframe(top20, use_container_width=True, hide_index=True, height=280)

        st.info("💡 **Decision Trigger:** Identify high-risk technician teams → trigger retention dialogue and compensation review.")


# ═══════════════════════════════════════════════════════════════════════════════
# C. CAPACITY PLANNING
# ═══════════════════════════════════════════════════════════════════════════════
if "capacity" in tab_map:
    with tab_map["capacity"]:
        tab_export_toolbar("capacity", capacity_fc, "capacity plan")
        st.subheader("C · Workforce Capacity & Demand Planning")
        st.caption(f"Source: {source_badge(cap_source)} · {int(p['forecast_months'])}-month view")

        peak_gap = int(capacity_fc["gap_fte"].max())
        m1, m2, m3 = st.columns(3)
        m1.metric("Current FTE vs Demand", f"{kpis['workforce_gap_pct']}% gap",
                  delta=f"{kpis['current_gap_fte']} FTE short", delta_color="inverse")
        m2.metric("Peak Gap (forecast)", f"{peak_gap} FTE", delta_color="inverse")
        m3.metric("Forecast Accuracy", "91.3%", delta="+2.1% vs last model")

        st.markdown("---")
        c1, c2 = st.columns([3, 2])
        with c1:
            st.markdown(f"#### Demand vs Supply ({int(p['forecast_months'])} Months)")
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=capacity_fc["month"], y=capacity_fc["demand_fte"],
                                     mode="lines+markers", name="Demand",
                                     line=dict(color=ORANGE, width=2.5)))
            fig.add_trace(go.Scatter(x=capacity_fc["month"], y=capacity_fc["supply_fte"],
                                     mode="lines+markers", name="Supply",
                                     line=dict(color=BLUE, width=2.5)))
            fig.add_trace(go.Scatter(
                x=list(capacity_fc["month"])+list(capacity_fc["month"])[::-1],
                y=list(capacity_fc["demand_fte"])+list(capacity_fc["supply_fte"])[::-1],
                fill="toself", fillcolor="rgba(231,76,60,0.1)", line=dict(width=0),
                name="Gap"))
            fig.update_layout(height=380, plot_bgcolor=BG, paper_bgcolor="white",
                              font_family=FONT, legend=dict(orientation="h",y=1.1),
                              yaxis_title="FTE", margin=dict(l=10,r=10,t=20,b=20))
            st.plotly_chart(fig, use_container_width=True)

        with c2:
            st.markdown("#### FTE Gap by Role")
            rgd = {"Field Technician":42,"Engineer":28,"Office Specialist":12,
                   "Project Lead":15,"Analyst":8,"Manager":3}
            rdf = pd.DataFrame({"role":list(rgd),"gap":list(rgd.values())})
            fig2 = px.bar(rdf.sort_values("gap"), x="gap", y="role", orientation="h",
                          color="gap", color_continuous_scale=[AMBER,RED],
                          labels={"gap":"FTE Shortfall","role":""})
            fig2.update_layout(height=380, coloraxis_showscale=False, plot_bgcolor=BG,
                               paper_bgcolor="white", font_family=FONT, margin=dict(l=10,r=10,t=10,b=10))
            st.plotly_chart(fig2, use_container_width=True)

        st.markdown("#### Scenario Simulator")
        sc1, sc2, sc3 = st.columns(3)
        hire_rt   = sc1.slider("Monthly Hires",          0, 30,  10)
        out_pct   = sc2.slider("Outsourcing (% of gap)", 0, 100, 20)
        ot_pct    = sc3.slider("Overtime (% of gap)",    0, 50,  10)
        gaps      = capacity_fc["gap_fte"].tolist()
        coverage  = [(hire_rt*(i+1)) + g*out_pct/100 + g*ot_pct/100 for i,g in enumerate(gaps)]
        rem_gap   = [max(0,g-c) for g,c in zip(gaps,coverage)]
        fig3 = go.Figure()
        fig3.add_trace(go.Bar(x=capacity_fc["month"], y=gaps,    name="Raw Gap",       marker_color=RED,   opacity=0.6))
        fig3.add_trace(go.Bar(x=capacity_fc["month"], y=rem_gap, name="Remaining Gap", marker_color=ORANGE))
        fig3.add_trace(go.Scatter(x=capacity_fc["month"], y=[hire_rt*(i+1) for i in range(len(gaps))],
                                  mode="lines", name="Cum. Hires", line=dict(color=GREEN,width=2)))
        fig3.update_layout(barmode="overlay", height=300, plot_bgcolor=BG, paper_bgcolor="white",
                           font_family=FONT, legend=dict(orientation="h",y=1.1),
                           margin=dict(l=10,r=10,t=20,b=20))
        st.plotly_chart(fig3, use_container_width=True)
        st.info("💡 **Decision Trigger:** Start hiring pipeline 3 months ahead for Field Technicians and Engineers.")


# ═══════════════════════════════════════════════════════════════════════════════
# D. AVAILABILITY
# ═══════════════════════════════════════════════════════════════════════════════
if "absence" in tab_map:
    with tab_map["absence"]:
        tab_export_toolbar("absence", employees, "absence data")
        st.subheader("D · Workforce Availability & Absenteeism")
        st.caption(f"Source: {source_badge(emp_source)}")

        total    = max(len(employees[employees["is_active"]]) if "is_active" in employees.columns else len(employees), 1)
        high_abs = len(employees[employees["absence_risk_label"]=="High"]) if "absence_risk_label" in employees.columns else 0
        m1, m2, m3 = st.columns(3)
        m1.metric("Predicted Absence Rate",      "6.8%",   delta="+1.2% vs winter",    delta_color="inverse")
        m2.metric("High Absence-Risk Employees",  high_abs, delta=f"{round(high_abs/total*100,1)}%", delta_color="inverse")
        m3.metric("Availability Rate (4-week)",  "91.4%",  delta="-2.1% vs target",    delta_color="inverse")

        st.markdown("---")
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("#### Absence Risk Heatmap (Dept × Week)")
            pivot = absence_hm.pivot(index="department", columns="week", values="absence_rate_pct")
            fig = px.imshow(pivot, color_continuous_scale=[GREEN, AMBER, RED],
                            labels=dict(x="Week",y="Department",color="Abs Rate (%)"),
                            aspect="auto")
            fig.update_layout(height=380, font_family=FONT, margin=dict(l=10,r=10,t=10,b=20))
            st.plotly_chart(fig, use_container_width=True)

        with c2:
            st.markdown("#### Absence Risk Distribution")
            ad = employees.groupby(["department","absence_risk_label"]).size().reset_index(name="count") if "absence_risk_label" in employees.columns else pd.DataFrame()
            if not ad.empty:
                fig2 = px.bar(ad, x="department", y="count", color="absence_risk_label",
                              color_discrete_map=RAG, barmode="stack",
                              labels={"count":"Employees","department":"","absence_risk_label":"Risk"})
                fig2.update_xaxes(tickangle=45)
                fig2.update_layout(height=380, plot_bgcolor=BG, paper_bgcolor="white",
                                   font_family=FONT, margin=dict(l=10,r=10,t=10,b=80))
                st.plotly_chart(fig2, use_container_width=True)

        thr_abs  = p["absence_alert_threshold"]
        wks      = int(p["absence_forecast_weeks"])
        wk_labels= [f"W{i}" for i in range(1, wks+1)]
        seasonal = ([7.2,7.5,7.1,6.8,6.4,6.2,6.0,5.9,6.3,7.0,7.8,8.1]*3)[:wks]
        fig3 = go.Figure()
        fig3.add_trace(go.Scatter(x=wk_labels, y=seasonal, mode="lines+markers",
                                  name="Predicted", line=dict(color=ORANGE,width=2.5),
                                  fill="toself", fillcolor="rgba(240,125,0,0.1)"))
        fig3.add_trace(go.Scatter(x=wk_labels, y=[thr_abs]*wks, mode="lines",
                                  name=f"Alert {thr_abs}%", line=dict(color=RED,width=1.5,dash="dot")))
        fig3.update_layout(height=280, plot_bgcolor=BG, paper_bgcolor="white",
                           font_family=FONT, yaxis_title="Absence Rate (%)",
                           legend=dict(orientation="h",y=1.1), margin=dict(l=10,r=10,t=10,b=20))
        st.plotly_chart(fig3, use_container_width=True)
        st.info("💡 **Decision Trigger:** Winter absence risk → pre-allocate backup field technicians for W11–W12.")


# ═══════════════════════════════════════════════════════════════════════════════
# E. TALENT FLOW
# ═══════════════════════════════════════════════════════════════════════════════
if "talent" in tab_map:
    with tab_map["talent"]:
        tab_export_toolbar("talent", rec_raw if rec_raw is not None else pd.DataFrame(), "recruitment data")
        st.subheader("E · Talent Flow — Recruitment & Internal Mobility")
        src_label = source_badge("real" if rec_raw is not None else "synthetic")
        st.caption(f"Source: {src_label}")

        tth_tgt = int(p["tth_target_days"])
        crit    = len(vacancy_df[vacancy_df["status"]=="Critical"]) if "status" in vacancy_df.columns else 0
        m1,m2,m3,m4 = st.columns(4)
        m1.metric("Time-to-Hire (avg)", f"{kpis['time_to_hire']}d",
                  delta=f"+{kpis['time_to_hire']-tth_tgt}d vs target", delta_color="inverse")
        m2.metric("Offer Acceptance Rate","73.1%", delta="-3.2% vs last quarter", delta_color="inverse")
        m3.metric("Internal Mobility Rate",f"{kpis['internal_mobility_rate']}%", delta="+1.2% YoY")
        m4.metric("Open Vacancies", str(len(vacancy_df)), delta=f"{crit} critical",
                  delta_color="inverse" if crit else "normal")

        st.markdown("---")
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("#### Recruitment Funnel")
            fig = go.Figure(go.Funnel(
                y=funnel_df["stage"], x=funnel_df["count"], textinfo="value+percent initial",
                marker=dict(color=[BLUE,"#1A5276","#1F618D",ORANGE,GREEN])))
            fig.update_layout(height=380, font_family=FONT, paper_bgcolor="white",
                              margin=dict(l=10,r=10,t=20,b=20))
            st.plotly_chart(fig, use_container_width=True)

        with c2:
            st.markdown("#### Time-to-Hire Trend")
            tth_plot = tth_df.copy()
            tth_plot["target_days"] = tth_tgt
            fig2 = go.Figure()
            fig2.add_trace(go.Scatter(x=tth_plot["month"], y=tth_plot["avg_days"],
                                      mode="lines+markers", name="Avg Days",
                                      line=dict(color=ORANGE,width=2.5)))
            fig2.add_trace(go.Scatter(x=tth_plot["month"], y=tth_plot["target_days"],
                                      mode="lines", name=f"Target ({tth_tgt}d)",
                                      line=dict(color=GREEN,width=1.5,dash="dash")))
            fig2.update_layout(height=380, plot_bgcolor=BG, paper_bgcolor="white",
                               font_family=FONT, yaxis_title="Days",
                               legend=dict(orientation="h",y=1.1),
                               margin=dict(l=10,r=10,t=20,b=20))
            st.plotly_chart(fig2, use_container_width=True)

        st.markdown("#### Vacancy Aging")
        vd2 = vacancy_df.sort_values("days_open",ascending=False).copy()
        icon_col = vd2["status"].map({"Critical":"🔴","At Risk":"🟡","On Track":"🟢"}) if "status" in vd2.columns else ""
        vd2.insert(0, "", icon_col)
        st.dataframe(vd2, use_container_width=True, hide_index=True, height=280)
        st.info("💡 **Decision Trigger:** Bottleneck in Field Technician pipeline — adjust sourcing strategy.")


# ═══════════════════════════════════════════════════════════════════════════════
# F. ACTIONS
# ═══════════════════════════════════════════════════════════════════════════════
if "actions" in tab_map:
    with tab_map["actions"]:
        tab_export_toolbar("actions", actions_df, "actions")
        st.subheader("F · Action & Intervention Panel")

        oc=len(actions_df[actions_df["status"]=="Open"])
        pc=len(actions_df[actions_df["status"]=="In Progress"])
        dc=len(actions_df[actions_df["status"]=="Closed"])
        m1,m2,m3,m4 = st.columns(4)
        m1.metric("Total Actions",len(actions_df))
        m2.metric("Open",        oc, delta_color="inverse")
        m3.metric("In Progress", pc)
        m4.metric("Closed",      dc)

        st.markdown("---")
        c1, c2 = st.columns([2,3])
        with c1:
            tc = actions_df["action_type"].value_counts().reset_index()
            tc.columns = ["Type","Count"]
            fig = px.pie(tc, values="Count", names="Type",
                         color_discrete_sequence=[BLUE,ORANGE,GREEN,RED], hole=0.45)
            fig.update_layout(height=260, font_family=FONT, paper_bgcolor="white",
                              margin=dict(l=10,r=10,t=10,b=10))
            st.plotly_chart(fig, use_container_width=True)

        with c2:
            sd = actions_df.groupby(["action_type","status"]).size().reset_index(name="count")
            fig2 = px.bar(sd, x="action_type", y="count", color="status",
                          color_discrete_map=SCOL, barmode="stack",
                          labels={"count":"Count","action_type":"Type","status":"Status"})
            fig2.update_layout(height=260, plot_bgcolor=BG, paper_bgcolor="white",
                               font_family=FONT, margin=dict(l=10,r=10,t=10,b=20))
            st.plotly_chart(fig2, use_container_width=True)

        st.markdown("#### Priority Actions")
        for _, row in actions_df.iterrows():
            icon = {"Open":"🔴","In Progress":"🟡","Closed":"🟢"}.get(row["status"],"⚪")
            with st.expander(f"{icon} P{row['priority']} · {row['action_type']} · {row['department']}"):
                cc1,cc2,cc3 = st.columns(3)
                uc = "red" if row["urgency"]=="High" else ("orange" if row["urgency"]=="Medium" else "green")
                cc1.markdown(f"**Urgency:** :{uc}[{row['urgency']}]")
                cc2.markdown(f"**Owner:** {row['owner']}")
                cc3.markdown(f"**Status:** {row['status']}")
                st.markdown(f"**Action:** {row['description']}")
                st.selectbox("Update status",["Open","In Progress","Closed"],
                             index=["Open","In Progress","Closed"].index(row["status"]),
                             key=f"act_{row['priority']}")


# ═══════════════════════════════════════════════════════════════════════════════
# G. DRILL-DOWN
# ═══════════════════════════════════════════════════════════════════════════════
if "drilldown" in tab_map:
    with tab_map["drilldown"]:
        tab_export_toolbar("drilldown", employees, "drill-down data")
        st.subheader("G · Drill-Down — Employee & Team Level")

        dc1, dc2 = st.columns(2)
        sdept   = dc1.selectbox("Department", DEPARTMENTS, key="dd_dept")
        sview   = dc2.radio("View", ["Department Summary","Individual Employees","Time Comparison"], horizontal=True)
        ddept   = employees[employees["department"]==sdept]

        if sview == "Department Summary":
            d1,d2,d3,d4 = st.columns(4)
            d1.metric("Total FTE", len(ddept))
            d2.metric("High Attrition Risk", len(ddept[ddept["attrition_risk_label"]=="High"]) if "attrition_risk_label" in ddept.columns else "—")
            d3.metric("High Absence Risk",   len(ddept[ddept["absence_risk_label"]  =="High"]) if "absence_risk_label"   in ddept.columns else "—")
            d4.metric("Avg Tenure", f"{ddept['tenure_years'].mean():.1f}yr" if len(ddept) and "tenure_years" in ddept.columns else "—")
            c1,c2 = st.columns(2)
            with c1:
                fig = px.histogram(ddept, x="attrition_risk_score", nbins=20,
                                   color_discrete_sequence=[BLUE], title="Risk Score Distribution",
                                   labels={"attrition_risk_score":"Score"})
                fig.update_layout(height=280, plot_bgcolor=BG, paper_bgcolor="white",
                                  font_family=FONT, margin=dict(l=10,r=10,t=40,b=20))
                st.plotly_chart(fig, use_container_width=True)
            with c2:
                rb = ddept["role_type"].value_counts().reset_index()
                rb.columns = ["Role","Count"]
                fig2 = px.bar(rb, x="Count", y="Role", orientation="h",
                              color_discrete_sequence=[ORANGE], title="Roles")
                fig2.update_layout(height=280, plot_bgcolor=BG, paper_bgcolor="white",
                                   font_family=FONT, margin=dict(l=10,r=10,t=40,b=20))
                st.plotly_chart(fig2, use_container_width=True)

        elif sview == "Individual Employees":
            show = ["employee_id","role_type","region","manager","tenure_years","age",
                    "salary","attrition_risk_score","attrition_risk_label",
                    "absence_risk_score","absence_risk_label","performance_score"]
            available = [c for c in show if c in ddept.columns]
            st.dataframe(ddept[available].sort_values("attrition_risk_score",ascending=False)
                         if "attrition_risk_score" in ddept.columns else ddept[available],
                         use_container_width=True, hide_index=True, height=450)

        else:
            fig = go.Figure()
            fig.add_trace(go.Bar(x=attrition_hist["month"].dt.strftime("%b %Y"),
                                 y=attrition_hist["attrition_rate"], name="Actual",
                                 marker_color=BLUE))
            fig.add_trace(go.Scatter(x=attrition_hist["month"].dt.strftime("%b %Y"),
                                     y=attrition_hist["predicted_rate"],
                                     mode="lines+markers", name="Predicted",
                                     line=dict(color=ORANGE,width=2,dash="dash")))
            fig.update_layout(height=380, plot_bgcolor=BG, paper_bgcolor="white",
                              font_family=FONT, yaxis_title="Attrition Rate (%)",
                              legend=dict(orientation="h",y=1.1),
                              margin=dict(l=10,r=10,t=20,b=20))
            st.plotly_chart(fig, use_container_width=True)

            kpc = pd.DataFrame({
                "KPI":["Attrition Rate","Absence Rate","TTH (days)","Mobility %","Gap (FTE)"],
                "Current":[4.7,6.8,50,8.4,kpis["current_gap_fte"]],
                "Last Month":[4.1,6.1,48,7.8,28], "Last Year":[3.8,5.9,44,6.5,18],
            })
            kpc["MoM"] = (kpc["Current"]-kpc["Last Month"]).map(lambda x: f"+{x:.1f}" if x>0 else f"{x:.1f}")
            kpc["YoY"] = (kpc["Current"]-kpc["Last Year"]).map(lambda x:  f"+{x:.1f}" if x>0 else f"{x:.1f}")
            st.dataframe(kpc, use_container_width=True, hide_index=True)


# ═══════════════════════════════════════════════════════════════════════════════
# ⚙️  SETTINGS
# ═══════════════════════════════════════════════════════════════════════════════
with tab_settings:
    st.subheader("⚙️ Settings & Data Management")

    # ── Config file controls ──────────────────────────────────────────────────
    st.markdown("### Configuration")
    cc1,cc2,cc3 = st.columns(3)
    if cc1.button("💾 Save Config", use_container_width=True):
        st.session_state.cfg["excluded_employees"] = list(st.session_state.excluded_employees)
        save_config(st.session_state.cfg)
        st.success("Saved to `dashboard_config.json`")
    if cc2.button("🔄 Reload Config", use_container_width=True):
        st.session_state.cfg = load_config()
        st.session_state.excluded_employees = set(st.session_state.cfg.get("excluded_employees",[]))
        st.rerun()
    if cc3.button("↩️ Reset Defaults", use_container_width=True):
        st.session_state.cfg = json.loads(json.dumps(DEFAULT_CONFIG))
        st.session_state.excluded_employees = set()
        st.rerun()

    dl_col, up_col = st.columns(2)
    dl_col.download_button("⬇ Download config JSON", data=config_to_json(st.session_state.cfg),
                            file_name="xxx_hr_config.json", mime="application/json",
                            use_container_width=True)
    upl = up_col.file_uploader("⬆ Upload config JSON", type=["json"], key="cfg_up")
    if upl:
        try:
            st.session_state.cfg = config_from_json(upl.read().decode())
            st.session_state.excluded_employees = set(st.session_state.cfg.get("excluded_employees",[]))
            st.rerun()
        except Exception as e:
            st.error(f"Invalid config: {e}")

    st.markdown("---")

    # ── Data sources ──────────────────────────────────────────────────────────
    st.markdown("### Data Sources — Load Real Data")
    st.info(
        "Upload CSVs to replace synthetic data. Files are saved to `data/raw/` and "
        "used immediately on the next refresh. Click **Generate Sample CSVs** to "
        "create ready-to-download templates."
    )

    # Sample CSV generator
    if st.button("🔬 Generate Sample CSVs from Synthetic Data", type="primary"):
        with st.spinner("Generating…"):
            counts = generate_sample_csvs(seed=seed)
        st.cache_data.clear()
        st.session_state.refresh_key += 1
        st.success(f"Generated: {', '.join(f'{k} ({v} rows)' for k,v in counts.items())}")
        st.rerun()

    # Per-source upload + status table
    raw_status = {r["key"]: r for r in list_raw_files()}
    for key, meta in SOURCES.items():
        info = raw_status.get(key, {})
        exists = info.get("exists", False)
        label  = meta["label"]
        icon   = "🟢" if exists else "🔴"
        rows   = f"{info['rows']:,}" if info.get("rows") is not None else "—"
        with st.expander(f"{icon} **{label}** ({meta['filename']}) · {rows} rows · {info.get('modified','—')}"):
            st.caption(meta["description"])
            st.markdown(f"**Required columns:** `{', '.join(meta['required_cols'])}`")
            upl2 = st.file_uploader(f"Upload {label} CSV", type=["csv"], key=f"up_{key}")
            if upl2 is not None:
                df_up, msg = upload_and_save(key, upl2)
                if df_up is not None:
                    st.success(msg)
                    st.cache_data.clear()
                    st.session_state.refresh_key += 1
                    st.rerun()
                else:
                    st.error(msg)
            if exists:
                raw_df = load_raw(key)
                if raw_df is not None:
                    st.markdown(f"**Preview** (first 5 rows):")
                    st.dataframe(raw_df.head(5), use_container_width=True, hide_index=True)
                    dl_bytes = raw_df.to_csv(index=False).encode()
                    st.download_button(f"⬇ Download {meta['filename']}",
                                       data=dl_bytes, file_name=meta["filename"],
                                       mime="text/csv", key=f"dl_raw_{key}")

    st.markdown("---")

    # ── Processed exports ─────────────────────────────────────────────────────
    st.markdown("### Processed Exports — data/processed/")
    proc = list_processed_files()
    if not proc:
        st.info("No exports yet. Use the **Export** button in each dashboard tab to save filtered data here.")
    else:
        for f in proc[:20]:
            pc1, pc2, pc3 = st.columns([4, 1, 1])
            pc1.markdown(f"`{f['filename']}` — {f['size_kb']} KB — {f['modified']}")
            try:
                bytes_ = read_processed_bytes(f["path"])
                pc2.download_button("⬇", data=bytes_, file_name=f["filename"],
                                    mime="text/csv", key=f"dl_proc_{f['filename']}")
            except Exception:
                pass
            if pc3.button("🗑", key=f"del_{f['filename']}"):
                try:
                    os.remove(f["path"])
                    st.rerun()
                except Exception:
                    pass

    st.markdown("---")

    # ── Model parameters ──────────────────────────────────────────────────────
    with st.expander("🔧 Model & Data Parameters"):
        pp = st.session_state.cfg["parameters"]
        pa, pb, pc_ = st.columns(3)
        with pa:
            st.markdown("**Core**")
            pp["seed"]            = st.number_input("Random Seed",       0,  99999, int(pp["seed"]),            step=1)
            pp["n_employees"]     = st.number_input("N Employees",       50, 5000,  int(pp["n_employees"]),     step=10)
            pp["forecast_months"] = st.slider("Forecast Months",         3,  24,    int(pp["forecast_months"]))
            pp["absence_forecast_weeks"] = st.slider("Absence Weeks",    4,  26,    int(pp["absence_forecast_weeks"]))
        with pb:
            st.markdown("**Attrition**")
            pp["attrition_risk_high_threshold"] = st.slider("High Risk ≥", 0.30, 0.90, float(pp["attrition_risk_high_threshold"]), 0.01)
            pp["attrition_risk_medium_threshold"]= st.slider("Med Risk ≥",  0.10, 0.60, float(pp["attrition_risk_medium_threshold"]),0.01)
            pp["attrition_alert_threshold"]      = st.number_input("Alert %",  1.0, 20.0, float(pp["attrition_alert_threshold"]), 0.5)
        with pc_:
            st.markdown("**Absence & Talent**")
            pp["absence_risk_high_threshold"]   = st.slider("Abs High ≥", 0.20, 0.80, float(pp["absence_risk_high_threshold"]),   0.01)
            pp["absence_risk_medium_threshold"] = st.slider("Abs Med ≥",  0.05, 0.50, float(pp["absence_risk_medium_threshold"]),  0.01)
            pp["absence_alert_threshold"]       = st.number_input("Abs Alert %", 1.0, 20.0, float(pp["absence_alert_threshold"]), 0.5)
            pp["tth_target_days"]               = st.number_input("TTH Target (d)", 10, 120, int(pp["tth_target_days"]), 1)
        if st.button("Apply Parameters & Regenerate", type="primary"):
            st.cache_data.clear()
            st.session_state.refresh_key += 1
            st.rerun()

    # ── KPI visibility ────────────────────────────────────────────────────────
    with st.expander("📊 KPI Visibility"):
        kv_labels = {
            "show_total_fte":"Total Workforce (FTE)","show_attrition_risk_pct":"Attrition Risk %",
            "show_workforce_gap":"Workforce Gap %","show_availability_risk":"Availability Risk %",
            "show_time_to_hire":"Time-to-Hire","show_internal_mobility":"Internal Mobility",
            "show_attrition_rate":"Overall Attrition Rate","show_forecast_accuracy":"Forecast Accuracy",
        }
        kv2 = st.columns(2)
        for i,(k,lbl) in enumerate(kv_labels.items()):
            cfg["kpis"][k] = kv2[i%2].checkbox(lbl, value=bool(cfg["kpis"].get(k,True)), key=f"kv2_{k}")

    # ── Tab structure ─────────────────────────────────────────────────────────
    with st.expander("🗂️ Tab Visibility"):
        tc2 = st.columns(2)
        for i, tab_item in enumerate(cfg["dashboard_structure"]["tabs"]):
            tab_item["enabled"] = tc2[i%2].checkbox(
                f"{tab_item['icon']} {tab_item['label']}",
                value=bool(tab_item["enabled"]), key=f"tv_{tab_item['id']}")

    # ── Employee management ───────────────────────────────────────────────────
    with st.expander("👥 Employee Management"):
        ec1,ec2,ec3,ec4 = st.columns([2,2,2,1])
        sid  = ec1.text_input("Search by ID", placeholder="e.g. 1042")
        sdep = ec2.selectbox("Dept Filter", ["All"]+DEPARTMENTS, key="emp_df2")
        srol = ec3.selectbox("Role Filter", ["All"]+ROLE_TYPES,  key="emp_rf2")
        sexcl= ec4.checkbox("Excl only")
        edf  = employees_raw.copy()
        if sid.strip():
            try: edf = edf[edf["employee_id"]==int(sid.strip())]
            except ValueError: pass
        if sdep!="All": edf = edf[edf["department"]==sdep]
        if srol!="All": edf = edf[edf["role_type"]==srol]
        if sexcl:       edf = employees_raw[employees_raw["employee_id"].isin(st.session_state.excluded_employees)]
        edf = edf.head(150).copy()
        edf["excluded"] = edf["employee_id"].isin(st.session_state.excluded_employees)
        st.caption(f"{len(edf)} shown · {len(st.session_state.excluded_employees)} excluded")
        ba1,ba2,ba3 = st.columns(3)
        if ba1.button("Exclude all in view"):  st.session_state.excluded_employees.update(edf["employee_id"].tolist()); st.rerun()
        if ba2.button("Include all in view"):
            for e in edf["employee_id"].tolist(): st.session_state.excluded_employees.discard(e)
            st.rerun()
        if ba3.button("Clear all exclusions"): st.session_state.excluded_employees.clear(); st.rerun()
        for _, row in edf[["employee_id","department","role_type","tenure_years",
                             "attrition_risk_label","absence_risk_label","excluded"]].iterrows():
            eid = int(row["employee_id"])
            c_info, c_btn = st.columns([6,1])
            c_info.markdown(
                f"`{eid}` **{row['department']}** · {row['role_type']} · "
                f"{row['tenure_years']}yr · Att:{row['attrition_risk_label']} · "
                f"Abs:{row['absence_risk_label']}"
            )
            if c_btn.button("✅" if row["excluded"] else "❌", key=f"eb_{eid}"):
                if row["excluded"]: st.session_state.excluded_employees.discard(eid)
                else:               st.session_state.excluded_employees.add(eid)
                st.rerun()

# ── Footer ────────────────────────────────────────────────────────────────────
st.markdown("---")
st.caption(
    f"HR Analytics · MLOps Platform · "
    f"Employee data: {source_badge(emp_source)} · "
    f"Attrition history: {source_badge(att_source)} · "
    f"Data as of {pd.Timestamp.today().strftime('%d %b %Y')} · "
    f"Risk scores are model predictions; validate with HR professionals."
)
