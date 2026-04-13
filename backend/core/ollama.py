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
        }
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
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