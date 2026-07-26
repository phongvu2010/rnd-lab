from fastapi import APIRouter

from .endpoints import backtest_runs, data, strategies

api_router = APIRouter()
api_router.include_router(
    data.router, prefix="/data", tags=["Đồng bộ Dữ liệu (Data Agent)"]
)
api_router.include_router(
    strategies.router, prefix="/strategies", tags=["Chiến lược đầu tư (Strategies)"]
)
api_router.include_router(
    backtest_runs.router,
    prefix="/backtest-runs",
    tags=["Lượt chạy kiểm định (Backtest Runs)"],
)
