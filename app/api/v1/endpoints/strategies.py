import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlmodel import select, Session
from typing import List, Optional
from uuid import UUID, uuid4

from app.agents.alpha_agent import AlphaAgent, get_alpha_agent
from app.core.database import get_session, engine
from app.schemas import (
    BacktestRun,
    MLStrategyRequest,
    Strategy,
    StrategyCreate,
    StrategyRead,
    StrategyReadWithBacktestRuns,
    StrategyStatus,
    StrategyUpdate,
)

logger = logging.getLogger(__name__)
router = APIRouter()


class SelfHealRequest(BaseModel):
    backtest_run_id: UUID
    traceback_log: str


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


@router.post("/trigger-ml-research", status_code=status.HTTP_202_ACCEPTED)
async def trigger_autonomous_ml_research(
    request: MLStrategyRequest,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
    agent: AlphaAgent = Depends(get_alpha_agent),
):
    """
    Kích hoạt Tác tử Kiến tạo tự động viết code ML ngầm (Background Task) và tự động ghi nhận vào CSDL.
    """
    # 1. Tạo trước bản ghi Strategy và BacktestRun ở trạng thái ban đầu để tránh mất dữ liệu khi lỗi
    strategy_name = f"auto_ml_{uuid4().hex[:8]}"
    db_strategy = Strategy(
        name=strategy_name,
        description=f"ML Strategy (Sinh code ngầm): {request.user_prompt[:80]}...",
        current_status=StrategyStatus.DRAFT,
    )
    session.add(db_strategy)
    session.commit()
    session.refresh(db_strategy)

    db_backtest_run = BacktestRun(
        strategy_id=db_strategy.id,
        kaggle_kernel_id="pending_generation",
        dataset_version="2026-07-v1",
        hyperparameters={"prompt": request.user_prompt},
        metrics={},
        is_successful=False,
    )
    session.add(db_backtest_run)
    session.commit()
    session.refresh(db_backtest_run)

    # Hàm chạy nền để không chặn HTTP Request của người dùng
    async def task_runner(
        strategy_id: UUID,
        backtest_run_id: UUID,
        prompt: str,
        agent_instance: AlphaAgent,
    ):
        try:
            # 2. Gọi Alpha Agent để sinh code và đẩy lên Kaggle
            result = await agent_instance.run_ml_dynamic_strategy(prompt)
            kernel_slug = result["kernel_slug"]
            rationale = result["rationale"]

            # 3. Cập nhật thông tin thực tế của Kernel lên DB
            with Session(engine) as db:
                db_strat = db.get(Strategy, strategy_id)
                db_run = db.get(BacktestRun, backtest_run_id)

                if db_strat and db_run:
                    db_strat.description = f"ML Strategy: {rationale}"
                    db_strat.current_status = StrategyStatus.TESTING
                    db_run.kaggle_kernel_id = kernel_slug

                    db.add(db_strat)
                    db.add(db_run)
                    db.commit()

                    logger.info(
                        f"Đã lưu thành công Strategy ID: {db_strat.id} và BacktestRun ID: {db_run.id} với Kaggle ID: {kernel_slug}"
                    )

                    # 4. Kích hoạt Polling Agent trực tiếp bằng cách await để theo dõi tiến độ chạy trên Kaggle
                    from app.agents.backtest_agent import get_backtest_agent
                    backtest_agent = get_backtest_agent()
                    await backtest_agent.poll_and_evaluate(db_run.id, kernel_slug)
        except Exception as e:
            logger.error(f"Lỗi trong quá trình suy nghĩ của Tác tử Alpha Agent: {e}")
            with Session(engine) as db:
                db_strat = db.get(Strategy, strategy_id)
                db_run = db.get(BacktestRun, backtest_run_id)
                if db_strat:
                    db_strat.current_status = StrategyStatus.REJECTED
                    db_strat.description = f"Lỗi sinh code chiến lược: {e}"
                    db.add(db_strat)

                if db_run:
                    db_run.kaggle_kernel_id = f"error_{uuid4().hex[:8]}"
                    db_run.metrics = {"error": str(e)}
                    db.add(db_run)

                db.commit()

    # Đẩy tác vụ cho FastAPI chạy ngầm
    background_tasks.add_task(task_runner, db_strategy.id, db_backtest_run.id, request.user_prompt, agent)

    return {
        "message": "Tác tử Kiến tạo đã tiếp nhận yêu cầu và đang suy nghĩ...",
        "strategy_id": db_strategy.id,
        "backtest_run_id": db_backtest_run.id,
        "prompt": request.user_prompt,
    }


@router.post("/heal-ml-research", status_code=status.HTTP_202_ACCEPTED)
async def trigger_self_healing_ml_research(
    request: SelfHealRequest,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
    agent: AlphaAgent = Depends(get_alpha_agent),
):
    """
    Kích hoạt cơ chế Self-Healing: Tác tử Alpha Agent tự sửa code ML khi Kaggle chạy thất bại.
    """
    # 1. Kiểm tra sự tồn tại của lượt chạy lỗi gốc
    backtest_run = session.get(BacktestRun, request.backtest_run_id)
    if not backtest_run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Không tìm thấy lượt backtest cũ với ID: {request.backtest_run_id}",
        )
    strategy = session.get(Strategy, backtest_run.strategy_id)
    prompt = backtest_run.hyperparameters.get(
        "prompt", strategy.description if strategy else "ML Strategy Fix"
    )

    # 2. Tạo trước bản ghi BacktestRun mới ở trạng thái chờ để lấy ID và tránh mất dữ liệu
    db_new_run = BacktestRun(
        strategy_id=backtest_run.strategy_id,
        kaggle_kernel_id="pending_healing",
        dataset_version=backtest_run.dataset_version,
        hyperparameters={"prompt": prompt, "healed_from_run_id": str(request.backtest_run_id)},
        metrics={},
        is_successful=False,
    )
    session.add(db_new_run)
    session.commit()
    session.refresh(db_new_run)

    async def heal_task_runner(
        new_run_id: UUID,
        traceback: str,
        prompt_str: str,
        agent_instance: AlphaAgent,
    ):
        try:
            # Gọi cơ chế Self-Healing của AlphaAgent
            result = await agent_instance.heal_ml_strategy(prompt_str, traceback)
            kernel_slug = result["kernel_slug"]

            with Session(engine) as db:
                db_run = db.get(BacktestRun, new_run_id)
                if db_run:
                    db_run.kaggle_kernel_id = kernel_slug
                    db.add(db_run)
                    db.commit()
                    db.refresh(db_run)

                    logger.info(f"Self-Healing hoàn tất. Lượt backtest mới: {db_run.id} với Kaggle ID: {kernel_slug}")
 
                    # Kích hoạt Polling Agent trực tiếp bằng cách await
                    from app.agents.backtest_agent import get_backtest_agent
                    backtest_agent = get_backtest_agent()
                    await backtest_agent.poll_and_evaluate(db_run.id, kernel_slug)
        except Exception as e:
            logger.error(f"Lỗi trong quá trình Self-Healing của Tác tử: {e}")
            with Session(engine) as db:
                db_run = db.get(BacktestRun, new_run_id)
                if db_run:
                    db_run.kaggle_kernel_id = f"failed_healing_{uuid4().hex[:8]}"
                    db_run.metrics = {"error": str(e)}
                    db.add(db_run)
                    db.commit()

    background_tasks.add_task(heal_task_runner, db_new_run.id, request.traceback_log, prompt, agent)

    return {
        "message": "Tác tử đã tiếp nhận log lỗi và đang tiến hành tự phục hồi code (Self-Healing)...",
        "backtest_run_id": db_new_run.id,
    }
