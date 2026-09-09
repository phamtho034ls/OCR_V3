# HỆ THỐNG OCR SỔ ĐỎ / SỔ HỒNG (CADASTRAL OCR & DATA CONVERSION)

> **Hệ thống AI xử lý, bóc tách dữ liệu Giấy chứng nhận quyền sử dụng đất (GCNQSDĐ), lưu trữ dữ liệu thô Markdown và chuyển đổi sang bảng chuẩn 129 cột Kê khai Địa chính theo quy định của Bộ Tài nguyên & Môi trường.**

---

## 🌟 Tính Năng Nổi Bật

1. **Pipeline OCR Đa Tầng Thông Minh (Mẫu A & Mẫu B)**:
   - Tự động phân loại **Mẫu A** (1 trang - Giấy đỏ truyền thống) và **Mẫu B** (4 trang - Giấy hồng chuẩn mới).
   - Khử nhiễu, chỉnh nghiêng (`Deskew`), lọc màu nền (`Color Profiles`), loại bỏ dấu mộc đỏ/xanh (`Seal Masking`).
   - Kết hợp mô hình nhận diện tiếng Việt độ chính xác cao: **PaddleOCR PP-OCRv4** (phát hiện vùng chữ) + **VietOCR Transformer** (nhận diện quang học chính xác).
   - Tự động định vị và crop **Sơ đồ thửa đất** và đọc **Mã vạch Barcode (Trang 4)**.

2. **Lưu Trữ Bền Vững Dữ Liệu Thô Dạng Markdown (`SQLite Raw Store`)**:
   - Lưu trữ toàn bộ kết quả bóc tách thô và các dòng text OCR theo thứ tự không gian (`Spatial Reading Order`) vào cơ sở dữ liệu SQLite cục bộ (`output/raw_ocr.db`) dạng Zero-Config.
   - Bảng tra cứu, tìm kiếm, lọc theo tên tệp và mẫu sổ trực quan trên Web.

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
   - Hệ thống kiểm thử tự động toàn diện (168 test cases, 100% PASS).

---

## 📁 Cấu Trúc Dự Án

```
ocr-so-do/
├── backend/
│   ├── api/
│   │   ├── main.py                     # Ứng dụng FastAPI, middleware, CORS, định tuyến
│   │   ├── dependencies.py             # Dependency injection cho API
│   │   └── static/                     # Giao diện HTML tĩnh phụ trợ (index.html, app.js)
│   ├── configs/                        # Tập tin cấu hình hệ thống
│   │   ├── template_labels.json        # Nhãn trường theo mẫu sổ A/B
│   │   ├── color_profiles.json         # Profile màu xử lý kênh ảnh
│   │   ├── field_mappings.json         # Ánh xạ mã mục đích sử dụng, nguồn gốc
│   │   └── excel_chuyen_doi_columns.json # Định nghĩa 129 cột địa chính
│   ├── weights/                        # Trọng số mô hình AI (VietOCR Transformer)
│   ├── src/ocr_so_do/                  # Core Clean Architecture (DDD)
│   │   ├── domain/                     # Thực thể, models (Job, Cadastral129Row), validators
│   │   ├── application/                # Use cases (Single Process, Batch Scan), Projections (Cadastral129Mapper)
│   │   ├── infrastructure/             # OCR Engine, Preprocessing, SQLite Store, Excel Exporters
│   │   └── interfaces/                 # API Routers (/ocr, /batch, /raw-ocr, /chuyen-doi)
│   └── tests/                          # Kiểm thử đơn vị domain models
├── frontend/                           # Giao diện Web SPA (React 18 + Vite + TypeScript)
│   ├── src/
│   │   ├── app/                        # Layout, điều hướng App.tsx, main.tsx
│   │   ├── pages/                      # Các màn hình chức năng chính
│   │   │   ├── batch-scan/             # Quét thư mục hàng loạt
│   │   │   ├── data-conversion/        # Bảng chuyển đổi 129 cột (Nạp từ Markdown DB)
│   │   │   ├── raw-markdown/           # Bảng quản lý & xem trước Excel Markdown DB
│   │   │   └── document-upload/        # Nhận dạng tài liệu đơn lẻ
│   │   └── shared/                     # Components, types, HTTP client
│   ├── package.json
│   └── vite.config.ts                  # Cấu hình proxy sang backend (:8000)
├── output/                             # Thư mục lưu kết quả xuất ra
│   ├── raw_ocr.db                      # Cơ sở dữ liệu SQLite lưu Markdown thô
│   └── diagrams/                       # Ảnh crop sơ đồ thửa đất
├── tests/                              # Bộ kiểm thử tích hợp (158 test cases)
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

---

### 2. Cài Đặt Môi Trường Frontend (Node.js)

Mở terminal mới, di chuyển vào thư mục `frontend/`:

```bash
cd frontend

# Cài đặt các package npm
npm install
```

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

### Nhóm Chuyển Đổi Dữ Liệu 129 Cột
| Phương thức | Đường dẫn | Chức năng |
| :---: | :--- | :--- |
| `GET` | `/chuyen-doi/columns` | Lấy danh sách định nghĩa 129 cột và các phân nhóm |
| `GET` | `/chuyen-doi/load-from-markdown-db` | **Nạp toàn bộ dữ liệu Markdown từ DB và chuyển đổi sang 129 cột** |
| `GET` | `/chuyen-doi/vinhyen-50` | Lấy dữ liệu mẫu đã bóc tách (hỗ trợ fallback DB) |
| `POST` | `/chuyen-doi/export` | Xuất danh sách các hàng 129 cột ra tệp Excel (.xlsx) |

### Nhóm Dữ Liệu Thô Markdown (Raw OCR)
| Phương thức | Đường dẫn | Chức năng |
| :---: | :--- | :--- |
| `GET` | `/api/v1/raw-ocr` | Danh sách bản ghi tóm tắt trong SQLite (hỗ trợ phân trang, tìm kiếm) |
| `GET` | `/api/v1/raw-ocr/to-129-rows` | Chuyển đổi toàn bộ dữ liệu thô sang 129 cột (chuẩn Clean Architecture) |
| `GET` | `/api/v1/raw-ocr/export-table-excel` | Tải về tệp Excel danh sách bảng dữ liệu thô |
| `GET` | `/api/v1/raw-ocr/{doc_id}` | Lấy chi tiết toàn văn Markdown của một hồ sơ |
| `GET` | `/api/v1/raw-ocr/{doc_id}/preview-excel` | **Lấy dữ liệu JSON để xem trước bảng tính Excel trên UI** |
| `GET` | `/api/v1/raw-ocr/{doc_id}/export-excel` | Tải về tệp Excel thô (.xlsx) gồm 2 Sheet |
| `GET` | `/api/v1/raw-ocr/{doc_id}/export-129-excel` | Tải về tệp Excel 129 cột (.xlsx) của hồ sơ |
| `GET` | `/api/v1/raw-ocr/{doc_id}/download` | Tải về tệp Markdown (.md) |
| `DELETE` | `/api/v1/raw-ocr/{doc_id}` | Xóa một bản ghi dữ liệu thô |

### Nhóm OCR & Xử Lý
| Phương thức | Đường dẫn | Chức năng |
| :---: | :--- | :--- |
| `POST` | `/ocr` | OCR một tệp ảnh / PDF đơn lẻ |
| `POST` | `/api/v1/batch/scan-directory` | Bắt đầu tác vụ quét toàn bộ một thư mục |
| `GET` | `/api/v1/batch/{batch_id}/status` | Theo dõi tiến độ quét thư mục theo thời gian thực |
| `GET` | `/health` | Kiểm tra trạng thái máy chủ và mô hình AI |

---

## 🧪 Kiểm Thử Hệ Thống (Automated Testing)

Dự án trang bị hệ thống kiểm thử tự động đạt độ phủ cao, bao quát toàn bộ pipeline tiền xử lý, nhận dạng, bóc tách, lưu trữ SQLite và xuất Excel.

Chạy toàn bộ 168 bài kiểm thử:
```bash
# 1. Chạy qua script runner:
python run.py test

# 2. Hoặc chạy trực tiếp qua pytest:
pytest tests/ -q
pytest backend/tests/ -q
```

**Kết quả kiểm thử chuẩn:**
- `tests/`: 158 passed (100%)
- `backend/tests/`: 10 passed (100%)
- **Tổng cộng: 168/168 test cases ĐẠT 100%.**

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
