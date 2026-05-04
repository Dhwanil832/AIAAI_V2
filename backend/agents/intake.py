from typing import Optional
from agents.extractor import extract_fields, infer_incident_type
from agents.flagging import check_flags
from core.ollama import generate_summary
import copy

SESSIONS = {}

INCIDENT_TYPE_OPTIONS = [
    "Personal Injuries",
    "Near Miss",
    "Equipment Damage"
]

REQUIRED_FIELDS = {
    "basic_info": ["datetime", "shift", "location", "person_involved", "person_type", "actions_taken", "severity"],
    "injury_data": ["accident_type", "accident_agent", "injury_type", "injury_agent", "sif_case"],
    "near_miss_data": ["sif_case", "life_saving_rules"],
    "equipment_damage_data": ["damage_amount", "activity_type", "incident_activity", "incident_agent"]
}

FIELD_TO_SECTION = {}
for _section, _fields in REQUIRED_FIELDS.items():
    for _field in _fields:
        if _field not in FIELD_TO_SECTION:
            FIELD_TO_SECTION[_field] = _section

WIDGET_MAP = {
    "datetime": "datetime-picker",
    "shift": None,
    "location": None,
    "person_involved": None,
    "person_type": "person-type-picker",
    "actions_taken": None,
    "severity": "severity-picker",
    "accident_type": "accident-type-picker",
    "accident_agent": "accident-agent-picker",
    "injury_type": "injury-type-picker",
    "injury_agent": "injury-agent-picker",
    "sif_case": "sif-case-picker",
    "life_saving_rules": "life-saving-rules-picker",
    "damage_amount": "damage-amount-picker",
    "activity_type": "activity-type-picker",
    "incident_activity": "incident-activity-picker",
    "incident_agent": "equipment-incident-agent-picker",
}

SKIP_PHRASES = [
    "skip", "i don't know", "i dont know", "not sure", "unknown",
    "n/a", "na", "not applicable", "don't know", "no idea",
    "not available", "pass", "skip this", "leave it"
]


def is_skip_message(message: str) -> bool:
    return message.strip().lower() in SKIP_PHRASES


def get_session(session_id: str) -> dict:
    if session_id not in SESSIONS:
        SESSIONS[session_id] = {
            "step": "greet",
            "incident_type": "",
            "ollama_initialized": False,
            "last_question": None,
            "pending_description": None,
            "inferred_incident_type": None,
            "generated_summary": None,      # Stores LLM-generated summary for context_document
            "vision_context": [],           # Pending vision observations to confirm with reporter
            "report": {
                "basic_info": {},
                "injury_data": {},
                "near_miss_data": {},
                "equipment_damage_data": {}
            },
            "chat_history": [],
            "skip_count": 0
        }
    return SESSIONS[session_id]


def clear_session(session_id: str):
    if session_id in SESSIONS:
        del SESSIONS[session_id]


def save_message(session: dict, content: str, is_user: bool):
    session["chat_history"].append({
        "content": content,
        "is_user": is_user
    })


def get_required_sections(incident_type: str) -> list:
    sections = ["basic_info"]
    if incident_type == "Personal Injuries":
        sections.append("injury_data")
    elif incident_type == "Near Miss":
        sections.append("near_miss_data")
    elif incident_type == "Equipment Damage":
        sections.append("equipment_damage_data")
    return sections


def find_next_missing_field(session: dict) -> tuple[Optional[str], Optional[str]]:
    incident_type = session["incident_type"]
    required_sections = get_required_sections(incident_type)
    report = session["report"]

    for section in required_sections:
        for field in REQUIRED_FIELDS[section]:
            value = report[section].get(field, "")
            if not value:
                return section, field

    return None, None


def merge_extracted(session: dict, extracted: dict):
    for section, fields in extracted.items():
        if not isinstance(fields, dict):
            continue
        for key, value in fields.items():
            if key == "incident_type":
                continue
            if not (isinstance(value, str) and value.strip()):
                continue
            canonical_section = FIELD_TO_SECTION.get(key)
            if not canonical_section:
                continue
            if not session["report"][canonical_section].get(key):
                session["report"][canonical_section][key] = value.strip()
                print(f"[intake] wrote {canonical_section}.{key} = '{value.strip()}'")


def get_report_with_incident_type(session: dict) -> dict:
    report = copy.deepcopy(session["report"])
    report["basic_info"]["incident_type"] = session["incident_type"]
    return report


def pop_next_vision_observation(session: dict) -> Optional[dict]:
    """
    Returns and removes the highest priority pending vision observation
    from session["vision_context"], or None if the list is empty.
    """
    vision_context = session.get("vision_context", [])
    if not vision_context:
        return None
    observation = vision_context.pop(0)
    session["vision_context"] = vision_context
    return observation


def build_vision_aware_question(field_label: str, vision_observation: Optional[dict]) -> str:
    """
    Build the next field question, naturally incorporating a vision observation
    if one is pending. The reporter should not feel a seam between the two.

    If no vision observation is pending, returns the standard field question.
    If one is pending, the vision message is returned as the question — the
    extractor will pick up the field confirmation from the reporter's reply.
    """
    if not vision_observation:
        return f"Could you please provide the {field_label}?"

    # Use the vision agent's pre-phrased natural message
    reporter_message = vision_observation.get("reporter_message", "")
    if reporter_message:
        return reporter_message

    # Fallback — plain observation text
    obs_text = vision_observation.get("observation", {}).get("observation", "")
    if obs_text:
        return f"I noticed {obs_text.lower()} — can you tell me more about that?"

    return f"Could you please provide the {field_label}?"


async def process_message(
    session_id: str,
    user_message: str = None,
    button_choice: str = None,
    current_data: dict = None
) -> dict:
    session = get_session(session_id)

    # Apply any widget data sent from frontend
    if current_data:
        for section in ["basic_info", "injury_data", "near_miss_data", "equipment_damage_data"]:
            if section in current_data and current_data[section]:
                for key, value in current_data[section].items():
                    if key == "incident_type":
                        continue
                    if value and isinstance(value, str) and value.strip():
                        if not session["report"][section].get(key):
                            session["report"][section][key] = value.strip()

    # ── GREETING ─────────────────────────────────────────────────────────────
    if session["step"] == "greet" and not user_message and not button_choice:
        greeting = "Hi, I'm your Safety Chatbot. How can I help you today?"
        save_message(session, greeting, is_user=False)
        session["step"] = "await_incident_type"
        return {
            "response": greeting,
            "show_widget": None,
            "extracted": None,
            "options": INCIDENT_TYPE_OPTIONS + ["Report an incident"]
        }

    # ── INCIDENT TYPE BUTTON ──────────────────────────────────────────────────
    if button_choice:
        # Confirm inferred incident type
        if button_choice == "confirm_incident_type" and session.get("inferred_incident_type"):
            session["incident_type"] = session["inferred_incident_type"]
            session["inferred_incident_type"] = None
            session["step"] = "collecting"
            session["last_question"] = None

            pending = session.pop("pending_description", None)
            if pending:
                try:
                    extracted = await extract_fields(pending, session["report"])
                    merge_extracted(session, extracted)
                except Exception as e:
                    print(f"[intake] extraction error on pending description: {e}")

            response = "Got it! Let me ask you a few more questions."
            save_message(session, response, is_user=False)

            section, field = find_next_missing_field(session)
            if section is None:
                session["step"] = "confirm"
                return {
                    "response": "Here's what I've collected so far. Does everything look correct?",
                    "extracted": get_report_with_incident_type(session),
                    "show_widget": "confirm-buttons"
                }

            field_label = field.replace("_", " ").title()

            # Check for pending vision observation
            vision_obs = pop_next_vision_observation(session)
            response = build_vision_aware_question(field_label, vision_obs)

            session["last_question"] = response
            save_message(session, response, is_user=False)
            return {
                "response": response,
                "extracted": get_report_with_incident_type(session),
                "show_widget": WIDGET_MAP.get(field) if not vision_obs else None
            }

        # User said inference was wrong — show incident type buttons again
        if button_choice == "wrong_incident_type":
            session["inferred_incident_type"] = None
            session["step"] = "await_incident_type"
            response = "No problem — which type best describes what happened?"
            save_message(session, response, is_user=False)
            return {
                "response": response,
                "show_widget": None,
                "extracted": get_report_with_incident_type(session),
                "options": INCIDENT_TYPE_OPTIONS
            }

        # Normal incident type selection from buttons
        if button_choice in INCIDENT_TYPE_OPTIONS:
            session["incident_type"] = button_choice
            session["step"] = "collecting"
            session["last_question"] = None
            save_message(session, button_choice, is_user=True)

            pending = session.pop("pending_description", None)
            if pending:
                try:
                    extracted = await extract_fields(pending, session["report"])
                    merge_extracted(session, extracted)
                except Exception as e:
                    print(f"[intake] extraction error on pending description: {e}")

            response = "Got it! Please describe what happened as much or as little as you have."
            save_message(session, response, is_user=False)
            return {
                "response": response,
                "show_widget": None,
                "extracted": get_report_with_incident_type(session)
            }

        # Report an incident button
        session["step"] = "collecting"
        session["last_question"] = None
        save_message(session, button_choice, is_user=True)
        response = "Got it! Please describe what happened as much or as little as you have."
        save_message(session, response, is_user=False)
        return {
            "response": response,
            "show_widget": None,
            "extracted": get_report_with_incident_type(session)
        }

    # Save user message to history
    if user_message:
        save_message(session, user_message, is_user=True)

    # ── CONFIRM INCIDENT TYPE STEP ────────────────────────────────────────────
    if session["step"] == "confirm_incident_type":
        if user_message and user_message.strip().lower() in ["yes", "correct", "right", "yeah", "yep", "confirm"]:
            session["incident_type"] = session["inferred_incident_type"]
            session["inferred_incident_type"] = None
            session["step"] = "collecting"
            session["last_question"] = None

            pending = session.pop("pending_description", None)
            if pending:
                try:
                    extracted = await extract_fields(pending, session["report"])
                    merge_extracted(session, extracted)
                except Exception as e:
                    print(f"[intake] extraction error on pending description: {e}")

            section, field = find_next_missing_field(session)
            if section is None:
                session["step"] = "confirm"
                response = "Here's what I've collected so far. Does everything look correct?"
                save_message(session, response, is_user=False)
                return {
                    "response": response,
                    "extracted": get_report_with_incident_type(session),
                    "show_widget": "confirm-buttons"
                }

            field_label = field.replace("_", " ").title()
            response = f"Could you please provide the {field_label}?"
            session["last_question"] = response
            save_message(session, response, is_user=False)
            return {
                "response": response,
                "extracted": get_report_with_incident_type(session),
                "show_widget": WIDGET_MAP.get(field)
            }
        else:
            session["inferred_incident_type"] = None
            session["step"] = "await_incident_type"
            response = "No problem — which type best describes what happened?"
            save_message(session, response, is_user=False)
            return {
                "response": response,
                "show_widget": None,
                "extracted": get_report_with_incident_type(session),
                "options": INCIDENT_TYPE_OPTIONS
            }

    # ── CONFIRMATION STEP ─────────────────────────────────────────────────────
    if session["step"] == "confirm":
        if user_message and user_message.lower() in ["yes", "confirm", "looks good", "looks correct"]:
            session["step"] = "summary"
            report = get_report_with_incident_type(session)

            # Generate LLM prose summary — falls back to structured list on failure
            summary_text = await generate_summary(report)
            session["generated_summary"] = summary_text

            response = f"{summary_text}\n\nDoes this summary look correct?"
            save_message(session, response, is_user=False)
            return {
                "response": response,
                "extracted": report,
                "show_widget": "summary-buttons",
                "summary": report
            }
        else:
            if user_message and " to " in user_message.lower():
                parts = user_message.lower().split(" to ", 1)
                field_name = parts[0].strip().replace(" ", "_")
                new_value = parts[1].strip()
                canonical_section = FIELD_TO_SECTION.get(field_name)
                if canonical_section:
                    session["report"][canonical_section][field_name] = new_value
            response = "Got it. Here's the updated information, does this look correct?"
            save_message(session, response, is_user=False)
            return {
                "response": response,
                "extracted": get_report_with_incident_type(session),
                "show_widget": "confirm-buttons"
            }

    # ── SUMMARY STEP ──────────────────────────────────────────────────────────
    if session["step"] == "summary":
        if user_message and user_message.lower() in ["yes", "confirm", "submit report"]:
            session["step"] = "submit"
            return {
                "response": "__SUBMIT__",
                "extracted": get_report_with_incident_type(session),
                "show_widget": None
            }
        elif user_message and " to " in user_message.lower():
            parts = user_message.lower().split(" to ", 1)
            field_name = parts[0].strip().replace(" ", "_")
            new_value = parts[1].strip()
            canonical_section = FIELD_TO_SECTION.get(field_name)
            if canonical_section:
                session["report"][canonical_section][field_name] = new_value

            # Re-generate summary after correction
            report = get_report_with_incident_type(session)
            summary_text = await generate_summary(report)
            session["generated_summary"] = summary_text

            response = f"{summary_text}\n\nDoes everything look correct now?"
            save_message(session, response, is_user=False)
            return {
                "response": response,
                "extracted": report,
                "show_widget": "summary-buttons"
            }
        else:
            response = "Does everything look correct? Click Submit Report to finalize."
            save_message(session, response, is_user=False)
            return {
                "response": response,
                "extracted": get_report_with_incident_type(session),
                "show_widget": "summary-buttons"
            }

    # ── FIELD EXTRACTION ──────────────────────────────────────────────────────
    if user_message and session["step"] in ["collecting", "await_incident_type"]:

        if not session["incident_type"] and session["step"] == "await_incident_type":
            try:
                if not session["ollama_initialized"]:
                    from core.ollama import reset_ollama_context
                    await reset_ollama_context()
                    session["ollama_initialized"] = True

                inferred_type, confidence = await infer_incident_type(user_message)

                if inferred_type != "Unknown" and confidence == "high":
                    session["pending_description"] = user_message
                    session["inferred_incident_type"] = inferred_type
                    session["step"] = "confirm_incident_type"

                    response = f"It sounds like this was a {inferred_type} incident. Is that correct?"
                    save_message(session, response, is_user=False)
                    return {
                        "response": response,
                        "show_widget": None,
                        "extracted": get_report_with_incident_type(session),
                        "options": ["Yes, that's correct", "That's not right"]
                    }
                else:
                    session["pending_description"] = user_message
                    response = "I wasn't sure what type of incident this was. Could you select the type?"
                    save_message(session, response, is_user=False)
                    return {
                        "response": response,
                        "show_widget": None,
                        "extracted": get_report_with_incident_type(session),
                        "options": INCIDENT_TYPE_OPTIONS
                    }

            except Exception as e:
                print(f"[intake] inference error: {e}")
                response = "Could you select the type of incident?"
                save_message(session, response, is_user=False)
                return {
                    "response": response,
                    "show_widget": None,
                    "extracted": get_report_with_incident_type(session),
                    "options": INCIDENT_TYPE_OPTIONS
                }

        # Handle skip
        if is_skip_message(user_message) and session.get("last_question"):
            section, field = find_next_missing_field(session)
            if section and field:
                session["report"][section][field] = "N/A"
                session["skip_count"] += 1
                print(f"[intake] skipped {section}.{field}")
        else:
            try:
                if not session["ollama_initialized"]:
                    from core.ollama import reset_ollama_context
                    await reset_ollama_context()
                    session["ollama_initialized"] = True

                extracted = await extract_fields(
                    user_message,
                    session["report"],
                    last_question=session.get("last_question")
                )
                merge_extracted(session, extracted)

            except Exception as e:
                print(f"[intake] extraction error: {e}")

        session["step"] = "collecting"

    # ── FIND NEXT MISSING FIELD ───────────────────────────────────────────────
    section, field = find_next_missing_field(session)

    if section is None:
        session["step"] = "confirm"
        session["last_question"] = None
        response = "Here's what I've collected so far. Does everything look correct?"
        save_message(session, response, is_user=False)
        return {
            "response": response,
            "extracted": get_report_with_incident_type(session),
            "show_widget": "confirm-buttons"
        }

    field_label = field.replace("_", " ").title()

    # Check for pending vision observation — fold into question naturally
    vision_obs = pop_next_vision_observation(session)
    response = build_vision_aware_question(field_label, vision_obs)

    session["last_question"] = response
    save_message(session, response, is_user=False)

    return {
        "response": response,
        "extracted": get_report_with_incident_type(session),
        "show_widget": WIDGET_MAP.get(field) if not vision_obs else None
    }