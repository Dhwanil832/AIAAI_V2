from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from database import get_db
from core.dependencies import get_current_user
from models.user import User
from models.report import IncidentReport
from collections import defaultdict
import json

router = APIRouter()


@router.get("/analytics")
async def get_analytics(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Returns analytics data for the dashboard.
    Admins see all reports. Regular users see only their own.
    """
    query = db.query(IncidentReport)
    if current_user.role != "admin":
        query = query.filter(IncidentReport.user_id == current_user.id)

    reports = query.all()

    total = len(reports)
    flagged_count = 0
    type_breakdown = defaultdict(int)
    severity_breakdown = defaultdict(int)
    location_counts = defaultdict(int)
    monthly_counts = defaultdict(int)
    sif_count = 0

    for report in reports:
        report_json = report.report_json
        if isinstance(report_json, str):
            report_json = json.loads(report_json)

        basic = report_json.get("basic_info", {}) if report_json else {}
        injury = report_json.get("injury_data", {}) if report_json else {}
        near_miss = report_json.get("near_miss_data", {}) if report_json else {}
        equipment = report_json.get("equipment_damage_data", {}) if report_json else {}

        # Flagged
        if report.flagged:
            flagged_count += 1

        # Incident type
        incident_type = basic.get("incident_type", "Unknown")
        type_breakdown[incident_type] += 1

        # Severity
        severity = basic.get("severity", "").lower()
        if severity:
            severity_breakdown[severity] += 1
        else:
            severity_breakdown["unknown"] += 1

        # Location
        location = basic.get("location", "").strip()
        if location:
            location_counts[location] += 1

        # Monthly trend — use created_at
        if report.created_at:
            month_key = report.created_at.strftime("%Y-%m")
            monthly_counts[month_key] += 1

        # SIF case
        sif = (
            injury.get("sif_case", "") or
            near_miss.get("sif_case", "") or
            equipment.get("sif_case", "")
        )
        if sif and sif.lower() in ("yes", "y", "true", "1"):
            sif_count += 1

    # Top 5 locations
    top_locations = sorted(location_counts.items(), key=lambda x: x[1], reverse=True)[:5]

    # Last 6 months trend — fill in zeros for missing months
    from datetime import datetime, timedelta
    today = datetime.utcnow()
    trend = []
    for i in range(5, -1, -1):
        d = today.replace(day=1) - timedelta(days=1)
        d = (today.replace(day=1) - timedelta(days=30 * i))
        month_key = d.strftime("%Y-%m")
        month_label = d.strftime("%b %Y")
        trend.append({
            "month": month_label,
            "count": monthly_counts.get(month_key, 0)
        })

    return {
        "total": total,
        "flagged": flagged_count,
        "sif_cases": sif_count,
        "type_breakdown": dict(type_breakdown),
        "severity_breakdown": dict(severity_breakdown),
        "top_locations": [{"location": loc, "count": cnt} for loc, cnt in top_locations],
        "monthly_trend": trend
    }