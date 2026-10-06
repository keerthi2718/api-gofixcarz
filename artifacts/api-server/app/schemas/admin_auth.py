import uuid

from pydantic import BaseModel, ConfigDict, EmailStr, Field, SecretStr, field_validator


class AdminLoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: EmailStr
    password: SecretStr

    @field_validator("password")
    @classmethod
    def bounded_password(cls, value):
        if not 1 <= len(value.get_secret_value()) <= 128:
            raise ValueError("Invalid password length")
        return value


class AdminRefreshRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    refresh_token: SecretStr = Field(min_length=32, max_length=256)


class AdminIdentity(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    email: str
    name: str
    role: str
    is_active: bool


class AdminMenu(BaseModel):
    key: str
    label: str
    api: str
