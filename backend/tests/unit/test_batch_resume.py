from pathlib import Path
import pytest
from ocr_so_do.interfaces.api.routers.batch import ScanDirectoryRequest

def test_scan_directory_request_defaults():
    req = ScanDirectoryRequest(directory_path="D:/data")
    assert req.directory_path == "D:/data"
    assert req.start_index == 0
    assert req.resume_batch_id is None
    assert req.sample_count == 0
    assert req.split_a3 is True
    assert req.smart_gcn_filter is True

def test_scan_directory_request_with_resume():
    req = ScanDirectoryRequest(
        directory_path="D:/data",
        sample_count=10,
        start_index=5,
        resume_batch_id="dir_abc12345"
    )
    assert req.start_index == 5
    assert req.resume_batch_id == "dir_abc12345"
    assert req.sample_count == 10
