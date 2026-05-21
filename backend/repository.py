# -*- coding: utf-8 -*-
"""Database persistence helpers."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from models import InspectionRecord, InspectionReport, PipeSegment


def upsert_pipe_segment(
    db: Session,
    *,
    pipe_code: str,
    length_m: float,
    diameter_mm: float,
    region_type: str,
    soil_type: str,
    location: str = "",
    remark: str = "",
) -> PipeSegment:
    pipe = db.scalar(select(PipeSegment).where(PipeSegment.pipe_code == pipe_code))
    if pipe is None:
        pipe = PipeSegment(pipe_code=pipe_code)
        db.add(pipe)

    pipe.length_m = length_m
    pipe.diameter_mm = diameter_mm
    pipe.region_type = region_type
    pipe.soil_type = soil_type
    pipe.location = location
    pipe.remark = remark
    db.commit()
    db.refresh(pipe)
    return pipe


def save_inspection_report(
    db: Session,
    *,
    pipe: PipeSegment,
    inspection: InspectionRecord,
    evaluation: dict,
    markdown: str,
    report_path: str,
) -> InspectionReport:
    report = InspectionReport(
        pipe_id=pipe.id,
        inspection_id=inspection.id,
        evaluation=evaluation,
        markdown=markdown,
        report_path=report_path,
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    return report


def save_inspection_record(
    db: Session,
    *,
    pipe: PipeSegment,
    input_data: dict,
    defects: list[dict],
) -> InspectionRecord:
    inspection = InspectionRecord(
        pipe_id=pipe.id,
        input_data=input_data,
        defects=defects,
    )
    db.add(inspection)
    db.commit()
    db.refresh(inspection)
    return inspection


def list_pipe_segments(db: Session) -> list[PipeSegment]:
    return list(db.scalars(select(PipeSegment).order_by(PipeSegment.created_at.desc())))


def list_reports(db: Session, limit: int = 50) -> list[InspectionReport]:
    stmt = select(InspectionReport).order_by(InspectionReport.created_at.desc()).limit(limit)
    return list(db.scalars(stmt))


def get_report(db: Session, report_id: int) -> InspectionReport | None:
    return db.get(InspectionReport, report_id)


def list_inspection_records(db: Session, limit: int = 50) -> list[InspectionRecord]:
    stmt = select(InspectionRecord).order_by(InspectionRecord.created_at.desc()).limit(limit)
    return list(db.scalars(stmt))


def get_inspection_record(db: Session, inspection_id: int) -> InspectionRecord | None:
    return db.get(InspectionRecord, inspection_id)
