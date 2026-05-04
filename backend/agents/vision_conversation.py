import json
import re
import base64
from datetime import datetime
from sqlalchemy.orm import Session
from models.vision import VisionThread
from models.report import IncidentReport
from models.notification import Notification
from agents.vision_agent import analyze_image
from core.minio import upload_image, get_image_presigned_url


# ── Public: reporter uploads image ────────────────────────────────────────────

async def handle_vision_upload(
    thread_id: int,
    image_b64: str,
    image_type: str,
    filename: str,
    db: Session
) -> dict:
    """
    Called when reporter uploads an image via the vision thread notification.

    Runs full vision agent in post_submission mode.
    Stores image in MinIO.
    Saves all observations to thread.
    Produces first reporter-facing question.

    Returns:
    {
        "quality_ok": bool,
        "message": str,        # first question or quality failure message
        "thread_id": int,
        "resolved": bool
    }
    """
    thread = db.query(VisionThread).filter(VisionThread.id == thread_id).first()
    if not thread:
        raise ValueError(f"VisionThread #{thread_id} not found")

    report = db.query(IncidentReport).filter(
        IncidentReport.id == thread.report_id
    ).first()

    report_json = report.report_json if report else {}

    # Store image in MinIO
    try:
        image_bytes = base64.b64decode(image_b64)
        folder = f"report_{thread.report_id}"
        stored_path = upload_image(image_bytes, filename, folder)

        current_paths = thread.image_paths or []
        current_paths.append({
            "path": stored_path,
            "filename": filename,
            "uploaded_at": datetime.utcnow().isoformat()
        })
        thread.image_paths = current_paths

    except Exception as e:
        print(f"[vision_conversation] image storage failed: {e}")
        stored_path = None

    # Run vision agent
    result = await analyze_image(
        image_b64=image_b64,
        image_type=image_type,
        report_state=report_json,
        trigger_context="post_submission"
    )

    thread.quality_ok = result["quality_ok"]
    thread.quality_reason = result.get("quality_reason")

    if not result["quality_ok"]:
        # Bad image — ask for retake, do not save observations yet
        message = result["reporter_message"]
        _append_conversation(thread, role="agent", content=message)
        thread.updated_at = datetime.utcnow()
        db.commit()
        return {
            "quality_ok": False,
            "message": message,
            "thread_id": thread_id,
            "resolved": False
        }

    # Good image — save full observations (admin only)
    thread.full_observations = result["full_observations"]
    thread.priority_observation = result["priority_observation"]

    reporter_message = result["reporter_message"]

    if not reporter_message:
        # Nothing significant observed — close gracefully
        closing = "Thanks for sending that over. I've added it to your report."
        _append_conversation(thread, role="agent", content=closing)
        thread.resolution = "confirmed"
        thread.status = "resolved"
        thread.updated_at = datetime.utcnow()
        db.commit()
        return {
            "quality_ok": True,
            "message": closing,
            "thread_id": thread_id,
            "resolved": True
        }

    # Ask the priority question
    _append_conversation(thread, role="agent", content=reporter_message)
    thread.updated_at = datetime.utcnow()
    db.commit()

    print(f"[vision_conversation] thread #{thread_id} — first question sent")

    return {
        "quality_ok": True,
        "message": reporter_message,
        "thread_id": thread_id,
        "resolved": False
    }


# ── Public: reporter replies ──────────────────────────────────────────────────

async def handle_vision_reply(
    thread_id: int,
    reporter_message: str,
    reporter_user_id: int,
    db: Session
) -> dict:
    """
    Called on each reporter reply in the vision thread.

    Reads current thread state, determines resolution, decides whether
    to ask one more thing or close gracefully.

    Returns:
    {
        "message": str,        # agent's next message
        "resolved": bool,
        "resolution": str      # "pending" | "confirmed" | "corrected" |
                               # "escalated" | "dismissed"
    }
    """
    thread = db.query(VisionThread).filter(VisionThread.id == thread_id).first()
    if not thread:
        raise ValueError(f"VisionThread #{thread_id} not found")

    # Save reporter's reply
    _append_conversation(thread, role="reporter", content=reporter_message)

    report = db.query(IncidentReport).filter(
        IncidentReport.id == thread.report_id
    ).first()
    report_json = report.report_json if report else {}

    # Assess the reply against the priority observation
    assessment = await _assess_reply(
        reporter_message=reporter_message,
        priority_observation=thread.priority_observation or {},
        report_json=report_json,
        conversation=thread.conversation or []
    )

    resolution_type = assessment.get("resolution")
    agent_response = assessment.get("agent_response", "")
    amendment = assessment.get("amendment")
    secondary_flag = assessment.get("secondary_flag")

    # Handle amendment — field correction confirmed by reporter
    if amendment:
        amendments = thread.amendments or []
        amendments.append({
            "field": amendment.get("field"),
            "section": amendment.get("section"),
            "old_value": amendment.get("old_value"),
            "new_value": amendment.get("new_value"),
            "reason": reporter_message,
            "timestamp": datetime.utcnow().isoformat()
        })
        thread.amendments = amendments

        # Apply amendment to the actual report
        if report and amendment.get("field") and amendment.get("new_value"):
            _apply_amendment_to_report(
                report=report,
                field=amendment["field"],
                section=amendment.get("section", "basic_info"),
                new_value=amendment["new_value"]
            )

    # Handle secondary flag — unreported hazard confirmed as real
    if secondary_flag:
        flags = thread.secondary_flags or []
        flags.append({
            "observation": secondary_flag.get("observation"),
            "severity": secondary_flag.get("severity"),
            "confirmed_by_user_id": reporter_user_id,
            "timestamp": datetime.utcnow().isoformat(),
            "supervisor_notified": False
        })
        thread.secondary_flags = flags

        # Notify supervisor if hazard is active danger
        if secondary_flag.get("severity") in ("critical", "high"):
            await _notify_supervisor_secondary_flag(
                report_id=thread.report_id,
                observation=secondary_flag.get("observation", ""),
                db=db
            )
            flags[-1]["supervisor_notified"] = True
            thread.secondary_flags = flags

    # Save agent reply
    _append_conversation(thread, role="agent", content=agent_response)

    # Determine if thread should close
    is_resolved = resolution_type in ("confirmed", "corrected", "escalated", "dismissed")

    if is_resolved:
        thread.resolution = resolution_type
        thread.resolution_note = reporter_message
        thread.status = "resolved" if resolution_type != "escalated" else "escalated"
    else:
        # Still pending — check if we've gone on too long
        reporter_turns = sum(
            1 for turn in (thread.conversation or [])
            if turn.get("role") == "reporter"
        )
        if reporter_turns >= 4:
            # Gracefully close — don't keep going
            closing = "Got it, thanks for the context. I've noted everything on the report."
            _append_conversation(thread, role="agent", content=closing)
            thread.resolution = "confirmed"
            thread.resolution_note = "closed after extended exchange"
            thread.status = "resolved"
            agent_response = closing
            is_resolved = True

    thread.updated_at = datetime.utcnow()
    db.commit()

    print(f"[vision_conversation] thread #{thread_id} — resolution: {thread.resolution}")

    return {
        "message": agent_response,
        "resolved": is_resolved,
        "resolution": thread.resolution
    }


# ── LLM: assess reporter reply ────────────────────────────────────────────────

async def _assess_reply(
    reporter_message: str,
    priority_observation: dict,
    report_json: dict,
    conversation: list
) -> dict:
    """
    Single LLM call — reads the reporter's reply and determines:
    - Is the observation resolved? How?
    - Does any field need amending?
    - Is there a secondary hazard to flag?
    - What should the agent say next?

    Returns:
    {
        "resolution": "confirmed" | "corrected" | "escalated" | "dismissed" | "pending",
        "agent_response": str,
        "amendment": {field, section, old_value, new_value} | None,
        "secondary_flag": {observation, severity} | None
    }
    """
    from core.ollama import chat_with_ollama

    obs_text = priority_observation.get("observation", "")
    obs_type = priority_observation.get("type", "context")
    obs_severity = priority_observation.get("severity", "low")

    # Build conversation history for context
    history_lines = []
    for turn in conversation[-6:]:  # last 6 turns for context
        role_label = "Safety officer" if turn.get("role") == "agent" else "Reporter"
        history_lines.append(f"{role_label}: {turn.get('content', '')}")
    history_text = "\n".join(history_lines)

    # Current field value if this is a contradiction
    current_value = _find_field_in_report(obs_text, report_json)

    system_prompt = (
        "You are a workplace safety officer reviewing a reporter's response "
        "to a follow-up question about an incident photo.\n\n"
        f"The observation from the photo was: {obs_text}\n"
        f"Observation type: {obs_type} | Severity: {obs_severity}\n\n"
        "Based on the reporter's reply, determine:\n"
        "1. Is this observation resolved?\n"
        "   - confirmed: reporter confirms the observation is correct, no change needed\n"
        "   - corrected: reporter provides a correction that should update the report\n"
        "   - escalated: reporter confirms an active hazard still exists\n"
        "   - dismissed: reporter says observation is not relevant or was a mistake\n"
        "   - pending: reply is unclear, needs one more clarifying question\n\n"
        "2. If corrected — what field changed and to what value?\n"
        "3. If escalated — describe the confirmed hazard\n"
        "4. What should the safety officer say next? "
        "Keep it to 1-2 sentences. Natural and conversational. "
        "If resolved, close warmly. If pending, ask one clarifying question.\n\n"
        "Return ONLY valid JSON. No explanation. No markdown.\n\n"
        "{\n"
        '  "resolution": "confirmed" | "corrected" | "escalated" | "dismissed" | "pending",\n'
        '  "agent_response": "what to say next",\n'
        '  "amendment": {"field": "field_name", "section": "section_name", '
        '"old_value": "...", "new_value": "..."} or null,\n'
        '  "secondary_flag": {"observation": "...", "severity": "critical|high|medium|low"} or null\n'
        "}"
    )

    user_prompt = (
        f"Conversation so far:\n{history_text}\n\n"
        f"Reporter just said: {reporter_message}\n\n"
        "Assess this reply."
    )

    try:
        from core.ollama import chat_with_ollama
        raw = await chat_with_ollama(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
        )
        result = _parse_json(raw)
        if not isinstance(result, dict):
            return _fallback_assessment()
        return result

    except Exception as e:
        print(f"[vision_conversation] reply assessment failed: {e}")
        return _fallback_assessment()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _append_conversation(thread: VisionThread, role: str, content: str):
    """Append a turn to the thread conversation list."""
    conversation = thread.conversation or []
    conversation.append({
        "role": role,
        "content": content,
        "timestamp": datetime.utcnow().isoformat()
    })
    thread.conversation = conversation


def _apply_amendment_to_report(
    report: IncidentReport,
    field: str,
    section: str,
    new_value: str
):
    """
    Apply a confirmed amendment to the live report_json.
    Only updates the field — does not touch any other data.
    """
    try:
        report_data = report.report_json or {}
        if section in report_data and isinstance(report_data[section], dict):
            report_data[section][field] = new_value
            report.report_json = report_data
            print(f"[vision_conversation] amended report: {section}.{field} = '{new_value}'")
    except Exception as e:
        print(f"[vision_conversation] amendment apply failed: {e}")


def _find_field_in_report(observation_text: str, report_json: dict) -> str:
    """
    Best-effort: find any report field value that relates to the observation.
    Used to populate old_value in amendment records.
    """
    obs_lower = observation_text.lower()
    for section, fields in report_json.items():
        if not isinstance(fields, dict):
            continue
        for key, value in fields.items():
            if value and key in obs_lower:
                return str(value)
    return ""


async def _notify_supervisor_secondary_flag(
    report_id: int,
    observation: str,
    db: Session
):
    """
    Notify admins when a reporter confirms a secondary hazard
    that was not in the original report.
    """
    try:
        from models.user import User
        admins = db.query(User).filter(User.role == "admin").all()
        for admin in admins:
            notification = Notification(
                user_id=admin.id,
                type="secondary_hazard_confirmed",
                title="Active hazard confirmed during visual review",
                message=(
                    f"A reporter confirmed an unreported hazard on report #{report_id}: "
                    f"{observation}"
                ),
                metadata=json.dumps({
                    "report_id": report_id,
                    "observation": observation
                }),
                is_read=False,
                created_at=datetime.utcnow()
            )
            db.add(notification)
        db.flush()
        print(f"[vision_conversation] secondary hazard notification sent to {len(admins)} admins")
    except Exception as e:
        print(f"[vision_conversation] supervisor notification failed: {e}")


def _fallback_assessment() -> dict:
    """Safe fallback when LLM assessment fails."""
    return {
        "resolution": "confirmed",
        "agent_response": "Thanks, I've noted that on the report.",
        "amendment": None,
        "secondary_flag": None
    }


def _parse_json(raw: str) -> any:
    """Safely parse JSON from LLM output, stripping think blocks and fences."""
    if not raw:
        return {}

    raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
    raw = re.sub(r"```(?:json)?", "", raw).replace("```", "").strip()

    for start_char, end_char in [("{", "}"), ("[", "]")]:
        start = raw.find(start_char)
        end = raw.rfind(end_char)
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(raw[start:end + 1])
            except json.JSONDecodeError:
                continue

    return {}