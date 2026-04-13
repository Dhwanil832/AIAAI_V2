from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from database import get_db
from models.user import User
from schemas.user import UserUpdate, UserResetPassword, UserResponse, UserListResponse
from core.auth import hash_password
from core.dependencies import get_current_admin
from datetime import datetime

router = APIRouter()


class UserCreate(BaseModel):
    username: str
    password: str
    email: Optional[str] = None
    job_title: Optional[str] = None
    role: str = "user"


@router.post("/", response_model=UserResponse, status_code=201)
def create_user(
    body: UserCreate,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin)
):
    """Admin only — create a new user."""
    if len(body.username.strip()) < 3:
        raise HTTPException(status_code=400, detail="Username must be at least 3 characters")
    if len(body.password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")
    if body.role not in ("user", "admin"):
        raise HTTPException(status_code=400, detail="Role must be 'user' or 'admin'")

    existing = db.query(User).filter(User.username == body.username).first()
    if existing:
        raise HTTPException(status_code=400, detail="Username already taken")

    if body.email:
        existing_email = db.query(User).filter(User.email == body.email).first()
        if existing_email:
            raise HTTPException(status_code=400, detail="Email already in use")

    new_user = User(
        username=body.username.strip(),
        hashed_password=hash_password(body.password),
        email=body.email or None,
        job_title=body.job_title or None,
        role=body.role,
        is_active=True,
        created_at=datetime.utcnow()
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    print(f"[users] user {new_user.username} created by admin {current_admin.username}")
    return new_user


@router.get("/", response_model=UserListResponse)
def list_users(
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin)
):
    """Admin only — list all users."""
    users = db.query(User).order_by(User.created_at.desc()).all()
    return {"total": len(users), "users": users}


@router.get("/{user_id}", response_model=UserResponse)
def get_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin)
):
    """Admin only — get a single user by ID."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.patch("/{user_id}", response_model=UserResponse)
def update_user(
    user_id: int,
    updates: UserUpdate,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin)
):
    """Admin only — update a user's email, job title, role, or active status."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if user.id == current_admin.id and updates.is_active is False:
        raise HTTPException(status_code=400, detail="You cannot deactivate your own account")

    if user.id == current_admin.id and updates.role and updates.role != "admin":
        raise HTTPException(status_code=400, detail="You cannot change your own role")

    if updates.email is not None:
        existing = db.query(User).filter(
            User.email == updates.email,
            User.id != user_id
        ).first()
        if existing:
            raise HTTPException(status_code=400, detail="Email already in use")
        user.email = updates.email

    if updates.job_title is not None:
        user.job_title = updates.job_title

    if updates.role is not None:
        if updates.role not in ("user", "admin"):
            raise HTTPException(status_code=400, detail="Role must be 'user' or 'admin'")
        user.role = updates.role

    if updates.is_active is not None:
        user.is_active = updates.is_active

    db.commit()
    db.refresh(user)
    print(f"[users] user {user.username} updated by admin {current_admin.username}")
    return user


@router.post("/{user_id}/reset-password", response_model=UserResponse)
def reset_password(
    user_id: int,
    body: UserResetPassword,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin)
):
    """Admin only — reset a user's password."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if len(body.new_password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")

    user.hashed_password = hash_password(body.new_password)
    db.commit()
    db.refresh(user)
    print(f"[users] password reset for {user.username} by admin {current_admin.username}")
    return user


@router.delete("/{user_id}")
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin)
):
    """Admin only — delete a user. Cannot delete your own account."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if user.id == current_admin.id:
        raise HTTPException(status_code=400, detail="You cannot delete your own account")

    db.delete(user)
    db.commit()
    print(f"[users] user {user.username} deleted by admin {current_admin.username}")
    return {"message": f"User '{user.username}' deleted successfully"}