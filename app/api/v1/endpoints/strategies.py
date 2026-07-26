import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlmodel import select, Session
from typing import List, Optional
from uuid import UUID

from app.core.database import get_session
from app.schemas import (
    Strategy,
    StrategyCreate,
    StrategyRead,
    StrategyReadWithBacktestRuns,
    StrategyStatus,
    StrategyUpdate,
)

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/", response_model=List[StrategyRead])
def read_strategies(
    *,
    session: Session = Depends(get_session),
    skip: int = Query(default=0, ge=0, description="Bỏ qua N bản ghi đầu"),
    limit: int = Query(default=100, ge=1, le=100, description="Lấy tối đa N bản ghi"),
    status: Optional[StrategyStatus] = Query(
        default=None, description="Lọc theo trạng thái chiến lược"
    ),
) -> List[Strategy]:
    """Lấy danh sách các chiến lược đầu tư, hỗ trợ lọc và phân trang."""
    statement = select(Strategy)
    if status:
        statement = statement.where(Strategy.current_status == status)

    statement = statement.offset(skip).limit(limit)
    strategies = session.exec(statement).all()
    return list(strategies)


@router.get("/{id}", response_model=StrategyReadWithBacktestRuns)
def read_strategy(*, session: Session = Depends(get_session), id: UUID) -> Strategy:
    """Lấy thông tin chi tiết của một chiến lược kèm theo lịch sử các lượt chạy Backtest."""
    db_strategy = session.get(Strategy, id)
    if not db_strategy:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Không tìm thấy chiến lược với ID: {id}",
        )
    return db_strategy


@router.post("/", response_model=StrategyRead, status_code=status.HTTP_201_CREATED)
def create_strategy(
    *, session: Session = Depends(get_session), strategy_in: StrategyCreate
) -> Strategy:
    """Tạo mới một chiến lược đầu tư.

    - **name**: Tên định danh duy nhất cho chiến lược.
    - **description**: Mô tả giả thuyết giao dịch.
    - **current_status**: Trạng thái (DRAFT, TESTING, APPROVED, REJECTED, ARCHIVED). Mặc định là DRAFT.
    """
    db_strategy = Strategy.model_validate(strategy_in)
    session.add(db_strategy)
    try:
        session.commit()
        session.refresh(db_strategy)
    except IntegrityError:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Chiến lược với tên '{strategy_in.name}' đã tồn tại trong hệ thống.",
        )

    return db_strategy


@router.patch("/{id}", response_model=StrategyRead)
def update_strategy(
    *,
    session: Session = Depends(get_session),
    id: UUID,
    strategy_in: StrategyUpdate,
) -> Strategy:
    """Cập nhật thông tin của một chiến lược."""
    db_strategy = session.get(Strategy, id)
    if not db_strategy:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Không tìm thấy chiến lược với ID: {id}",
        )

    # Cập nhật các trường dữ liệu được gửi lên
    strategy_data = strategy_in.model_dump(exclude_unset=True)
    for key, value in strategy_data.items():
        setattr(db_strategy, key, value)

    session.add(db_strategy)
    try:
        session.commit()
        session.refresh(db_strategy)
    except IntegrityError:
        session.rollback()
        err_detail = (
            f"Chiến lược với tên '{strategy_in.name}' đã tồn tại trong hệ thống."
            if strategy_in.name
            else "Cập nhật dữ liệu thất bại do vi phạm ràng buộc dữ liệu duy nhất (Integrity Error)."
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=err_detail,
        )

    return db_strategy


@router.delete("/{id}")
def delete_strategy(*, session: Session = Depends(get_session), id: UUID) -> dict:
    """Xóa một chiến lược đầu tư.

    Hành động xóa này sẽ tự động xóa tất cả các lượt chạy Backtest liên quan (Cascade Delete).
    """
    db_strategy = session.get(Strategy, id)
    if not db_strategy:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Không tìm thấy chiến lược với ID: {id}",
        )
    session.delete(db_strategy)
    session.commit()
    return {"message": f"Đã xóa thành công chiến lược với ID: {id}"}
