from datetime import datetime, timezone
from enum import Enum
from pydantic import BaseModel
from sqlalchemy import Column, DateTime
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, Relationship, SQLModel
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4


# -------------------------------------------------------------------
# 1. Định nghĩa trạng thái của Chiến lược
# -------------------------------------------------------------------
class StrategyStatus(str, Enum):
    DRAFT = "DRAFT"
    TESTING = "TESTING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    ARCHIVED = "ARCHIVED"


# -------------------------------------------------------------------
# 2. Định nghĩa các Schemas cho Strategy
# -------------------------------------------------------------------
class StrategyBase(SQLModel):
    name: str = Field(
        index=True,
        unique=True,
        description="Tên định danh chiến lược, vd: random_forest_v1",
    )
    description: Optional[str] = Field(
        default=None, description="Mô tả logic hoặc giả thuyết của chiến lược"
    )
    current_status: StrategyStatus = Field(default=StrategyStatus.DRAFT)


# Thực thể Database thực sự
class Strategy(StrategyBase, table=True):
    __tablename__ = "strategies"

    id: UUID = Field(default_factory=uuid4, primary_key=True, index=True)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True)),
    )

    # Thiết lập Relationship: Một Chiến lược có thể được backtest nhiều lần
    backtest_runs: List["BacktestRun"] = Relationship(
        back_populates="strategy",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )


# Schema dùng khi nhận request tạo mới
class StrategyCreate(StrategyBase):
    pass


# Schema dùng khi nhận request cập nhật (cho phép cập nhật một phần)
class StrategyUpdate(SQLModel):
    name: Optional[str] = None
    description: Optional[str] = None
    current_status: Optional[StrategyStatus] = None


# Schema dùng để trả về dữ liệu (Response)
class StrategyRead(StrategyBase):
    id: UUID
    created_at: datetime


# -------------------------------------------------------------------
# 3. Định nghĩa các Schemas cho BacktestRun
# -------------------------------------------------------------------
class BacktestRunBase(SQLModel):
    # Khóa ngoại liên kết chặt chẽ với bảng strategies
    strategy_id: UUID = Field(foreign_key="strategies.id", index=True)

    kaggle_kernel_id: str = Field(
        index=True, description="ID của Notebook trên Kaggle để gọi API đối soát"
    )
    dataset_version: str = Field(
        description="Phiên bản dữ liệu (vd: 2026-07-v1) đã dùng để train"
    )

    # Ép kiểu JSONB của PostgreSQL để chứa cấu trúc linh hoạt
    hyperparameters: Dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSONB),
        description="Tham số truyền vào mô hình",
    )
    metrics: Dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSONB),
        description="Kết quả: Lợi nhuận, Sharpe, Max Drawdown...",
    )

    model_artifact_path: Optional[str] = Field(
        default=None,
        description="Đường dẫn file .pkl đã lưu thực tế trong thư mục /registry",
    )
    is_successful: bool = Field(
        default=False, description="True nếu Kaggle chạy xong không bị lỗi code"
    )


# Thực thể Database thực sự
class BacktestRun(BacktestRunBase, table=True):
    __tablename__ = "backtest_runs"

    id: UUID = Field(default_factory=uuid4, primary_key=True, index=True)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True)),
    )

    # Thiết lập Relationship quay ngược trở lại Strategy
    strategy: Strategy = Relationship(back_populates="backtest_runs")


# Schema dùng khi nhận request tạo mới
class BacktestRunCreate(BacktestRunBase):
    pass


# Schema dùng khi nhận request cập nhật (cho phép cập nhật một phần)
class BacktestRunUpdate(SQLModel):
    strategy_id: Optional[UUID] = None
    kaggle_kernel_id: Optional[str] = None
    dataset_version: Optional[str] = None
    hyperparameters: Optional[Dict[str, Any]] = None
    metrics: Optional[Dict[str, Any]] = None
    model_artifact_path: Optional[str] = None
    is_successful: Optional[bool] = None


# Schema dùng để trả về dữ liệu (Response)
class BacktestRunRead(BacktestRunBase):
    id: UUID
    created_at: datetime


# -------------------------------------------------------------------
# 4. Các Schemas phức hợp (Relationship Schemas)
# -------------------------------------------------------------------
class StrategyReadWithBacktestRuns(StrategyRead):
    backtest_runs: List[BacktestRunRead] = []


class BacktestRunWithStrategy(BacktestRunRead):
    strategy: Optional[StrategyRead] = None


class MLStrategyRequest(BaseModel):
    user_prompt: str


class LLMGeneratedStrategy(BaseModel):
    """Schema ép kiểu đầu ra cho Tác tử Kiến tạo (LLM) khi sinh code ML."""

    rationale: str = Field(
        ..., description="Giải thích ngắn gọn logic và giả thuyết của chiến lược này."
    )
    cell_imports: str = Field(
        ...,
        description="Mã nguồn import các thư viện Python (pandas, scikit-learn...).",
    )
    cell_data_prep: str = Field(
        ..., description="Mã nguồn load file /kaggle/input/..., xử lý NaN, sinh X, y."
    )
    cell_model: str = Field(
        ..., description="Mã nguồn khởi tạo và huấn luyện mô hình Machine Learning."
    )
    cell_export: str = Field(
        ...,
        description="Mã nguồn lưu mô hình ra /kaggle/working/...pkl và tính toán backtest_metrics.json.",
    )
