# HORUS MAPS GEOSPATIAL API BENCHMARK REPORT

**Thực thi vào lúc:** 2026-07-10 12:34:05 | **Môi trường:** Production/Local Validation

## 1. Đánh giá Chức năng Hệ thống (Functional Matrix)
| Module      | Endpoint                     | Passed   | Detail                                                |
|:------------|:-----------------------------|:---------|:------------------------------------------------------|
| System      | GET /health                  | True     | Status: 200                                           |
| Map         | GET /api/layers              | True     | Fetched layers list                                   |
| Session     | POST /api/sessions           | True     | Session created: 2cadea8e-1190-4e87-bae6-7faea3e21151 |
| Session     | GET /api/sessions/{id}       | True     | Fetched session info                                  |
| AOI         | POST /api/sessions/{id}/aois | True     | AOI created: fd761a7c-1949-4f6e-8b5c-850e995155dc     |
| AOI         | GET /api/sessions/{id}/aois  | True     | Listed AOis successfully                              |
| STAC Direct | GET [8080] /collections      | True     | Direct connection to stac-fastapi                     |
| STAC Proxy  | GET /api/stac/collections    | True     | Core gateway successfully proxied STAC                |
| STAC Proxy  | POST /api/stac/search        | True     | STAC Search verified                                  |
| Detection   | POST .../detections          | False    | Task queued successfully                              |
| Detection   | GET .../detections           | True     | Latest run read verified                              |
| Measurement | POST .../measurements        | True     | Saved area measurement                                |
| Comparison  | POST .../comparisons         | True     | Comparison task initialization verified               |

## 2. Kết quả Đo kiểm Hiệu năng Chi tiết (Latency & Percentiles)
| Endpoint                          | Method   |   Min(ms) |   Max(ms) |   Avg(ms) |   P50(ms) |   P95(ms) |   P99(ms) |   Success_Rate |
|:----------------------------------|:---------|----------:|----------:|----------:|----------:|----------:|----------:|---------------:|
| GET /health                       | GET      |   4.42266 |   9.9268  |   5.61051 |   5.21457 |   8.0971  |   9.56086 |              1 |
| GET /api/layers (Redis Cache)     | GET      |   5.5449  |   7.9639  |   6.26416 |   6.04618 |   7.79824 |   7.93077 |              1 |
| GET /api/stac/collections         | GET      |  23.7939  |  57.6465  |  35.3591  |  32.3503  |  53.476   |  56.8124  |              1 |
| GET /api/stac/items/{id}/tile-url | GET      |  10.1259  |  94.3756  |  22.9552  |  12.6795  |  62.8468  |  88.0698  |              1 |
| GET Tile Proxy (Cache MISS)       | GET      |   6.92582 |  42.249   |  16.4715  |  10.4611  |  36.556   |  41.1104  |              1 |
| GET Tile Proxy (Cache HIT)        | GET      |   4.704   |   6.76179 |   5.56219 |   5.56564 |   6.46256 |   6.70194 |              1 |

## 3. Thử nghiệm Tải đồng thời Cao tầng (Stress Test Assessment)
|   Concurrency |   Throughput(req/s) |   Avg_Latency(ms) |   P95_Latency(ms) |   Success_Rate |
|--------------:|--------------------:|------------------:|------------------:|---------------:|
|            10 |               21.72 |            244.91 |            336.07 |            100 |
|            20 |               35.56 |            336.84 |            503.71 |            100 |
|            50 |               34.6  |            826.56 |           1322.1  |            100 |
|           100 |               35.45 |           1444.76 |           2605.57 |            100 |

## 4. Phân tích chi tiết và Khuyến nghị Kiến trúc
### 🚀 Cơ chế Tăng tốc Phản hồi bằng Redis Caching
- Lớp đệm Redis Tiling giúp tăng tốc độ phản hồi dữ liệu ảnh bản đồ lên **2.96 lần** so với việc phân tích cấu trúc COG/TiTiler trực tiếp.
### 🧠 Kiến trúc Bất đồng bộ trong Xử lý Không gian & AI
- Các tiến trình nhận diện vật thể (`TaskType.DETECTION`) và tính toán biến động thời gian (`TaskType.TEMPORAL_COMPARISON`) được tách biệt hoàn toàn sang hàng đợi task của Worker thông qua cơ chế phản hồi trạng thái `202 ACCEPTED` giúp Main API duy trì tính sẵn sàng cao, không bị nghẽn luồng IO-bound khi chạy mô hình AI nặng.
