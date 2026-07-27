import asyncio
import json
import logging
import shutil
import zipfile

from pathlib import Path
from sqlmodel import Session
from uuid import UUID

from app.core.database import engine
from app.schemas import BacktestRun, Strategy, StrategyStatus
from app.services.kaggle_service import KaggleService, get_kaggle_service

logger = logging.getLogger(__name__)


class BacktestAgent:
    def __init__(self, kaggle: KaggleService):
        """Khởi tạo BacktestAgent với KaggleService."""
        self.kaggle = kaggle

    async def poll_and_evaluate(self, backtest_run_id: UUID, kernel_id: str):
        """
        Hàm chạy nền liên tục kiểm tra trạng thái của Kaggle Kernel và cập nhật kết quả.

        Args:
            backtest_run_id: ID của bản ghi BacktestRun trong DB.
            kernel_id: ID của Kernel trên Kaggle (vd: "username/kernel-slug").
        """
        logger.info(f"[Backtest Agent] Bắt đầu theo dõi Kernel {kernel_id} cho lượt chạy {backtest_run_id}...")
        max_attempts = 60  # Đợi tối đa 30 phút (60 lần * 30 giây)

        for attempt in range(max_attempts):
            try:
                # Gọi kiểm tra trạng thái Kaggle qua Thread vì SDK Kaggle là đồng bộ (blocking)
                status = await asyncio.to_thread(self.kaggle.get_kernel_status, kernel_id)
                logger.info(f"[Backtest Agent] Lần thử {attempt + 1}: Trạng thái Kernel {kernel_id} = {status}")

                if status == "complete":
                    # 1. Tải file zip chứa output từ Kaggle về
                    zip_path_str = await asyncio.to_thread(self.kaggle.pull_kernel_output, kernel_id)
                    zip_path = Path(zip_path_str)

                    # 2. Giải nén đọc file metrics và model
                    extract_dir = zip_path.parent / zip_path.stem
                    extract_dir.mkdir(parents=True, exist_ok=True)

                    try:
                        with zipfile.ZipFile(zip_path, "r") as zip_ref:
                            zip_ref.extractall(extract_dir)

                        metrics_file = extract_dir / "backtest_metrics.json"
                        metrics_data = {}
                        if metrics_file.exists():
                            with open(metrics_file, "r", encoding="utf-8") as f:
                                metrics_data = json.load(f)
                        else:
                            logger.warning(f"[Backtest Agent] Không tìm thấy file backtest_metrics.json trong thư mục output.")

                        # Tìm kiếm file model (.pkl) nếu có
                        model_file_path = None
                        for f_path in extract_dir.glob("*.pkl"):
                            model_file_path = f_path
                            break

                        # Xác định kết quả duyệt chiến lược
                        sharpe = metrics_data.get("sharpe_ratio", 0)
                        is_approved = sharpe > 1.2
                        final_model_path = None

                        # Di chuyển file model vào thư mục registry/models bền vững
                        if model_file_path and is_approved:
                            registry_dir = Path("registry/models")
                            registry_dir.mkdir(parents=True, exist_ok=True)
                            dest_path = registry_dir / f"model_{backtest_run_id}.pkl"

                            # Di chuyển file qua Worker Thread
                            await asyncio.to_thread(shutil.move, str(model_file_path), str(dest_path))
                            final_model_path = str(dest_path)
                            logger.info(f"[Backtest Agent] Đã di chuyển model APPROVED vào: {final_model_path}")

                        # 3. Cập nhật kết quả vào database
                        with Session(engine) as db:
                            run = db.get(BacktestRun, backtest_run_id)
                            if run:
                                run.metrics = metrics_data
                                run.is_successful = True
                                if final_model_path:
                                    run.model_artifact_path = final_model_path

                                strategy = db.get(Strategy, run.strategy_id)
                                if strategy:
                                    if is_approved:
                                        strategy.current_status = StrategyStatus.APPROVED
                                        strategy.description = f"{strategy.description} | APPROVED (Sharpe: {sharpe:.2f})"
                                    else:
                                        strategy.current_status = StrategyStatus.REJECTED
                                        strategy.description = f"{strategy.description} | REJECTED (Sharpe: {sharpe:.2f})"
                                    db.add(strategy)

                                db.add(run)
                                db.commit()
                                logger.info(f"[Backtest Agent] Đã cập nhật thành công kết quả cho BacktestRun ID: {backtest_run_id}")
                    finally:
                        # Dọn dẹp file zip tải về và thư mục tạm
                        if zip_path.exists():
                            zip_path.unlink()

                        shutil.rmtree(extract_dir, ignore_errors=True)

                    break

                elif status == "error":
                    logger.error(f"[Backtest Agent] Kernel {kernel_id} bị lỗi thực thi trên Kaggle.")

                    # 1. Kéo log lỗi thực tế từ Kaggle qua Worker Thread
                    traceback_log = await asyncio.to_thread(self.kaggle.get_kernel_log, kernel_id)

                    with Session(engine) as db:
                        run = db.get(BacktestRun, backtest_run_id)
                        if run:
                            run.is_successful = False
                            # Lưu log lỗi vào DB để API /heal-ml-research có thể lấy ra dùng
                            run.metrics = {
                                "error": "Kaggle execution failed (Error status)",
                                "traceback": traceback_log[-5000:] if traceback_log else "No traceback",
                            }
                            strategy = db.get(Strategy, run.strategy_id)
                            if strategy:
                                strategy.current_status = StrategyStatus.REJECTED
                                strategy.description = f"{strategy.description} | RUN ERROR"
                                db.add(strategy)
                            db.add(run)
                            db.commit()
                    break

                elif status in ("queued", "running", "unknown"):
                    # Trạng thái đang chạy, tiếp tục đợi
                    await asyncio.sleep(30)
                else:
                    logger.warning(f"[Backtest Agent] Nhận trạng thái không xác định: {status}. Tiếp tục đợi...")
                    await asyncio.sleep(30)
            except Exception as e:
                logger.error(f"[Backtest Agent] Lỗi trong quá trình polling Kernel {kernel_id}: {e}")
                await asyncio.sleep(30)
        else:
            logger.error(f"[Backtest Agent] Hết thời gian chờ (Timeout) cho Kernel {kernel_id}.")
            with Session(engine) as db:
                run = db.get(BacktestRun, backtest_run_id)
                if run:
                    run.is_successful = False
                    run.metrics = {"error": "Timeout waiting for Kaggle completion"}
                    strategy = db.get(Strategy, run.strategy_id)
                    if strategy:
                        strategy.current_status = StrategyStatus.REJECTED
                        strategy.description = f"{strategy.description} | TIMEOUT"
                        db.add(strategy)
                    db.add(run)
                    db.commit()


# Hàm factory để sinh đối tượng BacktestAgent mà không cần FastAPI Depends (dùng cho task chạy nền)
def get_backtest_agent() -> BacktestAgent:
    kaggle_service = get_kaggle_service()
    return BacktestAgent(kaggle=kaggle_service)
