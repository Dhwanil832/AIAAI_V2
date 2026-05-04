from sqlalchemy import Column, Integer, String, Boolean, DateTime, JSON, ForeignKey, Text
from sqlalchemy.orm import relationship
from datetime import datetime
from database import Base


class VisionThread(Base):
    __tablename__ = "vision_threads"

    id = Column(Integer, primary_key=True, index=True)

    # Links to a submitted report (post_submission, admin_review)
    report_id = Column(Integer, ForeignKey("incident_reports.id"), nullable=True)

    # Links to an unfinished report (cold_start, mid_intake)
    unfinished_report_id = Column(Integer, ForeignKey("unfinished_reports.id"), nullable=True)

    # Who triggered this thread and from where
    trigger_context = Column(String, nullable=False)
    # "cold_start" | "mid_intake" | "post_submission" | "admin_review"

    triggered_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    # All images stored in MinIO for this thread
    # [{path, filename, uploaded_at}]
    image_paths = Column(JSON, default=list)

    # Image quality assessment
    quality_ok = Column(Boolean, nullable=True)
    quality_reason = Column(String, nullable=True)

    # Everything the agent observed — shown to admin only
    # [{type, observation, severity, detail}]
    # type: "active_danger" | "contradiction" | "unreported_hazard" | "context"
    # severity: "critical" | "high" | "medium" | "low"
    full_observations = Column(JSON, default=list)

    # The single observation surfaced to the reporter
    # {type, observation, severity, detail}
    priority_observation = Column(JSON, nullable=True)

    # Reporter-facing conversation turns
    # [{role: "agent"|"reporter", content, timestamp}]
    conversation = Column(JSON, default=list)

    # How the thread was resolved
    # "pending" | "confirmed" | "corrected" | "escalated" | "dismissed"
    resolution = Column(String, default="pending")

    # Reporter's final words verbatim — stored exactly as said
    resolution_note = Column(Text, nullable=True)

    # Any report fields changed as a result of this thread
    # [{field, section, old_value, new_value, reason, timestamp}]
    amendments = Column(JSON, default=list)

    # Unreported hazards the reporter confirmed are real
    # [{observation, severity, confirmed_by_user_id, timestamp, supervisor_notified}]
    secondary_flags = Column(JSON, default=list)

    # Thread status
    # "open" | "resolved" | "escalated"
    status = Column(String, default="open")

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    report = relationship("IncidentReport", back_populates="vision_threads")
    unfinished_report = relationship("UnfinishedReport", back_populates="vision_threads")
    triggered_by = relationship("User", foreign_keys=[triggered_by_user_id])