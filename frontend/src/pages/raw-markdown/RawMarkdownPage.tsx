import React, { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import {
  FileText,
  Search,
  RefreshCw,
  Download,
  Eye,
  Trash2,
  Copy,
  Check,
  X,
  FileCode,
  FileSpreadsheet,
  Layers,
  Table,
  Filter
} from 'lucide-react';

interface RawOcrRecordSummary {
  id: string;
  file_name: string;
  template: string;
  total_pages: number;
  created_at: string;
  content_length: number;
}

interface SummaryFieldItem {
  stt: number;
  field: string;
  value: string;
}

interface OcrLineItem {
  stt: number;
  page: number;
  file_name: string;
  text: string;
}

interface ExcelPreviewPayload {
  document_id: string;
  file_name: string;
  template: string;
  metadata: Record<string, string>;
  summary_fields: SummaryFieldItem[];
  ocr_lines: OcrLineItem[];
  cadastral_129_rows: Record<string, any>[];
  total_summary_fields: number;
  total_ocr_lines: number;
}

export const RawMarkdownPage: React.FC = () => {
  const [records, setRecords] = useState<RawOcrRecordSummary[]>([]);
  const [loading, setLoading] = useState<boolean>(false);
  const [search, setSearch] = useState<string>('');
  const [limit, setLimit] = useState<number>(100);

  // Modal xem Markdown chi tiết
  const [selectedDocId, setSelectedDocId] = useState<string | null>(null);
  const [selectedRecord, setSelectedRecord] = useState<any | null>(null);
  const [loadingDetail, setLoadingDetail] = useState<boolean>(false);
  const [copied, setCopied] = useState<boolean>(false);

  // Modal xem trước bảng tính Excel (Spreadsheet Preview)
  const [excelPreviewDocId, setExcelPreviewDocId] = useState<string | null>(null);
  const [excelPreviewData, setExcelPreviewData] = useState<ExcelPreviewPayload | null>(null);
  const [loadingExcelPreview, setLoadingExcelPreview] = useState<boolean>(false);
  const [activeExcelTab, setActiveExcelTab] = useState<'summary' | 'ocr_lines' | 'cadastral_129'>('summary');
  const [excelFilterText, setExcelFilterText] = useState<string>('');

  // Load danh sách bản ghi
  const fetchRecords = useCallback(async () => {
    setLoading(true);
    try {
      const res = await axios.get('/api/v1/raw-ocr', {
        params: {
          limit,
          search: search.trim() || undefined
        }
      });
      setRecords(res.data?.records || []);
    } catch (err) {
      console.error('Lỗi tải danh sách dữ liệu thô Markdown:', err);
    } finally {
      setLoading(false);
    }
  }, [limit, search]);

  useEffect(() => {
    fetchRecords();
  }, [fetchRecords]);

  // Xem Markdown chi tiết
  const handleViewDetail = async (docId: string) => {
    setSelectedDocId(docId);
    setLoadingDetail(true);
    setSelectedRecord(null);
    setCopied(false);
    try {
      const res = await axios.get(`/api/v1/raw-ocr/${encodeURIComponent(docId)}`);
      setSelectedRecord(res.data);
    } catch (err) {
      alert('Không thể nạp nội dung Markdown của hồ sơ này: ' + err);
      setSelectedDocId(null);
    } finally {
      setLoadingDetail(false);
    }
  };

  // Mở modal xem trước bảng tính Excel
  const handleOpenExcelPreview = async (docId: string) => {
    setExcelPreviewDocId(docId);
    setLoadingExcelPreview(true);
    setExcelPreviewData(null);
    setActiveExcelTab('summary');
    setExcelFilterText('');
    try {
      const res = await axios.get(`/api/v1/raw-ocr/${encodeURIComponent(docId)}/preview-excel`);
      setExcelPreviewData(res.data);
    } catch (err) {
      alert('Không thể nạp dữ liệu xem trước bảng tính Excel: ' + err);
      setExcelPreviewDocId(null);
    } finally {
      setLoadingExcelPreview(false);
    }
  };

  // Tải file .md
  const handleDownload = (docId: string) => {
    window.open(`/api/v1/raw-ocr/${encodeURIComponent(docId)}/download`, '_blank');
  };

  // Tải file Excel thô (.xlsx)
  const handleDownloadRawExcel = (docId: string) => {
    window.open(`/api/v1/raw-ocr/${encodeURIComponent(docId)}/export-excel`, '_blank');
  };

  // Tải file 129 Cột (.xlsx)
  const handleDownload129Excel = (docId: string) => {
    window.open(`/api/v1/raw-ocr/${encodeURIComponent(docId)}/export-129-excel`, '_blank');
  };

  // Tải file Excel danh sách bảng tổng hợp
  const handleDownloadTableExcel = () => {
    const params = new URLSearchParams();
    params.set('limit', limit.toString());
    if (search.trim()) params.set('search', search.trim());
    window.open(`/api/v1/raw-ocr/export-table-excel?${params.toString()}`, '_blank');
  };

  // Sao chép nội dung Markdown
  const handleCopyMarkdown = () => {
    if (!selectedRecord?.raw_markdown) return;
    navigator.clipboard.writeText(selectedRecord.raw_markdown);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  // Xóa bản ghi
  const handleDelete = async (docId: string, fileName: string) => {
    if (!window.confirm(`Bạn có chắc chắn muốn xóa bản ghi dữ liệu thô của file "${fileName}"?`)) {
      return;
    }
    try {
      await axios.delete(`/api/v1/raw-ocr/${encodeURIComponent(docId)}`);
      setRecords(prev => prev.filter(r => r.id !== docId));
      if (selectedDocId === docId) {
        setSelectedDocId(null);
        setSelectedRecord(null);
      }
      if (excelPreviewDocId === docId) {
        setExcelPreviewDocId(null);
        setExcelPreviewData(null);
      }
    } catch (err) {
      alert('Lỗi xóa bản ghi: ' + err);
    }
  };

  // Xóa toàn bộ dữ liệu Markdown thô
  const [clearingAll, setClearingAll] = useState<boolean>(false);
  const handleClearAll = async () => {
    if (records.length === 0) return;
    const confirmed = window.confirm(
      `CẢNH BÁO NGUY HIỂM:\nBạn có chắc chắn muốn XÓA TOÀN BỘ ${records.length} bản ghi dữ liệu Markdown thô trong cơ sở dữ liệu SQLite?\n\nThao tác này KHÔNG THỂ HOÀN TÁC!`
    );
    if (!confirmed) return;

    setClearingAll(true);
    try {
      const res = await axios.delete('/api/v1/raw-ocr/clear-all');
      alert(`Đã xóa thành công ${res.data?.deleted_count ?? ''} bản ghi dữ liệu thô!`);
      setRecords([]);
      if (selectedDocId) {
        setSelectedDocId(null);
        setSelectedRecord(null);
      }
      if (excelPreviewDocId) {
        setExcelPreviewDocId(null);
        setExcelPreviewData(null);
      }
      fetchRecords();
    } catch (err: any) {
      alert('Lỗi xóa toàn bộ dữ liệu: ' + (err.response?.data?.detail || err.message));
    } finally {
      setClearingAll(false);
    }
  };

  const formatBytes = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`;
    return `${(bytes / 1024).toFixed(1)} KB`;
  };

  // Dữ liệu lọc trong Excel Preview
  const filteredSummaryFields = (excelPreviewData?.summary_fields || []).filter(item => {
    if (!excelFilterText.trim()) return true;
    const q = excelFilterText.toLowerCase();
    return item.field.toLowerCase().includes(q) || item.value.toLowerCase().includes(q);
  });

  const filteredOcrLines = (excelPreviewData?.ocr_lines || []).filter(item => {
    if (!excelFilterText.trim()) return true;
    const q = excelFilterText.toLowerCase();
    return (
      item.text.toLowerCase().includes(q) ||
      item.file_name.toLowerCase().includes(q) ||
      `trang ${item.page}`.includes(q)
    );
  });

  const filteredCadastralRows = (excelPreviewData?.cadastral_129_rows || []).filter(row => {
    if (!excelFilterText.trim()) return true;
    const q = excelFilterText.toLowerCase();
    return Object.values(row).some(v => String(v || '').toLowerCase().includes(q));
  });

  return (
    <div className="space-y-6">
      {/* ── HEADER & STATS ── */}
      <div className="bg-white rounded-2xl p-6 border border-slate-200 shadow-sm">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div className="flex items-center gap-3.5">
            <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-indigo-500 to-indigo-700 flex items-center justify-center text-white shadow-md">
              <FileCode size={26} />
            </div>
            <div>
              <h2 className="text-lg font-bold text-slate-900 flex items-center gap-2">
                <span>Bảng Lưu Trữ Dữ Liệu Thô OCR (Raw Markdown)</span>
                <span className="bg-indigo-100 text-indigo-700 text-xs px-2.5 py-0.5 rounded-full font-bold">
                  SQLite Persistence
                </span>
              </h2>
              <p className="text-xs text-slate-500 mt-0.5">
                Xem toàn bộ văn bản OCR nguyên bản, xem trước bảng tính Excel trực quan và xuất file .xlsx
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2.5">
            <button
              onClick={handleDownloadTableExcel}
              disabled={loading || records.length === 0}
              className="px-3.5 py-2 bg-emerald-600 hover:bg-emerald-700 disabled:opacity-50 text-white text-xs font-semibold rounded-xl transition flex items-center gap-1.5 shadow-sm"
              title="Xuất toàn bộ bảng danh sách hồ sơ thô sang file Excel"
            >
              <FileSpreadsheet size={15} />
              <span>Xuất Excel Danh Sách</span>
            </button>

            <button
              onClick={() => fetchRecords()}
              disabled={loading}
              className="px-3.5 py-2 bg-slate-100 hover:bg-slate-200 text-slate-700 text-xs font-semibold rounded-xl transition flex items-center gap-1.5"
            >
              <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
              <span>Làm mới</span>
            </button>

            <button
              onClick={handleClearAll}
              disabled={loading || clearingAll || records.length === 0}
              className="px-3.5 py-2 bg-rose-50 hover:bg-rose-100 disabled:opacity-40 text-rose-700 border border-rose-200 text-xs font-semibold rounded-xl transition flex items-center gap-1.5 shadow-sm"
              title="Xóa vĩnh viễn toàn bộ dữ liệu Markdown thô trong cơ sở dữ liệu SQLite"
            >
              <Trash2 size={14} className={clearingAll ? 'animate-spin' : ''} />
              <span>{clearingAll ? 'Đang xóa...' : 'Xóa Toàn Bộ'}</span>
            </button>
          </div>
        </div>

        {/* Search & Filter Bar */}
        <div className="mt-5 pt-5 border-t border-slate-100 flex flex-col sm:flex-row items-center justify-between gap-3">
          <div className="relative w-full sm:w-96">
            <Search size={16} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400" />
            <input
              type="text"
              value={search}
              onChange={e => setSearch(e.target.value)}
              placeholder="Tìm kiếm theo tên file, mẫu sổ..."
              className="w-full pl-10 pr-4 py-2 bg-slate-50 border border-slate-200 rounded-xl text-xs text-slate-800 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:bg-white transition"
            />
          </div>

          <div className="flex items-center gap-2 text-xs text-slate-500 w-full sm:w-auto justify-between sm:justify-end">
            <span>Hiển thị:</span>
            <select
              value={limit}
              onChange={e => setLimit(parseInt(e.target.value))}
              className="bg-slate-50 border border-slate-200 rounded-lg px-2.5 py-1.5 text-xs text-slate-700 focus:outline-none"
            >
              <option value={50}>50 bản ghi</option>
              <option value={100}>100 bản ghi</option>
              <option value={200}>200 bản ghi</option>
              <option value={500}>500 bản ghi</option>
            </select>
            <span className="font-semibold text-slate-700 ml-2">Tổng: {records.length} bản ghi</span>
          </div>
        </div>
      </div>

      {/* ── BẢNG DỮ LIỆU THÔ ── */}
      <div className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
        <div className="overflow-x-auto min-h-[300px]">
          <table className="w-full text-left text-xs text-slate-700 border-collapse">
            <thead className="bg-slate-50 text-[11px] font-bold text-slate-600 uppercase tracking-wider sticky top-0 z-10 border-b border-slate-200">
              <tr>
                <th className="py-3 px-4 w-12 text-center">STT</th>
                <th className="py-3 px-4 min-w-[220px]">Tên tệp hồ sơ</th>
                <th className="py-3 px-4 w-28 text-center">Mẫu nhận diện</th>
                <th className="py-3 px-4 w-24 text-center">Số trang</th>
                <th className="py-3 px-4 w-28 text-right">Dung lượng</th>
                <th className="py-3 px-4 min-w-[150px]">Thời gian quét</th>
                <th className="py-3 px-4 w-52 text-center">Thao tác</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 font-medium">
              {loading && records.length === 0 ? (
                <tr>
                  <td colSpan={7} className="py-12 text-center text-slate-400">
                    <RefreshCw size={24} className="animate-spin mx-auto mb-2 text-indigo-500" />
                    <span>Đang nạp danh sách dữ liệu thô...</span>
                  </td>
                </tr>
              ) : records.length === 0 ? (
                <tr>
                  <td colSpan={7} className="py-12 text-center text-slate-400">
                    <FileText size={32} className="mx-auto mb-2 text-slate-300" />
                    <span>Chưa có bản ghi dữ liệu thô nào trong cơ sở dữ liệu.</span>
                    <p className="text-[11px] text-slate-400 mt-1">
                      Dữ liệu sẽ tự động được lưu trữ tại đây khi bạn chạy quét hồ sơ đơn lẻ hoặc theo lô.
                    </p>
                  </td>
                </tr>
              ) : (
                records.map((rec, idx) => (
                  <tr key={rec.id} className="hover:bg-indigo-50/40 transition group">
                    <td className="py-3 px-4 text-center text-slate-400 font-mono text-[11px]">
                      {idx + 1}
                    </td>
                    <td className="py-3 px-4 font-semibold text-slate-900">
                      <div className="flex items-center gap-2">
                        <FileText size={15} className="text-slate-400 shrink-0" />
                        <span className="truncate max-w-[320px]" title={rec.file_name}>
                          {rec.file_name}
                        </span>
                      </div>
                      <span className="text-[10px] text-slate-400 font-mono block mt-0.5">
                        ID: {rec.id}
                      </span>
                    </td>
                    <td className="py-3 px-4 text-center">
                      <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-slate-100 text-slate-700">
                        {rec.template || 'N/A'}
                      </span>
                    </td>
                    <td className="py-3 px-4 text-center font-bold text-slate-800">
                      {rec.total_pages} trang
                    </td>
                    <td className="py-3 px-4 text-right font-mono text-slate-600">
                      {formatBytes(rec.content_length)}
                    </td>
                    <td className="py-3 px-4 text-slate-500 font-mono text-[11px]">
                      {rec.created_at}
                    </td>
                    <td className="py-3 px-4 text-center">
                      <div className="flex items-center justify-center gap-1.5">
                        {/* Nút Xem Trước Bảng Excel */}
                        <button
                          onClick={() => handleOpenExcelPreview(rec.id)}
                          className="px-2.5 py-1 bg-emerald-50 hover:bg-emerald-100 text-emerald-700 rounded-lg text-xs font-semibold flex items-center gap-1 transition"
                          title="Xem trước bảng tính Excel & Tải về"
                        >
                          <FileSpreadsheet size={13} />
                          <span>Bảng Excel</span>
                        </button>

                        {/* Nút Xem Markdown */}
                        <button
                          onClick={() => handleViewDetail(rec.id)}
                          className="px-2 py-1 bg-indigo-50 hover:bg-indigo-100 text-indigo-700 rounded-lg text-xs font-semibold flex items-center gap-1 transition"
                          title="Xem toàn văn Markdown"
                        >
                          <Eye size={13} />
                          <span>Xem</span>
                        </button>

                        {/* Nút Tải .md */}
                        <button
                          onClick={() => handleDownload(rec.id)}
                          className="p-1 text-slate-400 hover:text-indigo-600 hover:bg-indigo-50 rounded-lg transition"
                          title="Tải tệp Markdown (.md)"
                        >
                          <Download size={14} />
                        </button>

                        {/* Nút Xóa */}
                        <button
                          onClick={() => handleDelete(rec.id, rec.file_name)}
                          className="p-1 text-slate-400 hover:text-rose-600 hover:bg-rose-50 rounded-lg transition"
                          title="Xóa bản ghi"
                        >
                          <Trash2 size={14} />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* ── MODAL XEM TRƯỚC BẢNG TÍNH EXCEL (EXCEL SPREADSHEET PREVIEW) ── */}
      {excelPreviewDocId && (
        <div className="fixed inset-0 z-50 bg-slate-900/60 backdrop-blur-sm flex items-center justify-center p-3 sm:p-6 animate-in fade-in duration-200">
          <div className="bg-white rounded-2xl max-w-6xl w-full h-[90vh] flex flex-col shadow-2xl border border-slate-200 overflow-hidden">
            {/* Modal Header */}
            <div className="px-6 py-4 border-b border-slate-200 bg-emerald-50/50 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-xl bg-emerald-600 flex items-center justify-center text-white shadow-md">
                  <FileSpreadsheet size={20} />
                </div>
                <div>
                  <h3 className="text-sm font-bold text-slate-900 flex items-center gap-2">
                    <span>Xem Trước Bảng Tính Excel (Spreadsheet Preview)</span>
                    {excelPreviewData?.template && (
                      <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-100 text-emerald-800">
                        {excelPreviewData.template}
                      </span>
                    )}
                  </h3>
                  <p className="text-xs text-slate-500 font-mono truncate max-w-lg">
                    {excelPreviewData?.file_name || excelPreviewDocId} ({excelPreviewData?.metadata?.total_pages || 1} trang)
                  </p>
                </div>
              </div>

              {/* Action Buttons Header */}
              <div className="flex items-center gap-2">
                <button
                  onClick={() => handleDownloadRawExcel(excelPreviewDocId)}
                  className="px-3.5 py-1.5 bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-semibold rounded-xl transition flex items-center gap-1.5 shadow-sm"
                  title="Tải về file Excel chứa Sheet Tóm tắt và Sheet Dòng OCR"
                >
                  <Download size={14} />
                  <span>Tải Excel Thô (.xlsx)</span>
                </button>

                <button
                  onClick={() => handleDownload129Excel(excelPreviewDocId)}
                  className="px-3.5 py-1.5 bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-semibold rounded-xl transition flex items-center gap-1.5 shadow-sm"
                  title="Chuyển đổi dữ liệu sang tệp Excel 129 cột của Bộ TN&MT"
                >
                  <Layers size={14} />
                  <span>Tải Bảng 129 Cột (.xlsx)</span>
                </button>

                <button
                  onClick={() => setExcelPreviewDocId(null)}
                  className="p-1.5 text-slate-400 hover:text-slate-700 hover:bg-slate-200 rounded-xl transition ml-1"
                >
                  <X size={18} />
                </button>
              </div>
            </div>

            {/* Subheader: Sheet Tabs & Search Filter */}
            <div className="px-6 py-2.5 bg-slate-100 border-b border-slate-200 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
              {/* Sheet Navigation Tabs (Like Excel) */}
              <div className="flex items-center gap-1 overflow-x-auto pb-1 sm:pb-0">
                <button
                  onClick={() => setActiveExcelTab('summary')}
                  className={`px-3 py-1.5 text-xs font-bold rounded-lg flex items-center gap-1.5 transition ${
                    activeExcelTab === 'summary'
                      ? 'bg-white text-emerald-800 shadow-xs border border-slate-200'
                      : 'text-slate-600 hover:bg-slate-200/70'
                  }`}
                >
                  <Table size={13} />
                  <span>Sheet 1: Tóm Tắt Bóc Tách</span>
                  <span className="px-1.5 py-0.2 rounded-full text-[10px] bg-slate-100 text-slate-600">
                    {excelPreviewData?.total_summary_fields || 0}
                  </span>
                </button>

                <button
                  onClick={() => setActiveExcelTab('ocr_lines')}
                  className={`px-3 py-1.5 text-xs font-bold rounded-lg flex items-center gap-1.5 transition ${
                    activeExcelTab === 'ocr_lines'
                      ? 'bg-white text-indigo-800 shadow-xs border border-slate-200'
                      : 'text-slate-600 hover:bg-slate-200/70'
                  }`}
                >
                  <FileText size={13} />
                  <span>Sheet 2: Dòng Văn Bản OCR</span>
                  <span className="px-1.5 py-0.2 rounded-full text-[10px] bg-slate-100 text-slate-600">
                    {excelPreviewData?.total_ocr_lines || 0}
                  </span>
                </button>

                <button
                  onClick={() => setActiveExcelTab('cadastral_129')}
                  className={`px-3 py-1.5 text-xs font-bold rounded-lg flex items-center gap-1.5 transition ${
                    activeExcelTab === 'cadastral_129'
                      ? 'bg-white text-blue-800 shadow-xs border border-slate-200'
                      : 'text-slate-600 hover:bg-slate-200/70'
                  }`}
                >
                  <Layers size={13} />
                  <span>Sheet 3: Bảng 129 Cột</span>
                  <span className="px-1.5 py-0.2 rounded-full text-[10px] bg-slate-100 text-slate-600">
                    {excelPreviewData?.cadastral_129_rows?.length || 0}
                  </span>
                </button>
              </div>

              {/* Filter inside preview */}
              <div className="relative w-full sm:w-64">
                <Filter size={13} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
                <input
                  type="text"
                  value={excelFilterText}
                  onChange={e => setExcelFilterText(e.target.value)}
                  placeholder="Lọc dữ liệu dòng..."
                  className="w-full pl-8 pr-3 py-1 bg-white border border-slate-200 rounded-lg text-xs text-slate-800 focus:outline-none focus:ring-2 focus:ring-emerald-500"
                />
              </div>
            </div>

            {/* Table Content (Spreadsheet View) */}
            <div className="flex-1 overflow-auto bg-slate-50 p-4">
              {loadingExcelPreview ? (
                <div className="h-full flex flex-col items-center justify-center text-slate-400 gap-3">
                  <RefreshCw size={32} className="animate-spin text-emerald-600" />
                  <span className="text-xs font-semibold">Đang chuẩn bị bảng tính Excel xem trước...</span>
                </div>
              ) : activeExcelTab === 'summary' ? (
                /* TAB 1: TÓM TẮT BÓC TÁCH */
                <div className="bg-white rounded-xl border border-slate-200 shadow-xs overflow-hidden">
                  <table className="w-full text-left text-xs border-collapse font-sans">
                    <thead className="bg-slate-800 text-white font-bold text-[11px] sticky top-0 z-10">
                      <tr>
                        <th className="py-2.5 px-3 w-16 text-center border-r border-slate-700">STT</th>
                        <th className="py-2.5 px-4 w-72 border-r border-slate-700">Trường Dữ Liệu Bóc Tách Thô</th>
                        <th className="py-2.5 px-4">Giá Trị Trích Xuất (Raw Value)</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-200">
                      {filteredSummaryFields.length === 0 ? (
                        <tr>
                          <td colSpan={3} className="py-8 text-center text-slate-400 text-xs">
                            Không có trường bóc tách nào khớp với bộ lọc.
                          </td>
                        </tr>
                      ) : (
                        filteredSummaryFields.map(item => (
                          <tr key={item.stt} className="even:bg-slate-50/70 hover:bg-emerald-50/40 transition">
                            <td className="py-2 px-3 text-center text-slate-400 font-mono text-[11px] border-r border-slate-200">
                              {item.stt}
                            </td>
                            <td className="py-2 px-4 font-semibold text-slate-900 border-r border-slate-200">
                              {item.field}
                            </td>
                            <td className="py-2 px-4 text-slate-800 font-medium">
                              {item.value || <span className="text-slate-300 italic">(Trống)</span>}
                            </td>
                          </tr>
                        ))
                      )}
                    </tbody>
                  </table>
                </div>
              ) : activeExcelTab === 'ocr_lines' ? (
                /* TAB 2: DÒNG VĂN BẢN OCR CHI TIẾT */
                <div className="bg-white rounded-xl border border-slate-200 shadow-xs overflow-hidden">
                  <table className="w-full text-left text-xs border-collapse font-sans">
                    <thead className="bg-indigo-900 text-white font-bold text-[11px] sticky top-0 z-10">
                      <tr>
                        <th className="py-2.5 px-3 w-16 text-center border-r border-indigo-800">STT</th>
                        <th className="py-2.5 px-3 w-24 text-center border-r border-indigo-800">Trang</th>
                        <th className="py-2.5 px-4 w-48 border-r border-indigo-800">Tệp Nguồn</th>
                        <th className="py-2.5 px-4">Nội Dung Văn Bản Nhận Dạng Quang Học (OCR Lines)</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-200">
                      {filteredOcrLines.length === 0 ? (
                        <tr>
                          <td colSpan={4} className="py-8 text-center text-slate-400 text-xs">
                            Không có dòng văn bản OCR nào khớp với bộ lọc.
                          </td>
                        </tr>
                      ) : (
                        filteredOcrLines.map(item => (
                          <tr key={item.stt} className="even:bg-slate-50/70 hover:bg-indigo-50/40 transition">
                            <td className="py-2 px-3 text-center text-slate-400 font-mono text-[11px] border-r border-slate-200">
                              {item.stt}
                            </td>
                            <td className="py-2 px-3 text-center font-bold text-slate-700 border-r border-slate-200">
                              Trang {item.page}
                            </td>
                            <td className="py-2 px-4 text-slate-500 font-mono text-[11px] truncate max-w-[180px] border-r border-slate-200" title={item.file_name}>
                              {item.file_name}
                            </td>
                            <td className="py-2 px-4 text-slate-900 font-mono text-xs">
                              {item.text}
                            </td>
                          </tr>
                        ))
                      )}
                    </tbody>
                  </table>
                </div>
              ) : (
                /* TAB 3: BẢNG CHUẨN 129 CỘT */
                <div className="bg-white rounded-xl border border-slate-200 shadow-xs overflow-x-auto">
                  <table className="min-w-[1400px] text-left text-xs border-collapse font-sans">
                    <thead className="bg-slate-900 text-white font-bold text-[11px] sticky top-0 z-10">
                      <tr>
                        <th className="py-2.5 px-3 text-center border-r border-slate-800 w-12">STT</th>
                        <th className="py-2.5 px-4 border-r border-slate-800 min-w-[160px]">Tên Chủ Đất</th>
                        <th className="py-2.5 px-3 border-r border-slate-800 w-24 text-center">Năm Sinh</th>
                        <th className="py-2.5 px-3 border-r border-slate-800 w-32 text-center">Số CCCD</th>
                        <th className="py-2.5 px-4 border-r border-slate-800 min-w-[200px]">Địa Chỉ Thường Trú</th>
                        <th className="py-2.5 px-3 border-r border-slate-800 w-24 text-center">Số Thửa</th>
                        <th className="py-2.5 px-3 border-r border-slate-800 w-24 text-center">Tờ Bản Đồ</th>
                        <th className="py-2.5 px-3 border-r border-slate-800 w-28 text-right">Diện Tích (m²)</th>
                        <th className="py-2.5 px-3 border-r border-slate-800 w-28 text-center">Mã Mục Đích</th>
                        <th className="py-2.5 px-3 border-r border-slate-800 w-28 text-center">Thời Hạn</th>
                        <th className="py-2.5 px-4 border-r border-slate-800 min-w-[160px]">Nguồn Gốc</th>
                        <th className="py-2.5 px-3 border-r border-slate-800 w-28 text-center">Ngày Cấp</th>
                        <th className="py-2.5 px-3 border-r border-slate-800 w-28 text-center">Số Vào Sổ</th>
                        <th className="py-2.5 px-3 border-r border-slate-800 w-28 text-center">Số Phát Hành</th>
                        <th className="py-2.5 px-3 w-36 text-center">Mã Vạch</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-200">
                      {filteredCadastralRows.length === 0 ? (
                        <tr>
                          <td colSpan={15} className="py-8 text-center text-slate-400 text-xs">
                            Chưa có dữ liệu 129 cột được ánh xạ.
                          </td>
                        </tr>
                      ) : (
                        filteredCadastralRows.map((r, i) => (
                          <tr key={i} className="even:bg-slate-50/70 hover:bg-blue-50/40 transition">
                            <td className="py-2 px-3 text-center font-mono text-slate-400 border-r border-slate-200">{r.STT || i + 1}</td>
                            <td className="py-2 px-4 font-bold text-slate-900 border-r border-slate-200">{r.CHU_hoTen || r.nguoi_su_dung?.ho_ten_chu_1 || '-'}</td>
                            <td className="py-2 px-3 text-center border-r border-slate-200">{r.CHU_ngaySinh || '-'}</td>
                            <td className="py-2 px-3 text-center font-mono border-r border-slate-200">{r.GT_soGiayTo || '-'}</td>
                            <td className="py-2 px-4 text-slate-600 border-r border-slate-200">{r.CHU_diaChiThuongTru || '-'}</td>
                            <td className="py-2 px-3 text-center font-bold text-slate-800 border-r border-slate-200">{r.TD_soThuTuThua || '-'}</td>
                            <td className="py-2 px-3 text-center font-bold text-slate-800 border-r border-slate-200">{r.TD_soHieuToBanDo || '-'}</td>
                            <td className="py-2 px-3 text-right font-bold text-emerald-700 font-mono border-r border-slate-200">{r.TD_dienTich || '-'}</td>
                            <td className="py-2 px-3 text-center font-bold text-indigo-700 border-r border-slate-200">{r.TD_maMucDichSuDung || '-'}</td>
                            <td className="py-2 px-3 text-center border-r border-slate-200">{r.TD_thoiHanSuDung || '-'}</td>
                            <td className="py-2 px-4 text-slate-600 border-r border-slate-200">{r.TD_nguonGoc || '-'}</td>
                            <td className="py-2 px-3 text-center font-mono border-r border-slate-200">{r.GCN_ngayCap || '-'}</td>
                            <td className="py-2 px-3 text-center font-mono border-r border-slate-200">{r.GCN_soVaoSo || '-'}</td>
                            <td className="py-2 px-3 text-center font-mono font-bold text-slate-900 border-r border-slate-200">{r.GCN_soPhatHanh || '-'}</td>
                            <td className="py-2 px-3 text-center font-mono text-slate-600">{r.GCN_maVach || '-'}</td>
                          </tr>
                        ))
                      )}
                    </tbody>
                  </table>
                </div>
              )}
            </div>

            {/* Modal Footer */}
            <div className="px-6 py-3 border-t border-slate-200 bg-white flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs text-slate-500">
              <div className="flex items-center gap-2">
                <span>Trạng thái:</span>
                <span className="font-semibold text-slate-800">
                  {activeExcelTab === 'summary'
                    ? `Hiển thị ${filteredSummaryFields.length}/${excelPreviewData?.total_summary_fields || 0} trường`
                    : activeExcelTab === 'ocr_lines'
                    ? `Hiển thị ${filteredOcrLines.length}/${excelPreviewData?.total_ocr_lines || 0} dòng text`
                    : `Hiển thị ${filteredCadastralRows.length} thửa đất 129 cột`}
                </span>
                <span className="text-slate-300">|</span>
                <span className="text-emerald-700 font-medium">Bấm các nút tải ở góc trên để lưu file .xlsx hoàn chỉnh</span>
              </div>

              <div className="flex items-center gap-2">
                <button
                  onClick={() => setExcelPreviewDocId(null)}
                  className="px-4 py-1.5 bg-slate-100 hover:bg-slate-200 text-slate-700 font-semibold rounded-lg transition"
                >
                  Đóng Bảng Tính
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ── MODAL XEM NỘI DUNG MARKDOWN THÔ ── */}
      {selectedDocId && (
        <div className="fixed inset-0 z-50 bg-slate-900/60 backdrop-blur-sm flex items-center justify-center p-4 sm:p-6 animate-in fade-in duration-200">
          <div className="bg-white rounded-2xl max-w-4xl w-full h-[85vh] flex flex-col shadow-2xl border border-slate-200 overflow-hidden">
            {/* Modal Header */}
            <div className="px-6 py-4 border-b border-slate-200 bg-slate-50 flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="w-9 h-9 rounded-lg bg-indigo-600 flex items-center justify-center text-white shadow-sm">
                  <FileCode size={18} />
                </div>
                <div>
                  <h3 className="text-sm font-bold text-slate-900 flex items-center gap-2">
                    <span>Nội Dung Markdown Thô (Raw OCR)</span>
                    {selectedRecord?.template && (
                      <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-indigo-100 text-indigo-800">
                        {selectedRecord.template}
                      </span>
                    )}
                  </h3>
                  <p className="text-xs text-slate-500 font-mono truncate max-w-md">
                    {selectedRecord?.file_name || selectedDocId}
                  </p>
                </div>
              </div>

              <div className="flex items-center gap-2">
                {/* Switch sang Excel Preview */}
                <button
                  onClick={() => {
                    const id = selectedDocId;
                    setSelectedDocId(null);
                    handleOpenExcelPreview(id);
                  }}
                  className="px-3 py-1.5 bg-emerald-50 hover:bg-emerald-100 border border-emerald-200 text-emerald-700 text-xs font-semibold rounded-xl transition flex items-center gap-1.5 shadow-sm"
                  title="Xem trước dưới dạng Bảng tính Excel"
                >
                  <FileSpreadsheet size={14} />
                  <span>Bảng Excel</span>
                </button>

                <button
                  onClick={handleCopyMarkdown}
                  disabled={!selectedRecord?.raw_markdown}
                  className="px-3 py-1.5 bg-white hover:bg-slate-100 border border-slate-200 text-slate-700 text-xs font-semibold rounded-xl transition flex items-center gap-1.5 shadow-sm"
                >
                  {copied ? <Check size={14} className="text-emerald-600" /> : <Copy size={14} />}
                  <span>{copied ? 'Đã sao chép!' : 'Sao chép'}</span>
                </button>

                <button
                  onClick={() => handleDownload(selectedDocId)}
                  className="px-3 py-1.5 bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-semibold rounded-xl transition flex items-center gap-1.5 shadow-sm"
                >
                  <Download size={14} />
                  <span>Tải .md</span>
                </button>

                <button
                  onClick={() => setSelectedDocId(null)}
                  className="p-1.5 text-slate-400 hover:text-slate-700 hover:bg-slate-200 rounded-xl transition ml-1"
                >
                  <X size={18} />
                </button>
              </div>
            </div>

            {/* Modal Content */}
            <div className="flex-1 p-6 overflow-y-auto bg-slate-950 text-slate-200 font-mono text-xs leading-relaxed selection:bg-indigo-600 selection:text-white">
              {loadingDetail ? (
                <div className="h-full flex flex-col items-center justify-center text-slate-400 gap-3">
                  <RefreshCw size={28} className="animate-spin text-indigo-400" />
                  <span>Đang tải nội dung Markdown...</span>
                </div>
              ) : selectedRecord?.raw_markdown ? (
                <pre className="whitespace-pre-wrap break-words font-mono">
                  {selectedRecord.raw_markdown}
                </pre>
              ) : (
                <div className="text-slate-500 text-center py-12">
                  Không có nội dung dữ liệu thô.
                </div>
              )}
            </div>

            {/* Modal Footer */}
            <div className="px-6 py-3 border-t border-slate-200 bg-slate-50 flex items-center justify-between text-xs text-slate-500">
              <span>Hồ sơ ID: <code className="font-mono">{selectedDocId}</code></span>
              <button
                onClick={() => setSelectedDocId(null)}
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
