import re
import json
import copy
from core.ollama import chat_with_ollama

SESSIONS = {}

INCIDENT_TYPES = ["Personal Injuries", "Near Miss", "Equipment Damage"]

REQUIRED_FIELDS = {
    "basic_info": ["datetime", "shift", "location", "person_involved", "person_type", "actions_taken", "severity"],
    "injury_data": ["accident_type", "accident_agent", "injury_type", "injury_agent", "sif_case"],
    "near_miss_data": ["sif_case", "life_saving_rules"],
    "equipment_damage_data": ["damage_amount", "incident_activity", "incident_agent"]
}

FIELD_TO_SECTION = {}
for _section, _fields in REQUIRED_FIELDS.items():
    for _field in _fields:
        if _field not in FIELD_TO_SECTION:
            FIELD_TO_SECTION[_field] = _section

# ── CALL 1: CONVERSATION PROMPT ───────────────────────────────────────────────
# Pure investigator — no JSON, no extraction. Just conducts the interview.

CONVERSATION_PROMPT = """You are a workplace safety investigator conducting an incident investigation interview. Your job is to talk to the worker naturally, gather information, and ask smart follow-up questions.

═══════════════════════════════════════════════════
INCIDENT TYPES
═══════════════════════════════════════════════════

Personal Injuries — someone was physically hurt or became ill
Near Miss — a close call with no injuries and no equipment damage
Equipment Damage — any equipment, machinery, or property was damaged

═══════════════════════════════════════════════════
WHAT YOU NEED TO COLLECT
═══════════════════════════════════════════════════

Always required:
- When it happened (date and time)
- Where it happened (exact location)
- Who was involved (full name)
- Their role (employee / contractor / visitor)
- What was done immediately after (actions taken)
- Severity (low / medium / high / critical)

For Personal Injuries also: how it happened, what caused it, what injury, what caused the injury, SIF case (Yes/No)
For Near Miss also: SIF case (Yes/No), which life saving rules were relevant
For Equipment Damage also: estimated damage cost, what activity was happening, what equipment was damaged

═══════════════════════════════════════════════════
HOW TO CONDUCT THE INTERVIEW
═══════════════════════════════════════════════════

- Be empathetic and professional — this is a real incident
- HARD LIMIT: Ask maximum TWO questions per response. If many things are missing, ask only the 2 most important.
- Never ask for something already answered, even indirectly
- Never use robotic language like "Please provide the Shift"
- When the worker says they want to make a correction, ask them what they would like to change
- When you believe you have everything, summarize what you have and ask the worker to confirm

RESPOND NATURALLY. Do not include any JSON, brackets, or structured data in your response.

IMPORTANT — SIGNAL WHEN DONE:
When you believe ALL required fields have been covered and you are summarizing for confirmation, add this exact line at the very end of your response (after your message):
CONV_READY
Do not add this line unless you are genuinely summarizing and asking the worker to confirm.
"""

# ── CALL 2: EXTRACTOR PROMPT ───────────────────────────────────────────────────
# Pure extraction — reads the conversation and pulls out fields as JSON only.

EXTRACTOR_PROMPT = """You are a data extraction system for workplace incident reports. You will be given a conversation between a safety investigator and a worker, plus a running narrative summary. Your job is to extract field values from everything that has been said.

═══════════════════════════════════════════════════
FIELDS TO EXTRACT
═══════════════════════════════════════════════════

basic_info:
- datetime — exact date and time mentioned
- shift — morning (before noon) / afternoon (noon-6pm) / night (after 6pm). Infer from time if given.
- location — where it happened
- person_involved — full name of the person involved in the incident (NOT the reporter unless they say "I was hurt")
- person_type — employee / contractor / visitor / subcontractor
- actions_taken — ALL immediate actions: first aid, calling supervisor, stopping equipment, evacuating, inspecting. One string.
- severity — low / medium / high / critical

injury_data (Personal Injuries only):
- accident_type — how it happened: slipped, fell, struck by, caught in, etc.
- accident_agent — what caused it: wet floor, machinery, falling object, etc.
- injury_type — nature of injury: fracture, sprain, burn, laceration, etc.
- injury_agent — what directly caused the injury
- sif_case — exactly "Yes" or "No"

near_miss_data (Near Miss only):
- sif_case — exactly "Yes" or "No"
- life_saving_rules — which safety rules were relevant or breached

equipment_damage_data (Equipment Damage only):
- damage_amount — estimated cost or extent of damage
- incident_activity — what was being done: maintenance, operation, loading, moving materials, etc.
- incident_agent — what equipment was damaged or caused damage

═══════════════════════════════════════════════════
EXTRACTION RULES
═══════════════════════════════════════════════════

1. Extract from EVERYTHING in the conversation — casual mentions, passing references, anything.
2. Infer what is clearly implied: "8am" → shift=morning, "he's a contractor" → person_type=contractor
3. NEVER overwrite a field already marked as collected
4. sif_case must be exactly "Yes" or "No" — nothing else
5. person_involved is the person hurt/involved, NOT the reporter
6. actions_taken: include ALL actions mentioned anywhere in the conversation as one string
7. Only extract fields you are confident about — do not guess

═══════════════════════════════════════════════════
OUTPUT FORMAT
═══════════════════════════════════════════════════

Respond with ONLY a JSON object. No explanation, no text before or after, no markdown fences.

{
  "incident_type": "Personal Injuries | Near Miss | Equipment Damage | Unknown",
  "narrative": "2-4 sentence running summary written as a safety officer documenting the case",
  "extracted": {
    "basic_info": {},
    "injury_data": {},
    "near_miss_data": {},
    "equipment_damage_data": {}
  }
}

- extracted: include ONLY fields with values found this turn. Empty sections should be empty dicts {}.
- narrative: update every turn based on everything known so far
- incident_type: once determined, keep consistent
- Do NOT include fields already marked as collected
"""


def get_session(session_id: str) -> dict:
    if session_id not in SESSIONS:
        SESSIONS[session_id] = {
            "step": "greet",
            "incident_type": "",
            "narrative": "",
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


def get_missing_fields(session: dict) -> list:
    incident_type = session["incident_type"]
    if not incident_type:
        return list(REQUIRED_FIELDS["basic_info"])
    sections = get_required_sections(incident_type)
    missing = []
    for section in sections:
        for field in REQUIRED_FIELDS[section]:
            value = session["report"][section].get(field, "")
            if not value:
                missing.append(field)
    return missing


SIF_CASE_SECTION = {
    "Personal Injuries": "injury_data",
    "Near Miss": "near_miss_data",
    "Equipment Damage": "equipment_damage_data",
}


def merge_extracted(session: dict, extracted: dict):
    incident_type = session.get("incident_type", "")
    for section, fields in extracted.items():
        if not isinstance(fields, dict):
            continue
        for key, value in fields.items():
            if key == "incident_type":
                continue
            if not (isinstance(value, str) and value.strip()):
                continue
            if key == "sif_case":
                if incident_type:
                    canonical_section = SIF_CASE_SECTION.get(incident_type, "injury_data")
                else:
                    session.setdefault("_pending_sif_case", value.strip())
                    print(f"[smart_intake] buffered sif_case = '{value.strip()}' (incident_type unknown)")
                    continue
            else:
                canonical_section = FIELD_TO_SECTION.get(key, section)
            if canonical_section not in session["report"]:
                continue
            if not session["report"][canonical_section].get(key):
                session["report"][canonical_section][key] = value.strip()
                print(f"[smart_intake] wrote {canonical_section}.{key} = '{value.strip()}'")


def flush_pending_sif_case(session: dict):
    pending = session.pop("_pending_sif_case", None)
    if pending and session.get("incident_type"):
        canonical_section = SIF_CASE_SECTION.get(session["incident_type"], "injury_data")
        if not session["report"][canonical_section].get("sif_case"):
            session["report"][canonical_section]["sif_case"] = pending
            print(f"[smart_intake] flushed sif_case to {canonical_section} = '{pending}'")


def get_report_with_incident_type(session: dict) -> dict:
    report = copy.deepcopy(session["report"])
    report["basic_info"]["incident_type"] = session["incident_type"]
    return report


def build_conversation_messages(session: dict, correction_hint: str = None) -> list:
    """Call 1 — conversational investigator. No JSON, no extraction pressure."""
    report = get_report_with_incident_type(session)
    missing = get_missing_fields(session)

    if correction_hint:
        state_context = (
            f"\n\nCURRENT REPORT STATE:\n{json.dumps(report, indent=2)}\n\n"
            f"NOTE: {correction_hint}\n"
            f"INCIDENT TYPE: {session['incident_type'] or 'Not yet determined'}\n"
        )
    elif missing:
        state_context = (
            f"\n\nCURRENT REPORT STATE (already collected):\n{json.dumps(report, indent=2)}\n\n"
            f"STILL MISSING: {', '.join(missing)}\n"
            f"Ask about the most important missing fields — maximum TWO questions.\n"
            f"INCIDENT TYPE: {session['incident_type'] or 'Not yet determined'}\n"
        )
    else:
        state_context = (
            f"\n\nCURRENT REPORT STATE:\n{json.dumps(report, indent=2)}\n\n"
            f"ALL FIELDS COLLECTED. Summarize what you have and ask the worker to confirm.\n"
            f"INCIDENT TYPE: {session['incident_type']}\n"
        )

    messages = [{"role": "system", "content": CONVERSATION_PROMPT + state_context}]
    for msg in session["chat_history"]:
        role = "user" if msg["is_user"] else "assistant"
        messages.append({"role": role, "content": msg["content"]})
    return messages


def build_extractor_messages(session: dict) -> list:
    """Call 2 — pure extractor. Gets full conversation + narrative. Returns JSON only."""
    report = get_report_with_incident_type(session)
    already_collected = {
        section: {k: v for k, v in fields.items() if v}
        for section, fields in report.items()
        if isinstance(fields, dict)
    }

    narrative = session.get("narrative", "")
    state_context = (
        f"\n\nALREADY COLLECTED (do not re-extract these):\n{json.dumps(already_collected, indent=2)}\n\n"
        f"RUNNING NARRATIVE:\n{narrative}\n\n"
        f"INCIDENT TYPE SO FAR: {session['incident_type'] or 'Unknown'}\n\n"
        f"Now read the full conversation below and extract any new field values.\n"
    )

    messages = [{"role": "system", "content": EXTRACTOR_PROMPT + state_context}]
    for msg in session["chat_history"]:
        role = "user" if msg["is_user"] else "assistant"
        messages.append({"role": role, "content": msg["content"]})
    return messages


def parse_extractor_response(response: str) -> dict:
    """Parse the extractor's JSON-only response."""
    response = re.sub(r"<think>.*?</think>", "", response, flags=re.DOTALL).strip()
    response = re.sub(r"^```json\s*", "", response).strip()
    response = re.sub(r"\s*```$", "", response).strip()

    try:
        return json.loads(response)
    except Exception:
        match = re.search(r"\{.*\}", response, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except Exception as e:
                print(f"[extractor] JSON parse error: {e}")
    return {}


async def process_message(
    session_id: str,
    user_message: str = None,
    button_choice: str = None,
    current_data: dict = None
) -> dict:
    session = get_session(session_id)

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
        greeting = (
            "Hi, I'm your Safety Investigation Assistant. "
            "I'm here to help document what happened. "
            "Please tell me about the incident — describe it in your own words."
        )
        save_message(session, greeting, is_user=False)
        session["step"] = "collecting"
        return {
            "response": greeting,
            "show_widget": None,
            "extracted": get_report_with_incident_type(session),
            "options": None
        }

    # ── CONFIRM STEP ─────────────────────────────────────────────────────────
    if session["step"] == "confirm":
        if button_choice == "confirm" or (user_message and user_message.lower() in ["yes", "confirm", "looks good", "looks correct"]):
            session["step"] = "summary"
            report = get_report_with_incident_type(session)
            narrative = session.get("narrative", "").strip()
            if not narrative:
                from core.ollama import generate_summary
                narrative = await generate_summary(report)
            session["generated_summary"] = narrative
            save_message(session, narrative, is_user=False)
            return {
                "response": narrative,
                "extracted": report,
                "show_widget": "summary-buttons",
                "summary": report
            }
        else:
            if user_message:
                save_message(session, user_message, is_user=True)
            session["step"] = "collecting"
            session["_correction_hint"] = "The worker reviewed the collected information and wants to make a correction. Ask them specifically what they would like to change, then update the report accordingly."

    # ── SUMMARY STEP ─────────────────────────────────────────────────────────
    if session["step"] == "summary":
        if button_choice == "submit" or (user_message and user_message.lower() in ["yes", "confirm", "submit report"]):
            session["step"] = "submit"
            return {
                "response": "__SUBMIT__",
                "extracted": get_report_with_incident_type(session),
                "show_widget": None
            }
        else:
            if user_message:
                save_message(session, user_message, is_user=True)
            session["step"] = "collecting"
            session["_correction_hint"] = "The worker wants to make a correction to the report. Ask them what they would like to change."

    # ── COLLECTING — PARALLEL LLM CALLS ──────────────────────────────────────
    if user_message and session["step"] == "collecting":
        save_message(session, user_message, is_user=True)

    if session["step"] == "collecting":
        correction_hint = session.pop("_correction_hint", None)
        conv_messages = build_conversation_messages(session, correction_hint=correction_hint)
        ext_messages = build_extractor_messages(session)

        try:
            # Fire sequentially — Ollama cannot handle parallel calls to same model
            conv_response = await chat_with_ollama(conv_messages)
            ext_response = await chat_with_ollama(ext_messages)

            print(f"[conversation] {conv_response[:120]}...")
            print(f"[extractor] raw: {ext_response[:300]}...")

            # Parse extractor result
            ext_data = parse_extractor_response(ext_response)

            # Update incident_type from extractor
            if ext_data.get("incident_type") and ext_data["incident_type"] in INCIDENT_TYPES:
                if not session["incident_type"]:
                    session["incident_type"] = ext_data["incident_type"]
                    print(f"[smart_intake] incident_type set to: {session['incident_type']}")
                    flush_pending_sif_case(session)

            # Update narrative from extractor
            if ext_data.get("narrative"):
                session["narrative"] = ext_data["narrative"]
                print(f"[smart_intake] narrative updated")

            # Merge extracted fields
            if ext_data.get("extracted"):
                merge_extracted(session, ext_data["extracted"])

            # Strip any accidental JSON the conversation model might include
            natural_text = conv_response.strip()
            natural_text = re.sub(r"```json.*?```", "", natural_text, flags=re.DOTALL).strip()

            # Detect conversation ready signal
            conv_ready = "CONV_READY" in natural_text
            natural_text = natural_text.replace("CONV_READY", "").strip()

            # Check extractor completeness
            missing = get_missing_fields(session)
            ext_ready = session["incident_type"] and not missing

            print(f"[smart_intake] conv_ready={conv_ready} ext_ready={ext_ready} missing={missing}")

            # ── FOUR RULES ────────────────────────────────────────────────────
            # Rule 1: Both ready → confirm
            if conv_ready and ext_ready:
                print(f"[smart_intake] both ready → confirm")
                session["step"] = "confirm"
                save_message(session, natural_text, is_user=False)
                return {
                    "response": natural_text,
                    "extracted": get_report_with_incident_type(session),
                    "show_widget": "confirm-buttons"
                }

            # Rule 2: Neither ready → keep going normally
            if not conv_ready and not ext_ready:
                print(f"[smart_intake] neither ready → continuing")
                save_message(session, natural_text, is_user=False)
                return {
                    "response": natural_text,
                    "extracted": get_report_with_incident_type(session),
                    "show_widget": None,
                    "options": None
                }

            # Rule 3: Extractor ready, conversation not ready
            # Keep going — conversation may be picking up on something extractor missed
            # Extractor will update on next turn without wiping existing fields
            if ext_ready and not conv_ready:
                print(f"[smart_intake] extractor ready but conversation still asking → keep going")
                save_message(session, natural_text, is_user=False)
                return {
                    "response": natural_text,
                    "extracted": get_report_with_incident_type(session),
                    "show_widget": None,
                    "options": None
                }

            # Rule 4: Conversation ready, extractor not ready
            # Inject missing fields back into conversation so it asks about them
            if conv_ready and not ext_ready:
                print(f"[smart_intake] conversation ready but extractor missing {missing} → injecting")
                session["_correction_hint"] = (
                    f"The system detected these fields are still missing: {', '.join(missing)}. "
                    f"Please ask the worker about these specifically before confirming."
                )
                save_message(session, natural_text, is_user=False)
                return {
                    "response": natural_text,
                    "extracted": get_report_with_incident_type(session),
                    "show_widget": None,
                    "options": None
                }

            # Fallback
            save_message(session, natural_text, is_user=False)
            return {
                "response": natural_text,
                "extracted": get_report_with_incident_type(session),
                "show_widget": None,
                "options": None
            }

        except Exception as e:
            print(f"[smart_intake] LLM error: {e}")
            error_response = "I'm having trouble processing that. Could you describe what happened again?"
            save_message(session, error_response, is_user=False)
            return {
                "response": error_response,
                "extracted": get_report_with_incident_type(session),
                "show_widget": None
            }

    return {
        "response": "Please describe what happened.",
        "extracted": get_report_with_incident_type(session),
        "show_widget": None
    }