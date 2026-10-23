"""Strict inputs for platform management; no client-controlled ownership."""
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, EmailStr, Field, SecretStr, model_validator
from app.schemas.admin_security import AdminDataScope
from app.schemas.garage import GarageUpdate, GarageResponse


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class GaragePatch(GarageUpdate):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    reason: str = Field(min_length=1, max_length=500)
    expected_version: int = Field(strict=True, ge=1)
    operational_status: Literal["ACTIVE", "SUSPENDED"] | None = None
    verification_status: Literal["UNVERIFIED", "VERIFIED", "REJECTED"] | None = None

    @model_validator(mode="after")
    def nonempty(self):
        changes = self.model_fields_set - {"reason", "expected_version"}
        if not changes:
            raise ValueError("At least one editable field is required")
        for field in changes & {"name", "owner", "operational_status", "verification_status"}:
            if getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        limits = {"name": 255, "owner": 255, "address": 2000, "city": 100,
                  "state": 100, "zipcode": 20, "country": 100, "alternate_number": 30}
        for field, limit in limits.items():
            value = getattr(self, field)
            if value is not None and len(value) > limit:
                raise ValueError(f"{field} exceeds {limit} characters")
        return self


class GarageListItem(GarageResponse):
    job_card_count: int = 0


class RoleCreate(Input):
    name: str = Field(min_length=1, max_length=100)
    permissions: list[str] = Field(min_length=1, max_length=100)
    reason: str = Field(min_length=1, max_length=500)


class RolePatch(Input):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    permissions: list[str] | None = Field(default=None, min_length=1, max_length=100)
    expected_version: int = Field(strict=True, ge=1)
    reason: str = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def nonempty(self):
        changes = self.model_fields_set & {"name", "permissions"}
        if not changes or any(getattr(self, x) is None for x in changes):
            raise ValueError("Provide a non-null name or permissions")
        return self


class VersionedDelete(Input):
    expected_version: int = Field(strict=True, ge=1)
    reason: str = Field(min_length=1, max_length=500)


class InvitationCreate(Input):
    email: EmailStr
    name: str = Field(min_length=1, max_length=255)
    role_ids: list[str] = Field(min_length=1, max_length=20)
    data_scope: AdminDataScope
    reason: str = Field(min_length=1, max_length=500)


class InvitationAccept(Input):
    invitation_id: UUID
    invitation_token: SecretStr = Field(min_length=40, max_length=200)
    password: SecretStr = Field(min_length=16, max_length=128)
