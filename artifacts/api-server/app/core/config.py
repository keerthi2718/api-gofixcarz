from typing import List
from pydantic import Field, SecretStr
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
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 10080  # 1 week (7 * 24 * 60)
    REFRESH_TOKEN_EXPIRE_DAYS: int = 365  # 1 year

    # OTP
    OTP_EXPIRY_SECONDS: int = 300  # 5 minutes
    OTP_LENGTH: int = 6

    # MSG91
    MSG91_AUTH_KEY: str = ""
    MSG91_TEMPLATE_ID: str = "6aabb705139475b847069b62"
    MSG91_DLT_TE_ID: str = "1307175464483723626"
    MSG91_SENDER: str = "GoFixAuto"
    MSG91_ROUTE: str = "4"
    MSG91_COUNTRY: str = "91"
    MSG91_WEBHOOK_TOKEN: SecretStr = SecretStr("")
    MSG91_DIAGNOSTICS_TOKEN: SecretStr = SecretStr("")

    # Database connection pool
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20

    # AWS S3
    AWS_API_KEY: str = ""          # Access Key ID
    AWS_SECRET_KEY: str = ""       # Secret Access Key
    S3_BUCKET_NAME: str = ""
    AWS_REGION: str = "ap-south-1"
    S3_UPLOAD_EXPIRES: int = 300   # seconds — pre-signed PUT URL lifetime
    S3_DOWNLOAD_EXPIRES: int = 3600  # seconds — pre-signed GET URL lifetime

    # CORS
    CORS_ORIGINS: List[str] = [
        "http://localhost",
        "http://localhost:3000",
        "http://localhost:5173",
        "http://localhost:5174",
        "https://partner.gofixcarz.com",
    ]


settings = Settings()
