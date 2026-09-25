# HƯỚNG DẪN TẢI, CẤU HÌNH VÀ QUẢN LÝ MODEL AI CHO HỆ THỐNG OCR SỔ ĐỎ

> **Tài liệu hướng dẫn tải weights, cấu hình đường dẫn và triển khai offline (không cần internet) cho các mô hình AI: VietOCR, PaddleOCR và LLM Suy luận biến động (Qwen/Ollama).**

---

## 📌 Tổng Quan Về Các Mô Hình AI Trong Hệ Thống

Hệ thống OCR Sổ Đỏ / Sổ Hồng kết hợp pipeline AI đa tầng gồm 3 nhóm mô hình chính:

| Nhóm Mô Hình | Tên Mô Hình / Kiến Trúc | Mục Đích Sử Dụng | Vị Trí Lưu Trữ Weights / Cache |
| :--- | :--- | :--- | :--- |
| **1. Text Recognition** | **VietOCR (`vgg_transformer`)** | Nhận dạng chữ tiếng Việt quang học độ chính xác cao trên các dòng thông tin chủ, thửa đất, số sổ | `backend/weights/vgg_transformer.pth` (~151 MB) |
| **2. Text Detection** | **PaddleOCR (PP-OCRv4)** | Phát hiện bounding box các khối chữ trên từng trang sổ | `~/.paddleocr/` (Host) hoặc `/root/.paddleocr` (Docker volume `ocr_paddle_cache`) |
| **3. Cadastral Reasoning** | **Qwen3-8B / Qwen2.5-7B** (qua Ollama) | Suy luận pháp lý, phân tích biến động Trang 4 (chuyển nhượng, tặng cho, thừa kế, đính chính) | Lưu trữ bởi Ollama (`~/.ollama/models`) |

---

## 1. Mô Hình VietOCR (Transformer)

### 1.1. Vị trí đặt file weights
Hệ thống ưu tiên tìm kiếm file weights theo thứ tự:
```
backend/weights/vgg_transformer.pth
weights/vgg_transformer.pth
```

### 1.2. Cách tải weights thủ công (Offline / On-premise)
Nếu máy chủ không có internet hoặc tải tự động bị lỗi mạng (Google Drive quota limit / SSL error):

1. **Tải file weights `vgg_transformer.pth` (151 MB):**
   - **Link chính thức VietOCR (Google Drive):** [vgg_transformer.pth](https://drive.google.com/uc?id=13327Y1tz1ohsm5YzspXWIHThB0dlHKI6)
   - **Link dự phòng (VOCR CDN):** `https://vocr.vn/data/vietocr/vgg_transformer.pth`
2. **Copy file vào thư mục dự án:**
   ```powershell
   # Tạo thư mục weights nếu chưa có
   New-Item -ItemType Directory -Force -Path "backend/weights"

   # Đặt file vào backend/weights/vgg_transformer.pth
   Copy-Item "C:\duong_dan_tai\vgg_transformer.pth" -Destination "backend/weights/vgg_transformer.pth"
   ```

### 1.3. Cấu hình file `vgg_transformer_config.json`
Tệp cấu hình đã được đặt sẵn tại `backend/configs/vgg_transformer_config.json`. Khi khởi tạo, hệ thống đọc trực tiếp cấu hình này mà không cần truy vấn tải config từ mạng.

### 1.4. Tùy chọn sử dụng mô hình khác (`vgg_seq2seq`)
Nếu muốn dùng mô hình nhẹ hơn cho CPU yếu:
1. Tải weights `vgg_seq2seq.pth`: [Link Google Drive](https://drive.google.com/uc?id=1nTKlEog9YFK74PT30mwRstWroO3XZ0bm)
2. Đặt vào `backend/weights/vgg_seq2seq.pth`.
3. Khởi tạo `VietOCRRecognizer(model_name='vgg_seq2seq')`.

---

## 2. Mô Hình PaddleOCR (PP-OCRv4)

### 2.1. Cơ chế tải tự động
Khi chạy lần đầu tiên, thư viện `paddleocr` sẽ tự động tải các gói mô hình pre-trained về thư mục người dùng:
- **Windows:** `C:\Users\<Tên_User>\.paddleocr\whl\`
- **Linux:** `/home/<user>/.paddleocr/whl/`
- **Docker:** `/root/.paddleocr/` (đã được ánh xạ vào Docker Volume `ocr_sodo_paddle_cache` trong `docker-compose.yml`).

Các gói mô hình bao gồm:
- `ch_PP-OCRv4_det_infer.tar` (Phát hiện chữ tiếng Việt / chữ Hán)
- `ch_PP-OCRv4_rec_infer.tar` (Nhận diện chữ đa ngữ)
- `cls_infer.tar` (Phát hiện hướng chữ nghiêng / xoay 180 độ)

### 2.2. Đóng gói Offline cho máy chủ không có mạng
Để triển khai máy chủ không có internet:
1. Chạy thử 1 lần trên máy có mạng để PaddleOCR tự tải đủ mô hình.
2. Nén toàn bộ thư mục `C:\Users\<User>\.paddleocr` thành file `.zip`.
3. Sang máy chủ không mạng, giải nén vào đúng thư mục `~/.paddleocr`.
4. Khi chạy Docker, copy các thư mục giải nén vào volume `ocr_sodo_paddle_cache` hoặc mount thư mục host vào container:
   ```yaml
   volumes:
     - D:/PaddleModels:/root/.paddleocr:ro
   ```

---

## 3. Mô Hình LLM Suy Luận Biến Động Trang 4 (Qwen3-8B / Qwen2.5-7B)

Hệ thống sử dụng mô hình ngôn ngữ lớn chạy cục bộ qua **Ollama** để đọc hiểu các dòng ghi chú biến động phức tạp tại Trang 4 (Ví dụ: *"Chuyển nhượng cho ông Nguyễn Văn A và bà Trần Thị B theo HĐ số 123/2023..."*).

### 3.1. Cài đặt Ollama
1. **Windows:** Tải và cài đặt tại [https://ollama.com/download/windows](https://ollama.com/download/windows).
2. **Linux (Ubuntu/Debian):**
   ```bash
   curl -fsSL https://ollama.com/install.sh | sh
   ```
3. Khởi chạy Ollama service:
   ```bash
   ollama serve
   ```

### 3.2. Tải mô hình Qwen về máy
Mở Terminal / PowerShell và chạy lệnh sau để tải weights mô hình:

```bash
# Lựa chọn 1 (Khuyến nghị cho GPU RTX 4060/4070/5070 - VRAM >= 8GB):
ollama run qwen3:8b

# Lựa chọn 2 (Mô hình rất ổn định, tương thích cao):
ollama run qwen2.5:7b

# Lựa chọn 3 (Cho máy cấu hình nhẹ, CPU-only hoặc VRAM 4GB-6GB):
ollama run qwen2.5:3b
```

Sau khi tải xong, kiểm tra danh sách mô hình đã sẵn sàng:
```bash
ollama list
```
Kết quả hiển thị tương tự:
```
NAME               ID              SIZE      MODIFIED
qwen3:8b           a2e1d51a24d8    4.9 GB    2 hours ago
qwen2.5:7b         845dbda0ea48    4.7 GB    1 day ago
```

### 3.3. Cấu hình kết nối Ollama với Hệ thống OCR
Mở file `.env` tại thư mục gốc của dự án:

```ini
# Đường dẫn kết nối Ollama API:
# - Nếu chạy backend trực tiếp bằng Python trên Windows:
OLLAMA_URL=http://localhost:11434

# - Nếu backend chạy trong Docker (Docker kết nối ngược ra máy chủ Host):
OLLAMA_URL=http://host.docker.internal:11434

# Tên mô hình đã tải ở bước 3.2:
LLM_MODEL_NAME=qwen3:8b

# Thời gian chờ phản hồi tối đa (giây):
OCR_OLLAMA_TIMEOUT=90
```

> 💡 **Mẹo:** Nếu chưa cài Ollama hoặc chưa tải model Qwen, hệ thống sẽ **tự động fallback sang bộ bóc tách Rule-based / Regex** (`mutation_extractor.py`), đảm bảo quy trình OCR vẫn chạy thông suốt không bị gián đoạn.

---

## 4. Kiểm Tra Toàn Diện Các Model Sau Khi Tải

Sau khi chuẩn bị xong các weights, chạy lệnh test đơn vị để xác nhận hệ thống nạp model thành công:

```powershell
# Kích hoạt môi trường ảo
.venv\Scripts\activate

# Chạy test kiểm tra rules và validators
pytest backend/tests/unit/test_domain_rules.py -v
```

Nếu console báo `PASSED` và không có lỗi thiếu weights, hệ thống đã sẵn sàng 100% để vận hành!
