import React, { useState, useRef, useEffect } from 'react';
import axios from 'axios';
import {
  FolderUp,
  Server,
  Play,
  Square,
  FileSpreadsheet,
  CheckCircle2,
  AlertTriangle,
  Clock,
  Files,
  ArrowRight,
  Download,
  Loader2,
  FolderOpen,
  FileText,
  Search,
  Check,
  RefreshCw,
  ExternalLink,
  FileCode,
  Copy,
  X,
  Database,
  Layers,
  Eye,
  RotateCcw,
} from 'lucide-react';
import { BatchItemSummary, BatchProgressResponse } from '../../shared/types';
import { QuickReviewPanel } from '../../shared/components/QuickReviewPanel';
import { useAuth } from '../../shared/auth/AuthProvider';
import { extractErrorMessage } from '../../shared/lib/errorHelper';

interface BatchScanPageProps {
  onView129Table: (rows: Record<string, any>[]) => void;
  onOpenPgStorage?: () => void;
  onRunningChange?: (isRunning: boolean) => void;
}

export const BatchScanPage: React.FC<BatchScanPageProps> = ({ onView129Table, onOpenPgStorage, onRunningChange }) => {
  const { can } = useAuth();
  const [scanMode, setScanMode] = useState<'client_folder' | 'server_path' | 'pair_scan'>('client_folder');

  // Pair Scan State (GCN & GT -> 129 Cột)
  const [pairServerPath, setPairServerPath] = useState<string>('');
  const [pairSampleLimit, setPairSampleLimit] = useState<number>(0);
  const [isPreviewingPairs, setIsPreviewingPairs] = useState<boolean>(false);
  const [pairPreviewData, setPairPreviewData] = useState<{
    directory_path: string;
    total_pairs: number;
    both_count: number;
    gcn_only_count: number;
    gt_only_count: number;
    pairs: Array<{
      pair_id: string;
      status: string;
      has_gcn: boolean;
      has_gt: boolean;
      gcn_file?: string;
      gt_file?: string;
    }>;
  } | null>(null);
  const [isPairScanning, setIsPairScanning] = useState<boolean>(false);
  const [activePairBatchId, setActivePairBatchId] = useState<string | null>(null);
  const [pairBatchStatus, setPairBatchStatus] = useState<'idle' | 'running' | 'completed' | 'cancelled' | 'error'>('idle');
  const [pairResults, setPairResults] = useState<any[]>([]);
  const [pairProgressPercent, setPairProgressPercent] = useState<number>(0);
  const [pairProcessedCount, setPairProcessedCount] = useState<number>(0);
  const [pairTotalCount, setPairTotalCount] = useState<number>(0);
  const [pairCurrentItem, setPairCurrentItem] = useState<string>('');
  const [pairElapsedSeconds, setPairElapsedSeconds] = useState<number>(0);
  const [pairSpeed, setPairSpeed] = useState<number>(0);
  const [pairExcelReady, setPairExcelReady] = useState<boolean>(false);
  const [pairCccdAuditSummary, setPairCccdAuditSummary] = useState<Record<string, number>>({});
  const [showPairPreviewModal, setShowPairPreviewModal] = useState<boolean>(false);

  // Client Folder Upload State
  const [clientFiles, setClientFiles] = useState<File[]>([]);
  const [folderName, setFolderName] = useState<string>('');
  const [isClientProcessing, setIsClientProcessing] = useState<boolean>(false);
  const abortControllerRef = useRef<AbortController | null>(null);

  // Server Path State
  const [serverPath, setServerPath] = useState<string>('');
  const [sampleCount, setSampleCount] = useState<number>(0);
  const [isServerScanning, setIsServerScanning] = useState<boolean>(false);
  const [activeBatchId, setActiveBatchId] = useState<string | null>(null);

  // Shared Progress & Results State
  const [progressPercent, setProgressPercent] = useState<number>(0);
  const [currentFileName, setCurrentFileName] = useState<string>('');
  const [processedCount, setProcessedCount] = useState<number>(0);
  const [totalFilesCount, setTotalFilesCount] = useState<number>(0);
  const [elapsedSeconds, setElapsedSeconds] = useState<number>(0);
  const [speedPerMin, setSpeedPerMin] = useState<number>(0);
  const [batchStatus, setBatchStatus] = useState<'idle' | 'running' | 'completed' | 'cancelled' | 'error' | 'paused'>('idle');
  const [clientPausedIndex, setClientPausedIndex] = useState<number>(0);
  const clientPausedIndexRef = useRef<number>(0);
  const [results, setResults] = useState<BatchItemSummary[]>([]);
  const [chuyenDoiRows, setChuyenDoiRows] = useState<Record<string, any>[]>([]);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [exportingExcel, setExportingExcel] = useState<boolean>(false);
  const [lastCheckpointIdx, setLastCheckpointIdx] = useState<number>(0);
  const [checkpointExcelUrl, setCheckpointExcelUrl] = useState<string | null>(null);
  const [lastCheckpointMsg, setLastCheckpointMsg] = useState<string | null>(null);
  const [viewingMarkdownItem, setViewingMarkdownItem] = useState<{ fileName: string; content: string } | null>(null);
  const [copiedMd, setCopiedMd] = useState<boolean>(false);
  const [reviewDocumentId, setReviewDocumentId] = useState<string | null>(null);

  const folderInputRef = useRef<HTMLInputElement | null>(null);
  const multiFileInputRef = useRef<HTMLInputElement | null>(null);

  // Handle client folder select
  const handleFolderSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (!e.target.files || e.target.files.length === 0) return;
    const rawFiles = Array.from(e.target.files);
    // Filter only valid PDF and image files
    const validExts = ['.pdf', '.png', '.jpg', '.jpeg'];
    const filtered = rawFiles.filter(f =>
      validExts.some(ext => f.name.toLowerCase().endsWith(ext))
    );

    if (filtered.length === 0) {
      alert('Không tìm thấy file PDF hoặc ảnh hợp lệ trong thư mục đã chọn!');
      return;
    }

    setClientFiles(filtered);
    setClientPausedIndex(0);
    clientPausedIndexRef.current = 0;
    // Detect folder name from webkitRelativePath
    const firstRel = filtered[0].webkitRelativePath;
    if (firstRel) {
      const topDir = firstRel.split('/')[0];
      setFolderName(topDir || 'Thư mục chọn');
    } else {
      setFolderName(`${filtered.length} files`);
    }

    // Reset results
    setResults([]);
    setChuyenDoiRows([]);
    setBatchStatus('idle');
    setProgressPercent(0);
    setProcessedCount(0);
    setTotalFilesCount(filtered.length);
  };

  // Run Client Folder Processing sequentially (hỗ trợ tiếp tục sau khi dừng)
  const startClientProcessing = async (resume: boolean = false) => {
    if (clientFiles.length === 0) return;

    const startIdx = resume ? clientPausedIndexRef.current : 0;
    if (startIdx >= clientFiles.length) {
      return;
    }

    setIsClientProcessing(true);
    setBatchStatus('running');
    setErrorMessage(null);

    let tempResults: BatchItemSummary[] = [];
    let tempRows: Record<string, any>[] = [];

    if (!resume) {
      setResults([]);
      setChuyenDoiRows([]);
      setProgressPercent(0);
      setProcessedCount(0);
      setElapsedSeconds(0);
      setSpeedPerMin(0);
      setClientPausedIndex(0);
      clientPausedIndexRef.current = 0;
    } else {
      tempResults = [...results];
      tempRows = [...chuyenDoiRows];
    }

    const abortController = new AbortController();
    abortControllerRef.current = abortController;

    const previousElapsed = resume ? elapsedSeconds : 0;
    const tStart = Date.now() - previousElapsed * 1000;

    for (let i = startIdx; i < clientFiles.length; i++) {
      if (abortController.signal.aborted) {
        setBatchStatus('paused');
        clientPausedIndexRef.current = i;
        setClientPausedIndex(i);
        break;
      }

      const file = clientFiles[i];
      setCurrentFileName(`(${i + 1}/${clientFiles.length}) ${file.name}`);
      const tFileStart = Date.now();

      const formData = new FormData();
      formData.append('file', file);

      try {
        const res = await axios.post('/api/v1/documents', formData, {
          signal: abortController.signal,
          headers: { 'Content-Type': 'multipart/form-data' },
        });

        const docData = res.data?.data || {};
        const nsd = docData.nguoi_su_dung || {};
        const td = docData.thua_dat || {};
        const elapsedFile = ((Date.now() - tFileStart) / 1000).toFixed(1);

        const item: BatchItemSummary = {
          stt: i + 1,
          file_name: file.name,
          status: 'success',
          elapsed_seconds: parseFloat(elapsedFile),
          mau: docData.mau || docData.template || 'unknown',
          so_phat_hanh: docData.so_phat_hanh || '',
          so_vao_so: docData.so_vao_so || '',
          ma_vach: docData.ma_vach || '',
          ten_chu: nsd.ten || nsd.ho_ten_chu_1 || '',
          cmnd: nsd.cmnd_chu_1 || nsd.cmnd || '',
          so_thua: td.so_thua || '',
          to_ban_do: td.to_ban_do || '',
          dien_tich: td.dien_tich_cap || '',
          dia_chi_thua: td.dia_chi || '',
          document_id: res.data?.document_id || '',
          raw_ocr_markdown: docData.raw_ocr_markdown || res.data?.raw_ocr_markdown || '',
          data: docData,
        };

        tempResults.push(item);
        if (docData.chuyen_doi_rows && Array.isArray(docData.chuyen_doi_rows)) {
          tempRows.push(...docData.chuyen_doi_rows);
        }
        clientPausedIndexRef.current = i + 1;
        setClientPausedIndex(i + 1);
      } catch (err: any) {
        if (axios.isCancel(err) || abortController.signal.aborted) {
          setBatchStatus('paused');
          clientPausedIndexRef.current = i;
          setClientPausedIndex(i);
          break;
        }
        const elapsedFile = ((Date.now() - tFileStart) / 1000).toFixed(1);
        tempResults.push({
          stt: i + 1,
          file_name: file.name,
          status: 'error',
          error: err.response?.data?.detail || err.message || 'Lỗi không xác định',
          elapsed_seconds: parseFloat(elapsedFile),
        });
        clientPausedIndexRef.current = i + 1;
        setClientPausedIndex(i + 1);
      }

      const totalElapsed = (Date.now() - tStart) / 1000;
      setElapsedSeconds(Math.round(totalElapsed));
      const currProcessed = i + 1;
      setProcessedCount(currProcessed);
      const pct = Math.round((currProcessed / clientFiles.length) * 100);
      setProgressPercent(pct);
      const speed = totalElapsed > 3 ? Math.round((currProcessed / (totalElapsed / 60)) * 10) / 10 : 0;
      setSpeedPerMin(speed);
      setResults([...tempResults]);
      setChuyenDoiRows([...tempRows]);
    }

    setIsClientProcessing(false);
    if (!abortController.signal.aborted) {
      setBatchStatus('completed');
      setCurrentFileName('Hoàn thành toàn bộ thư mục');
      setClientPausedIndex(0);
      clientPausedIndexRef.current = 0;
    }
  };

  const stopClientProcessing = () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    setIsClientProcessing(false);
    setBatchStatus('paused');
  };

  // Run Server Path Batch Scanning (hỗ trợ tiếp tục quét dở dang)
  const startServerScan = async (resume: boolean = false) => {
    if (!serverPath.trim()) {
      alert('Vui lòng nhập đường dẫn thư mục máy chủ!');
      return;
    }

    const startIdx = resume ? processedCount : 0;
    const resumeBatchId = resume ? activeBatchId : null;

    setIsServerScanning(true);
    setBatchStatus('running');
    setErrorMessage(null);
    if (!resume) {
      setResults([]);
      setChuyenDoiRows([]);
      setProgressPercent(0);
      setProcessedCount(0);
      setActiveBatchId(null);
    }

    try {
      const res = await axios.post('/api/v1/batch/scan-directory', {
        directory_path: serverPath.trim(),
        sample_count: sampleCount,
        split_a3: true,
        smart_gcn_filter: true,
        start_index: startIdx,
        resume_batch_id: resumeBatchId,
      });

      const batchId = res.data?.batch_id;
      setActiveBatchId(batchId);
      setTotalFilesCount(res.data?.total_files || 0);
    } catch (err: any) {
      setIsServerScanning(false);
      setBatchStatus('error');
      setErrorMessage(err.response?.data?.detail || 'Không thể khởi chạy quét thư mục.');
    }
  };

  // Polling Server Batch Status
  useEffect(() => {
    let timer: any = null;
    if (isServerScanning && activeBatchId) {
      timer = setInterval(async () => {
        try {
          const res = await axios.get<BatchProgressResponse>(`/api/v1/batch/${activeBatchId}`);
          const data = res.data;

          setProgressPercent(data.progress_percent || 0);
          setProcessedCount(data.processed_count || 0);
          setTotalFilesCount(data.total_files || 0);
          setCurrentFileName(data.current_file || '');
          setElapsedSeconds(data.elapsed_seconds || 0);
          setSpeedPerMin(data.speed_files_per_min || 0);
          if (data.last_checkpoint_idx) setLastCheckpointIdx(data.last_checkpoint_idx);
          if (data.checkpoint_excel_url) setCheckpointExcelUrl(data.checkpoint_excel_url);
          if (data.last_checkpoint_message) setLastCheckpointMsg(data.last_checkpoint_message);
          if (data.results) setResults(data.results);
          if (data.chuyen_doi_rows) setChuyenDoiRows(data.chuyen_doi_rows);

          if (data.status === 'done') {
            setIsServerScanning(false);
            setBatchStatus('completed');
            clearInterval(timer);
          } else if (data.status === 'cancelled') {
            setIsServerScanning(false);
            setBatchStatus('paused');
            clearInterval(timer);
          } else if (data.status === 'error') {
            setIsServerScanning(false);
            setBatchStatus('error');
            setErrorMessage(data.error || 'Lỗi trong quá trình quét thư mục.');
            clearInterval(timer);
          }
        } catch (err) {
          console.error('Lỗi khi polling batch status:', err);
        }
      }, 1500);
    }

    return () => {
      if (timer) clearInterval(timer);
    };
  }, [isServerScanning, activeBatchId]);

  const stopServerScan = async () => {
    if (activeBatchId) {
      try {
        await axios.post(`/api/v1/batch/${activeBatchId}/cancel`);
        setIsServerScanning(false);
        setBatchStatus('paused');
      } catch (err) {
        console.error('Lỗi hủy batch:', err);
      }
    }
  };

  // ── XỬ LÝ QUÉT GHÉP CẶP GCN & GT (CCCD) ──────────────────────────
  const handlePreviewPairs = async () => {
    if (!pairServerPath.trim()) {
      alert('Vui lòng nhập đường dẫn thư mục chứa hồ sơ!');
      return;
    }
    setIsPreviewingPairs(true);
    setErrorMessage(null);
    try {
      const res = await axios.post('/api/v1/batch-pairs/preview', {
        directory_path: pairServerPath.trim(),
      });
      setPairPreviewData(res.data);
    } catch (err: any) {
      alert(err.response?.data?.detail || 'Lỗi quét xem trước thư mục!');
    } finally {
      setIsPreviewingPairs(false);
    }
  };

  const handleStartPairScan = async () => {
    if (!pairServerPath.trim()) {
      alert('Vui lòng nhập đường dẫn thư mục!');
      return;
    }
    setErrorMessage(null);
    setPairResults([]);
    setPairProgressPercent(0);
    setPairProcessedCount(0);
    setPairElapsedSeconds(0);
    setPairExcelReady(false);
    setPairCccdAuditSummary({});
    try {
      const res = await axios.post('/api/v1/batch-pairs/start', {
        directory_path: pairServerPath.trim(),
        sample_limit: pairSampleLimit,
        use_gpu: true,
        enable_cccd_audit: true,
        persist_cccd_audit: true,
      });
      setActivePairBatchId(res.data.batch_id);
      setIsPairScanning(true);
      setPairBatchStatus('running');
    } catch (err: any) {
      alert(err.response?.data?.detail || 'Không thể khởi động tiến trình quét ghép cặp!');
    }
  };

  const handleStopPairScan = async () => {
    if (activePairBatchId) {
      try {
        await axios.post(`/api/v1/batch-pairs/${activePairBatchId}/cancel`);
        setIsPairScanning(false);
        setPairBatchStatus('cancelled');
      } catch (err) {
        console.error('Lỗi hủy batch:', err);
      }
    }
  };

  // Polling tiến độ pair batch
  useEffect(() => {
    let timer: any = null;
    if (isPairScanning && activePairBatchId) {
      timer = setInterval(async () => {
        try {
          const res = await axios.get(`/api/v1/batch-pairs/${activePairBatchId}/status`);
          const data = res.data;
          setPairProgressPercent(data.progress_percent || 0);
          setPairProcessedCount(data.processed_count || 0);
          setPairTotalCount(data.total_pairs || 0);
          setPairCurrentItem(data.current_pair || '');
          setPairElapsedSeconds(data.elapsed_seconds || 0);
          setPairSpeed(data.speed_pairs_per_min || 0);
          if (data.results) setPairResults(data.results);
          if (data.excel_129_available) setPairExcelReady(true);
          if (data.cccd_audit_summary) setPairCccdAuditSummary(data.cccd_audit_summary);

          if (data.status === 'done') {
            setIsPairScanning(false);
            setPairBatchStatus('completed');
            clearInterval(timer);
          } else if (data.status === 'cancelled') {
            setIsPairScanning(false);
            setPairBatchStatus('cancelled');
            clearInterval(timer);
          } else if (data.status === 'error') {
            setIsPairScanning(false);
            setPairBatchStatus('error');
            setErrorMessage(data.error || 'Lỗi trong quá trình quét ghép cặp.');
            clearInterval(timer);
          }
        } catch (err) {
          console.error('Lỗi khi polling pair batch status:', err);
        }
      }, 1500);
    }
    return () => {
      if (timer) clearInterval(timer);
    };
  }, [isPairScanning, activePairBatchId]);

  const handleExportPairExcel129 = async () => {
    if (!can('export.129')) {
      alert("Tài khoản của bạn cần có vai trò 'Khai thác dữ liệu' (ocr-exporter) để xuất file Excel 129 cột.");
      return;
    }
    if (!activePairBatchId) return;
    try {
      const response = await axios.get(`/api/v1/batch-pairs/${activePairBatchId}/export-129`, { responseType: 'blob' });
      const url = window.URL.createObjectURL(new Blob([response.data]));
      const link = document.createElement('a');
      link.href = url;
      link.download = `KetQua_ChuyenDoi_129Cot_${activePairBatchId}.xlsx`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
    } catch (err: any) {
      const msg = await extractErrorMessage(err, 'Không thể tải file Excel kết quả ghép cặp');
      alert(msg);
    }
  };

  const downloadProtectedArtifact = async (url: string, filename = 'evidence.png') => {
    const response = await axios.get(url, { responseType: 'blob' });
    const objectUrl = window.URL.createObjectURL(new Blob([response.data]));
    const link = document.createElement('a');
    link.href = objectUrl;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.URL.revokeObjectURL(objectUrl);
  };

  // Export Excel 129 Columns (On-Demand từ Markdown đã lưu)
  const handleExportExcel = async () => {
    if (!can('export.129')) {
      alert("Tài khoản của bạn cần có vai trò 'Khai thác dữ liệu' (ocr-exporter) để xuất file Excel 129 cột.");
      return;
    }
    if (results.length === 0 && chuyenDoiRows.length === 0) {
      alert('Chưa có dữ liệu hồ sơ để xuất Excel!');
      return;
    }
    setExportingExcel(true);
    try {
      let resp;
      if (activeBatchId) {
        // Gọi endpoint chuyển đổi on-demand từ Markdown thô đã lưu của batch sang Excel 129 cột
        resp = await axios.post(`/api/v1/batch/${activeBatchId}/convert-markdown-to-129-excel`, {}, {
          responseType: 'blob',
        });
      } else if (chuyenDoiRows.length > 0) {
        resp = await axios.post(
          '/api/v1/exports/excel-129',
          {
            rows: chuyenDoiRows,
            filename: `OCR_ThuMuc_${new Date().toISOString().slice(0, 10)}.xlsx`,
          },
          { responseType: 'blob' }
        );
      } else {
        throw new Error('Chưa có dữ liệu để xuất Excel. Vui lòng quét hồ sơ trước.');
      }
      const url = window.URL.createObjectURL(new Blob([resp.data]));
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', `OCR_Batch_129Cot_${new Date().toISOString().slice(0, 10)}.xlsx`);
      document.body.appendChild(link);
      link.click();
      link.remove();
    } catch (err: any) {
      const msg = await extractErrorMessage(err, 'Không thể xuất file Excel!');
      alert(msg);
    } finally {
      setExportingExcel(false);
    }
  };

  // Tải trực tiếp file Excel Checkpoint đã xuất tự động sau mỗi 20 file
  const handleDownloadCheckpointExcel = async () => {
    if (!can('export.129')) {
      alert("Tài khoản của bạn cần có vai trò 'Khai thác dữ liệu' (ocr-exporter) để tải file Excel checkpoint.");
      return;
    }
    if (!activeBatchId) return;
    try {
      const resp = await axios.get(`/api/v1/batch/${activeBatchId}/download-excel`, {
        responseType: 'blob',
      });
      const url = window.URL.createObjectURL(new Blob([resp.data]));
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', `BaoCao_129Cot_${activeBatchId}.xlsx`);
      document.body.appendChild(link);
      link.click();
      link.remove();
    } catch (err: any) {
      const msg = await extractErrorMessage(err, 'Chưa có file Excel checkpoint. Vui lòng chờ đến khi quét tối thiểu 10 file.');
      alert(msg);
    }
  };

  // Xem đúng dữ liệu của đợt quét đang mở; không trộn lịch sử từ SQLite.
  const handleView129Table = async () => {
    if (chuyenDoiRows.length > 0) {
      onView129Table(chuyenDoiRows);
      return;
    }
    try {
      if (!activeBatchId) {
        alert('Chưa có đợt quét nào đang mở. Vui lòng quét hồ sơ trước.');
        return;
      }
      const res = await axios.get(`/api/v1/batch/${activeBatchId}/rows-129`);
      const rows = res.data?.rows || [];
      if (rows.length > 0) {
        setChuyenDoiRows(rows);
        onView129Table(rows);
      } else {
        alert('Chưa có dữ liệu để xem bảng 129 cột!');
      }
    } catch (e) {
      alert('Không thể tải dữ liệu bảng 129 cột!');
    }
  };

  // Export JSON
  const handleExportJSON = () => {
    if (results.length === 0) return;
    const blob = new Blob([JSON.stringify(results, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `OCR_Batch_Results_${new Date().toISOString().slice(0, 10)}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const isRunning = isClientProcessing || isServerScanning;

  useEffect(() => {
    onRunningChange?.(isRunning);
  }, [isRunning, onRunningChange]);

  const successCount = results.filter(r => r.status === 'success').length;
  const errorCount = results.filter(r => r.status === 'error').length;
  const avgTimePerFile = processedCount > 0 ? (elapsedSeconds / processedCount).toFixed(1) : '0.0';

  return (
    <div className="space-y-6">
      
      {/* ── HEADER ── */}
      <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-6">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <div className="flex items-center gap-2.5">
              <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-indigo-600 to-indigo-800 flex items-center justify-center text-white shadow-sm">
                <FolderUp size={22} />
              </div>
              <div>
                <h2 className="text-xl font-semibold tracking-tight text-slate-950 leading-tight">
                  Xử lý hồ sơ hàng loạt
                </h2>
                <p className="text-xs text-slate-500 mt-0.5">
                  Chọn cách nạp hồ sơ phù hợp, theo dõi tiến độ và kiểm tra kết quả trước khi xuất.
                </p>
              </div>
            </div>
          </div>

          {/* Mode Switcher */}
          <div className="flex bg-slate-100 p-1 rounded-xl border border-slate-200 text-xs font-semibold">
            <button
              onClick={() => { if (!isRunning) setScanMode('client_folder'); }}
              disabled={isRunning}
              className={`px-3.5 py-2 rounded-lg transition flex items-center gap-1.5 ${
                scanMode === 'client_folder'
                  ? 'bg-white text-indigo-700 shadow-sm font-bold'
                  : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              <FolderUp size={15} />
              <span>Từ máy tính</span>
            </button>
            <button
              onClick={() => { if (!isRunning && !isPairScanning) setScanMode('server_path'); }}
              disabled={isRunning || isPairScanning}
              className={`px-3.5 py-2 rounded-lg transition flex items-center gap-1.5 ${
                scanMode === 'server_path'
                  ? 'bg-white text-indigo-700 shadow-sm font-bold'
                  : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              <Server size={15} />
              <span>Từ máy chủ</span>
            </button>
            {/* TODO: Tạm ẩn chức năng ghép cặp GCN */}
            {false && (
            <button
              onClick={() => { if (!isRunning && !isPairScanning) setScanMode('pair_scan'); }}
              disabled={isRunning || isPairScanning}
              className={`px-3.5 py-2 rounded-lg transition flex items-center gap-1.5 ${
                scanMode === 'pair_scan'
                  ? 'bg-white text-emerald-700 shadow-sm font-bold'
                  : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              <Layers size={15} />
              <span>Ghép GCN & giấy tờ</span>
            </button>
            )}
          </div>
        </div>

        {/* ── CHẾ ĐỘ 1: TẢI THƯ MỤC TỪ MÁY TÍNH ── */}
        {scanMode === 'client_folder' && (
          <div className="mt-6 pt-6 border-t border-slate-100 space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-12 gap-4 items-center">
              <div className="md:col-span-8">
                {/* Drag and Drop / Select Folder Area */}
                <div
                  onClick={() => folderInputRef.current?.click()}
                  className={`border-2 border-dashed rounded-xl p-5 text-center cursor-pointer transition ${
                    clientFiles.length > 0
                      ? 'border-emerald-300 bg-emerald-50/40'
                      : 'border-slate-300 hover:border-indigo-400 bg-slate-50/70 hover:bg-indigo-50/30'
                  }`}
                >
                  <input
                    ref={folderInputRef}
                    type="file"
                    // @ts-ignore
                    webkitdirectory=""
                    directory=""
                    multiple
                    className="hidden"
                    onChange={handleFolderSelect}
                  />
                  <input
                    ref={multiFileInputRef}
                    type="file"
                    multiple
                    accept=".pdf,.png,.jpg,.jpeg"
                    className="hidden"
                    onChange={handleFolderSelect}
                  />

                  <div className="flex items-center justify-center gap-3">
                    <div className="w-10 h-10 rounded-full bg-indigo-100 text-indigo-600 flex items-center justify-center">
                      <FolderOpen size={20} />
                    </div>
                    <div className="text-left">
                      {clientFiles.length > 0 ? (
                        <div>
                          <p className="text-sm font-bold text-slate-800">
                            Đã chọn: <span className="text-emerald-700">{folderName}</span>
                          </p>
                          <p className="text-xs text-slate-500">
                            Tìm thấy <b>{clientFiles.length}</b> file PDF/ảnh hợp lệ (Tổng dung lượng:{' '}
                            {(clientFiles.reduce((acc, f) => acc + f.size, 0) / (1024 * 1024)).toFixed(1)} MB)
                          </p>
                        </div>
                      ) : (
                        <div>
                          <p className="text-sm font-semibold text-slate-800">
                            Nhấn vào đây để chọn thư mục từ máy tính của bạn
                          </p>
                          <p className="text-xs text-slate-500">
                            Hệ thống sẽ tự động quét và lọc các file PDF và ảnh (.pdf, .png, .jpg)
                          </p>
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              </div>

              {/* Action Buttons */}
              <div className="md:col-span-4 flex flex-col gap-2">
                {isClientProcessing ? (
                  <button
                    onClick={stopClientProcessing}
                    className="w-full py-3 bg-rose-600 hover:bg-rose-700 text-white text-sm font-bold rounded-xl shadow-sm transition flex items-center justify-center gap-2"
                  >
                    <Square size={16} />
                    <span>Dừng Tiến Trình</span>
                  </button>
                ) : clientPausedIndex > 0 && clientPausedIndex < clientFiles.length ? (
                  <div className="flex flex-col gap-2">
                    <button
                      onClick={() => startClientProcessing(true)}
                      className="w-full py-3 bg-emerald-600 hover:bg-emerald-700 text-white text-sm font-bold rounded-xl shadow-sm transition flex items-center justify-center gap-2"
                    >
                      <Play size={16} />
                      <span>Tiếp Tục Xử Lý (Từ file {clientPausedIndex + 1}/{clientFiles.length})</span>
                    </button>
                    <button
                      onClick={() => startClientProcessing(false)}
                      className="w-full py-2 bg-slate-100 hover:bg-slate-200 text-slate-700 text-xs font-semibold rounded-lg transition flex items-center justify-center gap-1.5 border border-slate-200"
                    >
                      <RotateCcw size={14} />
                      <span>Quét lại từ đầu</span>
                    </button>
                  </div>
                ) : (
                  <button
                    onClick={() => startClientProcessing(false)}
                    disabled={clientFiles.length === 0}
                    className="w-full py-3 bg-emerald-600 hover:bg-emerald-700 disabled:bg-slate-200 text-white disabled:text-slate-400 text-sm font-bold rounded-xl shadow-sm transition flex items-center justify-center gap-2"
                  >
                    <Play size={16} />
                    <span>Bắt Đầu Xử Lý ({clientFiles.length} files)</span>
                  </button>
                )}

                <div className="flex gap-2">
                  <button
                    onClick={() => folderInputRef.current?.click()}
                    disabled={isRunning}
                    className="flex-1 py-2 bg-slate-100 hover:bg-slate-200 text-slate-700 text-xs font-semibold rounded-lg transition"
                  >
                    Chọn thư mục khác
                  </button>
                  <button
                    onClick={() => multiFileInputRef.current?.click()}
                    disabled={isRunning}
                    className="flex-1 py-2 bg-slate-100 hover:bg-slate-200 text-slate-700 text-xs font-semibold rounded-lg transition"
                  >
                    Chọn từng file
                  </button>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* ── CHẾ ĐỘ 2: QUÉT THƯ MỤC TRÊN MÁY CHỦ ── */}
        {scanMode === 'server_path' && (
          <div className="mt-6 pt-6 border-t border-slate-100 space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-12 gap-3 items-end">
              <div className="md:col-span-7">
                <label className="block text-xs font-semibold text-slate-700 mb-1">
                  Đường dẫn thư mục chứa hồ sơ trên máy chủ:
                </label>
                <input
                  type="text"
                  value={serverPath}
                  onChange={e => setServerPath(e.target.value)}
                  disabled={isRunning}
                  placeholder="Nhập đường dẫn thư mục trên máy chủ"
                  className="w-full text-sm font-mono bg-slate-50 border border-slate-300 rounded-xl px-3.5 py-2.5 text-slate-800 focus:outline-indigo-500"
                />
              </div>

              <div className="md:col-span-2">
                <label className="block text-xs font-semibold text-slate-700 mb-1">Số lượng mẫu:</label>
                <select
                  value={sampleCount}
                  onChange={e => setSampleCount(parseInt(e.target.value))}
                  disabled={isRunning}
                  className="w-full text-sm bg-slate-50 border border-slate-300 rounded-xl px-3 py-2.5 text-slate-800 focus:outline-indigo-500"
                >
                  <option value={0}>Tất cả file</option>
                  <option value={5}>5 file ngẫu nhiên</option>
                  <option value={10}>10 file</option>
                  <option value={20}>20 file</option>
                  <option value={50}>50 file</option>
                  <option value={100}>100 file</option>
                </select>
              </div>

              <div className="md:col-span-3 flex gap-2">
                {isServerScanning ? (
                  <button
                    onClick={stopServerScan}
                    className="flex-1 py-2.5 bg-rose-600 hover:bg-rose-700 text-white text-xs font-bold rounded-xl shadow-sm transition flex items-center justify-center gap-1.5"
                  >
                    <Square size={15} />
                    <span>Dừng Quét</span>
                  </button>
                ) : (batchStatus === 'paused' || batchStatus === 'cancelled') && activeBatchId && processedCount > 0 && processedCount < totalFilesCount ? (
                  <div className="flex-1 flex gap-1.5">
                    <button
                      onClick={() => startServerScan(true)}
                      className="flex-1 py-2.5 bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-bold rounded-xl shadow-sm transition flex items-center justify-center gap-1"
                      title={`Tiếp tục quét từ file ${processedCount + 1}`}
                    >
                      <Play size={14} />
                      <span>Tiếp tục ({processedCount + 1}/{totalFilesCount})</span>
                    </button>
                    <button
                      onClick={() => startServerScan(false)}
                      className="px-2.5 py-2.5 bg-slate-100 hover:bg-slate-200 text-slate-700 text-xs font-semibold rounded-xl transition flex items-center justify-center border border-slate-200"
                      title="Quét lại từ đầu"
                    >
                      <RotateCcw size={14} />
                    </button>
                  </div>
                ) : (
                  <button
                    onClick={() => startServerScan(false)}
                    className="flex-1 py-2.5 bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-bold rounded-xl shadow-sm transition flex items-center justify-center gap-1.5"
                  >
                    <Play size={15} />
                    <span>Bắt Đầu Quét</span>
                  </button>
                )}
              </div>
            </div>

          </div>
        )}

        {/* ── CHẾ ĐỘ 3: QUÉT GHÉP CẶP GCN & GT (CCCD) [MỚI] ── */}
        {scanMode === 'pair_scan' && (
          <div className="mt-6 pt-6 border-t border-slate-100 space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-12 gap-3 items-end">
              <div className="md:col-span-6">
                <label className="block text-xs font-semibold text-slate-700 mb-1">
                  Đường dẫn thư mục chứa hồ sơ (các file dạng *-GCN và *-GT):
                </label>
                <input
                  type="text"
                  value={pairServerPath}
                  onChange={e => setPairServerPath(e.target.value)}
                  disabled={isPairScanning}
                  placeholder="Nhập đường dẫn thư mục chứa các cặp hồ sơ"
                  className="w-full text-sm font-mono bg-slate-50 border border-slate-300 rounded-xl px-3.5 py-2.5 text-slate-800 focus:outline-emerald-500"
                />
              </div>

              <div className="md:col-span-2">
                <label className="block text-xs font-semibold text-slate-700 mb-1">Số lượng mẫu:</label>
                <select
                  value={pairSampleLimit}
                  onChange={e => setPairSampleLimit(parseInt(e.target.value))}
                  disabled={isPairScanning}
                  className="w-full text-sm bg-slate-50 border border-slate-300 rounded-xl px-3 py-2.5 text-slate-800 focus:outline-emerald-500"
                >
                  <option value={0}>Tất cả hồ sơ</option>
                  <option value={2}>2 bộ (chạy thử)</option>
                  <option value={5}>5 bộ mẫu</option>
                  <option value={10}>10 bộ</option>
                  <option value={20}>20 bộ</option>
                  <option value={50}>50 bộ</option>
                </select>
              </div>

              {/* Action Buttons */}
              <div className="md:col-span-4 flex items-center gap-2">
                <button
                  onClick={handlePreviewPairs}
                  disabled={isPairScanning || isPreviewingPairs || !pairServerPath.trim()}
                  className="flex-1 py-2.5 bg-slate-100 hover:bg-slate-200 text-slate-800 text-xs font-bold rounded-xl transition flex items-center justify-center gap-1.5 border border-slate-300"
                >
                  {isPreviewingPairs ? <Loader2 size={15} className="animate-spin" /> : <Search size={15} />}
                  <span>1. Phân Tích Cặp</span>
                </button>

                {!isPairScanning ? (
                  <button
                    onClick={handleStartPairScan}
                    disabled={!pairServerPath.trim()}
                    className="flex-1 py-2.5 bg-emerald-600 hover:bg-emerald-700 disabled:bg-slate-200 text-white disabled:text-slate-400 text-xs font-bold rounded-xl shadow-sm transition flex items-center justify-center gap-1.5"
                  >
                    <Play size={15} />
                    <span>2. Quét & Xuất Excel</span>
                  </button>
                ) : (
                  <button
                    onClick={handleStopPairScan}
                    className="flex-1 py-2.5 bg-rose-600 hover:bg-rose-700 text-white text-xs font-bold rounded-xl shadow-sm transition flex items-center justify-center gap-1.5"
                  >
                    <Square size={15} />
                    <span>Dừng Lại</span>
                  </button>
                )}
              </div>
            </div>

            {/* Thống kê Preview nếu đã phân tích */}
            {pairPreviewData && (
              <div className="mt-3 p-4 bg-emerald-50/50 border border-emerald-200 rounded-xl space-y-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <CheckCircle2 size={18} className="text-emerald-600" />
                    <span className="text-xs font-bold text-emerald-950">
                      Đã phân tích: {pairPreviewData.directory_path}
                    </span>
                  </div>
                  <button
                    onClick={() => setShowPairPreviewModal(!showPairPreviewModal)}
                    className="text-xs font-semibold text-emerald-700 hover:text-emerald-900 underline flex items-center gap-1"
                  >
                    <Eye size={13} />
                    <span>{showPairPreviewModal ? 'Ẩn danh sách cặp' : 'Xem danh sách chi tiết các cặp'}</span>
                  </button>
                </div>

                <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5 text-xs">
                  <div className="bg-white p-2.5 rounded-lg border border-emerald-100 shadow-xs">
                    <span className="text-slate-500 block text-[11px]">Tổng số bộ hồ sơ:</span>
                    <b className="text-slate-800 text-base">{pairPreviewData.total_pairs}</b>
                  </div>
                  <div className="bg-white p-2.5 rounded-lg border border-emerald-100 shadow-xs">
                    <span className="text-emerald-600 block text-[11px]">Đủ cả GCN + CCCD:</span>
                    <b className="text-emerald-700 text-base">{pairPreviewData.both_count} cặp</b>
                  </div>
                  <div className="bg-white p-2.5 rounded-lg border border-emerald-100 shadow-xs">
                    <span className="text-amber-600 block text-[11px]">Chỉ có Sổ Đỏ (GCN):</span>
                    <b className="text-amber-700 text-base">{pairPreviewData.gcn_only_count} file</b>
                  </div>
                  <div className="bg-white p-2.5 rounded-lg border border-emerald-100 shadow-xs">
                    <span className="text-blue-600 block text-[11px]">Chỉ có Giấy tờ (GT):</span>
                    <b className="text-blue-700 text-base">{pairPreviewData.gt_only_count} file</b>
                  </div>
                </div>

                {/* Bảng xem trước danh sách cặp (Toggle) */}
                {showPairPreviewModal && (
                  <div className="max-h-60 overflow-y-auto bg-white rounded-lg border border-slate-200 mt-2">
                    <table className="w-full text-left text-xs">
                      <thead className="bg-slate-50 text-[11px] font-bold text-slate-600 uppercase border-b sticky top-0">
                        <tr>
                          <th className="py-2 px-3 text-center w-12">#</th>
                          <th className="py-2 px-3">Mã hồ sơ</th>
                          <th className="py-2 px-3">File Sổ Đỏ (GCN)</th>
                          <th className="py-2 px-3">File Giấy Tờ (GT)</th>
                          <th className="py-2 px-3 text-center">Tình trạng</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-100">
                        {pairPreviewData.pairs.map((p, pidx) => (
                          <tr key={pidx} className="hover:bg-slate-50">
                            <td className="py-1.5 px-3 text-center text-slate-400 font-mono text-[11px]">{pidx + 1}</td>
                            <td className="py-1.5 px-3 font-bold text-slate-800">{p.pair_id}</td>
                            <td className="py-1.5 px-3 font-mono text-slate-600 text-[11px]">{p.gcn_file || <span className="text-slate-300 font-normal">Không có</span>}</td>
                            <td className="py-1.5 px-3 font-mono text-slate-600 text-[11px]">{p.gt_file || <span className="text-slate-300 font-normal">Không có</span>}</td>
                            <td className="py-1.5 px-3 text-center">
                              <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                                p.status === 'both' ? 'bg-emerald-100 text-emerald-800' : p.status === 'gcn_only' ? 'bg-amber-100 text-amber-800' : 'bg-blue-100 text-blue-800'
                              }`}>
                                {p.status === 'both' ? 'Đủ 2 file' : p.status === 'gcn_only' ? 'Chỉ GCN' : 'Chỉ GT'}
                              </span>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </div>

      {/* ── THÔNG BÁO LỖI NẾU CÓ ── */}
      {errorMessage && (
        <div className="bg-rose-50 border border-rose-200 rounded-xl p-4 flex items-center gap-3 text-rose-800 text-sm">
          <AlertTriangle size={18} className="text-rose-600 shrink-0" />
          <span>{errorMessage}</span>
        </div>
      )}

      {/* ── BẢNG ĐIỀU KHIỂN TIẾN ĐỘ GHÉP CẶP GCN & GT (PAIR SCAN) ── */}
      {scanMode === 'pair_scan' && (isPairScanning || pairBatchStatus !== 'idle') && (
        <div className="bg-white rounded-2xl border border-emerald-200 shadow-sm p-6 space-y-5">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className={`w-3 h-3 rounded-full ${
                isPairScanning ? 'bg-emerald-500 animate-pulse' : pairBatchStatus === 'completed' ? 'bg-emerald-600' : 'bg-amber-500'
              }`} />
              <h3 className="text-base font-bold text-slate-900">
                {isPairScanning
                  ? 'Đang tiến hành bóc tách và ghép cặp hồ sơ GCN - GT...'
                  : pairBatchStatus === 'completed'
                  ? 'Đã hoàn thành toàn bộ thư mục ghép cặp!'
                  : 'Tiến trình tạm dừng'}
              </h3>
            </div>
            <div className="text-xs font-bold text-slate-500">
              Tiến độ: <span className="text-emerald-600 text-sm">{pairProcessedCount}</span> / {pairTotalCount} bộ hồ sơ
            </div>
          </div>

          {/* Progress Bar */}
          <div className="space-y-1.5">
            <div className="flex items-center justify-between text-xs text-slate-600">
              <span className="font-mono truncate max-w-md">
                {isPairScanning ? `Đang xử lý bộ: ${pairCurrentItem}` : pairCurrentItem}
              </span>
              <span className="font-bold text-emerald-600">{pairProgressPercent}%</span>
            </div>
            <div className="w-full bg-slate-100 h-3.5 rounded-full overflow-hidden p-0.5 border border-slate-200">
              <div
                className="bg-gradient-to-r from-emerald-500 to-teal-600 h-full rounded-full transition-all duration-300"
                style={{ width: `${pairProgressPercent}%` }}
              />
            </div>
          </div>

          {/* 4 Cards KPI */}
          <div className="grid grid-cols-2 md:grid-cols-5 gap-3.5">
            <div className="bg-slate-50 rounded-xl p-3.5 border border-slate-200/80 flex items-center gap-3">
              <div className="w-10 h-10 rounded-lg bg-blue-100 text-blue-700 flex items-center justify-center">
                <Files size={20} />
              </div>
              <div>
                <p className="text-[11px] font-semibold text-slate-500">Tổng bộ hồ sơ</p>
                <p className="text-lg font-bold text-slate-800">{pairTotalCount}</p>
              </div>
            </div>

            <div className="bg-emerald-50/60 rounded-xl p-3.5 border border-emerald-200/80 flex items-center gap-3">
              <div className="w-10 h-10 rounded-lg bg-emerald-100 text-emerald-700 flex items-center justify-center">
                <CheckCircle2 size={20} />
              </div>
              <div>
                <p className="text-[11px] font-semibold text-emerald-700">Đã trích xuất</p>
                <p className="text-lg font-bold text-emerald-800">{pairResults.filter(r => r.status === 'ok').length}</p>
              </div>
            </div>

            <div className="bg-indigo-50/60 rounded-xl p-3.5 border border-indigo-200/80 flex items-center gap-3">
              <div className="w-10 h-10 rounded-lg bg-indigo-100 text-indigo-700 flex items-center justify-center">
                <Clock size={20} />
              </div>
              <div>
                <p className="text-[11px] font-semibold text-indigo-700">Thời gian chạy</p>
                <p className="text-lg font-bold text-indigo-800">{pairElapsedSeconds}s</p>
              </div>
            </div>

            <div className="bg-teal-50/60 rounded-xl p-3.5 border border-teal-200/80 flex items-center gap-3">
              <div className="w-10 h-10 rounded-lg bg-teal-100 text-teal-700 flex items-center justify-center">
                <RefreshCw size={20} />
              </div>
              <div>
                <p className="text-[11px] font-semibold text-teal-700">Tốc độ xử lý</p>
                <p className="text-lg font-bold text-teal-800">{pairSpeed} cặp/phút</p>
              </div>
            </div>

            <div className="bg-amber-50/60 rounded-xl p-3.5 border border-amber-200/80 flex items-center gap-3">
              <div className="w-10 h-10 rounded-lg bg-amber-100 text-amber-700 flex items-center justify-center">
                <AlertTriangle size={20} />
              </div>
              <div>
                <p className="text-[11px] font-semibold text-amber-700">CCCD cần duyệt</p>
                <p className="text-lg font-bold text-amber-800">{pairCccdAuditSummary.review_required || 0}</p>
              </div>
            </div>
          </div>

          {/* Action Bar */}
          <div className="flex flex-wrap items-center justify-between gap-3 pt-4 border-t border-slate-100">
            <div className="text-xs text-slate-500">
              {pairExcelReady ? (
                <span className="text-emerald-700 font-semibold flex items-center gap-1.5">
                  <CheckCircle2 size={14} className="text-emerald-600" />
                  Bảng dữ liệu đã sẵn sàng để tải.
                </span>
              ) : (
                <span>Đang xử lý và cập nhật kết quả...</span>
              )}
            </div>

            <div className="flex items-center gap-2">
              <button
                onClick={handleExportPairExcel129}
                disabled={!pairExcelReady}
                className="px-5 py-2.5 bg-emerald-600 hover:bg-emerald-700 disabled:bg-slate-200 text-white disabled:text-slate-400 text-xs font-bold rounded-xl transition flex items-center gap-2 shadow-sm"
              >
                <Download size={15} />
                <span>Xuất File Excel (129 Cột)</span>
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── BẢNG KẾT QUẢ QUÉT GHÉP CẶP (PAIR RESULTS TABLE) ── */}
      {scanMode === 'pair_scan' && pairResults.length > 0 && (
        <div className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
          <div className="px-6 py-4 border-b border-slate-100 flex items-center justify-between">
            <h4 className="text-sm font-bold text-slate-800 flex items-center gap-2">
              <FileSpreadsheet size={16} className="text-emerald-600" />
              <span>Danh Sách Cặp Hồ Sơ Đã Ghép & Điền Vào 129 Cột ({pairResults.length})</span>
            </h4>
            <span className="text-xs text-slate-400">
              Cập nhật trực tiếp theo thời gian thực
            </span>
          </div>

          <div className="overflow-x-auto max-h-[500px]">
            <table className="w-full text-left text-xs text-slate-700 border-collapse">
              <thead className="bg-slate-50 text-[11px] font-bold text-slate-600 uppercase tracking-wider sticky top-0 z-10 border-b border-slate-200">
                <tr>
                  <th className="py-2.5 px-3 w-12 text-center">STT</th>
                  <th className="py-2.5 px-3 min-w-[120px]">Mã Hồ Sơ</th>
                  <th className="py-2.5 px-3 min-w-[160px]">Chủ đất (từ CCCD)</th>
                  <th className="py-2.5 px-3 min-w-[110px]">Số CCCD</th>
                  <th className="py-2.5 px-3 w-20 text-center">Ngày sinh</th>
                  <th className="py-2.5 px-3 w-20 text-center">Giới tính</th>
                  <th className="py-2.5 px-3 w-24 text-center">Thửa / Tờ</th>
                  <th className="py-2.5 px-3 w-24 text-right">Diện tích (m²)</th>
                  <th className="py-2.5 px-3 min-w-[160px]">Địa chỉ thường trú</th>
                  <th className="py-2.5 px-3 w-28 text-center">Đối soát CCCD</th>
                  <th className="py-2.5 px-3 w-20 text-right">Thời gian</th>
                  <th className="py-2.5 px-3 w-24 text-center">Trạng thái</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 font-medium">
                {pairResults.map((item, idx) => (
                  <tr key={idx} className="hover:bg-slate-50 transition">
                    <td className="py-2.5 px-3 text-center text-slate-400 font-mono text-[11px]">{item.stt}</td>
                    <td className="py-2.5 px-3 font-bold text-slate-900">{item.pair_id}</td>
                    <td className="py-2.5 px-3 font-semibold text-emerald-800">{item.chu_ho_ten || '-'}</td>
                    <td className="py-2.5 px-3 font-mono text-[11px] text-slate-700">{item.so_cccd || '-'}</td>
                    <td className="py-2.5 px-3 text-center font-mono text-[11px]">{item.ngay_sinh || '-'}</td>
                    <td className="py-2.5 px-3 text-center">{item.gioi_tinh || '-'}</td>
                    <td className="py-2.5 px-3 text-center font-mono text-[11px]">
                      {item.so_thua ? `${item.so_thua} / ${item.to_ban_do || '-'}` : '-'}
                    </td>
                    <td className="py-2.5 px-3 text-right font-bold text-slate-800">{item.dien_tich || '-'}</td>
                    <td className="py-2.5 px-3 text-slate-600 truncate max-w-[200px]" title={item.dia_chi_thuong_tru}>
                      {item.dia_chi_thuong_tru || '-'}
                    </td>
                    <td className="py-2.5 px-3 text-center">
                      {item.cccd_audit ? (
                        <button
                          type="button"
                          disabled={!item.cccd_audit.crop_url}
                          onClick={() => item.cccd_audit.crop_url && void downloadProtectedArtifact(item.cccd_audit.crop_url, `${item.pair_id}_cccd-crop.png`)}
                          title={item.cccd_audit.reason || 'Đối soát lại từ ảnh crop CCCD'}
                          className={`inline-flex px-2 py-0.5 rounded text-[10px] font-bold border ${
                            item.cccd_audit.status === 'supported'
                              ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                              : item.cccd_audit.status === 'review_required'
                              ? 'bg-amber-50 text-amber-700 border-amber-200'
                              : 'bg-slate-50 text-slate-500 border-slate-200'
                          }`}
                        >
                          {item.cccd_audit.status === 'supported'
                            ? 'Khớp crop'
                            : item.cccd_audit.status === 'review_required'
                            ? 'Cần duyệt'
                            : 'Chưa có crop'}
                        </button>
                      ) : '-'}
                    </td>
                    <td className="py-2.5 px-3 text-right text-slate-500 font-mono text-[11px]">{item.elapsed_seconds}s</td>
                    <td className="py-2.5 px-3 text-center">
                      <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                        item.status === 'ok' ? 'bg-emerald-50 text-emerald-700 border border-emerald-200' : 'bg-rose-50 text-rose-700 border border-rose-200'
                      }`}>
                        {item.status === 'ok' ? 'Thành công' : 'Lỗi'}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* ── BẢNG ĐIỀU KHIỂN TIẾN ĐỘ THỜI GIAN THỰC (ĐƠN LẺ) ── */}
      {scanMode !== 'pair_scan' && (isRunning || batchStatus !== 'idle') && (
        <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-6 space-y-5">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className={`w-3 h-3 rounded-full ${
                isRunning
                  ? 'bg-indigo-500 animate-pulse'
                  : batchStatus === 'completed'
                  ? 'bg-emerald-500'
                  : batchStatus === 'paused' || batchStatus === 'cancelled'
                  ? 'bg-amber-500'
                  : 'bg-slate-400'
              }`} />
              <h3 className="text-base font-bold text-slate-900">
                {isRunning
                  ? 'Đang tiến hành nhận dạng OCR hàng loạt...'
                  : batchStatus === 'completed'
                  ? 'Đã hoàn thành toàn bộ thư mục!'
                  : (batchStatus === 'paused' || batchStatus === 'cancelled') && processedCount > 0
                  ? `Đang tạm dừng tại file ${processedCount + 1}/${totalFilesCount} (Kết quả đã xử lý được lưu an toàn)`
                  : 'Tiến trình tạm dừng'}
              </h3>
            </div>
            <div className="text-xs font-bold text-slate-500">
              Tiến độ: <span className="text-indigo-600 text-sm">{processedCount}</span> / {totalFilesCount} hồ sơ
            </div>
          </div>

          {/* Progress Bar */}
          <div className="space-y-1.5">
            <div className="flex items-center justify-between text-xs text-slate-600">
              <span className="font-mono truncate max-w-md">
                {isRunning
                  ? `Đang xử lý: ${currentFileName}`
                  : (batchStatus === 'paused' || batchStatus === 'cancelled') && processedCount > 0
                  ? `Tạm dừng sau file thứ ${processedCount}. Bạn có thể bấm Tiếp tục để chạy tiếp.`
                  : currentFileName}
              </span>
              <span className="font-bold text-indigo-600">{progressPercent}%</span>
            </div>
            <div className="w-full bg-slate-100 h-3.5 rounded-full overflow-hidden p-0.5 border border-slate-200">
              <div
                className="bg-gradient-to-r from-indigo-500 via-emerald-500 to-emerald-600 h-full rounded-full transition-all duration-300"
                style={{ width: `${progressPercent}%` }}
              />
            </div>
          </div>

          {/* 4 Cards Thống Kê KPI */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3.5">
            <div className="bg-slate-50 rounded-xl p-3.5 border border-slate-200/80 flex items-center gap-3">
              <div className="w-10 h-10 rounded-lg bg-blue-100 text-blue-700 flex items-center justify-center">
                <Files size={20} />
              </div>
              <div>
                <p className="text-[11px] font-semibold text-slate-500">Tổng số hồ sơ</p>
                <p className="text-lg font-bold text-slate-800">{totalFilesCount}</p>
              </div>
            </div>

            <div className="bg-emerald-50/60 rounded-xl p-3.5 border border-emerald-200/80 flex items-center gap-3">
              <div className="w-10 h-10 rounded-lg bg-emerald-100 text-emerald-700 flex items-center justify-center">
                <CheckCircle2 size={20} />
              </div>
              <div>
                <p className="text-[11px] font-semibold text-emerald-700">Trích xuất hợp lệ</p>
                <p className="text-lg font-bold text-emerald-800">{successCount}</p>
              </div>
            </div>

            <div className="bg-rose-50/60 rounded-xl p-3.5 border border-rose-200/80 flex items-center gap-3">
              <div className="w-10 h-10 rounded-lg bg-rose-100 text-rose-700 flex items-center justify-center">
                <AlertTriangle size={20} />
              </div>
              <div>
                <p className="text-[11px] font-semibold text-rose-700">Lỗi / Cảnh báo</p>
                <p className="text-lg font-bold text-rose-800">{errorCount}</p>
              </div>
            </div>

            <div className="bg-indigo-50/60 rounded-xl p-3.5 border border-indigo-200/80 flex items-center gap-3">
              <div className="w-10 h-10 rounded-lg bg-indigo-100 text-indigo-700 flex items-center justify-center">
                <Clock size={20} />
              </div>
              <div>
                <p className="text-[11px] font-semibold text-indigo-700">Thời gian TB / file</p>
                <p className="text-lg font-bold text-indigo-800">{avgTimePerFile}s</p>
              </div>
            </div>
          </div>

          {/* Action Bar khi đã có kết quả */}
          {results.length > 0 && (
            <div className="flex flex-wrap items-center justify-between gap-3 pt-4 border-t border-slate-100">
              <div className="text-xs text-slate-500 flex flex-wrap items-center gap-2">
                <span>Đã xử lý <b>{results.length}</b> hồ sơ.</span>
                {lastCheckpointIdx > 0 && (
                  <span className="px-2.5 py-1 bg-emerald-50 text-emerald-700 rounded-lg font-medium border border-emerald-200 text-xs flex items-center gap-1.5">
                    <CheckCircle2 size={13} />
                    <span>{lastCheckpointMsg || `Đã cập nhật kết quả cho ${lastCheckpointIdx} hồ sơ`}</span>
                  </span>
                )}
              </div>

              <div className="flex items-center gap-2">
                {activeBatchId && (lastCheckpointIdx > 0 || checkpointExcelUrl) && (
                  <button
                    onClick={handleDownloadCheckpointExcel}
                    className="px-4 py-2 bg-teal-600 hover:bg-teal-700 text-white text-xs font-bold rounded-xl transition flex items-center gap-1.5 shadow-sm"
                    title="Tải bảng dữ liệu đã cập nhật gần nhất"
                  >
                    <Download size={14} />
                    <span>Tải Excel ({lastCheckpointIdx} hồ sơ)</span>
                  </button>
                )}

                <button
                  onClick={handleView129Table}
                  disabled={results.length === 0 && chuyenDoiRows.length === 0}
                  className="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 disabled:bg-slate-200 text-white disabled:text-slate-400 text-xs font-bold rounded-xl transition flex items-center gap-1.5 shadow-sm"
                >
                  <span>Xem Trên Bảng 129 Cột</span>
                  <ArrowRight size={14} />
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      {/* ── BẢNG DANH SÁCH KẾT QUẢ TỪNG HỒ SƠ ── */}
      {scanMode !== 'pair_scan' && results.length > 0 && (
        <div className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
          <div className="px-6 py-4 border-b border-slate-100 flex items-center justify-between">
            <h4 className="text-sm font-bold text-slate-800 flex items-center gap-2">
              <FileText size={16} className="text-indigo-600" />
              <span>Danh Sách Hồ Sơ Đã Xử Lý ({results.length})</span>
            </h4>
            <span className="text-xs text-slate-400">
              Cập nhật trực tiếp theo thời gian thực
            </span>
          </div>

          <div className="overflow-x-auto max-h-[500px]">
            <table className="w-full text-left text-xs text-slate-700 border-collapse">
              <thead className="bg-slate-50 text-[11px] font-bold text-slate-600 uppercase tracking-wider sticky top-0 z-10 border-b border-slate-200">
                <tr>
                  <th className="py-2.5 px-3 w-12 text-center">STT</th>
                  <th className="py-2.5 px-3 min-w-[160px]">Tên file</th>
                  <th className="py-2.5 px-3 w-20 text-center">Mẫu</th>
                  <th className="py-2.5 px-3 min-w-[120px]">Số phát hành</th>
                  <th className="py-2.5 px-3 min-w-[180px]">Họ tên chủ 1</th>
                  <th className="py-2.5 px-3 min-w-[110px]">CMND/CCCD</th>
                  <th className="py-2.5 px-3 w-24 text-center">Thửa / Tờ</th>
                  <th className="py-2.5 px-3 w-24 text-right">Diện tích (m²)</th>
                  <th className="py-2.5 px-3 w-20 text-right">Thời gian</th>
                  <th className="py-2.5 px-3 w-28 text-center">Trạng thái</th>
                  <th className="py-2.5 px-3 w-40 text-center">Tra soát & dữ liệu thô</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 font-medium">
                {results.map((item, idx) => (
                  <tr key={idx} className="hover:bg-slate-50 transition">
                    <td className="py-2.5 px-3 text-center text-slate-400 font-mono text-[11px]">
                      {item.stt}
                    </td>
                    <td className="py-2.5 px-3" title={item.file_name}>
                      <button
                        type="button"
                        disabled={!item.document_id}
                        onClick={() => item.document_id && setReviewDocumentId(item.document_id)}
                        className="block max-w-[200px] truncate text-left font-semibold text-slate-900 transition hover:text-emerald-700 hover:underline disabled:cursor-not-allowed disabled:hover:text-slate-900 disabled:hover:no-underline"
                        title={item.document_id ? 'Mở tra soát nhanh hồ sơ' : 'Hồ sơ chưa có dữ liệu tra soát'}
                      >
                        {item.file_name}
                      </button>
                    </td>
                    <td className="py-2.5 px-3 text-center">
                      <span className="px-1.5 py-0.5 rounded text-[10px] font-bold bg-slate-100 text-slate-700">
                        {item.mau || '-'}
                      </span>
                    </td>
                    <td className="py-2.5 px-3 font-bold text-emerald-800">
                      <button
                        type="button"
                        disabled={!item.document_id}
                        onClick={() => item.document_id && setReviewDocumentId(item.document_id)}
                        className="transition hover:underline disabled:cursor-not-allowed disabled:hover:no-underline"
                        title={item.document_id ? 'Mở tra soát nhanh hồ sơ' : 'Hồ sơ chưa có dữ liệu tra soát'}
                      >
                        {item.so_phat_hanh || '-'}
                      </button>
                    </td>
                    <td className="py-2.5 px-3 font-semibold text-slate-800 truncate max-w-[180px]" title={item.ten_chu}>
                      {item.ten_chu || '-'}
                    </td>
                    <td className="py-2.5 px-3 font-mono text-[11px] text-slate-700">
                      {item.cmnd || '-'}
                    </td>
                    <td className="py-2.5 px-3 text-center font-mono text-[11px]">
                      {item.so_thua ? `${item.so_thua} / ${item.to_ban_do || '?'}` : '-'}
                    </td>
                    <td className="py-2.5 px-3 text-right font-bold text-slate-800">
                      {item.dien_tich || '-'}
                    </td>
                    <td className="py-2.5 px-3 text-right font-mono text-slate-500">
                      {item.elapsed_seconds ? `${item.elapsed_seconds}s` : '-'}
                    </td>
                    <td className="py-2.5 px-3 text-center">
                      {item.status === 'success' ? (
                        <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-100 text-emerald-800">
                          <Check size={11} className="mr-1" /> Hợp lệ
                        </span>
                      ) : (
                        <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold bg-rose-100 text-rose-800" title={item.error}>
                          <AlertTriangle size={11} className="mr-1" /> Lỗi
                        </span>
                      )}
                    </td>
                    <td className="py-2.5 px-3 text-center">
                      <div className="flex items-center justify-center gap-1">
                        <button
                          type="button"
                          disabled={!item.document_id}
                          onClick={() => item.document_id && setReviewDocumentId(item.document_id)}
                          className="px-2.5 py-1 bg-emerald-50 hover:bg-emerald-100 text-emerald-700 rounded-lg text-[11px] font-semibold inline-flex items-center gap-1 transition disabled:cursor-not-allowed disabled:opacity-50"
                          title="Xem ảnh trang, crop và box OCR"
                        >
                          <Eye size={12} />
                          <span>Tra soát</span>
                        </button>
                        <button
                          onClick={() => {
                            const md = item.raw_ocr_markdown || item.data?.raw_ocr_markdown || '';
                            setViewingMarkdownItem({
                              fileName: item.file_name,
                              content: md || '# Không tìm thấy dữ liệu thô Markdown cho hồ sơ này.'
                            });
                          }}
                          className="px-2.5 py-1 bg-indigo-50 hover:bg-indigo-100 text-indigo-700 rounded-lg text-[11px] font-semibold inline-flex items-center gap-1 transition"
                          title="Xem văn bản OCR thô dạng Markdown"
                        >
                          <FileCode size={12} />
                          <span>Markdown</span>
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* ── MODAL XEM NHANH MARKDOWN THÔ TRONG BATCH ── */}
      {viewingMarkdownItem && (
        <div className="fixed inset-0 z-50 bg-slate-900/60 backdrop-blur-sm flex items-center justify-center p-4 sm:p-6 animate-in fade-in duration-200">
          <div className="bg-white rounded-2xl max-w-4xl w-full h-[85vh] flex flex-col shadow-2xl border border-slate-200 overflow-hidden">
            <div className="px-6 py-4 border-b border-slate-200 bg-slate-50 flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="w-9 h-9 rounded-lg bg-indigo-600 flex items-center justify-center text-white shadow-sm">
                  <FileCode size={18} />
                </div>
                <div>
                  <h3 className="text-sm font-bold text-slate-900">Nội Dung Markdown Thô (Raw OCR)</h3>
                  <p className="text-xs text-slate-500 font-mono truncate max-w-md">{viewingMarkdownItem.fileName}</p>
                </div>
              </div>

              <div className="flex items-center gap-2">
                <button
                  onClick={() => {
                    navigator.clipboard.writeText(viewingMarkdownItem.content);
                    setCopiedMd(true);
                    setTimeout(() => setCopiedMd(false), 2000);
                  }}
                  className="px-3 py-1.5 bg-white hover:bg-slate-100 border border-slate-200 text-slate-700 text-xs font-semibold rounded-xl transition flex items-center gap-1.5 shadow-sm"
                >
                  {copiedMd ? <Check size={14} className="text-emerald-600" /> : <Copy size={14} />}
                  <span>{copiedMd ? 'Đã sao chép!' : 'Sao chép'}</span>
                </button>

                <button
                  onClick={() => {
                    const blob = new Blob([viewingMarkdownItem.content], { type: 'text/markdown;charset=utf-8' });
                    const url = URL.createObjectURL(blob);
                    const a = document.createElement('a');
                    a.href = url;
                    const baseName = viewingMarkdownItem.fileName.replace(/\.[^/.]+$/, '');
                    a.download = `${baseName}_raw_ocr.md`;
                    a.click();
                    URL.revokeObjectURL(url);
                  }}
                  className="px-3 py-1.5 bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-semibold rounded-xl transition flex items-center gap-1.5 shadow-sm"
                >
                  <Download size={14} />
                  <span>Tải .md</span>
                </button>

                <button
                  onClick={() => setViewingMarkdownItem(null)}
                  className="p-1.5 text-slate-400 hover:text-slate-700 hover:bg-slate-200 rounded-xl transition ml-1"
                >
                  <X size={18} />
                </button>
              </div>
            </div>

            <div className="flex-1 p-6 overflow-y-auto bg-slate-950 text-slate-200 font-mono text-xs leading-relaxed selection:bg-indigo-600 selection:text-white">
              <pre className="whitespace-pre-wrap break-words font-mono">
                {viewingMarkdownItem.content}
              </pre>
            </div>

            <div className="px-6 py-3 border-t border-slate-200 bg-slate-50 flex items-center justify-end text-xs">
              <button
                onClick={() => setViewingMarkdownItem(null)}
                className="px-4 py-1.5 bg-slate-200 hover:bg-slate-300 text-slate-700 font-semibold rounded-lg transition"
              >
                Đóng
              </button>
            </div>
          </div>
        </div>
      )}
      {reviewDocumentId && (
        <QuickReviewPanel documentId={reviewDocumentId} onClose={() => setReviewDocumentId(null)} />
      )}
    </div>
  );
};
