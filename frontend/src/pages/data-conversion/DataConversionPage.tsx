import React, { useState, useEffect, useMemo } from 'react';
import axios from 'axios';
import { Download, Search, Maximize2, Minimize2, Database, FileSpreadsheet } from 'lucide-react';
import { ChuyenDoiColumn } from '../../shared/types';

interface DataConversionPageProps {
  initialRows?: Record<string, any>[];
}

export const DataConversionPage: React.FC<DataConversionPageProps> = ({ initialRows }) => {
  const [columns, setColumns] = useState<ChuyenDoiColumn[]>([]);
  const [rows, setRows] = useState<Record<string, any>[]>(initialRows || []);
  const [loading, setLoading] = useState<boolean>(false);
  const [search, setSearch] = useState<string>('');
  const [fullscreen, setFullscreen] = useState<boolean>(false);
  const [activeSection, setActiveSection] = useState<string>('all');

  // Nạp danh sách 129 cột
  useEffect(() => {
    axios.get('/chuyen-doi/columns')
      .then(res => setColumns(res.data.columns || []))
      .catch(err => console.error('Lỗi nạp cột:', err));
  }, []);

  useEffect(() => {
    if (initialRows && initialRows.length > 0) {
      setRows(initialRows);
    }
  }, [initialRows]);

  // Nạp dữ liệu từ Markdown lưu trong SQLite DB vào bảng 129 trường
  const loadFromMarkdownDb = async () => {
    setLoading(true);
    try {
      const res = await axios.get('/chuyen-doi/load-from-markdown-db');
      setRows(res.data.rows || []);
    } catch (err) {
      alert('Không thể nạp dữ liệu từ Markdown DB: ' + err);
    } finally {
      setLoading(false);
    }
  };

  // Xuất file Excel 129 cột
  const handleExportExcel = async () => {
    if (rows.length === 0) {
      alert('Chưa có dữ liệu để xuất Excel!');
      return;
    }
    try {
      const res = await axios.post(
        '/chuyen-doi/export',
        { rows, filename: 'KetQua_ChuyenDoi_129Cot.xlsx' },
        { responseType: 'blob' }
      );
      const url = window.URL.createObjectURL(new Blob([res.data]));
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', 'KetQua_ChuyenDoi_129Cot.xlsx');
      document.body.appendChild(link);
      link.click();
      link.remove();
    } catch (err) {
      alert('Lỗi xuất file Excel: ' + err);
    }
  };

  // Lọc theo search và nhóm cột
  const filteredColumns = useMemo(() => {
    if (activeSection === 'all') return columns;
    return columns.filter(c => c.section === activeSection);
  }, [columns, activeSection]);

  const filteredRows = useMemo(() => {
    if (!search.trim()) return rows;
    const q = search.toLowerCase();
    return rows.filter(r => {
      return Object.values(r).some(val => val && String(val).toLowerCase().includes(q));
    });
  }, [rows, search]);

  const sections = useMemo(() => {
    const map = new Map<string, string>();
    columns.forEach(c => {
      if (c.section && c.section_title) {
        map.set(c.section, c.section_title);
      }
    });
    return Array.from(map.entries());
  }, [columns]);

  // Helper format và guard dữ liệu cell
  const renderCellValue = (code: string, rawVal: any) => {
    if (rawVal === undefined || rawVal === null || rawVal === '') return '-';
    const valStr = String(rawVal).trim();

    // Guard Năm sinh: nếu chứa từ ngữ địa danh hoặc dài > 10 ký tự
    if (code === 'CHU_ngaySinh' || code === 'VC_ngaySinh') {
      const isYearOrDate = /^(\d{4}|\d{1,2}[/-]\d{1,2}[/-]\d{4})$/.test(valStr);
      if (!isYearOrDate && valStr.length > 4) {
        return (
          <span className="text-rose-600 font-semibold bg-rose-50 px-1.5 py-0.5 rounded border border-rose-200" title={`Giá trị bất thường: ${valStr}`}>
            ⚠️ Cần kiểm tra
          </span>
        );
      }
    }

    // Guard Số vào sổ: nếu quá dài do dính văn bản
    if (code === 'GCN_soVaoSo' && valStr.length > 35) {
      return (
        <span className="text-amber-700 bg-amber-50 px-1.5 py-0.5 rounded border border-amber-200 max-w-[200px] truncate block" title={valStr}>
          ⚠️ {valStr.slice(0, 30)}...
        </span>
      );
    }

    // Guard Số giấy tờ (CMND/CCCD): nếu chứa chữ cái hoặc không phải 9/12 số
    if (code === 'GT_soGiayTo' || code === 'GT_VC_soGiayTo') {
      const isDigitsId = /^\d{9}(\d{3})?$/.test(valStr.replace(/\s+/g, ''));
      if (!isDigitsId) {
        return (
          <span className="text-rose-600 font-semibold bg-rose-50 px-1.5 py-0.5 rounded border border-rose-200" title={`Giá trị số giấy tờ bất thường: ${valStr}`}>
            ⚠️ Cần kiểm tra
          </span>
        );
      }
    }

    return valStr;
  };

  return (
    <div className={`space-y-4 ${fullscreen ? 'fixed inset-0 z-50 bg-white p-6 overflow-hidden flex flex-col' : ''}`}>
      {/* Header Panel */}
      <div className="bg-white rounded-2xl p-5 shadow-sm border border-slate-200 flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h2 className="text-lg font-bold text-slate-900 flex items-center gap-2">
            <FileSpreadsheet className="text-emerald-600" />
            Bảng Kết Quả Chuyển Đổi Địa Chính (129 Cột Chuẩn Mẫu Excel)
          </h2>
          <p className="text-xs text-slate-500 mt-0.5">
            Ánh xạ toàn bộ thông tin Giấy chứng nhận, Chủ sử dụng, Vợ/Chồng, Thửa đất, Tài sản gắn liền với đất
          </p>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={loadFromMarkdownDb}
            disabled={loading}
            className="px-3.5 py-2 bg-indigo-50 hover:bg-indigo-100 text-indigo-700 text-xs font-semibold rounded-xl border border-indigo-200 transition flex items-center gap-1.5 shadow-sm"
            title="Nạp dữ liệu thô Markdown từ cơ sở dữ liệu và chuyển đổi sang 129 cột"
          >
            <Database size={15} />
            {loading ? 'Đang nạp...' : 'Nạp Dữ Liệu Từ Markdown (DB)'}
          </button>
          <button
            onClick={handleExportExcel}
            className="px-4 py-2 bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-semibold rounded-xl shadow-md transition flex items-center gap-1.5"
          >
            <Download size={15} />
            Xuất File Excel (129 Cột)
          </button>
          <button
            onClick={() => setFullscreen(!fullscreen)}
            className="p-2 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-xl transition"
            title={fullscreen ? 'Thoát toàn màn hình' : 'Toàn màn hình'}
          >
            {fullscreen ? <Minimize2 size={16} /> : <Maximize2 size={16} />}
          </button>
        </div>
      </div>

      {/* Filter & Search */}
      <div className="bg-white rounded-2xl p-4 shadow-sm border border-slate-200 space-y-3">
        <div className="flex flex-col md:flex-row items-center justify-between gap-3">
          <div className="relative flex-1 max-w-md">
            <Search size={16} className="absolute left-3 top-2.5 text-slate-400" />
            <input
              type="text"
              value={search}
              onChange={e => setSearch(e.target.value)}
              placeholder="Tìm theo tên chủ, số seri, số thửa, tờ bản đồ, CCCD/CMND..."
              className="w-full text-xs pl-9 pr-3 py-2 bg-slate-50 border border-slate-200 rounded-lg focus:outline-indigo-500 focus:bg-white"
            />
          </div>
          <div className="text-xs font-semibold text-indigo-700 bg-indigo-50 px-3 py-1.5 rounded-lg border border-indigo-100">
            Tổng cộng: {filteredRows.length} hồ sơ ({filteredColumns.length} cột hiển thị)
          </div>
        </div>

        {/* Section Pills */}
        <div className="flex flex-wrap gap-1.5 pt-1">
          <button
            onClick={() => setActiveSection('all')}
            className={`text-[11px] px-2.5 py-1 rounded-lg font-medium transition ${
              activeSection === 'all'
                ? 'bg-indigo-600 text-white shadow-sm'
                : 'bg-slate-100 hover:bg-slate-200 text-slate-700'
            }`}
          >
            🌟 Tất Cả (129 Cột)
          </button>
          {sections.map(([secKey, secTitle]) => (
            <button
              key={secKey}
              onClick={() => setActiveSection(secKey)}
              className={`text-[11px] px-2.5 py-1 rounded-lg font-medium transition ${
                activeSection === secKey
                  ? 'bg-indigo-600 text-white shadow-sm'
                  : 'bg-slate-100 hover:bg-slate-200 text-slate-700'
              }`}
            >
              {secTitle}
            </button>
          ))}
        </div>
      </div>

      {/* Virtual Table */}
      <div className="bg-white rounded-2xl shadow-sm border border-slate-200 overflow-hidden flex-1 flex flex-col">
        <div className="overflow-x-auto max-h-[640px] custom-scroll flex-1">
          <table className="w-full text-xs text-left border-collapse border-spacing-0">
            <thead className="sticky top-0 z-20 bg-slate-100 shadow-sm border-b border-slate-300">
              <tr>
                <th className="p-2 border-r border-slate-200 font-bold text-slate-700 sticky left-0 bg-slate-100 z-30">STT</th>
                <th className="p-2 border-r border-slate-200 font-bold text-slate-700 sticky left-12 bg-slate-100 z-30">File GCN</th>
                {filteredColumns.map(c => (
                  <th key={c.code} className="p-2 border-r border-slate-200 whitespace-nowrap text-[11px] font-bold text-slate-700">
                    <div>{c.label}</div>
                    <div className="text-[9px] font-mono text-slate-400">{c.code}</div>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 bg-white">
              {filteredRows.length === 0 ? (
                <tr>
                  <td colSpan={filteredColumns.length + 2} className="text-center py-16 text-slate-400">
                    Chưa có dữ liệu. Hãy bấm "Nạp Dữ Liệu Từ Markdown (DB)" để tải bảng 129 cột.
                  </td>
                </tr>
              ) : (
                filteredRows.map((row, idx) => (
                  <tr key={idx} className="hover:bg-indigo-50/40 transition">
                    <td className="p-2 border-r border-slate-100 font-medium text-slate-600 sticky left-0 bg-white">
                      {idx + 1}
                    </td>
                    <td className="p-2 border-r border-slate-100 font-mono text-xs font-semibold text-slate-800 sticky left-12 bg-white max-w-[150px] truncate" title={row.file_name || row.HS_duongDanHSQ}>
                      {row.file_name || row.HS_duongDanHSQ || row.GCN_soPhatHanh || row.so_phat_hanh || '-'}
                    </td>
                    {filteredColumns.map(c => (
                      <td key={c.code} className="p-2 border-r border-slate-100 whitespace-nowrap text-slate-800">
                        {renderCellValue(c.code, row[c.code])}
                      </td>
                    ))}
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
