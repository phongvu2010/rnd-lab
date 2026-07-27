# Sử dụng base image Python để tối ưu dung lượng
FROM python:3.12-slim

# Thiết lập thư mục làm việc
WORKDIR /src

# Vô hiệu hóa bytecode và buffer để log hiện trực tiếp trên terminal
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Cài đặt các thư viện hệ thống cần thiết (nếu có)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev && rm -rf /var/lib/apt/lists/*

# Tạo và kích hoạt virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Cài đặt dependencies
COPY requirements.txt .
RUN pip install --upgrade pip && pip install --no-cache-dir -r requirements.txt

# Tạo thư mục và copy toàn bộ mã nguồn vào đó
COPY ./app /src/app

# Khai báo PYTHONPATH để Python coi /app là thư mục gốc chứa package
ENV PYTHONPATH=/src

# Tạo sẵn các thư mục cần thiết
RUN mkdir -p /src/data/staging /src/data/downloads /src/registry/models /src/config

# Mở port 8000 cho FastAPI
EXPOSE 8000

# Khởi chạy server bằng Uvicorn
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
