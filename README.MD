<div align="center">
<h1>Horus Maps</h1>
</div>

<div align="center">
  <img alt="Static Badge" src="https://img.shields.io/badge/Viettel_Digital_Talent-2026-red?labelColor=151515&color=EE4E4E">
  <img alt="Static Badge" src="https://img.shields.io/badge/Track-System Programming-orange?labelColor=151515&color=F4CE14">
  <img alt="GitHub code size in bytes" src="https://img.shields.io/github/languages/code-size/CptDat9/horus-maps?labelColor=7AA2E3&color=97E7E1">
</div>

Horus Maps là hệ thống bản đồ (Full-stack GIS) giúp quản lý, hiển thị, phân tích ảnh vệ tinh Sentinel-2, Google Satellite, OSM và tự động phát hiện đối tượng thông qua trí tuệ nhân tạo (AI Detection). Hệ thống đọc trực tiếp dữ liệu ảnh vệ tinh tối ưu hóa đám mây (COG) từ Cloud (AWS S3) và xử lý cắt lát bản đồ siêu tốc.

---

## Chức năng chính

### 1. Hiển thị bản đồ và Xử lý dữ liệu không gian
* Hiển thị đa nguồn nền: Hỗ trợ tích hợp đa dữ liệu nền bao gồm Sentinel-2, Google Maps và OpenFreeMap với khả năng chuyển đổi layer linh hoạt.
* Tile Server siêu tốc: Sử dụng TiTiler để giải mã động và cắt nhỏ ảnh vệ tinh dạng COG từ AWS S3 bằng HTTP Range Request, truyền trực tiếp pixel về trình duyệt theo lược đồ tọa độ Web Mercator.
* Quản lý mục lục chuẩn hóa (STAC API): Vận hành một catalog STAC cục bộ qua schema pgstac trên PostgreSQL, cho phép tìm kiếm dữ liệu không gian - thời gian thống nhất theo chuẩn OpenGIS.

### 2. Tương tác vùng quan tâm (AOI) và Đo đạc
* Quản lý vùng ngữ cảnh (AOI): Cho phép khoanh vùng đa giác quan tâm, lưu trữ dưới dạng hình học PostGIS (SRID 4326) làm tham số đầu vào cho mọi tác vụ phân tích.
* Tính toán hình học chính xác: Tích hợp công cụ đo chu vi bằng khoảng cách Haversine và tính diện tích bằng công cụ Shoelace hiệu chỉnh vĩ độ WGS84 ở phía Client, kết hợp kiểm tra chính xác phía Backend bằng PostGIS.
* So sánh dòng thời gian: Hỗ trợ hiển thị và đối chiếu biến động bề mặt của cùng một khu vực AOI giữa hai thời điểm chụp khác nhau.

### 3. Phát hiện đối tượng thông minh (AI Detection)
* Định vị khung bao có hướng (OBB): Sử dụng mô hình YOLO11s-OBB (huấn luyện trên bộ dữ liệu không ảnh DOTA v1.0) nhằm nhận diện chính xác các đối tượng có góc xoay tự do như máy bay, tàu thuyền, xe cộ, bến cảng.
* Trích xuất tọa độ địa lý trực tiếp: Quy chiếu kết quả nhận diện từ hệ tọa độ pixel của ô ảnh bản đồ ngược về tọa độ địa lý thế giới theo thuật toán Web Mercator thuận nghịch, xuất trực tiếp ra định dạng GeoJSON để chồng lớp (overlay) lên bản đồ.
* Thuật toán lọc trùng toàn cục: Áp dụng cơ chế Non-Maximum Suppression (NMS) tính toán IoU xoay trên toàn bộ ranh giới vùng AOI để khử trùng lặp đối tượng tại các vùng biên chồng lấn giữa các ô ảnh.

### 4. Kiến trúc bất đồng bộ và Tối ưu hiệu năng
* Xử lý đa luồng và Bất đồng bộ: Sử dụng mutex để lock việc nặng (AI Detection), 8 threads worker cho việc tải ảnh (sử dụng ThreadPool). Cấu hình gunicorn/uvicorn phân phối bất đồng bộ kết hợp tinh chỉnh các cờ nhớ gầm của thư viện GDAL (GDAL_CACHEMAX, VSI_CACHE), giúp tối ưu hóa dung lượng RAM và gánh tải mượt mà cho luồng đọc dữ liệu từ S3 Cloud.
* Hàng đợi tác vụ phân tầng (Message Queue): Tích hợp RabbitMQ để tách biệt hoàn toàn tác vụ nặng ra khỏi tiến trình xử lý HTTP request chính. Phân định mức độ ưu tiên (Priority) giúp các tác vụ nhẹ (so sánh ảnh, đo đạc) không bị nghẽn bởi tác vụ AI Detection chạy dài.
* Đồng bộ thời gian thực: Sử dụng cầu nối Redis Pub/Sub kết hợp SSE (Server-Sent Events) và WebSocket để cập nhật trạng thái, tiến độ xử lý của tác vụ AI từ Worker về giao diện người dùng theo thời gian thực.
* Cơ chế bộ nhớ đệm (Caching): Sử dụng Redis để lưu trữ tầng dữ liệu Map tiles và metadata STAC với cơ chế thời gian sống (TTL) phân tầng, giảm thiểu tối đa I/O hệ thống.

---

## Hướng dẫn khởi chạy nhanh

Dự án đã được đóng góigói bằng Docker Compose, chỉ cần chạy đúng một số lệnh để bật toàn bộ hạ tầng (Database, Message Broker, API, Frontend) lên môi trường Local.

### 1. Chuẩn bị
* Máy đã cài sẵn Docker và Docker Compose.
* Nếu dùng Windows, hãy chắc chắn đã bật ứng dụng Docker Desktop và kích hoạt tính năng tích hợp WSL 2.

### 2. Các bước chạy
Mở terminal tại thư mục gốc của dự án và chạy các lệnh sau:

#### Tạo file môi trường từ file mẫu
```bash
cp .env.example .env
```
#### Khởi chạy toàn bộ hệ thống dưới nền và tự động build
```bash
docker compose up -d --build
```
### 3. Địa chỉ truy cập các dịch vụ

| Thành phần | URL Truy cập | Ghi chú |
| :--- | :--- | :--- |
| Giao diện Web App | http://localhost:3000 | Nơi tương tác bản đồ, vẽ AOI và xem kết quả AI |
| Backend API | http://localhost:8000 | API chính xử lý logic và điều phối tác vụ |
| STAC API | http://localhost:8080 | Cổng truy vấn danh mục ảnh vệ tinh cục bộ |
| Tile Server | http://localhost:8081 | Máy chủ TiTiler render các ô bản đồ động |
| Quản lý RabbitMQ | http://localhost:15672 | Giao diện theo dõi hàng đợi (Tài khoản: admin / admin) |

---

## Kiểm tra hệ thống hoạt động

- Sau khi khởi chạy bằng Docker Compose, bạn có thể kiểm tra xem các dịch vụ đã sẵn sàng và khỏe mạnh (healthy) hay chưa bằng lệnh:

```bash
docker compose ps
```

- Nếu muốn theo dõi tiến trình nạp log hoặc gỡ lỗi trực tiếp từ các container (như API hoặc Worker), sử dụng lệnh:

```bash
docker compose logs -f
```
## Dừng hệ thống
- Khi không sử dụng và muốn giải phóng hoàn toàn tài nguyên CPU cũng như bộ nhớ RAM cho máy tính, bạn chạy lệnh sau để hạ các container xuống một cách an toàn:
```bash
docker compose down
```