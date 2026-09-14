"""
FastAPI application chính của backend ocr-so-do.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from .routers import documents, jobs, exports, batch, pg_storage

app = FastAPI(
    title="OCR Sổ Đỏ / Sổ Hồng - Backend Production",
    description="Hệ thống bóc tách dữ liệu địa chính và xuất bảng chuẩn 129 cột",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Đăng ký các router phiên bản v1
api_v1_prefix = "/api/v1"
app.include_router(documents.router, prefix=api_v1_prefix)
app.include_router(jobs.router, prefix=api_v1_prefix)
app.include_router(exports.router, prefix=api_v1_prefix)
app.include_router(batch.router, prefix=api_v1_prefix)
app.include_router(pg_storage.router, prefix=api_v1_prefix)


@app.get("/health", tags=["System"])
async def health():
    return {
        "status": "healthy",
        "version": "2.0.0",
        "service": "ocr-so-do-backend"
    }
