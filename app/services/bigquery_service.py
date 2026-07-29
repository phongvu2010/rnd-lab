import asyncio
import logging
import re
import time

from datetime import datetime
from functools import lru_cache
from google.cloud import bigquery
from pathlib import Path
from typing import Optional

from app.core.config import settings

logger = logging.getLogger(__name__)


class BigQueryService:
    def __init__(self):
        """Khởi tạo BigQuery Client."""
        self.client = bigquery.Client()

    def clean_expired_cache(
        self,
        output_dir: str = "data/staging",
        cache_ttl_days: int = 7,
        force_refresh: bool = False,
    ) -> list[str]:
        """
        Dọn dẹp chỉ các file `.parquet` trong thư mục output_dir khi cache đã vượt quá cache_ttl_days
        (hoặc khi force_refresh=True). Các file cache còn hạn vẫn được giữ nguyên để bảo vệ khi gặp lỗi.
        """
        out_path = Path(output_dir)
        if not out_path.exists():
            return []

        removed_files = []
        for file_path in out_path.glob("*.parquet"):
            try:
                file_age_days = (time.time() - file_path.stat().st_mtime) / (3600 * 24)
                if force_refresh or file_age_days >= cache_ttl_days:
                    file_path.unlink()
                    removed_files.append(file_path.name)
                    logger.info(
                        f"[Cache Cleanup] Đã dọn dẹp file cache parquet đã hết hạn: {file_path} "
                        f"(Tuổi file: {file_age_days:.1f} ngày >= TTL {cache_ttl_days} ngày)"
                    )
            except Exception as e:
                logger.error(
                    f"[Cache Cleanup] Không thể xóa file cache {file_path}: {e}"
                )

        return removed_files

    def fetch_table_to_parquet(
        self,
        table_id: str,
        output_dir: str = "data/staging",
        limit: Optional[int] = None,
        start_date: Optional[str] = None,
        years_back: Optional[int] = None,
        force_refresh: bool = False,
        cache_ttl_days: int = 7,
    ) -> str:
        """
        Truy vấn dữ liệu từ một bảng BigQuery (hỗ trợ cache cục bộ, lọc ngày linh hoạt, years_back và giới hạn dòng) và lưu thành file .parquet.

        Args:
            table_id: Tên bảng (vd: "adj_price" hoặc "raw_price")
            output_dir: Thư mục lưu file tạm trên máy chủ.
            limit: Giới hạn số lượng dòng tải về.
            start_date: Chỉ lấy dữ liệu từ ngày này trở đi (định dạng YYYY-MM-DD).
            years_back: Số năm backtest. Tự động tính start_date từ 01/01 của (Năm hiện tại - years_back) nếu start_date chưa được truyền.
            force_refresh: Bắt buộc tải mới từ BigQuery bất chấp file cache cũ.
            cache_ttl_days: Thời hạn hiệu lực của cache tính theo ngày (mặc định 7 ngày).

        Returns:
            Đường dẫn đến file .parquet đã lưu.
        """
        target_project = self.client.project

        out_path = Path(output_dir)
        out_path.mkdir(parents=True, exist_ok=True)
        file_path = out_path / f"{table_id}.parquet"

        # Kiểm tra cache cục bộ trước khi query BigQuery
        if file_path.exists() and not force_refresh:
            file_age_days = (time.time() - file_path.stat().st_mtime) / (3600 * 24)
            if file_age_days < cache_ttl_days:
                logger.info(
                    f"[Cache Hit] Sử dụng file parquet đã cache cục bộ: {file_path} "
                    f"(Tuổi file: {file_age_days:.1f} ngày < TTL {cache_ttl_days} ngày)"
                )
                return str(file_path)
            else:
                logger.info(
                    f"[Cache Expired] Cache file {file_path} đã hết hạn "
                    f"(Tuổi file: {file_age_days:.1f} ngày >= TTL {cache_ttl_days} ngày). Tiến hành tải dữ liệu mới từ BigQuery..."
                )
        elif force_refresh:
            logger.info(
                f"[Force Refresh] Bắt buộc tải dữ liệu mới từ BigQuery cho bảng {target_project}.{settings.BIGQUERY_DATASET_ID}.{table_id}..."
            )

        # Xử lý tự động start_date theo years_back nếu start_date không được chỉ định
        effective_start_date = start_date
        if not effective_start_date and years_back is not None:
            current_year = datetime.now().year
            start_year = current_year - years_back
            effective_start_date = f"{start_year}-01-01"
            logger.info(
                f"Tự động tính mốc start_date theo years_back={years_back}: {effective_start_date}"
            )

        # Xây dựng câu lệnh SQL có bộ lọc và giới hạn
        query = f"""
            SELECT * FROM `{target_project}.{settings.BIGQUERY_DATASET_ID}.{table_id}`
        """

        conditions = []
        if effective_start_date:
            # Kiểm tra định dạng ngày YYYY-MM-DD để chống SQL injection
            if re.match(r"^\d{4}-\d{2}-\d{2}$", effective_start_date):
                conditions.append(f"trading_date >= '{effective_start_date}'")
            else:
                raise ValueError("start_date phải có định dạng YYYY-MM-DD")

        if conditions:
            query += f" WHERE {' AND '.join(conditions)}"

        query += " ORDER BY trading_date DESC"

        if limit:
            query += f" LIMIT {int(limit)}"

        logger.info(
            f"Đang truy vấn BigQuery: {target_project}.{settings.BIGQUERY_DATASET_ID}.{table_id}..."
        )

        # Tải dữ liệu thẳng vào Pandas DataFrame
        df = self.client.query(query).to_dataframe()

        # Lưu ra file Parquet
        df.to_parquet(file_path, engine="pyarrow", index=False)

        logger.info(f"Đã lưu thành công: {file_path} (Shape: {df.shape})")
        return str(file_path)

    async def fetch_table_to_parquet_async(
        self,
        table_id: str,
        output_dir: str = "data/staging",
        limit: Optional[int] = None,
        start_date: Optional[str] = None,
        years_back: Optional[int] = None,
        force_refresh: bool = False,
        cache_ttl_days: int = 7,
    ) -> str:
        """
        Phiên bản bất đồng bộ của fetch_table_to_parquet, không làm nghẽn Event Loop.
        Sử dụng hàm này khi gọi trực tiếp từ FastAPI Routers.
        """
        return await asyncio.to_thread(
            self.fetch_table_to_parquet,
            table_id,
            output_dir,
            limit,
            start_date,
            years_back,
            force_refresh,
            cache_ttl_days,
        )


# Dependency Injection function cho FastAPI (được cache lại để tái sử dụng client)
@lru_cache()
def get_bigquery_service() -> BigQueryService:
    return BigQueryService()
