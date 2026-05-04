from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
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
    save_message,
    WIDGET_MAP,
    INCIDENT_TYPE_OPTIONS,
    FIELD_TO_SECTION
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
from agents.vision_agent import analyze_image
from agents.vision_reasoning import run_vision_reasoning_gate
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
    image_b64: Optional[str] = None       # base64 image, no data URI prefix
    image_type: Optional[str] = None      # e.g. "image/jpeg"
    image_filename: Optional[str] = None  # original filename for MinIO storage


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


# ── Vision background task wrapper ────────────────────────────────────────────

async def _vision_gate_wrapper(report_id: int, report_json: dict, incident_type: str):
    """
    Creates its own DB session so the background task is fully decoupled
    from the request lifecycle. Safe to run after response is sent.
    """
    from database import SessionLocal
    db = SessionLocal()
    try:
        await run_vision_reasoning_gate(report_id, report_json, incident_type, db)
    except Exception as e:
        print(f"[chat] vision gate wrapper error for report #{report_id}: {e}")
    finally:
        db.close()


# ── Field suggestion prefill helper ──────────────────────────────────────────

def _apply_field_suggestions(session: dict, suggestions: dict):
    """
    Soft-prefill session report fields from vision field_suggestions.
    Uses FIELD_TO_SECTION to place each field in the correct section.
    Never overwrites a field that already has a non-empty value.
    incident_type is stored on the session directly, not in the report sections.
    """
    if not suggestions:
        return

    report = session.setdefault("report", {
        "basic_info": {},
        "injury_data": {},
        "near_miss_data": {},
        "equipment_damage_data": {}
    })

    applied = []
    for field, value in suggestions.items():
        if not value or str(value).strip().lower() in ("", "n/a", "na", "none"):
            continue

        if field == "incident_type":
            if not session.get("incident_type"):
                session["incident_type"] = value
                applied.append(f"incident_type={value}")
            continue

        section = FIELD_TO_SECTION.get(field)
        if not section:
            continue

        section_data = report.setdefault(section, {})
        existing = section_data.get(field, "")
        if not existing or str(existing).strip().lower() in ("", "n/a", "na", "none"):
            section_data[field] = value
            applied.append(f"{field}={value}")

    if applied:
        print(f"[vision] prefilled: {', '.join(applied)}")


# ── Vision image handling (mid-intake + cold-start) ───────────────────────────

async def _handle_intake_image(
    session_id: str,
    session: dict,
    image_b64: str,
    image_type: str,
    image_filename: str
) -> Optional[dict]:
    """
    Runs vision agent when an image arrives during intake (mid-intake or cold-start).

    Returns a ChatResponse dict when the vision agent should respond directly.
    Returns None only when observations were found and injected silently into
    vision_context — intake will fold the question into its next response.
    """
    is_cold_start = (session["step"] == "greet" and not session.get("incident_type"))
    trigger_context = "cold_start" if is_cold_start else "mid_intake"
    report_state = session.get("report", {})

    print(f"[chat] image received — context: {trigger_context}, session: {session_id}")

    result = await analyze_image(
        image_b64=image_b64,
        image_type=image_type or "image/jpeg",
        report_state=report_state,
        trigger_context=trigger_context
    )

    # Bad image — respond with retake request, do not continue intake
    if not result["quality_ok"]:
        quality_message = result["reporter_message"]
        if is_cold_start:
            session["step"] = "await_incident_type"
        save_message(session, quality_message, is_user=False)
        return {
            "response": quality_message,
            "show_widget": None,
            "extracted": get_report_with_incident_type(session),
            "options": None
        }

    # Apply any field suggestions as soft prefills — happens regardless of observations
    field_suggestions = result.get("field_suggestions", {})
    if field_suggestions:
        _apply_field_suggestions(session, field_suggestions)

    priority_obs = result.get("priority_observation")
    reporter_message = result.get("reporter_message", "")

    # Inject priority observation into vision_context for intake agent to fold in
    if priority_obs and reporter_message:
        vision_context = session.get("vision_context", [])
        vision_context.append({
            "observation": priority_obs,
            "reporter_message": reporter_message,
            "added_at": datetime.utcnow().isoformat()
        })
        session["vision_context"] = vision_context

    # ── Cold-start ─────────────────────────────────────────────────────────────
    # Skip the greeting entirely — use the vision message as the opening question
    if is_cold_start:
        session["step"] = "await_incident_type"
        if reporter_message:
            # Already consumed as opening — remove from vision_context if it was added
            if priority_obs and session.get("vision_context"):
                session["vision_context"].pop(0)
            session["last_question"] = reporter_message
            save_message(session, reporter_message, is_user=False)
            return {
                "response": reporter_message,
                "show_widget": None,
                "extracted": get_report_with_incident_type(session),
                "options": INCIDENT_TYPE_OPTIONS
            }
        # Truly nothing to say — fall through to normal greeting
        return None

    # ── Mid-intake, observations found ─────────────────────────────────────────
    # Injected into vision_context above. Return None so smart_process_message
    # folds the question naturally into the next field question.
    if priority_obs:
        return None

    # ── Mid-intake, 0 observations ─────────────────────────────────────────────
    # vision_agent described the scene and produced a confirmable question.
    # Return it directly — never return None here (causes blank frontend turn).
    if reporter_message:
        save_message(session, reporter_message, is_user=False)
        return {
            "response": reporter_message,
            "show_widget": None,
            "extracted": get_report_with_incident_type(session),
            "options": None
        }

    # Absolute fallback — should rarely be reached
    fallback = "I received your photo. Could you describe what happened in your own words?"
    save_message(session, fallback, is_user=False)
    return {
        "response": fallback,
        "show_widget": None,
        "extracted": get_report_with_incident_type(session),
        "options": None
    }



# ── Shared submit handler ─────────────────────────────────────────────────────

async def _handle_submit(
    session_id: str,
    session: dict,
    current_user: User,
    db: Session,
    get_report_fn,
    background_tasks: BackgroundTasks,
    narrative: str = None
) -> ChatResponse:
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

    # Fire vision reasoning gate as background task — fully decoupled from request
    background_tasks.add_task(
        _vision_gate_wrapper,
        db_report.id,
        formatted["report_json"],
        incident_type
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
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    session_id = request.session_id or str(uuid.uuid4())

    # ── Image handling — runs before process_message ──────────────────────────
    if request.image_b64:
        session = get_session(session_id)
        vision_result = await _handle_intake_image(
            session_id=session_id,
            session=session,
            image_b64=request.image_b64,
            image_type=request.image_type or "image/jpeg",
            image_filename=request.image_filename or "image.jpg"
        )
        # Vision responded directly (bad quality or cold-start first message)
        if vision_result is not None:
            return ChatResponse(
                session_id=session_id,
                response=vision_result["response"],
                show_widget=vision_result.get("show_widget"),
                extracted=vision_result.get("extracted"),
                options=vision_result.get("options")
            )
        # Vision injected silently — fall through to process_message below

    result = await process_message(
        session_id=session_id,
        user_message=request.message,
        button_choice=request.button_choice,
        current_data=request.current_data
    )

    if result.get("response") == "__SUBMIT__":
        session = get_session(session_id)
        response = await _handle_submit(
            session_id, session, current_user, db,
            get_report_with_incident_type,
            background_tasks
        )
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
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    session_id = request.session_id or str(uuid.uuid4())

    # ── Image handling — runs before smart_process_message ────────────────────
    if request.image_b64:
        # Smart mode uses smart_get_session but vision logic is identical
        from agents.smart_intake import get_session as smart_get_sess
        session = smart_get_sess(session_id)
        vision_result = await _handle_intake_image(
            session_id=session_id,
            session=session,
            image_b64=request.image_b64,
            image_type=request.image_type or "image/jpeg",
            image_filename=request.image_filename or "image.jpg"
        )
        if vision_result is not None:
            return ChatResponse(
                session_id=session_id,
                response=vision_result["response"],
                show_widget=vision_result.get("show_widget"),
                extracted=vision_result.get("extracted"),
                options=vision_result.get("options")
            )

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
            background_tasks,
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