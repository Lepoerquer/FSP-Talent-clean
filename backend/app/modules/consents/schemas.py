from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class ConsentType(str, Enum):
    PERSONAL_DATA = "PERSONAL_DATA"
    PROFILE_DISTRIBUTION = "PROFILE_DISTRIBUTION"


class ConsentGiveRequest(BaseModel):
    consent_type: ConsentType
    version: str = Field("1.0", description="Document version consented to")


class ConsentRevokeRequest(BaseModel):
    consent_type: ConsentType


class ConsentItemResponse(BaseModel):
    id: str
    user_id: str
    consent_type: str
    version: str
    is_given: bool
    given_at: datetime
    revoked_at: datetime | None = None
    title: str | None = None
    description: str | None = None

    model_config = ConfigDict(from_attributes=True)


class ConsentStatusResponse(BaseModel):
    user_id: str
    personal_data_active: bool
    profile_distribution_active: bool
    consents: list[ConsentItemResponse]
