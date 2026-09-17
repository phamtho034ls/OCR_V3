"""
infrastructure/persistence/postgres_store.py
Quản lý kết nối và lưu trữ bền vững vào cơ sở dữ liệu PostgreSQL (PG).
Tự động tạo bảng ocr_batches và ocr_records, hỗ trợ lọc theo thư mục kết quả,
số lượng file, đường dẫn trên máy, và xóa có chọn lọc.
"""
import os
import json
import logging
import threading
import time
from typing import List, Dict, Any, Optional, Tuple
from contextlib import contextmanager

import psycopg2
from psycopg2 import pool
from psycopg2.extras import RealDictCursor, Json

logger = logging.getLogger(__name__)

# Cấu hình kết nối PostgreSQL từ biến môi trường hoặc giá trị mặc định đã xác định
PG_HOST = os.getenv("PG_HOST", "127.0.0.1")
PG_PORT = int(os.getenv("PG_PORT", "5433"))
PG_USER = os.getenv("PG_USER", "postgres")
PG_PASSWORD = os.getenv("PG_PASSWORD", "")
PG_DATABASE = os.getenv("PG_DATABASE", "ocr_so_do")
POSTGRES_ENABLED = os.getenv("OCR_POSTGRES_ENABLED", "true").strip().lower() not in {"0", "false", "no", "off"}
POSTGRES_RETRY_SECONDS = max(5, int(os.getenv("OCR_POSTGRES_RETRY_SECONDS", "60")))


class PostgresStore:
    """
    Quản lý lưu trữ PostgreSQL với connection pool đa luồng an toàn.
    """

    def __init__(
        self,
        host: str = PG_HOST,
        port: int = PG_PORT,
        user: str = PG_USER,
        password: str = PG_PASSWORD,
        database: str = PG_DATABASE,
        minconn: int = 1,
        maxconn: int = 10,
        enabled: bool = POSTGRES_ENABLED,
    ):
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.database = database
        self.enabled = enabled
        self._pool: Optional[pool.ThreadedConnectionPool] = None
        self._lock = threading.RLock()
        self._minconn = minconn
        self._maxconn = maxconn
        self._next_retry_at = 0.0
        self.unavailable_reason: Optional[str] = None
        if self.enabled:
            self._init_pool(minconn, maxconn)
            self._init_schema()
        else:
            self.unavailable_reason = "PostgreSQL đã được tắt bằng OCR_POSTGRES_ENABLED."
            logger.info("PostgreSQL bị tắt theo cấu hình; ứng dụng tiếp tục dùng kho SQLite cục bộ.")

    def _init_pool(self, minconn: int, maxconn: int) -> None:
        """Khởi tạo connection pool với cơ chế thử kết nối an toàn."""
        try:
            connect_kwargs = {
                "host": self.host,
                "port": self.port,
                "user": self.user,
                "dbname": self.database,
            }
            if self.password:
                connect_kwargs["password"] = self.password

            self._pool = pool.ThreadedConnectionPool(
                minconn=minconn,
                maxconn=maxconn,
                **connect_kwargs
            )
            logger.info(f"Đã kết nối PostgreSQL pool: {self.host}:{self.port}/{self.database}")
        except Exception as e:
            self.unavailable_reason = str(e)
            self._pool = None
            self._next_retry_at = time.monotonic() + POSTGRES_RETRY_SECONDS
            logger.warning(
                "PostgreSQL chưa sẵn sàng tại %s:%s; ứng dụng tiếp tục dùng SQLite. "
                "Sẽ thử kết nối lại sau %s giây. Chi tiết: %s",
                self.host,
                self.port,
                POSTGRES_RETRY_SECONDS,
                e,
            )

    def reconnect_if_due(self) -> bool:
        """Thử kết nối lại sau một khoảng chờ, không làm nghẽn luồng OCR khi DB tạm dừng."""
        if not self.enabled or time.monotonic() < self._next_retry_at:
            return False

        with self._lock:
            if self._pool:
                try:
                    self._pool.closeall()
                except Exception:
                    pass
                self._pool = None
            self._init_pool(self._minconn, self._maxconn)
            if self._pool:
                self.unavailable_reason = None
                self._init_schema()
                return True
        return False

    @contextmanager
    def get_connection(self):
        """Context manager mượn và trả kết nối về pool an toàn."""
        if not self._pool:
            raise ConnectionError("PostgreSQL pool chưa được khởi tạo thành công.")
        conn = self._pool.getconn()
        try:
            yield conn
        finally:
            if self._pool and conn:
                self._pool.putconn(conn)

    def is_connected(self) -> bool:
        """Kiểm tra trạng thái kết nối tới PostgreSQL."""
        if not self._pool:
            return False
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1;")
                    return cur.fetchone() is not None
        except Exception:
            return False

    def _init_schema(self) -> None:
        """Tự động tạo bảng ocr_batches và ocr_records nếu chưa có."""
        if not self._pool:
            return
        with self._lock:
            try:
                with self.get_connection() as conn:
                    with conn.cursor() as cur:
                        # 1. Bảng quản lý đợt quét / thư mục kết quả
                        cur.execute("""
                            CREATE TABLE IF NOT EXISTS ocr_batches (
                                batch_id VARCHAR(100) PRIMARY KEY,
                                folder_name VARCHAR(255) NOT NULL,
                                source_path TEXT,
                                output_dir TEXT,
                                total_files INT DEFAULT 0,
                                processed_count INT DEFAULT 0,
                                success_count INT DEFAULT 0,
                                error_count INT DEFAULT 0,
                                status VARCHAR(50) DEFAULT 'running',
                                created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                                updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                            );
                        """)

                        # 2. Bảng lưu trữ chi tiết từng hồ sơ
                        cur.execute("""
                            CREATE TABLE IF NOT EXISTS ocr_records (
                                id VARCHAR(150) PRIMARY KEY,
                                batch_id VARCHAR(100) REFERENCES ocr_batches(batch_id) ON DELETE CASCADE,
                                file_name VARCHAR(255) NOT NULL,
                                source_path TEXT,
                                source_folder TEXT,
                                folder_result VARCHAR(255),
                                template VARCHAR(50),
                                total_pages INT DEFAULT 1,
                                so_phat_hanh VARCHAR(100),
                                so_vao_so VARCHAR(100),
                                ma_vach VARCHAR(100),
                                ten_chu TEXT,
                                cmnd VARCHAR(50),
                                so_thua VARCHAR(50),
                                to_ban_do VARCHAR(50),
                                dien_tich VARCHAR(50),
                                dia_chi TEXT,
                                raw_markdown TEXT NOT NULL,
                                structured_data JSONB,
                                chuyen_doi_rows JSONB,
                                status VARCHAR(30) DEFAULT 'success',
                                elapsed_seconds REAL DEFAULT 0.0,
                                created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                            );
                        """)

                        # 3. Audit độc lập cho ảnh crop CCCD của luồng ghép cặp.
                        # Không dùng bảng này cho luồng OCR đơn lẻ để tránh thay đổi dữ liệu cũ.
                        cur.execute("""
                            CREATE TABLE IF NOT EXISTS cccd_crop_audits (
                                id BIGSERIAL PRIMARY KEY,
                                batch_id VARCHAR(100) NOT NULL REFERENCES ocr_batches(batch_id) ON DELETE CASCADE,
                                pair_id VARCHAR(255) NOT NULL,
                                crop_id VARCHAR(128) NOT NULL,
                                crop_path TEXT,
                                crop_url TEXT,
                                audit_status VARCHAR(32) NOT NULL,
                                audit_data JSONB NOT NULL,
                                created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                                updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                                UNIQUE (batch_id, pair_id, crop_id)
                            );
                        """)

                        # Index tối ưu hóa truy vấn và lọc
                        cur.execute("""
                            CREATE INDEX IF NOT EXISTS idx_ocr_batches_created ON ocr_batches(created_at DESC);
                            CREATE INDEX IF NOT EXISTS idx_ocr_records_batch ON ocr_records(batch_id);
                            CREATE INDEX IF NOT EXISTS idx_ocr_records_folder_result ON ocr_records(folder_result);
                            CREATE INDEX IF NOT EXISTS idx_ocr_records_source_folder ON ocr_records(source_folder);
                            CREATE INDEX IF NOT EXISTS idx_ocr_records_created ON ocr_records(created_at DESC);
                            CREATE INDEX IF NOT EXISTS idx_ocr_records_file_name ON ocr_records(file_name);
                            CREATE INDEX IF NOT EXISTS idx_cccd_crop_audits_batch ON cccd_crop_audits(batch_id);
                            CREATE INDEX IF NOT EXISTS idx_cccd_crop_audits_status ON cccd_crop_audits(audit_status);
                        """)
                        conn.commit()
                logger.info("Khởi tạo Schema PostgreSQL ocr_so_do thành công.")
            except Exception as e:
                logger.error(f"Lỗi khởi tạo schema PostgreSQL: {e}")

    # ─── QUẢN LÝ BATCH / FOLDER ───────────────────────────────────────────────

    def save_batch(
        self,
        batch_id: str,
        folder_name: str,
        source_path: str,
        output_dir: str,
        total_files: int = 0,
        status: str = "running",
    ) -> bool:
        """Tạo mới hoặc cập nhật một đợt quét / thư mục kết quả."""
        if not self._pool:
            return False
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO ocr_batches (
                            batch_id, folder_name, source_path, output_dir,
                            total_files, status, created_at, updated_at
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                        ON CONFLICT (batch_id) DO UPDATE SET
                            folder_name = EXCLUDED.folder_name,
                            source_path = EXCLUDED.source_path,
                            output_dir = EXCLUDED.output_dir,
                            total_files = EXCLUDED.total_files,
                            status = EXCLUDED.status,
                            updated_at = CURRENT_TIMESTAMP;
                    """, (batch_id, folder_name, source_path, output_dir, total_files, status))
                    conn.commit()
            return True
        except Exception as e:
            logger.error(f"Lỗi lưu batch vào PostgreSQL: {e}")
            return False

    def update_batch_progress(
        self,
        batch_id: str,
        processed_count: int,
        success_count: int,
        error_count: int,
        status: Optional[str] = None,
    ) -> bool:
        """Cập nhật tiến độ của một đợt quét."""
        if not self._pool:
            return False
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    if status:
                        cur.execute("""
                            UPDATE ocr_batches
                            SET processed_count = %s,
                                success_count = %s,
                                error_count = %s,
                                status = %s,
                                updated_at = CURRENT_TIMESTAMP
                            WHERE batch_id = %s;
                        """, (processed_count, success_count, error_count, status, batch_id))
                    else:
                        cur.execute("""
                            UPDATE ocr_batches
                            SET processed_count = %s,
                                success_count = %s,
                                error_count = %s,
                                updated_at = CURRENT_TIMESTAMP
                            WHERE batch_id = %s;
                        """, (processed_count, success_count, error_count, batch_id))
                    conn.commit()
            return True
        except Exception as e:
            logger.error(f"Lỗi cập nhật tiến độ batch PostgreSQL: {e}")
            return False

    def list_batches(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Lấy danh sách các thư mục kết quả / đợt quét."""
        if not self._pool:
            return []
        try:
            with self.get_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute("""
                        SELECT batch_id, folder_name, source_path, output_dir,
                               total_files, processed_count, success_count, error_count,
                               status, created_at, updated_at
                        FROM ocr_batches
                        ORDER BY created_at DESC
                        LIMIT %s;
                    """, (limit,))
                    rows = cur.fetchall()
                    result = []
                    for r in rows:
                        item = dict(r)
                        item["created_at"] = r["created_at"].strftime("%Y-%m-%d %H:%M:%S") if r.get("created_at") else ""
                        item["updated_at"] = r["updated_at"].strftime("%Y-%m-%d %H:%M:%S") if r.get("updated_at") else ""
                        result.append(item)
                    return result
        except Exception as e:
            logger.error(f"Lỗi truy vấn batches PostgreSQL: {e}")
            return []

    # ─── QUẢN LÝ BẢN GHI HỒ SƠ (OCR_RECORDS) ──────────────────────────────────

    def save_record(
        self,
        doc_id: str,
        file_name: str,
        raw_markdown: str,
        batch_id: Optional[str] = None,
        source_path: Optional[str] = None,
        source_folder: Optional[str] = None,
        folder_result: Optional[str] = None,
        template: Optional[str] = None,
        total_pages: int = 1,
        so_phat_hanh: Optional[str] = None,
        so_vao_so: Optional[str] = None,
        ma_vach: Optional[str] = None,
        ten_chu: Optional[str] = None,
        cmnd: Optional[str] = None,
        so_thua: Optional[str] = None,
        to_ban_do: Optional[str] = None,
        dien_tich: Optional[str] = None,
        dia_chi: Optional[str] = None,
        structured_data: Optional[Dict[str, Any]] = None,
        chuyen_doi_rows: Optional[List[Dict[str, Any]]] = None,
        status: str = "success",
        elapsed_seconds: float = 0.0,
    ) -> bool:
        """Lưu hoặc cập nhật một hồ sơ OCR vào PostgreSQL."""
        if not self._pool:
            return False
        try:
            # Tự động suy luận source_folder nếu có source_path
            if source_path and not source_folder:
                source_folder = str(os.path.dirname(source_path))

            # Đảm bảo batch_id tồn tại nếu được truyền vào
            if batch_id:
                self._ensure_batch_exists(batch_id, folder_result or batch_id, source_folder or "")

            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO ocr_records (
                            id, batch_id, file_name, source_path, source_folder, folder_result,
                            template, total_pages, so_phat_hanh, so_vao_so, ma_vach,
                            ten_chu, cmnd, so_thua, to_ban_do, dien_tich, dia_chi,
                            raw_markdown, structured_data, chuyen_doi_rows, status,
                            elapsed_seconds, created_at
                        )
                        VALUES (
                            %s, %s, %s, %s, %s, %s,
                            %s, %s, %s, %s, %s,
                            %s, %s, %s, %s, %s, %s,
                            %s, %s, %s, %s,
                            %s, CURRENT_TIMESTAMP
                        )
                        ON CONFLICT (id) DO UPDATE SET
                            batch_id = EXCLUDED.batch_id,
                            file_name = EXCLUDED.file_name,
                            source_path = EXCLUDED.source_path,
                            source_folder = EXCLUDED.source_folder,
                            folder_result = EXCLUDED.folder_result,
                            template = EXCLUDED.template,
                            total_pages = EXCLUDED.total_pages,
                            so_phat_hanh = EXCLUDED.so_phat_hanh,
                            so_vao_so = EXCLUDED.so_vao_so,
                            ma_vach = EXCLUDED.ma_vach,
                            ten_chu = EXCLUDED.ten_chu,
                            cmnd = EXCLUDED.cmnd,
                            so_thua = EXCLUDED.so_thua,
                            to_ban_do = EXCLUDED.to_ban_do,
                            dien_tich = EXCLUDED.dien_tich,
                            dia_chi = EXCLUDED.dia_chi,
                            raw_markdown = EXCLUDED.raw_markdown,
                            structured_data = EXCLUDED.structured_data,
                            chuyen_doi_rows = EXCLUDED.chuyen_doi_rows,
                            status = EXCLUDED.status,
                            elapsed_seconds = EXCLUDED.elapsed_seconds,
                            created_at = CURRENT_TIMESTAMP;
                    """, (
                        doc_id, batch_id, file_name, source_path, source_folder, folder_result,
                        template, total_pages, so_phat_hanh, so_vao_so, ma_vach,
                        ten_chu, cmnd, so_thua, to_ban_do, dien_tich, dia_chi,
                        raw_markdown,
                        Json(structured_data) if structured_data else None,
                        Json(chuyen_doi_rows) if chuyen_doi_rows else None,
                        status, elapsed_seconds
                    ))
                    conn.commit()
            return True
        except Exception as e:
            logger.error(f"Lỗi lưu ocr_record vào PostgreSQL: {e}")
            return False

    def _ensure_batch_exists(self, batch_id: str, folder_name: str, source_path: str):
        """Đảm bảo bản ghi batch_id đã có trong ocr_batches để không vi phạm khóa ngoại."""
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1 FROM ocr_batches WHERE batch_id = %s;", (batch_id,))
                    if not cur.fetchone():
                        cur.execute("""
                            INSERT INTO ocr_batches (batch_id, folder_name, source_path, output_dir, total_files, status)
                            VALUES (%s, %s, %s, %s, 1, 'running')
                            ON CONFLICT (batch_id) DO NOTHING;
                        """, (batch_id, folder_name, source_path, f"output/batches/{batch_id}"))
                        conn.commit()
        except Exception as e:
            logger.warning(f"Không thể kiểm tra/tạo trước batch {batch_id}: {e}")

    def save_cccd_crop_audit(
        self,
        batch_id: str,
        pair_id: str,
        audit: Dict[str, Any],
        source_path: str = "",
    ) -> bool:
        """Lưu audit CCCD của batch pair, không can thiệp ocr_records của luồng cũ."""
        if not self._pool or not batch_id or not pair_id:
            return False

        crop_id = str(audit.get("crop_id") or "")
        if not crop_id:
            logger.warning("Bỏ qua audit CCCD không có crop_id cho pair %s.", pair_id)
            return False

        try:
            self._ensure_batch_exists(batch_id, batch_id, source_path)
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO cccd_crop_audits (
                            batch_id, pair_id, crop_id, crop_path, crop_url,
                            audit_status, audit_data, created_at, updated_at
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                        ON CONFLICT (batch_id, pair_id, crop_id) DO UPDATE SET
                            crop_path = EXCLUDED.crop_path,
                            crop_url = EXCLUDED.crop_url,
                            audit_status = EXCLUDED.audit_status,
                            audit_data = EXCLUDED.audit_data,
                            updated_at = CURRENT_TIMESTAMP;
                    """, (
                        batch_id,
                        pair_id,
                        crop_id,
                        audit.get("crop_path"),
                        audit.get("crop_url"),
                        audit.get("status", "not_available"),
                        Json(audit),
                    ))
                    conn.commit()
            return True
        except Exception as e:
            # Lưu DB là best-effort: lỗi DB không được chặn Excel/JSON/crop của batch pair.
            logger.warning("Không thể lưu audit CCCD batch=%s pair=%s: %s", batch_id, pair_id, e)
            return False

    def list_records(
        self,
        limit: int = 100,
        offset: int = 0,
        folder_result: Optional[str] = None,
        source_path: Optional[str] = None,
        batch_id: Optional[str] = None,
        min_files: Optional[int] = None,
        max_files: Optional[int] = None,
        search: Optional[str] = None,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        Lấy danh sách bản ghi hồ sơ tóm tắt kèm hỗ trợ các bộ lọc:
        - folder_result: Lọc theo thư mục kết quả
        - source_path: Lọc theo link/thư mục nguồn trên máy
        - batch_id: Lọc theo đợt quét
        - min_files / max_files: Lọc các hồ sơ thuộc mẻ quét có số lượng file tương ứng
        - search: Tìm kiếm theo tên file, tên chủ, số phát hành, thửa/tờ
        Trả về (danh sách bản ghi, tổng số lượng thỏa mãn điều kiện).
        """
        if not self._pool:
            return [], 0
        try:
            where_clauses = []
            params: List[Any] = []

            if folder_result and folder_result.strip() and folder_result != "all":
                where_clauses.append("r.folder_result = %s")
                params.append(folder_result.strip())

            if source_path and source_path.strip() and source_path != "all":
                where_clauses.append("(r.source_folder = %s OR r.source_path LIKE %s)")
                params.append(source_path.strip())
                params.append(f"%{source_path.strip()}%")

            if batch_id and batch_id.strip() and batch_id != "all":
                where_clauses.append("r.batch_id = %s")
                params.append(batch_id.strip())

            if min_files is not None and min_files > 0:
                where_clauses.append("b.total_files >= %s")
                params.append(min_files)

            if max_files is not None and max_files > 0:
                where_clauses.append("b.total_files <= %s")
                params.append(max_files)

            if search and search.strip():
                pat = f"%{search.strip()}%"
                where_clauses.append("""
                    (r.file_name ILIKE %s OR r.ten_chu ILIKE %s OR r.so_phat_hanh ILIKE %s
                     OR r.so_thua ILIKE %s OR r.to_ban_do ILIKE %s OR r.id ILIKE %s
                     OR r.source_path ILIKE %s)
                """)
                params.extend([pat, pat, pat, pat, pat, pat, pat])

            where_sql = " AND ".join(where_clauses)
            if where_sql:
                where_sql = "WHERE " + where_sql

            with self.get_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    # Đếm tổng
                    count_query = f"""
                        SELECT COUNT(*) as cnt
                        FROM ocr_records r
                        LEFT JOIN ocr_batches b ON r.batch_id = b.batch_id
                        {where_sql};
                    """
                    cur.execute(count_query, params)
                    total_count = cur.fetchone()["cnt"]

                    # Truy vấn lấy dữ liệu
                    data_query = f"""
                        SELECT r.id, r.batch_id, r.file_name, r.source_path, r.source_folder,
                               r.folder_result, r.template, r.total_pages, r.so_phat_hanh,
                               r.so_vao_so, r.ma_vach, r.ten_chu, r.cmnd, r.so_thua,
                               r.to_ban_do, r.dien_tich, r.dia_chi, r.status,
                               r.elapsed_seconds, r.created_at,
                               LENGTH(r.raw_markdown) as content_length,
                               b.total_files as batch_total_files
                        FROM ocr_records r
                        LEFT JOIN ocr_batches b ON r.batch_id = b.batch_id
                        {where_sql}
                        ORDER BY r.created_at DESC
                        LIMIT %s OFFSET %s;
                    """
                    query_params = list(params) + [limit, offset]
                    cur.execute(data_query, query_params)
                    rows = cur.fetchall()

                    result = []
                    for r in rows:
                        item = dict(r)
                        item["created_at"] = r["created_at"].strftime("%Y-%m-%d %H:%M:%S") if r.get("created_at") else ""
                        result.append(item)

                    return result, total_count
        except Exception as e:
            logger.error(f"Lỗi list_records PostgreSQL: {e}")
            return [], 0

    def get_record(self, doc_id: str) -> Optional[Dict[str, Any]]:
        """Lấy chi tiết đầy đủ của một hồ sơ gồm Markdown, JSON, các dòng 129 cột."""
        if not self._pool:
            return None
        try:
            with self.get_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute("""
                        SELECT id, batch_id, file_name, source_path, source_folder, folder_result,
                               template, total_pages, so_phat_hanh, so_vao_so, ma_vach,
                               ten_chu, cmnd, so_thua, to_ban_do, dien_tich, dia_chi,
                               raw_markdown, structured_data, chuyen_doi_rows, status,
                               elapsed_seconds, created_at
                        FROM ocr_records
                        WHERE id = %s;
                    """, (doc_id,))
                    row = cur.fetchone()
                    if not row:
                        return None
                    item = dict(row)
                    item["created_at"] = row["created_at"].strftime("%Y-%m-%d %H:%M:%S") if row.get("created_at") else ""
                    return item
        except Exception as e:
            logger.error(f"Lỗi get_record PostgreSQL: {e}")
            return None

    def get_raw_records_dump(
        self,
        folder_result: Optional[str] = None,
        source_path: Optional[str] = None,
        batch_id: Optional[str] = None,
        search: Optional[str] = None,
        ids: Optional[List[str]] = None,
        limit: int = 10000
    ) -> List[Dict[str, Any]]:
        """Lấy toàn bộ các bản ghi OCR đầy đủ (kèm raw_markdown, structured_data) phục vụ backup/export."""
        if not self._pool:
            return []
        try:
            where_clauses = []
            params: List[Any] = []

            if ids:
                where_clauses.append("r.id = ANY(%s)")
                params.append(list(ids))

            if folder_result and folder_result.strip() and folder_result != "all":
                where_clauses.append("r.folder_result = %s")
                params.append(folder_result.strip())

            if source_path and source_path.strip() and source_path != "all":
                where_clauses.append("(r.source_folder = %s OR r.source_path LIKE %s)")
                params.append(source_path.strip())
                params.append(f"%{source_path.strip()}%")

            if batch_id and batch_id.strip() and batch_id != "all":
                where_clauses.append("r.batch_id = %s")
                params.append(batch_id.strip())

            if search and search.strip():
                pat = f"%{search.strip()}%"
                where_clauses.append("""
                    (r.file_name ILIKE %s OR r.ten_chu ILIKE %s OR r.so_phat_hanh ILIKE %s
                     OR r.so_thua ILIKE %s OR r.to_ban_do ILIKE %s OR r.id ILIKE %s
                     OR r.source_path ILIKE %s)
                """)
                params.extend([pat, pat, pat, pat, pat, pat, pat])

            where_sql = " AND ".join(where_clauses)
            if where_sql:
                where_sql = "WHERE " + where_sql

            query = f"""
                SELECT r.id, r.batch_id, r.file_name, r.source_path, r.source_folder,
                       r.folder_result, r.template, r.total_pages, r.so_phat_hanh,
                       r.so_vao_so, r.ma_vach, r.ten_chu, r.cmnd, r.so_thua,
                       r.to_ban_do, r.dien_tich, r.dia_chi, r.raw_markdown,
                       r.structured_data, r.chuyen_doi_rows, r.status,
                       r.elapsed_seconds, r.created_at
                FROM ocr_records r
                {where_sql}
                ORDER BY r.created_at DESC
                LIMIT %s;
            """
            params.append(limit)

            with self.get_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute(query, params)
                    rows = cur.fetchall()
                    result = []
                    for row in rows:
                        item = dict(row)
                        item["created_at"] = row["created_at"].strftime("%Y-%m-%d %H:%M:%S") if row.get("created_at") else ""
                        result.append(item)
                    return result
        except Exception as e:
            logger.error(f"Lỗi get_raw_records_dump PostgreSQL: {e}")
            return []

    def get_129_rows(
        self,
        folder_result: Optional[str] = None,
        source_path: Optional[str] = None,
        batch_id: Optional[str] = None,
        limit: int = 5000,
    ) -> List[Dict[str, Any]]:
        """
        Trích xuất trực tiếp danh sách hàng 129 cột đã lưu từ PostgreSQL
        theo mẻ quét hoặc thư mục kết quả được chọn.
        """
        if not self._pool:
            return []
        try:
            where_clauses = ["r.chuyen_doi_rows IS NOT NULL"]
            params: List[Any] = []

            if folder_result and folder_result.strip() and folder_result != "all":
                where_clauses.append("r.folder_result = %s")
                params.append(folder_result.strip())

            if source_path and source_path.strip() and source_path != "all":
                where_clauses.append("(r.source_folder = %s OR r.source_path LIKE %s)")
                params.append(source_path.strip())
                params.append(f"%{source_path.strip()}%")

            if batch_id and batch_id.strip() and batch_id != "all":
                where_clauses.append("r.batch_id = %s")
                params.append(batch_id.strip())

            where_sql = "WHERE " + " AND ".join(where_clauses)

            with self.get_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute(f"""
                        SELECT r.id, r.file_name, r.chuyen_doi_rows, r.created_at
                        FROM ocr_records r
                        {where_sql}
                        ORDER BY r.created_at ASC
                        LIMIT %s;
                    """, list(params) + [limit])
                    rows = cur.fetchall()

                    all_rows = []
                    curr_stt = 1
                    for r in rows:
                        c_rows = r.get("chuyen_doi_rows")
                        if isinstance(c_rows, list):
                            for crow in c_rows:
                                row_copy = dict(crow)
                                row_copy["STT"] = curr_stt
                                row_copy["raw_doc_id"] = r["id"]
                                if not row_copy.get("file_name"):
                                    row_copy["file_name"] = r["file_name"]
                                all_rows.append(row_copy)
                                curr_stt += 1
                    return all_rows
        except Exception as e:
            logger.error(f"Lỗi lấy 129 rows từ PostgreSQL: {e}")
            return []

    # ─── BỘ LỌC DANH SÁCH THƯ MỤC & NGUỒN ──────────────────────────────────────

    def get_filter_options(self) -> Dict[str, Any]:
        """
        Lấy danh sách các thư mục kết quả (folders), các đường dẫn nguồn (source paths),
        và các mức số lượng file để hiển thị trên bộ lọc UI.
        """
        if not self._pool:
            return {"folders": [], "sources": [], "batches": []}
        try:
            with self.get_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    # 1. Danh sách thư mục kết quả / batch
                    cur.execute("""
                        SELECT DISTINCT COALESCE(folder_result, batch_id, 'Khác') as folder,
                               COUNT(*) as doc_count,
                               MIN(created_at) as first_created,
                               MAX(created_at) as last_created
                        FROM ocr_records
                        GROUP BY COALESCE(folder_result, batch_id, 'Khác')
                        ORDER BY last_created DESC;
                    """)
                    folders_raw = cur.fetchall()
                    folders = [
                        {
                            "name": r["folder"],
                            "count": r["doc_count"],
                            "date": r["last_created"].strftime("%Y-%m-%d %H:%M") if r.get("last_created") else ""
                        }
                        for r in folders_raw
                    ]

                    # 2. Danh sách link trên máy (source_folder)
                    cur.execute("""
                        SELECT DISTINCT source_folder, COUNT(*) as doc_count
                        FROM ocr_records
                        WHERE source_folder IS NOT NULL AND source_folder != ''
                        GROUP BY source_folder
                        ORDER BY doc_count DESC;
                    """)
                    sources_raw = cur.fetchall()
                    sources = [
                        {"path": r["source_folder"], "count": r["doc_count"]}
                        for r in sources_raw
                    ]

                    # 3. Phân bố số lượng file theo batch
                    cur.execute("""
                        SELECT batch_id, folder_name, total_files, processed_count
                        FROM ocr_batches
                        ORDER BY created_at DESC
                        LIMIT 50;
                    """)
                    batches_raw = cur.fetchall()
                    batches = [dict(b) for b in batches_raw]

                    return {
                        "folders": folders,
                        "sources": sources,
                        "batches": batches,
                    }
        except Exception as e:
            logger.error(f"Lỗi lấy filter options từ PostgreSQL: {e}")
            return {"folders": [], "sources": [], "batches": []}

    def get_stats(self) -> Dict[str, Any]:
        """Thống kê tổng thể về số batch, tổng số hồ sơ, số hồ sơ hợp lệ và lỗi."""
        if not self._pool:
            return {"connected": False}
        try:
            with self.get_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute("""
                        SELECT 
                            (SELECT COUNT(*) FROM ocr_batches) as total_batches,
                            (SELECT COUNT(*) FROM ocr_records) as total_records,
                            (SELECT COUNT(*) FROM ocr_records WHERE status = 'success') as success_records,
                            (SELECT COUNT(*) FROM ocr_records WHERE status = 'error') as error_records,
                            (SELECT COUNT(DISTINCT folder_result) FROM ocr_records) as total_folders;
                    """)
                    row = cur.fetchone()
                    return {
                        "connected": True,
                        "host": self.host,
                        "port": self.port,
                        "database": self.database,
                        "total_batches": row["total_batches"] or 0,
                        "total_records": row["total_records"] or 0,
                        "success_records": row["success_records"] or 0,
                        "error_records": row["error_records"] or 0,
                        "total_folders": row["total_folders"] or 0,
                    }
        except Exception as e:
            return {"connected": False, "error": str(e)}

    # ─── XÓA CÓ CHỌN LỌC (SELECTIVE DELETION) ─────────────────────────────────

    def delete_records_by_ids(self, ids: List[str]) -> int:
        """Xóa có chọn lọc danh sách hồ sơ theo ID."""
        if not self._pool or not ids:
            return 0
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        DELETE FROM ocr_records
                        WHERE id = ANY(%s);
                    """, (ids,))
                    deleted_count = cur.rowcount
                    conn.commit()
            return deleted_count
        except Exception as e:
            logger.error(f"Lỗi xóa records theo IDs trong PostgreSQL: {e}")
            return 0

    def delete_by_folder(self, folder_result: str) -> int:
        """Xóa có chọn lọc toàn bộ hồ sơ thuộc một thư mục kết quả."""
        if not self._pool or not folder_result:
            return 0
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    # 1. Xóa trong ocr_records
                    cur.execute("""
                        DELETE FROM ocr_records
                        WHERE folder_result = %s;
                    """, (folder_result,))
                    deleted_count = cur.rowcount

                    # 2. Xóa hoặc cập nhật batch liên quan
                    cur.execute("""
                        DELETE FROM ocr_batches
                        WHERE folder_name = %s OR batch_id = %s;
                    """, (folder_result, folder_result))
                    conn.commit()
            return deleted_count
        except Exception as e:
            logger.error(f"Lỗi xóa theo folder_result trong PostgreSQL: {e}")
            return 0

    def delete_by_source_path(self, source_path: str) -> int:
        """Xóa có chọn lọc toàn bộ hồ sơ thuộc một đường dẫn/link nguồn trên máy."""
        if not self._pool or not source_path:
            return 0
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        DELETE FROM ocr_records
                        WHERE source_folder = %s OR source_path LIKE %s;
                    """, (source_path, f"%{source_path}%"))
                    deleted_count = cur.rowcount
                    conn.commit()
            return deleted_count
        except Exception as e:
            logger.error(f"Lỗi xóa theo source_path trong PostgreSQL: {e}")
            return 0

    def delete_batch(self, batch_id: str) -> int:
        """Xóa toàn bộ một đợt quét (tự động CASCADE xóa tất cả ocr_records thuộc batch đó)."""
        if not self._pool or not batch_id:
            return 0
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT COUNT(*) FROM ocr_records WHERE batch_id = %s;", (batch_id,))
                    row = cur.fetchone()
                    rec_count = row[0] if row else 0

                    cur.execute("DELETE FROM ocr_batches WHERE batch_id = %s;", (batch_id,))
                    conn.commit()
            return rec_count
        except Exception as e:
            logger.error(f"Lỗi xóa batch trong PostgreSQL: {e}")
            return 0


# Singleton instance
_pg_store: Optional[PostgresStore] = None


def get_postgres_store() -> PostgresStore:
    """Trả về singleton PostgreSQL; tự phục hồi khi dịch vụ DB khởi động lại."""
    global _pg_store
    if _pg_store is None:
        _pg_store = PostgresStore()
    elif not _pg_store.is_connected():
        _pg_store.reconnect_if_due()
    return _pg_store
