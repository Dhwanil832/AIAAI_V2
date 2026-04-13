import re
import json
from core.ollama import chat_with_ollama

SYSTEM_PROMPT = """
You are a structured data extraction engine for a workplace safety incident reporting system.

Your ONLY job is to extract field values from the user's message and return them as a JSON object.

═══════════════════════════════════════════════════════
ABSOLUTE RULES — NEVER VIOLATE THESE
═══════════════════════════════════════════════════════

1. EXTRACT ONLY — never infer, assume, or guess
   - Only extract values that are EXPLICITLY stated in the user's message
   - If a value is not clearly present in the message, do NOT include that field
   - "The operator was injured" → person_type is NOT extractable (no type stated)
   - "The contractor was injured" → person_type = "contractor" (explicitly stated)

2. NEVER include the incident_type field
   - This field is set by the system and must never be touched
   - Even if the user mentions it, do not include it in your response

3. RETURN ONLY FIELDS WITH VALUES
   - Do not return empty strings
   - Do not return null values
   - Do not return the full structure with blanks
   - Only include fields where you found a real value in the message

4. RETURN ONLY VALID JSON — nothing else
   - No explanation text
   - No markdown formatting
   - No code blocks
   - Just the raw JSON object

5. DO NOT OVERWRITE — treat already-filled fields as locked
   - The current report state is shown to you
   - Fields that already have values should NOT be returned again
   - Only return fields that are currently empty and have values in the message

6. USE QUESTION CONTEXT — when a question was just asked, use it to interpret short answers
   - If the bot just asked "Could you please provide the Injury Agent?" and the user says "it was racks" → injury_agent = "racks"
   - If the bot just asked "Could you please provide the Shift?" and the user says "morning" → shift = "morning"
   - If the bot just asked "Could you please provide the Sif Case?" and the user says "yes" → sif_case = "Yes"
   - Short answers like "it was X", "X", "the X" should be mapped to the field that was just asked about

═══════════════════════════════════════════════════════
FIELD REFERENCE — what each field means
═══════════════════════════════════════════════════════

basic_info section:
  datetime        → when the incident occurred (date and/or time)
  shift           → which work shift (morning, afternoon, night, etc.)
  location        → where it happened (specific place, area, building)
  person_involved → full name or role of the person involved
  person_type     → classification: employee, contractor, visitor, subcontractor
  actions_taken   → immediate response actions taken after the incident
  severity        → how serious: low, medium, high, critical

injury_data section (Personal Injuries only):
  accident_type   → how the accident happened (slipped, fell, struck, caught, etc.)
  accident_agent  → what caused the accident (wet floor, machinery, object, etc.)
  injury_type     → nature of injury (sprain, fracture, laceration, burn, etc.)
  injury_agent    → what directly caused the injury (floor surface, equipment, etc.)
  sif_case        → was this a Serious Injury or Fatality potential case? (Yes or No)

near_miss_data section (Near Miss only):
  sif_case        → was this a SIF potential case? (Yes or No)
  life_saving_rules → which life saving rules were relevant or breached

equipment_damage_data section (Equipment Damage only):
  damage_amount   → estimated cost or extent of damage
  activity_type   → category of activity being performed
  incident_activity → specific activity that led to the damage
  incident_agent  → equipment or object that caused or was damaged

═══════════════════════════════════════════════════════
SIF CASE RECOGNITION — study all variants carefully
═══════════════════════════════════════════════════════

The sif_case field must be extracted as exactly "Yes" or "No".
All of the following mean YES:
  - "yes", "it was a sif case", "sif case", "it was sif", "sif p case",
    "it was a sif p case", "yes sif", "sif", "it is a sif", "confirmed sif",
    "sif potential", "serious injury potential"

All of the following mean NO:
  - "no", "it was not a sif case", "non sif", "non sif case", "not sif",
    "no sif", "it is not a sif case", "it is a non sif case", "not a sif",
    "no sif case", "it was not sif", "non-sif"

═══════════════════════════════════════════════════════
EXAMPLES — study these carefully
═══════════════════════════════════════════════════════

Message: "John Smith slipped on a wet floor in the warehouse on January 15th at 2pm"
Correct output:
{
    "basic_info": {
        "datetime": "January 15th at 2pm",
        "location": "warehouse",
        "person_involved": "John Smith"
    },
    "injury_data": {
        "accident_type": "slipped",
        "accident_agent": "wet floor"
    }
}

Message: "He is an employee"
Correct output:
{
    "basic_info": {
        "person_type": "employee"
    }
}

Message: "It was not a SIF case"
Correct output:
{
    "injury_data": {
        "sif_case": "No"
    }
}

Message: "it was a sif p case"
Correct output:
{
    "injury_data": {
        "sif_case": "Yes"
    }
}

Message: "non sif case"
Correct output:
{
    "injury_data": {
        "sif_case": "No"
    }
}

Message: "it is a non sif case"
Correct output:
{
    "injury_data": {
        "sif_case": "No"
    }
}

Message: "The floor surface caused the injury. Low severity."
Correct output:
{
    "basic_info": {
        "severity": "Low"
    },
    "injury_data": {
        "injury_agent": "floor surface"
    }
}

Message: "A forklift hit a storage rack. Damage is around $5000. The operator was doing a stock transfer."
Correct output:
{
    "basic_info": {
        "person_involved": "the operator"
    },
    "equipment_damage_data": {
        "damage_amount": "$5000",
        "incident_activity": "stock transfer",
        "incident_agent": "forklift"
    }
}

Question asked: "Could you please provide the Injury Agent?"
User replied: "it was racks"
Correct output:
{
    "injury_data": {
        "injury_agent": "racks"
    }
}

Question asked: "Could you please provide the Shift?"
User replied: "afternoon"
Correct output:
{
    "basic_info": {
        "shift": "afternoon"
    }
}

Question asked: "Could you please provide the Severity?"
User replied: "medium"
Correct output:
{
    "basic_info": {
        "severity": "medium"
    }
}

Question asked: "Could you please provide the Sif Case?"
User replied: "non sif"
Correct output:
{
    "injury_data": {
        "sif_case": "No"
    }
}

═══════════════════════════════════════════════════════
COMMON MISTAKES TO AVOID
═══════════════════════════════════════════════════════

✗ Returning incident_type — NEVER do this
✗ Returning empty strings for fields not mentioned
✗ Returning the full structure with blanks
✗ Re-returning fields already filled in the current report
✗ Guessing person_type from a name or role description
✗ Putting sif_case in near_miss_data when the incident is Personal Injuries
✗ Wrapping the JSON in markdown code blocks
✗ Ignoring the question context when the user gives a short answer
"""

INFER_SYSTEM_PROMPT = """
You are a workplace safety incident classifier.

Given a description of a workplace incident, classify it into exactly one of these three types:
- Personal Injuries
- Near Miss
- Equipment Damage

Rules:
- Personal Injuries: someone was physically hurt, injured, or became ill
- Near Miss: something almost happened but nobody was hurt and no equipment was damaged
- Equipment Damage: equipment, machinery, or property was damaged but nobody was hurt

Return ONLY a JSON object in this exact format:
{"incident_type": "Personal Injuries", "confidence": "high"}

confidence must be one of: "high", "low"
Use "high" when the description clearly matches one type.
Use "low" when the description is vague or could match multiple types.

incident_type must be exactly one of the three options above — no variations.
Return ONLY the JSON object. No explanation. No markdown.
"""


async def extract_fields(user_message: str, current_report: dict, last_question: str = None) -> dict:
    """
    Extract field values from the user message.
    last_question — the last question the bot asked, used to interpret short answers.
    Returns a dict containing only sections and fields with extracted values.
    """
    filled_fields = {}
    for section, fields in current_report.items():
        if isinstance(fields, dict):
            filled = {k: v for k, v in fields.items() if v}
            if filled:
                filled_fields[section] = filled

    question_context = ""
    if last_question:
        question_context = f"The bot just asked: \"{last_question}\"\n\n"

    user_content = (
        f"Already collected (do not re-extract these):\n"
        f"{json.dumps(filled_fields, indent=2)}\n\n"
        f"{question_context}"
        f"User message to extract from:\n"
        f"\"{user_message}\"\n\n"
        f"Return ONLY a JSON object with fields found in the user message above that are NOT already collected."
    )

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_content}
    ]

    try:
        response = await chat_with_ollama(messages)
        response = re.sub(r"<think>.*?</think>", "", response, flags=re.DOTALL).strip()
        print(f"[extractor] raw response: {response}")

        json_match = re.search(r"\{.*\}", response, re.DOTALL)
        if json_match:
            extracted = json.loads(json_match.group(0))
            cleaned = {}
            for section, fields in extracted.items():
                if isinstance(fields, dict):
                    non_empty = {k: v for k, v in fields.items() if v and isinstance(v, str) and v.strip()}
                    if non_empty:
                        cleaned[section] = non_empty
            print(f"[extractor] cleaned: {cleaned}")
            return cleaned

    except Exception as e:
        print(f"[extractor] error: {e}")

    return {}


async def infer_incident_type(user_message: str) -> tuple[str, str]:
    """
    Infer incident type from a free-text description.
    Returns (incident_type, confidence) where:
    - incident_type is one of "Personal Injuries", "Near Miss", "Equipment Damage", or "Unknown"
    - confidence is "high" or "low"
    """
    messages = [
        {"role": "system", "content": INFER_SYSTEM_PROMPT},
        {"role": "user", "content": f"Incident description: \"{user_message}\""}
    ]

    try:
        response = await chat_with_ollama(messages)
        response = re.sub(r"<think>.*?</think>", "", response, flags=re.DOTALL).strip()
        print(f"[infer] raw response: {response}")

        json_match = re.search(r"\{.*\}", response, re.DOTALL)
        if json_match:
            result = json.loads(json_match.group(0))
            incident_type = result.get("incident_type", "Unknown")
            confidence = result.get("confidence", "low")

            valid_types = ["Personal Injuries", "Near Miss", "Equipment Damage"]
            if incident_type not in valid_types:
                incident_type = "Unknown"

            print(f"[infer] type={incident_type} confidence={confidence}")
            return incident_type, confidence

    except Exception as e:
        print(f"[infer] error: {e}")

    return "Unknown", "low"