from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from typing import Optional
from database import get_db
from core.dependencies import get_current_user, get_current_admin
from core.qdrant import upsert_historical_incident
from models.user import User
from models.historical import HistoricalIncident
import pandas as pd
import io
import json
import math

router = APIRouter()


# ── Column mappings per incident type ────────────────────────────────────────

PERSONAL_INJURY_MAP = {
    "incident id":                  "source_id",
    "injury date":                  "datetime",
    "turn":                         "shift",
    "accident loc":                 "location",
    "department":                   "department",
    "plant":                        "plant",
    "employee name":                "person_involved",
    "contractor name":              "person_involved_contractor",
    "accident type desc":           "accident_type",
    "accident agent desc":          "accident_agent",
    "injury type desc":             "injury_type",
    "injury agent desc":            "injury_agent",
    "sif case":                     "sif_case",
    "activity type":                "activity_type",
    "immediate corrective action":  "actions_taken",
    "risk assessment severity":     "severity",
}

NEAR_MISS_MAP = {
    "incident id":                  "source_id",
    "incident date":                "datetime",
    "turn":                         "shift",
    "incident loc":                 "location",
    "department":                   "department",
    "plant":                        "plant",
    "employee name":                "person_involved",
    "contractor name":              "person_involved_contractor",
    "sif case":                     "sif_case",
    "activity type":                "activity_type",
    "incident activity desc":       "incident_activity",
    "incident agent desc":          "incident_agent",
    "immediate corrective action":  "actions_taken",
    "risk assessment severity":     "severity",
}

EQUIPMENT_DAMAGE_MAP = {
    "incident id":                  "source_id",
    "incident date":                "datetime",
    "turn":                         "shift",
    "incident loc":                 "location",
    "department":                   "department",
    "plant":                        "plant",
    "employee name":                "person_involved",
    "contractor name":              "person_involved_contractor",
    "sif case":                     "sif_case",
    "equipment damage amount":      "damage_amount",
    "activity type":                "activity_type",
    "incident activity desc":       "incident_activity",
    "incident agent desc":          "incident_agent",
    "immediate corrective action":  "actions_taken",
    "risk assessment severity":     "severity",
}

INCIDENT_TYPE_MAP = {
    "Personal Injuries": PERSONAL_INJURY_MAP,
    "Near Miss":         NEAR_MISS_MAP,
    "Equipment Damage":  EQUIPMENT_DAMAGE_MAP,
}


def _sanitize_for_json(obj):
    """
    Recursively sanitize a dict for PostgreSQL JSON storage.
    Replaces NaN, Infinity, and non-serializable values with None.
    """
    if isinstance(obj, dict):
        return {k: _sanitize_for_json(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_sanitize_for_json(v) for v in obj]
    elif isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    else:
        return obj


def _safe_get(row: dict, col_map: dict, field: str) -> Optional[str]:
    """
    Look up a field value from a row using the column map.
    Case-insensitive. Returns None if not found or empty.
    """
    for xls_col, normalized_field in col_map.items():
        if normalized_field == field:
            for row_col, value in row.items():
                if str(row_col).strip().lower() == xls_col.lower():
                    if value is not None and str(value).strip() not in ("", "nan", "NaT", "None"):
                        return str(value).strip()
    return None


def _parse_xls(file_bytes: bytes, incident_type: str, source_file: str) -> tuple[list, int]:
    """
    Parse an XLS/XLSX file and return normalized records.
    Returns (records, skipped_count)
    """
    if incident_type not in INCIDENT_TYPE_MAP:
        raise ValueError(f"Unknown incident type: {incident_type}")

    col_map = INCIDENT_TYPE_MAP[incident_type]

    try:
        df = pd.read_excel(io.BytesIO(file_bytes), dtype=str, header=4)
    except Exception as e:
        raise ValueError(f"Failed to read Excel file: {e}")

    df = df.where(pd.notna(df), None)

    records = []
    skipped = 0

    for _, row in df.iterrows():
        row_dict = row.to_dict()

        source_id = _safe_get(row_dict, col_map, "source_id")

        person_involved = _safe_get(row_dict, col_map, "person_involved")
        if not person_involved:
            person_involved = _safe_get(row_dict, col_map, "person_involved_contractor")

        person_type = None
        emp = _safe_get(row_dict, col_map, "person_involved")
        contractor = _safe_get(row_dict, col_map, "person_involved_contractor")
        if emp:
            person_type = "employee"
        elif contractor:
            person_type = "contractor"

        record = HistoricalIncident(
            source_id=source_id,
            source_file=source_file,
            incident_type=incident_type,
            datetime=_safe_get(row_dict, col_map, "datetime"),
            shift=_safe_get(row_dict, col_map, "shift"),
            location=_safe_get(row_dict, col_map, "location"),
            department=_safe_get(row_dict, col_map, "department"),
            plant=_safe_get(row_dict, col_map, "plant"),
            person_involved=person_involved,
            person_type=person_type,
            actions_taken=_safe_get(row_dict, col_map, "actions_taken"),
            severity=_safe_get(row_dict, col_map, "severity"),
            sif_case=_safe_get(row_dict, col_map, "sif_case"),
            accident_type=_safe_get(row_dict, col_map, "accident_type"),
            accident_agent=_safe_get(row_dict, col_map, "accident_agent"),
            injury_type=_safe_get(row_dict, col_map, "injury_type"),
            injury_agent=_safe_get(row_dict, col_map, "injury_agent"),
            damage_amount=_safe_get(row_dict, col_map, "damage_amount"),
            activity_type=_safe_get(row_dict, col_map, "activity_type"),
            incident_activity=_safe_get(row_dict, col_map, "incident_activity"),
            incident_agent=_safe_get(row_dict, col_map, "incident_agent"),
            raw_data=_sanitize_for_json(row_dict)
        )
        records.append((source_id, record))

    return records, skipped


@router.post("/upload")
async def upload_historical(
    file: UploadFile = File(...),
    incident_type: str = Form(...),
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """
    Admin only — upload an XLS/XLSX file of historical incidents.
    Blocks re-upload of the same filename.
    Deduplicates by source_id for rows where Incident ID is available.
    After saving to PostgreSQL, indexes each new record into Qdrant.
    """
    if incident_type not in INCIDENT_TYPE_MAP:
        raise HTTPException(
            status_code=400,
            detail=f"incident_type must be one of: {list(INCIDENT_TYPE_MAP.keys())}"
        )

    allowed_extensions = (".xls", ".xlsx")
    if not file.filename.lower().endswith(allowed_extensions):
        raise HTTPException(status_code=400, detail="File must be .xls or .xlsx")

    file_bytes = await file.read()

    try:
        records, _ = _parse_xls(file_bytes, incident_type, file.filename)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Block re-upload of the same filename for the same incident type
    existing_file = db.query(HistoricalIncident).filter(
        HistoricalIncident.incident_type == incident_type,
        HistoricalIncident.source_file == file.filename
    ).first()

    if existing_file:
        raise HTTPException(
            status_code=400,
            detail=f"File '{file.filename}' has already been uploaded for {incident_type}. Delete existing records first if you want to re-upload."
        )

    # Deduplicate by source_id for rows where Incident ID is available
    existing_ids = set(
        r.source_id for r in
        db.query(HistoricalIncident.source_id)
        .filter(
            HistoricalIncident.incident_type == incident_type,
            HistoricalIncident.source_id.isnot(None)
        )
        .all()
    )

    imported = 0
    skipped = 0
    new_records = []

    for source_id, record in records:
        if source_id and source_id in existing_ids:
            skipped += 1
            continue
        db.add(record)
        new_records.append(record)
        imported += 1

    db.commit()

    # ── Index new records into Qdrant ─────────────────────────────────────────
    # Refresh each record so it has its DB-assigned id before upserting
    qdrant_success = 0
    qdrant_failed = 0

    for record in new_records:
        try:
            db.refresh(record)
            await upsert_historical_incident(record)
            qdrant_success += 1
        except Exception as e:
            print(f"[historical] qdrant upsert failed for id={record.id}: {e}")
            qdrant_failed += 1

    print(
        f"[historical] upload complete — type={incident_type} file={file.filename} "
        f"imported={imported} skipped={skipped} "
        f"qdrant_indexed={qdrant_success} qdrant_failed={qdrant_failed}"
    )

    return {
        "message": "Upload complete",
        "incident_type": incident_type,
        "file": file.filename,
        "imported": imported,
        "skipped": skipped,
        "total_rows": imported + skipped,
        "qdrant_indexed": qdrant_success,
        "qdrant_failed": qdrant_failed,
    }


@router.get("/")
async def list_historical(
    incident_type: Optional[str] = None,
    skip: int = 0,
    limit: int = 50,
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Admin only — list historical incidents with optional type filter."""
    query = db.query(HistoricalIncident)

    if incident_type:
        query = query.filter(HistoricalIncident.incident_type == incident_type)

    total = query.count()
    records = query.order_by(HistoricalIncident.created_at.desc()).offset(skip).limit(limit).all()

    return {
        "total": total,
        "records": [serialize_historical(r) for r in records]
    }


@router.get("/stats")
async def historical_stats(
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Admin only — counts by incident type."""
    total = db.query(HistoricalIncident).count()
    personal = db.query(HistoricalIncident).filter(
        HistoricalIncident.incident_type == "Personal Injuries"
    ).count()
    near_miss = db.query(HistoricalIncident).filter(
        HistoricalIncident.incident_type == "Near Miss"
    ).count()
    equipment = db.query(HistoricalIncident).filter(
        HistoricalIncident.incident_type == "Equipment Damage"
    ).count()

    return {
        "total": total,
        "Personal Injuries": personal,
        "Near Miss": near_miss,
        "Equipment Damage": equipment
    }


def serialize_historical(record: HistoricalIncident) -> dict:
    return {
        "id": record.id,
        "source_id": record.source_id,
        "source_file": record.source_file,
        "incident_type": record.incident_type,
        "datetime": record.datetime,
        "shift": record.shift,
        "location": record.location,
        "department": record.department,
        "plant": record.plant,
        "person_involved": record.person_involved,
        "person_type": record.person_type,
        "actions_taken": record.actions_taken,
        "severity": record.severity,
        "sif_case": record.sif_case,
        "accident_type": record.accident_type,
        "accident_agent": record.accident_agent,
        "injury_type": record.injury_type,
        "injury_agent": record.injury_agent,
        "damage_amount": record.damage_amount,
        "activity_type": record.activity_type,
        "incident_activity": record.incident_activity,
        "incident_agent": record.incident_agent,
        "created_at": record.created_at.isoformat() if record.created_at else None,
    }