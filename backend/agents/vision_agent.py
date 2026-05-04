import json
import re
from core.ollama import chat_with_ollama_vision, chat_with_ollama

# ── Context labels for logging ────────────────────────────────────────────────
VALID_CONTEXTS = {"cold_start", "mid_intake", "post_submission", "admin_review"}


# ── Public entry point ────────────────────────────────────────────────────────

async def analyze_image(
    image_b64: str,
    image_type: str,
    report_state: dict,
    trigger_context: str
) -> dict:
    """
    Core vision agent. Context-aware image analysis for safety investigations.

    image_b64       — raw base64 string, no data URI prefix
    image_type      — MIME type e.g. "image/jpeg"
    report_state    — current report dict (full or partial depending on context)
    trigger_context — "cold_start" | "mid_intake" | "post_submission" | "admin_review"

    Returns:
    {
        "quality_ok": bool,
        "quality_reason": str | None,
        "full_observations": [...],      # everything seen — for admin
        "priority_observation": {...},   # top one — drives reporter question
        "reporter_message": str,         # natural question for intake agent to use
        "field_suggestions": {...}       # cold_start + mid_intake only
    }
    """
    if trigger_context not in VALID_CONTEXTS:
        trigger_context = "post_submission"

    print(f"[vision_agent] running — context: {trigger_context}")

    # Step 1 — quality gate
    quality = await _check_quality(image_b64, image_type)
    if not quality["ok"]:
        print(f"[vision_agent] quality check failed: {quality['reason']}")
        return {
            "quality_ok": False,
            "quality_reason": quality["reason"],
            "full_observations": [],
            "priority_observation": None,
            "reporter_message": quality["reporter_message"],
            "field_suggestions": {}
        }

    # Step 2 — scene analysis
    observations = await _analyze_scene(image_b64, image_type, report_state, trigger_context)
    print(f"[vision_agent] observations produced: {len(observations)}")

    # Step 3 — if 0 observations in an intake context, describe the scene instead
    # of returning nothing. This produces a confirmable question ("It looks like a
    # rolling mill — is that where this happened?") and any extractable field prefills.
    if not observations and trigger_context in ("cold_start", "mid_intake"):
        print(f"[vision_agent] 0 observations — running scene description for intake")
        described = await _describe_scene_for_intake(image_b64, image_type, report_state)
        return {
            "quality_ok": True,
            "quality_reason": None,
            "full_observations": [],
            "priority_observation": None,
            "reporter_message": described.get("message", ""),
            "field_suggestions": described.get("field_suggestions", {})
        }

    # Step 3b — priority selection + reporter message (observations found)
    priority = await _select_priority(observations, report_state, trigger_context)

    # Step 4 — field suggestions for intake contexts
    field_suggestions = {}
    if trigger_context in ("cold_start", "mid_intake"):
        field_suggestions = await _extract_field_suggestions(image_b64, image_type, report_state)

    return {
        "quality_ok": True,
        "quality_reason": None,
        "full_observations": observations,
        "priority_observation": priority.get("observation"),
        "reporter_message": priority.get("reporter_message", ""),
        "field_suggestions": field_suggestions
    }


# ── Step 1 — Image quality check ─────────────────────────────────────────────

async def _check_quality(image_b64: str, image_type: str) -> dict:
    """
    Fast quality gate. Checks for blur, darkness, flash overexposure,
    obstructions, and unreadable content before running full analysis.
    """
    system_prompt = (
        "You are checking whether a workplace incident photo is usable for safety investigation. "
        "Assess only image quality — not content. "
        "Return ONLY valid JSON, no explanation, no markdown.\n\n"
        "JSON format:\n"
        '{"ok": true} if the image is clear enough to analyze.\n'
        '{"ok": false, "reason": "brief reason"} if it is too blurry, too dark, '
        "overexposed from flash, obstructed, or otherwise unreadable."
    )

    user_prompt = "Is this image clear enough to use for a safety investigation?"

    try:
        raw = await chat_with_ollama_vision(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            image_b64=image_b64,
            image_type=image_type
        )

        result = _parse_json(raw)

        if result.get("ok") is True:
            return {"ok": True, "reason": None, "reporter_message": ""}

        reason = result.get("reason", "unclear image")
        return {
            "ok": False,
            "reason": reason,
            "reporter_message": (
                f"The photo is a bit hard to make out — {reason}. "
                "Could you try taking another one with better lighting or from a bit further back?"
            )
        }

    except Exception as e:
        print(f"[vision_agent] quality check error: {e}")
        # Fail open — if quality check errors, proceed with analysis
        return {"ok": True, "reason": None, "reporter_message": ""}


# ── Step 2 — Full scene analysis ─────────────────────────────────────────────

async def _analyze_scene(
    image_b64: str,
    image_type: str,
    report_state: dict,
    trigger_context: str
) -> list:
    """
    Full safety expert read of the image.

    Reads image alongside current report state.
    Returns a ranked list of observations — everything the agent notices.
    """
    report_summary = _build_report_summary(report_state)

    context_instruction = ""
    if trigger_context == "cold_start":
        context_instruction = (
            "No report has been started yet. Analyze the image entirely from scratch. "
            "Identify the incident type, environment, and any visible conditions."
        )
    elif trigger_context == "mid_intake":
        context_instruction = (
            "A report is being filled out. Some fields may already be collected. "
            "Look for anything that confirms, contradicts, or adds to what has been reported so far."
        )
    elif trigger_context in ("post_submission", "admin_review"):
        context_instruction = (
            "A full incident report has been submitted. "
            "Analyze the image as an experienced safety investigator reviewing the scene after the fact. "
            "Look for anything the reporter may have missed, any hazards still present, "
            "and anything that contradicts or adds important context to the report."
        )

    system_prompt = (
        "You are an experienced industrial safety investigator with 20 years of experience "
        "in steel manufacturing environments. "
        "You are reviewing a workplace incident photo. "
        f"{context_instruction}\n\n"
        "Think like a safety officer walking into the scene. Notice everything:\n"
        "- Active dangers — anything that could hurt someone right now\n"
        "- Contradictions — things visible that conflict with the written report\n"
        "- Unreported hazards — conditions not mentioned that pose risk\n"
        "- PPE compliance — is appropriate equipment visible or absent\n"
        "- Environmental conditions — housekeeping, lighting, spills, clutter\n"
        "- Equipment state — guards, indicators, damage, loose components\n"
        "- Proximity hazards — what else is near the incident point\n"
        "- Actions taken — are barriers, cones, or other controls visible\n\n"
        "RULES:\n"
        "- Only report what you can actually see. Do not infer or guess.\n"
        "- If the image is of a general area with no clear hazard, say so honestly.\n"
        "- Rank observations by urgency: active_danger first, then contradiction, "
        "then unreported_hazard, then context.\n"
        "- Return ONLY valid JSON. No explanation. No markdown.\n\n"
        "JSON format:\n"
        "[\n"
        "  {\n"
        '    "type": "active_danger" | "contradiction" | "unreported_hazard" | "context",\n'
        '    "observation": "one clear sentence describing what you see",\n'
        '    "severity": "critical" | "high" | "medium" | "low",\n'
        '    "detail": "brief additional context if needed"\n'
        "  }\n"
        "]\n\n"
        "Return an empty array [] if nothing significant is observable."
    )

    user_prompt = f"Current report state:\n{report_summary}\n\nAnalyze this scene."

    try:
        raw = await chat_with_ollama_vision(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            image_b64=image_b64,
            image_type=image_type
        )

        observations = _parse_json(raw)
        if not isinstance(observations, list):
            observations = []

        # Validate each observation has required keys
        cleaned = []
        for obs in observations:
            if isinstance(obs, dict) and obs.get("observation"):
                cleaned.append({
                    "type": obs.get("type", "context"),
                    "observation": obs.get("observation", ""),
                    "severity": obs.get("severity", "low"),
                    "detail": obs.get("detail", "")
                })

        return cleaned

    except Exception as e:
        print(f"[vision_agent] scene analysis error: {e}")
        return []


# ── Step 3 — Priority selection ───────────────────────────────────────────────

async def _select_priority(
    observations: list,
    report_state: dict,
    trigger_context: str
) -> dict:
    """
    From the full observation list, pick the single most important thing
    and phrase it as a natural follow-up question for the reporter.

    Priority order: active_danger > contradiction > unreported_hazard > context
    Within same type: critical > high > medium > low
    """
    if not observations:
        return {"observation": None, "reporter_message": ""}

    # Sort by type priority then severity
    type_order = {"active_danger": 0, "contradiction": 1, "unreported_hazard": 2, "context": 3}
    severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}

    sorted_obs = sorted(
        observations,
        key=lambda o: (
            type_order.get(o.get("type", "context"), 3),
            severity_order.get(o.get("severity", "low"), 3)
        )
    )

    top = sorted_obs[0]

    # For low-severity context observations in post_submission — skip asking
    if (trigger_context == "post_submission"
            and top.get("type") == "context"
            and top.get("severity") == "low"):
        return {"observation": top, "reporter_message": ""}

    # Generate natural reporter message
    reporter_message = await _phrase_reporter_question(top, report_state, trigger_context)

    return {
        "observation": top,
        "reporter_message": reporter_message
    }


async def _phrase_reporter_question(
    observation: dict,
    report_state: dict,
    trigger_context: str
) -> str:
    """
    Turn a structured observation into a natural, conversational question
    for the reporter. Reads like a colleague following up, not a compliance audit.
    """
    obs_text = observation.get("observation", "")
    obs_type = observation.get("type", "context")
    obs_detail = observation.get("detail", "")

    if trigger_context in ("cold_start", "mid_intake"):
        tone_instruction = (
            "You are an intake agent helping a worker report a workplace incident. "
            "Ask naturally as if continuing a conversation."
        )
    else:
        tone_instruction = (
            "You are a safety officer following up on a submitted incident report. "
            "Ask naturally as if sending a quick follow-up message to a colleague."
        )

    type_guidance = {
        "active_danger": "This looks like a potentially active hazard. Ask if it has been addressed.",
        "contradiction": "This appears to contradict something in the report. Ask for clarification naturally.",
        "unreported_hazard": "This is something not mentioned in the report. Ask about it briefly.",
        "context": "This adds context to the report. Ask a simple confirming question."
    }.get(obs_type, "Ask a brief follow-up question.")

    system_prompt = (
        f"{tone_instruction}\n\n"
        "Write ONE short, natural follow-up question based on something observed in a photo. "
        "Do not mention that you analyzed an image or used AI. "
        "Do not ask multiple questions. Do not use bullet points. "
        "Keep it to 1-2 sentences maximum. Write in plain conversational English.\n\n"
        f"Guidance: {type_guidance}"
    )

    user_prompt = (
        f"Observation: {obs_text}\n"
        f"Additional detail: {obs_detail}\n\n"
        "Write the follow-up question."
    )

    try:
        message = await chat_with_ollama(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
        )
        return message.strip()
    except Exception as e:
        print(f"[vision_agent] phrase question error: {e}")
        # Fallback — plain version of the observation
        return f"I noticed {obs_text.lower()} — can you tell me more about that?"


# ── Step 2b — Scene description for intake (0 observations fallback) ──────────

async def _describe_scene_for_intake(
    image_b64: str,
    image_type: str,
    report_state: dict
) -> dict:
    """
    Called when scene analysis produced 0 observations in a cold_start or
    mid_intake context. Makes a fresh vision call focused on describing what
    is visible rather than identifying hazards.

    Returns:
    {
        "message": "It looks like this was taken near a rolling mill — is that where the incident happened?",
        "field_suggestions": {"location": "rolling mill"}   # may be empty
    }

    The message is framed as a confirmable question so the reporter can say
    "yes" (keeps the prefill) or correct it ("no, it was the blast furnace").
    """
    already_filled = _get_filled_fields(report_state)
    already_filled_str = ", ".join(already_filled) if already_filled else "none"
    report_summary = _build_report_summary(report_state)

    system_prompt = (
        "You are helping a worker fill out a workplace incident report. "
        "They have attached a photo. Your job is two things:\n\n"
        "1. Write ONE short, natural sentence describing the most prominent visible element "
        "(equipment, location, environment) framed as a confirmable question. "
        "Examples:\n"
        "  'It looks like this was taken near a rolling mill — is that where the incident happened?'\n"
        "  'I can see what appears to be a furnace area — was the incident near here?'\n"
        "  'This looks like it could be near a conveyor system — is that right?'\n"
        "Rules for the message:\n"
        "  - Do not say 'I notice', 'I can see', or mention analyzing an image.\n"
        "  - Keep it to 1 sentence ending with a short confirmable question.\n"
        "  - If the image is blank, very dark, or shows nothing recognizable, say: "
        "'I wasn\\'t able to make out much from the photo — could you describe where the incident happened?'\n\n"
        "2. Extract any incident report fields you can confidently identify from the image.\n"
        f"Fields already collected (skip these): {already_filled_str}\n"
        "Fields you may extract if clearly visible:\n"
        "  - incident_type: 'Personal Injuries' | 'Near Miss' | 'Equipment Damage'\n"
        "  - location: visible area name or description\n"
        "  - accident_agent: the equipment or object involved\n"
        "  - incident_agent: equipment involved in damage if visible\n"
        "  - actions_taken: any visible barriers, cones, or safety controls\n\n"
        "Return ONLY valid JSON with exactly these two keys. No explanation. No markdown.\n"
        '{"message": "your confirmable question here", "field_suggestions": {"location": "rolling mill"}}\n'
        'Return {"message": "...", "field_suggestions": {}} if no fields can be confidently extracted.'
    )

    user_prompt = (
        f"Current report state:\n{report_summary}\n\n"
        "Describe what you see and extract any visible fields."
    )

    try:
        raw = await chat_with_ollama_vision(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            image_b64=image_b64,
            image_type=image_type
        )

        result = _parse_json(raw)
        if not isinstance(result, dict):
            return {
                "message": "I wasn't able to make out much from the photo — could you describe where the incident happened?",
                "field_suggestions": {}
            }

        message = result.get("message", "").strip()
        suggestions = result.get("field_suggestions", {})

        if not isinstance(suggestions, dict):
            suggestions = {}

        # Never suggest already-filled fields
        for field in already_filled:
            suggestions.pop(field, None)

        if not message:
            message = "I wasn't able to make out much from the photo — could you describe where the incident happened?"

        print(f"[vision_agent] scene description: '{message}' | suggestions: {suggestions}")
        return {"message": message, "field_suggestions": suggestions}

    except Exception as e:
        print(f"[vision_agent] scene description error: {e}")
        return {
            "message": "I wasn't able to make out much from the photo — could you describe where the incident happened?",
            "field_suggestions": {}
        }



async def _extract_field_suggestions(
    image_b64: str,
    image_type: str,
    report_state: dict
) -> dict:
    """
    For cold_start and mid_intake: extract any form fields that can be
    confidently read from the image. Only returns fields with clear visual
    evidence. Never guesses.

    Returns dict of field: value pairs e.g.
    {"location": "rolling mill bay 4", "incident_type": "Equipment Damage"}
    """
    already_filled = _get_filled_fields(report_state)
    already_filled_str = ", ".join(already_filled) if already_filled else "none"

    system_prompt = (
        "You are helping pre-fill a workplace incident report from a photo. "
        "Extract ONLY field values you can clearly see visual evidence for. "
        "Do not infer. Do not guess. If you are not certain, leave the field out.\n\n"
        f"Fields already collected (do not suggest these): {already_filled_str}\n\n"
        "Fields you may suggest if clearly visible:\n"
        "- incident_type: 'Personal Injuries' | 'Near Miss' | 'Equipment Damage'\n"
        "- location: visible area name or description\n"
        "- person_type: 'Employee' | 'Contractor' (only if a person is clearly visible)\n"
        "- actions_taken: any visible barriers, cones, or safety controls\n"
        "- accident_agent: the equipment or object involved if clearly visible\n"
        "- incident_agent: equipment involved in damage if clearly visible\n\n"
        "Return ONLY valid JSON. No explanation. No markdown.\n"
        'Example: {"location": "rolling mill", "incident_type": "Equipment Damage"}\n'
        "Return {} if nothing can be confidently extracted."
    )

    user_prompt = "What incident report fields can you extract from this image?"

    try:
        raw = await chat_with_ollama_vision(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            image_b64=image_b64,
            image_type=image_type
        )

        suggestions = _parse_json(raw)
        if not isinstance(suggestions, dict):
            return {}

        # Strip out any already-filled fields — never overwrite what reporter said
        for field in already_filled:
            suggestions.pop(field, None)

        return suggestions

    except Exception as e:
        print(f"[vision_agent] field extraction error: {e}")
        return {}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _build_report_summary(report_state: dict) -> str:
    """
    Build a compact plain-text summary of current report state
    to give the vision model context without overwhelming it.
    """
    if not report_state:
        return "No report data collected yet."

    lines = []
    for section, fields in report_state.items():
        if not isinstance(fields, dict):
            continue
        for key, value in fields.items():
            if value and str(value).strip().lower() not in ("", "n/a", "na", "none"):
                lines.append(f"- {key.replace('_', ' ')}: {value}")

    return "\n".join(lines) if lines else "No report data collected yet."


def _get_filled_fields(report_state: dict) -> list:
    """Return a flat list of field names already filled in the report."""
    filled = []
    for section, fields in report_state.items():
        if not isinstance(fields, dict):
            continue
        for key, value in fields.items():
            if value and str(value).strip().lower() not in ("", "n/a", "na", "none"):
                filled.append(key)
    return filled


def _parse_json(raw: str) -> any:
    """
    Safely parse JSON from LLM output.
    Strips markdown fences and thinking tags if present.
    """
    if not raw:
        return {}

    # Strip <think>...</think> blocks
    raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()

    # Strip markdown fences
    raw = re.sub(r"```(?:json)?", "", raw).replace("```", "").strip()

    # Find first JSON structure
    for start_char, end_char in [("[", "]"), ("{", "}")]:
        start = raw.find(start_char)
        end = raw.rfind(end_char)
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(raw[start:end + 1])
            except json.JSONDecodeError:
                continue

    return {}   