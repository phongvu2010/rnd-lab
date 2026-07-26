import logging
import sys

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.v1.api import api_router
from .core.config import settings

# Thiết lập ghi nhật ký ra terminal chuẩn đầu ra
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

logger = logging.getLogger(__name__)

# Khởi tạo ứng dụng FastAPI với đầy đủ siêu dữ liệu
app = FastAPI(
    title=settings.PROJECT_NAME,
    description=settings.DESCRIPTION,
    openapi_url=f"{settings.API_PREFIX}/openapi.json",
    version="1.0",
)

# Cấu hình CORS Middleware an toàn để cho phép kết nối từ giao diện frontend và microservices
if settings.BACKEND_CORS_ORIGINS:
    cors_origins = [str(origin).rstrip("/") for origin in settings.BACKEND_CORS_ORIGINS]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )

# Đăng ký các endpoints API
app.include_router(api_router, prefix=settings.API_PREFIX)


@app.get("/", tags=["Hệ thống"])
def root() -> dict[str, str]:
    """Kiểm tra tình trạng hoạt động (healthcheck) của máy chủ API.

    Returns:
        dict[str, str]: Trạng thái hoạt động.
    """
    return {
        "status": "online",
        "service": "Research Lab Agents API",
        "message": "Vietnam Securities Investment Fund",
    }
