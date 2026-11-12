"""
NASA Space Apps - Crew Health Monitoring Console
Unit Tests (tests/test_detect.py)

Validates:
1. HRV deviation rule against clean fixture (must NOT fire)
2. HRV deviation rule against planted anomaly fixture (MUST fire with z <= -2.0)
3. Multi-signal rule on clean vs planted anomaly fixtures
4. Anti-diagnostic explanation post-check guardrail (verifies blocking of diagnostic language)
"""

import json
from pathlib import Path
import pytest
import numpy as np

from src.compute.detect import hrv_deviation, signal_deviation, multi_signal_rule, evaluate_vitals_frame
from src.agent.explanation import generate_explanation, validate_non_diagnostic_language


FIXTURES_DIR = Path(__file__).resolve().parent.parent / "demo_fixtures"


@pytest.fixture
def clean_fixture():
    with open(FIXTURES_DIR / "vitals_clean.json", "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def planted_fixture():
    with open(FIXTURES_DIR / "vitals_planted.json", "r", encoding="utf-8") as f:
        return json.load(f)


def test_hrv_deviation_nominal(clean_fixture):
    """Clean fixture should maintain z > -2.0 and never fire an anomaly flag."""
    baseline = clean_fixture["baseline_history"]["hrv"]
    # Test across all clean frames
    for frame in clean_fixture["stream"]:
        series = baseline + [frame["hrv"]]
        res = hrv_deviation(series, baseline_days=30, threshold_sd=2.0)
        assert res["fired"] is False, f"Nominal frame triggered anomaly: {res}"
        assert res["z"] > -2.0


def test_hrv_deviation_planted_anomaly(planted_fixture):
    """Planted fixture should trigger hrv_below_personal_baseline with z <= -2.0."""
    baseline = planted_fixture["baseline_history"]["hrv"]
    # Look for the planted anomaly frame where HRV was set to 41.2
    anomaly_frames = [f for f in planted_fixture["stream"] if f["anomaly_planted"] and f["hrv"] == 41.2]
    assert len(anomaly_frames) > 0, "No anomaly frame with HRV=41.2 found"
    
    frame = anomaly_frames[0]
    series = baseline + [frame["hrv"]]
    res = hrv_deviation(series, baseline_days=30, threshold_sd=2.0)
    
    assert res["fired"] is True
    assert res["rule"] == "hrv_below_personal_baseline"
    assert res["current"] == 41.2
    assert res["z"] <= -2.0
    assert "baseline_mean" in res
    assert "baseline_sd" in res


def test_multi_signal_rule_clean_fixture(clean_fixture):
    """Clean fixture should not trigger multi-signal deviation rule."""
    baseline_history = clean_fixture["baseline_history"]
    frame = clean_fixture["stream"][0]
    eval_result = evaluate_vitals_frame(baseline_history, current_values=frame)
    
    assert eval_result["multi_signal"]["fired"] is False
    assert eval_result["any_rule_fired"] is False
    assert eval_result["status"] == "NOMINAL"


def test_multi_signal_rule_planted_anomaly(planted_fixture):
    """Planted fixture with multiple deviations in window should trigger multi_signal rule."""
    baseline_history = planted_fixture["baseline_history"]
    # Pick a frame from the end where both HRV and sleep hours were planted as anomalous
    multi_frame = planted_fixture["stream"][-1]
    eval_result = evaluate_vitals_frame(baseline_history, current_values=multi_frame)
    
    assert eval_result["multi_signal"]["fired"] is True
    assert eval_result["multi_signal"]["active_count"] >= 2
    assert "hrv" in eval_result["multi_signal"]["triggering_signals"]
    assert eval_result["status"] == "ANOMALY_DETECTED"


def test_explanation_agent_anti_diagnostic_post_check():
    """
    Validates that the explanation layer strictly rejects and sanitizes diagnostic claims,
    and cites OSDR study identifiers.
    """
    # 1. Test clean explanation
    mock_alert = {
        "rules": [
            {
                "rule": "hrv_below_personal_baseline",
                "signal": "hrv",
                "unit": "ms",
                "current": 41.2,
                "baseline_mean": 68.4,
                "baseline_sd": 9.8,
                "z": -2.77,
                "threshold_sd": 2.0,
                "fired": True
            }
        ],
        "multi_signal": {"fired": False}
    }
    
    explanation_res = generate_explanation(mock_alert)
    assert explanation_res["status"] == "EVIDENCED_ALERT"
    assert explanation_res["post_check_passed"] is True
    assert len(explanation_res["evidence_citations"]) > 0
    assert any("OSD-379" in c["id"] or "OSD-194" in c["id"] for c in explanation_res["evidence_citations"])
    
    # 2. Test the post-check validator explicitly with prohibited diagnostic words
    prohibited_text = "The system diagnosed that the patient suffers from cardiovascular disease and prescribes medication treatment."
    valid, violations = validate_non_diagnostic_language(prohibited_text)
    assert valid is False
    assert len(violations) > 0, "Validator failed to flag prohibited clinical words"
