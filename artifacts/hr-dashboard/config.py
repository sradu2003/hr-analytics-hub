import json
import os
from datetime import datetime

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "dashboard_config.json")

DEFAULT_CONFIG = {
    "meta": {
        "version": "1.0",
        "created": datetime.today().strftime("%Y-%m-%d"),
        "description": "HR Analytics Dashboard Configuration",
    },
    "parameters": {
        "seed": 42,
        "n_employees": 620,
        "forecast_months": 12,
        "absence_forecast_weeks": 12,
        "attrition_risk_high_threshold": 0.55,
        "attrition_risk_medium_threshold": 0.30,
        "absence_risk_high_threshold": 0.40,
        "absence_risk_medium_threshold": 0.20,
        "attrition_alert_threshold": 5.0,
        "absence_alert_threshold": 7.0,
        "tth_target_days": 40,
    },
    "data_sources": {
        "employee_master":      {"type": "synthetic", "path": "", "description": "Synthetic employee master data"},
        "absence_records":      {"type": "synthetic", "path": "", "description": "Synthetic absence records"},
        "recruitment_pipeline": {"type": "synthetic", "path": "", "description": "Synthetic recruitment pipeline"},
        "workforce_planning":   {"type": "synthetic", "path": "", "description": "Synthetic capacity / workforce plan"},
    },
    "kpis": {
        "show_total_fte":         True,
        "show_attrition_risk_pct": True,
        "show_workforce_gap":     True,
        "show_availability_risk": True,
        "show_time_to_hire":      True,
        "show_internal_mobility": True,
        "show_attrition_rate":    True,
        "show_forecast_accuracy": True,
    },
    "dashboard_structure": {
        "tabs": [
            {"id": "overview",   "label": "Executive Overview",  "icon": "🎯", "enabled": True},
            {"id": "attrition",  "label": "Attrition Risk",      "icon": "⚠️", "enabled": True},
            {"id": "capacity",   "label": "Capacity Planning",   "icon": "📊", "enabled": True},
            {"id": "absence",    "label": "Availability",        "icon": "🏥", "enabled": True},
            {"id": "talent",     "label": "Talent Flow",         "icon": "🔄", "enabled": True},
            {"id": "actions",    "label": "Actions",             "icon": "✅", "enabled": True},
            {"id": "drilldown",  "label": "Drill-Down",          "icon": "🔍", "enabled": True},
        ]
    },
    "excluded_employees": [],
}


def load_config(path: str = CONFIG_PATH) -> dict:
    if os.path.exists(path):
        try:
            with open(path, "r") as f:
                saved = json.load(f)
            merged = _deep_merge(DEFAULT_CONFIG, saved)
            return merged
        except Exception:
            pass
    return _deep_copy(DEFAULT_CONFIG)


def save_config(cfg: dict, path: str = CONFIG_PATH) -> None:
    cfg["meta"]["created"] = datetime.today().strftime("%Y-%m-%d")
    with open(path, "w") as f:
        json.dump(cfg, f, indent=2)


def config_to_json(cfg: dict) -> str:
    return json.dumps(cfg, indent=2)


def config_from_json(raw: str) -> dict:
    parsed = json.loads(raw)
    return _deep_merge(DEFAULT_CONFIG, parsed)


def _deep_copy(d):
    return json.loads(json.dumps(d))


def _deep_merge(base: dict, override: dict) -> dict:
    result = _deep_copy(base)
    for k, v in override.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = v
    return result
