from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field


# ===== users =====

class UserPublic(BaseModel):
    """Public view of a user, privacy-filtered by the caller before instantiation."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    surname: str
    patronymic: Optional[str] = None
    avatar_url: Optional[str] = None
    pronouns: Optional[str] = None
    url: Optional[str] = None
    email: Optional[str] = None
    bio: Optional[str] = None
    position: Optional[str] = None
    company: Optional[str] = None
    workplace: Optional[str] = None


class UserMe(BaseModel):
    """Full self view — the caller is always authorised to see everything."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    name: str
    surname: str
    patronymic: Optional[str] = None
    bio: Optional[str] = None
    position: Optional[str] = None
    company: Optional[str] = None
    workplace: Optional[str] = None
    pronouns: Optional[str] = None
    url: Optional[str] = None
    avatar_url: Optional[str] = None
    confirmed: bool
    privacy_email: str
    privacy_bio: str
    privacy_position: str
    privacy_company: str
    privacy_workplace: str
    created_at: datetime


# ===== auth =====

class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1)


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6)
    name: str = Field(min_length=1, max_length=255)
    surname: str = Field(min_length=1, max_length=255)
    patronymic: Optional[str] = Field(default=None, max_length=255)


# ===== tasks =====

_TASK_STATE_PATTERN = r"^(todo|in_progress|review|done|paused)$"


class TaskCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str = ""
    color: str = "#0ea5e9"
    ended_at: Optional[datetime] = None
    parent_task_id: Optional[int] = None
    assignee_id: Optional[int] = None


class TaskUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    description: Optional[str] = None
    color: Optional[str] = None
    state: Optional[str] = Field(default=None, pattern=_TASK_STATE_PATTERN)
    assignee_id: Optional[int] = None
    ended_at: Optional[datetime] = None


class TaskResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str
    color: str
    state: str
    status: str
    parent_task_id: Optional[int] = None
    creator_id: int
    assignee_id: Optional[int] = None
    created_at: datetime
    ended_at: Optional[datetime] = None


# ===== roles =====

class RoleCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    permissions: list[str] = Field(default_factory=list)


class RoleUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    permissions: Optional[list[str]] = None


class RoleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    task_id: int
    name: str
    is_system: bool
    permissions: list[str]


# ===== misc =====

class MessageResponse(BaseModel):
    message: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
