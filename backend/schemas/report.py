from pydantic import BaseModel
from typing import Optional, Any
from datetime import datetime

class ReportResponse(BaseModel):
    id: int
    report_json: dict
    creator_name: str
    creator_job_title: str
    flagged: bool
    flag_reason: Optional[str]
    created_at: datetime
    last_modified_at: datetime

    class Config:
        from_attributes = True

class UnfinishedReportResponse(BaseModel):
    id: int
    session_id: str
    report_data: dict
    last_updated: datetime

    class Config:
        from_attributes = True