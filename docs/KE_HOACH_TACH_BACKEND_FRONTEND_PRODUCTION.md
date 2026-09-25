# Kế hoạch tái cấu trúc hệ thống OCR theo mô hình Backend/Frontend Production

## 1. Mục tiêu

Tái cấu trúc hệ thống OCR Giấy chứng nhận quyền sử dụng đất thành hai ứng dụng độc lập:

- **Backend** chịu trách nhiệm xử lý ảnh/PDF, OCR, crop, rule/regex, trích xuất dữ liệu, kiểm tra nghiệp vụ, quản lý job và xuất file.
- **Frontend** chịu trách nhiệm giao diện, upload tài liệu, theo dõi tiến độ, hiển thị kết quả, review dữ liệu và yêu cầu xuất báo cáo.

Việc chuyển đổi phải được thực hiện tăng dần, giữ tương thích với kết quả OCR hiện tại và tránh viết lại đồng loạt các parser/rule đã được kiểm chứng.

## 2. Kết quả cần đạt

Sau khi hoàn thành:

1. API, CLI và worker dùng chung một `ProcessDocumentUseCase`, không import logic từ web layer.
2. Pipeline OCR có hợp đồng dữ liệu rõ ràng từ detection đến kết quả cuối.
3. Ảnh crop được đưa trực tiếp vào recognizer trong bộ nhớ; việc lưu crop chỉ là chế độ artifact/debug.
4. `Border Token Pruning` thực sự cung cấp dữ liệu sạch cho parser nhưng vẫn bảo toàn text OCR gốc.
5. Regex/rule không còn nằm trong API hoặc Excel mapper.
6. Backend không phụ thuộc vào frontend và frontend không chứa rule nghiệp vụ OCR.
7. Batch job có trạng thái bền vững, không mất khi API restart.
8. Có cấu hình môi trường, logging, metrics, test và quy trình deployment tái lập được.

## 3. Kiến trúc tổng thể mục tiêu

```text
Browser
   |
   | HTTPS / JSON / Multipart / SSE
   v
Frontend (React + TypeScript)
   |
   | /api/v1/*
   v
Backend API (FastAPI)
   |
   +--> Application Use Cases
   |        |
   |        +--> Domain models/rules
   |        +--> OCR pipeline ports
   |
   +--> Job Queue --> OCR Worker --> PaddleOCR / VietOCR / OpenCV
   |
   +--> Database / Redis / Artifact Storage
```

Chiều phụ thuộc bắt buộc:

```text
interfaces -> application -> domain
                    ^
                    |
             infrastructure
```

- `domain` không import FastAPI, OpenCV, PaddleOCR, VietOCR, pandas hoặc openpyxl.
- `application` không biết HTTP route hay giao diện web.
- `infrastructure` triển khai các port do application khai báo.
- `interfaces` chỉ chuyển request thành command và chuyển result thành response.

## 4. Cấu trúc repository đề xuất

```text
ocr-so-do/
├── backend/
│   ├── pyproject.toml
│   ├── uv.lock
│   ├── src/
│   │   └── ocr_so_do/
│   │       ├── domain/
│   │       ├── application/
│   │       ├── infrastructure/
│   │       ├── interfaces/
│   │       ├── config/
│   │       └── bootstrap.py
│   ├── tests/
│   ├── migrations/
│   └── Dockerfile
│
├── frontend/
│   ├── package.json
│   ├── package-lock.json
│   ├── vite.config.ts
│   ├── tsconfig.json
│   ├── src/
│   │   ├── app/
│   │   ├── pages/
│   │   ├── features/
│   │   ├── entities/
│   │   └── shared/
│   ├── tests/
│   └── Dockerfile
│
├── configs/
│   ├── templates/
│   ├── rules/
│   ├── mappings/
│   └── profiles/
│
├── deployments/
│   ├── docker-compose.yml
│   ├── nginx/
│   └── environments/
│
├── tools/
├── experiments/
├── docs/
└── README.md
```

Không đặt `output`, model weights, dữ liệu khách hàng hoặc `.venv` bên trong source package. Các thư mục này phải được cấu hình qua biến môi trường hoặc volume khi triển khai.

---

# Phần A — Kế hoạch Backend

## 5. Cấu trúc Backend chi tiết

```text
backend/src/ocr_so_do/
├── domain/
│   ├── models/
│   │   ├── bounding_box.py
│   │   ├── ocr_token.py
│   │   ├── field_candidate.py
│   │   ├── field_result.py
│   │   ├── document.py
│   │   ├── gcn.py
│   │   └── job.py
│   ├── enums/
│   │   ├── document_type.py
│   │   ├── page_role.py
│   │   ├── field_status.py
│   │   └── ocr_engine.py
│   ├── rules/
│   │   ├── owner/
│   │   ├── parcel/
│   │   ├── certification/
│   │   ├── transfer/
│   │   ├── land_assets/
│   │   └── validation/
│   └── errors.py
│
├── application/
│   ├── pipeline/
│   │   ├── orchestrator.py
│   │   ├── context.py
│   │   ├── stage.py
│   │   └── stages/
│   │       ├── ingest.py
│   │       ├── preprocess.py
│   │       ├── classify.py
│   │       ├── detect.py
│   │       ├── crop.py
│   │       ├── recognize.py
│   │       ├── prune.py
│   │       ├── extract.py
│   │       ├── merge.py
│   │       ├── normalize.py
│   │       └── validate.py
│   ├── use_cases/
│   │   ├── process_document.py
│   │   ├── process_batch.py
│   │   ├── process_gcn_cccd_pair.py
│   │   ├── review_document.py
│   │   └── export_document.py
│   ├── projections/
│   │   ├── gcn_29_fields.py
│   │   ├── excel_129_columns.py
│   │   └── ke_hoach_515.py
│   └── ports/
│       ├── detector.py
│       ├── recognizer.py
│       ├── artifact_store.py
│       ├── job_queue.py
│       ├── job_repository.py
│       └── document_repository.py
│
├── infrastructure/
│   ├── imaging/
│   │   ├── opencv_cropper.py
│   │   ├── deskew.py
│   │   ├── orientation.py
│   │   ├── color_profile.py
│   │   └── pdf_loader.py
│   ├── ocr/
│   │   ├── paddle_detector.py
│   │   ├── vietocr_recognizer.py
│   │   └── model_registry.py
│   ├── persistence/
│   │   ├── sqlalchemy_job_repository.py
│   │   ├── sqlalchemy_document_repository.py
│   │   └── filesystem_artifact_store.py
│   ├── queue/
│   │   ├── redis_queue.py
│   │   └── worker_runtime.py
│   ├── exporters/
│   │   ├── excel_exporter.py
│   │   ├── json_exporter.py
│   │   └── markdown_exporter.py
│   └── observability/
│       ├── logging.py
│       ├── metrics.py
│       └── tracing.py
│
├── interfaces/
│   ├── api/
│   │   ├── app.py
│   │   ├── dependencies.py
│   │   ├── error_handlers.py
│   │   ├── middleware/
│   │   ├── schemas/
│   │   │   ├── documents.py
│   │   │   ├── jobs.py
│   │   │   ├── reviews.py
│   │   │   └── exports.py
│   │   └── routers/
│   │       ├── health.py
│   │       ├── documents.py
│   │       ├── jobs.py
│   │       ├── reviews.py
│   │       └── exports.py
│   ├── cli/
│   │   └── main.py
│   └── worker/
│       └── main.py
│
├── config/
│   ├── settings.py
│   ├── rule_loader.py
│   └── template_loader.py
└── bootstrap.py
```

## 6. Hợp đồng dữ liệu OCR chuẩn

Không truyền `Dict[str, Any]` tự do giữa các bước. Dùng model typed, có version.

### 6.1. OCR token

```python
class OCRToken:
    token_id: str
    page_index: int
    bbox_original: BoundingBox
    bbox_padded: BoundingBox | None
    paddle_text: str | None
    paddle_confidence: float | None
    vietocr_text: str | None
    vietocr_confidence: float | None
    selected_raw_text: str
    clean_text: str
    removed_border_tokens: list[str]
    selected_engine: OCREngine
    confidence: float
```

### 6.2. Field result

```python
class FieldResult:
    field_name: str
    raw_text: str | None
    normalized_value: str | float | int | None
    status: FieldStatus
    is_valid: bool
    confidence: float
    page_index: int | None
    token_ids: list[str]
    bbox: BoundingBox | None
    rule_ids: list[str]
    selection_reason: str | None
    error_reason: str | None
```

`status` phải là enum: `valid`, `review_required`, `missing`, `not_applicable`. Không cho phép trạng thái `valid` khi cả raw và normalized value đều rỗng.

## 7. Thiết kế lại Crop và Bounding Box Padding

### 7.1. Luồng xử lý

```text
Detected box
  -> normalize polygon order
  -> classify box type
  -> calculate padding policy
  -> clip padded polygon to page boundary
  -> crop/rectify in memory
  -> recognize crop
  -> optionally persist artifact
```

### 7.2. Padding policy

Tạo interface `PaddingPolicy` và các profile:

- `default_text`: padding theo chiều cao dòng.
- `identity_number`: ưu tiên padding ngang để tránh mất chữ số đầu/cuối.
- `serial_number`: giữ tiền tố chữ và đủ 6–8 chữ số.
- `barcode_number`: mở rộng ngang theo vị trí barcode.
- `area_value`: giữ cả số và đơn vị diện tích để validator đối chiếu.

Padding phải tính theo tỉ lệ kích thước box/trang và có giới hạn min/max trong config. Không hardcode trực tiếp trong API.

### 7.3. Artifact mode

- Mặc định recognizer nhận crop trực tiếp từ memory.
- `ArtifactStore` chỉ lưu crop khi bật `OCR_SAVE_CROPS=true`, khi cần review hoặc khi confidence thấp.
- Metadata lưu checksum, kích thước crop, bbox gốc và bbox đã padding.
- Có retention policy tự động xóa artifact chứa dữ liệu cá nhân.

## 8. Thiết kế lại Border Token Pruning

Áp dụng hai tầng:

1. **Generic pruning** sau recognition: chỉ xóa noise chắc chắn, marker đầu dòng và dấu câu thừa.
2. **Field-aware pruning** sau khi parser xác định field: xử lý label, đơn vị hoặc tiền tố riêng của `so_thua`, `to_ban_do`, `dien_tich`, `cccd`, `serial`.

Quy tắc bắt buộc:

- Không ghi đè `selected_raw_text`.
- Parser đọc `clean_text`.
- Mỗi thay đổi ghi `rule_id` và `removed_tokens` để audit.
- Nếu PaddleOCR và VietOCR bất đồng mạnh, giữ cả hai candidate và đẩy review thay vì xóa không thể truy vết.

## 9. Quản lý Regex và Rule

Regex chỉ được phép xuất hiện trong các module sau:

- `domain/rules/<domain>/patterns.py`.
- `domain/rules/<domain>/parser.py`.
- `domain/rules/validation/`.

Không đặt regex tại:

- FastAPI router.
- Pipeline orchestrator.
- Excel exporter/mapper.
- Frontend.

Mỗi regex quan trọng cần có:

```text
rule_id
version
domain
description
positive_examples
negative_examples
applicable_templates
```

Rule sửa lỗi OCR theo địa phương phải nằm trong profile cấu hình, ví dụ:

```text
configs/profiles/vinh_yen_v1.yaml
configs/profiles/gia_vien_v1.yaml
```

Không đưa tên xã/huyện cụ thể trực tiếp vào Excel mapper.

## 10. API Backend đề xuất

Toàn bộ API được version hóa dưới `/api/v1`.

### 10.1. Document và job

```text
POST   /api/v1/documents
GET    /api/v1/documents/{document_id}
GET    /api/v1/documents/{document_id}/result
GET    /api/v1/documents/{document_id}/tokens
GET    /api/v1/documents/{document_id}/artifacts

POST   /api/v1/jobs
GET    /api/v1/jobs/{job_id}
GET    /api/v1/jobs/{job_id}/events
POST   /api/v1/jobs/{job_id}/cancel
```

Upload trả `202 Accepted` cùng `job_id`. Frontend nhận tiến độ qua SSE hoặc polling có backoff.

### 10.2. Review

```text
GET    /api/v1/reviews
GET    /api/v1/reviews/{review_id}
PATCH  /api/v1/reviews/{review_id}/fields/{field_name}
POST   /api/v1/reviews/{review_id}/approve
POST   /api/v1/reviews/{review_id}/reject
```

Không dùng `DELETE` để biểu diễn hành động “đã review”.

### 10.3. Export

```text
POST   /api/v1/exports
GET    /api/v1/exports/{export_id}
GET    /api/v1/exports/{export_id}/download
```

Frontend gửi `document_ids`, `format` và `mapping_profile`; không gửi tùy ý 129 cột đã xử lý từ trình duyệt.

### 10.4. Directory scan

Không nhận raw path tùy ý từ client public. Có hai lựa chọn:

- Upload file/thư mục qua API.
- Admin chọn một `data_source_id` đã được cấu hình và allowlist phía server.

## 11. Batch, concurrency và model lifecycle

- FastAPI chỉ tiếp nhận request và tạo job.
- OCR chạy trong worker process riêng.
- Mỗi GPU có giới hạn worker/semaphore phù hợp.
- Model được load một lần trong worker lifecycle, không load theo request.
- Job state lưu trong database/Redis, không lưu bằng global dictionary.
- Mỗi stage ghi thời gian, lỗi và số lượng token để quan sát hiệu năng.
- Retry chỉ áp dụng cho lỗi kỹ thuật; lỗi dữ liệu được chuyển sang review.

## 12. Bảo mật Backend

- Authentication và role: `operator`, `reviewer`, `admin`.
- CORS allowlist theo môi trường.
- Giới hạn kích thước upload, số trang và số file mỗi batch.
- Kiểm tra MIME dựa trên nội dung, không chỉ extension.
- Resolve path và xác nhận containment trước khi đọc/trả file.
- Không đưa đường dẫn filesystem nội bộ vào response.
- Log phải che CCCD/CMND, mã vạch và tên người dùng khi không cần thiết.
- Artifact download dùng ID hoặc signed URL có thời hạn.
- Có retention policy cho PDF, crop, JSON và Excel chứa PII.
- Không tải model/config runtime qua kết nối bỏ kiểm tra TLS.

## 13. Test Backend

```text
backend/tests/
├── unit/
│   ├── domain/
│   ├── rules/
│   ├── crop/
│   └── pruning/
├── contract/
│   ├── detector_contract.py
│   ├── recognizer_contract.py
│   └── pipeline_stage_contract.py
├── integration/
│   ├── pipeline/
│   ├── persistence/
│   └── exporters/
├── api/
└── golden/
    ├── mau_a/
    ├── mau_b/
    ├── vinh_yen/
    └── ke_hoach_515/
```

Unit test không được load model OCR. Integration model và E2E phải có marker riêng để CI có thể chạy theo tầng.

---

# Phần B — Kế hoạch Frontend

## 14. Công nghệ Frontend đề xuất

- React.
- TypeScript strict mode.
- Vite.
- React Router.
- TanStack Query cho server state, polling và cache.
- Zustand hoặc Context chỉ cho UI state nhỏ; không sao chép toàn bộ server state.
- Zod để kiểm tra dữ liệu response ở runtime nếu cần.
- Vitest + Testing Library.
- Playwright cho E2E.

## 15. Cấu trúc Frontend chi tiết

```text
frontend/src/
├── app/
│   ├── App.tsx
│   ├── router.tsx
│   ├── providers.tsx
│   ├── queryClient.ts
│   └── styles/
│
├── pages/
│   ├── dashboard/
│   ├── document-upload/
│   ├── document-result/
│   ├── batch-processing/
│   ├── review-queue/
│   ├── review-detail/
│   ├── data-conversion/
│   └── system-status/
│
├── features/
│   ├── upload-document/
│   ├── create-batch/
│   ├── monitor-job/
│   ├── inspect-bounding-box/
│   ├── inspect-crop/
│   ├── edit-field/
│   ├── approve-review/
│   ├── filter-results/
│   └── export-data/
│
├── entities/
│   ├── document/
│   ├── ocr-token/
│   ├── extracted-field/
│   ├── job/
│   ├── review/
│   └── export/
│
└── shared/
    ├── api/
    │   ├── client.ts
    │   ├── generated/
    │   └── errors.ts
    ├── config/
    ├── hooks/
    ├── lib/
    ├── types/
    └── ui/
        ├── button/
        ├── data-table/
        ├── dialog/
        ├── field-status/
        ├── image-canvas/
        └── progress/
```

Mỗi feature có thể chứa:

```text
feature-name/
├── api/
├── model/
├── ui/
├── lib/
└── index.ts
```

Không để toàn bộ logic trong một `app.js` hoặc một trang HTML lớn.

## 16. Ranh giới trách nhiệm Frontend

Frontend được phép:

- Kiểm tra định dạng và kích thước file trước upload để cải thiện UX.
- Gửi lệnh tạo job và theo dõi tiến độ.
- Hiển thị preview, bbox, crop và provenance.
- Cho phép người dùng sửa field và gửi patch về backend.
- Lọc, sắp xếp và phân trang dữ liệu đã trả về.
- Khởi tạo yêu cầu export và tải file hoàn chỉnh.

Frontend không được phép:

- Chạy regex để quyết định số thửa, CCCD, serial hoặc mã vạch.
- Tự sửa dữ liệu nghiệp vụ trước khi lưu.
- Tự mapping canonical model thành 129 cột production.
- Tự quyết định confidence hoặc `can_review`.
- Nhận hoặc hiển thị đường dẫn filesystem nội bộ của server.

## 17. Các màn hình chính

### 17.1. Upload tài liệu

- Drag/drop nhiều file.
- Hiển thị dung lượng, số file và lỗi định dạng.
- Chọn profile xử lý nếu người dùng có quyền.
- Sau upload chuyển đến trang job progress.

### 17.2. Job progress

- Trạng thái: queued, running, completed, failed, cancelled.
- Tiến độ theo file/trang/stage.
- Tự dừng polling khi job kết thúc hoặc component unmount.
- Retry có backoff, không polling cố định vô hạn.

### 17.3. Document result

- Preview ảnh theo trang.
- Canvas bbox tách khỏi DOM table.
- Bảng field hiển thị value, confidence, status, nguồn engine và trang.
- Cho phép chuyển giữa raw text và clean text.
- Crop gallery tải lazy, không tải toàn bộ ảnh khi mở trang.

### 17.4. Review

- Chỉ hiển thị field `review_required` theo mặc định.
- So sánh PaddleOCR, VietOCR, raw text, clean text và crop.
- Mọi chỉnh sửa gửi về backend và lưu audit history.
- Hành động approve/reject có trạng thái rõ ràng.

### 17.5. Chuyển đổi 129 cột

- Frontend hiển thị projection backend trả về.
- Hỗ trợ nhóm cột, ẩn/hiện và tìm kiếm.
- Không giữ toàn bộ file lớn trong memory nếu có thể dùng pagination/virtualization.
- Export được xử lý phía backend dưới dạng job.

## 18. API client và type safety

- Backend xuất OpenAPI schema.
- Frontend sinh TypeScript client/types từ OpenAPI trong CI.
- Không viết lại thủ công các interface OCR ở nhiều nơi.
- Chuẩn hóa một kiểu lỗi:

```typescript
type ApiError = {
  code: string;
  message: string;
  requestId: string;
  details?: Record<string, unknown>;
};
```

- Mọi request có timeout và hỗ trợ `AbortController`.
- Không tự retry các request mutation như approve hoặc export nếu chưa có idempotency key.

## 19. Test Frontend

```text
frontend/tests/
├── unit/
├── components/
├── integration/
└── e2e/
```

Các luồng E2E tối thiểu:

1. Upload một PDF và nhận `job_id`.
2. Theo dõi job đến khi hoàn tất.
3. Mở kết quả và chuyển trang preview.
4. Hiển thị bbox/crop đúng token.
5. Sửa field và approve review.
6. Tạo export 129 cột và tải file.
7. Hiển thị lỗi khi backend mất kết nối hoặc job thất bại.

---

# Phần C — Mapping code hiện tại sang cấu trúc mới

## 20. Bảng chuyển đổi module

| Code hiện tại | Vị trí mục tiêu | Ghi chú |
|---|---|---|
| `api/main.py:get_pipeline` | `backend/.../bootstrap.py` | Khởi tạo dependency/model theo lifecycle |
| `api/main.py:run_pipeline_on_image` | `application/pipeline/orchestrator.py` | Không phụ thuộc FastAPI |
| `api/main.py:get_perspective_crop` | `infrastructure/imaging/opencv_cropper.py` | Có `PaddingPolicy` |
| `preprocessing/*` | `infrastructure/imaging/*` | Triển khai các image stage |
| `detection/paddleocr_detect.py` | `infrastructure/ocr/paddle_detector.py` | Implement `DetectorPort` |
| `recognition/vietocr_recognize.py` | `infrastructure/ocr/vietocr_recognizer.py` | Implement `RecognizerPort` |
| `extraction/spatial_engine.py` | `domain/rules/spatial/` | Dùng bbox/token typed |
| `extraction/parsers/*` | `domain/rules/<domain>/` | Tách pattern/parser/normalizer |
| `extraction/validators.py` | `domain/rules/validation/` | Validator thuần, không I/O |
| `extraction/gcn_merger.py` | `application/pipeline/stages/merge.py` | Nhận field candidate typed |
| `extraction/border_token_pruner.py` | `application/pipeline/stages/prune.py` | Generic và field-aware pruning |
| `excel_chuyen_doi_mapper.py` | `application/projections/excel_129_columns.py` | Chỉ projection, không sửa lỗi OCR |
| `excel_template_exporter.py` | `infrastructure/exporters/excel_exporter.py` | Chỉ thao tác workbook |
| `process_cleardata_batch.py` | `application/use_cases/process_batch.py` | Worker gọi use case |
| `run.py` | `interfaces/cli/main.py` | CLI gọi application layer |
| `api/static/app.js` | `frontend/src/features` và `pages` | Tách theo chức năng |
| `api/static/index.html` | `frontend/index.html` + React pages | HTML chỉ còn shell |

## 21. Thành phần tạm thời cần tách khỏi production

- `run_e2e_30_samples.py`, `run_e2e_50_vinhyen.py` chuyển vào `experiments/e2e/`.
- `evaluation/` giữ thành package/tool độc lập, không import API layer.
- `scratch/` không được đóng gói hoặc deploy.
- Endpoint riêng cho dữ liệu mẫu Vĩnh Yên chuyển sang development fixture hoặc admin tool.
- `output/`, `outputs/`, CSV/XLSX kết quả không nằm trong source tree production.

---

# Phần D — Lộ trình triển khai

## 22. Giai đoạn 0: Đóng băng baseline

- Commit riêng toàn bộ thay đổi đang có.
- Lưu output chuẩn cho bộ 30/50 mẫu và các mẫu A/B quan trọng.
- Ghi metric baseline theo từng field: precision, recall, exact match và review rate.
- Chốt canonical schema, tên field và alias legacy.
- Đánh version `current-v1` cho rule hiện tại.

Điều kiện hoàn thành: có thể chạy lại baseline và so sánh tự động sau mỗi thay đổi.

## 23. Giai đoạn 1: Tạo khung Backend/Frontend

- Tạo `backend/`, `frontend/`, `deployments/`.
- Tạo `pyproject.toml`, lockfile và package `src/ocr_so_do`.
- Tạo frontend React/TypeScript/Vite.
- Giữ API cũ hoạt động trong thời gian migration.
- Thiết lập CI cho lint, type-check và unit test.

Điều kiện hoàn thành: backend/frontend build độc lập và health check chạy được.

## 24. Giai đoạn 2: Tách crop, recognition và pruning

- Di chuyển crop/padding khỏi `api/main.py`.
- Tạo `OCRToken` và `CropResult` typed.
- Recognition chạy trực tiếp trên crop trong memory.
- Nối `clean_text` vào Spatial Engine/parser.
- Lưu raw text và audit pruning đầy đủ.
- Thêm golden tests cho các lỗi mất chữ đầu/cuối crop.

Điều kiện hoàn thành: kết quả không thấp hơn baseline và không còn disk round-trip bắt buộc.

## 25. Giai đoạn 3: Tách application pipeline

- Tạo `ProcessDocumentUseCase`.
- Chuyển orchestration ra khỏi FastAPI.
- CLI, API và E2E cùng gọi một use case.
- Loại bỏ pipeline dictionary dùng string key.
- Sửa provenance để truyền `field_name` rõ ràng, không suy ra từ lambda.

Điều kiện hoàn thành: `interfaces` có thể được thay thế mà pipeline vẫn chạy bằng unit/integration test.

## 26. Giai đoạn 4: Chuẩn hóa rule và schema

- Chuyển toàn bộ regex khỏi API/exporter.
- Tách rule chung và profile địa phương.
- Thống nhất `cccd`/`cmnd`, `nam_sinh`/`ngay_sinh`, `dien_tich`/`dien_tich_cap`.
- Version schema và cung cấp adapter legacy tạm thời.
- Mapper Excel chỉ nhận canonical `GCNDocument`.

Điều kiện hoàn thành: một field chỉ có một nguồn định nghĩa và một validator chính.

## 27. Giai đoạn 5: Job worker và persistence

- Thay global dictionary/queue bằng repository và job queue.
- Tách OCR worker khỏi API process.
- Thêm retry, cancellation, heartbeat và trạng thái tiến độ.
- Thêm artifact storage và retention.

Điều kiện hoàn thành: restart API không làm mất job/result; OCR nặng không block HTTP event loop.

## 28. Giai đoạn 6: Chuyển Frontend

- Tách upload, batch, review, crop gallery và conversion thành feature.
- Sinh API client từ OpenAPI.
- Chuyển từng màn hình khỏi `api/static/app.js`.
- Thêm virtual table/lazy image cho dữ liệu lớn.
- Sau khi đủ chức năng mới loại bỏ static UI cũ.

Điều kiện hoàn thành: frontend mới đáp ứng toàn bộ luồng nghiệp vụ hiện tại và vượt qua Playwright E2E.

## 29. Giai đoạn 7: Hardening và triển khai production

- Auth/RBAC, CORS allowlist, rate limit và upload limit.
- Container hóa API, worker, frontend, database và Redis.
- Health/readiness check riêng cho API và model worker.
- Structured logging, metrics, tracing và alert.
- Backup database và kiểm thử restore.
- Load test theo số trang, số crop và batch đồng thời.

Điều kiện hoàn thành: deployment tái lập được trên môi trường mới và có rollback.

---

# Phần E — Thứ tự ưu tiên thực hiện

## 30. P0 — Thực hiện trước

1. Đưa `pruned_text`/`clean_text` thực sự vào parser.
2. Tách crop/padding khỏi API và bỏ disk round-trip bắt buộc.
3. Sửa bước `processed` đang tạo ra nhưng không được dùng.
4. Sửa `pipeline["use_gpu"]` tại endpoint 515.
5. Chặn path traversal, raw server path và upload không giới hạn.
6. Commit/đóng băng baseline trước khi di chuyển module.

## 31. P1 — Thực hiện trong các giai đoạn tiếp theo

1. Canonical schema và provenance typed.
2. Tách pipeline application khỏi FastAPI.
3. Gom regex/rule và profile địa phương.
4. Worker queue, database và artifact store.
5. Tách frontend khỏi `api/static`.

## 32. P2 — Hoàn thiện vận hành

1. Observability và dashboard metrics.
2. Performance/load testing.
3. Autoscaling worker theo GPU/CPU.
4. Quy trình version/migration rule và schema.

---

# Phần F — Tiêu chí nghiệm thu chung

## 33. Functional

- Kết quả 29 field và projection 129 cột không thấp hơn baseline đã chốt.
- Raw OCR, clean text và normalized value được phân biệt rõ.
- Tất cả field có provenance đến page/token/bbox.
- Review sửa dữ liệu có audit history.
- Export sử dụng dữ liệu đã duyệt đúng version.

## 34. Technical

- Backend và frontend build/deploy độc lập.
- Không còn import từ backend API vào CLI, worker hoặc domain.
- Không còn regex nghiệp vụ trong API, frontend hoặc exporter.
- Không còn `Dict[str, Any]` tại ranh giới pipeline chính.
- Unit test không load OCR model.
- API response có schema và version.
- Job không mất khi restart API.

## 35. Security và vận hành

- Không đọc tùy ý đường dẫn trên server từ public request.
- Không trả đường dẫn filesystem nội bộ.
- Artifact PII có authentication và retention.
- Dependency được khóa phiên bản.
- Không bỏ kiểm tra TLS khi tải model/config.
- Có health, readiness, metrics, log có `request_id`/`job_id` và quy trình rollback.

## 36. Nguyên tắc migration

Trong toàn bộ quá trình:

- Không sửa rule và đổi kiến trúc trong cùng một commit lớn.
- Mỗi module di chuyển phải có adapter tương thích tạm thời.
- So sánh golden output sau từng bước.
- Chỉ xóa code cũ khi frontend, API, CLI và E2E đã chuyển hết sang đường mới.
- Các thay đổi làm giảm accuracy phải được rollback hoặc ghi rõ trade-off trước khi merge.
