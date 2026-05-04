from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from database import get_db
from core.dependencies import get_current_user, get_current_admin
from models.user import User
from models.report import IncidentReport
from models.vision import VisionThread
from agents.notifier import notify_reporter_needs_info, notify_witness_nominated
from agents.witness import generate_incident_summary
from core.ollama import generate_safety_briefing
from datetime import datetime, timedelta
import json
import copy
import csv
import io


router = APIRouter()

VALID_STATUSES = ["submitted", "under_review", "approved", "needs_more_info", "closed"]


class ReviewRequest(BaseModel):
    status: str
    review_note: Optional[str] = None


class NominateWitnessRequest(BaseModel):
    username: str


class WitnessAccountRequest(BaseModel):
    account: str


# ══════════════════════════════════════════════════════════════════════════════
# EXISTING ENDPOINTS — UNCHANGED
# ══════════════════════════════════════════════════════════════════════════════

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

    # Pre-fetch vision thread statuses — single query, no N+1
    report_ids = [r.id for r in paginated]
    vision_threads = db.query(VisionThread).filter(
        VisionThread.report_id.in_(report_ids)
    ).all() if report_ids else []
    vision_status_map = {vt.report_id: vt.status for vt in vision_threads}

    return {
        "total": total,
        "reports": [
            serialize_report(r, vision_thread_status=vision_status_map.get(r.id))
            for r in paginated
        ]
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


@router.get("/witness-pending")
async def list_pending_witness_requests(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Returns all reports where the current user has a pending witness nomination.
    Used by DashboardPage to show the Pending Witness Requests section.
    """
    all_reports = db.query(IncidentReport).filter(
        IncidentReport.witness_nominations != None
    ).all()

    pending = []
    for report in all_reports:
        nominations = report.witness_nominations or []
        for nom in nominations:
            if nom.get("username") == current_user.username and nom.get("status") == "pending":
                rj = report.report_json if isinstance(report.report_json, dict) else json.loads(report.report_json)
                basic = rj.get("basic_info", {})
                pending.append({
                    "report_id": report.id,
                    "person_involved": basic.get("person_involved", ""),
                    "location": basic.get("location", ""),
                    "datetime": basic.get("datetime", ""),
                    "incident_type": basic.get("incident_type", ""),
                    "nominated_at": nom.get("nominated_at", ""),
                })
                break

    return {"pending": pending}


@router.get("/witness-submissions")
async def list_witness_submissions(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Returns all reports where the current user has submitted a witness account.
    Used by DashboardPage to show the Witness Submissions section.
    """
    all_reports = db.query(IncidentReport).filter(
        IncidentReport.witness_nominations != None
    ).all()

    submissions = []
    for report in all_reports:
        nominations = report.witness_nominations or []
        for nom in nominations:
            if nom.get("username") == current_user.username and nom.get("status") == "submitted":
                rj = report.report_json if isinstance(report.report_json, dict) else json.loads(report.report_json)
                basic = rj.get("basic_info", {})
                submissions.append({
                    "report_id": report.id,
                    "person_involved": basic.get("person_involved", ""),
                    "location": basic.get("location", ""),
                    "datetime": basic.get("datetime", ""),
                    "incident_type": basic.get("incident_type", ""),
                    "submitted_at": nom.get("submitted_at", ""),
                })
                break

    return {"submissions": submissions}


# ══════════════════════════════════════════════════════════════════════════════
# EXPORT ENDPOINT — must be before /{report_id} to avoid path conflict
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/export")
async def export_reports(
    format: str = "json",
    date_range: Optional[str] = None,
    incident_type: Optional[str] = None,
    location: Optional[str] = None,
    flagged: Optional[bool] = None,
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """
    Admin only — export all reports matching filters as JSON or CSV.

    date_range options: 30d, 3m, 6m, 1y, all (default: all)
    format options: json, csv (default: json)
    """
    query = db.query(IncidentReport)

    # Date range filter
    if date_range and date_range != "all":
        now = datetime.utcnow()
        if date_range == "30d":
            cutoff = now - timedelta(days=30)
        elif date_range == "3m":
            cutoff = now - timedelta(days=90)
        elif date_range == "6m":
            cutoff = now - timedelta(days=180)
        elif date_range == "1y":
            cutoff = now - timedelta(days=365)
        else:
            cutoff = None
        if cutoff:
            query = query.filter(IncidentReport.created_at >= cutoff)

    # Flagged filter
    if flagged is not None:
        query = query.filter(IncidentReport.flagged == flagged)

    all_reports = query.order_by(IncidentReport.created_at.desc()).all()

    # Python-side filters for incident_type and location (JSON field)
    if incident_type:
        all_reports = [
            r for r in all_reports
            if (r.report_json if isinstance(r.report_json, dict) else json.loads(r.report_json))
               .get("basic_info", {}).get("incident_type", "") == incident_type
        ]

    if location:
        loc_lower = location.strip().lower()
        all_reports = [
            r for r in all_reports
            if loc_lower in (
                (r.report_json if isinstance(r.report_json, dict) else json.loads(r.report_json))
                .get("basic_info", {}).get("location", "").lower()
            )
        ]

    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")

    # ── JSON export ───────────────────────────────────────────────────────────
    if format == "json":
        export_data = []
        for r in all_reports:
            rj = r.report_json if isinstance(r.report_json, dict) else json.loads(r.report_json)
            ctx = r.context_document or {}
            if isinstance(ctx, str):
                ctx = json.loads(ctx)
            export_data.append({
                "id": r.id,
                "creator_name": r.creator_name,
                "creator_job_title": r.creator_job_title,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "status": r.status,
                "flagged": r.flagged,
                "flag_reason": r.flag_reason,
                "reviewed_by": r.reviewed_by,
                "reviewed_at": r.reviewed_at.isoformat() if r.reviewed_at else None,
                "review_note": r.review_note,
                "report_json": rj,
                "witness_nominations": r.witness_nominations or [],
                "similar_incidents": r.similar_incidents or [],
                "ai_summary": ctx.get("ai_summary"),
                "safety_briefing": ctx.get("safety_briefing"),
                "witness_accounts": ctx.get("witness_accounts", []),
                "chat_history": ctx.get("chat_history", []),
            })

        json_bytes = json.dumps(export_data, indent=2, ensure_ascii=False).encode("utf-8")
        filename = f"incident_reports_{timestamp}.json"
        return StreamingResponse(
            io.BytesIO(json_bytes),
            media_type="application/json",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )

    # ── CSV export ────────────────────────────────────────────────────────────
    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow([
        "Report ID", "Creator", "Job Title", "Created At", "Status",
        "Flagged", "Flag Reason", "Reviewed By", "Review Note",
        "Incident Type", "Date/Time", "Shift", "Location",
        "Person Involved", "Person Type", "Severity", "Actions Taken",
        "Accident Type", "Accident Agent", "Injury Type", "Injury Agent", "SIF Case",
        "Life Saving Rules",
        "Damage Amount", "Activity Type", "Incident Activity", "Incident Agent",
        "Witness Accounts", "AI Summary", "Safety Briefing",
    ])

    for r in all_reports:
        rj = r.report_json if isinstance(r.report_json, dict) else json.loads(r.report_json)
        ctx = r.context_document or {}
        if isinstance(ctx, str):
            ctx = json.loads(ctx)

        basic = rj.get("basic_info", {})
        injury = rj.get("injury_data", {})
        near_miss = rj.get("near_miss_data", {})
        equipment = rj.get("equipment_damage_data", {})

        witness_accounts = ctx.get("witness_accounts", [])
        witness_text = " | ".join(
            f"{wa.get('username', '?')}: {wa.get('account', '').strip()}"
            for wa in witness_accounts
        )

        writer.writerow([
            r.id, r.creator_name, r.creator_job_title,
            r.created_at.isoformat() if r.created_at else "",
            r.status, r.flagged, r.flag_reason or "",
            r.reviewed_by or "", r.review_note or "",
            basic.get("incident_type", ""), basic.get("datetime", ""),
            basic.get("shift", ""), basic.get("location", ""),
            basic.get("person_involved", ""), basic.get("person_type", ""),
            basic.get("severity", ""), basic.get("actions_taken", ""),
            injury.get("accident_type", ""), injury.get("accident_agent", ""),
            injury.get("injury_type", ""), injury.get("injury_agent", ""),
            injury.get("sif_case", "") or near_miss.get("sif_case", "") or equipment.get("sif_case", ""),
            near_miss.get("life_saving_rules", ""),
            equipment.get("damage_amount", ""), equipment.get("activity_type", ""),
            equipment.get("incident_activity", ""), equipment.get("incident_agent", ""),
            witness_text, ctx.get("ai_summary", ""), ctx.get("safety_briefing", ""),
        ])

    csv_bytes = output.getvalue().encode("utf-8")
    filename = f"incident_reports_{timestamp}.csv"
    return StreamingResponse(
        io.BytesIO(csv_bytes),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


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


@router.get("/{report_id}/witness-view")
async def get_witness_view(
    report_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Returns only what a nominated witness is allowed to see:
    - Person involved, location, date (identification only)
    - Structured report fields
    - Their own submitted account (if already submitted)

    Blocked if the user is not a nominated witness for this report.
    """
    report = db.query(IncidentReport).filter(IncidentReport.id == report_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    nominations = report.witness_nominations or []
    my_nomination = next(
        (n for n in nominations if n.get("username") == current_user.username),
        None
    )

    if not my_nomination and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Access denied")

    rj = report.report_json if isinstance(report.report_json, dict) else json.loads(report.report_json)
    basic = rj.get("basic_info", {})

    # Only person/location/date for the prompt header
    identification = {
        "person_involved": basic.get("person_involved", ""),
        "location": basic.get("location", ""),
        "datetime": basic.get("datetime", ""),
    }

    # Structured fields — no chat history
    structured_fields = {
        "incident_type": basic.get("incident_type", ""),
        "shift": basic.get("shift", ""),
        "severity": basic.get("severity", ""),
        "actions_taken": basic.get("actions_taken", ""),
    }

    # Their own account if submitted
    my_account = None
    if my_nomination and my_nomination.get("status") == "submitted":
        ctx = report.context_document or {}
        if isinstance(ctx, str):
            ctx = json.loads(ctx)
        witness_accounts = ctx.get("witness_accounts", [])
        my_account = next(
            (wa.get("account") for wa in witness_accounts if wa.get("username") == current_user.username),
            None
        )

    return {
        "report_id": report.id,
        "identification": identification,
        "structured_fields": structured_fields,
        "my_nomination_status": my_nomination.get("status") if my_nomination else None,
        "my_account": my_account,
    }


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


# ══════════════════════════════════════════════════════════════════════════════
# WITNESS ENDPOINTS — NEW
# ══════════════════════════════════════════════════════════════════════════════

@router.post("/{report_id}/nominate-witness")
async def nominate_witness(
    report_id: int,
    request: NominateWitnessRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Nominate a user as a witness to this report.
    Allowed for: the original reporter or any admin.
    """
    report = db.query(IncidentReport).filter(IncidentReport.id == report_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    # Only reporter or admin can nominate
    if current_user.role != "admin" and report.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")

    # Validate the nominated username exists
    witness_user = db.query(User).filter(User.username == request.username).first()
    if not witness_user:
        raise HTTPException(status_code=404, detail=f"User '{request.username}' not found")

    # Cannot nominate yourself
    if witness_user.id == report.user_id:
        raise HTTPException(status_code=400, detail="Cannot nominate the report creator as a witness")

    # Check for duplicate nomination
    nominations = report.witness_nominations or []
    already_nominated = any(n.get("username") == request.username for n in nominations)
    if already_nominated:
        raise HTTPException(status_code=400, detail=f"'{request.username}' is already nominated")

    # Append nomination
    new_nomination = {
        "username": request.username,
        "status": "pending",
        "nominated_at": datetime.utcnow().isoformat(),
        "submitted_at": None,
    }
    nominations = list(nominations) + [new_nomination]
    report.witness_nominations = nominations

    db.commit()
    db.refresh(report)

    # Notify the witness
    rj = report.report_json if isinstance(report.report_json, dict) else json.loads(report.report_json)
    basic = rj.get("basic_info", {})
    notify_witness_nominated(
        report_id=report.id,
        witness_user_id=witness_user.id,
        person_involved=basic.get("person_involved", ""),
        location=basic.get("location", ""),
        datetime_str=basic.get("datetime", ""),
        db=db
    )

    print(f"[reports] witness '{request.username}' nominated for report #{report_id} by {current_user.username}")

    return {
        "report_id": report.id,
        "witness_nominations": report.witness_nominations
    }


@router.post("/{report_id}/witness-account")
async def submit_witness_account(
    report_id: int,
    request: WitnessAccountRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Submit a witness account for a report.
    Only callable by a user who has a pending nomination on this report.
    Appends the account to context_document.witness_accounts and
    auto-regenerates the AI summary.
    """
    report = db.query(IncidentReport).filter(IncidentReport.id == report_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    nominations = report.witness_nominations or []
    my_nomination = next(
        (n for n in nominations if n.get("username") == current_user.username),
        None
    )

    if not my_nomination:
        raise HTTPException(status_code=403, detail="You are not nominated as a witness for this report")

    if my_nomination.get("status") == "submitted":
        raise HTTPException(status_code=400, detail="You have already submitted your account")

    if not request.account or not request.account.strip():
        raise HTTPException(status_code=400, detail="Account text cannot be empty")

    # Update nomination status
    updated_nominations = []
    for n in nominations:
        if n.get("username") == current_user.username:
            n = dict(n)
            n["status"] = "submitted"
            n["submitted_at"] = datetime.utcnow().isoformat()
        updated_nominations.append(n)
    report.witness_nominations = updated_nominations

    # Append to context_document.witness_accounts
    ctx = report.context_document or {}
    if isinstance(ctx, str):
        ctx = json.loads(ctx)
    ctx = copy.deepcopy(ctx)

    witness_accounts = ctx.get("witness_accounts", [])
    witness_accounts.append({
        "username": current_user.username,
        "submitted_at": datetime.utcnow().isoformat(),
        "account": request.account.strip(),
    })
    ctx["witness_accounts"] = witness_accounts

    # Auto-regenerate AI summary with all accounts now available
    try:
        rj = report.report_json if isinstance(report.report_json, dict) else json.loads(report.report_json)
        new_summary = await generate_incident_summary(ctx, rj)
        ctx["ai_summary"] = new_summary
        print(f"[reports] AI summary regenerated for report #{report_id} after witness submission")
    except Exception as e:
        print(f"[reports] AI summary regeneration failed: {e}")

    report.context_document = ctx
    db.commit()
    db.refresh(report)

    print(f"[reports] witness account submitted by '{current_user.username}' for report #{report_id}")

    return {"ok": True, "report_id": report.id}


@router.post("/{report_id}/regenerate-summary")
async def regenerate_summary(
    report_id: int,
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """
    Admin only — manually regenerate the AI incident summary.
    Reads all available accounts from context_document and calls the witness agent.
    """
    report = db.query(IncidentReport).filter(IncidentReport.id == report_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    ctx = report.context_document or {}
    if isinstance(ctx, str):
        ctx = json.loads(ctx)
    ctx = copy.deepcopy(ctx)

    rj = report.report_json if isinstance(report.report_json, dict) else json.loads(report.report_json)

    try:
        new_summary = await generate_incident_summary(ctx, rj)
        ctx["ai_summary"] = new_summary
        report.context_document = ctx
        db.commit()
        db.refresh(report)
        print(f"[reports] AI summary manually regenerated for report #{report_id} by {current_user.username}")
        return {"ok": True, "ai_summary": new_summary}
    except Exception as e:
        print(f"[reports] regenerate_summary failed: {e}")
        raise HTTPException(status_code=500, detail="Summary generation failed")


@router.post("/{report_id}/generate-briefing")
async def generate_briefing(
    report_id: int,
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """
    Admin only — generate a shift-ready safety briefing from the full context document.
    Written for a supervisor to deliver verbally to workers before the next shift.
    Stored in context_document.safety_briefing so it persists between sessions.
    """
    report = db.query(IncidentReport).filter(IncidentReport.id == report_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    ctx = report.context_document or {}
    if isinstance(ctx, str):
        ctx = json.loads(ctx)
    ctx = copy.deepcopy(ctx)

    rj = report.report_json if isinstance(report.report_json, dict) else json.loads(report.report_json)

    try:
        briefing = await generate_safety_briefing(ctx, rj)
        ctx["safety_briefing"] = briefing
        report.context_document = ctx
        db.commit()
        db.refresh(report)
        print(f"[reports] safety briefing generated for report #{report_id} by {current_user.username}")
        return {"ok": True, "safety_briefing": briefing}
    except Exception as e:
        print(f"[reports] generate_briefing failed: {e}")
        raise HTTPException(status_code=500, detail="Briefing generation failed")


# ══════════════════════════════════════════════════════════════════════════════
# SERIALIZER
# ══════════════════════════════════════════════════════════════════════════════

def serialize_report(report: IncidentReport, include_context: bool = False, vision_thread_status: str = None) -> dict:
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
        "witness_nominations": report.witness_nominations or [],
        "vision_thread_status": vision_thread_status,
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