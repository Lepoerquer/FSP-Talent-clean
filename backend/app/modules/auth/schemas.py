from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserRole(str, Enum):
    CANDIDATE = "CANDIDATE"
    EMPLOYER = "EMPLOYER"
    ADMIN = "ADMIN"


class RegisterRole(str, Enum):
    """Roles open to self-registration: an administrator is never created through the public API."""
    CANDIDATE = "CANDIDATE"
    EMPLOYER = "EMPLOYER"


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=6, description="Password min 6 characters")
    role: RegisterRole = RegisterRole.CANDIDATE
    fsp_id: str | None = Field(
        None,
        description="Optional ID in FSP Registry. Stored as declared; achievements are verified by POST /me/fsp/link",
    )
    first_name: str | None = None
    last_name: str | None = None
    company_name: str | None = Field(None, description="Company name if registering as EMPLOYER")
    
    # 152-FZ Mandatory consent flags
    consent_personal_data: bool = Field(True, description="Consent to processing of personal data (152-FZ)")
    consent_profile_distribution: bool = Field(True, description="Consent to profile distribution to employers (152-FZ)")


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user_id: str
    email: str
    role: str
    fsp_id: str | None = None
    email_verified: bool


class VerifyEmailRequest(BaseModel):
    email: EmailStr | None = Field(None, description="Must match the signed-in user's email if given")
    code: str | None = Field("123456", description="Verification code (the demo stand accepts 123456)")


class UserResponse(BaseModel):
    id: str
    email: str
    role: str
    is_active: bool
    email_verified: bool
    fsp_id: str | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
