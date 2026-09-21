"""
FastAPI application chính của backend ocr-so-do.
"""
from pathlib import Path
import os
from dotenv import load_dotenv

project_root = Path(__file__).resolve().parents[5]
load_dotenv(project_root / ".env")

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

from .routers import admin, auth, documents, exports, batch, pg_storage, batch_pairs, projects
from .security import (
    authenticate_authorization_header,
    required_permission_for_request,
)


def _allowed_origins() -> list[str]:
    raw = os.getenv("OCR_ALLOWED_ORIGINS", "").strip()
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


class AuthenticationMiddleware(BaseHTTPMiddleware):
    """Chặn toàn bộ API/artifact trước khi router xử lý request.

    Router vẫn dùng `require_permission` ở những API quản trị để giữ rõ hợp
    đồng quyền tại điểm nhạy cảm. Middleware giúp tránh sót endpoint cũ.
    """

    async def dispatch(self, request: Request, call_next):
        if request.method == "OPTIONS":
            return await call_next(request)

        required = required_permission_for_request(request.method, request.url.path)
        if required is None:
            return await call_next(request)
        try:
            principal = authenticate_authorization_header(request.headers.get("Authorization"))
            if required != "authenticated" and required not in principal.permissions:
                return JSONResponse(
                    status_code=403,
                    content={"detail": "Tài khoản không có quyền thực hiện thao tác này."},
                )
            request.state.principal = principal
        except Exception as exc:
            status_code = getattr(exc, "status_code", 401)
            detail = getattr(exc, "detail", "Không thể xác thực phiên đăng nhập.")
            headers = getattr(exc, "headers", None)
            return JSONResponse(status_code=status_code, content={"detail": detail}, headers=headers)
        return await call_next(request)


expose_docs = os.getenv("OCR_EXPOSE_API_DOCS", "false").strip().lower() in {"1", "true", "yes", "on"}

app = FastAPI(
    title="OCR Sổ Đỏ / Sổ Hồng - Backend Production",
    description="Hệ thống bóc tách dữ liệu địa chính và xuất bảng chuẩn 129 cột",
    version="2.0.0",
    docs_url="/docs" if expose_docs else None,
    redoc_url="/redoc" if expose_docs else None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins(),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["Authorization", "Content-Type"],
)
app.add_middleware(AuthenticationMiddleware)

# Đăng ký các router phiên bản v1
api_v1_prefix = "/api/v1"
app.include_router(documents.router, prefix=api_v1_prefix)
app.include_router(exports.router, prefix=api_v1_prefix)
app.include_router(batch.router, prefix=api_v1_prefix)
app.include_router(pg_storage.router, prefix=api_v1_prefix)
app.include_router(batch_pairs.router, prefix=api_v1_prefix)
app.include_router(auth.router, prefix=api_v1_prefix)
app.include_router(admin.router, prefix=api_v1_prefix)
app.include_router(projects.router, prefix=api_v1_prefix)

# Ảnh trang gốc, crop OCR và sơ đồ thửa đất là bằng chứng trực quan trong màn
# tra soát. AuthenticationMiddleware bắt buộc `record.read` cho mọi URL /output.
project_root = Path(__file__).resolve().parents[5]
output_dir = project_root / "output"
output_dir.mkdir(parents=True, exist_ok=True)
app.mount("/output", StaticFiles(directory=str(output_dir)), name="output")


@app.get("/health", tags=["System"])
async def health():
    return {
        "status": "ok",
        "healthy": True,
        "version": "2.0.0",
        "service": "ocr-so-do-backend"
    }
