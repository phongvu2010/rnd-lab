import json
import logging

from functools import lru_cache
from kaggle.api.kaggle_api_extended import KaggleApi
from pathlib import Path

from ..core.config import settings

logger = logging.getLogger(__name__)


class KaggleService:
    def __init__(self):
        """Khởi tạo KaggleService an toàn cho quá trình startup, không gọi authenticate ngay."""
        self._api = None
        self.username = settings.KAGGLE_USERNAME

    def _get_api(self) -> KaggleApi:
        """Thực hiện Lazy Authentication khi thực sự cần truy cập Kaggle API."""
        if self._api is None:
            try:
                api = KaggleApi()
                api.authenticate()
                self._api = api
                logger.info("Xác thực Kaggle API thành công.")
            except Exception as e:
                logger.error(f"Lỗi khi xác thực Kaggle API: {e}")
                raise RuntimeError(
                    "Không thể xác thực với Kaggle API. Vui lòng kiểm tra "
                    f"file cấu hình kaggle.json hoặc biến môi trường: {e}"
                )
        return self._api

    def push_dataset(
        self, folder_path: str, dataset_slug: str, title: str, is_private: bool = True
    ) -> bool:
        """Đóng gói dữ liệu lịch sử và đẩy lên Kaggle dưới dạng Private Dataset."""
        if not self.username:
            raise ValueError(
                "KAGGLE_USERNAME chưa được cấu hình trong file settings hoặc biến môi trường."
            )

        api = self._get_api()

        folder = Path(folder_path)
        folder.mkdir(parents=True, exist_ok=True)

        metadata = {
            "title": title,
            "id": f"{self.username}/{dataset_slug}",
            "licenses": [{"name": "unknown"}],
            "isPrivate": is_private,
        }

        meta_path = folder / "dataset-metadata.json"
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2)

        logger.info(
            f"Đã tạo file metadata cho dataset: {self.username}/{dataset_slug} tại {meta_path}"
        )

        try:
            # Sử dụng dir_mode="zip" để tự động nén trước khi upload
            api.dataset_create_version(
                folder=str(folder),
                version_notes="Auto-sync from R&D Lab Backend",
                dir_mode="zip",
            )
            logger.info(f"Đã cập nhật phiên bản dataset thành công: {dataset_slug}")
            return True
        except Exception as e:
            logger.warning(
                f"Không thể cập nhật phiên bản dataset '{dataset_slug}' ({e}). "
                "Đang thử tạo mới dataset..."
            )
            try:
                api.dataset_create_new(folder=str(folder), dir_mode="zip")
                logger.info(f"Đã tạo mới dataset thành công: {dataset_slug}")
                return True
            except Exception as create_err:
                logger.error(f"Lỗi khi tạo mới dataset '{dataset_slug}': {create_err}")
                return False


# Dependency Injection function cho FastAPI (được cache lại để tránh khởi tạo nhiều lần)
@lru_cache()
def get_kaggle_service() -> KaggleService:
    return KaggleService()
