# Autonomous Crew Health Monitoring Console (CDSS)

> **DATA NOTICE & COMPLIANCE DISCLAIMER:**  
> **All telemetry in this repository is SIMULATED physiological data** generated specifically for algorithm validation, system testing, and hackathon evaluation. In accordance with NASA flight medicine guidance, this console operates strictly on an **evidence-based observation framework**: **nothing is diagnosed; everything is evidenced.**

---

## 1. Challenge & Core Philosophy

Long-duration spaceflight (e.g. aboard the International Space Station or Lunar Gateway) places crew members months away from tertiary medical facilities. Traditional telemetry displays either overwhelm flight surgeons with raw streams or attempt risky black-box diagnoses.

This system demonstrates a valid, clinically grounded architecture:
1. **Deterministic Anomaly Detection:** Real mathematical rules in `src/compute/detect.py` establish personal rolling 30-day baselines ($z$-score calculations) for individual crew members.
2. **Multi-Signal Co-Deviation:** A 48-hour correlation rule flags coupled physiological stressors across multiple signals.
3. **NASA OSDR Literature Layer:** Every flagged deviation is paired directly with published peer-reviewed studies from the **NASA Open Science Data Repository (OSDR)**, **GeneLab**, and **NASA Technical Reports Server (NTRS)**.
4. **Strict Anti-Diagnostic Guardrail:** The explanation agent explains *what mathematical deviation occurred* and *cites the study*, strictly prohibiting diagnostic claims or unauthorized clinical prescribing.

---

## 2. System Architecture

```text
  [demo_fixtures/vitals.json]
             │ (Simulated telemetry replay)
             ▼
  FastAPI WebSocket Stream (/ws/vitals)  ──► Speed Control (0.5x - 10x)
             │
             ▼
    src/compute/detect.py  ◄── Tested Rules & Personal 30-day Baselines
             │
      ┌──────┴──────────────────────┐
      ▼                             ▼
 Live Console View           Alert Object (Rule + Exact Numbers)
 (Baseline Bands + Charts)          │
                                    ▼
                          src/agent/explanation.py
                          (Reads alert + OSDR metadata,
                           cites Study ID & URL,
                           post-check blocks diagnostic language)
```

---

## 3. Physiological Signals Monitored

- **HRV (Heart Rate Variability - rMSSD, ms):** Primary autonomic nervous system metric.
- **Heart Rate (bpm):** Basal cardiovascular exertion.
- **SpO2 (%):** Arterial oxygen saturation.
- **Sleep Architecture (hours):** Rest duration and circadian disruption.
- **Core Temperature (°C):** Thermoregulatory rhythm.
- **Exercise Output (minutes):** Countermeasure compliance.

---

## 4. NASA Open Science Studies Cited

- **NASA OSDR OSD-379:** *Comprehensive Multi-Omics and Autonomic Modulation in Spaceflight* (URL: https://osdr.nasa.gov/bio/repo/data/studies/OSD-379)
- **NASA OSDR OSD-194:** *Cardiovascular and Autonomic Deconditioning in Long-Duration Low Earth Orbit Spaceflight* (URL: https://osdr.nasa.gov/bio/repo/data/studies/OSD-194)
- **NASA OSDR OSD-665:** *Microgravity Hemodynamics and Venous Engorgement* (URL: https://osdr.nasa.gov/bio/repo/data/studies/OSD-665)
- **NASA GeneLab GLDS-114:** *Circadian Pacemaker Disruption and Thermoregulatory Shifts* (URL: https://genelab.nasa.gov/study/GLDS-114)
- **NASA NTRS 20210018049:** *Human Research Program Evidence Book: Sleep & Circadian Adaptation* (URL: https://ntrs.nasa.gov/citations/20210018049)

---

## 5. Quick Start & Execution

### Prerequisites
- Python 3.10+
- Modern Web Browser

### Installation
```bash
pip install -r requirements.txt
```

### Running the Unit Tests
Validates personal baseline $z$-score detection, planted anomaly triggers, clean fixture bounds, and the anti-diagnostic post-check:
```bash
python -m pytest tests/ -v
```

### Starting the Server & Web Console
```bash
python -m uvicorn src.server.main:app --port 8000 --reload
```
Open `http://localhost:8000` in your browser. The console will connect to the live WebSocket stream, replay the telemetry fixture at 1 row/sec, render personal baseline shaded tolerance bands, and allow interactive speed control and instant anomaly triggering.

---

## 6. License
Distributed under the **Apache-2.0 License**. See `LICENSE` for details.
