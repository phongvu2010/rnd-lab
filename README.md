# Vietnam Securities Investment Fund - Research Lab (Khối 2: R&D API)

Hệ thống **Research Lab Agents API** là nền tảng R&D thuộc quỹ đầu tư chứng khoán Việt Nam, có nhiệm vụ tự động hóa toàn bộ vòng đời nghiên cứu, kiến tạo, huấn luyện, kiểm định và quản lý các chiến lược giao dịch (Rule-Based & Machine Learning) thông qua dàn tác tử AI độc lập (Autonomous AI Agents) kết hợp với hạ tầng điện toán đám mây Kaggle Kernels và cơ sở dữ liệu TimescaleDB.

---

## 📋 Mục lục

1. [Tổng quan Kiến trúc & Các Tác tử](#-tổng-quan-kiến-trúc--các-tác-tử)
2. [Cấu trúc Thư mục](#-cấu-trúc-thư-mục)
3. [Yêu cầu Môi trường & Cấu hình (.env)](#-yêu-cầu-môi-trường--cấu-hình-env)
4. [Hướng dẫn Khởi chạy Hệ thống](#-hướng-dẫn-khởi-chạy-hệ-thống)
5. [Hướng dẫn Sử dụng theo Các Giai đoạn Hoạt động](#-hướng-dẫn-sử-dụng-theo-các-giai-đoạn-hoạt-động)
   - [Giai đoạn 1: Chuẩn bị Nguyên liệu & Đồng bộ Dữ liệu](#giai-đoạn-1-chuẩn-bị-nguyên-liệu--đồng-bộ-dữ-liệu-data-synchronization)
   - [Giai đoạn 2: Kiến tạo Chiến lược (Strategy Generation)](#giai-đoạn-2-kiến-tạo-chiến-lược-strategy-generation)
   - [Giai đoạn 3: Thực thi trên Môi trường Cách ly (Sandbox Execution)](#giai-đoạn-3-thực-thi-trên-môi-trường-cách-ly-sandbox-execution)
   - [Giai đoạn 4: Thu hoạch & Kiểm định Tự động (Harvesting & Validation)](#giai-đoạn-4-thu-hoạch--kiểm-định-tự-động-harvesting--validation)
   - [Giai đoạn 5: Cơ chế Tự sửa lỗi (Self-Healing Loop)](#giai-đoạn-5-cơ-chế-tự-sửa-lỗi-self-healing-loop)
   - [Giai đoạn 6: Sẵn sàng Bàn giao (Handover to Live Operations)](#giai-đoạn-6-sẵn-sàng-bàn-giao-handover-to-live-operations)
6. [Danh mục API Endpoints & cURL Ví dụ](#-danh-mục-api-endpoints--curl-ví-dụ)
7. [Cơ chế Phục hồi Trạng thái (State Recovery)](#-cơ-chế-phục-hồi-trạng-thái-state-recovery)

---

## 🏗 Tổng quan Kiến trúc & Các Tác tử

Hệ thống được thiết kế theo kiến trúc Microservices và Event-Driven Agents, giải phóng RAM/CPU nội bộ bằng cách đẩy toàn bộ tải tính toán huấn luyện mô hình lên Kaggle Cloud.

```mermaid
flowchart TD
    subgraph Giai đoạn 1: Data Prep
        BQ[(BigQuery)] -->|fetch_table_to_parquet| Staging[data/staging]
        Staging -->|push_dataset| KaggleDS[(Kaggle Private Dataset)]
    end

    subgraph Giai đoạn 2 & 3: Strategy & Sandbox
        User([Nhà nghiên cứu / Trigger API]) -->|Prompt / Params| AlphaAgent[Alpha Agent]
        LLM[LLM Service / GPT-4o] <-->|Structured JSON| AlphaAgent
        AlphaAgent -->|Build .ipynb| KaggleKernel[Kaggle Kernels Cloud]
        KaggleDS -.->|Link Dataset| KaggleKernel
    end

    subgraph Giai đoạn 4 & 5: Harvesting & Healing
        KaggleKernel -->|Polling Status| BacktestAgent[Backtest Agent]
        BacktestAgent -->|Complete -> Zip output| Evaluator{Kiểm định Sharpe > 1.2?}
        Evaluator -->|Đạt| Approved[Lưu .pkl vào /registry/models & Set APPROVED]
        Evaluator -->|Không đạt| Rejected[Set REJECTED]
        BacktestAgent -->|Error -> Traceback| SelfHealing[Self-Healing API]
        SelfHealing -->|Yêu cầu sửa code| AlphaAgent
    end

    subgraph Giai đoạn 6: Handover
        Approved --> DB[(TimescaleDB)]
        LiveOps([Khối 3: Live Trading Engine]) -->|GET /api/v1/strategies?status=APPROVED| DB
        LiveOps -->|Load .pkl| Registry[/registry/models]
    end
```

### Các Tác tử chính trong Hệ thống:
- **Tác tử Dữ liệu (Data Agent):** Trích xuất dữ liệu tài chính lịch sử từ Google Cloud BigQuery, lưu định dạng `.parquet` và tự động đẩy lên Kaggle Dataset.
- **Tác tử Kiến tạo (Alpha Agent):** Sử dụng LLM (OpenAI/Gemini) thông qua bộ thư viện `instructor` để tự động suy nghĩ, lập luận, viết mã Machine Learning hoặc bơm tham số kịch bản tĩnh (Rule-Based) vào Notebook `.ipynb`.
- **Tác tử Kiểm định (Backtest Agent):** Theo dõi tiến độ chạy ngầm trên Kaggle, thu hoạch file báo cáo chỉ số (`backtest_metrics.json`), lưu lưu trữ artifact mô hình (`.pkl`), đánh giá tự động và kích hoạt vòng lặp tự sửa lỗi khi phát hiện sự cố.

---

## 📁 Cấu trúc Thư mục

```text
research-lab/
├── app/
│   ├── agents/                 # Quản lý các Tác tử AI
│   │   ├── alpha_agent.py      # Alpha Agent: Tạo chiến lược tĩnh & động (ML) & Self-Healing
│   │   └── backtest_agent.py   # Backtest Agent: Polling, thu hoạch output, đánh giá
│   ├── api/                    # Tầng API Web (FastAPI)
│   │   └── v1/
│   │       ├── api.py          # Gom router v1
│   │       └── endpoints/
│   │           ├── strategies.py     # Endpoints CRUD chiến lược & kích hoạt AI Research/Self-Healing
│   │           └── backtest_runs.py  # Endpoints quản lý lịch sử kiểm định (Backtest Runs)
│   ├── core/                   # Cấu hình lõi & Kết nối CSDL
│   │   ├── config.py           # Đọc biến môi trường (.env) qua Pydantic Settings
│   │   └── database.py         # Khởi tạo SQLModel / SQLAlchemy engine
│   ├── prompts/                # Lưu trữ System Prompts & User Prompts cho LLM
│   ├── services/               # Các Dịch vụ nền tảng kết nối bên ngoài
│   │   ├── bigquery_service.py # Kéo dữ liệu giá từ Google Cloud BigQuery
│   │   ├── kaggle_service.py   # Tương tác Kaggle API (push/pull dataset & kernel)
│   │   ├── llm_service.py      # Kết nối LLM (OpenAI/Gemini) & ép cấu trúc JSON (Instructor)
│   │   └── notebook_builder.py # Sinh & đóng gói file .ipynb bằng nbformat & papermill
│   ├── templates/              # Các mẫu Notebook (.ipynb) cho luồng tĩnh (Rule-Based)
│   ├── main.py                 # Điểm khởi chạy FastAPI, cấu hình Lifespan & State Recovery
│   └── schemas.py              # Định nghĩa các mô hình CSDL & Schemas DTO (SQLModel/Pydantic)
├── data/                       # Thư mục chứa dữ liệu tạm thời
│   ├── staging/                # Dữ liệu Parquet chờ đẩy lên Kaggle Dataset
│   └── downloads/              # File Zip kết quả thu hoạch từ Kaggle chờ giải nén
├── docs/                       # Tài liệu thiết kế & mô tả chi tiết
│   ├── Activity_Description.md # Mô tả 6 giai đoạn hoạt động của hệ thống
│   └── Directory_Structure.md  # Sơ đồ thư mục dự án
├── registry/                   # Thư mục lưu trữ tài sản lâu dài (Volume Mount)
│   └── models/                 # Chứa các tệp mô hình (.pkl) đã qua kiểm định (APPROVED)
├── .env.example                # File mẫu cấu hình biến môi trường
├── Dockerfile                  # Containerize ứng dụng FastAPI Backend
├── docker-compose.yml          # Đóng gói và chạy đồng loạt Backend & TimescaleDB
└── requirements.txt            # Thư viện phụ thuộc (FastAPI, SQLModel, Kaggle, Instructor...)
```

---

## 🔑 Yêu cầu Môi trường & Cấu hình (.env)

### 1. Phụ thuộc phần mềm:
- **Docker** & **Docker Compose**
- Python **3.10+** (nếu chạy trực tiếp ở môi trường cục bộ)

### 2. Các tệp Bí mật & Cấu hình (Secrets):
Hệ thống cần các tệp chứng thực được đặt tại thư mục bí mật (mặc định là `../.secrets` tương đương cấu hình volume trong `docker-compose.yml`):
- `kaggle.json`: Chứa `username` và `key` API Kaggle.
- `credentials.json` (hoặc Service Account GCP): Kết nối Google BigQuery.

### 3. Thiết lập tệp `.env`:
Sao chép `.env.example` thành `.env` và cập nhật thông tin:

```env
# Cấu hình CSDL TimescaleDB / PostgreSQL
POSTGRES_SERVER=timescaledb
POSTGRES_PORT=5432
POSTGRES_USER=admin
POSTGRES_PASSWORD=Admin123
POSTGRES_DB=rnd_lab_db
ECHO_SQL=False

# Cấu hình Kaggle API
KAGGLE_USERNAME=your-kaggle-username

# Cấu hình OpenAI API (Dùng cho Alpha Agent)
OPENAI_API_KEY=sk-proj-your-openai-key
OPENAI_MODEL=gpt-4o
```

---

## 🚀 Hướng dẫn Khởi chạy Hệ thống

### Cách 1: Khởi chạy bằng Docker Compose (Khuyên dùng)

1. **Khởi chạy container CSDL và Backend API:**
   ```bash
   docker-compose up -d --build
   ```

2. **Kiểm tra trạng thái container:**
   ```bash
   docker-compose ps
   ```

3. **Xem nhật ký hoạt động (Logs):**
   ```bash
   docker-compose logs -f backend
   ```

4. **Truy cập tài liệu OpenAPI (Swagger UI):**
   - **Swagger UI:** [http://localhost:8000/docs](http://localhost:8000/docs)
   - **ReDoc:** [http://localhost:8000/redoc](http://localhost:8000/redoc)
   - **Healthcheck:** [http://localhost:8000/](http://localhost:8000/)

### Cách 2: Khởi chạy Cục bộ (Development Mode)

1. **Khởi tạo và kích hoạt môi trường ảo Python:**
   ```bash
   python -m venv venv
   source venv/bin/activate  # Trên macOS/Linux
   # venv\Scripts\activate   # Trên Windows
   ```

2. **Cài đặt thư viện:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Khởi chạy CSDL Postgres/TimescaleDB:**
   ```bash
   docker-compose up -d timescaledb
   ```

4. **Khởi chạy FastAPI Uvicorn Server:**
   ```bash
   uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
   ```

---

## 📖 Hướng dẫn Sử dụng theo Các Giai đoạn Hoạt động

Vòng đời hoạt động của hệ thống nghiên cứu chiến lược gồm 6 giai đoạn chính:

---

### Giai đoạn 1: Chuẩn bị Nguyên liệu & Đồng bộ Dữ liệu (Data Synchronization)

Trước khi khởi tạo chiến lược, hệ thống cần chuẩn bị bộ dữ liệu giá cổ phiếu Việt Nam sạch nhất trên môi trường mây.

1. **Truy vấn & Kéo dữ liệu:** `BigQueryService` kết nối tới GCP BigQuery, truy vấn dữ liệu giá thô (`raw_price`) và giá điều chỉnh (`adj_price`), sau đó kết xuất ra các file định dạng `.parquet` đặt tại thư mục `data/staging/`.
2. **Đẩy lên Kaggle Dataset:** `KaggleService` tự động nén dữ liệu tại `data/staging/` và tạo/cập nhật một Private Dataset trên Kaggle tên là `vn-stock-market-data` (ví dụ: `your-username/vn-stock-market-data`).

> **Kết quả:** Môi trường mây Kaggle đã có sẵn dữ liệu cổ phiếu mới nhất để sẵn sàng cho các Notebook truy cập (`/kaggle/input/vn-stock-market-data`).

---

### Giai đoạn 2: Kiến tạo Chiến lược (Strategy Generation)

Khi nhận được yêu cầu từ người dùng hoặc hệ thống tự động, **Tác tử Kiến tạo (Alpha Agent)** sẽ bắt đầu hoạt động. Hệ thống hỗ trợ 2 luồng:

#### 🟢 Luồng A: Chiến lược Tĩnh (Rule-Based / Heuristics)
- **Cơ chế:** Nhận bộ tham số cố định (ví dụ: `rsi_period=14`, `overbought=70`, `oversold=30`).
- **Thực thi:** `AlphaAgent` dùng `NotebookBuilderService` gọi `papermill` để bơm thẳng tham số này vào một file template `.ipynb` có sẵn trong thư mục `app/templates/`.

#### 🔵 Luồng B: Chiến lược Tự học (Machine Learning - Dynamic AI)
- **Cơ chế:** Nhận ý tưởng hoặc giả thuyết giao dịch bằng ngôn ngữ tự nhiên (Natural Language Prompt).
- **Thực thi:**
  1. `AlphaAgent` gửi prompt tới `LLMService`.
  2. `LLMService` kết hợp với thư viện `instructor` ép mô hình LLM trả về cấu trúc JSON chuẩn `LLMGeneratedStrategy` (bao gồm: `rationale`, `cell_imports`, `cell_data_prep`, `cell_model`, `cell_export`).
  3. `NotebookBuilderService` dùng `nbformat` lắp ráp các đoạn mã Python này thành một file Notebook `.ipynb` hoàn toàn mới.

*Ví dụ gọi API kích hoạt luồng sinh chiến lược ML:*
- **Endpoint:** `POST /api/v1/strategies/trigger-ml-research`
- **Request Payload:**
  ```json
  {
    "user_prompt": "Xây dựng mô hình Random Forest dự đoán xu hướng tăng giá dựa trên độ lệch giá so với đường MA20 và chỉ số RSI."
  }
  ```

---

### Giai đoạn 3: Thực thi trên Môi trường Cách ly (Sandbox Execution)

Sau khi tạo xong file `.ipynb`:

1. `AlphaAgent` tạo tệp cấu hình `kernel-metadata.json`, liên kết trực tiếp Notebook với bộ dữ liệu `vn-stock-market-data` ở Giai đoạn 1.
2. `KaggleService.push_kernel` đẩy Notebook này lên Kaggle Cloud.
3. Kaggle tiếp nhận và bắt đầu xếp hàng (`queued`) và chạy (`running`) huấn luyện/backtest mô hình trên hạ tầng ảo của Kaggle.
4. Cơ sở dữ liệu ghi nhận bản ghi `Strategy` ở trạng thái `TESTING` và `BacktestRun` chứa mã định danh `kaggle_kernel_id`. Máy chủ FastAPI giải phóng tài nguyên CPU/RAM ngay lập tức.

---

### Giai đoạn 4: Thu hoạch & Kiểm định Tự động (Harvesting & Validation)

Song song với quá trình Kaggle chạy, **Tác tử Kiểm định (Backtest Agent)** được kích hoạt ngầm (Background Task):

1. **Polling tiến độ:** `BacktestAgent` liên tục kiểm tra trạng thái Kaggle Kernel mỗi 30 giây qua API `get_kernel_status`.
2. **Kéo kết quả (Harvesting):** Khi trạng thái Kernel chuyển sang `complete`, `BacktestAgent` gọi `pull_kernel_output` tải tệp `.zip` kết quả về thư mục `data/downloads/` và giải nén.
3. **Đọc Metrics & Model Artifact:**
   - Đọc tệp `backtest_metrics.json` chứa các chỉ số đo đạc (`sharpe_ratio`, `max_drawdown`, `annual_return`...).
   - Tìm kiếm tệp mô hình đã huấn luyện (`.pkl`).
4. **Kiểm định tự động (Validation Rules):**
   - Nếu **Sharpe Ratio > 1.2** (hoặc vượt ngưỡng an toàn rủi ro):
     - Gán trạng thái chiến lược thành `APPROVED`.
     - Di chuyển tệp `.pkl` vào thư mục bền vững `/registry/models/model_<backtest_run_id>.pkl`.
   - Nếu không đạt chỉ số: Gán trạng thái chiến lược thành `REJECTED`.
5. **Cập nhật CSDL:** Ghi đầy đủ kết quả, chỉ số và đường dẫn artifact vào bảng `backtest_runs` và `strategies` trong TimescaleDB.

---

### Giai đoạn 5: Cơ chế Tự sửa lỗi (Self-Healing Loop)

Nếu ở Giai đoạn 4, Kaggle Kernel trả về trạng thái `error` (do LLM viết code bị lỗi cú pháp Python, thiếu thư viện, hoặc dính lỗi tràn RAM):

1. `BacktestAgent` gọi `get_kernel_log` để trích xuất đoạn log lỗi (traceback) thực tế trên Kaggle và lưu vào CSDL.
2. Tác tử kích hoạt cơ chế **Self-Healing**:
   - **Endpoint:** `POST /api/v1/strategies/heal-ml-research`
   - **Request Payload:**
     ```json
     {
       "backtest_run_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
       "traceback_log": "NameError: name 'pd' is not defined at line 12..."
     }
     ```
3. `AlphaAgent.heal_ml_strategy` truyền prompt gốc và đoạn traceback cho `LLMService.fix_strategy_error`.
4. LLM phân tích nguyên nhân gây ra lỗi, sửa lại đoạn code hỏng, lắp ráp thành Notebook `.ipynb` mới và đẩy lại Kaggle Kernel mới.
5. Quy trình tự động quay trở lại **Giai đoạn 3 & 4**.

---

### Giai đoạn 6: Sẵn sàng Bàn giao (Handover to Live Operations)

Khối 2 (Research Lab) lưu giữ danh mục các mô hình giao dịch chất lượng cao. Khi máy chủ của Khối 3 (**Live Operations / Automated Trading Engine**) khởi động:

1. **Khối 3 gọi REST API sang Khối 2:** Lấy danh sách các chiến lược đang ở trạng thái `APPROVED`:
   ```http
   GET /api/v1/strategies?status=APPROVED
   ```
2. **Khối 2 trả về danh sách:** Gồm thông tin mô hình, chỉ số Sharpe Ratio và đường dẫn lưu trữ tệp `.pkl` tại `/registry/models/`.
3. **Nạp Mô hình & Ra quyết định:** Khối 3 đọc tệp `.pkl` tương ứng vào RAM, kết nối dữ liệu thời gian thực (Real-time Feed) và bắt đầu sinh tín hiệu mua/bán thực tế.

---

## 📊 Danh mục API Endpoints & cURL Ví dụ

### 1. Đồng bộ Dữ liệu (`/api/v1/data`)

| HTTP Method | Endpoint | Mô tả |
| :--- | :--- | :--- |
| `POST` | `/api/v1/data/sync` | **[Kích hoạt Data Agent]** Kéo dữ liệu BigQuery (`adj_price`, `raw_price`) $\rightarrow$ Parquet $\rightarrow$ Kaggle Dataset |

### 2. Quản lý Chiến lược (`/api/v1/strategies`)

| HTTP Method | Endpoint | Mô tả |
| :--- | :--- | :--- |
| `POST` | `/api/v1/strategies/` | Tạo mới bản ghi chiến lược thủ công |
| `GET` | `/api/v1/strategies/` | Lấy danh sách chiến lược (Hỗ trợ lọc theo `status`, phân trang `skip`, `limit`) |
| `GET` | `/api/v1/strategies/{id}` | Lấy chi tiết chiến lược kèm lịch sử các lượt Backtest |
| `PATCH` | `/api/v1/strategies/{id}` | Cập nhật thông tin chiến lược |
| `DELETE` | `/api/v1/strategies/{id}` | Xóa chiến lược (Tự động xóa các BacktestRun liên quan) |
| `POST` | `/api/v1/strategies/trigger-ml-research` | **[Kích hoạt Alpha Agent]** Sinh code ML tự động từ Prompt |
| `POST` | `/api/v1/strategies/heal-ml-research` | **[Self-Healing]** Sửa lỗi code ML từ log traceback |

### 3. Quản lý Lượt Kiểm định (`/api/v1/backtest-runs`)

| HTTP Method | Endpoint | Mô tả |
| :--- | :--- | :--- |
| `POST` | `/api/v1/backtest-runs/` | Tạo mới lượt chạy kiểm định |
| `GET` | `/api/v1/backtest-runs/` | Lấy danh sách kiểm định (Lọc theo `is_successful`) |
| `GET` | `/api/v1/backtest-runs/{id}` | Lấy chi tiết lượt kiểm định kèm chiến lược liên quan |
| `PATCH` | `/api/v1/backtest-runs/{id}` | Cập nhật kết quả kiểm định |
| `DELETE` | `/api/v1/backtest-runs/{id}` | Xóa lượt kiểm định |

---

### 💡 Ví dụ cURL Thực thi

#### A. Kích hoạt Data Agent đồng bộ dữ liệu BigQuery lên Kaggle Dataset
```bash
curl -X 'POST' \
  'http://localhost:8000/api/v1/data/sync' \
  -H 'accept: application/json' \
  -H 'Content-Type: application/json' \
  -d '{
  "dataset_id": "financial_data",
  "table_ids": ["adj_price", "raw_price"],
  "dataset_slug": "vn-stock-market-data",
  "title": "Vietnam Stock Market Data (Auto-sync)"
}'
```

#### B. Kích hoạt Alpha Agent tự nghiên cứu chiến lược Machine Learning
```bash
curl -X 'POST' \
  'http://localhost:8000/api/v1/strategies/trigger-ml-research' \
  -H 'accept: application/json' \
  -H 'Content-Type: application/json' \
  -d '{
  "user_prompt": "Tạo mô hình XGBoost dự đoán lợi nhuận T+5 dựa trên biến động khối lượng giao dịch và dải Bollinger Bands."
}'
```

#### C. Xem danh sách các chiến lược đã được APPROVED cho Live Trading
```bash
curl -X 'GET' \
  'http://localhost:8000/api/v1/strategies?status=APPROVED&skip=0&limit=10' \
  -H 'accept: application/json'
```

#### D. Khôi phục tự động khi Kernel Kaggle báo lỗi (Self-Healing)
```bash
curl -X 'POST' \
  'http://localhost:8000/api/v1/strategies/heal-ml-research' \
  -H 'accept: application/json' \
  -H 'Content-Type: application/json' \
  -d '{
  "backtest_run_id": "YOUR_FAILED_BACKTEST_RUN_UUID",
  "traceback_log": "KeyError: '\''close_price'\'' not found in DataFrame columns"
}'
```


---

## 🔄 Cơ chế Phục hồi Trạng thái (State Recovery)

Trong trường hợp máy chủ Backend bị khởi động lại đột ngột (hoặc bị sập do sự cố điện/mạng) khi có các Kaggle Kernel đang trong quá trình huấn luyện trên đám mây:

- **Tính năng tự động phục hồi:** Trong hàm `lifespan` tại `app/main.py`, khi ứng dụng khởi động lại, hệ thống sẽ tự động quét CSDL TimescaleDB tìm tất cả các chiến lược đang ở trạng thái `TESTING` với lượt chạy chưa hoàn thành.
- **Tự khôi phục Polling Task:** Với mỗi tệp Kernel chưa hoàn tất, hệ thống sẽ tự động đăng ký lại tác vụ `poll_and_evaluate` vào Event Loop của FastAPI để tiếp tục theo dõi tiến độ Kaggle mà không bị mất dấu hay thất thoát dữ liệu.

---

## 🔒 Bảo mật & Quy tắc An toàn

1. **Không Commit Secret:** Không commit tệp `.env`, `kaggle.json` hoặc các tệp khóa GCP Service Account lên Git (Đã được chặn trong `.gitignore`).
2. **Ủy quyền Sandbox:** Mọi mã nguồn do LLM tự do sinh ra **chỉ được phép thực thi bên trong Kaggle Kernels**, tuyệt đối không chạy trực tiếp (`exec` / `eval`) trên server FastAPI cục bộ để đảm bảo an toàn hệ thống.
3. **Quản lý Volume:** Thư mục `/registry/models` cần được mount volume bền vững trên môi trường Production để bảo toàn tệp mô hình giao dịch `.pkl`.
