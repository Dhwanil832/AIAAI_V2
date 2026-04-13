from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from database import get_db
from core.dependencies import get_current_user, get_current_admin
from models.user import User
from models.report import IncidentReport
from agents.notifier import notify_reporter_needs_info
from datetime import datetime
import json

router = APIRouter()

VALID_STATUSES = ["submitted", "under_review", "approved", "needs_more_info", "closed"]


class ReviewRequest(BaseModel):
    status: str
    review_note: Optional[str] = None


@router.get("/")
async def list_reports(
    skip: int = 0,
    limit: int = 20,
    incident_type: Optional[str] = None,
    flagged: Optional[bool] = None,
    status: Optional[str] = None,
    search: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List reports. Admins see all, regular users see only their own."""
    query = db.query(IncidentReport)

    if current_user.role != "admin":
        query = query.filter(IncidentReport.user_id == current_user.id)

    if flagged is not None:
        query = query.filter(IncidentReport.flagged == flagged)

    if status:
        query = query.filter(IncidentReport.status == status)

    all_reports = query.order_by(IncidentReport.created_at.desc()).all()

    # Python-side filters — avoids .astext SQLite/PostgreSQL JSON incompatibility
    if incident_type:
        filtered = []
        for r in all_reports:
            rj = r.report_json if isinstance(r.report_json, dict) else json.loads(r.report_json)
            if rj.get("basic_info", {}).get("incident_type", "") == incident_type:
                filtered.append(r)
        all_reports = filtered

    if search:
        keyword = search.strip().lower()
        searched = []
        for r in all_reports:
            rj = r.report_json if isinstance(r.report_json, dict) else json.loads(r.report_json)
            basic = rj.get("basic_info", {})
            # Search across person, location, actions taken, creator name, and report id
            haystack = " ".join(str(v) for v in [
                basic.get("person_involved", ""),
                basic.get("location", ""),
                basic.get("actions_taken", ""),
                r.creator_name or "",
                str(r.id),
            ]).lower()
            if keyword in haystack:
                searched.append(r)
        all_reports = searched

    total = len(all_reports)
    paginated = all_reports[skip: skip + limit]

    return {
        "total": total,
        "reports": [serialize_report(r) for r in paginated]
    }


@router.get("/flagged")
async def list_flagged_reports(
    skip: int = 0,
    limit: int = 20,
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Admin only — list all flagged reports."""
    reports = (
        db.query(IncidentReport)
        .filter(IncidentReport.flagged == True)
        .order_by(IncidentReport.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return {"reports": [serialize_report(r) for r in reports]}


@router.get("/{report_id}")
async def get_report(
    report_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get a single report by ID."""
    report = db.query(IncidentReport).filter(IncidentReport.id == report_id).first()

    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    if current_user.role != "admin" and report.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")

    return serialize_report(report, include_context=True)


@router.patch("/{report_id}/flag")
async def toggle_flag(
    report_id: int,
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Admin only — manually flag or unflag a report."""
    report = db.query(IncidentReport).filter(IncidentReport.id == report_id).first()

    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    report.flagged = not report.flagged
    report.flag_reason = None if not report.flagged else "Manually flagged by admin"

    db.commit()
    db.refresh(report)

    return {"id": report.id, "flagged": report.flagged, "flag_reason": report.flag_reason}


@router.patch("/{report_id}/review")
async def review_report(
    report_id: int,
    request: ReviewRequest,
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """
    Admin only — update report review status.
    Valid statuses: submitted, under_review, approved, needs_more_info, closed
    """
    if request.status not in VALID_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status. Must be one of: {VALID_STATUSES}"
        )

    report = db.query(IncidentReport).filter(IncidentReport.id == report_id).first()

    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    report.status = request.status
    report.review_note = request.review_note
    report.reviewed_by = current_user.username
    report.reviewed_at = datetime.utcnow()

    db.commit()
    db.refresh(report)

    # Notify reporter when admin requests more information
    if request.status == "needs_more_info" and report.user_id:
        notify_reporter_needs_info(
            report_id=report.id,
            reporter_user_id=report.user_id,
            review_note=request.review_note or "",
            db=db
        )

    print(f"[reports] report #{report_id} status → {request.status} by {current_user.username}")

    return serialize_report(report)


@router.patch("/{report_id}/edit")
async def edit_report(
    report_id: int,
    updates: dict,
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Admin only — edit a report's JSON fields."""
    report = db.query(IncidentReport).filter(IncidentReport.id == report_id).first()

    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    current = report.report_json if isinstance(report.report_json, dict) else json.loads(report.report_json)

    for section, fields in updates.items():
        if section in current and isinstance(fields, dict):
            current[section].update(fields)

    report.report_json = current
    report.last_modified_name = current_user.username
    report.last_modified_job = current_user.job_title or ""

    db.commit()
    db.refresh(report)

    return serialize_report(report)


@router.delete("/{report_id}")
async def delete_report(
    report_id: int,
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Admin only — delete a report."""
    report = db.query(IncidentReport).filter(IncidentReport.id == report_id).first()

    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    db.delete(report)
    db.commit()

    return {"message": f"Report #{report_id} deleted"}


def serialize_report(report: IncidentReport, include_context: bool = False) -> dict:
    report_json = report.report_json
    if isinstance(report_json, str):
        report_json = json.loads(report_json)

    basic_info = report_json.get("basic_info", {}) if report_json else {}

    data = {
        "id": report.id,
        "user_id": report.user_id,
        "creator_name": report.creator_name,
        "creator_job_title": report.creator_job_title,
        "incident_type": basic_info.get("incident_type", ""),
        "datetime": basic_info.get("datetime", ""),
        "location": basic_info.get("location", ""),
        "severity": basic_info.get("severity", ""),
        "flagged": report.flagged,
        "flag_reason": report.flag_reason,
        "status": report.status or "submitted",
        "review_note": report.review_note,
        "reviewed_by": report.reviewed_by,
        "reviewed_at": report.reviewed_at.isoformat() if report.reviewed_at else None,
        "similar_incidents": report.similar_incidents,
        "created_at": report.created_at.isoformat() if report.created_at else None,
        "last_modified_at": report.last_modified_at.isoformat() if report.last_modified_at else None,
        "report_json": report_json,
    }

    if include_context and report.context_document:
        context = report.context_document
        if isinstance(context, str):
            context = json.loads(context)
        data["context_document"] = context

    return data