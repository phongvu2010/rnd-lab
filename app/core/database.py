from sqlmodel import create_engine, Session

from .config import settings

# Khởi tạo engine kết nối
# echo=True để in các câu lệnh SQL ra terminal (tiện cho việc debug lúc đầu)
engine = create_engine(
    settings.DATABASE_URL,
    echo=settings.ECHO_SQL,
    pool_pre_ping=True,  # Tự động kiểm tra và tái tạo kết nối bị hỏng
    pool_size=10,  # Số lượng connection duy trì sẵn
    max_overflow=20,  # Số connection tối đa được mở thêm khi tải cao
)


def get_session():
    """
    Dependency function dùng để tiêm (inject) database session vào các API endpoints.
    Đảm bảo mỗi request có một session độc lập và tự đóng sau khi xong.
    """
    with Session(engine) as session:
        yield session
