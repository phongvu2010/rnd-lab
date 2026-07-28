# Mô tả chi tiết từng bước trong vòng đời hoạt động của hệ thống mã nguồn


### Giai đoạn 1: Chuẩn bị Nguyên liệu (Data Synchronization)

Mọi chiến lược đều cần dữ liệu sạch. Quy trình bắt đầu với Tác tử Dữ liệu (Data Agent):

1. Thông qua `BigQueryService`, hệ thống truy vấn và kéo dữ liệu lịch sử giá (bảng `raw_price` và `adj_price`) từ kho dữ liệu Google Cloud BigQuery về máy chủ nội bộ.

2. Dữ liệu này được lưu trữ tạm thời dưới định dạng `.parquet` (tối ưu cho đọc/ghi tốc độ cao).

3. Thông qua `KaggleService`, toàn bộ tập dữ liệu này được tự động nén và đẩy lên Kaggle dưới dạng một Private Dataset (ví dụ: `vn-stock-market-data`). Môi trường Lab trên mây lúc này đã có sẵn nguyên liệu mới nhất.

### Giai đoạn 2: Kiến tạo Chiến lược (Strategy Generation)

Đây là lúc **Tác tử Kiến tạo (Alpha Agent)** vào việc. Có hai luồng chạy song song tùy thuộc vào loại chiến lược:

* **Luồng tĩnh (Rule-Based / Heuristics):** API nhận một bộ tham số tĩnh (ví dụ: chu kỳ RSI = 14). `AlphaAgent` sẽ gọi `NotebookBuilderService` để dùng thư viện `papermill` "tiêm" trực tiếp các tham số này vào một file mẫu `.ipynb` có sẵn.

* **Luồng động (Machine Learning):** API nhận một mô tả bằng ngôn ngữ tự nhiên. `AlphaAgent` gọi `LLMService`. Bằng việc sử dụng bộ thư viện `instructor` và `openai`, hệ thống ép mô hình LLM (GPT/Gemini) phải viết ra các đoạn mã Python chuẩn xác và trả về dưới dạng một JSON có cấu trúc (`LLMGeneratedStrategy`). Sau đó, `NotebookBuilderService` dùng `nbformat` để lắp ráp các đoạn mã này thành một file `.ipynb` hoàn toàn mới.

### Giai đoạn 3: Đẩy vào "Lò luyện" (Sandbox Execution)

Sau khi tệp `.ipynb` (Notebook) được sinh ra, hệ thống không chạy mã nguồn này trực tiếp trên máy chủ nội bộ để tránh quá tải và rủi ro bảo mật.

1. `AlphaAgent` gọi `KaggleService` để đóng gói file Notebook này cùng với file cấu hình `kernel-metadata.json`.

2. Hệ thống đẩy (push) tệp này lên Kaggle, đồng thời khai báo liên kết với bộ dữ liệu `vn-stock-market-data` đã chuẩn bị ở Giai đoạn 1.

3. Kaggle tiếp nhận và bắt đầu xếp hàng chạy (huấn luyện và backtest) hoàn toàn trên môi trường máy chủ ảo của họ. Tác vụ trên máy chủ nội bộ lúc này kết thúc (giải phóng RAM/CPU).

### Giai đoạn 4: Thu hoạch và Kiểm định (Harvesting & Validation)

Trong lúc Kaggle đang chạy, **Tác tử Kiểm định (Backtesting Agent)** (chạy ngầm thông qua Background Tasks của FastAPI) sẽ liên tục thăm dò (polling) trạng thái thông qua API `get_kernel_status`.

1. Khi Kaggle báo trạng thái `complete`, hệ thống lập tức gọi `pull_kernel_output` để kéo một tệp `.zip` kết quả về.

2. Tệp `.zip` này được giải nén. Bên trong chứa mô hình đã huấn luyện (tệp `.pkl`) và file báo cáo hiệu suất (tệp `backtest_metrics.json`).

3. Hệ thống đọc file `backtest_metrics.json` (chứa Lợi nhuận, Sharpe Ratio, Max Drawdown) và ghi một bản ghi mới vào bảng `backtest_runs` trên cơ sở dữ liệu TimescaleDB.

4. **Đánh giá tự động:** Nếu các chỉ số vượt qua ngưỡng an toàn rủi ro tĩnh đã cấu hình, hệ thống sẽ gán trạng thái `APPROVED` cho chiến lược đó, đồng thời di chuyển tệp `.pkl` vào thư mục lưu trữ vĩnh viễn (`/registry/models`). Nếu thất bại, trạng thái sẽ là `REJECTED`.

### Giai đoạn 5: Cơ chế Tự sửa lỗi (Self-Healing Loop) - Tùy chọn

Nếu ở Giai đoạn 4, hệ thống phát hiện Kaggle trả về trạng thái `error` (do LLM viết code bị lỗi cú pháp hoặc tràn RAM), Tác tử Kiểm định sẽ đọc file log lỗi (traceback). Nó gửi toàn bộ log lỗi này ngược lại cho `LLMService` qua hàm `fix_strategy_error`. Tác tử Kiến tạo sẽ tự động phân tích lỗi, viết lại code mới và vòng lặp quy trình quay trở lại Giai đoạn 2.

### Giai đoạn 6: Sẵn sàng Bàn giao (Handover to Live Operations)

Khối 2 lúc này chỉ đóng vai trò "nằm im" và cung cấp REST API. Khi máy chủ của Khối 3 (Live Operations) khởi động mỗi ngày, **Tác tử Trưởng (Master Portfolio Agent)** của Khối 3 sẽ gọi API sang Khối 2: *"Hãy đưa cho tôi đường dẫn tệp `.pkl` của chiến lược A đang ở trạng thái APPROVED và có Sharpe Ratio cao nhất"*.

Khối 3 tải tệp `.pkl` đó về bộ nhớ RAM của nó, kết nối với dữ liệu Real-time và bắt đầu ra quyết định sinh lời thực tế.
