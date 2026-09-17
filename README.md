# HỆ THỐNG OCR SỔ ĐỎ / SỔ HỒNG (CADASTRAL OCR & DATA CONVERSION)

> **Hệ thống AI xử lý, bóc tách dữ liệu Giấy chứng nhận quyền sử dụng đất (GCNQSDĐ), lưu trữ dữ liệu thô Markdown và chuyển đổi sang bảng chuẩn 129 cột Kê khai Địa chính theo quy định của Bộ Tài nguyên & Môi trường.**

---

## 🌟 Tính Năng Nổi Bật

1. **Pipeline OCR Đa Tầng Thông Minh (Mẫu A & Mẫu B)**:
   - Tự động phân loại **Mẫu A** (1 trang - Giấy đỏ truyền thống) và **Mẫu B** (4 trang - Giấy hồng chuẩn mới).
   - Khử nhiễu, chỉnh nghiêng (`Deskew`), lọc màu nền (`Color Profiles`), loại bỏ dấu mộc đỏ/xanh (`Seal Masking`).
   - Kết hợp mô hình nhận diện tiếng Việt độ chính xác cao: **PaddleOCR PP-OCRv4** (phát hiện vùng chữ) + **VietOCR Transformer** (nhận diện quang học chính xác).
   - Tự động định vị và crop **Sơ đồ thửa đất** và đọc **Mã vạch Barcode (Trang 4)**.

2. **Lưu Trữ Bền Vững Vào PostgreSQL**:
   - Lưu trữ toàn bộ kết quả bóc tách, dữ liệu cấu trúc JSON và các dòng 129 cột vào cơ sở dữ liệu PostgreSQL.
   - Bảng tra cứu, tìm kiếm, lọc đa tiêu chí theo tên tệp, mẫu sổ, thư mục, đường dẫn nguồn trực quan trên Web.

3. **Xem Trước & Xuất Excel Bảng Tính Dữ Liệu Thô (3 Sheets)**:
   - Cho phép **xem trước dữ liệu bảng tính (Spreadsheet Preview Modal)** trực tiếp trên Web trước khi tải xuống:
     - **Sheet 1 (`Tóm Tắt Bóc Tách`)**: Toàn bộ các trường dữ liệu trích xuất chính.
     - **Sheet 2 (`Văn Bản OCR Chi Tiết`)**: Từng dòng chữ OCR kèm số trang và tệp ảnh nguồn.
     - **Sheet 3 (`Bảng 129 Cột`)**: Ánh xạ sơ bộ sang chuẩn địa chính.
   - Hỗ trợ xuất file Excel thô (`.xlsx`), file Markdown (`.md`) và file Excel 129 cột.

4. **Bảng Chuyển Đổi Địa Chính 129 Cột (Bộ Tài nguyên & Môi trường)**:
   - **Nạp Dữ Liệu Từ Markdown (DB)**: Tự động chuyển đổi toàn bộ kho dữ liệu Markdown thô trong DB sang cấu trúc bảng 129 trường.
   - Tự động phân tách hồ sơ có **nhiều thửa đất** thành từng dòng riêng biệt.
   - Bộ thẩm định & cảnh báo dữ liệu bất thường (`GCNValidators`): Cảnh báo sai định dạng CCCD/CMND, năm sinh, số vào sổ.
   - Lọc theo 12 phân nhóm nghiệp vụ (Chủ sử dụng, Giấy chứng nhận, Thửa đất, Nhà ở, Rừng trồng...).
   - Xuất dữ liệu ra tệp Excel (`.xlsx`) chuẩn theo biểu mẫu quy chuẩn nhà nước.

5. **Kiến Trúc Chuẩn Clean Architecture (DDD)**:
   - Tách biệt hoàn toàn Backend (FastAPI, Python) và Frontend (React 18, Vite, TypeScript, Tailwind CSS).
   - Bộ kiểm thử tự động cho parser, ánh xạ địa chính, pipeline và API.

---

## 📁 Cấu Trúc Dự Án

```
ocr-so-do/
├── backend/
│   ├── api/
│   │   ├── main.py                     # Bridge module → re-exports FastAPI app
│   │   └── __init__.py
│   ├── configs/                        # Tập tin cấu hình hệ thống
│   │   ├── template_labels.json        # Nhãn trường theo mẫu sổ A/B
│   │   ├── color_profiles.json         # Profile màu xử lý kênh ảnh
│   │   ├── field_mappings.json         # Ánh xạ mã mục đích sử dụng, nguồn gốc
│   │   └── excel_chuyen_doi_columns.json # Định nghĩa 129 cột địa chính
│   ├── weights/                        # Trọng số mô hình AI (VietOCR Transformer)
│   ├── src/ocr_so_do/                  # Core Clean Architecture (DDD)
│   │   ├── domain/                     # Thực thể, models (Cadastral129Row), validators
│   │   ├── application/                # Use cases (Single Process, Batch Scan), Projections (Cadastral129Mapper)
│   │   ├── infrastructure/             # OCR Engine, Preprocessing, PostgreSQL Store, Excel Exporters
│   │   └── interfaces/                 # API Routers (/documents, /batch, /batch-pairs, /pg, /exports)
│   └── tests/                          # Kiểm thử đơn vị domain models
├── frontend/                           # Giao diện Web SPA (React 18 + Vite + TypeScript)
│   ├── src/
│   │   ├── app/                        # Layout, điều hướng App.tsx, main.tsx
│   │   ├── pages/                      # Các màn hình chức năng chính
│   │   │   ├── batch-scan/             # Quét thư mục hàng loạt
│   │   │   ├── data-conversion/        # Bảng chuyển đổi 129 cột
│   │   │   ├── raw-markdown/           # Kho hồ sơ (PostgreSQL)
│   │   │   └── document-upload/        # Nhận dạng tài liệu đơn lẻ
│   │   └── shared/                     # Components, types, HTTP client
│   ├── package.json
│   └── vite.config.ts                  # Cấu hình proxy sang backend (:8000)
├── output/                             # Thư mục lưu kết quả xuất ra
│   └── diagrams/                       # Ảnh crop sơ đồ thửa đất
├── tests/                              # Bộ kiểm thử tích hợp
├── requirements.txt                    # Danh sách thư viện Python
├── run.py                              # CLI runner điều khiển hệ thống
└── README.md
```

---

## ⚙️ Yêu Cầu Hệ Thống

| Thành phần | Yêu cầu tối thiểu | Khuyến nghị |
| :--- | :--- | :--- |
| **Hệ điều hành** | Windows 10/11 64-bit hoặc Linux | Windows 11 / Ubuntu 22.04 LTS |
| **Python** | 3.10 – 3.12 | Python 3.12 |
| **Node.js** | Node.js 18+ | Node.js 20 LTS + npm |
| **RAM** | 8 GB | 16 GB trở lên |
| **GPU (Tuỳ chọn)** | NVIDIA GPU 4GB VRAM (CUDA 11.8/12.x) | NVIDIA RTX (Xử lý nhanh hơn gấp 5x so với CPU) |

---

## 🚀 Hướng Dẫn Cài Đặt

### 1. Cài Đặt Môi Trường Backend (Python)

Mở terminal tại thư mục gốc của dự án (`ocr-so-do`):

```bash
# 1. Tạo môi trường ảo Python
python -m venv .venv

# 2. Kích hoạt môi trường ảo
# Trên Windows PowerShell / CMD:
.venv\Scripts\activate
# Trên Linux / macOS:
source .venv/bin/activate

# 3. Nâng cấp pip
python -m pip install --upgrade pip

# 4. Cài đặt PyTorch
# Nếu có NVIDIA GPU (CUDA 12.1):
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121
# Nếu chỉ chạy bằng CPU:
pip install torch torchvision

# 5. Cài đặt PaddlePaddle
# Nếu có NVIDIA GPU (Windows):
pip install paddlepaddle-gpu==2.6.2.post120 -f https://www.paddlepaddle.org.cn/whl/windows/mkl/avx/stable.html
# Nếu chỉ chạy bằng CPU:
pip install paddlepaddle

# 6. Cài đặt toàn bộ các dependency còn lại
pip install -r requirements.txt
```

### Cấu hình môi trường

Sao chép `.env.example` thành `.env`, sau đó đặt `PG_PASSWORD` đủ mạnh nếu chạy PostgreSQL/Docker. Không đưa `.env` vào Git. Nếu PostgreSQL cục bộ chưa chạy, ứng dụng tự lưu dữ liệu OCR bằng SQLite; đặt `OCR_POSTGRES_ENABLED=false` để chủ động tắt kết nối PostgreSQL. Các biến giới hạn upload, CORS và worker batch đều được mô tả trong file mẫu.

---

### 2. Cài Đặt Môi Trường Frontend (Node.js)

Mở terminal mới, di chuyển vào thư mục `frontend/`:

```bash
cd frontend

# Cài đặt các package npm
npm install
```

### Chạy bằng Docker (cục bộ)

Sau khi đặt `PG_PASSWORD` trong `.env`:

```bash
docker compose up --build
```

Các cổng Docker mặc định chỉ bind vào `127.0.0.1`; dùng reverse proxy có TLS và xác thực khi triển khai cho nhiều người dùng.

---

## 🏃 Hướng Dẫn Khởi Chạy Hệ Thống

### Cách 1: Chạy Đầy Đủ Cả Backend và Frontend (Khuyến Nghị)

#### Bước 1: Khởi động Backend API Server (Port 8000)
Tại terminal gốc (đã kích hoạt `.venv`):

```bash
python run.py serve --host 127.0.0.1 --port 8000 --reload
```

Hoặc chạy trực tiếp qua `uvicorn`:
```bash
python -m uvicorn backend.api.main:app --host 127.0.0.1 --port 8000 --reload
```

- **Backend API**: [http://127.0.0.1:8000](http://127.0.0.1:8000)
- **Tài liệu API tương tác (Swagger UI)**: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- **Tài liệu Redoc**: [http://127.0.0.1:8000/redoc](http://127.0.0.1:8000/redoc)

#### Bước 2: Khởi động Frontend Web Application (Port 3000)
Tại terminal thư mục `frontend/`:

```bash
npm run dev -- --host 127.0.0.1 --port 3000
```

Truy cập ứng dụng tại trình duyệt: **[http://127.0.0.1:3000](http://127.0.0.1:3000)**

---

### Cách 2: Chạy Bằng Giao Diện Dòng Lệnh (CLI Runner)

Hệ thống cung cấp script `run.py` giúp thao tác trực tiếp từ terminal mà không cần mở giao diện Web:

```bash
# 1. OCR một file ảnh hoặc PDF và in kết quả ra màn hình:
python run.py ocr path/to/so_do.pdf

# 2. OCR và lưu kết quả cấu trúc ra file JSON:
python run.py ocr path/to/so_do.pdf -o ket_qua.json

# 3. OCR hàng loạt nhiều file và lưu vào thư mục:
python run.py ocr file1.pdf file2.jpg file3.png -d output/results/

# 4. Chạy chế độ CPU-only (không dùng GPU):
python run.py ocr path/to/so_do.pdf --cpu
```

---

## 📖 Hướng Dẫn Sử Dụng Các Phân Hệ Trên Giao Diện Web

Khi truy cập vào **[http://127.0.0.1:3000](http://127.0.0.1:3000)**, hệ thống cung cấp 4 phân hệ chính:

### 1. Quét Thư Mục Hàng Loạt (`Batch Scan`)
- Nhập đường dẫn thư mục trên máy chủ chứa các tệp PDF/ảnh Giấy chứng nhận (ví dụ: `D:\Tho\OCR\DataOCR\Ho so quet_VINHYEN`).
- Bấm **"Bắt Đầu Quét"** để pipeline tự động phân tích lần lượt từng tệp:
  - Tự động gom 4 trang đối với Mẫu B, crop ảnh sơ đồ thửa đất, đọc mã vạch trang 4.
  - Tự động lưu bản ghi dữ liệu thô Markdown vào cơ sở dữ liệu SQLite (`raw_ocr.db`).
- Bấm **"Xem Bảng 129 Cột"** để đối soát kết quả ngay lập tức.

### 2. Bảng Chuyển Đổi Địa Chính 129 Cột (`Data Conversion`)
- Bấm **"Nạp Dữ Liệu Từ Markdown (DB)"** để tải và tự động ánh xạ toàn bộ kho dữ liệu Markdown thô đã lưu trong DB thành bảng 129 cột chuẩn mẫu Kê khai Địa chính.
- Thanh tìm kiếm thông minh: Tìm theo số thửa, tờ bản đồ, số phát hành, tên chủ đất, số CCCD...
- Lọc nhanh theo từng nhóm cột: *Đơn đăng ký, Giấy chứng nhận, Chủ sử dụng 1, Vợ/Chồng, Thửa đất, Nhà ở, Rừng trồng...*
- Cảnh báo dữ liệu: Các ô chứa giá trị bất thường (ví dụ dính chữ trong năm sinh, sai số CCCD) sẽ được gắn cờ cảnh báo ⚠️ màu vàng/đỏ.
- Bấm **"Xuất File Excel (129 Cột)"** để tải về tệp `.xlsx` hoàn chỉnh theo định dạng của Bộ TN&MT.

### 3. Bảng Dữ Liệu Thô Markdown (`Raw Markdown`)
- Quản lý danh sách toàn bộ các bản ghi dữ liệu thô đã quét từ trước đến nay trong SQLite `raw_ocr.db`.
- **Xem trước bảng tính Excel (Spreadsheet Preview Modal)**: Bấm nút **"Bảng Excel"** trên bất kỳ dòng nào để mở modal xem trước 3 Sheet (Tóm tắt bóc tách, Dòng văn bản OCR chi tiết, Bảng 129 cột).
- Các chức năng xuất tệp:
  - **Tải Excel Thô (.xlsx)**: File Excel 2 Sheet chi tiết nội dung bóc tách và từng dòng OCR.
  - **Tải Bảng 129 Cột (.xlsx)**: File Excel chuẩn 129 cột của hồ sơ tương ứng.
  - **Tải Markdown (.md)**: Tải toàn văn bản ghi OCR Markdown để lưu trữ văn bản.
  - **Xuất Excel Danh Sách**: Tải file Excel tổng hợp danh sách toàn bộ hồ sơ trong bảng.

### 4. Nhận Dạng Tài Liệu Đơn Lẻ (`Single Upload`)
- Kéo thả hoặc chọn 1 tệp ảnh / PDF cần kiểm tra nhanh.
- Xem trực tiếp ảnh gốc, ảnh sơ đồ thửa đất đã bóc tách, mã vạch và dữ liệu JSON chi tiết.

---

## 🔌 Danh Sách API Endpoints Chính

### Nhóm Tiếp Nhận & OCR Hồ Sơ (`/api/v1/documents`)
| Phương thức | Đường dẫn | Chức năng |
| :---: | :--- | :--- |
| `POST` | `/api/v1/documents` | Upload một file tài liệu (PDF, PNG, JPG), chạy OCR và lưu PostgreSQL |

### Nhóm Quét Thư Mục Hàng Loạt (`/api/v1/batch`)
| Phương thức | Đường dẫn | Chức năng |
| :---: | :--- | :--- |
| `POST` | `/api/v1/batch/scan-directory` | Khởi chạy tác vụ quét thư mục trên máy chủ |
| `GET` | `/api/v1/batch/{batch_id}` | Theo dõi tiến độ quét thư mục theo thời gian thực |
| `POST` | `/api/v1/batch/{batch_id}/cancel` | Gửi yêu cầu dừng tác vụ quét |
| `GET` | `/api/v1/batch/{batch_id}/download-excel` | Tải file Excel 129 cột checkpoint |
| `GET` | `/api/v1/batch/{batch_id}/rows-129` | Lấy dữ liệu 129 cột của đúng đợt quét |
| `POST` | `/api/v1/batch/{batch_id}/convert-markdown-to-129-excel` | Xuất Excel 129 cột theo yêu cầu |

### Nhóm Kho Lưu Trữ PostgreSQL (`/api/v1/pg`)
| Phương thức | Đường dẫn | Chức năng |
| :---: | :--- | :--- |
| `GET` | `/api/v1/pg/health` | Kiểm tra kết nối cơ sở dữ liệu PostgreSQL |
| `GET` | `/api/v1/pg/stats` | Thống kê số lượng mẻ quét, tổng hồ sơ, thành công / lỗi |
| `GET` | `/api/v1/pg/filters` | Danh sách các thư mục kết quả và đường dẫn nguồn để lọc |
| `GET` | `/api/v1/pg/records` | Tra cứu danh sách hồ sơ với bộ lọc đa tiêu chí |
| `GET` | `/api/v1/pg/records/{doc_id}` | Lấy chi tiết hồ sơ (Markdown, JSONB cấu trúc, 129 cột) |
| `GET` | `/api/v1/pg/records/{doc_id}/preview-excel` | Dữ liệu xem trước 3 bảng trong Modal Excel |
| `GET` | `/api/v1/pg/records/{doc_id}/download-md` | Tải về tệp Markdown (.md) thô |
| `GET` | `/api/v1/pg/129-rows` | Trích xuất các dòng 129 cột theo thư mục/mẻ quét |
| `POST` | `/api/v1/pg/export-129-excel` | Xuất trực tiếp file Excel 129 cột từ dữ liệu PostgreSQL |
| `GET` | `/api/v1/pg/export-raw-db` | **Tải toàn bộ CSDL dữ liệu thô dạng JSON (sao lưu/đối soát)** |
| `GET` | `/api/v1/pg/export-raw-markdown` | **Tải trọn gói các tệp văn bản Markdown thô dạng .zip** |
| `DELETE` | `/api/v1/pg/records` | Xóa có chọn lọc danh sách hồ sơ theo ID |
| `DELETE` | `/api/v1/pg/by-folder` | Xóa toàn bộ hồ sơ thuộc thư mục kết quả |
| `DELETE` | `/api/v1/pg/by-source` | Xóa toàn bộ hồ sơ theo đường dẫn trên máy |

### Nhóm Xuất & Cấu Hình 129 Cột (`/api/v1/exports`)
| Phương thức | Đường dẫn | Chức năng |
| :---: | :--- | :--- |
| `GET` | `/api/v1/exports/columns-129` | Lấy cấu hình 129 cột và danh mục 12 nhóm nghiệp vụ |
| `POST` | `/api/v1/exports/excel-129` | Xuất danh sách các hàng 129 cột ra tệp Excel (.xlsx) |

### Nhóm Hệ Thống
| Phương thức | Đường dẫn | Chức năng |
| :---: | :--- | :--- |
| `GET` | `/health` | Kiểm tra trạng thái hoạt động của backend API |

---

## 🧪 Kiểm Thử Hệ Thống (Automated Testing)

Dự án có kiểm thử cho tiền xử lý, parser, ánh xạ dữ liệu, lưu trữ và API. Chạy hai nhóm riêng biệt để tránh xung đột tên package `tests`:
```bash
# Tại thư mục gốc dự án
pytest tests/ -q

# Tại thư mục backend
cd backend
pytest tests/ -q
```

Hãy dùng kết quả của CI/lần chạy hiện tại làm chuẩn; không cố định số lượng test trong tài liệu.

Kiểm thử biên dịch Frontend:
```bash
cd frontend
npm run build
# Kết quả: tsc && vite build hoàn thành không có lỗi Type/CSS
```

---

## 🛠️ Xử Lý Sự Cố Thường Gặp (Troubleshooting)

| Sự cố | Nguyên nhân | Hướng khắc phục |
| :--- | :--- | :--- |
| **CUDA out of memory** | VRAM của GPU không đủ tải đồng thời mô hình | Thêm cờ `--cpu` khi chạy lệnh CLI hoặc giảm số luồng xử lý song song trong file cấu hình. |
| **Lỗi font / Unicode trên Console Windows** | Bảng mã CMD/PowerShell mặc định là cp1252/cp437 | Hệ thống đã tích hợp sẵn tự động `sys.stdout.reconfigure(encoding="utf-8")`. Bạn cũng có thể gõ `chcp 65001` trước khi chạy terminal. |
| **VietOCR không tải được model** | Lần đầu chạy cần tải weights từ internet | Đảm bảo kết nối internet ổn định hoặc kiểm tra tệp weights trong thư mục `backend/weights/`. |
| **Frontend không gọi được API (:8000)** | Backend chưa khởi động hoặc sai port | Kiểm tra terminal backend xem đã có log `Uvicorn running on http://127.0.0.1:8000` chưa. Đảm bảo cổng 8000 không bị chiếm dụng bởi ứng dụng khác. |

---

## 📄 Bản Quyền & Giấy Phép
Dự án phát triển phục vụ mục đích số hóa và chuyển đổi dữ liệu địa chính Giấy chứng nhận quyền sử dụng đất tại Việt Nam.
Mọi thắc mắc và đóng góp phát triển vui lòng mở Issue hoặc Pull Request.
