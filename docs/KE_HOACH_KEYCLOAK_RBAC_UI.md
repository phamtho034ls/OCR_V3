# Kế hoạch triển khai Keycloak, phân quyền và UI

## Mục tiêu đã triển khai

- Keycloak là nguồn danh tính duy nhất; tài khoản không tồn tại trong mã OCR hay
  trong một bảng password riêng.
- Quản trị viên OCR tạo nhân viên, cấp/thu hồi role, khóa/mở tài khoản tại UI.
- Mọi API và artifact OCR yêu cầu JWT được Keycloak ký. UI không phải lớp bảo vệ.
- Tên người tra soát lấy từ JWT, không nhận từ dữ liệu người dùng gửi lên.

## Role và quyền

| Role Keycloak | Nghiệp vụ |
| --- | --- |
| `ocr-admin` | Toàn quyền; tạo/khóa tài khoản, gán role, xóa dữ liệu, xuất thô. |
| `ocr-truongphong` | Tạo dự án; quản lý thành viên và toàn bộ dữ liệu trong dự án mình tham gia. |
| `ocr-member` | Upload/quét trong dự án được giao; chỉ xem dữ liệu do chính mình tạo. |

Mã quyền backend là `document.create`, `batch.create`, `batch.read`,
`batch.cancel`, `record.read`, `record.review`, `record.delete`, `export.129`,
`export.raw`, `user.manage`, `audit.read`.

## Thành phần đã thêm

1. `security.py` xác minh JWT qua JWKS, kiểm tra issuer/audience và chặn endpoint theo permission.
2. `keycloak_admin.py` gọi Admin API bằng service account chỉ có `manage-users`,
   `query-users`, `view-users`.
3. `/api/v1/admin/*` cho UI quản trị nhân viên; `/api/v1/auth/me` trả role/quyền
   đã tính từ token.
4. `UserManagementPage` cho tạo tài khoản, gán nhiều role và khóa/mở tài khoản.
5. Docker Compose khởi chạy Keycloak + PostgreSQL riêng, import realm/role/client
   và tài khoản OCR admin đầu tiên.

## Kế hoạch tiếp theo trước khi triển khai đa đơn vị

1. Hoàn thiện workflow `assigned_to`, xóa mềm và audit append-only; batch/hồ sơ
   hiện đã có `project_id` + `created_by` và mọi truy vấn dữ liệu được lọc theo scope dự án.
2. Lưu audit event append-only cho tạo/xóa/export/cấp quyền và giữ lại trước/sau
   (không đưa full CCCD vào log).
3. URL artifact tĩnh hiện đã kiểm tra scope theo `document_id`/`batch_id`; có thể
   đổi thành endpoint riêng nếu cần chính sách cache hoặc audit tải file chi tiết.
4. Chuyển trạng thái batch đang chạy khỏi RAM để có khả năng khôi phục sau restart.
5. Mở rộng test 401/403 và E2E cho 3 realm role kết hợp hai mức role dự án.

## Cài đặt lần đầu

1. Sao chép `.env.example` thành `.env` và thay tất cả mật khẩu/secret mẫu.
2. Đặt `OCR_ALLOWED_SOURCE_ROOTS` là thư mục nguồn được phép quét.
3. Chạy `docker compose up --build`.
4. Đăng nhập ứng dụng bằng `OCR_INITIAL_ADMIN_USERNAME`; Keycloak bắt đổi mật
   khẩu tạm. Từ tab **Tài khoản & quyền**, tạo nhân viên và gán role.

Realm import chỉ diễn ra khi realm chưa tồn tại. Nếu cần import lại cấu hình ở
môi trường thử nghiệm, dùng volume Keycloak mới thay vì xóa dữ liệu production.
