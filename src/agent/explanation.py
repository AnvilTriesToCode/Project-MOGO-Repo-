"""
NASA Space Apps - Crew Health Monitoring Console
Explanation Layer (src/agent/explanation.py)

Core Principle: Nothing is diagnosed; everything is evidenced.
Receives ONLY the alert object + cached OSDR study metadata.
Describes what deviated and cites study ID + URL.
Must NEVER state a diagnosis or recommend treatment.
Enforced via system constraints AND a deterministic post-check that blocks diagnostic language.
"""

import json
import re
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple


BLOCKED_DIAGNOSTIC_TERMS = [
    r"\bdiagnos(is|ed|ing|e)?\b",
    r"\bprescrib(e|ed|ing|tion)?\b",
    r"\btreat(ment|ed|ing|s)?\b",
    r"\bpatient suffers from\b",
    r"\bpatholog(y|ical)\b",
    r"\bdisease\b",
    r"\billness\b",
    r"\bcur(e|ed|ing)?\b",
    r"\bprognos(is|tic)?\b",
    r"\bclinical condition\b",
    r"\bmedicat(e|ed|ion|ions)\b",
    r"\bdrug therapy\b"
]

SYSTEM_PROMPT = """
You are the NASA Crew Health Telemetry Explanation Agent.
Your SOLE purpose is to explain deterministic mathematical anomalies flagged in crew physiological streams.
You have access ONLY to:
1. The structured mathematical alert object (signal name, current value, personal baseline mean, baseline standard deviation, z-score, and window duration).
2. Cached NASA Open Science Data Repository (OSDR), GeneLab, and NTRS study metadata.

MANDATORY RULES:
1. NEVER diagnose a disease, pathology, or medical condition.
2. NEVER prescribe drugs or recommend clinical treatments.
3. CLEARLY state what changed numerically against the crewmember's personal baseline.
4. CITE the relevant NASA OSDR, GeneLab, or NTRS study identifier and URL supporting the physiological interpretation.
5. Emphasize that all findings are purely observational, evidence-backed statistical deviations.
"""


def load_cached_studies() -> List[Dict[str, Any]]:
    """Loads cached OSDR/GeneLab metadata from src/data/osdr_cache.json."""
    cache_path = Path(__file__).resolve().parent.parent / "data" / "osdr_cache.json"
    if cache_path.exists():
        with open(cache_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("studies", [])
    return []


def validate_non_diagnostic_language(text: str) -> Tuple[bool, List[str]]:
    """
    POST-CHECK GUARDRAIL:
    Scans the generated explanation text for any prohibited diagnostic or treatment terms.
    Returns (is_valid, list_of_violations).
    """
    violations = []
    text_lower = text.lower()
    for pattern in BLOCKED_DIAGNOSTIC_TERMS:
        matches = re.findall(pattern, text_lower)
        if matches:
            violations.append(pattern)
    return len(violations) == 0, violations


def find_matching_studies(signal_names: List[str], studies: Optional[List[Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
    """Finds OSDR/GeneLab studies matching the deviated signals."""
    if studies is None:
        studies = load_cached_studies()
        
    matched = []
    for study in studies:
        targets = study.get("target_signals", [])
        if any(sig in targets for sig in signal_names):
            matched.append(study)
            
    if not matched and studies:
        matched.append(studies[0])  # Fallback to general autonomic study OSD-379
    return matched


def generate_explanation(alert_object: Dict[str, Any], studies: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """
    Generates an evidence-backed explanation from an alert object and cached OSDR studies.
    Ensures zero diagnostic claims and strictly verifies through the post-check filter.
    """
    if studies is None:
        studies = load_cached_studies()
        
    rules_fired = [r for r in alert_object.get("rules", []) if r.get("fired")]
    multi_signal = alert_object.get("multi_signal", {})
    
    if not rules_fired and not multi_signal.get("fired"):
        explanation_text = "All physiological telemetry remains within nominal personal baseline tolerances (within +/- 2.0 standard deviations). No deterministic deviation rules have triggered."
        valid, _ = validate_non_diagnostic_language(explanation_text)
        return {
            "status": "NOMINAL",
            "explanation": explanation_text,
            "evidence_citations": [],
            "post_check_passed": valid,
            "violations_detected": []
        }
        
    # Gather signals that deviated
    deviated_signals = [r.get("signal", "unknown") for r in rules_fired]
    matched_studies = find_matching_studies(deviated_signals, studies)
    
    # Construct evidenced explanation
    parts = []
    parts.append("DETERMINISTIC TELEMETRY ANOMALY DETECTED:")
    for r in rules_fired:
        sig = r.get("signal", "").upper()
        curr = r.get("current")
        unit = r.get("unit", "")
        mu = r.get("baseline_mean")
        sd = r.get("baseline_sd")
        z = r.get("z")
        win = r.get("window_days", 30)
        parts.append(
            f"• {sig}: Current value is {curr} {unit} compared to personal {win}-day baseline mean of {mu} {unit} (SD: {sd}). "
            f"Z-score deviation: {z} (Threshold: {r.get('threshold_sd', 2.0)} SD). Rule: '{r.get('rule')}'."
        )
        
    if multi_signal.get("fired"):
        parts.append(
            f"• MULTI-SIGNAL DEVIATION: {multi_signal.get('active_count')} physiological signals concurrently deviated "
            f"in a {multi_signal.get('window_hours')}-hour observation window: {', '.join(multi_signal.get('triggering_signals', []))}."
        )
        
    parts.append("\nPHYSIOLOGICAL CONTEXT & SCIENTIFIC LITERATURE EVIDENCE:")
    citations = []
    for s in matched_studies[:2]:
        parts.append(f"• [{s['repository']} - {s['id']}] {s['title']}")
        parts.append(f"  Context: {s['physiological_context']}")
        parts.append(f"  Reference URL: {s['url']}")
        citations.append({
            "id": s["id"],
            "repository": s["repository"],
            "title": s["title"],
            "url": s["url"]
        })
        
    parts.append("\nREGULATORY DISCLAIMER: This is a statistical anomaly detection notice based on individual baseline deviations. In compliance with flight autonomy standards, this system does not provide medical diagnoses or prescribe clinical therapies.")
    
    full_explanation = "\n".join(parts)
    
    # Run post-check guardrail
    valid, violations = validate_non_diagnostic_language(full_explanation)
    if not valid:
        # Sanitize any accidental violation
        for pattern in violations:
            full_explanation = re.sub(pattern, "[EVIDENCE_TERM]", full_explanation, flags=re.IGNORECASE)
        valid, violations = validate_non_diagnostic_language(full_explanation)
        
    return {
        "status": "EVIDENCED_ALERT",
        "explanation": full_explanation,
        "rules_triggered": [r.get("rule") for r in rules_fired],
        "deviating_signals": deviated_signals,
        "evidence_citations": citations,
        "post_check_passed": valid,
        "violations_detected": violations
    }
