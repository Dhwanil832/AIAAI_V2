from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List
from database import get_db
from core.dependencies import get_current_user
from models.user import User
from models.report import IncidentReport
from models.unfinished import UnfinishedReport
from agents.intake import (
    process_message,
    clear_session,
    get_session,
    get_report_with_incident_type,
    find_next_missing_field,
    WIDGET_MAP
)
from agents.smart_intake import (
    process_message as smart_process_message,
    clear_session as smart_clear_session,
    get_session as smart_get_session,
    get_report_with_incident_type as smart_get_report_with_incident_type,
    get_missing_fields
)
from agents.flagging import check_flags
from agents.formatter import format_report
from agents.similarity import find_similar
from agents.corrective_actions import get_corrective_action_suggestions
from agents.notifier import notify_admins_on_submit
from core.qdrant import upsert_incident
import json
import copy
import uuid
from datetime import datetime

router = APIRouter()


class ChatRequest(BaseModel):
    session_id: Optional[str] = None
    message: Optional[str] = None
    button_choice: Optional[str] = None
    current_data: Optional[dict] = None


class ChatResponse(BaseModel):
    session_id: str
    response: str
    show_widget: Optional[str] = None
    extracted: Optional[dict] = None
    options: Optional[list] = None
    summary: Optional[dict] = None
    report_id: Optional[int] = None
    similar_incidents: Optional[list] = None
    suggested_actions: Optional[list] = None


# ── SHARED SUBMIT HANDLER ─────────────────────────────────────────────────────
async def _handle_submit(session_id: str, session: dict, current_user: User, db: Session, get_report_fn, narrative: str = None) -> ChatResponse:
    incident_type = session.get("incident_type", "")
    final_report = get_report_fn(session)

    is_flagged, flag_reason = check_flags(final_report, incident_type)

    session_copy = copy.deepcopy(session)
    session_copy["report"] = final_report

    user_info = {
        "name": current_user.username,
        "job": current_user.job_title or ""
    }
    formatted = format_report(session_copy, user_info)

    # Inject narrative into context_document if present
    if narrative:
        formatted["context_document"]["narrative"] = narrative

    similar = []
    try:
        similar = await find_similar(final_report, incident_type, db)
    except Exception as e:
        print(f"[chat] similarity search failed: {e}")

    suggested_actions = []
    try:
        suggested_actions = get_corrective_action_suggestions(similar)
    except Exception as e:
        print(f"[chat] corrective actions failed: {e}")

    db_report = IncidentReport(
        user_id=current_user.id,
        creator_name=current_user.username,
        creator_job_title=current_user.job_title or "",
        report_json=formatted["report_json"],
        context_document=formatted["context_document"],
        flagged=is_flagged,
        flag_reason=flag_reason if is_flagged else None,
        similar_incidents=similar if similar else None,
        created_at=datetime.utcnow()
    )
    db.add(db_report)
    db.commit()
    db.refresh(db_report)

    basic = final_report.get("basic_info", {})
    await upsert_incident(
        point_id=db_report.id + 1_000_000,
        report=final_report,
        incident_type=incident_type,
        source="submitted",
        source_id=f"report-{db_report.id}",
        source_file="chatbot",
        actions_taken=basic.get("actions_taken", ""),
        severity=basic.get("severity", ""),
        location=basic.get("location", ""),
        datetime_str=basic.get("datetime", ""),
    )

    notify_admins_on_submit(
        report_id=db_report.id,
        incident_type=incident_type,
        location=basic.get("location", ""),
        db=db
    )

    print(f"[chat] report #{db_report.id} submitted by {current_user.username} — flagged: {is_flagged} — similar: {len(similar)}")

    return ChatResponse(
        session_id=session_id,
        response=f"Report submitted successfully! Your report ID is #{db_report.id}.",
        show_widget=None,
        extracted=None,
        report_id=db_report.id,
        similar_incidents=similar if similar else None,
        suggested_actions=suggested_actions if suggested_actions else None
    )


# ══════════════════════════════════════════════════════════════════════════════
# STANDARD REPORT ENDPOINTS
# ══════════════════════════════════════════════════════════════════════════════

@router.post("/start")
async def start_chat(
    current_user: User = Depends(get_current_user)
):
    session_id = str(uuid.uuid4())
    result = await process_message(session_id=session_id)
    return ChatResponse(
        session_id=session_id,
        response=result.get("response", ""),
        show_widget=result.get("show_widget"),
        options=result.get("options")
    )


@router.post("/message", response_model=ChatResponse)
async def chat_message(
    request: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    session_id = request.session_id or str(uuid.uuid4())

    result = await process_message(
        session_id=session_id,
        user_message=request.message,
        button_choice=request.button_choice,
        current_data=request.current_data
    )

    if result.get("response") == "__SUBMIT__":
        session = get_session(session_id)
        response = await _handle_submit(session_id, session, current_user, db, get_report_with_incident_type)
        clear_session(session_id)
        return response

    return ChatResponse(
        session_id=session_id,
        response=result.get("response", ""),
        show_widget=result.get("show_widget"),
        extracted=result.get("extracted"),
        options=result.get("options"),
        summary=result.get("summary")
    )


@router.post("/save-progress")
async def save_progress(
    request: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if not request.session_id:
        raise HTTPException(status_code=400, detail="session_id required")

    session = get_session(request.session_id)
    report_data = get_report_with_incident_type(session)
    chat_history = session.get("chat_history", [])

    existing = db.query(UnfinishedReport).filter(
        UnfinishedReport.session_id == request.session_id
    ).first()

    if existing:
        existing.report_json = json.dumps(report_data)
        existing.chat_history = json.dumps(chat_history)
        existing.updated_at = datetime.utcnow()
        db.commit()
        print(f"[chat] progress updated for session {request.session_id}")
        return {"message": "Progress updated", "id": existing.id}
    else:
        unfinished = UnfinishedReport(
            user_id=current_user.id,
            session_id=request.session_id,
            report_json=json.dumps(report_data),
            chat_history=json.dumps(chat_history),
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        db.add(unfinished)
        db.commit()
        db.refresh(unfinished)
        print(f"[chat] progress saved for session {request.session_id}")
        return {"message": "Progress saved", "id": unfinished.id}


@router.post("/resume")
async def resume_chat(
    request: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if not request.session_id:
        raise HTTPException(status_code=400, detail="session_id required")

    unfinished = db.query(UnfinishedReport).filter(
        UnfinishedReport.session_id == request.session_id,
        UnfinishedReport.user_id == current_user.id
    ).first()

    if not unfinished:
        raise HTTPException(status_code=404, detail="Unfinished report not found")

    session = get_session(request.session_id)
    restored_report = json.loads(unfinished.report_json) if isinstance(unfinished.report_json, str) else unfinished.report_json
    incident_type = restored_report.get("basic_info", {}).pop("incident_type", "")

    session["report"] = restored_report
    session["chat_history"] = json.loads(unfinished.chat_history) if isinstance(unfinished.chat_history, str) else unfinished.chat_history
    session["incident_type"] = incident_type
    session["step"] = "collecting"
    session["ollama_initialized"] = True

    print(f"[chat] session {request.session_id} resumed — incident_type: {incident_type}")

    section, field = find_next_missing_field(session)
    final_report = get_report_with_incident_type(session)

    if section is None:
        session["step"] = "confirm"
        return ChatResponse(
            session_id=request.session_id,
            response="Welcome back! It looks like all fields are filled. Does everything look correct?",
            show_widget="confirm-buttons",
            extracted=final_report
        )

    field_label = field.replace("_", " ").title()
    return ChatResponse(
        session_id=request.session_id,
        response=f"Welcome back! Let's continue where you left off. Could you please provide the {field_label}?",
        show_widget=WIDGET_MAP.get(field),
        extracted=final_report
    )


# ══════════════════════════════════════════════════════════════════════════════
# SMART REPORT ENDPOINTS
# ══════════════════════════════════════════════════════════════════════════════

@router.post("/smart-start")
async def smart_start_chat(
    current_user: User = Depends(get_current_user)
):
    session_id = str(uuid.uuid4())
    result = await smart_process_message(session_id=session_id)
    return ChatResponse(
        session_id=session_id,
        response=result.get("response", ""),
        show_widget=result.get("show_widget"),
        options=result.get("options")
    )


@router.post("/smart-message", response_model=ChatResponse)
async def smart_chat_message(
    request: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    session_id = request.session_id or str(uuid.uuid4())

    result = await smart_process_message(
        session_id=session_id,
        user_message=request.message,
        button_choice=request.button_choice,
        current_data=request.current_data
    )

    if result.get("response") == "__SUBMIT__":
        session = smart_get_session(session_id)
        narrative = session.get("narrative", "")
        response = await _handle_submit(
            session_id, session, current_user, db,
            smart_get_report_with_incident_type,
            narrative=narrative
        )
        smart_clear_session(session_id)
        return response

    return ChatResponse(
        session_id=session_id,
        response=result.get("response", ""),
        show_widget=result.get("show_widget"),
        extracted=result.get("extracted"),
        options=result.get("options"),
        summary=result.get("summary")
    )


@router.post("/smart-save-progress")
async def smart_save_progress(
    request: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if not request.session_id:
        raise HTTPException(status_code=400, detail="session_id required")

    session = smart_get_session(request.session_id)
    report_data = smart_get_report_with_incident_type(session)
    chat_history = session.get("chat_history", [])

    # Store narrative in report_json so it survives resume
    report_data["_narrative"] = session.get("narrative", "")
    report_data["_mode"] = "smart"

    existing = db.query(UnfinishedReport).filter(
        UnfinishedReport.session_id == request.session_id
    ).first()

    if existing:
        existing.report_json = json.dumps(report_data)
        existing.chat_history = json.dumps(chat_history)
        existing.updated_at = datetime.utcnow()
        db.commit()
        print(f"[chat] smart progress updated for session {request.session_id}")
        return {"message": "Progress updated", "id": existing.id}
    else:
        unfinished = UnfinishedReport(
            user_id=current_user.id,
            session_id=request.session_id,
            report_json=json.dumps(report_data),
            chat_history=json.dumps(chat_history),
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        db.add(unfinished)
        db.commit()
        db.refresh(unfinished)
        print(f"[chat] smart progress saved for session {request.session_id}")
        return {"message": "Progress saved", "id": unfinished.id}


@router.post("/smart-resume")
async def smart_resume_chat(
    request: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if not request.session_id:
        raise HTTPException(status_code=400, detail="session_id required")

    unfinished = db.query(UnfinishedReport).filter(
        UnfinishedReport.session_id == request.session_id,
        UnfinishedReport.user_id == current_user.id
    ).first()

    if not unfinished:
        raise HTTPException(status_code=404, detail="Unfinished report not found")

    session = smart_get_session(request.session_id)
    restored_report = json.loads(unfinished.report_json) if isinstance(unfinished.report_json, str) else unfinished.report_json

    # Extract meta fields stored at resume time
    incident_type = restored_report.get("basic_info", {}).pop("incident_type", "")
    narrative = restored_report.pop("_narrative", "")
    restored_report.pop("_mode", None)

    session["report"] = restored_report
    session["chat_history"] = json.loads(unfinished.chat_history) if isinstance(unfinished.chat_history, str) else unfinished.chat_history
    session["incident_type"] = incident_type
    session["narrative"] = narrative
    session["step"] = "collecting"

    print(f"[chat] smart session {request.session_id} resumed — incident_type: {incident_type}")

    # LLM picks up naturally from full conversation history
    # Just send a resume trigger so it greets the user and continues
    result = await smart_process_message(
        session_id=request.session_id,
        user_message="I'm back, let's continue."
    )

    return ChatResponse(
        session_id=request.session_id,
        response=result.get("response", "Welcome back! Let's continue where we left off."),
        show_widget=result.get("show_widget"),
        extracted=smart_get_report_with_incident_type(session),
        options=result.get("options")
    )