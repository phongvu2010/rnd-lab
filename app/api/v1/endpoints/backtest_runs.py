from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import select, Session
from typing import List, Optional
from uuid import UUID

from app.core.database import get_session
from app.schemas import (
    BacktestRun,
    BacktestRunCreate,
    BacktestRunRead,
    BacktestRunUpdate,
    BacktestRunWithStrategy,
    Strategy,
)

router = APIRouter()


@router.get("/", response_model=List[BacktestRunRead])
def read_backtest_runs(
    *,
    session: Session = Depends(get_session),
    skip: int = Query(default=0, ge=0, description="Bỏ qua N bản ghi đầu"),
    limit: int = Query(default=100, ge=1, le=100, description="Lấy tối đa N bản ghi"),
    is_successful: Optional[bool] = Query(
        default=None, description="Lọc theo kết quả thành công/thất bại"
    ),
) -> List[BacktestRun]:
    """Lấy danh sách các lượt chạy kiểm định, hỗ trợ lọc và phân trang."""
    statement = select(BacktestRun)
    if is_successful is not None:
        statement = statement.where(BacktestRun.is_successful == is_successful)

    statement = statement.offset(skip).limit(limit)
    runs = session.exec(statement).all()
    return list(runs)


@router.get("/{id}", response_model=BacktestRunWithStrategy)
def read_backtest_run(
    *, session: Session = Depends(get_session), id: UUID
) -> BacktestRun:
    """Lấy chi tiết một lượt kiểm định kèm thông tin chiến lược gốc."""
    db_backtest = session.get(BacktestRun, id)
    if not db_backtest:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Không tìm thấy lượt chạy kiểm định với ID: {id}",
        )
    return db_backtest


@router.post("/", response_model=BacktestRunRead, status_code=status.HTTP_201_CREATED)
def create_backtest_run(
    *, session: Session = Depends(get_session), backtest_run_in: BacktestRunCreate
) -> BacktestRun:
    """Tạo mới (ghi nhận) một lượt kiểm định chiến lược trên Kaggle.

    - **strategy_id**: ID của chiến lược liên quan.
    - **kaggle_kernel_id**: ID Notebook trên Kaggle.
    - **dataset_version**: Phiên bản dữ liệu sử dụng để train/test.
    - **hyperparameters**: Các tham số truyền vào mô hình (dạng JSON).
    - **metrics**: Kết quả đo đạc (Lợi nhuận, Sharpe, Max Drawdown, ...) (dạng JSON).
    - **model_artifact_path**: Đường dẫn file model (.pkl) đã lưu.
    - **is_successful**: Trạng thái chạy thành công của notebook.
    """
    # Kiểm tra sự tồn tại của chiến lược
    strategy = session.get(Strategy, backtest_run_in.strategy_id)
    if not strategy:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Không tìm thấy chiến lược với ID: {backtest_run_in.strategy_id}",
        )

    db_backtest = BacktestRun.model_validate(backtest_run_in)
    session.add(db_backtest)
    session.commit()
    session.refresh(db_backtest)
    return db_backtest


@router.patch("/{id}", response_model=BacktestRunRead)
def update_backtest_run(
    *,
    session: Session = Depends(get_session),
    id: UUID,
    backtest_run_in: BacktestRunUpdate,
) -> BacktestRun:
    """Cập nhật thông tin/kết quả của một lượt kiểm định."""
    db_backtest = session.get(BacktestRun, id)
    if not db_backtest:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Không tìm thấy lượt chạy kiểm định với ID: {id}",
        )

    # Nếu cập nhật strategy_id, cần kiểm tra strategy đó có tồn tại không
    if (
        backtest_run_in.strategy_id is not None
        and backtest_run_in.strategy_id != db_backtest.strategy_id
    ):
        strategy = session.get(Strategy, backtest_run_in.strategy_id)
        if not strategy:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Không tìm thấy chiến lược mới với ID: {backtest_run_in.strategy_id}",
            )

    # Cập nhật các trường dữ liệu được gửi lên
    backtest_data = backtest_run_in.model_dump(exclude_unset=True)
    for key, value in backtest_data.items():
        setattr(db_backtest, key, value)

    session.add(db_backtest)
    session.commit()
    session.refresh(db_backtest)
    return db_backtest


@router.delete("/{id}")
def delete_backtest_run(*, session: Session = Depends(get_session), id: UUID) -> dict:
    """Xóa lịch sử một lượt kiểm định."""
    db_backtest = session.get(BacktestRun, id)
    if not db_backtest:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Không tìm thấy lượt chạy kiểm định với ID: {id}",
        )
    session.delete(db_backtest)
    session.commit()
    return {"message": f"Đã xóa thành công lượt chạy kiểm định với ID: {id}"}
