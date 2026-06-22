"""
STAC API chuẩn, chạy thành một service riêng (mặc định port 8080).

Đây là nguồn dữ liệu STAC chính của hệ thống: ứng dụng stac-fastapi-pgstac
được kết nối với PgSTAC schema trong PostgreSQL/PostGIS dùng chung.

API chính của Horus (`app.main`) không mount trực tiếp app này. Thay vào đó,
`app.apis.stac_api` sẽ proxy các request `/api/stac/*` sang service này.
Làm như vậy giúp frontend vẫn gọi cùng một domain/origin, nhưng toàn bộ request
STAC vẫn được xử lý bởi engine STAC chuẩn.

Ở đây ta import lại app có sẵn từ thư viện `stac-fastapi-pgstac`, thay vì tự tạo
`StacApi` thủ công. Cách này giúp app luôn khớp với version thư viện đang cài
và tự dùng đúng các extension mà thư viện cấu hình.

Các biến môi trường:

    POSTGRES_USER / POSTGRES_PASS / POSTGRES_DBNAME
    POSTGRES_HOST_READER / POSTGRES_HOST_WRITER / POSTGRES_PORT
    STAC_FASTAPI_TITLE / STAC_FASTAPI_DESCRIPTION

Nếu không set `ENABLED_EXTENSIONS`, stac-fastapi-pgstac sẽ bật các extension
mặc định/có sẵn. Nếu có set `ENABLED_EXTENSIONS`, nó chỉ bật các extension
được khai báo trong biến đó.

Chạy service bằng lệnh:

    uvicorn app.stac.app:app --host 0.0.0.0 --port 8080
"""
from stac_fastapi.pgstac.app import app

__all__ = ["app"]
