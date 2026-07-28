rnd_lab_backend/
├── app/
│   ├── api/                    
│   │   ├── endpoints/          
│   │   │   ├── kaggle.py       # API kích hoạt và đồng bộ Kaggle
│   │   │   └── strategies.py   # API CRUD quản lý chiến lược
│   │   └── router.py           # Gom nhóm các route
│   ├── core/                   
│   │   ├── config.py           # Đọc biến môi trường (.env)
│   │   ├── database.py         # Khởi tạo engine PostgreSQL (SQLModel)
│   │   └── kaggle_client.py    # Cấu hình xác thực thư viện Kaggle API
│   ├── models/                 
│   │   └── schemas.py          # Class Strategy, BacktestRun (SQLModel)
│   ├── services/               
│   │   ├── kaggle_service.py   # Xử lý nén zip, push/pull dataset & kernel
│   │   ├── llm_service.py      # Giao tiếp OpenAI/Gemini & ép kiểu JSON
│   │   ├── notebook_builder.py # Dùng nbformat sinh file .ipynb
│   │   └── evaluator.py        # Đọc metrics.json và quyết định Approved/Rejected
│   ├── agents/                 
│   │   ├── alpha_agent.py      # Tổ chức luồng: LLM -> Notebook -> Kaggle
│   │   └── backtest_agent.py   # Nhận webhook/polling -> Đánh giá -> Lưu Database
│   ├── prompts/                
│   │   └── alpha_prompts.py    # Lưu trữ System Prompt & User Prompt cho LLM
│   └── main.py                 # Điểm khởi chạy của ứng dụng FastAPI
├── data/                       # Thư mục tạm (gắn volume rác)
│   ├── staging/                # File CSV/Parquet chờ đẩy lên Kaggle
│   └── downloads/              # File .zip Kaggle trả về chờ giải nén
├── registry/                   # Thư mục lưu trữ bền vững (gắn volume thật)
│   └── models/                 # Chứa các file .pkl đã được APPROVED
├── .env                        # Chứa DB_URL, KAGGLE_USERNAME, OPENAI_API_KEY...
├── .gitignore
├── requirements.txt            # fastapi, sqlmodel, kaggle, nbformat, instructor...
├── Dockerfile                  # Lệnh build image cho backend
└── docker-compose.yml          # Khởi chạy đồng loạt Backend và PostgreSQL
