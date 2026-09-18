import React, { useState, useEffect, useCallback, useMemo } from 'react';
import axios from 'axios';
import {
  Database,
  Search,
  RefreshCw,
  Download,
  Trash2,
  Copy,
  Check,
  X,
  FileCode,
  FileSpreadsheet,
  Layers,
  Filter,
  AlertTriangle,
  Folder,
  HardDrive,
  ArrowRight,
  ExternalLink,
  Eye,
  SlidersHorizontal,
  FileText,
  ChevronDown,
  CheckCircle2,
  RotateCcw
} from 'lucide-react';
import { PgRecordSummary, PgFolderOption, PgSourceOption, PgStats } from '../../shared/types';
import { QuickReviewPanel } from '../../shared/components/QuickReviewPanel';
import { useAuth } from '../../shared/auth/AuthProvider';
import { extractErrorMessage } from '../../shared/lib/errorHelper';

interface RawMarkdownPageProps {
  onView129Table?: (rows: Record<string, any>[]) => void;
  isActive?: boolean;
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

export const RawMarkdownPage: React.FC<RawMarkdownPageProps> = ({ onView129Table, isActive }) => {
  const { can } = useAuth();
  // Dữ liệu hồ sơ
  const [records, setRecords] = useState<PgRecordSummary[]>([]);
  const [totalRecords, setTotalRecords] = useState<number>(0);
  const [loading, setLoading] = useState<boolean>(false);
  const [stats, setStats] = useState<PgStats | null>(null);

  // Danh mục bộ lọc
  const [folderOptions, setFolderOptions] = useState<PgFolderOption[]>([]);
  const [sourceOptions, setSourceOptions] = useState<PgSourceOption[]>([]);

  // Trạng thái bộ lọc
  const [selectedFolder, setSelectedFolder] = useState<string>('all');
  const [selectedSource, setSelectedSource] = useState<string>('all');
  const [search, setSearch] = useState<string>('');
  const [limit, setLimit] = useState<number>(50);
  const [page, setPage] = useState<number>(1);

  // Trạng thái xuất Excel & tải DB
  const [exportingExcel, setExportingExcel] = useState<boolean>(false);
  const [downloadingRawDb, setDownloadingRawDb] = useState<boolean>(false);
  const [downloadingRawMarkdown, setDownloadingRawMarkdown] = useState<boolean>(false);
  const [downloadingRawExcel, setDownloadingRawExcel] = useState<boolean>(false);
  const [showDownloadMenu, setShowDownloadMenu] = useState<boolean>(false);

  // Modal xác nhận xóa
  const [deleteConfirm, setDeleteConfirm] = useState<{
    open: boolean;
    type: 'single' | 'folder' | 'source';
    targetName: string;
    targetIds?: string[];
  } | null>(null);
  const [deleting, setDeleting] = useState<boolean>(false);

  // Modal xem Markdown chi tiết
  const [selectedDocId, setSelectedDocId] = useState<string | null>(null);
  const [selectedRecord, setSelectedRecord] = useState<any | null>(null);
  const [loadingDetail, setLoadingDetail] = useState<boolean>(false);
  const [copied, setCopied] = useState<boolean>(false);
  const [reviewDocId, setReviewDocId] = useState<string | null>(null);

  // Modal xem trước bảng tính Excel
  const [excelPreviewDocId, setExcelPreviewDocId] = useState<string | null>(null);
  const [excelPreviewData, setExcelPreviewData] = useState<ExcelPreviewPayload | null>(null);
  const [loadingExcelPreview, setLoadingExcelPreview] = useState<boolean>(false);
  const [activeExcelTab, setActiveExcelTab] = useState<'summary' | 'ocr_lines' | 'cadastral_129'>('summary');
  const [excelFilterText, setExcelFilterText] = useState<string>('');

  // Nạp danh mục filter và stats
  const fetchFilterOptionsAndStats = useCallback(async () => {
    try {
      const [filterRes, statsRes] = await Promise.all([
        axios.get('/api/v1/pg/filters'),
        axios.get('/api/v1/pg/stats')
      ]);
      setFolderOptions(filterRes.data?.folders || []);
      setSourceOptions(filterRes.data?.sources || []);
      setStats(statsRes.data || null);
    } catch (err) {
      console.error('Lỗi nạp danh mục filter/stats PostgreSQL:', err);
    }
  }, []);

  // Nạp danh sách bản ghi theo filter
  const fetchRecords = useCallback(async () => {
    setLoading(true);
    try {
      const offset = (page - 1) * limit;
      const res = await axios.get('/api/v1/pg/records', {
        params: {
          limit,
          offset,
          folder_result: selectedFolder !== 'all' ? selectedFolder : undefined,
          source_path: selectedSource !== 'all' ? selectedSource : undefined,
          search: search.trim() || undefined
        }
      });
      setRecords(res.data?.records || []);
      setTotalRecords(res.data?.total || 0);
    } catch (err) {
      console.error('Lỗi nạp danh sách hồ sơ PostgreSQL:', err);
    } finally {
      setLoading(false);
    }
  }, [limit, page, selectedFolder, selectedSource, search]);

  useEffect(() => {
    fetchFilterOptionsAndStats();
  }, [fetchFilterOptionsAndStats]);

  useEffect(() => {
    fetchRecords();
  }, [fetchRecords]);

  // Tự động làm mới khi người dùng chuyển sang tab Kho hồ sơ
  useEffect(() => {
    if (isActive) {
      fetchRecords();
      fetchFilterOptionsAndStats();
    }
  }, [isActive, fetchRecords, fetchFilterOptionsAndStats]);



  // Xem Markdown chi tiết
  const handleViewDetail = async (docId: string) => {
    setSelectedDocId(docId);
    setLoadingDetail(true);
    setSelectedRecord(null);
    setCopied(false);
    try {
      const res = await axios.get(`/api/v1/pg/records/${encodeURIComponent(docId)}`);
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
      const res = await axios.get(`/api/v1/pg/records/${encodeURIComponent(docId)}/preview-excel`);
      setExcelPreviewData(res.data);
    } catch (err) {
      alert('Không thể nạp dữ liệu xem trước bảng tính Excel: ' + err);
      setExcelPreviewDocId(null);
    } finally {
      setLoadingExcelPreview(false);
    }
  };

  // Tải file .md
  const handleDownloadMd = async (docId: string) => {
    try {
      const response = await axios.get(`/api/v1/pg/records/${encodeURIComponent(docId)}/download-md`, { responseType: 'blob' });
      const url = window.URL.createObjectURL(new Blob([response.data], { type: 'text/markdown;charset=utf-8' }));
      const link = document.createElement('a');
      link.href = url;
      link.download = `${docId}_raw_ocr.md`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
    } catch (err: any) {
      const msg = await extractErrorMessage(err, 'Không thể tải Markdown của hồ sơ.');
      alert(msg);
    }
  };

  // Xem trên Bảng 129 Cột
  const handleViewIn129Table = async () => {
    try {
      const params: any = { limit: 5000 };
      if (selectedFolder !== 'all') params.folder_result = selectedFolder;
      if (selectedSource !== 'all') params.source_path = selectedSource;

      const res = await axios.get('/api/v1/pg/129-rows', { params });
      const rows = res.data?.rows || [];
      if (rows.length === 0) {
        alert('Không có dữ liệu 129 cột thỏa mãn điều kiện lọc!');
        return;
      }
      if (onView129Table) {
        onView129Table(rows);
      } else {
        alert(`Đã nạp thành công ${rows.length} dòng 129 cột! Chuyển sang tab Bảng Chuyển Đổi Địa Chính để xem.`);
      }
    } catch (err) {
      alert('Không thể nạp dữ liệu 129 cột: ' + err);
    }
  };

  // Xuất file Excel 129 Cột cho mẻ / thư mục đang lọc
  const handleExport129Excel = async () => {
    setExportingExcel(true);
    try {
      const params: any = {};
      if (selectedFolder !== 'all') params.folder_result = selectedFolder;
      if (selectedSource !== 'all') params.source_path = selectedSource;

      const res = await axios.post('/api/v1/pg/export-129-excel', {}, {
        params,
        responseType: 'blob'
      });
      const url = window.URL.createObjectURL(new Blob([res.data]));
      const link = document.createElement('a');
      link.href = url;
      const fn = selectedFolder !== 'all' ? selectedFolder : 'KhoDuLieu_PG';
      link.setAttribute('download', `KetQua_129Cot_${fn}_${new Date().toISOString().slice(0, 10)}.xlsx`);
      document.body.appendChild(link);
      link.click();
      link.remove();
    } catch (err: any) {
      const msg = await extractErrorMessage(err, 'Không thể xuất file Excel 129 cột');
      alert(msg);
    } finally {
      setExportingExcel(false);
    }
  };

  // Tải tệp sao lưu CSDL thô (JSON Dump)
  const handleDownloadRawDb = async () => {
    setDownloadingRawDb(true);
    try {
      const params: any = {};
      if (selectedFolder !== 'all') params.folder_result = selectedFolder;
      if (selectedSource !== 'all') params.source_path = selectedSource;
      if (search.trim()) params.search = search.trim();

      const res = await axios.get('/api/v1/pg/export-raw-db', {
        params,
        responseType: 'blob'
      });
      const url = window.URL.createObjectURL(new Blob([res.data], { type: 'application/json' }));
      const link = document.createElement('a');
      link.href = url;
      const fn = selectedFolder !== 'all' ? selectedFolder : 'KhoDuLieu_PG';
      link.setAttribute('download', `CSDL_DuLieuTho_${fn}_${new Date().toISOString().slice(0, 10)}.json`);
      document.body.appendChild(link);
      link.click();
      link.remove();
    } catch (err: any) {
      const msg = await extractErrorMessage(err, 'Không thể tải CSDL dữ liệu thô');
      alert(msg);
    } finally {
      setDownloadingRawDb(false);
    }
  };

  // Tải gói toàn bộ file Markdown thô (.zip)
  const handleDownloadRawMarkdown = async () => {
    setDownloadingRawMarkdown(true);
    try {
      const params: any = {};
      if (selectedFolder !== 'all') params.folder_result = selectedFolder;
      if (selectedSource !== 'all') params.source_path = selectedSource;
      if (search.trim()) params.search = search.trim();

      const res = await axios.get('/api/v1/pg/export-raw-markdown', {
        params,
        responseType: 'blob'
      });
      const url = window.URL.createObjectURL(new Blob([res.data], { type: 'application/zip' }));
      const link = document.createElement('a');
      link.href = url;
      const fn = selectedFolder !== 'all' ? selectedFolder : 'KhoDuLieu_PG';
      link.setAttribute('download', `GoiMarkdown_DuLieuTho_${fn}_${new Date().toISOString().slice(0, 10)}.zip`);
      document.body.appendChild(link);
      link.click();
      link.remove();
    } catch (err: any) {
      const msg = await extractErrorMessage(err, 'Không thể tải gói Markdown thô');
      alert(msg);
    } finally {
      setDownloadingRawMarkdown(false);
    }
  };

  // Tải file Excel Bảng tổng hợp dữ liệu thô (.xlsx)
  const handleExportRawExcel = async () => {
    setDownloadingRawExcel(true);
    try {
      const params: any = {};
      if (selectedFolder !== 'all') params.folder_result = selectedFolder;
      if (selectedSource !== 'all') params.source_path = selectedSource;
      if (search.trim()) params.search = search.trim();

      const res = await axios.get('/api/v1/pg/export-raw-excel', {
        params,
        responseType: 'blob'
      });
      const url = window.URL.createObjectURL(new Blob([res.data]));
      const link = document.createElement('a');
      link.href = url;
      const fn = selectedFolder !== 'all' ? selectedFolder : 'KhoDuLieu_PG';
      link.setAttribute('download', `BangTongHop_DuLieuTho_${fn}_${new Date().toISOString().slice(0, 10)}.xlsx`);
      document.body.appendChild(link);
      link.click();
      link.remove();
    } catch (err: any) {
      const msg = await extractErrorMessage(err, 'Không thể tải bảng tổng hợp dữ liệu thô');
      alert(msg);
    } finally {
      setDownloadingRawExcel(false);
    }
  };

  // Thực thi xóa sau khi người dùng xác nhận
  const executeDelete = async () => {
    if (!deleteConfirm) return;
    if (!can('record.delete')) {
      alert('Tài khoản của bạn không có quyền xóa hồ sơ (record.delete).');
      setDeleteConfirm(null);
      return;
    }
    setDeleting(true);
    try {
      if (deleteConfirm.type === 'single' && deleteConfirm.targetIds?.[0]) {
        await axios.delete('/api/v1/pg/records', {
          data: { ids: deleteConfirm.targetIds }
        });
      } else if (deleteConfirm.type === 'folder') {
        await axios.delete('/api/v1/pg/by-folder', {
          params: { folder_result: deleteConfirm.targetName }
        });
        setSelectedFolder('all');
      } else if (deleteConfirm.type === 'source') {
        await axios.delete('/api/v1/pg/by-source', {
          params: { source_path: deleteConfirm.targetName }
        });
        setSelectedSource('all');
      }
      // Nạp lại dữ liệu
      await Promise.all([fetchRecords(), fetchFilterOptionsAndStats()]);
      setDeleteConfirm(null);
    } catch (err: any) {
      const msg = await extractErrorMessage(err, 'Lỗi khi thực hiện xóa dữ liệu');
      alert(msg);
    } finally {
      setDeleting(false);
    }
  };

  // Dữ liệu lọc trong modal Excel Preview
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

  const totalPages = Math.ceil(totalRecords / limit) || 1;

  return (
    <div className="space-y-6">
      {/* ── HEADER & THỐNG KÊ ── */}
      <div className="bg-white rounded-2xl p-5 sm:p-6 border border-slate-200/80 shadow-sm relative overflow-hidden">
        {/* Subtle decorative glow */}
        <div className="absolute -top-24 -right-24 w-80 h-80 bg-gradient-to-br from-indigo-100/40 via-purple-50/20 to-transparent rounded-full blur-3xl pointer-events-none" />

        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-5 relative z-10">
          {/* Title & Subtitle */}
          <div className="flex items-center gap-3.5">
            <div className="w-12 h-12 rounded-2xl bg-gradient-to-br from-indigo-600 via-indigo-600 to-indigo-800 flex items-center justify-center text-white shadow-md shadow-indigo-500/20 ring-4 ring-indigo-50 shrink-0">
              <Database size={24} />
            </div>
            <div>
              <div className="flex items-center gap-2.5 flex-wrap">
                <h2 className="text-xl font-bold tracking-tight text-slate-900 leading-tight">
                  Kho hồ sơ
                </h2>
                <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200/80 shadow-2xs">
                  <span className="relative flex h-2 w-2">
                    <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                    <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
                  </span>
                  Sẵn sàng
                </span>
              </div>
              <p className="text-xs text-slate-500 mt-1 leading-relaxed max-w-xl">
                Tự động lưu trữ bền vững sau mỗi lần quét. Tra cứu, lọc theo thư mục kết quả, link máy và quản lý dữ liệu bóc tách.
              </p>
            </div>
          </div>

          {/* KPI Stat Cards */}
          <div className="flex flex-wrap items-center gap-2.5 text-xs">
            {/* Thư mục */}
            <div className="flex items-center gap-2.5 px-3.5 py-2 bg-slate-50 hover:bg-slate-100/70 border border-slate-200/70 rounded-xl transition-all shadow-2xs">
              <div className="w-8 h-8 rounded-lg bg-white border border-slate-200/70 flex items-center justify-center text-slate-600 shadow-2xs shrink-0">
                <Folder size={15} />
              </div>
              <div>
                <span className="text-slate-400 block text-[10px] font-semibold uppercase tracking-wider leading-tight">Thư mục</span>
                <span className="text-sm font-bold text-slate-800 leading-tight">{stats?.total_folders ?? folderOptions.length}</span>
              </div>
            </div>

            {/* Tổng hồ sơ */}
            <div className="flex items-center gap-2.5 px-3.5 py-2 bg-indigo-50/70 hover:bg-indigo-50 border border-indigo-100/80 rounded-xl transition-all shadow-2xs">
              <div className="w-8 h-8 rounded-lg bg-indigo-600 text-white flex items-center justify-center shadow-2xs shrink-0">
                <Layers size={15} />
              </div>
              <div>
                <span className="text-indigo-600/90 block text-[10px] font-semibold uppercase tracking-wider leading-tight">Tổng số hồ sơ</span>
                <span className="text-sm font-bold text-indigo-950 leading-tight">{stats?.total_records ?? totalRecords}</span>
              </div>
            </div>

            {/* Trích xuất hợp lệ */}
            <div className="flex items-center gap-2.5 px-3.5 py-2 bg-emerald-50/70 hover:bg-emerald-50 border border-emerald-100/80 rounded-xl transition-all shadow-2xs">
              <div className="w-8 h-8 rounded-lg bg-emerald-600 text-white flex items-center justify-center shadow-2xs shrink-0">
                <CheckCircle2 size={15} />
              </div>
              <div>
                <span className="text-emerald-700/90 block text-[10px] font-semibold uppercase tracking-wider leading-tight">Trích xuất hợp lệ</span>
                <span className="text-sm font-bold text-emerald-950 leading-tight">{stats?.success_records ?? 0}</span>
              </div>
            </div>

            {/* Lỗi nhận dạng (nếu có) */}
            {stats && stats.error_records! > 0 && (
              <div className="flex items-center gap-2.5 px-3.5 py-2 bg-rose-50/70 hover:bg-rose-50 border border-rose-100/80 rounded-xl transition-all shadow-2xs">
                <div className="w-8 h-8 rounded-lg bg-rose-600 text-white flex items-center justify-center shadow-2xs shrink-0">
                  <AlertTriangle size={15} />
                </div>
                <div>
                  <span className="text-rose-700/90 block text-[10px] font-semibold uppercase tracking-wider leading-tight">Lỗi nhận dạng</span>
                  <span className="text-sm font-bold text-rose-950 leading-tight">{stats.error_records}</span>
                </div>
              </div>
            )}

            {/* Nút Làm mới */}
            <button
              onClick={() => { fetchRecords(); fetchFilterOptionsAndStats(); }}
              disabled={loading}
              className="p-2.5 bg-slate-50 hover:bg-slate-100 active:scale-95 text-slate-600 hover:text-indigo-600 border border-slate-200/80 rounded-xl transition-all shadow-2xs cursor-pointer ml-0.5"
              title="Làm mới dữ liệu kho"
            >
              <RefreshCw size={15} className={loading ? 'animate-spin text-indigo-600' : ''} />
            </button>
          </div>
        </div>

        {/* ── BỘ LỌC THÔNG MINH (SMART FILTERS) ── */}
        <div className="mt-5 pt-5 border-t border-slate-100/80 relative z-10">
          <div className="grid grid-cols-1 md:grid-cols-12 gap-3.5 items-end">
            {/* Lọc theo Thư Mục Kết Quả (Folder) */}
            <div className="md:col-span-5">
              <label className="block text-xs font-semibold text-slate-700 mb-1.5 flex items-center justify-between">
                <span className="flex items-center gap-1.5">
                  <Folder size={14} className="text-indigo-600" />
                  <span>Thư mục kết quả đã lưu</span>
                </span>
                {selectedFolder !== 'all' && (
                  <span className="text-[10px] font-semibold text-indigo-600 bg-indigo-50 border border-indigo-100 px-1.5 py-0.5 rounded-md">
                    Đã lọc
                  </span>
                )}
              </label>
              <div className="relative">
                <select
                  value={selectedFolder}
                  onChange={e => { setSelectedFolder(e.target.value); setPage(1); }}
                  className="w-full appearance-none bg-slate-50/80 hover:bg-white focus:bg-white border border-slate-200 hover:border-slate-300 focus:border-indigo-500 focus:ring-4 focus:ring-indigo-500/10 rounded-xl pl-3.5 pr-9 py-2.5 text-xs font-semibold text-slate-800 transition-all cursor-pointer shadow-2xs"
                >
                  <option value="all">🌟 Tất cả thư mục kết quả ({totalRecords} hồ sơ)</option>
                  {folderOptions.map(f => (
                    <option key={f.name} value={f.name}>
                      📁 {f.name} ({f.count} hồ sơ) {f.date ? `• ${f.date}` : ''}
                    </option>
                  ))}
                </select>
                <ChevronDown size={14} className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-slate-400" />
              </div>
            </div>

            {/* Lọc theo Đường Dẫn Máy (Source Path) */}
            <div className="md:col-span-4">
              <label className="block text-xs font-semibold text-slate-700 mb-1.5 flex items-center justify-between">
                <span className="flex items-center gap-1.5">
                  <HardDrive size={14} className="text-violet-600" />
                  <span>Đường dẫn trên máy</span>
                </span>
                {selectedSource !== 'all' && (
                  <span className="text-[10px] font-semibold text-violet-600 bg-violet-50 border border-violet-100 px-1.5 py-0.5 rounded-md">
                    Đã lọc
                  </span>
                )}
              </label>
              <div className="relative">
                <select
                  value={selectedSource}
                  onChange={e => { setSelectedSource(e.target.value); setPage(1); }}
                  className="w-full appearance-none bg-slate-50/80 hover:bg-white focus:bg-white border border-slate-200 hover:border-slate-300 focus:border-indigo-500 focus:ring-4 focus:ring-indigo-500/10 rounded-xl pl-3.5 pr-9 py-2.5 text-xs font-semibold text-slate-800 transition-all cursor-pointer truncate shadow-2xs"
                  title={selectedSource !== 'all' ? selectedSource : 'Tất cả đường dẫn trên máy'}
                >
                  <option value="all">💻 Tất cả link trên máy</option>
                  {sourceOptions.map(s => (
                    <option key={s.path} value={s.path} title={s.path}>
                      💻 {s.path} ({s.count} file)
                    </option>
                  ))}
                </select>
                <ChevronDown size={14} className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-slate-400" />
              </div>
            </div>

            {/* Ô Tìm Kiếm Từ Khóa */}
            <div className="md:col-span-3">
              <label className="block text-xs font-semibold text-slate-700 mb-1.5 flex items-center gap-1.5">
                <Search size={14} className="text-slate-500" />
                <span>Tìm từ khóa</span>
              </label>
              <div className="relative">
                <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none" />
                <input
                  type="text"
                  value={search}
                  onChange={e => { setSearch(e.target.value); setPage(1); }}
                  placeholder="Tên file, tên chủ, số phát hành..."
                  className="w-full pl-9 pr-8 py-2.5 bg-slate-50/80 hover:bg-white focus:bg-white border border-slate-200 hover:border-slate-300 focus:border-indigo-500 focus:ring-4 focus:ring-indigo-500/10 rounded-xl text-xs font-medium text-slate-800 placeholder:text-slate-400 transition-all shadow-2xs"
                />
                {search && (
                  <button
                    type="button"
                    onClick={() => { setSearch(''); setPage(1); }}
                    className="absolute right-2.5 top-1/2 -translate-y-1/2 p-1 text-slate-400 hover:text-slate-600 rounded-full hover:bg-slate-200/60 transition cursor-pointer"
                    title="Xóa từ khóa tìm kiếm"
                  >
                    <X size={12} />
                  </button>
                )}
              </div>
            </div>
          </div>

          {/* Active Filter Chips & Reset */}
          {(selectedFolder !== 'all' || selectedSource !== 'all' || search) && (
            <div className="mt-4 pt-3.5 border-t border-slate-100 flex flex-wrap items-center gap-2 text-xs">
              <div className="inline-flex items-center gap-1.5 text-slate-500 font-semibold text-[11px] bg-slate-100/90 px-2.5 py-1 rounded-lg">
                <Filter size={12} className="text-slate-600" />
                <span>Đang lọc:</span>
              </div>

              {selectedFolder !== 'all' && (
                <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-indigo-50 text-indigo-700 border border-indigo-200/80 font-medium text-xs shadow-2xs">
                  <Folder size={12} className="text-indigo-500 shrink-0" />
                  <span className="truncate max-w-[200px]" title={selectedFolder}>
                    Folder: <strong className="font-semibold">{selectedFolder}</strong>
                  </span>
                  <button
                    onClick={() => { setSelectedFolder('all'); setPage(1); }}
                    className="p-0.5 hover:bg-indigo-200/60 rounded text-indigo-500 hover:text-indigo-800 transition cursor-pointer"
                    title="Bỏ lọc thư mục này"
                  >
                    <X size={12} />
                  </button>
                </span>
              )}

              {selectedSource !== 'all' && (
                <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-violet-50 text-violet-700 border border-violet-200/80 font-medium text-xs shadow-2xs max-w-sm">
                  <HardDrive size={12} className="text-violet-500 shrink-0" />
                  <span className="truncate" title={selectedSource}>
                    Link: <strong className="font-semibold">{selectedSource}</strong>
                  </span>
                  <button
                    onClick={() => { setSelectedSource('all'); setPage(1); }}
                    className="p-0.5 hover:bg-violet-200/60 rounded text-violet-500 hover:text-violet-800 transition shrink-0 cursor-pointer"
                    title="Bỏ lọc link máy này"
                  >
                    <X size={12} />
                  </button>
                </span>
              )}

              {search && (
                <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-sky-50 text-sky-700 border border-sky-200/80 font-medium text-xs shadow-2xs">
                  <Search size={12} className="text-sky-500 shrink-0" />
                  <span>
                    Từ khóa: <strong className="font-semibold">"{search}"</strong>
                  </span>
                  <button
                    onClick={() => { setSearch(''); setPage(1); }}
                    className="p-0.5 hover:bg-sky-200/60 rounded text-sky-500 hover:text-sky-800 transition cursor-pointer"
                    title="Bỏ từ khóa tìm kiếm"
                  >
                    <X size={12} />
                  </button>
                </span>
              )}

              <button
                onClick={() => {
                  setSelectedFolder('all');
                  setSelectedSource('all');
                  setSearch('');
                  setPage(1);
                }}
                className="inline-flex items-center gap-1.5 px-3 py-1 rounded-lg bg-rose-50 hover:bg-rose-100 active:scale-95 text-rose-600 hover:text-rose-700 border border-rose-200/80 font-semibold text-xs transition-all cursor-pointer ml-auto sm:ml-2 shadow-2xs"
                title="Xóa toàn bộ bộ lọc đang chọn"
              >
                <RotateCcw size={12} />
                <span>Xóa tất cả bộ lọc</span>
              </button>
            </div>
          )}
        </div>
      </div>

      {/* ── ACTION BAR: QUẢN LÝ & XUẤT DỮ LIỆU ── */}
      <div className="bg-white rounded-2xl p-4 border border-slate-200/80 shadow-sm flex flex-wrap items-center justify-between gap-3">
        {/* Nhóm Thông Tin & Xóa Theo Bộ Lọc */}
        <div className="flex flex-wrap items-center gap-2.5">
          {can('record.delete') && selectedFolder !== 'all' && (
            <button
              onClick={() => setDeleteConfirm({
                open: true,
                type: 'folder',
                targetName: selectedFolder
              })}
              className="px-3 py-2 bg-rose-50 hover:bg-rose-100 active:scale-95 text-rose-700 border border-rose-200 text-xs font-semibold rounded-xl transition flex items-center gap-1.5 shadow-2xs cursor-pointer"
              title={`Xóa toàn bộ hồ sơ thuộc thư mục kết quả "${selectedFolder}"`}
            >
              <Trash2 size={14} />
              <span>Xóa cả thư mục "{selectedFolder}"</span>
            </button>
          )}

          {can('record.delete') && selectedSource !== 'all' && (
            <button
              onClick={() => setDeleteConfirm({
                open: true,
                type: 'source',
                targetName: selectedSource
              })}
              className="px-3 py-2 bg-rose-50 hover:bg-rose-100 active:scale-95 text-rose-700 border border-rose-200 text-xs font-semibold rounded-xl transition flex items-center gap-1.5 max-w-xs truncate shadow-2xs cursor-pointer"
              title={`Xóa toàn bộ hồ sơ có đường dẫn trên máy thuộc "${selectedSource}"`}
            >
              <Trash2 size={14} />
              <span>Xóa theo link máy này</span>
            </button>
          )}

          <div className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-slate-50 border border-slate-200/70 rounded-xl text-xs text-slate-600 font-medium shadow-2xs">
            <Database size={13} className="text-slate-400" />
            <span>Hiển thị: <strong className="text-slate-900 font-bold">{records.length}</strong> / {totalRecords} hồ sơ</span>
          </div>
        </div>

        {/* Nhóm Hành Động Tải Dữ Liệu Thô, Xuất 129 Cột & Xem Bảng */}
        <div className="flex items-center gap-2 flex-wrap">
          {/* Menu Tải Dữ Liệu Thô (JSON, Markdown, Excel thô) */}
          {can('export.raw') && <div className="relative">
            <button
              onClick={() => setShowDownloadMenu(!showDownloadMenu)}
              disabled={records.length === 0 || downloadingRawDb || downloadingRawMarkdown || downloadingRawExcel}
              className="px-3.5 py-2.5 bg-slate-900 hover:bg-slate-800 disabled:bg-slate-200 text-white disabled:text-slate-400 text-xs font-semibold rounded-xl transition flex items-center gap-2 shadow-sm cursor-pointer disabled:cursor-not-allowed"
              title="Tải dữ liệu thô (JSON / Markdown / Excel thô) về máy"
            >
              <Database size={14} />
              <span>
                {downloadingRawDb ? 'Đang tải JSON...' : downloadingRawMarkdown ? 'Đang tải Markdown...' : downloadingRawExcel ? 'Đang tải Excel...' : 'Tải Dữ Liệu Thô'}
              </span>
              <ChevronDown size={13} className={`transition-transform duration-200 ${showDownloadMenu ? 'rotate-180' : ''}`} />
            </button>

            {showDownloadMenu && (
              <>
                <div
                  className="fixed inset-0 z-20"
                  onClick={() => setShowDownloadMenu(false)}
                />
                <div className="absolute right-0 mt-2 w-72 bg-white rounded-2xl shadow-2xl border border-slate-200/90 py-2 z-30 animate-in fade-in duration-100">
                  <button
                    onClick={() => { setShowDownloadMenu(false); handleDownloadRawDb(); }}
                    className="w-full px-4 py-2.5 text-left text-xs text-slate-700 hover:bg-indigo-50/80 hover:text-indigo-700 flex items-start gap-3 transition cursor-pointer"
                  >
                    <FileCode size={16} className="text-indigo-600 mt-0.5 shrink-0" />
                    <div>
                      <div className="font-bold text-slate-800">Tải CSDL Thô (.json)</div>
                      <div className="text-[11px] text-slate-500 font-normal mt-0.5">
                        Bản sao lưu toàn bộ bản ghi & dữ liệu bóc tách dạng JSON
                      </div>
                    </div>
                  </button>
                  <button
                    onClick={() => { setShowDownloadMenu(false); handleDownloadRawMarkdown(); }}
                    className="w-full px-4 py-2.5 text-left text-xs text-slate-700 hover:bg-emerald-50/80 hover:text-emerald-700 flex items-start gap-3 transition border-t border-slate-100 cursor-pointer"
                  >
                    <FileText size={16} className="text-emerald-600 mt-0.5 shrink-0" />
                    <div>
                      <div className="font-bold text-slate-800">Tải Gói Markdown Thô (.zip)</div>
                      <div className="text-[11px] text-slate-500 font-normal mt-0.5">
                        Tập hợp file văn bản Markdown (.md) thô của các hồ sơ
                      </div>
                    </div>
                  </button>
                  <button
                    onClick={() => { setShowDownloadMenu(false); handleExportRawExcel(); }}
                    className="w-full px-4 py-2.5 text-left text-xs text-slate-700 hover:bg-teal-50/80 hover:text-teal-700 flex items-start gap-3 transition border-t border-slate-100 cursor-pointer"
                  >
                    <FileSpreadsheet size={16} className="text-teal-600 mt-0.5 shrink-0" />
                    <div>
                      <div className="font-bold text-slate-800">Tải Bảng Tổng Hợp Thô (.xlsx)</div>
                      <div className="text-[11px] text-slate-500 font-normal mt-0.5">
                        Bảng tính Excel tổng hợp dữ liệu và toàn văn bóc tách
                      </div>
                    </div>
                  </button>
                </div>
              </>
            )}
          </div>}

          {can('export.129') && <button
            onClick={handleExport129Excel}
            disabled={exportingExcel || records.length === 0}
            className="px-4 py-2.5 bg-emerald-600 hover:bg-emerald-700 active:scale-95 disabled:bg-slate-200 text-white disabled:text-slate-400 text-xs font-semibold rounded-xl transition flex items-center gap-2 shadow-sm shadow-emerald-600/20 cursor-pointer disabled:cursor-not-allowed"
            title="Xuất file Excel 129 cột cho tập hồ sơ đang lọc"
          >
            <FileSpreadsheet size={15} />
            <span>{exportingExcel ? 'Đang xuất Excel...' : 'Xuất Excel 129 Cột'}</span>
          </button>}

          <button
            onClick={handleViewIn129Table}
            disabled={records.length === 0}
            className="px-4 py-2.5 bg-indigo-600 hover:bg-indigo-700 active:scale-95 disabled:bg-slate-200 text-white disabled:text-slate-400 text-xs font-semibold rounded-xl transition flex items-center gap-2 shadow-sm shadow-indigo-600/20 cursor-pointer disabled:cursor-not-allowed"
            title="Nạp toàn bộ dữ liệu đang lọc vào giao diện Bảng 129 Cột"
          >
            <span>Xem Trên Bảng 129 Cột</span>
            <ArrowRight size={14} />
          </button>
        </div>
      </div>

      {/* ── BẢNG DANH SÁCH HỒ SƠ TỪ POSTGRESQL ── */}
      <div className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
        <div className="overflow-x-auto min-h-[350px]">
          <table className="w-full text-left text-xs text-slate-700 border-collapse">
            <thead className="bg-slate-50 text-[11px] font-bold text-slate-600 uppercase tracking-wider sticky top-0 z-10 border-b border-slate-200">
              <tr>
                <th className="py-3 px-3 w-12 text-center">STT</th>
                <th className="py-3 px-3 min-w-[200px]">Tên tệp & Link máy</th>
                <th className="py-3 px-3 min-w-[140px]">Thư mục kết quả</th>
                <th className="py-3 px-3 w-20 text-center">Mẫu</th>
                <th className="py-3 px-3 min-w-[120px]">Số phát hành</th>
                <th className="py-3 px-3 min-w-[160px]">Họ tên chủ</th>
                <th className="py-3 px-3 w-24 text-center">Thửa / Tờ</th>
                <th className="py-3 px-3 min-w-[130px]">Thời gian lưu</th>
                <th className="py-3 px-3 w-24 text-center">Trạng thái</th>
                <th className="py-3 px-3 w-40 text-center">Thao tác</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 font-medium">
              {loading && records.length === 0 ? (
                <tr>
                  <td colSpan={10} className="py-16 text-center text-slate-400">
                    <RefreshCw size={24} className="animate-spin mx-auto mb-2 text-indigo-500" />
                    <span>Đang tải dữ liệu từ PostgreSQL...</span>
                  </td>
                </tr>
              ) : records.length === 0 ? (
                <tr>
                  <td colSpan={10} className="py-16 text-center text-slate-400">
                    <FileText size={36} className="mx-auto mb-2 text-slate-300" />
                    <p className="text-sm font-semibold text-slate-600">Không tìm thấy hồ sơ nào trong PostgreSQL</p>
                    <p className="text-xs text-slate-400 mt-1">Hãy quét thư mục hoặc nhận dạng file để lưu dữ liệu vào đây.</p>
                  </td>
                </tr>
              ) : (
                records.map((r, idx) => {
                  const sttNumber = (page - 1) * limit + idx + 1;
                  return (
                    <tr key={r.id} className="hover:bg-indigo-50/40 transition">
                      <td className="py-3 px-3 text-center text-slate-400 font-mono text-[11px]">
                        {sttNumber}
                      </td>
                      <td className="py-3 px-3">
                        <button
                          type="button"
                          onClick={() => setReviewDocId(r.id)}
                          className="block max-w-[220px] truncate text-left font-bold text-slate-900 transition hover:text-emerald-700 hover:underline"
                          title="Mở tra soát nhanh hồ sơ"
                        >
                          {r.file_name}
                        </button>
                        {r.source_path && (
                          <div className="text-[10px] text-slate-400 font-mono truncate max-w-[220px]" title={r.source_path}>
                            {r.source_path}
                          </div>
                        )}
                      </td>
                      <td className="py-3 px-3">
                        <span className="px-2 py-0.5 rounded-lg text-[10px] font-bold bg-slate-100 text-indigo-700 border border-slate-200">
                          {r.folder_result || r.batch_id || 'Khác'}
                        </span>
                      </td>
                      <td className="py-3 px-3 text-center">
                        <span className="px-1.5 py-0.5 rounded text-[10px] font-bold bg-slate-100 text-slate-700">
                          {r.template || '-'}
                        </span>
                      </td>
                      <td className="py-3 px-3 font-bold text-emerald-800">
                        <button
                          type="button"
                          onClick={() => setReviewDocId(r.id)}
                          className="transition hover:underline"
                          title="Mở tra soát nhanh hồ sơ"
                        >
                          {r.so_phat_hanh || '-'}
                        </button>
                      </td>
                      <td className="py-3 px-3 font-semibold text-slate-800 truncate max-w-[160px]" title={r.ten_chu}>
                        {r.ten_chu || '-'}
                      </td>
                      <td className="py-3 px-3 text-center font-mono text-[11px]">
                        {r.so_thua ? `${r.so_thua} / ${r.to_ban_do || '?'}` : '-'}
                      </td>
                      <td className="py-3 px-3 text-slate-500 text-[11px] font-mono">
                        {r.created_at}
                      </td>
                      <td className="py-3 px-3 text-center">
                        {r.status === 'success' ? (
                          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-100 text-emerald-800">
                            Hợp lệ
                          </span>
                        ) : (
                          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold bg-rose-100 text-rose-800">
                            Lỗi
                          </span>
                        )}
                      </td>
                      <td className="py-3 px-3 text-center">
                        <div className="flex items-center justify-center gap-1">
                          {(can('record.review') || can('record.read')) && (
                            <button
                              onClick={() => setReviewDocId(r.id)}
                              className="p-1.5 bg-emerald-50 hover:bg-emerald-100 text-emerald-700 rounded-lg transition"
                              title="Tra soát nhanh: ảnh trang, crop và box OCR"
                            >
                              <SlidersHorizontal size={13} />
                            </button>
                          )}
                          <button
                            onClick={() => handleViewDetail(r.id)}
                            className="p-1.5 bg-indigo-50 hover:bg-indigo-100 text-indigo-700 rounded-lg transition"
                            title="Xem văn bản Markdown thô"
                          >
                            <FileCode size={13} />
                          </button>
                          <button
                            onClick={() => handleOpenExcelPreview(r.id)}
                            className="p-1.5 bg-teal-50 hover:bg-teal-100 text-teal-700 rounded-lg transition"
                            title="Xem trước bảng tính Excel"
                          >
                            <Eye size={13} />
                          </button>
                          <button
                            onClick={() => handleDownloadMd(r.id)}
                            className="p-1.5 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-lg transition"
                            title="Tải tệp .md"
                          >
                            <Download size={13} />
                          </button>
                          {can('record.delete') && (
                            <button
                              onClick={() => setDeleteConfirm({
                                open: true,
                                type: 'single',
                                targetName: r.file_name,
                                targetIds: [r.id]
                              })}
                              className="p-1.5 bg-rose-50 hover:bg-rose-100 text-rose-600 rounded-lg transition"
                              title="Xóa bản ghi này khỏi PostgreSQL"
                            >
                              <Trash2 size={13} />
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>

        {/* Phân trang (Pagination) */}
        {totalRecords > limit && (
          <div className="px-6 py-3 border-t border-slate-100 bg-slate-50 flex items-center justify-between text-xs text-slate-600">
            <div>
              Trang <b>{page}</b> / <b>{totalPages}</b> (Tổng số: {totalRecords} hồ sơ)
            </div>
            <div className="flex items-center gap-1.5">
              <button
                onClick={() => setPage(prev => Math.max(1, prev - 1))}
                disabled={page === 1}
                className="px-3 py-1.5 bg-white hover:bg-slate-100 disabled:opacity-40 border border-slate-200 rounded-lg font-semibold transition"
              >
                Trang trước
              </button>
              <button
                onClick={() => setPage(prev => Math.min(totalPages, prev + 1))}
                disabled={page >= totalPages}
                className="px-3 py-1.5 bg-white hover:bg-slate-100 disabled:opacity-40 border border-slate-200 rounded-lg font-semibold transition"
              >
                Trang tiếp
              </button>
            </div>
          </div>
        )}
      </div>

      {/* ── MODAL XÁC NHẬN XÓA CÓ CHỌN LỌC ── */}
      {deleteConfirm && (
        <div className="fixed inset-0 z-50 bg-slate-900/60 backdrop-blur-sm flex items-center justify-center p-4 animate-in fade-in duration-150">
          <div className="bg-white rounded-2xl max-w-md w-full p-6 shadow-2xl border border-slate-200 space-y-4">
            <div className="w-12 h-12 rounded-full bg-rose-100 text-rose-600 flex items-center justify-center mx-auto">
              <AlertTriangle size={24} />
            </div>
            <div className="text-center">
              <h3 className="text-base font-bold text-slate-900">Xác Nhận Xóa Dữ Liệu Trong PostgreSQL</h3>
              <p className="text-xs text-slate-500 mt-2 leading-relaxed">
                {deleteConfirm.type === 'single' && (
                  <>Bạn có chắc chắn muốn xóa hồ sơ <b>"{deleteConfirm.targetName}"</b> khỏi PostgreSQL?</>
                )}
                {deleteConfirm.type === 'folder' && (
                  <>Bạn có chắc chắn muốn xóa toàn bộ hồ sơ thuộc thư mục kết quả <b>"{deleteConfirm.targetName}"</b> khỏi PostgreSQL?</>
                )}
                {deleteConfirm.type === 'source' && (
                  <>Bạn có chắc chắn muốn xóa toàn bộ hồ sơ có link trên máy thuộc <b>"{deleteConfirm.targetName}"</b> khỏi PostgreSQL?</>
                )}
              </p>
              <p className="text-[11px] text-rose-600 font-semibold mt-1">
                Thao tác này sẽ xóa các bản ghi được chỉ định.
              </p>
            </div>

            <div className="flex gap-3 pt-2">
              <button
                onClick={() => setDeleteConfirm(null)}
                disabled={deleting}
                className="flex-1 py-2.5 bg-slate-100 hover:bg-slate-200 text-slate-700 text-xs font-semibold rounded-xl transition"
              >
                Hủy bỏ
              </button>
              <button
                onClick={executeDelete}
                disabled={deleting}
                className="flex-1 py-2.5 bg-rose-600 hover:bg-rose-700 text-white text-xs font-bold rounded-xl transition flex items-center justify-center gap-1.5 shadow-sm"
              >
                {deleting ? <RefreshCw size={14} className="animate-spin" /> : <Trash2 size={14} />}
                <span>{deleting ? 'Đang xóa...' : 'Đồng ý xóa'}</span>
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── MODAL XEM NHANH MARKDOWN THÔ ── */}
      {selectedDocId && (
        <div className="fixed inset-0 z-50 bg-slate-900/60 backdrop-blur-sm flex items-center justify-center p-4 sm:p-6 animate-in fade-in duration-200">
          <div className="bg-white rounded-2xl max-w-4xl w-full h-[85vh] flex flex-col shadow-2xl border border-slate-200 overflow-hidden">
            <div className="px-6 py-4 border-b border-slate-200 bg-slate-50 flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="w-9 h-9 rounded-lg bg-indigo-600 flex items-center justify-center text-white shadow-sm">
                  <FileCode size={18} />
                </div>
                <div>
                  <h3 className="text-sm font-bold text-slate-900">Văn Bản OCR Thô (Markdown)</h3>
                  <p className="text-xs text-slate-500 font-mono truncate max-w-md">
                    {selectedRecord?.file_name || selectedDocId}
                  </p>
                </div>
              </div>

              <div className="flex items-center gap-2">
                <button
                  onClick={() => {
                    if (selectedRecord?.raw_markdown) {
                      navigator.clipboard.writeText(selectedRecord.raw_markdown);
                      setCopied(true);
                      setTimeout(() => setCopied(false), 2000);
                    }
                  }}
                  className="px-3 py-1.5 bg-white hover:bg-slate-100 border border-slate-200 text-slate-700 text-xs font-semibold rounded-xl transition flex items-center gap-1.5 shadow-sm"
                >
                  {copied ? <Check size={14} className="text-emerald-600" /> : <Copy size={14} />}
                  <span>{copied ? 'Đã chép!' : 'Sao chép'}</span>
                </button>

                <button
                  onClick={() => handleDownloadMd(selectedDocId)}
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

            <div className="flex-1 p-6 overflow-y-auto bg-slate-950 text-slate-200 font-mono text-xs leading-relaxed selection:bg-indigo-600 selection:text-white">
              {loadingDetail ? (
                <div className="flex items-center justify-center h-full text-slate-400">
                  <RefreshCw size={24} className="animate-spin mr-2" />
                  <span>Đang nạp Markdown từ PostgreSQL...</span>
                </div>
              ) : (
                <pre className="whitespace-pre-wrap break-words font-mono">
                  {selectedRecord?.raw_markdown || '# Không có nội dung Markdown cho hồ sơ này.'}
                </pre>
              )}
            </div>

            <div className="px-6 py-3 border-t border-slate-200 bg-slate-50 flex items-center justify-end text-xs">
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

      {/* ── MODAL XEM TRƯỚC BẢNG TÍNH EXCEL (SPREADSHEET PREVIEW) ── */}
      {excelPreviewDocId && (
        <div className="fixed inset-0 z-50 bg-slate-900/60 backdrop-blur-sm flex items-center justify-center p-4 sm:p-6 animate-in fade-in duration-200">
          <div className="bg-white rounded-2xl max-w-6xl w-full h-[90vh] flex flex-col shadow-2xl border border-slate-200 overflow-hidden">
            <div className="px-6 py-4 border-b border-slate-200 bg-slate-50 flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-xl bg-teal-600 flex items-center justify-center text-white shadow-sm">
                  <FileSpreadsheet size={20} />
                </div>
                <div>
                  <h3 className="text-sm font-bold text-slate-900 flex items-center gap-2">
                    <span>Xem Trước Dữ Liệu Bảng Tính Excel</span>
                    <span className="bg-teal-100 text-teal-800 text-[10px] px-2 py-0.5 rounded-full font-bold">
                      {excelPreviewData?.template || 'Mẫu chuẩn'}
                    </span>
                  </h3>
                  <p className="text-xs text-slate-500 font-mono truncate max-w-md">
                    {excelPreviewData?.file_name || excelPreviewDocId}
                  </p>
                </div>
              </div>

              <div className="flex items-center gap-2">
                <button
                  onClick={() => excelPreviewDocId && handleDownloadMd(excelPreviewDocId)}
                  className="px-3 py-1.5 bg-white hover:bg-slate-100 border border-slate-200 text-slate-700 text-xs font-semibold rounded-xl transition flex items-center gap-1.5 shadow-sm"
                >
                  <Download size={14} />
                  <span>Tải .md</span>
                </button>
                <button
                  onClick={() => setExcelPreviewDocId(null)}
                  className="p-1.5 text-slate-400 hover:text-slate-700 hover:bg-slate-200 rounded-xl transition ml-1"
                >
                  <X size={18} />
                </button>
              </div>
            </div>

            {/* Sub-header tabs in modal */}
            <div className="px-6 py-2.5 border-b border-slate-200 bg-slate-100 flex items-center justify-between gap-4">
              <div className="flex items-center gap-2">
                <button
                  onClick={() => setActiveExcelTab('summary')}
                  className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition ${
                    activeExcelTab === 'summary' ? 'bg-white text-teal-800 shadow-sm' : 'text-slate-600 hover:text-slate-900'
                  }`}
                >
                  Bảng tổng hợp ({excelPreviewData?.summary_fields?.length || 0} trường)
                </button>
                <button
                  onClick={() => setActiveExcelTab('ocr_lines')}
                  className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition ${
                    activeExcelTab === 'ocr_lines' ? 'bg-white text-teal-800 shadow-sm' : 'text-slate-600 hover:text-slate-900'
                  }`}
                >
                  Từng dòng OCR ({excelPreviewData?.ocr_lines?.length || 0} dòng)
                </button>
                <button
                  onClick={() => setActiveExcelTab('cadastral_129')}
                  className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition ${
                    activeExcelTab === 'cadastral_129' ? 'bg-white text-teal-800 shadow-sm' : 'text-slate-600 hover:text-slate-900'
                  }`}
                >
                  Ánh xạ 129 Cột ({excelPreviewData?.cadastral_129_rows?.length || 0} dòng)
                </button>
              </div>

              <div className="relative w-64">
                <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-400" />
                <input
                  type="text"
                  value={excelFilterText}
                  onChange={e => setExcelFilterText(e.target.value)}
                  placeholder="Lọc trong bảng..."
                  className="w-full pl-7 pr-2.5 py-1 bg-white border border-slate-200 rounded-lg text-xs text-slate-800 focus:outline-teal-500"
                />
              </div>
            </div>

            {/* Modal Body */}
            <div className="flex-1 overflow-auto p-4 bg-slate-50 text-xs">
              {loadingExcelPreview ? (
                <div className="flex items-center justify-center h-full text-slate-400">
                  <RefreshCw size={24} className="animate-spin mr-2" />
                  <span>Đang dựng dữ liệu bảng tính...</span>
                </div>
              ) : activeExcelTab === 'summary' ? (
                <table className="w-full bg-white rounded-xl border border-slate-200 text-left border-collapse">
                  <thead className="bg-slate-100 text-[11px] font-bold text-slate-600 border-b border-slate-200">
                    <tr>
                      <th className="py-2.5 px-3 w-16 text-center">STT</th>
                      <th className="py-2.5 px-4 w-64">Tên trường thông tin</th>
                      <th className="py-2.5 px-4">Giá trị trích xuất</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100 font-medium">
                    {filteredSummaryFields.map((f, i) => (
                      <tr key={i} className="hover:bg-slate-50">
                        <td className="py-2 px-3 text-center text-slate-400 font-mono">{f.stt}</td>
                        <td className="py-2 px-4 font-bold text-slate-700">{f.field}</td>
                        <td className="py-2 px-4 font-mono text-slate-900">{f.value || '-'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              ) : activeExcelTab === 'ocr_lines' ? (
                <table className="w-full bg-white rounded-xl border border-slate-200 text-left border-collapse">
                  <thead className="bg-slate-100 text-[11px] font-bold text-slate-600 border-b border-slate-200">
                    <tr>
                      <th className="py-2.5 px-3 w-16 text-center">STT</th>
                      <th className="py-2.5 px-3 w-20 text-center">Trang</th>
                      <th className="py-2.5 px-4">Văn bản OCR nhận dạng được</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100 font-mono text-xs">
                    {filteredOcrLines.map((l, i) => (
                      <tr key={i} className="hover:bg-slate-50">
                        <td className="py-2 px-3 text-center text-slate-400">{l.stt}</td>
                        <td className="py-2 px-3 text-center">
                          <span className="px-1.5 py-0.5 rounded bg-slate-100 text-slate-700 text-[10px] font-bold">
                            Trang {l.page}
                          </span>
                        </td>
                        <td className="py-2 px-4 text-slate-800">{l.text}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              ) : (
                <div className="overflow-x-auto">
                  <table className="min-w-full bg-white rounded-xl border border-slate-200 text-left border-collapse text-[11px]">
                    <thead className="bg-slate-100 font-bold text-slate-700 border-b border-slate-200">
                      <tr>
                        <th className="p-2 border-r border-slate-200">STT</th>
                        <th className="p-2 border-r border-slate-200">Số phát hành</th>
                        <th className="p-2 border-r border-slate-200">Chủ sử dụng</th>
                        <th className="p-2 border-r border-slate-200">Số giấy tờ</th>
                        <th className="p-2 border-r border-slate-200">Thửa / Tờ</th>
                        <th className="p-2 border-r border-slate-200">Diện tích</th>
                        <th className="p-2 border-r border-slate-200">Địa chỉ thửa</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                      {filteredCadastralRows.map((row, i) => (
                        <tr key={i} className="hover:bg-slate-50">
                          <td className="p-2 border-r border-slate-100 text-center font-mono">{i + 1}</td>
                          <td className="p-2 border-r border-slate-100 font-bold text-emerald-700">{row.GCN_soPhatHanh || '-'}</td>
                          <td className="p-2 border-r border-slate-100 font-semibold">{row.CHU_hoTen || '-'}</td>
                          <td className="p-2 border-r border-slate-100 font-mono">{row.GT_soGiayTo || '-'}</td>
                          <td className="p-2 border-r border-slate-100 font-mono">{row.TD_soThuTuThua ? `${row.TD_soThuTuThua} / ${row.TD_soHieuToBanDo || '?'}` : '-'}</td>
                          <td className="p-2 border-r border-slate-100 font-bold text-right">{row.TD_dienTich || '-'}</td>
                          <td className="p-2 border-r border-slate-100 max-w-xs truncate">{row.TD_diaChiChiTiet || '-'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>

            <div className="px-6 py-3 border-t border-slate-200 bg-slate-50 flex items-center justify-end">
              <button
                onClick={() => setExcelPreviewDocId(null)}
                className="px-4 py-1.5 bg-slate-200 hover:bg-slate-300 text-slate-700 font-semibold rounded-lg transition"
              >
                Đóng
              </button>
            </div>
          </div>
        </div>
      )}
      {reviewDocId && (
        <QuickReviewPanel documentId={reviewDocId} onClose={() => setReviewDocId(null)} />
      )}
    </div>
  );
};
