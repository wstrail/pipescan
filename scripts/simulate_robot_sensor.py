"""SIMULATION-ONLY: Embedded robot telemetry and sensor-event simulator.

This script mirrors the final production shape:

- The web console sends motion commands to the backend.
- This simulator reads the current command/status from the backend.
- It behaves like an embedded controller by reporting telemetry back.
- It saves inspection defects only when a simulated sensor encounters a pipe
  problem event, not by time or by fixed distance.

Replace this script with the real embedded adapter when hardware is connected.
"""

from __future__ import annotations

import argparse
import json
import math
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime


DEFAULT_API_BASE = "http://localhost:8000"
SENSOR_LOOKAHEAD_M = 0.5


@dataclass(frozen=True)
class PipeEvent:
    start_m: float
    end_m: float
    category: str
    code: str
    score: int
    length: float
    severity: str
    description: str


PIPE_EVENTS = [
    PipeEvent(3.8, 4.6, "functional", "CJ", 3, 0.4, "warning", "管内轻微沉积并影响通行视野，请减速观察。"),
    PipeEvent(8.1, 9.0, "structural", "BX", 6, 0.7, "warning", "管壁变形并伴随局部破损，请减速观察。"),
    PipeEvent(12.9, 13.8, "functional", "SG", 5, 0.5, "warning", "疑似树根侵入，通行空间收窄。"),
    PipeEvent(18.2, 19.5, "structural", "PL", 9, 1.4, "critical", "管道破损严重，疑似塌陷阻挡，请立即停止并复核。"),
    PipeEvent(23.9, 25.1, "functional", "CJ", 4, 0.8, "none", "沉积加重，建议后续养护清理。"),
]


def request_json(api_base: str, path: str, method: str = "GET", payload: dict | None = None) -> dict | list:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        f"{api_base}{path}",
        data=data,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method=method,
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def post_json(api_base: str, path: str, payload: dict) -> dict:
    return request_json(api_base, path, method="POST", payload=payload)


def route_point(distance_m: float) -> tuple[float, float]:
    return (
        round(distance_m, 2),
        round(math.sin(distance_m / 4.0) * 0.32, 2),
    )


def build_status(
    *,
    command_status: dict,
    distance_m: float,
    event: PipeEvent | None,
    battery_percent: int,
) -> dict:
    x, y = route_point(distance_m)
    command = command_status.get("last_command") or "stop"
    speed = float(command_status.get("speed") or 0.0)
    obstacle = event is not None and event.severity in {"warning", "critical"}

    return {
        "connected": True,
        "mode": "manual" if command in {"forward", "backward", "left", "right"} else "ready",
        "speed": 0.0 if command == "stop" else speed,
        "battery_percent": battery_percent,
        "distance_m": round(distance_m, 2),
        "last_command": command,
        "error_code": 0,
        "message": f"route=R-A, point=({x},{y})",
        "temperature_c": round(34.0 + distance_m * 0.08, 1),
        "pitch_deg": round(math.sin(distance_m / 3.5) * 2.0, 1),
        "roll_deg": round(math.cos(distance_m / 4.2) * 1.5, 1),
        "obstacle_detected": obstacle,
        "obstacle_distance_m": 0.45 if event and event.severity == "critical" else (1.1 if obstacle else None),
        "obstacle_severity": event.severity if obstacle and event else "none",
        "obstacle_message": event.description if obstacle and event else "",
    }


def build_inspection_payload(run_id: str, event: PipeEvent, status: dict) -> dict:
    defect_distance = round((event.start_m + event.end_m) / 2, 2)
    x, y = route_point(defect_distance)
    return {
        "pipe_id": run_id,
        "pipe_length": 30,
        "diameter_mm": 800,
        "region_type": "traffic",
        "soil_type": "medium",
        "location": f"route R-A / x={x}, y={y}",
        "remark": (
            f"embedded simulator event; speed={status['speed']}m/s; "
            f"range={event.start_m}-{event.end_m}m"
        ),
        "defects": [
            {
                "category": event.category,
                "code": event.code,
                "score": event.score,
                "length": event.length,
                "distance_m": defect_distance,
                "description": event.description,
            }
        ],
    }


def next_detected_event(previous_distance: float, current_distance: float, reported: set[int]) -> tuple[int, PipeEvent] | None:
    for index, event in enumerate(PIPE_EVENTS):
        if index in reported:
            continue
        trigger_start = max(0.0, event.start_m - SENSOR_LOOKAHEAD_M)
        trigger_end = event.end_m
        if previous_distance <= trigger_end and current_distance >= trigger_start:
            return index, event
    return None


def run(api_base: str, interval: float, duration: float) -> None:
    run_id = f"SIM-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    print(f"Embedded simulator started: run_id={run_id}, api={api_base}")
    print("Use the web console controls. Sensor defects are saved only when pipe events are reached.")

    distance_m = 0.0
    battery_percent = 92
    reported_events: set[int] = set()
    active_event: PipeEvent | None = None
    active_event_until = 0.0
    last_tick = time.monotonic()
    started_at = last_tick

    while True:
        now = time.monotonic()
        elapsed = min(now - last_tick, interval * 2)
        last_tick = now

        command_status = request_json(api_base, "/api/robot/status")
        command = command_status.get("last_command") or "stop"
        speed = float(command_status.get("speed") or 0.0)
        platform_distance = float(command_status.get("distance_m") or 0.0)

        if platform_distance <= 0.01 and command == "stop" and distance_m > 0.01:
            distance_m = 0.0
            reported_events.clear()
            active_event = None
            active_event_until = 0.0
            print("platform reset detected; simulator distance and sensor events cleared")

        if command == "stop":
            speed = 0.0
        previous_distance = distance_m
        if command == "forward":
            distance_m += speed * elapsed
        elif command == "backward":
            distance_m = max(0.0, distance_m - speed * elapsed)

        detected = next_detected_event(previous_distance, distance_m, reported_events)
        if detected:
            index, active_event = detected
            reported_events.add(index)
            active_event_until = now + 5.0
            if active_event.severity in {"warning", "critical"}:
                command_status = {
                    **command_status,
                    "last_command": "stop",
                    "speed": 0.0,
                }
                command = "stop"
                speed = 0.0

        if active_event is not None and distance_m > active_event.end_m + 1.0 and now > active_event_until:
            active_event = None

        battery_percent = max(28, int(92 - distance_m * 0.35))
        status = build_status(
            command_status=command_status,
            distance_m=distance_m,
            event=active_event,
            battery_percent=battery_percent,
        )
        saved_status = post_json(api_base, "/api/robot/status", status)

        if detected:
            _, event = detected
            report = post_json(api_base, "/api/inspection/report", build_inspection_payload(run_id, event, saved_status))
            print(
                f"event detected_at={distance_m:.2f}m range={event.start_m:.2f}-{event.end_m:.2f}m severity={event.severity} "
                f"code={event.code} inspection_id={report['inspection_id']}"
            )
        else:
            print(
                f"telemetry command={command:<8} speed={saved_status['speed']:.2f} "
                f"distance={saved_status['distance_m']:.2f}m obstacle={saved_status['obstacle_severity']}"
            )

        if duration > 0 and now - started_at >= duration:
            break
        time.sleep(interval)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the PipeScan embedded robot simulator.")
    parser.add_argument("--api-base", default=DEFAULT_API_BASE)
    parser.add_argument("--interval", type=float, default=0.5)
    parser.add_argument("--duration", type=float, default=0.0, help="Seconds to run; 0 means run forever.")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    try:
        run(args.api_base.rstrip("/"), args.interval, args.duration)
    except urllib.error.URLError as exc:
        raise SystemExit(f"API request failed: {exc}") from exc
