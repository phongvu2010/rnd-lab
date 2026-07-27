import json
import logging
import shutil

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

    def push_kernel(
        self,
        notebook_path: str,
        kernel_slug: str,
        title: str,
        dataset_sources: list = None,
    ) -> str:
        """Đẩy file .ipynb lên Kaggle để chạy ngầm (Training/Backtesting)."""
        if not self.username:
            raise ValueError(
                "KAGGLE_USERNAME chưa được cấu hình trong file settings hoặc biến môi trường."
            )

        src_nb = Path(notebook_path)

        # 1. Tạo thư mục tạm để chứa code chuẩn bị push
        staging_dir = Path("data/staging") / kernel_slug
        try:
            staging_dir.mkdir(parents=True, exist_ok=True)

            # 2. Copy file .ipynb vào thư mục tạm
            shutil.copy(src_nb, staging_dir)

            # 3. Tạo file kernel-metadata.json
            metadata = {
                "id": f"{self.username}/{kernel_slug}",
                "title": title,
                "code_file": src_nb.name,
                "language": "python",
                "kernel_type": "notebook",
                "is_private": "true",
                "enable_gpu": "true",  # Bật GPU nếu cần train ML nặng
                "enable_internet": "true",
                "dataset_sources": dataset_sources or [],
                "competition_sources": [],
                "kernel_sources": [],
            }

            meta_path = staging_dir / "kernel-metadata.json"
            with open(meta_path, "w", encoding="utf-8") as f:
                json.dump(metadata, f, indent=2)

            # 4. Push lên Kaggle
            logger.info(f"Đang đẩy kernel lên Kaggle: {self.username}/{kernel_slug}...")
            self.api.kernels_push(str(staging_dir))

            return f"{self.username}/{kernel_slug}"
        finally:
            # Dọn dẹp thư mục tạm an toàn trong mọi trường hợp (kể cả khi gặp exception)
            shutil.rmtree(staging_dir, ignore_errors=True)

    def get_kernel_log(self, kernel_id: str) -> str:
        """Lấy log thực thi của Kernel để truy vết lỗi (Traceback)."""
        try:
            # api.kernel_log trả về một string chứa toàn bộ console log
            # (Ở một số phiên bản Kaggle API cũ, bạn có thể dùng self.api.kernel_status(kernel_id).get('failureMessage'))
            log = self.api.kernel_log(kernel_id)
            return log if log else "No log available."
        except AttributeError:
            # Fallback an toàn nếu thư viện Kaggle API hiện tại không bộc lộ hàm kernel_log
            status_info = self.api.kernel_status(kernel_id)
            return status_info.get("failureMessage", "Không thể lấy log lỗi chi tiết từ Kaggle.")
        except Exception as e:
            logger.error(f"Lỗi khi kéo log từ Kaggle: {e}")
            return str(e)

    def get_kernel_status(self, kernel_id: str) -> str:
        """Kiểm tra trạng thái Notebook: 'queued', 'running', 'complete', 'error'"""
        status = self.api.kernel_status(kernel_id)
        return status.get("status", "unknown")

    def pull_kernel_output(
        self, kernel_id: str, download_path: str = "data/downloads"
    ) -> str:
        """
        Tải toàn bộ file đầu ra (metrics, model) về khi Kaggle chạy xong.
        Tác tử Kiểm định sẽ nghiệm thu dữ liệu từ hàm này.
        """
        dl_dir = Path(download_path)
        dl_dir.mkdir(parents=True, exist_ok=True)

        # API sẽ tải về một file .zip chứa toàn bộ nội dung của /kaggle/working/
        logger.info(f"Đang tải output của kernel: {kernel_id} về {dl_dir}...")
        self.api.kernels_output(kernel_id, path=str(dl_dir))

        # Tên file zip thường được định dạng theo tên kernel
        kernel_slug = kernel_id.split("/")[-1]
        zip_path = dl_dir / f"{kernel_slug}.zip"

        return str(zip_path)


# Dependency Injection function cho FastAPI (được cache lại để tránh khởi tạo nhiều lần)
@lru_cache()
def get_kaggle_service() -> KaggleService:
    return KaggleService()
