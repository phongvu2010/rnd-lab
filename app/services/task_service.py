import json
import logging
import redis

from functools import lru_cache
from typing import Dict, List, Optional

from ..core.config import settings

logger = logging.getLogger(__name__)


class TaskService:
    """
    Dịch vụ quản lý trạng thái Tác vụ (Task State Manager).
    Lưu trữ trạng thái bền vững trên Redis. Sử dụng In-Memory Store tạm thời khi Redis chưa sẵn sàng.
    """

    KEY_PREFIX = "rnd_lab:task:"

    def __init__(self):
        self._memory_store: Dict[str, dict] = {}
        self._redis_client: Optional[redis.Redis] = None
        # Thực hiện kết nối thử nghiệm khi khởi tạo
        _ = self.redis_client

    @property
    def redis_client(self) -> Optional[redis.Redis]:
        """
        Lấy đối tượng Redis client với khả năng tự động kết nối / kết nối lại.
        Nếu chưa kết nối hoặc kết nối cũ bị gián đoạn, tự động khởi tạo kết nối mới.
        """
        if self._redis_client is not None:
            try:
                self._redis_client.ping()
                return self._redis_client
            except Exception as e:
                logger.warning(
                    f"[TaskService] Kết nối Redis cũ bị gián đoạn ({e}). Đang thử kết nối lại..."
                )
                self._redis_client = None

        try:
            client = redis.Redis.from_url(
                settings.REDIS_URL,
                decode_responses=True,
                socket_connect_timeout=2,
            )
            client.ping()
            self._redis_client = client
            logger.info(
                f"[TaskService] Kết nối thành công tới Redis: {settings.REDIS_URL}"
            )
            return self._redis_client
        except Exception as e:
            logger.warning(
                f"[TaskService] Không thể kết nối Redis ({e}). Tạm thời sử dụng In-Memory Task Store."
            )
            self._redis_client = None
            return None

    def save_task(self, task_id: str, task_data: dict, ttl_days: int = 30) -> None:
        """Lưu hoặc cập nhật trạng thái tác vụ."""
        # Cập nhật memory store
        self._memory_store[task_id] = task_data

        client = self.redis_client
        if client:
            try:
                key = f"{self.KEY_PREFIX}{task_id}"
                json_str = json.dumps(task_data, ensure_ascii=False)
                # TTL mặc định 30 ngày (tính theo giây)
                client.set(key, json_str, ex=ttl_days * 86400)
            except Exception as e:
                logger.error(
                    f"[TaskService] Lỗi khi ghi trạng thái task [{task_id}] vào Redis: {e}"
                )
                self._redis_client = None

    def get_task(self, task_id: str) -> Optional[dict]:
        """
        Lấy thông tin chi tiết tác vụ theo task_id.
        """
        client = self.redis_client
        if client:
            try:
                key = f"{self.KEY_PREFIX}{task_id}"
                data_str = client.get(key)
                if data_str:
                    return json.loads(data_str)
            except Exception as e:
                logger.error(
                    f"[TaskService] Lỗi khi đọc task [{task_id}] từ Redis: {e}"
                )
                self._redis_client = None

        return self._memory_store.get(task_id)

    def list_tasks(self) -> List[dict]:
        """
        Lấy danh sách tất cả các tác vụ gần đây.
        """
        tasks: List[dict] = []
        client = self.redis_client
        if client:
            try:
                pattern = f"{self.KEY_PREFIX}*"
                keys = client.keys(pattern)
                if keys:
                    # Lấy danh sách nhiều key một lúc
                    raw_items = client.mget(keys)
                    for item in raw_items:
                        if item:
                            tasks.append(json.loads(item))
                    # Sắp xếp theo ngày cập nhật giảm dần (mới nhất lên đầu)
                    tasks.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
                    return tasks
            except Exception as e:
                logger.error(f"[TaskService] Lỗi khi lấy danh sách tasks từ Redis: {e}")
                self._redis_client = None

        # Fallback về memory store
        fallback_list = list(self._memory_store.values())
        fallback_list.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
        return fallback_list


@lru_cache()
def get_task_service() -> TaskService:
    return TaskService()
