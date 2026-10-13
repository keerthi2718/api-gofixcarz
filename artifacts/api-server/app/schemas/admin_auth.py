import uuid

from pydantic import AliasChoices, BaseModel, ConfigDict, EmailStr, Field, SecretStr, field_validator


class AdminSignupRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: EmailStr = Field(max_length=255)
    name: str = Field(min_length=1, max_length=255)
    password: SecretStr

    @field_validator("name", mode="before")
    @classmethod
    def trimmed_name(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator("password")
    @classmethod
    def bounded_password(cls, value):
        if not 16 <= len(value.get_secret_value()) <= 128:
            raise ValueError("Admin password must contain 16 to 128 characters.")
        return value


class AdminLoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: EmailStr = Field(validation_alias=AliasChoices("email", "identifier"))
    password: SecretStr
    device_name: str | None = Field(default=None, max_length=100)

    @field_validator("password")
    @classmethod
    def bounded_password(cls, value):
        if not 1 <= len(value.get_secret_value()) <= 128:
            raise ValueError("Invalid password length")
        return value


class AdminRefreshRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    refresh_token: SecretStr = Field(min_length=32, max_length=256)


class AdminMfaRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    challenge_id: uuid.UUID
    code: str = Field(pattern=r"^\d{6}$")


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
