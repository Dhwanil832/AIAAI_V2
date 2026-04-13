from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct, Filter, FieldCondition, MatchValue
from config import settings
from core.embeddings import embed_report, embed_historical

# Vector size must match the embedding model output
# nomic-embed-text produces 768-dimensional vectors
VECTOR_SIZE = 768

client = QdrantClient(url=settings.QDRANT_URL)


def get_qdrant_client() -> QdrantClient:
    return client


def ensure_collection_exists():
    existing = [c.name for c in client.get_collections().collections]
    if settings.QDRANT_COLLECTION not in existing:
        client.create_collection(
            collection_name=settings.QDRANT_COLLECTION,
            vectors_config=VectorParams(
                size=VECTOR_SIZE,
                distance=Distance.COSINE
            )
        )
        print(f"[qdrant] created collection: {settings.QDRANT_COLLECTION}")
    else:
        print(f"[qdrant] collection exists: {settings.QDRANT_COLLECTION}")


async def upsert_incident(
    point_id: int,
    report: dict,
    incident_type: str,
    source: str,
    source_id: str,
    source_file: str,
    actions_taken: str = "",
    severity: str = "",
    location: str = "",
    datetime_str: str = "",
):
    """
    Embed a submitted report and upsert into Qdrant with full payload.
    point_id for submitted reports = DB id + 1_000_000
    """
    try:
        vector = await embed_report(report, incident_type)

        basic = report.get("basic_info", {})
        injury = report.get("injury_data", {})
        near_miss = report.get("near_miss_data", {})
        equipment = report.get("equipment_damage_data", {})

        payload = {
            "source": source,
            "source_id": source_id,
            "source_file": source_file,
            "incident_type": incident_type,
            "datetime": datetime_str or basic.get("datetime", ""),
            "shift": basic.get("shift", ""),
            "location": location or basic.get("location", ""),
            "person_involved": basic.get("person_involved", ""),
            "person_type": basic.get("person_type", ""),
            "actions_taken": actions_taken or basic.get("actions_taken", ""),
            "severity": severity or basic.get("severity", ""),
            "accident_type": injury.get("accident_type", ""),
            "accident_agent": injury.get("accident_agent", ""),
            "injury_type": injury.get("injury_type", ""),
            "injury_agent": injury.get("injury_agent", ""),
            "sif_case": injury.get("sif_case", "") or near_miss.get("sif_case", "") or equipment.get("sif_case", ""),
            "life_saving_rules": near_miss.get("life_saving_rules", ""),
            "damage_amount": equipment.get("damage_amount", ""),
            "activity_type": equipment.get("activity_type", ""),
            "incident_activity": equipment.get("incident_activity", ""),
            "incident_agent": equipment.get("incident_agent", ""),
        }

        client.upsert(
            collection_name=settings.QDRANT_COLLECTION,
            points=[PointStruct(id=point_id, vector=vector, payload=payload)]
        )
        print(f"[qdrant] upserted point {point_id} | source={source} | type={incident_type}")

    except Exception as e:
        print(f"[qdrant] upsert failed for point {point_id}: {e}")


async def upsert_historical_incident(candidate) -> None:
    """
    Embed and upsert a HistoricalIncident ORM object with full payload.
    Point ID space: historical incidents use their DB id directly (1 - 999_999).
    """
    try:
        vector = await embed_historical(candidate)

        payload = {
            "source": "historical",
            "source_id": candidate.source_id or "",
            "source_file": candidate.source_file or "",
            "incident_type": candidate.incident_type or "",
            "datetime": candidate.datetime or "",
            "shift": candidate.shift or "",
            "location": candidate.location or "",
            "department": candidate.department or "",
            "plant": candidate.plant or "",
            "person_involved": candidate.person_involved or "",
            "person_type": candidate.person_type or "",
            "actions_taken": candidate.actions_taken or "",
            "severity": candidate.severity or "",
            "sif_case": candidate.sif_case or "",
            "accident_type": candidate.accident_type or "",
            "accident_agent": candidate.accident_agent or "",
            "injury_type": candidate.injury_type or "",
            "injury_agent": candidate.injury_agent or "",
            "damage_amount": candidate.damage_amount or "",
            "activity_type": candidate.activity_type or "",
            "incident_activity": candidate.incident_activity or "",
            "incident_agent": candidate.incident_agent or "",
        }

        client.upsert(
            collection_name=settings.QDRANT_COLLECTION,
            points=[PointStruct(id=candidate.id, vector=vector, payload=payload)]
        )
        print(f"[qdrant] upserted historical incident id={candidate.id}")

    except Exception as e:
        print(f"[qdrant] upsert failed for historical id={getattr(candidate, 'id', '?')}: {e}")


async def search_similar(
    report: dict,
    incident_type: str,
    top_k: int = 5,
) -> list[dict]:
    """
    Embed the new report and find semantically similar incidents in Qdrant.
    Returns full payload for each match so cards and modals can display all details.
    """
    try:
        vector = await embed_report(report, incident_type)

        results = client.query_points(
            collection_name=settings.QDRANT_COLLECTION,
            query=vector,
            query_filter=Filter(
                must=[
                    FieldCondition(
                        key="incident_type",
                        match=MatchValue(value=incident_type)
                    )
                ]
            ),
            limit=top_k,
            with_payload=True,
        ).points

        matches = []
        for hit in results:
            p = hit.payload or {}
            matches.append({
                "source": p.get("source", ""),
                "source_id": p.get("source_id", ""),
                "source_file": p.get("source_file", ""),
                "incident_type": p.get("incident_type", incident_type),
                "score": round(hit.score, 4),
                "datetime": p.get("datetime", ""),
                "shift": p.get("shift", ""),
                "location": p.get("location", ""),
                "department": p.get("department", ""),
                "plant": p.get("plant", ""),
                "person_involved": p.get("person_involved", ""),
                "person_type": p.get("person_type", ""),
                "actions_taken": p.get("actions_taken", ""),
                "severity": p.get("severity", ""),
                "sif_case": p.get("sif_case", ""),
                "accident_type": p.get("accident_type", ""),
                "accident_agent": p.get("accident_agent", ""),
                "injury_type": p.get("injury_type", ""),
                "injury_agent": p.get("injury_agent", ""),
                "life_saving_rules": p.get("life_saving_rules", ""),
                "damage_amount": p.get("damage_amount", ""),
                "activity_type": p.get("activity_type", ""),
                "incident_activity": p.get("incident_activity", ""),
                "incident_agent": p.get("incident_agent", ""),
            })

        print(f"[qdrant] search | type={incident_type} | results={len(matches)}")
        return matches

    except Exception as e:
        print(f"[qdrant] search failed: {e}")
        return []