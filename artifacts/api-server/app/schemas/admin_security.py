from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, model_validator


class AdminDataScope(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["PLATFORM", "GARAGES"]
    garage_ids: list[UUID] = Field(default_factory=list, max_length=1000)

    @model_validator(mode="after")
    def valid_scope(self):
        if (self.type == "GARAGES" and not self.garage_ids) or (
            self.type == "PLATFORM" and self.garage_ids
        ):
            raise ValueError("GARAGES requires garage IDs; PLATFORM forbids garage IDs")
        if len(set(self.garage_ids)) != len(self.garage_ids):
            raise ValueError("Duplicate garage IDs")
        return self


class AdminRoleAssignment(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role_ids: list[str] = Field(min_length=1, max_length=20)
    data_scope: AdminDataScope
    reason: str = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def validate_assignment(self):
        self.reason = self.reason.strip()
        if not self.reason or len(set(self.role_ids)) != len(self.role_ids):
            raise ValueError("A nonblank reason and unique roles are required")
        if "role_ceo" in self.role_ids and self.data_scope.type != "PLATFORM":
            raise ValueError("CEO requires PLATFORM scope")
        return self
