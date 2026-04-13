from sqlalchemy.orm import Session
from models.historical import HistoricalIncident
from models.report import IncidentReport
from core.qdrant import search_similar as qdrant_search_similar
import json


# ── Scoring-based fallback (kept for when Qdrant index is empty) ──────────────

FIELD_WEIGHTS = {
    "location":        3,
    "accident_type":   2,
    "injury_type":     2,
    "accident_agent":  2,
    "incident_agent":  2,
    "injury_agent":    1,
    "activity_type":   1,
    "sif_case":        1,
}

MIN_SCORE = 2
MAX_RESULTS = 5


def _partial_match(a: str, b: str) -> bool:
    """
    Case-insensitive partial match.
    Returns True if either string contains the other.
    e.g. "wet floor" matches "floor surface"
    """
    if not a or not b:
        return False
    a = a.lower().strip()
    b = b.lower().strip()
    return a in b or b in a


def _score_candidate(new_report: dict, candidate) -> int:
    basic = new_report.get("basic_info", {})
    injury = new_report.get("injury_data", {})
    equipment = new_report.get("equipment_damage_data", {})
    near_miss = new_report.get("near_miss_data", {})

    new_fields = {
        "location":       basic.get("location", ""),
        "accident_type":  injury.get("accident_type", ""),
        "injury_type":    injury.get("injury_type", ""),
        "accident_agent": injury.get("accident_agent", ""),
        "injury_agent":   injury.get("injury_agent", ""),
        "activity_type":  equipment.get("activity_type", "") or near_miss.get("activity_type", ""),
        "incident_agent": equipment.get("incident_agent", ""),
        "sif_case":       injury.get("sif_case", "") or near_miss.get("sif_case", "") or equipment.get("sif_case", ""),
    }

    candidate_fields = {
        "location":       getattr(candidate, "location", "") or "",
        "accident_type":  getattr(candidate, "accident_type", "") or "",
        "injury_type":    getattr(candidate, "injury_type", "") or "",
        "accident_agent": getattr(candidate, "accident_agent", "") or "",
        "injury_agent":   getattr(candidate, "injury_agent", "") or "",
        "activity_type":  getattr(candidate, "activity_type", "") or "",
        "incident_agent": getattr(candidate, "incident_agent", "") or "",
        "sif_case":       getattr(candidate, "sif_case", "") or "",
    }

    score = 0
    for field, weight in FIELD_WEIGHTS.items():
        if _partial_match(new_fields[field], candidate_fields[field]):
            score += weight

    return score


def _report_json_to_candidate(report_json: dict):
    basic = report_json.get("basic_info", {})
    injury = report_json.get("injury_data", {})
    equipment = report_json.get("equipment_damage_data", {})
    near_miss = report_json.get("near_miss_data", {})

    class PseudoCandidate:
        pass

    c = PseudoCandidate()
    c.location = basic.get("location", "")
    c.accident_type = injury.get("accident_type", "")
    c.injury_type = injury.get("injury_type", "")
    c.accident_agent = injury.get("accident_agent", "")
    c.injury_agent = injury.get("injury_agent", "")
    c.activity_type = equipment.get("activity_type", "") or near_miss.get("activity_type", "")
    c.incident_agent = equipment.get("incident_agent", "")
    c.sif_case = injury.get("sif_case", "") or near_miss.get("sif_case", "") or equipment.get("sif_case", "")
    return c


def _scoring_fallback(new_report: dict, incident_type: str, db: Session) -> list:
    """
    Original scoring-based search.
    Used when Qdrant returns 0 results (e.g. index not yet populated).
    """
    results = []

    historical_candidates = (
        db.query(HistoricalIncident)
        .filter(HistoricalIncident.incident_type == incident_type)
        .all()
    )

    for candidate in historical_candidates:
        score = _score_candidate(new_report, candidate)
        if score >= MIN_SCORE:
            results.append({
                "source": "historical",
                "id": candidate.id,
                "source_id": candidate.source_id,
                "source_file": candidate.source_file,
                "incident_type": candidate.incident_type,
                "datetime": candidate.datetime,
                "location": candidate.location,
                "department": candidate.department,
                "plant": candidate.plant,
                "accident_type": candidate.accident_type,
                "injury_type": candidate.injury_type,
                "accident_agent": candidate.accident_agent,
                "injury_agent": candidate.injury_agent,
                "activity_type": candidate.activity_type,
                "incident_agent": candidate.incident_agent,
                "sif_case": candidate.sif_case,
                "actions_taken": candidate.actions_taken,
                "severity": candidate.severity,
                "score": score
            })

    all_submitted = db.query(IncidentReport).all()
    for candidate in all_submitted:
        report_json = candidate.report_json
        if isinstance(report_json, str):
            report_json = json.loads(report_json)

        candidate_type = report_json.get("basic_info", {}).get("incident_type", "")
        if candidate_type != incident_type:
            continue

        pseudo = _report_json_to_candidate(report_json)
        score = _score_candidate(new_report, pseudo)
        if score >= MIN_SCORE:
            basic = report_json.get("basic_info", {})
            injury = report_json.get("injury_data", {})
            equipment = report_json.get("equipment_damage_data", {})
            results.append({
                "source": "submitted",
                "id": candidate.id,
                "source_id": f"report-{candidate.id}",
                "source_file": "chatbot",
                "incident_type": basic.get("incident_type", ""),
                "datetime": basic.get("datetime", ""),
                "location": basic.get("location", ""),
                "department": "",
                "plant": "",
                "accident_type": injury.get("accident_type", ""),
                "injury_type": injury.get("injury_type", ""),
                "accident_agent": injury.get("accident_agent", ""),
                "injury_agent": injury.get("injury_agent", ""),
                "activity_type": equipment.get("activity_type", ""),
                "incident_agent": equipment.get("incident_agent", ""),
                "sif_case": injury.get("sif_case", "") or equipment.get("sif_case", ""),
                "actions_taken": basic.get("actions_taken", ""),
                "severity": basic.get("severity", ""),
                "score": score
            })

    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:MAX_RESULTS]


# ── Main entry point ──────────────────────────────────────────────────────────

async def find_similar(new_report: dict, incident_type: str, db: Session) -> list:
    """
    Find the top similar incidents for a new report.

    Strategy:
    1. Try Qdrant vector search first (semantic, model-based)
    2. If Qdrant returns 0 results (empty index or connection issue),
       fall back to scoring-based search against PostgreSQL
    3. Always return at most MAX_RESULTS results

    The fallback ensures the system keeps working even before the
    Qdrant index has been populated with historical data.
    """

    # ── 1. Try Qdrant ─────────────────────────────────────────────────────────
    qdrant_results = []
    try:
        qdrant_results = await qdrant_search_similar(
            report=new_report,
            incident_type=incident_type,
            top_k=MAX_RESULTS
        )
    except Exception as e:
        print(f"[similarity] Qdrant search error: {e}")

    if qdrant_results:
        print(f"[similarity] using Qdrant results: {len(qdrant_results)} matches")
        return qdrant_results

    # ── 2. Fall back to scoring ───────────────────────────────────────────────
    print(f"[similarity] Qdrant returned 0 — falling back to scoring search")
    scoring_results = _scoring_fallback(new_report, incident_type, db)
    print(f"[similarity] scoring fallback: {len(scoring_results)} matches")
    return scoring_results