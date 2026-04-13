from sqlalchemy import Column, Integer, String, Boolean, DateTime, JSON, ForeignKey, Text
from sqlalchemy.orm import relationship
from datetime import datetime
from database import Base


class IncidentReport(Base):
    __tablename__ = "incident_reports"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    # Core report data
    report_json = Column(JSON, nullable=False)

    # Context document — full narrative, chat history, everything
    context_document = Column(JSON, nullable=True)

    # Creator info
    creator_name = Column(String, nullable=False)
    creator_job_title = Column(String, nullable=False)

    # Last modified
    last_modified_name = Column(String, nullable=True)
    last_modified_job = Column(String, nullable=True)

    # Flagging
    flagged = Column(Boolean, default=False)
    flag_reason = Column(String, nullable=True)

    # Similar incidents — filled by similarity agent on submit
    similar_incidents = Column(JSON, nullable=True)
    supervisor_notified = Column(Boolean, default=False)

    # Review workflow
    # Status: submitted → under_review → approved / needs_more_info / closed
    status = Column(String, default="submitted", nullable=False)
    review_note = Column(Text, nullable=True)
    reviewed_by = Column(String, nullable=True)
    reviewed_at = Column(DateTime, nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    last_modified_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="reports")
    uploaded_files = relationship("UploadedFile", back_populates="report")
