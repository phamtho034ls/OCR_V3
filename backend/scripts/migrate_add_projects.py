"""
Migration script: Thêm bảng dự án và cập nhật schema cho production.

Chạy một lần duy nhất khi upgrade lên phiên bản mới:
  python backend/scripts/migrate_add_projects.py

Script này an toàn khi chạy nhiều lần (đều dùng IF NOT EXISTS / ALTER IF NOT EXISTS).
"""
import os
import sys
import logging
from pathlib import Path

# Thêm backend/src vào PYTHONPATH
script_dir = Path(__file__).resolve().parent
project_root = script_dir.parent.parent
backend_src = project_root / "ocr-so-do" / "backend" / "src"
if str(backend_src) not in sys.path:
    sys.path.insert(0, str(backend_src))

# Load .env
try:
    from dotenv import load_dotenv
    env_path = project_root / "ocr-so-do" / ".env"
    if env_path.exists():
        load_dotenv(env_path)
        print(f"Loaded .env from {env_path}")
except ImportError:
    print("python-dotenv not installed, reading from environment directly")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def run_migration():
    import psycopg2

    host = os.getenv("PG_HOST", "127.0.0.1")
    port = int(os.getenv("PG_PORT", "5433"))
    user = os.getenv("PG_USER", "postgres")
    password = os.getenv("PG_PASSWORD", "")
    database = os.getenv("PG_DATABASE", "ocr_so_do")

    logger.info(f"Kết nối PostgreSQL: {host}:{port}/{database} user={user}")
    conn = psycopg2.connect(
        host=host, port=port, user=user, password=password, dbname=database
    )
    conn.autocommit = False
    cur = conn.cursor()

    try:
        logger.info("[1/6] Tạo bảng ocr_projects nếu chưa có...")
        cur.execute("""
            CREATE TABLE IF NOT EXISTS ocr_projects (
                project_id   VARCHAR(100) PRIMARY KEY,
                project_name VARCHAR(255) NOT NULL,
                description  TEXT,
                created_by   VARCHAR(255) NOT NULL,
                status       VARCHAR(30) DEFAULT 'active',
                created_at   TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                updated_at   TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
            );
        """)

        logger.info("[2/6] Tạo bảng project_members nếu chưa có...")
        cur.execute("""
            CREATE TABLE IF NOT EXISTS project_members (
                id               BIGSERIAL PRIMARY KEY,
                project_id       VARCHAR(100) NOT NULL
                                 REFERENCES ocr_projects(project_id) ON DELETE CASCADE,
                user_id          VARCHAR(255) NOT NULL,
                username         VARCHAR(255) NOT NULL,
                display_name     VARCHAR(255),
                role_in_project  VARCHAR(30) DEFAULT 'member',
                added_by         VARCHAR(255) NOT NULL,
                added_at         TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (project_id, user_id)
            );
        """)

        logger.info("[3/6] Thêm cột project_id và created_by vào ocr_batches...")
        cur.execute("""
            ALTER TABLE ocr_batches
                ADD COLUMN IF NOT EXISTS project_id VARCHAR(100)
                    REFERENCES ocr_projects(project_id),
                ADD COLUMN IF NOT EXISTS created_by VARCHAR(255);
        """)

        logger.info("[4/6] Thêm cột project_id và created_by vào ocr_records...")
        cur.execute("""
            ALTER TABLE ocr_records
                ADD COLUMN IF NOT EXISTS project_id VARCHAR(100)
                    REFERENCES ocr_projects(project_id),
                ADD COLUMN IF NOT EXISTS created_by VARCHAR(255);
        """)

        logger.info("[5/6] Tạo indexes mới...")
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_projects_created_by ON ocr_projects(created_by);
            CREATE INDEX IF NOT EXISTS idx_project_members_user ON project_members(user_id);
            CREATE INDEX IF NOT EXISTS idx_project_members_project ON project_members(project_id);
            CREATE INDEX IF NOT EXISTS idx_ocr_batches_project ON ocr_batches(project_id);
            CREATE INDEX IF NOT EXISTS idx_ocr_batches_created_by ON ocr_batches(created_by);
            CREATE INDEX IF NOT EXISTS idx_ocr_records_project ON ocr_records(project_id);
            CREATE INDEX IF NOT EXISTS idx_ocr_records_created_by ON ocr_records(created_by);
        """)

        logger.info("[6/6] Tạo dự án mặc định cho dữ liệu cũ...")
        cur.execute("""
            INSERT INTO ocr_projects
                (project_id, project_name, description, created_by, status)
            VALUES
                ('proj_legacy_default',
                 'Dữ liệu cũ (trước khi phân dự án)',
                 'Dự án tự động tạo ra cho toàn bộ dữ liệu OCR cũ trước khi hệ thống phân dự án.',
                 'admin',
                 'active')
            ON CONFLICT (project_id) DO NOTHING;
        """)

        conn.commit()
        logger.info("✅ Migration hoàn thành thành công!")
        logger.info("   - Bảng ocr_projects và project_members đã được tạo")
        logger.info("   - Cột project_id, created_by đã được thêm")
        logger.info("   - Dự án mặc định 'proj_legacy_default' đã được tạo")
        logger.info("   Tiếp theo: Dùng trang Admin để tạo dự án và thêm thành viên.")

    except Exception as e:
        conn.rollback()
        logger.error(f"❌ Lỗi migration: {e}")
        raise
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    run_migration()
