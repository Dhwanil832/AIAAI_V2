from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import get_db
from core.dependencies import get_current_user
from models.user import User
from models.unfinished import UnfinishedReport
import json

router = APIRouter()


@router.get("/")
async def list_unfinished(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List all unfinished reports for the current user."""
    reports = (
        db.query(UnfinishedReport)
        .filter(UnfinishedReport.user_id == current_user.id)
        .order_by(UnfinishedReport.updated_at.desc())
        .all()
    )
    return {"unfinished": [serialize_unfinished(r) for r in reports]}


@router.delete("/{unfinished_id}")
async def discard_unfinished(
    unfinished_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Discard an unfinished report."""
    report = db.query(UnfinishedReport).filter(
        UnfinishedReport.id == unfinished_id,
        UnfinishedReport.user_id == current_user.id
    ).first()

    if not report:
        raise HTTPException(status_code=404, detail="Unfinished report not found")

    db.delete(report)
    db.commit()

    return {"message": f"Unfinished report #{unfinished_id} discarded"}


def serialize_unfinished(report: UnfinishedReport) -> dict:
    report_json = report.report_json
    if isinstance(report_json, str):
        report_json = json.loads(report_json)

    basic_info = report_json.get("basic_info", {}) if report_json else {}

    return {
        "id": report.id,
        "session_id": report.session_id,
        "incident_type": basic_info.get("incident_type", ""),
        "location": basic_info.get("location", ""),
        "datetime": basic_info.get("datetime", ""),
        "person_involved": basic_info.get("person_involved", ""),
        "updated_at": report.updated_at.isoformat() if report.updated_at else None,
        "created_at": report.created_at.isoformat() if report.created_at else None,
        "report_json": report_json
    }