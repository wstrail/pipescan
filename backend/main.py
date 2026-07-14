# -*- coding: utf-8 -*-
"""FastAPI service for the pipe inspection robot platform."""

from datetime import datetime
from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from database import get_db, init_db, ping_db
from evaluator import Defect, PipeDefectEvaluator
from repository import (
    get_inspection_record,
    get_report,
    list_inspection_records,
    list_pipe_segments,
    list_reports,
    save_inspection_record,
    save_inspection_report,
    upsert_pipe_segment,
)
from reportgenerator import ReportGenerator


class MotionCommand(BaseModel):
    action: Literal["forward", "backward", "left", "right", "stop", "set_speed"]
    speed: float = Field(default=0.0, ge=0, le=1)
    duration_ms: int = Field(default=0, ge=0, le=60000)


class RobotStatusPayload(BaseModel):
    connected: bool | None = None
    mode: str | None = None
    speed: float | None = Field(default=None, ge=0, le=1)
    battery_percent: int | None = Field(default=None, ge=0, le=100)
    distance_m: float | None = Field(default=None, ge=0)
    last_command: str | None = None
    error_code: int | None = Field(default=None, ge=0)
    message: str | None = None
    temperature_c: float | None = None
    pitch_deg: float | None = None
    roll_deg: float | None = None
    obstacle_detected: bool | None = None
    obstacle_distance_m: float | None = Field(default=None, ge=0)
    obstacle_severity: Literal["none", "warning", "critical"] | None = None
    obstacle_message: str | None = None


class CameraConfig(BaseModel):
    source: str = "mock://camera-0"
    enabled: bool = True
    resolution: str = "1280x720"


class DefectPayload(BaseModel):
    category: Literal["structural", "functional"]
    code: str
    score: float = Field(ge=0, le=10)
    length: float = Field(default=0.0, ge=0)
    distance_m: float = Field(default=0.0, ge=0)
    description: str = ""


class InspectionPayload(BaseModel):
    pipe_id: str = "P-001"
    pipe_length: float = Field(default=30, gt=0)
    diameter_mm: float = Field(default=800, gt=0)
    region_type: Literal["central", "traffic", "normal", "other"] = "normal"
    soil_type: Literal["weak", "medium", "strong", "unknown"] = "unknown"
    location: str = ""
    remark: str = ""
    defects: list[DefectPayload] = Field(default_factory=list)


class PipeSegmentPayload(BaseModel):
    pipe_code: str = Field(min_length=1, max_length=80)
    length_m: float = Field(gt=0)
    diameter_mm: float = Field(gt=0)
    region_type: Literal["central", "traffic", "normal", "other"] = "normal"
    soil_type: Literal["weak", "medium", "strong", "unknown"] = "unknown"
    location: str = ""
    remark: str = ""


class RobotState(BaseModel):
    connected: bool = False
    mode: str = "standby"
    speed: float = 0.0
    battery_percent: int = 86
    distance_m: float = 0.0
    last_command: str = "stop"
    error_code: int = 0
    message: str = ""
    temperature_c: float | None = None
    pitch_deg: float | None = None
    roll_deg: float | None = None
    obstacle_detected: bool = False
    obstacle_distance_m: float | None = None
    obstacle_severity: Literal["none", "warning", "critical"] = "none"
    obstacle_message: str = ""
    updated_at: str


class MotionController:
    """Hardware adapter placeholder.

    Replace send_command with serial/CAN/TCP calls when the embedded controller
    protocol is ready.
    """

    def __init__(self) -> None:
        self.state = RobotState(updated_at=datetime.now().isoformat(timespec="seconds"))
        self.last_motion_at = datetime.now()
        self.last_external_status_at: datetime | None = None

    def reset(self) -> RobotState:
        self.state = RobotState(
            connected=True,
            mode="ready",
            speed=0.0,
            distance_m=0.0,
            last_command="stop",
            updated_at=datetime.now().isoformat(timespec="seconds"),
        )
        self.last_motion_at = datetime.now()
        self.last_external_status_at = None
        return self.state

    def _advance_motion(self) -> None:
        now = datetime.now()
        has_recent_external_status = (
            self.last_external_status_at is not None
            and (now - self.last_external_status_at).total_seconds() < 2.0
        )
        if has_recent_external_status:
            self.last_motion_at = now
            return

        elapsed = max(0.0, (now - self.last_motion_at).total_seconds())
        if self.state.last_command == "forward":
            self.state.distance_m = round(self.state.distance_m + self.state.speed * elapsed, 2)
        elif self.state.last_command == "backward":
            self.state.distance_m = max(0.0, round(self.state.distance_m - self.state.speed * elapsed, 2))
        self.last_motion_at = now

    def current_state(self) -> RobotState:
        self._advance_motion()
        self.state.updated_at = datetime.now().isoformat(timespec="seconds")
        return self.state

    def connect(self) -> RobotState:
        self._advance_motion()
        self.state.connected = True
        self.state.mode = "ready"
        self.state.updated_at = datetime.now().isoformat(timespec="seconds")
        return self.state

    def send_command(self, command: MotionCommand) -> RobotState:
        self._advance_motion()
        self.state.connected = True
        if command.action == "set_speed":
            self.state.speed = command.speed
            self.state.mode = "manual" if self.state.last_command in {"forward", "backward", "left", "right"} else self.state.mode
            self.state.updated_at = datetime.now().isoformat(timespec="seconds")
            return self.state

        self.state.last_command = command.action
        self.state.speed = 0 if command.action == "stop" else command.speed
        self.state.mode = "stopped" if command.action == "stop" else "manual"
        self.state.updated_at = datetime.now().isoformat(timespec="seconds")
        return self.state

    def update_status(self, payload: RobotStatusPayload) -> RobotState:
        data = payload.model_dump(exclude_unset=True)
        for key, value in data.items():
            if value is not None:
                setattr(self.state, key, value)
        self.state.connected = data.get("connected", True)
        self.last_motion_at = datetime.now()
        self.last_external_status_at = self.last_motion_at
        self.state.updated_at = datetime.now().isoformat(timespec="seconds")
        return self.state


class CameraAdapter:
    """Camera interface placeholder for USB/RTSP/vendor SDK integration."""

    def __init__(self) -> None:
        self.config = CameraConfig()

    def update(self, config: CameraConfig) -> CameraConfig:
        self.config = config
        return self.config

    def snapshot(self) -> dict[str, str | bool]:
        return {
            "enabled": self.config.enabled,
            "source": self.config.source,
            "resolution": self.config.resolution,
            "frame_url": "/api/camera/mock-frame",
            "captured_at": datetime.now().isoformat(timespec="seconds"),
        }


app = FastAPI(title="PipeScan Robot API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

motion = MotionController()
camera = CameraAdapter()
evaluator = PipeDefectEvaluator()
report_generator = ReportGenerator()
database_ready = False
database_message = "database not initialized"


@app.on_event("startup")
def startup() -> None:
    global database_ready, database_message
    database_ready, database_message = init_db()


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "time": datetime.now().isoformat(timespec="seconds")}


@app.get("/api/db/health")
def db_health() -> dict[str, str | bool]:
    ok, message = ping_db()
    return {"connected": ok, "message": message}


@app.post("/api/robot/connect", response_model=RobotState)
def connect_robot() -> RobotState:
    return motion.connect()


@app.post("/api/robot/reset", response_model=RobotState)
def reset_robot() -> RobotState:
    return motion.reset()


@app.get("/api/robot/status", response_model=RobotState)
def robot_status() -> RobotState:
    return motion.current_state()


@app.post("/api/robot/status", response_model=RobotState)
def update_robot_status(status: RobotStatusPayload) -> RobotState:
    return motion.update_status(status)


@app.post("/api/robot/motion", response_model=RobotState)
def robot_motion(command: MotionCommand) -> RobotState:
    return motion.send_command(command)


@app.get("/api/camera")
def camera_status() -> CameraConfig:
    return camera.config


@app.post("/api/camera")
def configure_camera(config: CameraConfig) -> CameraConfig:
    return camera.update(config)


@app.get("/api/camera/snapshot")
def camera_snapshot() -> dict[str, str | bool]:
    return camera.snapshot()


@app.post("/api/inspection/evaluate")
def evaluate_inspection(payload: InspectionPayload) -> dict:
    defects = [Defect(**item.model_dump()) for item in payload.defects]
    return evaluator.evaluate(
        pipe_id=payload.pipe_id,
        pipe_length=payload.pipe_length,
        diameter_mm=payload.diameter_mm,
        region_type=payload.region_type,
        soil_type=payload.soil_type,
        defects=defects,
    )


@app.post("/api/inspection/report")
def create_report(payload: InspectionPayload, db: Session = Depends(get_db)) -> dict[str, str | int | None | dict]:
    evaluation = evaluate_inspection(payload)
    path = report_generator.save_markdown(evaluation, Path(__file__).parent / "reports")
    markdown = report_generator.generate_markdown(evaluation)

    try:
        pipe = upsert_pipe_segment(
            db,
            pipe_code=payload.pipe_id,
            length_m=payload.pipe_length,
            diameter_mm=payload.diameter_mm,
            region_type=payload.region_type,
            soil_type=payload.soil_type,
            location=payload.location,
            remark=payload.remark,
        )
        inspection = save_inspection_record(
            db,
            pipe=pipe,
            input_data=payload.model_dump(),
            defects=[item.model_dump() for item in payload.defects],
        )
        report = save_inspection_report(
            db,
            pipe=pipe,
            inspection=inspection,
            evaluation=evaluation,
            markdown=markdown,
            report_path=str(path),
        )
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=503, detail=f"Database unavailable or save failed: {exc}") from exc

    return {
        "inspection_id": inspection.id,
        "report_id": report.id,
        "report_path": str(path),
        "markdown": markdown,
        "evaluation": evaluation,
    }


@app.post("/api/pipes")
def create_or_update_pipe(payload: PipeSegmentPayload, db: Session = Depends(get_db)) -> dict:
    try:
        pipe = upsert_pipe_segment(db, **payload.model_dump())
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=503, detail=f"Database unavailable or save failed: {exc}") from exc

    return {
        "id": pipe.id,
        "pipe_code": pipe.pipe_code,
        "length_m": pipe.length_m,
        "diameter_mm": pipe.diameter_mm,
        "region_type": pipe.region_type,
        "soil_type": pipe.soil_type,
        "location": pipe.location,
        "remark": pipe.remark,
    }


@app.get("/api/pipes")
def get_pipes(db: Session = Depends(get_db)) -> list[dict]:
    try:
        pipes = list_pipe_segments(db)
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail=f"Database unavailable: {exc}") from exc

    return [
        {
            "id": pipe.id,
            "pipe_code": pipe.pipe_code,
            "length_m": pipe.length_m,
            "diameter_mm": pipe.diameter_mm,
            "region_type": pipe.region_type,
            "soil_type": pipe.soil_type,
            "location": pipe.location,
            "remark": pipe.remark,
            "created_at": pipe.created_at.isoformat(),
        }
        for pipe in pipes
    ]


@app.get("/api/inspection/reports")
def get_reports(limit: int = 50, db: Session = Depends(get_db)) -> list[dict]:
    try:
        reports = list_reports(db, limit=limit)
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail=f"Database unavailable: {exc}") from exc

    return [
        {
            "id": report.id,
            "inspection_id": report.inspection_id,
            "pipe_id": report.pipe_id,
            "pipe_code": report.pipe.pipe_code if report.pipe else "",
            "report_path": report.report_path,
            "created_at": report.created_at.isoformat(),
            "repair_level": report.evaluation.get("levels", {}).get("repair_level", {}),
            "maintenance_level": report.evaluation.get("levels", {}).get("maintenance_level", {}),
        }
        for report in reports
    ]


@app.get("/api/inspection/reports/{report_id}")
def get_report_detail(report_id: int, db: Session = Depends(get_db)) -> dict:
    try:
        report = get_report(db, report_id)
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail=f"Database unavailable: {exc}") from exc

    if report is None:
        raise HTTPException(status_code=404, detail="Report not found")

    return {
        "id": report.id,
        "inspection_id": report.inspection_id,
        "pipe_id": report.pipe_id,
        "pipe_code": report.pipe.pipe_code if report.pipe else "",
        "input_data": report.inspection.input_data if report.inspection else {},
        "defects": report.inspection.defects if report.inspection else [],
        "evaluation": report.evaluation,
        "markdown": report.markdown,
        "report_path": report.report_path,
        "created_at": report.created_at.isoformat(),
    }


@app.get("/api/inspection/records")
def get_inspection_records(limit: int = 50, db: Session = Depends(get_db)) -> list[dict]:
    try:
        records = list_inspection_records(db, limit=limit)
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail=f"Database unavailable: {exc}") from exc

    return [
        {
            "id": record.id,
            "pipe_id": record.pipe_id,
            "pipe_code": record.pipe.pipe_code if record.pipe else "",
            "input_data": record.input_data,
            "defects": record.defects,
            "created_at": record.created_at.isoformat(),
            "report_id": record.report.id if record.report else None,
        }
        for record in records
    ]


@app.get("/api/inspection/records/{inspection_id}")
def get_inspection_record_detail(inspection_id: int, db: Session = Depends(get_db)) -> dict:
    try:
        record = get_inspection_record(db, inspection_id)
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail=f"Database unavailable: {exc}") from exc

    if record is None:
        raise HTTPException(status_code=404, detail="Inspection record not found")

    return {
        "id": record.id,
        "pipe_id": record.pipe_id,
        "pipe_code": record.pipe.pipe_code if record.pipe else "",
        "input_data": record.input_data,
        "defects": record.defects,
        "created_at": record.created_at.isoformat(),
        "report_id": record.report.id if record.report else None,
    }
