"""
NASA Space Apps - Crew Health Monitoring Console
Deterministic Anomaly Detection Engine (src/compute/detect.py)

Core Principle: A detection rule, not a diagnosis. Nothing is diagnosed; everything is evidenced.
Calculates personal baselines, rolling statistics, and z-score deviation rules.
No language model is used for computing these rules.
"""

from typing import Dict, List, Any, Optional, Union
import numpy as np


def hrv_deviation(series: Union[List[float], np.ndarray], baseline_days: int = 30, threshold_sd: float = 2.0) -> Dict[str, Any]:
    """
    Flags when HRV falls more than threshold_sd below the personal baseline.
    Returns the rule that fired and the exact numbers behind it. No interpretation.
    
    Formula:
      mu = mean(series[-baseline_days:])
      sd = std(series[-baseline_days:], ddof=1)
      z = (current - mu) / sd
      fired = (z <= -threshold_sd)
    """
    arr = np.asarray(series, dtype=float)
    if len(arr) == 0:
        return {
            "rule": "hrv_below_personal_baseline",
            "current": 0.0,
            "baseline_mean": 0.0,
            "baseline_sd": 0.0,
            "z": 0.0,
            "fired": False,
            "window_days": baseline_days,
            "error": "empty_series"
        }
    
    # Baseline consists of the historical window up to the current point
    base_window = arr[-baseline_days:] if len(arr) >= baseline_days else arr
    mu = float(base_window.mean())
    sd = float(base_window.std(ddof=1)) if len(base_window) > 1 else 0.0
    current = float(arr[-1])
    
    z = float((current - mu) / sd) if sd > 1e-6 else 0.0
    fired = bool(z <= -threshold_sd)
    
    return {
        "rule": "hrv_below_personal_baseline",
        "signal": "hrv",
        "unit": "ms",
        "current": float(round(current, 2)),
        "baseline_mean": float(round(mu, 2)),
        "baseline_sd": float(round(sd, 2)),
        "z": float(round(z, 2)),
        "threshold_sd": float(threshold_sd),
        "fired": fired,
        "window_days": baseline_days
    }


def signal_deviation(
    series: Union[List[float], np.ndarray],
    signal_name: str,
    unit: str,
    baseline_window: int = 30,
    threshold_sd: float = 2.0,
    direction: str = "both"  # 'below', 'above', or 'both'
) -> Dict[str, Any]:
    """
    Generic personal baseline z-score deviation detector for any physiological signal.
    """
    arr = np.asarray(series, dtype=float)
    if len(arr) == 0:
        return {
            "rule": f"{signal_name}_deviation",
            "signal": signal_name,
            "unit": unit,
            "current": 0.0,
            "baseline_mean": 0.0,
            "baseline_sd": 0.0,
            "z": 0.0,
            "fired": False,
            "window_days": baseline_window
        }
    
    base_window = arr[-baseline_window:] if len(arr) >= baseline_window else arr
    mu = float(base_window.mean())
    sd = float(base_window.std(ddof=1)) if len(base_window) > 1 else 0.0
    current = float(arr[-1])
    
    z = float((current - mu) / sd) if sd > 1e-6 else 0.0
    
    if direction == "below":
        fired = bool(z <= -threshold_sd)
    elif direction == "above":
        fired = bool(z >= threshold_sd)
    else:
        fired = bool(abs(z) >= threshold_sd)
        
    return {
        "rule": f"{signal_name}_deviation",
        "signal": signal_name,
        "unit": unit,
        "current": float(round(current, 2)),
        "baseline_mean": float(round(mu, 2)),
        "baseline_sd": float(round(sd, 2)),
        "z": float(round(z, 2)),
        "threshold_sd": float(threshold_sd),
        "direction": direction,
        "fired": fired,
        "window_days": baseline_window
    }


def multi_signal_rule(
    deviations: List[Dict[str, Any]],
    min_deviations: int = 2,
    window_hours: int = 48
) -> Dict[str, Any]:
    """
    Multi-signal rule that fires when two or more physiological signals
    deviate beyond their personal baselines in the same window (e.g. 48 hours).
    
    Returns the composite alert object containing all triggering deviations.
    """
    active_deviations = [d for d in deviations if d.get("fired") is True]
    fired = len(active_deviations) >= min_deviations
    
    triggering_signals = [d.get("signal", d.get("rule", "unknown")) for d in active_deviations]
    
    return {
        "rule": "multi_signal_deviation_48h",
        "fired": fired,
        "active_count": len(active_deviations),
        "min_required": min_deviations,
        "window_hours": window_hours,
        "triggering_signals": triggering_signals,
        "sub_rules": active_deviations
    }


def evaluate_vitals_frame(
    history: Dict[str, List[float]],
    current_values: Optional[Dict[str, float]] = None,
    baseline_days: int = 30,
    threshold_sd: float = 2.0
) -> Dict[str, Any]:
    """
    Evaluates all required physiological signals for a given timestamp:
      - Heart Rate (bpm)
      - HRV (ms)
      - SpO2 (%)
      - Sleep Hours (hrs)
      - Core Temperature (C)
      - Exercise Minutes (min)
      
    Returns a structured alert object with every signal rule and the multi-signal composite rule.
    """
    # Append current values if provided
    combined: Dict[str, List[float]] = {}
    for key, series in history.items():
        arr = list(series)
        if current_values and key in current_values:
            arr.append(current_values[key])
        combined[key] = arr
        
    rules_evaluated: List[Dict[str, Any]] = []
    
    # 1. HRV Rule (Primary OSDR metric)
    if "hrv" in combined and len(combined["hrv"]) > 0:
        hrv_res = hrv_deviation(combined["hrv"], baseline_days=baseline_days, threshold_sd=threshold_sd)
        rules_evaluated.append(hrv_res)
        
    # 2. Heart Rate Rule
    if "heart_rate" in combined and len(combined["heart_rate"]) > 0:
        hr_res = signal_deviation(combined["heart_rate"], "heart_rate", "bpm", baseline_days, threshold_sd, direction="above")
        rules_evaluated.append(hr_res)
        
    # 3. SpO2 Rule
    if "spo2" in combined and len(combined["spo2"]) > 0:
        spo2_res = signal_deviation(combined["spo2"], "spo2", "%", baseline_days, threshold_sd, direction="below")
        rules_evaluated.append(spo2_res)
        
    # 4. Sleep Hours Rule
    if "sleep_hours" in combined and len(combined["sleep_hours"]) > 0:
        sleep_res = signal_deviation(combined["sleep_hours"], "sleep_hours", "hrs", baseline_days, threshold_sd, direction="below")
        rules_evaluated.append(sleep_res)
        
    # 5. Core Temperature Rule
    if "core_temp" in combined and len(combined["core_temp"]) > 0:
        temp_res = signal_deviation(combined["core_temp"], "core_temp", "C", baseline_days, threshold_sd, direction="above")
        rules_evaluated.append(temp_res)
        
    # 6. Exercise Minutes Rule
    if "exercise_minutes" in combined and len(combined["exercise_minutes"]) > 0:
        ex_res = signal_deviation(combined["exercise_minutes"], "exercise_minutes", "min", baseline_days, threshold_sd, direction="below")
        rules_evaluated.append(ex_res)
        
    # 7. Composite Multi-Signal Rule
    multi_res = multi_signal_rule(rules_evaluated, min_deviations=2, window_hours=48)
    
    any_fired = any(r.get("fired") for r in rules_evaluated) or multi_res["fired"]
    
    return {
        "status": "ANOMALY_DETECTED" if any_fired else "NOMINAL",
        "any_rule_fired": any_fired,
        "rules": rules_evaluated,
        "multi_signal": multi_res,
        "summary": {
            "total_signals_evaluated": len(rules_evaluated),
            "signals_deviating": [r["signal"] for r in rules_evaluated if r.get("fired")],
            "multi_signal_triggered": multi_res["fired"]
        }
    }
