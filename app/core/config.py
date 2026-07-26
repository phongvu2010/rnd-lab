from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional


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


# Khởi tạo đối tượng settings duy nhất cho toàn hệ thống
settings = Settings()
