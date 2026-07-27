import asyncio
import logging
import sys

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import select, Session, SQLModel

from .agents.backtest_agent import get_backtest_agent
from .api.v1.api import api_router
from .core.config import settings
from .core.database import engine

# Import các models để chúng đăng ký với SQLModel.metadata trước khi chạy create_all
from .schemas import BacktestRun, Strategy, StrategyStatus

# Thiết lập ghi nhật ký ra terminal chuẩn đầu ra
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Quản lý vòng đời của ứng dụng FastAPI.
    Tự động kiểm tra và khởi tạo database schemas, đồng thời khôi phục các tác vụ đang chạy dở.
    """
    logger.info("Đang khởi tạo database schemas...")
    try:
        SQLModel.metadata.create_all(engine)
        logger.info("Khởi tạo database schemas thành công!")

        # --- State Recovery: Phục hồi các task đang chạy dở ---
        with Session(engine) as db:
            statement = (
                select(BacktestRun)
                .join(Strategy)
                .where(Strategy.current_status == StrategyStatus.TESTING)
                .where(BacktestRun.is_successful == False)
            )
            pending_runs = db.exec(statement).all()

            if pending_runs:
                logger.info(f"Phát hiện {len(pending_runs)} lượt chạy chưa hoàn thành. Đang khôi phục (State Recovery)...")
                backtest_agent = get_backtest_agent()

                for run in pending_runs:
                    # Bỏ qua các run bị lỗi ngay từ bước tạo (chưa có kernel id thực tế)
                    if run.kaggle_kernel_id and not run.kaggle_kernel_id.startswith(("pending", "error", "failed")):
                        # Đẩy vào event loop chạy ngầm để tiếp tục theo dõi
                        asyncio.create_task(
                            backtest_agent.poll_and_evaluate(run.id, run.kaggle_kernel_id)
                        )
                        logger.info(f"Đã khôi phục tác vụ theo dõi Kaggle ID: {run.kaggle_kernel_id}")
    except Exception as e:
        logger.error(f"Lỗi khởi tạo database schemas hoặc State Recovery: {e}")

    yield
    logger.info("Đang tắt ứng dụng...")


# Khởi tạo ứng dụng FastAPI với đầy đủ siêu dữ liệu
app = FastAPI(
    title=settings.PROJECT_NAME,
    description=settings.DESCRIPTION,
    openapi_url=f"{settings.API_PREFIX}/openapi.json",
    version="1.0",
    lifespan=lifespan,
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
