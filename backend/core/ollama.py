import httpx
from config import settings

async def chat_with_ollama(messages: list, model: str = None) -> str:
    model = model or settings.OLLAMA_MODEL
    url = f"{settings.OLLAMA_BASE_URL}/api/chat"

    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "options": {
            "temperature": 0.1,
            "num_predict": 2048,
        },
        "think": False
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(url, json=payload)
        response.raise_for_status()
        data = response.json()
        return data["message"]["content"]


async def chat_with_ollama_vision(messages: list, image_b64: str, image_type: str, model: str = None) -> str:
    """
    Send a message with an image to qwen3.5:9b.

    The image is attached to the last user message in the messages list.
    If messages is empty a bare image message is constructed automatically.

    image_b64  — base64-encoded image string (no data URI prefix)
    image_type — MIME type e.g. "image/jpeg", "image/png"
    """
    model = model or settings.OLLAMA_MODEL
    url = f"{settings.OLLAMA_BASE_URL}/api/chat"

    # Build messages — attach image to the last user turn
    vision_messages = [m for m in messages]

    if vision_messages and vision_messages[-1]["role"] == "user":
        # Attach image to existing last user message
        last = vision_messages[-1]
        existing_content = last.get("content", "")

        vision_messages[-1] = {
            "role": "user",
            "content": existing_content,
            "images": [image_b64]
        }
    else:
        # No user message to attach to — create a bare image turn
        vision_messages.append({
            "role": "user",
            "content": "",
            "images": [image_b64]
        })

    payload = {
        "model": model,
        "messages": vision_messages,
        "stream": False,
        "options": {
            "temperature": 0.1,
            "num_predict": 2048,
        },
        "think": False
    }

    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(url, json=payload)
        response.raise_for_status()
        data = response.json()
        return data["message"]["content"]


async def reset_ollama_context(model: str = None) -> None:
    """
    Wipes Ollama's KV cache for this model by sending keep_alive: 0.
    Call this once at the start of each NEW session only.
    Never call this when resuming an unfinished report.
    """
    model = model or settings.OLLAMA_MODEL
    url = f"{settings.OLLAMA_BASE_URL}/api/chat"

    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "reset"}],
        "stream": False,
        "keep_alive": 0
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.post(url, json=payload)
            print(f"[ollama] context reset for model: {model}")
    except Exception as e:
        print(f"[ollama] context reset failed: {e}")


async def check_ollama_connection() -> bool:
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{settings.OLLAMA_BASE_URL}/api/tags")
            return response.status_code == 200
    except Exception:
        return False


async def generate_summary(report: dict) -> str:
    """
    Generate a plain-language prose narrative of an incident report.

    Takes the structured report dict and asks Ollama to write a 2-3 sentence
    summary that reads like a safety officer wrote it — factual, clear, and
    based only on the fields provided. Falls back to a structured field list
    if Ollama fails so the chat flow is never blocked.
    """
    basic = report.get("basic_info", {})
    injury = report.get("injury_data", {})
    near_miss = report.get("near_miss_data", {})
    equipment = report.get("equipment_damage_data", {})
    incident_type = basic.get("incident_type", "")

    # Build a flat field list to hand to Ollama — only include non-empty values
    field_lines = []

    def add(label: str, value: str):
        if value and value.strip() and value.strip().lower() not in ("n/a", "na", "none", ""):
            field_lines.append(f"- {label}: {value.strip()}")

    add("Incident Type", incident_type)
    add("Date/Time", basic.get("datetime", ""))
    add("Shift", basic.get("shift", ""))
    add("Location", basic.get("location", ""))
    add("Person Involved", basic.get("person_involved", ""))
    add("Person Type", basic.get("person_type", ""))
    add("Severity", basic.get("severity", ""))
    add("Actions Taken", basic.get("actions_taken", ""))

    if incident_type == "Personal Injuries":
        add("Accident Type", injury.get("accident_type", ""))
        add("Accident Agent", injury.get("accident_agent", ""))
        add("Injury Type", injury.get("injury_type", ""))
        add("Injury Agent", injury.get("injury_agent", ""))
        add("SIF Case", injury.get("sif_case", ""))

    elif incident_type == "Near Miss":
        add("SIF Case", near_miss.get("sif_case", ""))
        add("Life Saving Rules", near_miss.get("life_saving_rules", ""))

    elif incident_type == "Equipment Damage":
        add("Damage Amount", equipment.get("damage_amount", ""))
        add("Activity Type", equipment.get("activity_type", ""))
        add("Incident Activity", equipment.get("incident_activity", ""))
        add("Incident Agent", equipment.get("incident_agent", ""))
        add("SIF Case", equipment.get("sif_case", ""))

    if not field_lines:
        return _fallback_summary(report)

    fields_text = "\n".join(field_lines)

    system_prompt = (
        "You are a workplace safety documentation assistant. "
        "Your job is to write clear, factual incident summaries for safety records. "
        "Write in plain English. Use past tense. Be concise — 2 to 4 sentences maximum. "
        "Do not add information that is not in the provided fields. "
        "Do not use bullet points. Do not include headers. Just write the narrative paragraph."
    )

    user_prompt = (
        f"Write a brief incident summary using only the following information:\n\n"
        f"{fields_text}\n\n"
        f"Write 2 to 4 sentences. Do not add details that aren't listed above."
    )

    try:
        summary = await chat_with_ollama(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
        )
        return summary.strip()

    except Exception as e:
        print(f"[ollama] generate_summary failed: {e}")
        return _fallback_summary(report)


def _fallback_summary(report: dict) -> str:
    """
    Structured field list used when Ollama is unavailable.
    Matches the original build_summary() output so the chat never breaks.
    """
    basic = report.get("basic_info", {})
    parts = []

    if basic.get("datetime"):
        parts.append(f"On {basic['datetime']},")
    if basic.get("shift"):
        parts.append(f"during the {basic['shift']} shift,")
    if basic.get("person_involved"):
        person = basic["person_involved"]
        if basic.get("person_type"):
            person += f" ({basic['person_type']})"
        parts.append(f"{person} was involved")
    if basic.get("incident_type"):
        parts.append(f"in a {basic['incident_type']} incident")
    if basic.get("location"):
        parts.append(f"at {basic['location']}.")
    if basic.get("severity"):
        parts.append(f"Severity: {basic['severity']}.")
    if basic.get("actions_taken"):
        parts.append(f"Actions taken: {basic['actions_taken']}.")

    return " ".join(parts) if parts else "Incident report collected."


async def generate_safety_briefing(context_document: dict, report_json: dict) -> str:
    """
    Generate a shift-ready safety briefing from the full context document.

    This is distinct from generate_summary — it is written for a supervisor
    to deliver verbally to workers before the next shift starts. Plain language,
    no jargon, practical and actionable. Covers what happened, where, what to
    watch for, and what has been done about it.

    Reads:
    - report_json structured fields
    - context_document.chat_history — main reporter's account
    - context_document.witness_accounts — any witness accounts
    - context_document.ai_summary — if already generated, used as additional context

    Falls back to a structured plain-text briefing if Ollama fails.
    """
    basic = report_json.get("basic_info", {})
    injury = report_json.get("injury_data", {})
    near_miss = report_json.get("near_miss_data", {})
    equipment = report_json.get("equipment_damage_data", {})
    incident_type = basic.get("incident_type", "")

    # ── Build field block ─────────────────────────────────────────────────────
    field_lines = []

    def add(label, value):
        if value and str(value).strip().lower() not in ("", "n/a", "na", "none"):
            field_lines.append(f"- {label}: {value}")

    add("Incident Type", incident_type)
    add("Date/Time", basic.get("datetime", ""))
    add("Shift", basic.get("shift", ""))
    add("Location", basic.get("location", ""))
    add("Person Involved", basic.get("person_involved", ""))
    add("Severity", basic.get("severity", ""))
    add("Actions Taken", basic.get("actions_taken", ""))

    if incident_type == "Personal Injuries":
        add("Accident Type", injury.get("accident_type", ""))
        add("Accident Agent", injury.get("accident_agent", ""))
        add("Injury Type", injury.get("injury_type", ""))
        add("SIF Case", injury.get("sif_case", ""))
    elif incident_type == "Near Miss":
        add("SIF Case", near_miss.get("sif_case", ""))
        add("Life Saving Rules", near_miss.get("life_saving_rules", ""))
    elif incident_type == "Equipment Damage":
        add("Damage Amount", equipment.get("damage_amount", ""))
        add("Incident Activity", equipment.get("incident_activity", ""))
        add("Incident Agent", equipment.get("incident_agent", ""))

    fields_text = "\n".join(field_lines) if field_lines else "No structured fields available."

    # ── Pull existing AI summary if available ─────────────────────────────────
    ai_summary = context_document.get("ai_summary", "")

    # ── Pull reporter narrative from chat history ─────────────────────────────
    chat_history = context_document.get("chat_history", [])
    reporter_messages = [
        msg.get("content", "")
        for msg in chat_history
        if msg.get("is_user", False) and msg.get("content", "").strip()
    ]
    reporter_narrative = " ".join(reporter_messages).strip()[:600]

    # ── Pull witness accounts ─────────────────────────────────────────────────
    witness_accounts = context_document.get("witness_accounts", [])

    # ── Build combined context ────────────────────────────────────────────────
    sections = [f"INCIDENT FIELDS:\n{fields_text}"]

    if ai_summary:
        sections.append(f"INCIDENT SUMMARY:\n{ai_summary}")
    elif reporter_narrative:
        sections.append(f"REPORTER'S ACCOUNT:\n{reporter_narrative}")

    for i, wa in enumerate(witness_accounts, 1):
        acct = wa.get("account", "").strip()[:300]
        if acct:
            sections.append(f"WITNESS {i} ACCOUNT:\n{acct}")

    combined = "\n\n".join(sections)

    system_prompt = (
        "You are a workplace safety supervisor assistant. "
        "Your job is to write pre-shift safety briefings that supervisors read aloud to their team. "
        "The briefing must be written in plain, simple English — no technical jargon, no abbreviations. "
        "It should be conversational, as if a supervisor is speaking directly to a group of workers. "
        "Structure it as follows, with each section on its own line:\n"
        "1. What happened — one or two plain sentences describing the incident\n"
        "2. Where — the specific location to be cautious around\n"
        "3. What to watch out for — specific hazards or conditions workers should be aware of\n"
        "4. What we have done — actions already taken to address the situation\n"
        "5. What to do if you see something — one clear instruction\n\n"
        "Keep the entire briefing under 150 words. "
        "Do not use bullet points or numbered lists in the output — write in natural spoken paragraphs. "
        "Do not add information that is not in the provided data."
    )

    user_prompt = (
        f"Write a pre-shift safety briefing based on the following incident information:\n\n"
        f"{combined}\n\n"
        f"Write it as a supervisor speaking to their team. Keep it under 150 words."
    )

    try:
        briefing = await chat_with_ollama(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
        )
        return briefing.strip()

    except Exception as e:
        print(f"[ollama] generate_safety_briefing failed: {e}")
        return _fallback_briefing(basic, incident_type)


def _fallback_briefing(basic: dict, incident_type: str) -> str:
    """
    Plain structured fallback when Ollama is unavailable.
    Produces a minimal but usable briefing from structured fields alone.
    """
    parts = ["SAFETY BRIEFING"]

    if basic.get("datetime") or basic.get("location"):
        line = "An incident occurred"
        if basic.get("datetime"):
            line += f" on {basic['datetime']}"
        if basic.get("location"):
            line += f" at {basic['location']}"
        parts.append(line + ".")

    if basic.get("person_involved"):
        parts.append(f"{basic['person_involved']} was involved.")

    if basic.get("severity"):
        parts.append(f"Severity was recorded as {basic['severity']}.")

    if basic.get("actions_taken"):
        parts.append(f"Actions taken: {basic['actions_taken']}.")

    parts.append("Please remain vigilant in the affected area and report any concerns to your supervisor immediately.")

    return " ".join(parts)