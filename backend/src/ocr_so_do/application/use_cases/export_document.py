"""
Use Case: Xuất kết quả OCR ra bảng Excel 129 cột theo mẫu chuẩn.
"""
from typing import List, Dict, Any, Optional
from ..ports import ArtifactStorePort
from ...infrastructure.exporters.excel_129_exporter import Excel129Exporter


class ExportDocumentUseCase:
    @staticmethod
    def export_excel_129(
        rows: List[Dict[str, Any]],
        output_path: str,
        template_path: Optional[str] = None
    ) -> str:
        return Excel129Exporter.export(
            mapped_rows=rows,
            output_path=output_path,
            template_path=template_path
        )
