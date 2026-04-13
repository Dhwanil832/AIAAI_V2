from sqlalchemy import Column, Integer, String, DateTime, JSON, ForeignKey
from sqlalchemy.orm import relationship
import datetime as dt
from database import Base


class HistoricalIncident(Base):
    __tablename__ = "historical_incidents"

    id = Column(Integer, primary_key=True, index=True)

    # Source tracking — which file this came from, original ID for deduplication
    source_id = Column(String, nullable=True, index=True)
    source_file = Column(String, nullable=True)  # e.g. "personal_injuries_2024.xlsx"

    # Incident type — Personal Injuries / Near Miss / Equipment Damage
    incident_type = Column(String, nullable=False, index=True)

    # Core fields — shared across all types
    datetime = Column(String, nullable=True)
    shift = Column(String, nullable=True)
    location = Column(String, nullable=True, index=True)
    department = Column(String, nullable=True)
    plant = Column(String, nullable=True)
    person_involved = Column(String, nullable=True)
    person_type = Column(String, nullable=True)  # employee / contractor
    actions_taken = Column(String, nullable=True)
    severity = Column(String, nullable=True)
    sif_case = Column(String, nullable=True)

    # Personal Injuries + Near Miss fields
    accident_type = Column(String, nullable=True, index=True)
    accident_agent = Column(String, nullable=True)
    injury_type = Column(String, nullable=True, index=True)
    injury_agent = Column(String, nullable=True)

    # Equipment Damage fields
    damage_amount = Column(String, nullable=True)
    activity_type = Column(String, nullable=True)
    incident_activity = Column(String, nullable=True)
    incident_agent = Column(String, nullable=True)

    # Full original row stored as JSON — nothing lost
    raw_data = Column(JSON, nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=dt.datetime.utcnow)


