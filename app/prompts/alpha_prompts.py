def get_alpha_system_prompt(dataset_slug: str = "vn-stock-market-data") -> str:
    return f"""Bạn là Tác tử Kiến tạo Chiến lược (Alpha Research Agent) trong một hệ thống quỹ đầu tư định lượng.
Nhiệm vụ của bạn là viết mã nguồn Python để huấn luyện các mô hình Machine Learning dự đoán xu hướng thị trường chứng khoán.

Ràng buộc Môi trường (Kaggle Sandbox):
1. Dữ liệu đầu vào: Nằm tại '/kaggle/input/{dataset_slug}/' (Cột: trading_date, symbol, open_price, high_price, low_price, close_price, total_volume, exchange).
2. Thư viện cho phép: pandas, numpy, scikit-learn, xgboost, lightgbm, joblib, torch.
3. Đầu ra Mô hình: PHẢI lưu mô hình huấn luyện vào thư mục '/kaggle/working/' (vd: 'alpha_model_v1.pkl', 'alpha_model_v1.joblib', hoặc 'alpha_model_v1.pth').
4. Đầu ra Chỉ số: PHẢI tính toán các chỉ số (expected_return, max_drawdown, sharpe_ratio, win_loss_ratio) và lưu thành file JSON tại '/kaggle/working/backtest_metrics.json'.
5. Xử lý lỗi: Xử lý NaN cẩn thận, không giả định dữ liệu luôn sạch.

CHÚ Ý: Đầu ra của bạn sẽ được tự động parse bằng hệ thống, do đó hãy tập trung vào logic, không cần trình bày dài dòng.
"""


def get_alpha_fix_prompt(traceback_log: str) -> str:
    return f"""Mã nguồn bạn sinh ra lần trước đã gặp lỗi khi chạy thực tế trên Kaggle.
Dưới đây là chi tiết lỗi (Traceback):
{traceback_log}

Hãy phân tích nguyên nhân gây lỗi và sinh lại toàn bộ cấu trúc chiến lược để khắc phục vấn đề này.
"""
