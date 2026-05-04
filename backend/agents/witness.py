"""
agents/witness.py
─────────────────
Generates an AI incident summary from the full context_document.

Called when:
- Admin clicks "Regenerate Summary" on ReportPage
- A witness submits their account (auto-regenerate)

Reads:
- context_document.chat_history      — main reporter's full conversation
- context_document.witness_accounts  — list of witness free-text accounts

Produces:
- A single prose paragraph summarising the incident from all available perspectives
- Stored back into context_document.ai_summary
"""

from core.ollama import chat_with_ollama


async def generate_incident_summary(context_document: dict, report_json: dict) -> str:
    """
    Generate a prose incident summary from all available accounts.

    Args:
        context_document: the full context_document dict from the IncidentReport
        report_json: the structured report fields

    Returns:
        A plain-language prose paragraph. Falls back to a structured summary
        if Ollama fails so the endpoint never errors out.
    """
    basic = report_json.get("basic_info", {})
    incident_type = basic.get("incident_type", "")
    person = basic.get("person_involved", "")
    location = basic.get("location", "")
    datetime_str = basic.get("datetime", "")
    severity = basic.get("severity", "")
    actions = basic.get("actions_taken", "")

    # ── Build structured field block ──────────────────────────────────────────
    field_lines = []

    def add(label, value):
        if value and str(value).strip().lower() not in ("", "n/a", "na", "none"):
            field_lines.append(f"- {label}: {value}")

    add("Incident Type", incident_type)
    add("Date/Time", datetime_str)
    add("Location", location)
    add("Person Involved", person)
    add("Severity", severity)
    add("Actions Taken", actions)

    # Type-specific fields
    injury = report_json.get("injury_data", {})
    near_miss = report_json.get("near_miss_data", {})
    equipment = report_json.get("equipment_damage_data", {})

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

    fields_text = "\n".join(field_lines) if field_lines else "No structured fields available."

    # ── Extract main reporter narrative from chat history ─────────────────────
    chat_history = context_document.get("chat_history", [])
    reporter_messages = [
        msg.get("content", "")
        for msg in chat_history
        if msg.get("is_user", False) and msg.get("content", "").strip()
    ]
    reporter_narrative = " ".join(reporter_messages).strip()

    # ── Extract witness accounts ───────────────────────────────────────────────
    witness_accounts = context_document.get("witness_accounts", [])

    # ── Build prompt ──────────────────────────────────────────────────────────
    sections = []
    sections.append(f"STRUCTURED REPORT FIELDS:\n{fields_text}")

    if reporter_narrative:
        # Limit to 800 chars to keep prompt manageable
        sections.append(f"MAIN REPORTER'S ACCOUNT:\n{reporter_narrative[:800]}")

    if witness_accounts:
        for i, wa in enumerate(witness_accounts, 1):
            acct = wa.get("account", "").strip()
            username = wa.get("username", f"Witness {i}")
            if acct:
                sections.append(f"WITNESS ACCOUNT ({username}):\n{acct[:500]}")

    combined = "\n\n".join(sections)

    source_count = 1 + len(witness_accounts)
    account_label = "one account" if source_count == 1 else f"{source_count} accounts"

    system_prompt = (
        "You are a workplace safety documentation assistant. "
        "Your job is to write concise, factual incident summaries for safety records. "
        "Write in plain English. Use past tense. Be objective — do not assign blame. "
        "If multiple accounts are provided, synthesize them into one coherent narrative. "
        "If accounts contradict each other, note the discrepancy briefly and factually. "
        "Do not use bullet points. Do not include headers. Write 3 to 5 sentences maximum. "
        "Do not add information that is not in the provided data."
    )

    user_prompt = (
        f"Write a concise incident summary based on the following information "
        f"collected from {account_label}:\n\n"
        f"{combined}\n\n"
        f"Write 3 to 5 sentences. Be factual and objective."
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
        print(f"[witness] generate_incident_summary failed: {e}")
        return _fallback_summary(basic, witness_accounts)


def _fallback_summary(basic: dict, witness_accounts: list) -> str:
    """
    Plain structured fallback when Ollama is unavailable.
    """
    parts = []

    if basic.get("datetime"):
        parts.append(f"On {basic['datetime']},")
    if basic.get("person_involved"):
        parts.append(f"{basic['person_involved']} was involved")
    if basic.get("incident_type"):
        parts.append(f"in a {basic['incident_type']} incident")
    if basic.get("location"):
        parts.append(f"at {basic['location']}.")
    if basic.get("severity"):
        parts.append(f"Severity: {basic['severity']}.")
    if basic.get("actions_taken"):
        parts.append(f"Actions taken: {basic['actions_taken']}.")
    if witness_accounts:
        parts.append(f"{len(witness_accounts)} witness account(s) recorded.")

    return " ".join(parts) if parts else "Incident report collected."