import json
import re
from datetime import datetime
from sqlalchemy.orm import Session
from models.vision import VisionThread
from models.notification import Notification
from core.ollama import chat_with_ollama

# ── Incident types where images almost never add value ────────────────────────
LOW_VALUE_TYPES = set()  # reserved for future tuning

# ── Minimum severity to trigger image request ─────────────────────────────────
# Reports below this threshold skip the gate unless SIF case is flagged
SEVERITY_PASS = {"medium", "high", "critical"}


async def run_vision_reasoning_gate(
    report_id: int,
    report_json: dict,
    incident_type: str,
    db: Session
) -> None:
    """
    Background task — runs after report submission.

    Reads the full report and decides whether visual documentation
    would materially help the investigation. If yes, creates a
    VisionThread and notifies the reporter.

    Conservative by design — if uncertain, does not fire.
    Better to miss an image request than to annoy reporters on minor incidents.
    """
    print(f"[vision_reasoning] gate running for report #{report_id}")

    try:
        result = await _assess_report(report_json, incident_type)

        if not result.get("warranted"):
            print(f"[vision_reasoning] images not warranted for report #{report_id}: {result.get('reason')}")
            return

        # Create the VisionThread
        thread = VisionThread(
            report_id=report_id,
            unfinished_report_id=None,
            trigger_context="post_submission",
            triggered_by_user_id=_get_reporter_user_id(report_id, db),
            image_paths=[],
            quality_ok=None,
            quality_reason=None,
            full_observations=[],
            priority_observation=None,
            conversation=[],
            resolution="pending",
            resolution_note=None,
            amendments=[],
            secondary_flags=[],
            status="open",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        db.add(thread)
        db.flush()  # get thread.id before creating notification

        # Create notification for the reporter
        notification = Notification(
            user_id=_get_reporter_user_id(report_id, db),
            type="vision_image_request",
            title="Photo requested for your report",
            message=result.get("notification_message", ""),
            metadata=json.dumps({
                "report_id": report_id,
                "thread_id": thread.id,
                "what_to_capture": result.get("what_to_capture", [])
            }),
            is_read=False,
            created_at=datetime.utcnow()
        )
        db.add(notification)
        db.commit()

        print(f"[vision_reasoning] thread #{thread.id} created, notification sent for report #{report_id}")

    except Exception as e:
        print(f"[vision_reasoning] gate failed for report #{report_id}: {e}")
        db.rollback()


async def _assess_report(report_json: dict, incident_type: str) -> dict:
    """
    Single LLM call — reads the report and decides if images are warranted.

    Returns:
    {
        "warranted": bool,
        "reason": str,
        "what_to_capture": [...],
        "notification_message": str
    }
    """
    basic = report_json.get("basic_info", {})
    injury = report_json.get("injury_data", {})
    near_miss = report_json.get("near_miss_data", {})
    equipment = report_json.get("equipment_damage_data", {})

    severity = basic.get("severity", "").lower()
    sif_case = (
        injury.get("sif_case") or
        near_miss.get("sif_case") or
        equipment.get("sif_case") or ""
    ).lower()
    actions_taken = basic.get("actions_taken", "").lower()
    location = basic.get("location", "")

    # Fast path — clearly not warranted
    if incident_type not in ("Personal Injuries", "Near Miss", "Equipment Damage"):
        return {"warranted": False, "reason": "unknown incident type"}

    if severity and severity not in SEVERITY_PASS and "sif" not in sif_case:
        return {"warranted": False, "reason": f"severity '{severity}' below threshold"}

    # Build report context for LLM
    field_lines = []

    def add(label, value):
        if value and str(value).strip().lower() not in ("", "n/a", "na", "none"):
            field_lines.append(f"- {label}: {value}")

    add("Incident Type", incident_type)
    add("Location", location)
    add("Severity", basic.get("severity", ""))
    add("SIF Case", sif_case)
    add("Actions Taken", basic.get("actions_taken", ""))
    add("Person Involved", basic.get("person_involved", ""))
    add("Accident Type", injury.get("accident_type", ""))
    add("Accident Agent", injury.get("accident_agent", ""))
    add("Injury Type", injury.get("injury_type", ""))
    add("Damage Amount", equipment.get("damage_amount", ""))
    add("Incident Activity", equipment.get("incident_activity", ""))
    add("Incident Agent", equipment.get("incident_agent", ""))

    fields_text = "\n".join(field_lines)

    system_prompt = (
        "You are a workplace safety investigator deciding whether to request "
        "photographic evidence for an incident report.\n\n"
        "Decide if a photo of the incident scene or equipment would materially "
        "help the investigation. Be conservative — only request images when they "
        "would genuinely add investigative value.\n\n"
        "Images ADD value when:\n"
        "- The incident involved physical damage to equipment or infrastructure\n"
        "- The mechanism of injury could be clarified by seeing the scene\n"
        "- The location or conditions are important to understand what happened\n"
        "- It is a SIF case or high/critical severity\n"
        "- Actions taken could be verified visually\n\n"
        "Images do NOT add value when:\n"
        "- It is a purely administrative or paperwork incident\n"
        "- The incident has no physical scene (e.g. verbal altercation only)\n"
        "- Severity is low and no SIF case is indicated\n\n"
        "If warranted, specify exactly what to photograph — be specific, not generic.\n\n"
        "Return ONLY valid JSON. No explanation. No markdown.\n\n"
        "JSON format:\n"
        "{\n"
        '  "warranted": true | false,\n'
        '  "reason": "one sentence explanation",\n'
        '  "what_to_capture": ["specific thing 1", "specific thing 2"],\n'
        '  "notification_message": "natural 2-sentence message to reporter explaining '
        'what photo to take and why — write as if from a safety officer, not a system"\n'
        "}\n\n"
        'If not warranted: {"warranted": false, "reason": "..."}'
    )

    user_prompt = f"Incident report:\n{fields_text}\n\nShould we request a photo?"

    try:
        raw = await chat_with_ollama(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
        )

        result = _parse_json(raw)

        if not isinstance(result, dict):
            return {"warranted": False, "reason": "parse error"}

        return result

    except Exception as e:
        print(f"[vision_reasoning] LLM call failed: {e}")
        return {"warranted": False, "reason": f"LLM error: {e}"}


def _get_reporter_user_id(report_id: int, db: Session) -> int:
    """Fetch the user_id of the report's creator."""
    from models.report import IncidentReport
    report = db.query(IncidentReport).filter(IncidentReport.id == report_id).first()
    if report:
        return report.user_id
    raise ValueError(f"Report #{report_id} not found")


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