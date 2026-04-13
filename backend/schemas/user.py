from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime

class UserCreate(BaseModel):
    username: str
    password: str
    email: Optional[str] = None
    job_title: Optional[str] = None
    role: str = "user"

class UserLogin(BaseModel):
    username: str
    password: str

class UserUpdate(BaseModel):
    email: Optional[str] = None
    job_title: Optional[str] = None
    role: Optional[str] = None
    is_active: Optional[bool] = None

class UserResetPassword(BaseModel):
    new_password: str

class UserResponse(BaseModel):
    id: int
    username: str
    email: Optional[str]
    job_title: Optional[str]
    role: str
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True

class UserListResponse(BaseModel):
    total: int
    users: list[UserResponse]

class Token(BaseModel):
    access_token: str
    token_type: str
    user: UserResponse