import logging
import nbformat as nbf
# import papermill as pm

from pathlib import Path

logger = logging.getLogger(__name__)


class NotebookBuilderService:
    def __init__(self):
        """Service hỗ trợ tạo và tiêm tham số vào các tệp Jupyter Notebook (.ipynb)"""
        pass

    def build_from_scratch(
        self, kernel_id: str, llm_code_blocks: dict, output_dir: str = "data/staging"
    ) -> str:
        """
        Xây dựng một file .ipynb hoàn toàn mới từ các khối code do LLM sinh ra.

        Args:
            kernel_id: Mã ID duy nhất cho đợt chạy (dùng làm tên file).
            llm_code_blocks: Dictionary chứa các cell code từ LLM (theo schema LLMGeneratedStrategy).
            output_dir: Thư mục chứa file tạm trước khi đẩy lên Kaggle.

        Returns:
            Đường dẫn tới file .ipynb vừa được tạo.
        """
        out_dir = Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        nb = nbf.v4.new_notebook()

        # 1. Trích xuất lý luận của LLM thành Markdown Cell
        rationale = llm_code_blocks.get("rationale", "Chiến lược không có mô tả.")

        # Lắp ráp các cells theo đúng thứ tự logic
        nb["cells"] = [
            nbf.v4.new_markdown_cell(f"# Logic Chiến lược\n{rationale}"),
            nbf.v4.new_code_cell(llm_code_blocks.get("cell_imports", "")),
            nbf.v4.new_code_cell(llm_code_blocks.get("cell_data_prep", "")),
            nbf.v4.new_code_cell(llm_code_blocks.get("cell_model", "")),
            nbf.v4.new_code_cell(llm_code_blocks.get("cell_export", "")),
        ]

        # Xuất ra file
        output_filename = f"generated_ml_{kernel_id}.ipynb"
        output_path = out_dir / output_filename

        logger.info(f"Đang ghi file notebook ML: {output_path}")
        with open(output_path, "w", encoding="utf-8") as f:
            nbf.write(nb, f)

        return str(output_path)

    # def inject_parameters(
    #     self,
    #     template_path: str,
    #     params: dict,
    #     kernel_id: str,
    #     output_dir: str = "data/staging",
    # ) -> str:
    #     """
    #     Tiêm tham số mới vào một file Notebook mẫu (template) có sẵn.
    #     Dành cho các chiến lược dạng Rule-Based (Heuristics).

    #     Args:
    #         template_path: Đường dẫn tới file mẫu (vd: app/templates/rsi_macd.ipynb).
    #         params: Dictionary chứa các tham số (vd: {"rsi_period": 14}).
    #         kernel_id: Mã ID duy nhất.
    #         output_dir: Thư mục chứa file tạm.

    #     Returns:
    #         Đường dẫn tới file .ipynb đã được tiêm tham số.
    #     """
    #     out_dir = Path(output_dir)
    #     out_dir.mkdir(parents=True, exist_ok=True)

    #     output_filename = f"generated_heuristic_{kernel_id}.ipynb"
    #     output_path = out_dir / output_filename

    #     logger.info(
    #         f"Đang tiêm tham số vào notebook template '{template_path}' ➔ '{output_path}'"
    #     )
    #     # Sử dụng papermill để sinh file mới với tham số được bơm vào ô được tag "parameters"
    #     # prepare_only=True nghĩa là chỉ tạo file chứ KHÔNG chạy code tại máy chủ này
    #     pm.execute_notebook(
    #         str(template_path),
    #         str(output_path),
    #         parameters=params,
    #         prepare_only=True,
    #     )

    #     return str(output_path)


# Dependency Injection function cho FastAPI
def get_notebook_builder() -> NotebookBuilderService:
    return NotebookBuilderService()
