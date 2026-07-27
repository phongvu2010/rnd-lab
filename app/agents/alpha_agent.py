import asyncio
import logging

from fastapi import Depends
# from pathlib import Path
from uuid import uuid4

from app.core.config import settings
from app.schemas import LLMGeneratedStrategy
from app.services.kaggle_service import KaggleService, get_kaggle_service
from app.services.llm_service import LLMService, get_llm_service
from app.services.notebook_builder import NotebookBuilderService, get_notebook_builder

logger = logging.getLogger(__name__)


class AlphaAgent:
    def __init__(
        self,
        llm: LLMService,
        builder: NotebookBuilderService,
        kaggle: KaggleService,
    ):
        """
        Tác tử Kiến tạo (Alpha Research Agent) được tiêm (inject) các dịch vụ nền tảng.
        """
        self.llm = llm
        self.builder = builder
        self.kaggle = kaggle

        username = settings.KAGGLE_USERNAME or ""
        if not username:
            logger.warning(
                "[AlphaAgent] KAGGLE_USERNAME chưa được cấu hình. Các tác vụ đẩy Kernel có thể báo lỗi."
            )
        # Đường dẫn dataset trên Kaggle mà Tác tử Dữ liệu đã đẩy lên
        # Ví dụ: "phongvu2010/vn-stock-market-data"
        self.dataset_sources = [f"{username}/vn-stock-market-data"] if username else []

    async def run_ml_dynamic_strategy(self, request_prompt: str) -> dict:
        """
        Thực thi chiến lược Tự học (Machine Learning) bằng cách yêu cầu LLM viết code.
        """
        kernel_id = f"ml-dynamic-{uuid4().hex[:8]}"

        logger.info(f"[Alpha Agent] Bắt đầu suy nghĩ về chiến lược: {request_prompt}")

        # 1. LLM sinh code động (Ép kiểu nghiêm ngặt theo Schema)
        strategy_schema: LLMGeneratedStrategy = await self.llm.generate_ml_strategy(request_prompt)

        logger.info(f"[Alpha Agent] LLM đã đề xuất xong: {strategy_schema.rationale[:50]}...")

        # 2. Lắp ráp các khối code thành file .ipynb hoàn chỉnh
        notebook_path = self.builder.build_from_scratch(
            kernel_id=kernel_id,
            llm_code_blocks=strategy_schema.model_dump(),
        )

        # 3. Đẩy lên Kaggle để huấn luyện bằng Worker Thread
        kernel_slug = await asyncio.to_thread(
            self.kaggle.push_kernel,
            notebook_path=notebook_path,
            kernel_slug=kernel_id,
            title=f"Auto ML: {strategy_schema.rationale[:30]}...",
            dataset_sources=self.dataset_sources,
        )

        logger.info(f"[Alpha Agent] Đã đưa mô hình vào lò luyện. Kaggle Kernel: {kernel_slug}")

        # Trả về kèm theo cả rationale (lý luận) để API có thể lưu vào Database
        return {
            "kernel_slug": kernel_slug,
            "rationale": strategy_schema.rationale,
        }

    # async def run_heuristic_strategy(self, strategy_name: str, template_name: str, params: dict) -> str:
    #     """
    #     Thực thi chiến lược mớm kịch bản tĩnh (Rule-Based).
    #     """
    #     kernel_id = f"heuristic-{uuid4().hex[:8]}"
    #     template_path = Path("app/templates") / template_name

    #     if not template_path.exists():
    #         raise FileNotFoundError(f"Không tìm thấy template: {template_path}")

    #     logger.info(f"[Alpha Agent] Đang tiêm tham số vào {template_name}...")

    #     # 1. Bơm tham số vào file Notebook
    #     notebook_path = self.builder.inject_parameters(
    #         template_path=template_path,
    #         params=params,
    #         kernel_id=kernel_id,
    #     )

    #     # 2. Đẩy lên môi trường Lab (Kaggle) bằng Worker Thread để không nghẽn Event Loop
    #     kernel_slug = await asyncio.to_thread(
    #         self.kaggle.push_kernel,
    #         notebook_path=notebook_path,
    #         kernel_slug=kernel_id,
    #         title=f"Rule-Based: {strategy_name}",
    #         dataset_sources=self.dataset_sources,
    #     )

    #     logger.info(f"[Alpha Agent] Đã kích hoạt thành công. Kaggle Kernel: {kernel_slug}")
    #     return kernel_slug

    async def heal_ml_strategy(self, original_prompt: str, traceback_log: str) -> dict:
        """
        Cơ chế Self-Healing: Khi Kaggle Kernel bị lỗi, tự động gọi LLM phân tích log lỗi để sửa code và push lại.
        """
        kernel_id = f"ml-healed-{uuid4().hex[:8]}"

        logger.info(f"[Alpha Agent - Self Healing] Bắt đầu sửa lỗi code cho prompt: {original_prompt}")

        # 1. Yêu cầu LLM sửa code dựa trên log lỗi
        fixed_schema: LLMGeneratedStrategy = await self.llm.fix_strategy_error(
            original_request=original_prompt,
            traceback_log=traceback_log,
        )

        logger.info(f"[Alpha Agent - Self Healing] Code đã được khắc phục: {fixed_schema.rationale[:50]}...")

        # 2. Xây dựng lại notebook .ipynb
        notebook_path = self.builder.build_from_scratch(
            kernel_id=kernel_id,
            llm_code_blocks=fixed_schema.model_dump(),
        )

        # 3. Đẩy lại kernel mới lên Kaggle
        kernel_slug = await asyncio.to_thread(
            self.kaggle.push_kernel,
            notebook_path=notebook_path,
            kernel_slug=kernel_id,
            title=f"Auto ML (Healed): {fixed_schema.rationale[:25]}...",
            dataset_sources=self.dataset_sources,
        )

        logger.info(f"[Alpha Agent - Self Healing] Đã đẩy lại kernel thành công: {kernel_slug}")

        return {
            "kernel_slug": kernel_slug,
            "rationale": fixed_schema.rationale,
            "is_healed": True,
        }


# Dependency Injection function cho FastAPI
def get_alpha_agent(
    llm: LLMService = Depends(get_llm_service),
    builder: NotebookBuilderService = Depends(get_notebook_builder),
    kaggle: KaggleService = Depends(get_kaggle_service)
) -> AlphaAgent:
    return AlphaAgent(llm=llm, builder=builder, kaggle=kaggle)
