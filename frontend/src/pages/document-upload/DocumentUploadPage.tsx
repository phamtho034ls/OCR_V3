import React, { useState, useMemo } from 'react';
import axios from 'axios';
import {
  UploadCloud,
  CheckCircle2,
  AlertCircle,
  Loader2,
  RotateCw,
  ZoomIn,
  ZoomOut,
  Maximize2,
  FileSpreadsheet,
  Code,
  Scissors,
  ExternalLink,
  ChevronDown,
  ChevronUp,
  UserCheck,
  Check,
  Building,
  FileText,
  MapPin,
  Stamp,
  RefreshCw,
  Layers,
  ShieldCheck,
  AlertTriangle,
  Table as TableIcon,
  LayoutGrid
} from 'lucide-react';
import { DocumentResult, PageResult, CropItem, ParcelItem } from '../../shared/types';

export const DocumentUploadPage: React.FC = () => {
  const [file, setFile] = useState<File | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [result, setResult] = useState<DocumentResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Viewer state
  const [activePageIndex, setActivePageIndex] = useState<number>(0);
  const [rotation, setRotation] = useState<number>(0);
  const [zoom, setZoom] = useState<number>(1);
  const [showCropGallery, setShowCropGallery] = useState<boolean>(false);
  const [cropDiffOnly, setCropDiffOnly] = useState<boolean>(false);
  const [exportingExcel, setExportingExcel] = useState<boolean>(false);
  const [parcelViewMode, setParcelViewMode] = useState<'table' | 'cards'>('table');

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      setFile(e.target.files[0]);
      setResult(null);
      setError(null);
      setActivePageIndex(0);
      setRotation(0);
      setZoom(1);
    }
  };

  const handleUpload = async () => {
    if (!file) return;
    setLoading(true);
    setError(null);

    const formData = new FormData();
    formData.append('file', file);

    try {
      const res = await axios.post('/api/v1/documents', formData);
      const data: DocumentResult = res.data.data;
      setResult(data);

      if (data.selected_page_index !== undefined) {
        setActivePageIndex(data.selected_page_index);
      } else {
        setActivePageIndex(0);
      }
      setRotation(0);
      setZoom(1);
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message || 'Lỗi xử lý tài liệu');
    } finally {
      setLoading(false);
    }
  };

  // Export JSON
  const handleExportJSON = () => {
    if (!result) return;
    const blob = new Blob([JSON.stringify(result, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${result.document_id || 'ocr_result'}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  // Export Excel
  const handleExportExcel = async () => {
    if (!result) return;
    setExportingExcel(true);
    try {
      const rows = result.chuyen_doi_rows && result.chuyen_doi_rows.length > 0
        ? result.chuyen_doi_rows
        : [];

      if (rows.length === 0) {
        alert('Không có hàng dữ liệu 129 cột để xuất');
        return;
      }

      const res = await axios.post(
        '/chuyen-doi/export',
        {
          rows: rows,
          filename: `GCN_${result.so_phat_hanh || result.document_id || 'export'}.xlsx`
        },
        { responseType: 'blob' }
      );

      const blob = new Blob([res.data], {
        type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `GCN_${result.so_phat_hanh || result.document_id || 'export'}.xlsx`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err: any) {
      alert('Lỗi xuất file Excel: ' + (err.response?.data?.detail || err.message));
    } finally {
      setExportingExcel(false);
    }
  };

  const pages: PageResult[] = result?.pages || [];
  const activePage: PageResult | undefined = pages[activePageIndex] || pages[0];
  const previewImgUrl = activePage?.preview_url || result?.preview_url || '';
  const diagramUrl = result?.attachments?.so_do_thua_dat || activePage?.diagram_url || '';

  // All crops
  const allCrops: CropItem[] = result?.crops || activePage?.crops || [];
  const filteredCrops = cropDiffOnly
    ? allCrops.filter(c => c.paddle_text && c.viet_text && c.paddle_text.trim() !== c.viet_text.trim())
    : allCrops;

  // Formatting helpers
  const nguoi = result?.nguoi_su_dung || {};
  const thua = result?.thua_dat || {};
  const taisan = result?.tai_san || {};
  const cap = result?.cap_gcn || {};
  const bd = result?.bien_dong || {};

  // Danh sách chi tiết từng thửa đất (chuẩn hóa hiển thị bảng đầy đủ như Ảnh 2)
  const danhSachThua: Array<{
    stt: number;
    so_thua: string;
    to_ban_do: string;
    dia_chi: string;
    dien_tich_rieng: string | number;
    dien_tich_chung: string | number;
    dien_tich_tong?: string | number;
    muc_dich_su_dung: string;
    ma_muc_dich?: string;
    thoi_han: string;
    nguon_goc: string;
    nguon_goc_ky_hieu?: string;
  }> = useMemo(() => {
    // 1. Ưu tiên danh_sach_thua tường minh từ backend
    if (thua?.danh_sach_thua && Array.isArray(thua.danh_sach_thua) && thua.danh_sach_thua.length > 0) {
      return thua.danh_sach_thua.map((item: any, idx: number) => ({
        stt: idx + 1,
        so_thua: String(item.so_thua || '-'),
        to_ban_do: String(item.to_ban_do || thua.to_ban_do || '-'),
        dia_chi: item.dia_chi || thua.dia_chi || '-',
        dien_tich_rieng: item.dien_tich_rieng !== undefined && item.dien_tich_rieng !== null && item.dien_tich_rieng !== ''
          ? item.dien_tich_rieng
          : (item.dien_tich !== undefined && item.dien_tich !== null && item.dien_tich !== ''
              ? item.dien_tich
              : (thua.dien_tich_rieng || '-')),
        dien_tich_chung: item.dien_tich_chung !== undefined && item.dien_tich_chung !== null && item.dien_tich_chung !== ''
          ? item.dien_tich_chung
          : (thua.dien_tich_chung || 'không'),
        dien_tich_tong: item.dien_tich || item.dien_tich_rieng,
        muc_dich_su_dung: item.muc_dich_su_dung || thua.muc_dich_su_dung || '-',
        ma_muc_dich: item.ma_muc_dich || thua.ma_muc_dich || '',
        thoi_han: item.thoi_han || item.thoi_han_su_dung || thua.thoi_han || thua.thoi_han_su_dung || '-',
        nguon_goc: item.nguon_goc || item.nguon_goc_su_dung || thua.nguon_goc || thua.nguon_goc_su_dung || '-',
        nguon_goc_ky_hieu: item.nguon_goc_ky_hieu || thua.nguon_goc_ky_hieu || '',
      }));
    }

    // 2. Dự phòng từ chuyen_doi_rows (nếu có tách nhiều dòng 129 cột)
    if (result?.chuyen_doi_rows && Array.isArray(result.chuyen_doi_rows) && result.chuyen_doi_rows.length > 0) {
      const validRows = result.chuyen_doi_rows.filter((r: any) => r.TD_soThuTuThua || r.TD_dienTich);
      if (validRows.length > 0) {
        return validRows.map((r: any, idx: number) => ({
          stt: idx + 1,
          so_thua: String(r.TD_soThuTuThua || '-'),
          to_ban_do: String(r.TD_soHieuToBanDo || thua.to_ban_do || '-'),
          dia_chi: r.TD_diaChiChiTiet || thua.dia_chi || '-',
          dien_tich_rieng: r.TD_dienTich !== undefined ? r.TD_dienTich : (thua.dien_tich_rieng || '-'),
          dien_tich_chung: 'không',
          dien_tich_tong: r.TD_dienTich,
          muc_dich_su_dung: r.TD_maMucDichSuDung ? (thua.muc_dich_su_dung || r.TD_maMucDichSuDung) : (thua.muc_dich_su_dung || '-'),
          ma_muc_dich: r.TD_maMucDichSuDung || thua.ma_muc_dich || '',
          thoi_han: r.TD_thoiHanSuDung || thua.thoi_han || '-',
          nguon_goc: r.TD_nguonGoc || thua.nguon_goc || '-',
          nguon_goc_ky_hieu: thua.nguon_goc_ky_hieu || '',
        }));
      }
    }

    // 3. Dự phòng tách chuỗi số thửa nối bởi dấu '+' (ví dụ: '22+23+12+24+25')
    if (thua?.so_thua && String(thua.so_thua).includes('+')) {
      const stParts = String(thua.so_thua).split('+').map(s => s.trim()).filter(Boolean);
      const tbParts = (thua.to_ban_do ? String(thua.to_ban_do).split('+').map(s => s.trim()).filter(Boolean) : []);
      return stParts.map((st, idx) => ({
        stt: idx + 1,
        so_thua: st,
        to_ban_do: tbParts[idx % tbParts.length] || thua.to_ban_do || '-',
        dia_chi: thua.dia_chi || '-',
        dien_tich_rieng: idx === 0 ? (thua.dien_tich_rieng || thua.dien_tich_cap || '-') : '-',
        dien_tich_chung: thua.dien_tich_chung || 'không',
        dien_tich_tong: thua.dien_tich_cap,
        muc_dich_su_dung: thua.muc_dich_su_dung || '-',
        ma_muc_dich: thua.ma_muc_dich || '',
        thoi_han: thua.thoi_han || thua.thoi_han_su_dung || '-',
        nguon_goc: thua.nguon_goc || thua.nguon_goc_su_dung || '-',
        nguon_goc_ky_hieu: thua.nguon_goc_ky_hieu || '',
      }));
    }

    // 4. Sổ 1 thửa đơn
    if (thua?.so_thua) {
      return [{
        stt: 1,
        so_thua: String(thua.so_thua),
        to_ban_do: String(thua.to_ban_do || '-'),
        dia_chi: thua.dia_chi || '-',
        dien_tich_rieng: thua.dien_tich_rieng || thua.dien_tich_cap || '-',
        dien_tich_chung: thua.dien_tich_chung || 'không',
        dien_tich_tong: thua.dien_tich_cap,
        muc_dich_su_dung: thua.muc_dich_su_dung || '-',
        ma_muc_dich: thua.ma_muc_dich || '',
        thoi_han: thua.thoi_han || thua.thoi_han_su_dung || '-',
        nguon_goc: thua.nguon_goc || thua.nguon_goc_su_dung || '-',
        nguon_goc_ky_hieu: thua.nguon_goc_ky_hieu || '',
      }];
    }

    return [];
  }, [thua, result]);

  // Tổng diện tích tính toán từ các dòng thửa
  const totalRowArea = useMemo(() => {
    let sum = 0;
    let hasArea = false;
    danhSachThua.forEach(r => {
      const val = parseFloat(String(r.dien_tich_rieng).replace(',', '.'));
      if (!isNaN(val) && val > 0) {
        sum += val;
        hasArea = true;
      }
    });
    return hasArea ? Math.round(sum * 100) / 100 : null;
  }, [danhSachThua]);

  return (
    <div className="space-y-6 max-w-7xl mx-auto pb-12">
      {/* Upload Box */}
      <div className="bg-white border-2 border-dashed border-slate-300 hover:border-emerald-500 rounded-2xl p-6 text-center transition shadow-sm">
        <input
          type="file"
          id="file-upload"
          className="hidden"
          accept=".pdf,.png,.jpg,.jpeg,.tif,.tiff"
          onChange={handleFileChange}
        />
        <div className="space-y-3">
          <div className="w-12 h-12 mx-auto rounded-full bg-emerald-50 text-emerald-600 flex items-center justify-center text-xl shadow-inner">
            <UploadCloud size={24} />
          </div>
          <div>
            <h3 className="text-base font-bold text-slate-800">
              {file ? file.name : 'Kéo thả file PDF hoặc ảnh Giấy chứng nhận vào đây'}
            </h3>
            <p className="text-xs text-slate-500 mt-0.5">
              Hỗ trợ tự động tách scan đôi A3, nắn thẳng Deskew, xoay đúng chiều & nhận dạng toàn diện 29 trường
            </p>
          </div>
          <div className="flex items-center justify-center gap-3 pt-1">
            <label
              htmlFor="file-upload"
              className="px-4 py-2 bg-slate-100 hover:bg-slate-200 text-slate-700 text-xs font-semibold rounded-xl cursor-pointer transition flex items-center gap-1.5"
            >
              <FileText size={14} /> Chọn File Từ Máy Tính
            </label>
            {file && (
              <button
                onClick={handleUpload}
                disabled={loading}
                className="px-5 py-2 bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-semibold rounded-xl shadow-md transition flex items-center gap-2"
              >
                {loading && <Loader2 size={15} className="animate-spin" />}
                {loading ? 'Đang OCR pipeline...' : 'Bắt Đầu Nhận Dạng'}
              </button>
            )}
          </div>
        </div>
      </div>

      {error && (
        <div className="p-4 bg-rose-50 border border-rose-200 rounded-xl text-rose-700 text-xs flex items-center gap-2">
          <AlertCircle size={16} />
          <span>{error}</span>
        </div>
      )}

      {/* Main Split View */}
      {result && (
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
          
          {/* ── CỘT TRÁI: ẢNH TÀI LIỆU, CHUYỂN TRANG, SƠ ĐỒ & CROP GALLERY ── */}
          <div className="lg:col-span-5 bg-white rounded-2xl border border-slate-200 shadow-sm p-4 space-y-4 sticky top-20">
            {/* Toolbar */}
            <div className="flex items-center justify-between border-b border-slate-100 pb-3">
              <div className="flex items-center gap-2">
                <span className="text-sm font-bold text-slate-800">Ảnh Tài Liệu</span>
                <span className="text-xs bg-emerald-50 text-emerald-700 px-2 py-0.5 rounded-full font-bold border border-emerald-200">
                  Trang {activePageIndex + 1}/{pages.length || 1}
                </span>
              </div>
              <div className="flex items-center gap-1 text-slate-600">
                <button
                  onClick={() => setRotation((r) => (r + 90) % 360)}
                  className="p-1.5 hover:bg-slate-100 rounded text-xs transition"
                  title="Xoay 90°"
                >
                  <RotateCw size={15} />
                </button>
                <button
                  onClick={() => setZoom((z) => Math.min(2.5, z + 0.2))}
                  className="p-1.5 hover:bg-slate-100 rounded text-xs transition"
                  title="Phóng to"
                >
                  <ZoomIn size={15} />
                </button>
                <button
                  onClick={() => setZoom((z) => Math.max(0.6, z - 0.2))}
                  className="p-1.5 hover:bg-slate-100 rounded text-xs transition"
                  title="Thu nhỏ"
                >
                  <ZoomOut size={15} />
                </button>
                <button
                  onClick={() => { setZoom(1); setRotation(0); }}
                  className="p-1.5 hover:bg-slate-100 rounded text-xs transition"
                  title="Reset hiển thị"
                >
                  <Maximize2 size={15} />
                </button>
              </div>
            </div>

            {/* Canvas / Image Box */}
            <div className="relative w-full h-[540px] bg-slate-950 rounded-xl overflow-hidden flex items-center justify-center border border-slate-800 shadow-inner">
              {previewImgUrl ? (
                <img
                  src={previewImgUrl}
                  alt={`Trang ${activePageIndex + 1}`}
                  style={{
                    transform: `rotate(${rotation}deg) scale(${zoom})`,
                    transition: 'transform 0.2s ease-out'
                  }}
                  className="max-h-full max-w-full object-contain select-none"
                />
              ) : (
                <div className="text-slate-500 text-xs text-center p-6">
                  <FileText size={36} className="mx-auto mb-2 opacity-40" />
                  Chưa có ảnh preview trang
                </div>
              )}
            </div>

            {/* Page Switcher Bar */}
            {pages.length > 1 && (
              <div>
                <div className="text-[11px] font-bold text-slate-500 uppercase tracking-wider mb-1.5 flex items-center gap-1">
                  <Layers size={13} className="text-emerald-600" /> Chọn trang để đối soát:
                </div>
                <div className="flex flex-wrap items-center gap-1.5">
                  {pages.map((p, idx) => {
                    const isActive = idx === activePageIndex;
                    return (
                      <button
                        key={idx}
                        onClick={() => {
                          setActivePageIndex(idx);
                          setRotation(0);
                        }}
                        className={`px-3 py-1.5 text-xs font-semibold rounded-lg transition flex items-center gap-1.5 ${
                          isActive
                            ? 'bg-emerald-600 text-white shadow-sm'
                            : 'bg-slate-100 hover:bg-slate-200 text-slate-700'
                        }`}
                      >
                        <span>Trang {idx + 1}</span>
                        {p.mau && (
                          <span className={`text-[10px] px-1 py-0.2 rounded font-normal ${
                            isActive ? 'bg-emerald-700 text-emerald-100' : 'bg-slate-200 text-slate-600'
                          }`}>
                            {p.mau}
                          </span>
                        )}
                      </button>
                    );
                  })}
                </div>
              </div>
            )}

            {/* Sơ đồ thửa đất đã tách (Diagram) */}
            {diagramUrl && (
              <div className="bg-slate-50 rounded-xl p-3 border border-slate-200 space-y-2">
                <div className="flex items-center justify-between text-xs font-bold text-slate-700">
                  <span className="flex items-center gap-1.5">
                    <MapPin size={14} className="text-emerald-600" /> Sơ đồ thửa đất đã tách
                  </span>
                  <a
                    href={diagramUrl}
                    target="_blank"
                    rel="noreferrer"
                    className="text-emerald-600 hover:underline flex items-center gap-1 text-[11px]"
                  >
                    Xem ảnh gốc <ExternalLink size={11} />
                  </a>
                </div>
                <div className="bg-white rounded-lg p-1 border border-slate-200 flex items-center justify-center h-40 overflow-hidden">
                  <img
                    src={diagramUrl}
                    alt="Sơ đồ thửa đất"
                    className="max-h-full max-w-full object-contain"
                  />
                </div>
              </div>
            )}

            {/* Thư viện Crop Gallery (Trước VietOCR) */}
            {allCrops.length > 0 && (
              <div className="border border-slate-200 rounded-xl p-3 bg-slate-50/70 space-y-2.5">
                <div className="flex items-center justify-between">
                  <button
                    onClick={() => setShowCropGallery(!showCropGallery)}
                    className="flex items-center gap-1.5 text-xs font-bold text-slate-800 hover:text-emerald-700"
                  >
                    <Scissors size={14} className="text-indigo-600" />
                    <span>Ảnh Crops Trước VietOCR</span>
                    <span className="bg-indigo-100 text-indigo-700 text-[10px] px-2 py-0.5 rounded-full font-bold">
                      {allCrops.length}
                    </span>
                    {showCropGallery ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                  </button>
                  {showCropGallery && (
                    <label className="text-[11px] text-slate-600 flex items-center gap-1 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={cropDiffOnly}
                        onChange={(e) => setCropDiffOnly(e.target.checked)}
                        className="rounded text-emerald-600"
                      />
                      <span>Chỉ khác biệt</span>
                    </label>
                  )}
                </div>

                {showCropGallery && (
                  <div className="grid grid-cols-2 gap-2 max-h-[360px] overflow-y-auto pr-1">
                    {filteredCrops.map((c, i) => (
                      <div key={i} className="bg-white p-2 rounded-lg border border-slate-200 text-[11px] space-y-1 shadow-2xs">
                        {c.url && (
                          <div className="bg-slate-100 rounded flex items-center justify-center h-12 overflow-hidden border border-slate-200">
                            <img src={c.url} alt={`crop-${i}`} className="max-h-full max-w-full object-contain" />
                          </div>
                        )}
                        <div className="space-y-0.5">
                          <p className="text-slate-500 font-medium">Paddle: <span className="text-slate-800">{c.paddle_text || '-'}</span></p>
                          <p className="text-slate-500 font-medium">VietOCR: <span className="text-indigo-700 font-bold">{c.viet_text || '-'}</span></p>
                          <p className="text-emerald-700 font-bold">Final: {c.final_text || '-'}</p>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>

          {/* ── CỘT PHẢI: TOÀN BỘ FORM DỮ LIỆU CẤU TRÚC ── */}
          <div className="lg:col-span-7 bg-white rounded-2xl border border-slate-200 shadow-sm p-6 space-y-6">
            
            {/* Header thông tin hồ sơ */}
            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 pb-4">
              <div>
                <div className="flex items-center gap-2">
                  <h3 className="text-lg font-bold text-slate-900">
                    {result.file_name || result.document_id || 'Giấy Chứng Nhận'}
                  </h3>
                  <span className="bg-emerald-100 text-emerald-800 text-xs px-2.5 py-0.5 rounded-full font-bold">
                    {result.mau || result.template || 'Mẫu Chuẩn'}
                  </span>
                </div>
                <p className="text-xs text-slate-500 mt-0.5">
                  Thời gian xử lý: <b>{result.tong_thoi_gian_sec || result.processing_time_ms ? `${result.tong_thoi_gian_sec || (result.processing_time_ms! / 1000).toFixed(1)}s` : '10.5s'}</b> | 
                  Tổng số trang: <b>{pages.length || 1}</b>
                </p>
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={handleExportJSON}
                  className="px-3 py-1.5 bg-slate-100 hover:bg-slate-200 text-slate-700 text-xs font-medium rounded-xl transition flex items-center gap-1.5"
                >
                  <Code size={13} /> JSON
                </button>
                <button
                  onClick={handleExportExcel}
                  disabled={exportingExcel}
                  className="px-3.5 py-1.5 bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-semibold rounded-xl transition flex items-center gap-1.5 shadow-sm"
                >
                  {exportingExcel ? <Loader2 size={13} className="animate-spin" /> : <FileSpreadsheet size={13} />}
                  <span>Xuất Excel (129 Cột)</span>
                </button>
              </div>
            </div>

            {/* Nhóm: Định danh & Mã sổ */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 bg-slate-50 p-4 rounded-xl border border-slate-100">
              <div>
                <label className="block text-xs font-semibold text-slate-600 mb-1">Mã số phát hành (Serial)</label>
                <input
                  type="text"
                  readOnly
                  value={result.so_phat_hanh || ''}
                  className="w-full text-sm font-bold bg-white border border-slate-200 rounded-lg px-3 py-1.5 text-emerald-800"
                />
              </div>
              <div>
                <label className="block text-xs font-semibold text-slate-600 mb-1">Số vào sổ cấp GCN</label>
                <input
                  type="text"
                  readOnly
                  value={result.so_vao_so || ''}
                  className="w-full text-sm font-bold bg-white border border-slate-200 rounded-lg px-3 py-1.5 text-slate-800"
                />
              </div>
              <div>
                <label className="block text-xs font-semibold text-slate-600 mb-1">Mã vạch (Barcode)</label>
                <input
                  type="text"
                  readOnly
                  value={result.ma_vach || ''}
                  className="w-full text-sm font-mono bg-white border border-slate-200 rounded-lg px-3 py-1.5 text-slate-800"
                />
              </div>
              <div>
                <label className="block text-xs font-semibold text-slate-600 mb-1">Loại cấp / Đợt cấp</label>
                <input
                  type="text"
                  readOnly
                  value={[result.loai_cap, result.dot_cap_gcn].filter(Boolean).join(' - ') || '-'}
                  className="w-full text-sm bg-white border border-slate-200 rounded-lg px-3 py-1.5 text-slate-800"
                />
              </div>
            </div>

            {/* I. Người sử dụng đất / Chủ sở hữu */}
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <h4 className="text-xs font-bold uppercase tracking-wider text-slate-600 flex items-center gap-1.5">
                  <UserCheck size={15} className="text-emerald-600" /> I. Người Sử Dụng Đất / Chủ Sở Hữu
                </h4>
                <div className="flex items-center gap-2">
                  <span className="text-xs font-semibold bg-slate-100 text-slate-700 px-2.5 py-0.5 rounded-lg border border-slate-200">
                    {nguoi.loai_chu || 'Cá nhân'}
                  </span>
                  <span className="text-xs font-semibold bg-emerald-50 text-emerald-700 px-2.5 py-0.5 rounded-lg border border-emerald-200">
                    {result.dong_su_dung || 'Không đồng sở hữu'}
                  </span>
                </div>
              </div>

              {/* Chủ 1 */}
              <div className="bg-slate-50/90 rounded-xl p-3.5 border border-slate-200 space-y-2">
                <div className="text-xs font-bold text-blue-700 flex items-center gap-1">
                  <span>Chủ 1 (Chồng / Đại diện chính)</span>
                </div>
                <div className="grid grid-cols-1 md:grid-cols-12 gap-2.5">
                  <div className="md:col-span-6">
                    <label className="block text-[11px] text-slate-500 mb-0.5">Họ và tên Chủ 1</label>
                    <input
                      type="text"
                      readOnly
                      value={nguoi.ho_ten_chu_1 || nguoi.ten || '-'}
                      className="w-full text-sm font-bold bg-white border border-slate-200 rounded-lg px-3 py-1.5 text-slate-900"
                    />
                  </div>
                  <div className="md:col-span-3">
                    <label className="block text-[11px] text-slate-500 mb-0.5">CMND / CCCD</label>
                    <input
                      type="text"
                      readOnly
                      value={nguoi.cmnd_chu_1 || nguoi.cmnd || '-'}
                      className="w-full text-sm font-mono bg-white border border-slate-200 rounded-lg px-3 py-1.5 text-slate-800"
                    />
                  </div>
                  <div className="md:col-span-3">
                    <label className="block text-[11px] text-slate-500 mb-0.5">Năm sinh</label>
                    <input
                      type="text"
                      readOnly
                      value={nguoi.ngay_sinh_chu_1 || nguoi.ngay_sinh || '-'}
                      className="w-full text-sm bg-white border border-slate-200 rounded-lg px-3 py-1.5 text-slate-800"
                    />
                  </div>
                </div>
              </div>

              {/* Chủ 2 */}
              <div className="bg-rose-50/40 rounded-xl p-3.5 border border-rose-200/60 space-y-2">
                <div className="text-xs font-bold text-rose-700 flex items-center gap-1">
                  <span>Chủ 2 (Vợ / Người đồng sở hữu)</span>
                </div>
                <div className="grid grid-cols-1 md:grid-cols-12 gap-2.5">
                  <div className="md:col-span-6">
                    <label className="block text-[11px] text-slate-500 mb-0.5">Họ và tên Chủ 2</label>
                    <input
                      type="text"
                      readOnly
                      value={nguoi.ho_ten_chu_2 || '-'}
                      className="w-full text-sm font-bold bg-white border border-slate-200 rounded-lg px-3 py-1.5 text-slate-900"
                    />
                  </div>
                  <div className="md:col-span-3">
                    <label className="block text-[11px] text-slate-500 mb-0.5">CMND / CCCD</label>
                    <input
                      type="text"
                      readOnly
                      value={nguoi.cmnd_chu_2 || '-'}
                      className="w-full text-sm font-mono bg-white border border-slate-200 rounded-lg px-3 py-1.5 text-slate-800"
                    />
                  </div>
                  <div className="md:col-span-3">
                    <label className="block text-[11px] text-slate-500 mb-0.5">Năm sinh</label>
                    <input
                      type="text"
                      readOnly
                      value={nguoi.ngay_sinh_chu_2 || '-'}
                      className="w-full text-sm bg-white border border-slate-200 rounded-lg px-3 py-1.5 text-slate-800"
                    />
                  </div>
                </div>
              </div>

              {/* Chủ gốc bìa & Địa chỉ thường trú */}
              <div className="grid grid-cols-1 md:grid-cols-12 gap-3">
                <div className="md:col-span-5">
                  <label className="block text-xs text-slate-600 mb-1 font-medium">Chủ sở hữu ban đầu (trên trang bìa)</label>
                  <input
                    type="text"
                    readOnly
                    value={nguoi.ho_ten_goc || '-'}
                    className="w-full text-sm bg-white border border-slate-200 rounded-lg px-3 py-1.5 text-slate-800"
                  />
                </div>
                <div className="md:col-span-7">
                  <label className="block text-xs text-slate-600 mb-1 font-medium">Địa chỉ thường trú</label>
                  <input
                    type="text"
                    readOnly
                    value={nguoi.dia_chi_thuong_tru || '-'}
                    className="w-full text-sm bg-white border border-slate-200 rounded-lg px-3 py-1.5 text-slate-800"
                  />
                </div>
              </div>
            </div>

            {/* II. Thông tin Thửa đất */}
            <div className="space-y-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                  <h4 className="text-xs font-bold uppercase tracking-wider text-slate-700 flex items-center gap-1.5">
                    <MapPin size={15} className="text-emerald-600" /> II. Thông Tin Thửa Đất
                  </h4>
                  {danhSachThua.length > 1 ? (
                    <span className="bg-emerald-100 text-emerald-800 text-[11px] px-2.5 py-0.5 rounded-full font-bold flex items-center gap-1 border border-emerald-200">
                      <Layers size={12} /> Sổ {danhSachThua.length} thửa đất
                    </span>
                  ) : (
                    <span className="bg-slate-100 text-slate-700 text-[11px] px-2 py-0.5 rounded-full font-medium">
                      1 Thửa đất
                    </span>
                  )}
                  {thua.dien_tich_cap && (
                    <span className="bg-blue-50 text-blue-700 text-[11px] px-2.5 py-0.5 rounded-full font-bold border border-blue-200">
                      Tổng DT: {thua.dien_tich_cap} m²
                    </span>
                  )}
                </div>

                <div className="flex items-center gap-1 bg-slate-100 p-0.5 rounded-lg border border-slate-200 text-xs">
                  <button
                    type="button"
                    onClick={() => setParcelViewMode('table')}
                    className={`px-2.5 py-1 rounded-md font-medium transition flex items-center gap-1.5 ${
                      parcelViewMode === 'table'
                        ? 'bg-white text-emerald-700 font-bold shadow-xs'
                        : 'text-slate-600 hover:text-slate-900'
                    }`}
                  >
                    <TableIcon size={13} />
                    <span>Bảng chi tiết (Ảnh 2)</span>
                  </button>
                  <button
                    type="button"
                    onClick={() => setParcelViewMode('cards')}
                    className={`px-2.5 py-1 rounded-md font-medium transition flex items-center gap-1.5 ${
                      parcelViewMode === 'cards'
                        ? 'bg-white text-emerald-700 font-bold shadow-xs'
                        : 'text-slate-600 hover:text-slate-900'
                    }`}
                  >
                    <LayoutGrid size={13} />
                    <span>Dạng ô nhập</span>
                  </button>
                </div>
              </div>

              {/* View 1: BẢNG CHI TIẾT TỪNG THỬA ĐẤT (CHUẨN ẢNH 2) */}
              {parcelViewMode === 'table' && danhSachThua.length > 0 && (
                <div className="space-y-3">
                  <div className="overflow-x-auto border border-slate-300 rounded-xl shadow-xs bg-white">
                    <table className="w-full text-xs text-left border-collapse">
                      <thead>
                        <tr className="bg-slate-100 text-slate-800 text-center font-bold">
                          <th rowSpan={2} className="border border-slate-300 px-2 py-2 w-10 text-slate-600">STT</th>
                          <th rowSpan={2} className="border border-slate-300 px-3 py-2 w-20">Tờ bản đồ</th>
                          <th rowSpan={2} className="border border-slate-300 px-3 py-2 w-24">Thửa đất số</th>
                          <th rowSpan={2} className="border border-slate-300 px-3 py-2 min-w-[180px]">Địa chỉ thửa đất</th>
                          <th colSpan={2} className="border border-slate-300 px-3 py-1.5 text-center bg-slate-100/95 font-bold">
                            Diện tích (m²)
                          </th>
                          <th rowSpan={2} className="border border-slate-300 px-3 py-2 min-w-[160px]">Mục đích sử dụng</th>
                          <th rowSpan={2} className="border border-slate-300 px-3 py-2 w-28">Thời hạn sử dụng</th>
                          <th rowSpan={2} className="border border-slate-300 px-3 py-2 min-w-[220px]">Nguồn gốc sử dụng</th>
                        </tr>
                        <tr className="bg-slate-50 text-slate-700 text-center font-semibold text-[11px]">
                          <th className="border border-slate-300 px-2 py-1 w-20">riêng</th>
                          <th className="border border-slate-300 px-2 py-1 w-20">chung</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-200">
                        {danhSachThua.map((item, idx) => (
                          <tr key={idx} className="hover:bg-emerald-50/40 transition">
                            <td className="border border-slate-300 px-2 py-2 text-center text-slate-500 font-medium">
                              {item.stt}
                            </td>
                            <td className="border border-slate-300 px-3 py-2 text-center font-bold text-slate-900">
                              {item.to_ban_do}
                            </td>
                            <td className="border border-slate-300 px-3 py-2 text-center font-extrabold text-emerald-800">
                              <span className="bg-emerald-50 border border-emerald-200 text-emerald-800 px-2 py-0.5 rounded font-mono text-xs shadow-2xs">
                                {item.so_thua}
                              </span>
                            </td>
                            <td className="border border-slate-300 px-3 py-2 text-slate-800 font-medium">
                              {item.dia_chi}
                            </td>
                            <td className="border border-slate-300 px-2 py-2 text-right font-bold text-slate-900 pr-3">
                              {item.dien_tich_rieng !== '-' && !isNaN(Number(item.dien_tich_rieng))
                                ? `${item.dien_tich_rieng}`
                                : (item.dien_tich_rieng || '-')}
                            </td>
                            <td className="border border-slate-300 px-2 py-2 text-center text-slate-500 italic">
                              {item.dien_tich_chung || 'không'}
                            </td>
                            <td className="border border-slate-300 px-3 py-2 text-slate-800">
                              <div className="flex items-center gap-1.5 flex-wrap">
                                <span>{item.muc_dich_su_dung}</span>
                                {item.ma_muc_dich && (
                                  <span className="bg-blue-50 text-blue-700 border border-blue-200 text-[10px] px-1.5 py-0.5 rounded font-bold uppercase">
                                    {item.ma_muc_dich}
                                  </span>
                                )}
                              </div>
                            </td>
                            <td className="border border-slate-300 px-3 py-2 text-center text-slate-700 whitespace-nowrap">
                              {item.thoi_han}
                            </td>
                            <td className="border border-slate-300 px-3 py-2 text-slate-800 text-[11px] leading-snug">
                              <span>{item.nguon_goc}</span>
                              {item.nguon_goc_ky_hieu && (
                                <span className="ml-1.5 bg-emerald-50 text-emerald-700 border border-emerald-200 text-[10px] px-1.5 py-0.5 rounded font-semibold inline-block">
                                  {item.nguon_goc_ky_hieu}
                                </span>
                              )}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                      {/* Footer tổng hợp */}
                      <tfoot>
                        <tr className="bg-slate-100/90 font-bold text-slate-800 border-t border-slate-300">
                          <td colSpan={4} className="border border-slate-300 px-3 py-2 text-right">
                            Tổng cộng ({danhSachThua.length} thửa):
                          </td>
                          <td className="border border-slate-300 px-2 py-2 text-right text-emerald-800 pr-3">
                            {totalRowArea !== null
                              ? `${totalRowArea} m²`
                              : (thua.dien_tich_cap ? `${thua.dien_tich_cap} m²` : '-')}
                          </td>
                          <td className="border border-slate-300 px-2 py-2 text-center text-slate-500 italic">
                            {thua.dien_tich_chung || 'không'}
                          </td>
                          <td colSpan={3} className="border border-slate-300 px-3 py-2 text-slate-500 text-xs">
                            {thua.dien_tich_chu ? `Bằng chữ: ${thua.dien_tich_chu}` : ''}
                          </td>
                        </tr>
                      </tfoot>
                    </table>
                  </div>

                  {/* Thông tin phụ trợ đi kèm thửa đất */}
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-3 bg-slate-50/70 p-3 rounded-xl border border-slate-200">
                    <div>
                      <label className="block text-[11px] text-slate-500 mb-0.5 font-medium">Tỷ lệ bản đồ</label>
                      <input
                        type="text"
                        readOnly
                        value={thua.ty_le || '-'}
                        className="w-full text-xs font-bold bg-white border border-slate-200 rounded-lg px-2.5 py-1.5 text-slate-800"
                      />
                    </div>
                    <div>
                      <label className="block text-[11px] text-slate-500 mb-0.5 font-medium">Hình thức sử dụng</label>
                      <input
                        type="text"
                        readOnly
                        value={thua.hinh_thuc_su_dung || (danhSachThua.length > 1 ? 'Sử dụng riêng từng thửa' : 'Sử dụng riêng')}
                        className="w-full text-xs bg-white border border-slate-200 rounded-lg px-2.5 py-1.5 text-slate-800"
                      />
                    </div>
                    <div className="col-span-2">
                      <div className="flex items-center justify-between mb-0.5">
                        <label className="block text-[11px] text-slate-500 font-medium">Diện tích bằng chữ (GCN)</label>
                        {thua.dien_tich_validated ? (
                          <span className="text-[10px] px-2 py-0.2 rounded font-bold bg-emerald-100 text-emerald-800 flex items-center gap-0.5">
                            <Check size={10} /> Khớp 100% Số & Chữ
                          </span>
                        ) : (
                          <span className="text-[10px] px-2 py-0.2 rounded font-bold bg-amber-100 text-amber-800 flex items-center gap-0.5">
                            <AlertTriangle size={10} /> Cần đối soát
                          </span>
                        )}
                      </div>
                      <input
                        type="text"
                        readOnly
                        value={thua.dien_tich_chu || '-'}
                        className="w-full text-xs bg-white border border-slate-200 rounded-lg px-2.5 py-1.5 text-slate-800"
                      />
                    </div>
                  </div>
                </div>
              )}

              {/* View 2: DẠNG FORM Ô NHẬP TỔNG HỢP (KHI NGƯỜI DÙNG CHỌN XEM DẠNG FORM HOẶC KHÔNG CÓ BẢNG) */}
              {(parcelViewMode === 'cards' || danhSachThua.length === 0) && (
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                  <div>
                    <label className="block text-xs text-slate-600 mb-1 font-medium">Thửa đất số</label>
                    <input
                      type="text"
                      readOnly
                      value={thua.so_thua || '-'}
                      className="w-full text-sm font-bold bg-white border border-slate-200 rounded-lg px-3 py-1.5 text-slate-900"
                    />
                  </div>
                  <div>
                    <label className="block text-xs text-slate-600 mb-1 font-medium">Tờ bản đồ số</label>
                    <input
                      type="text"
                      readOnly
                      value={thua.to_ban_do || '-'}
                      className="w-full text-sm font-bold bg-white border border-slate-200 rounded-lg px-3 py-1.5 text-slate-900"
                    />
                  </div>
                  <div>
                    <label className="block text-xs text-slate-600 mb-1 font-medium">Tỷ lệ bản đồ</label>
                    <input
                      type="text"
                      readOnly
                      value={thua.ty_le || '-'}
                      className="w-full text-sm bg-white border border-slate-200 rounded-lg px-3 py-1.5 text-slate-800"
                    />
                  </div>
                  <div>
                    <label className="block text-xs text-slate-600 mb-1 font-medium">Diện tích cấp (m²)</label>
                    <input
                      type="text"
                      readOnly
                      value={thua.dien_tich_cap ? `${thua.dien_tich_cap} m²` : '-'}
                      className="w-full text-sm font-bold bg-white border border-slate-200 rounded-lg px-3 py-1.5 text-emerald-700"
                    />
                  </div>
                  <div className="col-span-2">
                    <label className="block text-xs text-slate-600 mb-1 font-medium">Diện tích Riêng / Chung (m²)</label>
                    <div className="flex gap-2">
                      <input
                        type="text"
                        readOnly
                        value={thua.dien_tich_rieng ? `Riêng: ${thua.dien_tich_rieng} m²` : 'Riêng: -'}
                        className="w-1/2 text-xs bg-white border border-slate-200 rounded-lg px-3 py-1.5 text-slate-800"
                      />
                      <input
                        type="text"
                        readOnly
                        value={thua.dien_tich_chung ? `Chung: ${thua.dien_tich_chung} m²` : 'Chung: 0 m²'}
                        className="w-1/2 text-xs bg-white border border-slate-200 rounded-lg px-3 py-1.5 text-slate-800"
                      />
                    </div>
                  </div>
                  <div className="col-span-2">
                    <div className="flex items-center justify-between mb-1">
                      <label className="block text-xs text-slate-600 font-medium">Diện tích bằng chữ</label>
                      {thua.dien_tich_validated ? (
                        <span className="text-[11px] px-2 py-0.5 rounded font-bold bg-emerald-100 text-emerald-800 flex items-center gap-1">
                          <Check size={11} /> Khớp 100% Số & Chữ
                        </span>
                      ) : (
                        <span className="text-[11px] px-2 py-0.5 rounded font-bold bg-amber-100 text-amber-800 flex items-center gap-1">
                          <AlertTriangle size={11} /> Cần đối soát
                        </span>
                      )}
                    </div>
                    <input
                      type="text"
                      readOnly
                      value={thua.dien_tich_chu || '-'}
                      className="w-full text-sm bg-white border border-slate-200 rounded-lg px-3 py-1.5 text-slate-800"
                    />
                  </div>
                  <div className="col-span-2 md:col-span-4">
                    <label className="block text-xs text-slate-600 mb-1 font-medium">Địa chỉ thửa đất</label>
                    <input
                      type="text"
                      readOnly
                      value={thua.dia_chi || '-'}
                      className="w-full text-sm bg-white border border-slate-200 rounded-lg px-3 py-1.5 text-slate-800"
                    />
                  </div>
                  <div className="col-span-2 md:col-span-2">
                    <label className="block text-xs text-slate-600 mb-1 font-medium">Mục đích sử dụng</label>
                    <input
                      type="text"
                      readOnly
                      value={thua.muc_dich_su_dung || '-'}
                      className="w-full text-sm bg-white border border-slate-200 rounded-lg px-3 py-1.5 text-slate-800"
                    />
                  </div>
                  <div>
                    <label className="block text-xs text-slate-600 mb-1 font-medium">Mã mục đích</label>
                    <input
                      type="text"
                      readOnly
                      value={thua.ma_muc_dich || '-'}
                      className="w-full text-sm font-bold bg-white border border-slate-200 rounded-lg px-3 py-1.5 text-emerald-700"
                    />
                  </div>
                  <div>
                    <label className="block text-xs text-slate-600 mb-1 font-medium">Thời hạn sử dụng</label>
                    <input
                      type="text"
                      readOnly
                      value={thua.thoi_han_su_dung || thua.thoi_han || '-'}
                      className="w-full text-sm bg-white border border-slate-200 rounded-lg px-3 py-1.5 text-slate-800"
                    />
                  </div>
                  <div className="col-span-2 md:col-span-3">
                    <label className="block text-xs text-slate-600 mb-1 font-medium">Nguồn gốc sử dụng</label>
                    <input
                      type="text"
                      readOnly
                      value={thua.nguon_goc_su_dung || thua.nguon_goc || '-'}
                      className="w-full text-sm bg-white border border-slate-200 rounded-lg px-3 py-1.5 text-slate-800"
                    />
                  </div>
                  <div>
                    <label className="block text-xs text-slate-600 mb-1 font-medium">Mã nguồn gốc</label>
                    <input
                      type="text"
                      readOnly
                      value={thua.nguon_goc_ky_hieu || '-'}
                      className="w-full text-sm font-bold bg-white border border-slate-200 rounded-lg px-3 py-1.5 text-emerald-700"
                    />
                  </div>
                </div>
              )}
            </div>

            {/* III. Tài sản gắn liền với đất & Ghi chú */}
            <div className="space-y-3">
              <h4 className="text-xs font-bold uppercase tracking-wider text-slate-600 flex items-center gap-1.5">
                <Building size={15} className="text-emerald-600" /> III. Tài Sản Gắn Liền Với Đất & Ghi Chú
              </h4>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                <div>
                  <label className="block text-xs text-slate-600 mb-1 font-medium">Nhà ở (loại nhà, diện tích)</label>
                  <input
                    type="text"
                    readOnly
                    value={taisan.nha_o || '-'}
                    className="w-full text-sm bg-white border border-slate-200 rounded-lg px-3 py-1.5 text-slate-800"
                  />
                </div>
                <div>
                  <label className="block text-xs text-slate-600 mb-1 font-medium">Công trình xây dựng khác</label>
                  <input
                    type="text"
                    readOnly
                    value={taisan.cong_trinh_khac || '-'}
                    className="w-full text-sm bg-white border border-slate-200 rounded-lg px-3 py-1.5 text-slate-800"
                  />
                </div>
                <div>
                  <label className="block text-xs text-slate-600 mb-1 font-medium">Rừng SX / Cây lâu năm</label>
                  <input
                    type="text"
                    readOnly
                    value={taisan.rung_cay || '-'}
                    className="w-full text-sm bg-white border border-slate-200 rounded-lg px-3 py-1.5 text-slate-800"
                  />
                </div>
                <div className="col-span-1 md:col-span-3">
                  <label className="block text-xs text-slate-600 mb-1 font-medium">Ghi chú / Hạn chế quyền sử dụng đất</label>
                  <input
                    type="text"
                    readOnly
                    value={taisan.ghi_chu || '-'}
                    className="w-full text-sm bg-white border border-slate-200 rounded-lg px-3 py-1.5 text-slate-800"
                  />
                </div>
              </div>
            </div>

            {/* IV. Thông tin Cấp GCN */}
            <div className="space-y-3">
              <h4 className="text-xs font-bold uppercase tracking-wider text-slate-600 flex items-center gap-1.5">
                <Stamp size={15} className="text-emerald-600" /> IV. Thông Tin Cấp Giấy Chứng Nhận
              </h4>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                <div>
                  <label className="block text-xs text-slate-600 mb-1 font-medium">Nơi cấp (Cơ quan ban đầu)</label>
                  <input
                    type="text"
                    readOnly
                    value={cap.noi_cap || '-'}
                    className="w-full text-sm bg-white border border-slate-200 rounded-lg px-3 py-1.5 text-slate-800"
                  />
                </div>
                <div>
                  <label className="block text-xs text-slate-600 mb-1 font-medium">Ngày cấp GCN</label>
                  <input
                    type="text"
                    readOnly
                    value={cap.ngay_cap || '-'}
                    className="w-full text-sm bg-white border border-slate-200 rounded-lg px-3 py-1.5 text-slate-800"
                  />
                </div>
                <div>
                  <label className="block text-xs text-slate-600 mb-1 font-medium">Người ký / Chức vụ</label>
                  <input
                    type="text"
                    readOnly
                    value={[cap.chuc_vu_nguoi_ky, cap.nguoi_ky_qd].filter(Boolean).join(' - ') || cap.nguoi_ky_qd || '-'}
                    className="w-full text-sm bg-white border border-slate-200 rounded-lg px-3 py-1.5 text-slate-800"
                  />
                </div>
                <div>
                  <label className="block text-xs text-slate-600 mb-1 font-medium">Số quyết định cấp</label>
                  <input
                    type="text"
                    readOnly
                    value={cap.so_quyet_dinh || '-'}
                    className="w-full text-sm bg-white border border-slate-200 rounded-lg px-3 py-1.5 text-slate-800"
                  />
                </div>
                <div>
                  <label className="block text-xs text-slate-600 mb-1 font-medium">Ngày vào sổ</label>
                  <input
                    type="text"
                    readOnly
                    value={cap.ngay_vao_so || '-'}
                    className="w-full text-sm bg-white border border-slate-200 rounded-lg px-3 py-1.5 text-slate-800"
                  />
                </div>
                <div>
                  <label className="block text-xs text-slate-600 mb-1 font-medium">Số hồ sơ gốc</label>
                  <input
                    type="text"
                    readOnly
                    value={cap.so_ho_so_goc || '-'}
                    className="w-full text-sm bg-white border border-slate-200 rounded-lg px-3 py-1.5 text-slate-800"
                  />
                </div>
              </div>
            </div>

            {/* V. Những thay đổi sau khi cấp GCN (Biến động / Chuyển nhượng) */}
            <div className="space-y-3 bg-amber-50/40 p-4 rounded-xl border border-amber-200/60">
              <h4 className="text-xs font-bold uppercase tracking-wider text-amber-900 flex items-center gap-1.5">
                <RefreshCw size={15} className="text-amber-700" /> V. Những Thay Đổi Sau Khi Cấp GCN (Biến Động / Chuyển Nhượng)
              </h4>
              <div className="space-y-3">
                <div>
                  <label className="block text-xs text-slate-600 mb-1 font-medium">Nội dung thay đổi & Cơ sở pháp lý</label>
                  <textarea
                    rows={2}
                    readOnly
                    value={bd.thong_tin_bien_dong || bd.bien_dong || '-'}
                    className="w-full text-sm bg-white border border-slate-200 rounded-lg px-3 py-1.5 text-slate-800 resize-none"
                  />
                </div>

                {/* Người nhận 1 & 2 */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  <div className="bg-white p-3 rounded-lg border border-amber-200/80 space-y-1.5">
                    <p className="text-xs font-bold text-blue-700">Người nhận chuyển nhượng 1</p>
                    <p className="text-xs text-slate-700 font-medium">Họ tên: <span className="font-bold">{bd.ten_chuyen_nhuong_1 || bd.ten_chuyen_nhuong_moi || '-'}</span></p>
                    <p className="text-xs text-slate-700 font-mono">CCCD: {bd.cmnd_chuyen_nhuong_1 || bd.cmnd_chuyen_nhuong || '-'}</p>
                  </div>
                  <div className="bg-white p-3 rounded-lg border border-amber-200/80 space-y-1.5">
                    <p className="text-xs font-bold text-rose-700">Người nhận chuyển nhượng 2</p>
                    <p className="text-xs text-slate-700 font-medium">Họ tên: <span className="font-bold">{bd.ten_chuyen_nhuong_2 || '-'}</span></p>
                    <p className="text-xs text-slate-700 font-mono">CCCD: {bd.cmnd_chuyen_nhuong_2 || '-'}</p>
                  </div>
                </div>

                {/* Chi tiết xác nhận */}
                <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                  <div>
                    <label className="block text-xs text-slate-600 mb-1 font-medium">Ngày xác nhận</label>
                    <input
                      type="text"
                      readOnly
                      value={bd.ngay_chuyen_nhuong || '-'}
                      className="w-full text-sm bg-white border border-slate-200 rounded-lg px-3 py-1.5 text-slate-800"
                    />
                  </div>
                  <div>
                    <label className="block text-xs text-slate-600 mb-1 font-medium">Người ký / Cơ quan</label>
                    <input
                      type="text"
                      readOnly
                      value={bd.nguoi_ky_xac_nhan || '-'}
                      className="w-full text-sm bg-white border border-slate-200 rounded-lg px-3 py-1.5 text-slate-800"
                    />
                  </div>
                  <div>
                    <label className="block text-xs text-slate-600 mb-1 font-medium">Số hồ sơ biến động</label>
                    <input
                      type="text"
                      readOnly
                      value={bd.so_ho_so_bien_dong || '-'}
                      className="w-full text-sm font-mono bg-white border border-slate-200 rounded-lg px-3 py-1.5 text-slate-800"
                    />
                  </div>
                </div>
              </div>
            </div>

            {/* VI. Bảng Kiểm Tra & Đối Soát Độ Tin Cậy (Audit Check) */}
            <div className="space-y-3">
              <h4 className="text-xs font-bold uppercase tracking-wider text-slate-600 flex items-center gap-1.5">
                <ShieldCheck size={15} className="text-emerald-600" /> VI. Bảng Kiểm Tra Độ Tin Cậy Bóc Tách
              </h4>
              <div className="border border-slate-200 rounded-xl overflow-hidden shadow-2xs">
                <table className="w-full text-left text-xs border-collapse">
                  <thead className="bg-slate-50 border-b border-slate-200 text-slate-600">
                    <tr>
                      <th className="py-2.5 px-3 font-semibold">Trường dữ liệu</th>
                      <th className="py-2.5 px-3 font-semibold">Giá trị nhận dạng</th>
                      <th className="py-2.5 px-3 font-semibold text-center w-24">Độ tin cậy</th>
                      <th className="py-2.5 px-3 font-semibold text-center w-28">Trạng thái</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100 text-slate-800">
                    {[
                      { label: 'Số phát hành', val: result.so_phat_hanh, conf: result.confidence?.so_phat_hanh || 0.95 },
                      { label: 'Số vào sổ', val: result.so_vao_so, conf: result.confidence?.so_vao_so || 0.92 },
                      { label: 'Mã vạch', val: result.ma_vach, conf: result.confidence?.ma_vach || 0.96 },
                      { label: 'Chủ 1 - Họ tên', val: nguoi.ho_ten_chu_1, conf: result.confidence?.ho_ten || 0.90 },
                      { label: 'Chủ 1 - CCCD', val: nguoi.cmnd_chu_1, conf: result.confidence?.cmnd || 0.94 },
                      { label: 'Thửa đất số', val: thua.so_thua, conf: result.confidence?.so_thua || 0.93 },
                      { label: 'Tờ bản đồ số', val: thua.to_ban_do, conf: result.confidence?.to_ban_do || 0.91 },
                      { label: 'Diện tích cấp', val: thua.dien_tich_cap, conf: result.confidence?.dien_tich || 0.95 },
                      { label: 'Địa chỉ thửa đất', val: thua.dia_chi, conf: result.confidence?.dia_chi_thua || 0.88 },
                    ].map((row, idx) => {
                      const score = Math.round(row.conf * 100);
                      const isHigh = score >= 85;
                      const hasVal = Boolean(row.val && row.val !== '-');
                      return (
                        <tr key={idx} className="hover:bg-slate-50/70">
                          <td className="py-2 px-3 font-medium text-slate-600">{row.label}</td>
                          <td className="py-2 px-3 font-semibold text-slate-900">{row.val || '-'}</td>
                          <td className="py-2 px-3 text-center">
                            <span className={`px-2 py-0.5 rounded-md font-mono text-[11px] font-bold ${
                              isHigh ? 'bg-emerald-50 text-emerald-700' : 'bg-amber-50 text-amber-700'
                            }`}>
                              {score}%
                            </span>
                          </td>
                          <td className="py-2 px-3 text-center">
                            {hasVal ? (
                              <span className="text-[11px] px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-800 font-bold">
                                Hợp lệ
                              </span>
                            ) : (
                              <span className="text-[11px] px-2 py-0.5 rounded-full bg-slate-100 text-slate-500 font-normal">
                                Trống
                              </span>
                            )}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>

          </div>

        </div>
      )}
    </div>
  );
};
