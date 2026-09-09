"""
Domain errors định nghĩa các exception chuẩn của hệ thống OCR.
"""

class DomainError(Exception):
    """Lỗi cơ sở cho toàn bộ domain logic."""
    def __init__(self, message: str, code: str = "DOMAIN_ERROR"):
        super().__init__(message)
        self.message = message
        self.code = code


class DocumentNotFoundError(DomainError):
    def __init__(self, doc_id: str):
        super().__init__(f"Không tìm thấy tài liệu với ID: {doc_id}", "DOCUMENT_NOT_FOUND")


class InvalidBoundingBoxError(DomainError):
    def __init__(self, reason: str):
        super().__init__(f"Tọa độ BoundingBox không hợp lệ: {reason}", "INVALID_BOUNDING_BOX")


class ExtractionRuleError(DomainError):
    def __init__(self, rule_id: str, reason: str):
        super().__init__(f"Lỗi thực thi quy tắc trích xuất '{rule_id}': {reason}", "EXTRACTION_RULE_ERROR")


class JobStateError(DomainError):
    def __init__(self, job_id: str, reason: str):
        super().__init__(f"Lỗi trạng thái Job '{job_id}': {reason}", "JOB_STATE_ERROR")
