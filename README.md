# hr-analytics-hub

> Version: v01: 2026-05-02

A BI analytics dashboard showcasing the data visualization part of a talent analytics system for the energy domain.
Packaged as one integrated screen with layered navigation, where each section maps directly to HR decisions and associated talent analytics metrics.

It is a decision-first integrated dashboard structure, aligned with core HR competencies + highest-impact business components in utilities.

## 1. Design Philosophy

This screen is built around 3 principles:

- Top = decisions (what needs attention now)
- Middle = diagnostics (why it’s happening)
- Bottom = actions (what to do next)

It maps to 4 core HR domains:

- Workforce Stability
- Workforce Capacity
- Workforce Productivity & Availability
- Talent Flow (Recruitment & Mobility)

## 2. Integrated Dashboard Layout (Single Screen)

### A. Executive Control Panel (Top Strip — “Where do I act now?”)

Purpose: Immediate prioritization for HRBP / management

Components:

- Total workforce (FTE)
- Attrition risk (next 6 months)
- Workforce gap (demand vs supply)
- Availability risk (% workforce at risk of absence)

Visuals:

- KPI tiles with trend arrows
- Traffic light indicators (Red / Amber / Green)

Decision Trigger:  “Which teams require intervention this week?”

### B. Workforce Risk & Stability (Attrition Focus)

HR Competency: Retention & Employee Experience

Visual Blocks:

- Attrition risk distribution (by department/role)
- High-risk employee segments (Top 10–20%)

Key drivers:

- salary growth
- tenure
- manager/team effect

Advanced Layer: “What changed vs last month?”

Decision Example:  Identify high-risk technician teams +  trigger retention actions

### C. Workforce Capacity & Demand Planning

HR Competency: Strategic Workforce Planning

Visual Blocks:

- Demand vs capacity forecast (line chart)
- Gap analysis by:

	- role (technicians, engineers)
	- region

- Scenario simulation:

	- hiring vs outsourcing vs overtime

Decision Example:  Anticipate shortage +  start hiring 3 months earlier

### D. Workforce Availability & Absenteeism

HR Competency: Workforce Health & Continuity

Visual Blocks:

- Predicted absenteeism rate
- Availability forecast (next 4–12 weeks)
- Heatmap:

	- department × absence risk
	- Seasonal trends

Decision Example:  High winter absence risk + pre-allocate backup staff

### E. Talent Flow (Recruitment & Internal Mobility)

HR Competency: Talent Acquisition & Development

Visual Blocks:

- Time-to-hire trends
- Funnel conversion rates
- Internal mobility rate
- Vacancy aging

Decision Example:  Bottleneck in hiring +  adjust sourcing strategy

### F. Action & Intervention Panel

This is what makes the dashboard actionable.

Components:

- “Recommended actions” based on models:
- Retention intervention needed
- Hiring required
- Workforce redistribution
- Priority list: Top 5 teams needing attention
- Action tracking:

	- Actions taken
	- Status (open / in progress / closed)

Decision Example:  HRBP executes actions directly from this list

### G. Drill-Down Layer (Interactive)

Accessible from every section:

- Employee-level view (if allowed)
- Team-level breakdown
- Time comparison (MoM, YoY)

## 3. Cross-Dashboard Filters (Global Controls)

These must be consistent across tools (Power BI / Tableau / Grafana / Streamlit):

- Department
- Role type (field vs office — critical for utilities)
- Region
- Time period
- Manager

## 4. Data Model Behind the Dashboard

Core datasets:

- Employee master data
- Absence records
- Recruitment pipeline
- Workforce planning / scheduling
- Organizational hierarchy

Key design principle:  Build a unified employee-level dataset (single source of truth)

## 5. KPI Layer (Standardized Across All Sections)

- Stability
- Attrition rate
- Predicted attrition risk
- Capacity
- Workforce gap (%)
- Forecast accuracy
- Availability
- Absenteeism rate
- Predicted absence risk
- Talent Flow
- Time-to-hire
- Internal mobility rate
- Adoption (internal success metric)
- Dashboard usage
- Actions taken
