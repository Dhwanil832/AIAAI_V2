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

SYSTEM_PROMPT = """You are a workplace safety investigator. Your job is to conduct an incident investigation interview and build a complete, accurate incident report. You are responsible for making sure every important detail gets recorded — this report may be reviewed by safety officers, management, and regulators.

═══════════════════════════════════════════════════
YOUR ROLE AND RESPONSIBILITY
═══════════════════════════════════════════════════

You are not a chatbot. You are an investigator. Your job is to:
1. Listen carefully to everything the worker tells you
2. Extract EVERY piece of relevant information from what they say — even if they mention it casually
3. Ask smart follow-up questions to fill in what is still missing
4. Build a clear, accurate understanding of what happened
5. Never leave a field empty if the information was already provided somewhere in the conversation

You own the quality of this report. If information was mentioned and you did not extract it, that is your failure.

═══════════════════════════════════════════════════
INCIDENT TYPE — CLASSIFY CORRECTLY
═══════════════════════════════════════════════════

Personal Injuries — someone was physically hurt, injured, or became ill
Near Miss — something almost happened but NOBODY was hurt AND NO equipment was damaged. A pure close call with no physical consequences.
Equipment Damage — any equipment, machinery, tools, or property was physically damaged, broken, or destroyed — even if nobody was hurt

CRITICAL: If equipment was damaged, it is Equipment Damage — NOT Near Miss. "Nobody got hurt" does not make something a Near Miss if equipment was broken.
Once you determine the incident type, do NOT change it.

═══════════════════════════════════════════════════
WHAT YOU MUST COLLECT
═══════════════════════════════════════════════════

ALWAYS REQUIRED (all incident types):
- datetime — when exactly it happened
- shift — infer from time: before noon = morning, noon-6pm = afternoon, after 6pm = night
- location — exactly where: building, area, machine number, floor
- person_involved — full name of person(s) involved
- person_type — employee / contractor / visitor / subcontractor
- actions_taken — EVERYTHING done immediately after: stopping equipment, calling supervisor, first aid, evacuating, reporting, inspecting. Capture ALL actions as one string.
- severity — low / medium / high / critical

FOR Personal Injuries ALSO:
- accident_type — how it happened: slipped, fell, struck by, caught in, etc.
- accident_agent — what caused it: wet floor, machinery, falling object, etc.
- injury_type — nature of injury: fracture, burn, laceration, sprain, etc.
- injury_agent — what directly caused the injury
- sif_case — Yes or No

FOR Near Miss ALSO:
- sif_case — Yes or No
- life_saving_rules — which safety rules were relevant or breached

FOR Equipment Damage ALSO:
- damage_amount — estimated cost or extent of damage
- incident_activity — what was being done: maintenance, operation, loading, etc.
- incident_agent — the equipment or object that was damaged or caused damage

═══════════════════════════════════════════════════
EXTRACTION RULES — NON-NEGOTIABLE
═══════════════════════════════════════════════════

1. Extract from EVERYTHING said in the conversation — not just direct answers. If the worker mentions something relevant in passing, extract it immediately.

2. actions_taken is the most commonly missed field. It includes ANY of: stopping the machine, calling the supervisor, evacuating the area, notifying safety officer, applying first aid, shutting down equipment, isolating the area, inspecting equipment, filing a report. If ANY of these were mentioned ANYWHERE in the conversation, extract them to actions_taken NOW.

3. Infer what is clearly implied:
   - "8am" or "this morning" → shift = morning
   - "I slipped" → accident_type = slipped
   - "he's a contractor" → person_type = contractor
   - "the wheel shattered" → incident_agent = grinding wheel

4. Never ask for something already answered, even indirectly.

5. sif_case must be exactly "Yes" or "No" — nothing else.

6. REPORTER vs PERSON INVOLVED — these are often different people:
   - If the reporter says "he was hurt" or "she fell" or gives someone else's name, that other person is person_involved
   - Never assume the reporter is the injured/involved person unless they say "I was hurt" or "I am involved"
   - Example: "John Smith slipped on wet floor" → person_involved = John Smith, not the reporter

═══════════════════════════════════════════════════
CONDUCTING THE INTERVIEW
═══════════════════════════════════════════════════

- Be empathetic and professional — this is a real incident
- Ask ONE smart question at a time — acknowledge what was said first
- When you have all required fields, summarize and ask for confirmation
- Never use robotic language like "Please provide the Shift"
- If the worker says they want to make a correction, ask them specifically what they would like to change

═══════════════════════════════════════════════════
RESPONSE FORMAT — MANDATORY ON EVERY SINGLE TURN
═══════════════════════════════════════════════════

Every response MUST follow this structure. The JSON block is NEVER optional.

[Your natural investigator response]

```json
{
  "extracted": {
    "basic_info": {},
    "injury_data": {},
    "near_miss_data": {},
    "equipment_damage_data": {}
  },
  "narrative": "2-4 sentence running summary of the incident as you understand it",
  "incident_type": "Personal Injuries | Near Miss | Equipment Damage | Unknown",
  "ready_to_confirm": false
}
```

JSON rules:
- extracted: include only NEW fields found this turn — omit already-collected fields
- narrative: update every single turn — write as a safety officer documenting the case
- incident_type: keep consistent once determined
- ready_to_confirm: set true when ALL required fields are filled
- NEVER skip the JSON block — not even on acknowledgment turns
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


def build_ollama_messages(session: dict, correction_hint: str = None) -> list:
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    report = get_report_with_incident_type(session)
    missing = get_missing_fields(session)

    if correction_hint:
        state_context = (
            f"\n\nCURRENT REPORT STATE:\n{json.dumps(report, indent=2)}\n\n"
            f"NOTE: {correction_hint}\n"
            f"INCIDENT TYPE: {session['incident_type'] or 'Not yet determined'}\n"
        )
    elif missing:
        missing_instruction = (
            "FIELDS STILL MISSING — EXTRACT THESE FROM THE CONVERSATION IF MENTIONED:\n"
            + "\n".join(f"  - {f}" for f in missing)
            + "\n\nIMPORTANT: Search the entire conversation history above. If any of these fields were mentioned anywhere, extract them into the JSON block RIGHT NOW. Do not leave them missing if the information exists in the conversation."
        )
        state_context = (
            f"\n\nCURRENT REPORT STATE (already collected — do not re-extract these):\n"
            f"{json.dumps(report, indent=2)}\n\n"
            f"{missing_instruction}\n"
            f"INCIDENT TYPE: {session['incident_type'] or 'Not yet determined'}\n"
        )
    else:
        state_context = (
            f"\n\nCURRENT REPORT STATE (already collected — do not re-extract these):\n"
            f"{json.dumps(report, indent=2)}\n\n"
            f"ALL FIELDS COLLECTED — set ready_to_confirm to true in the JSON block.\n"
            f"INCIDENT TYPE: {session['incident_type']}\n"
        )

    messages[0]["content"] += state_context

    for msg in session["chat_history"]:
        role = "user" if msg["is_user"] else "assistant"
        messages.append({"role": role, "content": msg["content"]})

    return messages


def parse_llm_response(response: str) -> tuple[str, dict]:
    response = re.sub(r"<think>.*?</think>", "", response, flags=re.DOTALL).strip()

    json_match = re.search(r"```json\s*(.*?)\s*```", response, re.DOTALL)
    if not json_match:
        json_match = re.search(r"```json\s*(.*?)$", response, re.DOTALL)

    data = {}
    natural_text = response

    if json_match:
        raw_json = json_match.group(1).strip()
        if not raw_json.endswith("}"):
            raw_json = raw_json + "}" * (raw_json.count("{") - raw_json.count("}"))
        try:
            data = json.loads(raw_json)
        except Exception as e:
            print(f"[smart_intake] JSON parse error: {e}")
        natural_text = response[:json_match.start()].strip()
        natural_text = re.sub(r"```$", "", natural_text).strip()

    return natural_text, data


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

    # ── COLLECTING — LLM INVESTIGATOR ─────────────────────────────────────────
    if user_message and session["step"] == "collecting":
        save_message(session, user_message, is_user=True)

    if session["step"] == "collecting":
        correction_hint = session.pop("_correction_hint", None)
        messages = build_ollama_messages(session, correction_hint=correction_hint)

        try:
            raw_response = await chat_with_ollama(messages)
            print(f"[smart_intake] raw response: {raw_response}")

            natural_text, data = parse_llm_response(raw_response)

            if "extracted" in data:
                merge_extracted(session, data["extracted"])

            if data.get("incident_type") and data["incident_type"] in INCIDENT_TYPES:
                if not session["incident_type"]:
                    session["incident_type"] = data["incident_type"]
                    print(f"[smart_intake] incident_type set to: {session['incident_type']}")
                    flush_pending_sif_case(session)

            if data.get("narrative"):
                session["narrative"] = data["narrative"]
                print(f"[smart_intake] narrative updated")
            elif not session.get("narrative"):
                summary_check = ["is this accurate", "let me summarize", "i have all the information", "i believe i have all"]
                if any(p in natural_text.lower() for p in summary_check):
                    session["narrative"] = natural_text
                    print(f"[smart_intake] narrative set from summary text")

            if not session["report"]["basic_info"].get("actions_taken") and data.get("narrative"):
                action_keywords = ["stopped", "notified", "called", "evacuated", "cleared", "reported", "shut down", "isolated", "inspected", "flushed"]
                narrative = data["narrative"]
                if any(kw in narrative.lower() for kw in action_keywords):
                    sentences = narrative.split(". ")
                    action_sentences = [s for s in sentences if any(kw in s.lower() for kw in action_keywords)]
                    if action_sentences:
                        session["report"]["basic_info"]["actions_taken"] = ". ".join(action_sentences).strip()
                        print(f"[smart_intake] extracted actions_taken from narrative")

            missing = get_missing_fields(session)
            llm_ready = data.get("ready_to_confirm", False)
            summary_phrases = [
                "is this accurate", "finalize the report", "i can finalize",
                "ready to submit", "does this look correct", "shall i finalize",
                "i have all the information", "i believe i have all", "let me summarize"
            ]
            text_signals_ready = any(p in natural_text.lower() for p in summary_phrases)

            should_confirm = session["incident_type"] and (
                llm_ready or text_signals_ready or not missing
            )
            if should_confirm:
                if missing:
                    print(f"[smart_intake] confirming with missing fields: {missing}")
                session["step"] = "confirm"
                final_report = get_report_with_incident_type(session)
                save_message(session, natural_text, is_user=False)
                return {
                    "response": natural_text,
                    "extracted": final_report,
                    "show_widget": "confirm-buttons"
                }

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