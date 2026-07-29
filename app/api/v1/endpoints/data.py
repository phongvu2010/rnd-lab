import asyncio
import logging

from datetime import datetime
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from pathlib import Path
from pydantic import BaseModel, Field
from typing import List, Optional
from uuid import uuid4

from app.core.config import settings
from app.services.bigquery_service import BigQueryService, get_bigquery_service
from app.services.kaggle_service import KaggleService, get_kaggle_service
from app.services.task_service import TaskService, get_task_service

logger = logging.getLogger(__name__)
router = APIRouter()


class SyncDataRequest(BaseModel):
    table_ids: List[str] = Field(
        default=["adj_price", "raw_price"],
        description="Danh sách các bảng cần kéo dữ liệu (vd: adj_price, raw_price)",
    )
    output_dir: str = Field(
        default="data/staging",
        description="Thư mục gốc lưu trữ tạm các file Parquet (sẽ tự động tạo thư mục con theo dataset_slug để cách ly)",
    )
    start_date: Optional[str] = Field(
        default=None,
        description="Lọc ngày từ ngày này trở đi (định dạng YYYY-MM-DD). Nếu không truyền, mặc định dùng years_back.",
    )
    years_back: Optional[int] = Field(
        default=10,
        description="Số năm backtest tính từ ngày 01/01 của N năm trước (mặc định 10 năm)",
    )
    force_refresh: bool = Field(
        default=False,
        description="Bắt buộc tải lại dữ liệu mới từ BigQuery bất chấp cache cũ",
    )
    cache_ttl_days: int = Field(
        default=7,
        description="Thời hạn hiệu lực của cache tính theo ngày (mặc định 7 ngày = 1 tuần)",
    )
    is_private: bool = Field(
        default=True,
        description="Đẩy dataset lên Kaggle dưới dạng Private Dataset (bảo mật)",
    )
    limit: Optional[int] = Field(
        default=None,
        description="Giới hạn số dòng tải về cho mỗi bảng",
    )


class SyncDataResponse(BaseModel):
    task_id: str
    message: str
    status: str
    dataset_slug: str
    synced_tables: List[str]


class TaskStatusResponse(BaseModel):
    task_id: str
    dataset_slug: str
    status: str
    created_at: str
    updated_at: str
    synced_files: List[str]
    error: Optional[str] = None


@router.post(
    "/sync",
    response_model=SyncDataResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Đồng bộ dữ liệu từ BigQuery lên Kaggle Dataset",
)
async def sync_data_to_kaggle(
    request: SyncDataRequest,
    background_tasks: BackgroundTasks,
    bq_service: BigQueryService = Depends(get_bigquery_service),
    kaggle_service: KaggleService = Depends(get_kaggle_service),
    task_service: TaskService = Depends(get_task_service),
):
    """
    Kích hoạt Tác tử Dữ liệu (Data Agent) thực hiện luồng đồng bộ nguyên liệu:

    1. Truy vấn các bảng dữ liệu từ Google Cloud BigQuery và kết xuất ra các file `.parquet` trong thư mục cách ly `data/staging/{dataset_slug}/`.
    2. Đóng gói nén zip và tự động tải tập dữ liệu lên Kaggle dưới dạng Private Dataset (`vn-stock-market-data`).

    Tác vụ này được thực thi ngầm (**Background Task**) để không làm gián đoạn HTTP request.
    Có thể sử dụng endpoint `GET /sync/status/{task_id}` để kiểm tra tiến độ.
    """
    task_id = str(uuid4())
    now_iso = datetime.now().isoformat()
    dataset_slug = settings.KAGGLE_DATASET_SLUG

    # Thư mục staging cách ly riêng cho từng dataset_slug
    target_staging_dir = str(Path(request.output_dir) / dataset_slug)

    # Khởi tạo dữ liệu task ban đầu
    task_info = {
        "task_id": task_id,
        "dataset_slug": dataset_slug,
        "status": "PENDING",
        "created_at": now_iso,
        "updated_at": now_iso,
        "synced_files": [],
        "error": None,
    }
    task_service.save_task(task_id, task_info)

    async def sync_task_runner(task_id: str, req: SyncDataRequest, staging_dir: str):
        current_task = task_service.get_task(task_id) or task_info
        current_task["status"] = "RUNNING"
        current_task["updated_at"] = datetime.now().isoformat()
        task_service.save_task(task_id, current_task)

        synced_files = []
        try:
            # Chỉ dọn dẹp các file cache parquet đã hết hạn trước khi tải dữ liệu mới
            await asyncio.to_thread(
                bq_service.clean_expired_cache,
                output_dir=staging_dir,
                cache_ttl_days=req.cache_ttl_days,
                force_refresh=req.force_refresh,
            )

            for table_id in req.table_ids:
                logger.info(
                    f"[Data Agent] [{task_id}] Đang kiểm tra/kéo dữ liệu bảng {settings.BIGQUERY_DATASET_ID}.{table_id} từ BigQuery..."
                )
                file_path = await bq_service.fetch_table_to_parquet_async(
                    table_id=table_id,
                    output_dir=staging_dir,
                    limit=req.limit,
                    start_date=req.start_date,
                    years_back=req.years_back,
                    force_refresh=req.force_refresh,
                    cache_ttl_days=req.cache_ttl_days,
                )
                synced_files.append(file_path)
                current_task["synced_files"] = synced_files
                current_task["updated_at"] = datetime.now().isoformat()
                task_service.save_task(task_id, current_task)

            logger.info(
                f"[Data Agent] [{task_id}] Đã tải về {len(synced_files)} file parquet. "
                f"Đang đóng gói từ '{staging_dir}' và đẩy lên Kaggle Dataset '{dataset_slug}'..."
            )
            success = await asyncio.to_thread(
                kaggle_service.push_dataset,
                folder_path=staging_dir,
                is_private=req.is_private,
            )

            current_task["updated_at"] = datetime.now().isoformat()
            if success:
                current_task["status"] = "SUCCESS"
                task_service.save_task(task_id, current_task)
                logger.info(
                    f"[Data Agent] [{task_id}] Đồng bộ thành công Kaggle Dataset '{dataset_slug}'!"
                )
            else:
                current_task["status"] = "FAILED"
                current_task["error"] = "Tải dữ liệu lên Kaggle không thành công."
                task_service.save_task(task_id, current_task)
                logger.error(
                    f"[Data Agent] [{task_id}] Đồng bộ thất bại khi đẩy lên Kaggle Dataset '{dataset_slug}'."
                )
        except Exception as e:
            logger.error(
                f"[Data Agent] [{task_id}] Lỗi trong quá trình đồng bộ dữ liệu: {e}"
            )
            current_task["status"] = "FAILED"
            current_task["error"] = str(e)
            current_task["updated_at"] = datetime.now().isoformat()
            task_service.save_task(task_id, current_task)

    # Đẩy tác vụ cho FastAPI chạy ngầm
    background_tasks.add_task(sync_task_runner, task_id, request, target_staging_dir)

    return SyncDataResponse(
        task_id=task_id,
        message="Tác tử Dữ liệu đã tiếp nhận yêu cầu và đang tiến hành đồng bộ dữ liệu BigQuery -> Kaggle...",
        status="PENDING",
        dataset_slug=dataset_slug,
        synced_tables=request.table_ids,
    )


@router.get(
    "/sync/status/{task_id}",
    response_model=TaskStatusResponse,
    summary="Kiểm tra trạng thái tiến trình đồng bộ dữ liệu",
)
async def get_sync_task_status(
    task_id: str,
    task_service: TaskService = Depends(get_task_service),
):
    """Truy vấn trạng thái thực thi của tác vụ ngầm đồng bộ dữ liệu theo `task_id`."""
    task_info = task_service.get_task(task_id)
    if not task_info:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Không tìm thấy tác vụ với ID '{task_id}'.",
        )
    return task_info


@router.get(
    "/sync/tasks",
    response_model=List[TaskStatusResponse],
    summary="Lấy danh sách tất cả các tác vụ đồng bộ gần đây",
)
async def list_sync_tasks(
    task_service: TaskService = Depends(get_task_service),
):
    """Lấy danh sách lịch sử các tác vụ đồng bộ dữ liệu."""
    return task_service.list_tasks()
