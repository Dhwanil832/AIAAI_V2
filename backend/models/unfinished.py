from sqlalchemy import Column, Integer, String, DateTime, JSON, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from datetime import datetime
from database import Base


class UnfinishedReport(Base):
    __tablename__ = "unfinished_reports"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    session_id = Column(String, unique=True, index=True, nullable=False)

    # Full session state
    report_json = Column(JSON, default=dict)
    chat_history = Column(JSON, default=list)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="unfinished_reports")
    uploaded_files = relationship("UploadedFile", back_populates="unfinished_report")
    vision_threads = relationship("VisionThread", back_populates="unfinished_report")


class UploadedFile(Base):
    __tablename__ = "uploaded_files"

    id = Column(Integer, primary_key=True, index=True)
    original_name = Column(String, nullable=False)
    file_path = Column(String, nullable=False)
    file_type = Column(String, nullable=False)
    session_id = Column(String, nullable=False)
    is_temp = Column(Boolean, default=True)
    uploaded_at = Column(DateTime, default=datetime.utcnow)

    # Links to either a finished or unfinished report
    report_id = Column(Integer, ForeignKey("incident_reports.id"), nullable=True)
    unfinished_report_id = Column(Integer, ForeignKey("unfinished_reports.id"), nullable=True)

    # Relationships
    report = relationship("IncidentReport", back_populates="uploaded_files")
    unfinished_report = relationship("UnfinishedReport", back_populates="uploaded_files")