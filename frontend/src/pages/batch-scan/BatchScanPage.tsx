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
  X
} from 'lucide-react';
import { BatchItemSummary, BatchProgressResponse } from '../../shared/types';

interface BatchScanPageProps {
  onView129Table: (rows: Record<string, any>[]) => void;
}

export const BatchScanPage: React.FC<BatchScanPageProps> = ({ onView129Table }) => {
  const [scanMode, setScanMode] = useState<'client_folder' | 'server_path'>('client_folder');

  // Client Folder Upload State
  const [clientFiles, setClientFiles] = useState<File[]>([]);
  const [folderName, setFolderName] = useState<string>('');
  const [isClientProcessing, setIsClientProcessing] = useState<boolean>(false);
  const abortControllerRef = useRef<AbortController | null>(null);

  // Server Path State
  const [serverPath, setServerPath] = useState<string>('D:\\Tho\\OCR\\DataOCR\\Ho so quet_VINHYEN');
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
  const [batchStatus, setBatchStatus] = useState<'idle' | 'running' | 'completed' | 'cancelled' | 'error'>('idle');
  const [results, setResults] = useState<BatchItemSummary[]>([]);
  const [chuyenDoiRows, setChuyenDoiRows] = useState<Record<string, any>[]>([]);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [exportingExcel, setExportingExcel] = useState<boolean>(false);
  const [lastCheckpointIdx, setLastCheckpointIdx] = useState<number>(0);
  const [checkpointExcelUrl, setCheckpointExcelUrl] = useState<string | null>(null);
  const [lastCheckpointMsg, setLastCheckpointMsg] = useState<string | null>(null);
  const [viewingMarkdownItem, setViewingMarkdownItem] = useState<{ fileName: string; content: string } | null>(null);
  const [copiedMd, setCopiedMd] = useState<boolean>(false);

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

  // Run Client Folder Processing sequentially
  const startClientProcessing = async () => {
    if (clientFiles.length === 0) return;

    setIsClientProcessing(true);
    setBatchStatus('running');
    setErrorMessage(null);
    setResults([]);
    setChuyenDoiRows([]);
    setProgressPercent(0);
    setProcessedCount(0);

    const abortController = new AbortController();
    abortControllerRef.current = abortController;

    const tStart = Date.now();
    const tempResults: BatchItemSummary[] = [];
    const tempRows: Record<string, any>[] = [];

    for (let i = 0; i < clientFiles.length; i++) {
      if (abortController.signal.aborted) {
        setBatchStatus('cancelled');
        break;
      }

      const file = clientFiles[i];
      setCurrentFileName(file.name);
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
      } catch (err: any) {
        if (axios.isCancel(err)) {
          setBatchStatus('cancelled');
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
    }
  };

  const stopClientProcessing = () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      setIsClientProcessing(false);
      setBatchStatus('cancelled');
    }
  };

  // Run Server Path Batch Scanning
  const startServerScan = async () => {
    if (!serverPath.trim()) {
      alert('Vui lòng nhập đường dẫn thư mục máy chủ!');
      return;
    }

    setIsServerScanning(true);
    setBatchStatus('running');
    setErrorMessage(null);
    setResults([]);
    setChuyenDoiRows([]);
    setProgressPercent(0);
    setProcessedCount(0);

    try {
      const res = await axios.post('/api/v1/batch/scan-directory', {
        directory_path: serverPath.trim(),
        sample_count: sampleCount,
        split_a3: true,
        smart_gcn_filter: true,
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
            setBatchStatus('cancelled');
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
        setBatchStatus('cancelled');
      } catch (err) {
        console.error('Lỗi hủy batch:', err);
      }
    }
  };

  // Export Excel 129 Columns (On-Demand từ Markdown đã lưu)
  const handleExportExcel = async () => {
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
          '/api/v1/exports/excel',
          {
            rows: chuyenDoiRows,
            file_name: `OCR_ThuMuc_${new Date().toISOString().slice(0, 10)}.xlsx`,
          },
          { responseType: 'blob' }
        );
      } else {
        const rowRes = await axios.get('/api/v1/raw-ocr/to-129-rows?limit=2000');
        const rows = rowRes.data?.rows || [];
        if (rows.length === 0) throw new Error('Chưa có dữ liệu Markdown để xuất Excel');
        resp = await axios.post(
          '/api/v1/exports/excel',
          {
            rows,
            file_name: `OCR_ThuMuc_${new Date().toISOString().slice(0, 10)}.xlsx`,
          },
          { responseType: 'blob' }
        );
      }
      const url = window.URL.createObjectURL(new Blob([resp.data]));
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', `OCR_Batch_129Cot_${new Date().toISOString().slice(0, 10)}.xlsx`);
      document.body.appendChild(link);
      link.click();
      link.remove();
    } catch (err: any) {
      alert(err.response?.data?.detail || 'Không thể xuất file Excel!');
    } finally {
      setExportingExcel(false);
    }
  };

  // Tải trực tiếp file Excel Checkpoint đã xuất tự động sau mỗi 20 file
  const handleDownloadCheckpointExcel = async () => {
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
      alert(err.response?.data?.detail || 'Chưa có file Excel checkpoint. Vui lòng chờ đến khi quét tối thiểu 20 file.');
    }
  };

  // Xem trên bảng 129 cột (On-Demand từ Markdown)
  const handleView129Table = async () => {
    if (chuyenDoiRows.length > 0) {
      onView129Table(chuyenDoiRows);
      return;
    }
    try {
      const res = await axios.get('/api/v1/raw-ocr/to-129-rows?limit=2000');
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
  const successCount = results.filter(r => r.status === 'success').length;
  const errorCount = results.filter(r => r.status === 'error').length;
  const avgTimePerFile = processedCount > 0 ? (elapsedSeconds / processedCount).toFixed(1) : '0.0';

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6 space-y-6">
      
      {/* ── HEADER ── */}
      <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-6">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <div className="flex items-center gap-2.5">
              <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-indigo-600 to-indigo-800 flex items-center justify-center text-white shadow-sm">
                <FolderUp size={22} />
              </div>
              <div>
                <h2 className="text-xl font-bold text-slate-900 leading-tight">
                  Quét Thư Mục & Xử Lý Hàng Loạt (Batch OCR)
                </h2>
                <p className="text-xs text-slate-500 mt-0.5">
                  Tải cả thư mục từ máy tính hoặc quét đệ quy thư mục máy chủ (Zero-OOM Pipeline)
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
              <span>Tải Thư Mục Từ Máy Tính</span>
            </button>
            <button
              onClick={() => { if (!isRunning) setScanMode('server_path'); }}
              disabled={isRunning}
              className={`px-3.5 py-2 rounded-lg transition flex items-center gap-1.5 ${
                scanMode === 'server_path'
                  ? 'bg-white text-indigo-700 shadow-sm font-bold'
                  : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              <Server size={15} />
              <span>Quét Thư Mục Máy Chủ</span>
            </button>
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
                {!isClientProcessing ? (
                  <button
                    onClick={startClientProcessing}
                    disabled={clientFiles.length === 0}
                    className="w-full py-3 bg-emerald-600 hover:bg-emerald-700 disabled:bg-slate-200 text-white disabled:text-slate-400 text-sm font-bold rounded-xl shadow-sm transition flex items-center justify-center gap-2"
                  >
                    <Play size={16} />
                    <span>Bắt Đầu Xử Lý ({clientFiles.length} files)</span>
                  </button>
                ) : (
                  <button
                    onClick={stopClientProcessing}
                    className="w-full py-3 bg-rose-600 hover:bg-rose-700 text-white text-sm font-bold rounded-xl shadow-sm transition flex items-center justify-center gap-2"
                  >
                    <Square size={16} />
                    <span>Dừng Tiến Trình</span>
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
                  placeholder="VD: D:\Tho\OCR\DataOCR\Ho so quet_VINHYEN"
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
                {!isServerScanning ? (
                  <button
                    onClick={startServerScan}
                    className="flex-1 py-2.5 bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-bold rounded-xl shadow-sm transition flex items-center justify-center gap-1.5"
                  >
                    <Play size={15} />
                    <span>Bắt Đầu Quét</span>
                  </button>
                ) : (
                  <button
                    onClick={stopServerScan}
                    className="flex-1 py-2.5 bg-rose-600 hover:bg-rose-700 text-white text-xs font-bold rounded-xl shadow-sm transition flex items-center justify-center gap-1.5"
                  >
                    <Square size={15} />
                    <span>Dừng Quét</span>
                  </button>
                )}
              </div>
            </div>

            {/* Quick Suggestions */}
            <div className="flex flex-wrap items-center gap-2 text-xs">
              <span className="text-slate-500 font-medium">Gợi ý đường dẫn:</span>
              <button
                onClick={() => setServerPath('D:\\Tho\\OCR\\DataOCR\\Ho so quet_VINHYEN')}
                className="px-2.5 py-1 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-lg font-mono text-[11px] transition"
              >
                📁 Ho so quet_VINHYEN (50 Sổ Vĩnh Yên)
              </button>
              <button
                onClick={() => setServerPath('D:\\Tho\\OCR\\DataOCR\\Du Hang sau VILG\\ClearData')}
                className="px-2.5 py-1 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-lg font-mono text-[11px] transition"
              >
                📁 Du Hang sau VILG\\ClearData
              </button>
            </div>
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

      {/* ── BẢNG ĐIỀU KHIỂN TIẾN ĐỘ THỜI GIAN THỰC ── */}
      {(isRunning || batchStatus !== 'idle') && (
        <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-6 space-y-5">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className={`w-3 h-3 rounded-full ${
                isRunning ? 'bg-indigo-500 animate-pulse' : batchStatus === 'completed' ? 'bg-emerald-500' : 'bg-amber-500'
              }`} />
              <h3 className="text-base font-bold text-slate-900">
                {isRunning
                  ? 'Đang tiến hành nhận dạng OCR hàng loạt...'
                  : batchStatus === 'completed'
                  ? 'Đã hoàn thành toàn bộ thư mục!'
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
                {isRunning ? `Đang xử lý: ${currentFileName}` : currentFileName}
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
                <span>Đã lưu ảnh crop & Markdown: <b>{results.length}</b> hồ sơ.</span>
                {lastCheckpointIdx > 0 && (
                  <span className="px-2.5 py-1 bg-emerald-50 text-emerald-700 rounded-lg font-medium border border-emerald-200 text-xs flex items-center gap-1.5">
                    <CheckCircle2 size={13} />
                    <span>{lastCheckpointMsg || `Checkpoint: Đã lưu ${lastCheckpointIdx} hồ sơ vào Excel & Reset RAM`}</span>
                  </span>
                )}
              </div>

              <div className="flex items-center gap-2">
                {activeBatchId && (lastCheckpointIdx > 0 || checkpointExcelUrl) && (
                  <button
                    onClick={handleDownloadCheckpointExcel}
                    className="px-4 py-2 bg-teal-600 hover:bg-teal-700 text-white text-xs font-bold rounded-xl transition flex items-center gap-1.5 shadow-sm"
                    title="Tải ngay file Excel 129 cột đã lưu tại checkpoint gần nhất"
                  >
                    <Download size={14} />
                    <span>Tải Excel Checkpoint ({lastCheckpointIdx} hồ sơ)</span>
                  </button>
                )}

                <button
                  onClick={handleExportJSON}
                  className="px-3.5 py-2 bg-slate-100 hover:bg-slate-200 text-slate-700 text-xs font-semibold rounded-xl transition flex items-center gap-1.5"
                >
                  <Download size={14} /> JSON
                </button>

                <button
                  onClick={handleExportExcel}
                  disabled={exportingExcel || (results.length === 0 && chuyenDoiRows.length === 0)}
                  className="px-4 py-2 bg-emerald-600 hover:bg-emerald-700 disabled:bg-slate-200 text-white disabled:text-slate-400 text-xs font-bold rounded-xl transition flex items-center gap-1.5 shadow-sm"
                  title="Chuyển đổi on-demand từ Markdown sang Excel 129 cột"
                >
                  {exportingExcel ? <Loader2 size={14} className="animate-spin" /> : <FileSpreadsheet size={14} />}
                  <span>Chuyển đổi sang Excel (129 Cột)</span>
                </button>

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
      {results.length > 0 && (
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
                  <th className="py-2.5 px-3 w-24 text-center">Dữ liệu thô</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 font-medium">
                {results.map((item, idx) => (
                  <tr key={idx} className="hover:bg-slate-50 transition">
                    <td className="py-2.5 px-3 text-center text-slate-400 font-mono text-[11px]">
                      {item.stt}
                    </td>
                    <td className="py-2.5 px-3 font-semibold text-slate-900 truncate max-w-[200px]" title={item.file_name}>
                      {item.file_name}
                    </td>
                    <td className="py-2.5 px-3 text-center">
                      <span className="px-1.5 py-0.5 rounded text-[10px] font-bold bg-slate-100 text-slate-700">
                        {item.mau || '-'}
                      </span>
                    </td>
                    <td className="py-2.5 px-3 font-bold text-emerald-800">
                      {item.so_phat_hanh || '-'}
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
    </div>
  );
};
