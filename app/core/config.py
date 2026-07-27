from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Any, Optional
from urllib.parse import quote_plus


class Settings(BaseSettings):
    """Lớp chứa toàn bộ cấu hình hệ thống của Alpha Agent."""

    # Cho phép đọc cấu hình từ file .env
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        env_ignore_empty=True,
        extra="ignore",
    )

    # Project Config
    PROJECT_NAME: str = "Vietnam Securities Investment Fund - Research Lab Agents API"
    DESCRIPTION: str = "Hệ thống Nghiên cứu & Phát triển (R&D / Lab)."
    API_PREFIX: str = "/api/v1"

    # CORS Middleware Config
    BACKEND_CORS_ORIGINS: list[str] = [
        "http://localhost:3000",
        "http://localhost:5173",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
    ]

    # Kaggle config
    KAGGLE_USERNAME: Optional[str] = Field(
        default=None, description="Tên tài khoản Kaggle API"
    )

    # Redis config
    REDIS_URL: str = Field(
        default="redis://localhost:6379/0", description="URL kết nối Redis DB"
    )

    # Postgres config
    POSTGRES_SERVER: str = "timescaledb"
    POSTGRES_PORT: str = "5432"
    POSTGRES_USER: str = "admin"
    POSTGRES_PASSWORD: str = "Admin@123"
    POSTGRES_DB: str = "rnd_lab_db"

    DATABASE_URL: str = ""
    ECHO_SQL: bool = False

    @model_validator(mode="before")
    @classmethod
    def assemble_db_connection(cls, data: Any) -> Any:
        if isinstance(data, dict):
            # Chỉ lắp ráp DATABASE_URL nếu chưa được truyền từ môi trường
            database_url = data.get("DATABASE_URL")
            if not database_url:
                server = data.get("POSTGRES_SERVER", "timescaledb")
                port = data.get("POSTGRES_PORT", "5432")
                user = data.get("POSTGRES_USER", "admin")
                password = data.get("POSTGRES_PASSWORD", "Admin@123")
                db = data.get("POSTGRES_DB", "rnd_lab_db")

                # Mã hóa ký tự đặc biệt trong username và password (ví dụ ký tự "@")
                safe_user = quote_plus(user)
                safe_password = quote_plus(password)

                data["DATABASE_URL"] = (
                    f"postgresql://{safe_user}:{safe_password}@{server}:{port}/{db}"
                )
        return data

    # OpenAI config
    OPENAI_API_KEY: Optional[str] = Field(
        default=None,
        description="Khóa API OpenAI",
    )
    OPENAI_MODEL: str = Field(
        default="gpt-4o",
        description="Model OpenAI mặc định sử dụng cho Research Agent",
    )


# Khởi tạo đối tượng settings duy nhất cho toàn hệ thống
settings = Settings()
