import instructor

from functools import lru_cache
from openai import AsyncOpenAI

from app.core.config import settings
from app.prompts.alpha_prompts import get_alpha_system_prompt, get_alpha_fix_prompt
from app.schemas import LLMGeneratedStrategy


class LLMService:
    def __init__(self):
        """
        Khởi tạo Client kết nối LLM, bọc qua 'instructor' để hỗ trợ ép kiểu Pydantic.
        Sử dụng AsyncOpenAI để không chặn luồng (non-blocking) của FastAPI.
        """
        api_key = settings.OPENAI_API_KEY
        if not api_key:
            raise ValueError("OPENAI_API_KEY chưa được cấu hình trong biến môi trường.")

        # Patch AsyncOpenAI client bằng instructor
        self.client = instructor.from_openai(AsyncOpenAI(api_key=api_key))

        # Sử dụng model từ file cấu hình hệ thống
        self.default_model = settings.OPENAI_MODEL

    async def generate_ml_strategy(self, user_request: str) -> LLMGeneratedStrategy:
        """
        Gọi LLM để tự động thiết kế một chiến lược Machine Learning dựa trên yêu cầu.

        Args:
            user_request: Mô tả ý tưởng (vd: "Tạo mô hình Random Forest dự đoán T+3...")

        Returns:
            LLMGeneratedStrategy: Đối tượng Pydantic chứa các khối code hoàn chỉnh.
        """
        print(f"Đang phân tích và sinh mã nguồn AI cho: {user_request}")

        strategy_response = await self.client.chat.completions.create(
            model=self.default_model,
            response_model=LLMGeneratedStrategy,
            temperature=0.7,  # Cho phép mô hình sáng tạo vừa phải
            messages=[
                {"role": "system", "content": get_alpha_system_prompt()},
                {"role": "user", "content": user_request},
            ],
            max_tokens=6000,
        )

        return strategy_response

    async def fix_strategy_error(self, original_request: str, traceback_log: str) -> LLMGeneratedStrategy:
        """
        Cơ chế tự phục hồi (Self-healing): Cung cấp log lỗi để LLM tự sửa code.
        """
        print("Phát hiện lỗi từ Kaggle. Đang yêu cầu Tác tử tự khắc phục...")

        fixed_response = await self.client.chat.completions.create(
            model=self.default_model,
            response_model=LLMGeneratedStrategy,
            temperature=0.3,  # Giảm nhiệt độ để LLM tập trung vào fix bug, bớt sáng tạo
            messages=[
                {"role": "system", "content": get_alpha_system_prompt()},
                {"role": "user", "content": original_request},
                {"role": "user", "content": get_alpha_fix_prompt(traceback_log)},
            ],
            max_tokens=6000,
        )

        return fixed_response


# Dependency Injection function cho FastAPI (được cache lại để tránh khởi tạo nhiều lần)
@lru_cache()
def get_llm_service() -> LLMService:
    return LLMService()
