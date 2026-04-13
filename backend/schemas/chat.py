from pydantic import BaseModel
from typing import Optional, Any

class ChatMessage(BaseModel):
    message: Optional[str] = None
    button_choice: Optional[str] = None
    current_data: Optional[dict] = None
    user_info: Optional[dict] = None
    session_id: Optional[str] = None

class ChatResponse(BaseModel):
    response: str
    extracted: Optional[dict] = None
    show_widget: Optional[str] = None
    suggestions: Optional[list] = None
    summary: Optional[dict] = None
    redirect: Optional[str] = None
    session_id: Optional[str] = None