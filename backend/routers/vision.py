from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List
from database import get_db
from core.dependencies import get_current_user
from models.user import User
from models.vision import VisionThread
from models.report import IncidentReport
from agents.vision_agent import analyze_image
from agents.vision_conversation import handle_vision_upload, handle_vision_reply
from core.minio import get_image_presigned_url
from datetime import datetime

router = APIRouter()


# ── Request / Response models ─────────────────────────────────────────────────

class MidIntakeUploadRequest(BaseModel):
    session_id: str
    image_b64: str
    image_type: str
    filename: Optional[str] = "image.jpg"


class MidIntakeUploadResponse(BaseModel):
    quality_ok: bool
    reporter_message: str          # intake agent folds this into next question
    field_suggestions: dict        # pre-filled fields from image
    vision_context_injected: bool  # whether session vision_context was updated


class PostSubmissionUploadRequest(BaseModel):
    image_b64: str
    image_type: str
    filename: Optional[str] = "image.jpg"


class VisionReplyRequest(BaseModel):
    message: str


class VisionReplyResponse(BaseModel):
    message: str
    resolved: bool
    resolution: str


class ConversationTurn(BaseModel):
    role: str
    content: str
    timestamp: str


class ReporterThreadResponse(BaseModel):
    thread_id: int
    status: str
    resolution: str
    conversation: List[ConversationTurn]
    has_images: bool


class ObservationItem(BaseModel):
    type: str
    observation: str
    severity: str
    detail: Optional[str] = ""


class AmendmentItem(BaseModel):
    field: str
    section: str
    old_value: Optional[str] = ""
    new_value: str
    reason: str
    timestamp: str


class SecondaryFlagItem(BaseModel):
    observation: str
    severity: str
    confirmed_by_user_id: int
    timestamp: str
    supervisor_notified: bool


class AdminThreadResponse(BaseModel):
    thread_id: int
    report_id: Optional[int]
    trigger_context: str
    status: str
    resolution: str
    resolution_note: Optional[str]
    quality_ok: Optional[bool]
    quality_reason: Optional[str]
    image_urls: List[str]          # presigned MinIO URLs
    full_observations: List[ObservationItem]
    priority_observation: Optional[ObservationItem]
    conversation: List[ConversationTurn]
    amendments: List[AmendmentItem]
    secondary_flags: List[SecondaryFlagItem]
    created_at: str
    updated_at: str


# ── 1. Mid-intake image upload ────────────────────────────────────────────────

@router.post("/upload-mid-intake", response_model=MidIntakeUploadResponse)
async def upload_mid_intake(
    request: MidIntakeUploadRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Reporter attaches image during active intake session.

    Runs vision agent with mid_intake context.
    Injects priority observation into session vision_context.
    Returns field_suggestions and reporter_message for intake agent to use.
    """
    # Import here to avoid circular — intake imports are session-level
    from agents.intake import get_session

    session = get_session(request.session_id)
    report_state = session.get("report", {})

    # Determine context — cold_start if no incident type yet
    has_incident_type = bool(session.get("incident_type", ""))
    trigger_context = "mid_intake" if has_incident_type else "cold_start"

    result = await analyze_image(
        image_b64=request.image_b64,
        image_type=request.image_type,
        report_state=report_state,
        trigger_context=trigger_context
    )

    reporter_message = result.get("reporter_message", "")
    field_suggestions = result.get("field_suggestions", {})
    priority_observation = result.get("priority_observation")
    injected = False

    # Inject into session vision_context if there's something to ask
    if priority_observation and reporter_message:
        vision_context = session.get("vision_context", [])
        vision_context.append({
            "observation": priority_observation,
            "reporter_message": reporter_message,
            "added_at": datetime.utcnow().isoformat()
        })
        session["vision_context"] = vision_context
        injected = True
        print(f"[vision_router] injected observation into session {request.session_id}")

    # Store VisionThread linked to unfinished report if session_id maps to one
    _create_intake_thread(
        session_id=request.session_id,
        trigger_context=trigger_context,
        user_id=current_user.id,
        result=result,
        db=db
    )

    return MidIntakeUploadResponse(
        quality_ok=result["quality_ok"],
        reporter_message=reporter_message,
        field_suggestions=field_suggestions,
        vision_context_injected=injected
    )


# ── 2. Post-submission image upload ───────────────────────────────────────────

@router.post("/upload-post-submission/{thread_id}")
async def upload_post_submission(
    thread_id: int,
    request: PostSubmissionUploadRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Reporter uploads image after receiving a vision follow-up notification.
    Only the reporter who owns the report can upload.
    """
    thread = db.query(VisionThread).filter(VisionThread.id == thread_id).first()
    if not thread:
        raise HTTPException(status_code=404, detail="Vision thread not found")

    if thread.triggered_by_user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized for this thread")

    if thread.status == "resolved":
        raise HTTPException(status_code=400, detail="This thread is already resolved")

    result = await handle_vision_upload(
        thread_id=thread_id,
        image_b64=request.image_b64,
        image_type=request.image_type,
        filename=request.filename,
        db=db
    )

    return result


# ── 3. Reporter reply in vision thread ────────────────────────────────────────

@router.post("/reply/{thread_id}", response_model=VisionReplyResponse)
async def vision_reply(
    thread_id: int,
    request: VisionReplyRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Reporter sends a reply in the vision follow-up thread.
    Only the reporter who owns the report can reply.
    """
    thread = db.query(VisionThread).filter(VisionThread.id == thread_id).first()
    if not thread:
        raise HTTPException(status_code=404, detail="Vision thread not found")

    if thread.triggered_by_user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized for this thread")

    if thread.status == "resolved":
        return VisionReplyResponse(
            message="This conversation has already been resolved.",
            resolved=True,
            resolution=thread.resolution
        )

    result = await handle_vision_reply(
        thread_id=thread_id,
        reporter_message=request.message,
        reporter_user_id=current_user.id,
        db=db
    )

    return VisionReplyResponse(
        message=result["message"],
        resolved=result["resolved"],
        resolution=result["resolution"]
    )


# ── 4. Reporter view — conversation only ──────────────────────────────────────

@router.get("/thread/reporter/{report_id}", response_model=ReporterThreadResponse)
async def get_reporter_thread(
    report_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Reporter fetches their vision thread for a report.
    Returns conversation turns only — no full_observations.
    """
    # Verify ownership
    report = db.query(IncidentReport).filter(
        IncidentReport.id == report_id,
        IncidentReport.user_id == current_user.id
    ).first()

    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    thread = db.query(VisionThread).filter(
        VisionThread.report_id == report_id,
        VisionThread.trigger_context == "post_submission"
    ).order_by(VisionThread.created_at.desc()).first()

    if not thread:
        raise HTTPException(status_code=404, detail="No vision thread for this report")

    return ReporterThreadResponse(
        thread_id=thread.id,
        status=thread.status,
        resolution=thread.resolution,
        conversation=[
            ConversationTurn(**turn)
            for turn in (thread.conversation or [])
        ],
        has_images=bool(thread.image_paths)
    )


# ── 5. Admin view — full thread ───────────────────────────────────────────────

@router.get("/thread/admin/{report_id}", response_model=AdminThreadResponse)
async def get_admin_thread(
    report_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Admin fetches the full vision thread for a report.
    Returns everything — observations, conversation, amendments, secondary flags.
    Admin only.
    """
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")

    thread = db.query(VisionThread).filter(
        VisionThread.report_id == report_id
    ).order_by(VisionThread.created_at.desc()).first()

    if not thread:
        raise HTTPException(status_code=404, detail="No vision thread for this report")

    # Generate presigned URLs for all stored images
    image_urls = []
    for img in (thread.image_paths or []):
        try:
            url = get_image_presigned_url(img["path"])
            image_urls.append(url)
        except Exception as e:
            print(f"[vision_router] presigned URL failed: {e}")

    return AdminThreadResponse(
        thread_id=thread.id,
        report_id=thread.report_id,
        trigger_context=thread.trigger_context,
        status=thread.status,
        resolution=thread.resolution,
        resolution_note=thread.resolution_note,
        quality_ok=thread.quality_ok,
        quality_reason=thread.quality_reason,
        image_urls=image_urls,
        full_observations=[
            ObservationItem(**obs)
            for obs in (thread.full_observations or [])
        ],
        priority_observation=(
            ObservationItem(**thread.priority_observation)
            if thread.priority_observation else None
        ),
        conversation=[
            ConversationTurn(**turn)
            for turn in (thread.conversation or [])
        ],
        amendments=[
            AmendmentItem(**a)
            for a in (thread.amendments or [])
        ],
        secondary_flags=[
            SecondaryFlagItem(**f)
            for f in (thread.secondary_flags or [])
        ],
        created_at=thread.created_at.isoformat() if thread.created_at else "",
        updated_at=thread.updated_at.isoformat() if thread.updated_at else ""
    )


# ── Helper ─────────────────────────────────────────────────────────────────────

def _create_intake_thread(
    session_id: str,
    trigger_context: str,
    user_id: int,
    result: dict,
    db: Session
):
    """
    Create a VisionThread record for mid_intake and cold_start contexts.
    Tries to link to UnfinishedReport by session_id if it exists.
    Swallows errors — thread creation is best-effort for intake contexts.
    """
    try:
        from models.unfinished import UnfinishedReport
        unfinished = db.query(UnfinishedReport).filter(
            UnfinishedReport.session_id == session_id
        ).first()

        thread = VisionThread(
            report_id=None,
            unfinished_report_id=unfinished.id if unfinished else None,
            trigger_context=trigger_context,
            triggered_by_user_id=user_id,
            image_paths=[],
            quality_ok=result.get("quality_ok"),
            quality_reason=result.get("quality_reason"),
            full_observations=result.get("full_observations", []),
            priority_observation=result.get("priority_observation"),
            conversation=[],
            resolution="pending",
            amendments=[],
            secondary_flags=[],
            status="open",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        db.add(thread)
        db.commit()
        print(f"[vision_router] intake thread created — context: {trigger_context}")

    except Exception as e:
        print(f"[vision_router] intake thread creation failed (non-fatal): {e}")
        db.rollback()