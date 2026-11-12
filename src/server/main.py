"""
NASA Space Apps - Crew Health Monitoring Console
FastAPI WebSocket & REST Server (src/server/main.py)

Streams physiological telemetry from demo_fixtures/vitals.json at 1 row/second (with speed control).
Runs compute/detect.py rules on each frame and emits live alerts + OSDR evidence citations.
Also serves static HTML console for local hosting.
"""

import asyncio
import json
from pathlib import Path
from typing import Dict, Any, List, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from src.compute.detect import evaluate_vitals_frame
from src.agent.explanation import generate_explanation, load_cached_studies

BASE_DIR = Path(__file__).resolve().parent.parent.parent
FIXTURES_DIR = BASE_DIR / "demo_fixtures"

app = FastAPI(
    title="NASA Space Apps - CDSS Autonomous Crew Health Core",
    description="Deterministic anomaly detection, personal baselines, and NASA OSDR scientific literature evidence layer.",
    version="2.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def load_fixture_data(filename: str = "vitals.json") -> Dict[str, Any]:
    file_path = FIXTURES_DIR / filename
    if not file_path.exists():
        file_path = FIXTURES_DIR / "vitals_planted.json"
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)


@app.get("/api/health")
def health_check():
    return {
        "status": "ONLINE",
        "system": "CDSS Autonomous Crew Health Core",
        "disclaimer": "SIMULATED TELEMETRY FOR RESEARCH & EVALUATION",
        "mode": "deterministic_detection_engine",
        "license": "Apache-2.0"
    }


@app.get("/api/osdr-studies")
def get_osdr_studies():
    return {"studies": load_cached_studies()}


@app.post("/api/evaluate-frame")
def evaluate_frame_endpoint(payload: Dict[str, Any]):
    """Runs deterministic z-score and multi-signal detection rules."""
    history = payload.get("history", {})
    current_values = payload.get("current", {})
    baseline_days = payload.get("baseline_days", 30)
    threshold_sd = payload.get("threshold_sd", 2.0)
    
    alert_obj = evaluate_vitals_frame(history, current_values, baseline_days, threshold_sd)
    explanation_res = generate_explanation(alert_obj)
    
    return {
        "alert": alert_obj,
        "explanation": explanation_res
    }


@app.websocket("/ws/vitals")
async def websocket_vitals_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint replaying demo_fixtures/vitals.json at 1 row/second.
    Supports client commands:
      - {"action": "speed", "multiplier": 2.0}
      - {"action": "pause"}
      - {"action": "play"}
      - {"action": "restart"}
      - {"action": "jump_to_anomaly"}
    """
    await websocket.accept()
    data = load_fixture_data("vitals.json")
    stream: List[Dict[str, Any]] = data.get("stream", [])
    baseline_history: Dict[str, List[float]] = data.get("baseline_history", {})
    
    speed_multiplier = 1.0
    is_paused = False
    index = 0
    total_frames = len(stream)
    
    # Send initial handshake with baseline ranges and OSDR metadata
    await websocket.send_json({
        "type": "INIT_METADATA",
        "disclaimer": "SIMULATED TELEMETRY FOR RESEARCH & EVALUATION",
        "crew_id": data.get("crew_id", "ASTRO-CDR-4"),
        "crew_name": data.get("crew_name", "Commander Sarah Vance"),
        "mission": data.get("mission", "ISS Expedition 74"),
        "baseline_window_days": data.get("baseline_window_days", 30),
        "baseline_history": baseline_history,
        "total_frames": total_frames,
        "osdr_studies": load_cached_studies()
    })
    
    # Task to listen for incoming client control commands
    async def command_listener():
        nonlocal speed_multiplier, is_paused, index
        try:
            while True:
                text = await websocket.receive_text()
                msg = json.loads(text)
                action = msg.get("action")
                if action == "speed":
                    speed_multiplier = float(msg.get("multiplier", 1.0))
                elif action == "pause":
                    is_paused = True
                elif action == "play":
                    is_paused = False
                elif action == "restart":
                    index = 0
                elif action == "jump_to_anomaly":
                    # Jump directly to the frame where anomaly is planted
                    for i, f in enumerate(stream):
                        if f.get("anomaly_planted"):
                            index = i
                            break
        except Exception:
            pass

    listener_task = asyncio.create_task(command_listener())
    
    try:
        while True:
            if not is_paused and total_frames > 0:
                frame = stream[index]
                
                # Run deterministic detection rules
                alert_obj = evaluate_vitals_frame(baseline_history, current_values=frame)
                
                # If an anomaly fired, generate the non-diagnostic explanation with OSDR citations
                explanation_res = None
                if alert_obj.get("any_rule_fired"):
                    explanation_res = generate_explanation(alert_obj)
                    
                payload = {
                    "type": "VITALS_FRAME",
                    "frame_index": index,
                    "second": frame.get("second", index + 1),
                    "timestamp_offset": frame.get("timestamp_offset", f"+00:00:{index+1:02d}"),
                    "vitals": frame,
                    "alert": alert_obj,
                    "explanation": explanation_res,
                    "speed_multiplier": speed_multiplier
                }
                
                await websocket.send_json(payload)
                index = (index + 1) % total_frames
                
            sleep_duration = max(0.05, 1.0 / max(0.1, speed_multiplier))
            await asyncio.sleep(sleep_duration)
            
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        listener_task.cancel()


# Mount static files so navigating to http://localhost:8000/ opens the console directly
if (BASE_DIR / "index.html").exists():
    app.mount("/", StaticFiles(directory=str(BASE_DIR), html=True), name="static")
