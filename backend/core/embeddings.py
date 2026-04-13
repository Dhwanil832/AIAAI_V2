import httpx
from config import settings

EMBEDDING_MODEL = "nomic-embed-text"


def _build_incident_text(report: dict, incident_type: str) -> str:
    """
    Flatten a structured report dict into a single text string for embedding.
    Includes all meaningful fields so the vector captures full incident context.
    """
    basic = report.get("basic_info", {})
    injury = report.get("injury_data", {})
    near_miss = report.get("near_miss_data", {})
    equipment = report.get("equipment_damage_data", {})

    parts = [
        f"Incident Type: {incident_type}",
        f"Location: {basic.get('location', '')}",
        f"Shift: {basic.get('shift', '')}",
        f"Severity: {basic.get('severity', '')}",
        f"Person Involved: {basic.get('person_involved', '')}",
        f"Person Type: {basic.get('person_type', '')}",
        f"Actions Taken: {basic.get('actions_taken', '')}",
        f"Accident Type: {injury.get('accident_type', '')}",
        f"Accident Agent: {injury.get('accident_agent', '')}",
        f"Injury Type: {injury.get('injury_type', '')}",
        f"Injury Agent: {injury.get('injury_agent', '')}",
        f"SIF Case: {injury.get('sif_case', '') or near_miss.get('sif_case', '') or equipment.get('sif_case', '')}",
        f"Life Saving Rules: {near_miss.get('life_saving_rules', '')}",
        f"Damage Amount: {equipment.get('damage_amount', '')}",
        f"Activity Type: {equipment.get('activity_type', '') or near_miss.get('activity_type', '')}",
        f"Incident Activity: {equipment.get('incident_activity', '')}",
        f"Incident Agent: {equipment.get('incident_agent', '')}",
    ]

    # Filter out empty values so the embedding isn't polluted with blank fields
    return " | ".join(p for p in parts if not p.endswith(": ") and not p.endswith(":"))


def _build_historical_text(candidate) -> str:
    """
    Flatten a HistoricalIncident ORM object into text for embedding.
    """
    parts = [
        f"Incident Type: {getattr(candidate, 'incident_type', '') or ''}",
        f"Location: {getattr(candidate, 'location', '') or ''}",
        f"Shift: {getattr(candidate, 'shift', '') or ''}",
        f"Severity: {getattr(candidate, 'severity', '') or ''}",
        f"Actions Taken: {getattr(candidate, 'actions_taken', '') or ''}",
        f"Accident Type: {getattr(candidate, 'accident_type', '') or ''}",
        f"Accident Agent: {getattr(candidate, 'accident_agent', '') or ''}",
        f"Injury Type: {getattr(candidate, 'injury_type', '') or ''}",
        f"Injury Agent: {getattr(candidate, 'injury_agent', '') or ''}",
        f"SIF Case: {getattr(candidate, 'sif_case', '') or ''}",
        f"Activity Type: {getattr(candidate, 'activity_type', '') or ''}",
        f"Incident Agent: {getattr(candidate, 'incident_agent', '') or ''}",
    ]

    return " | ".join(p for p in parts if not p.endswith(": ") and not p.endswith(":"))


async def get_embedding(text: str) -> list[float]:
    """
    Call Ollama's embedding endpoint and return the vector.
    Uses nomic-embed-text which produces 768-dimensional vectors.
    Raises on failure so callers can decide whether to fall back.
    """
    url = f"{settings.OLLAMA_BASE_URL}/api/embeddings"
    payload = {
        "model": EMBEDDING_MODEL,
        "prompt": text
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(url, json=payload)
        response.raise_for_status()
        data = response.json()
        return data["embedding"]


async def embed_report(report: dict, incident_type: str) -> list[float]:
    """
    Embed a structured report dict.
    Convenience wrapper used at submission time.
    """
    text = _build_incident_text(report, incident_type)
    return await get_embedding(text)


async def embed_historical(candidate) -> list[float]:
    """
    Embed a HistoricalIncident ORM object.
    Convenience wrapper used during historical data indexing.
    """
    text = _build_historical_text(candidate)
    return await get_embedding(text)