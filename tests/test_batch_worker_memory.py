from pathlib import Path
from types import SimpleNamespace


class RecordingQueue:
    def __init__(self):
        self.messages = []

    def put(self, message):
        self.messages.append(message)


class SuccessfulUseCase:
    def execute(self, document_path, document_id, split_a3, smart_gcn_filter, stt):
        return {
            "file_name": Path(document_path).name,
            "merged": {
                "mau": "mau_A",
                "so_phat_hanh": "AB123456",
                "nguoi_su_dung": {"ho_ten_chu_1": "Nguyen Van A"},
                "thua_dat": {"so_thua": "12", "to_ban_do": "3"},
            },
            "page_results": [],
            "raw_ocr_markdown": "",
            "chuyen_doi_rows": [],
            "elapsed_seconds": 0.01,
        }


def test_worker_chunk_persists_result_and_only_sends_summary(monkeypatch, tmp_path):
    from ocr_so_do.interfaces.api.routers import batch

    container = SimpleNamespace(process_document_uc=SuccessfulUseCase())
    monkeypatch.setattr(batch, "get_container", lambda save_crops_to_disk=True: container)
    monkeypatch.setattr(batch, "cleanup_memory", lambda force_os_trim=False: None)

    source = tmp_path / "sample.jpg"
    source.write_bytes(b"test")
    messages = RecordingQueue()

    batch._run_batch_worker_chunk(
        "test_batch",
        [(1, str(source))],
        True,
        True,
        str(tmp_path),
        messages,
    )

    assert [item["type"] for item in messages.messages] == ["started", "result", "done"]
    summary = messages.messages[1]["summary"]
    assert summary["status"] == "success"
    assert summary["file_name"] == "sample.jpg"
    assert "merged" not in summary
    assert Path(summary["result_path"]).is_file()


def test_worker_chunk_reports_file_error_and_continues(monkeypatch, tmp_path):
    from ocr_so_do.interfaces.api.routers import batch

    class FailingUseCase:
        def execute(self, **kwargs):
            raise MemoryError("synthetic OOM")

    container = SimpleNamespace(process_document_uc=FailingUseCase())
    monkeypatch.setattr(batch, "get_container", lambda save_crops_to_disk=True: container)
    monkeypatch.setattr(batch, "cleanup_memory", lambda force_os_trim=False: None)
    messages = RecordingQueue()

    batch._run_batch_worker_chunk(
        "test_batch",
        [(1, str(tmp_path / "one.jpg")), (2, str(tmp_path / "two.jpg"))],
        True,
        True,
        str(tmp_path),
        messages,
    )

    result_messages = [item for item in messages.messages if item["type"] == "result"]
    assert len(result_messages) == 2
    assert all(item["summary"]["status"] == "error" for item in result_messages)
    assert messages.messages[-1]["type"] == "done"


def test_process_local_cleanup_never_recreates_detector(monkeypatch):
    from ocr_so_do.infrastructure import memory

    detector = object()
    orchestrator = SimpleNamespace(detector=detector)
    container = SimpleNamespace(detector=detector, orchestrator=orchestrator)
    monkeypatch.setattr(memory, "cleanup_memory", lambda force_os_trim=True: None)

    result = memory.reset_system_memory(container, deep_engine_reset=True)

    assert container.detector is detector
    assert container.orchestrator.detector is detector
    assert result["engine_recreated"] is False
