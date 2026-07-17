from typing import List
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # App
    APP_NAME: str = "Garage Management API"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    ENVIRONMENT: str = "development"

    # Database — injected automatically by Replit
    DATABASE_URL: str = ""

    # JWT — uses Replit's SESSION_SECRET
    SECRET_KEY: str = Field(default="dev-secret-key-change-in-production", alias="SESSION_SECRET")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days

    # OTP
    OTP_EXPIRY_SECONDS: int = 300  # 5 minutes
    OTP_LENGTH: int = 6

    # MSG91
    MSG91_AUTH_KEY: str = ""
    MSG91_DLT_TE_ID: str = "1307175464483723626"
    MSG91_SENDER: str = "MYSKWT"
    MSG91_ROUTE: str = "4"
    MSG91_COUNTRY: str = "91"

    # CORS
    CORS_ORIGINS: List[str] = ["*"]


settings = Settings()
