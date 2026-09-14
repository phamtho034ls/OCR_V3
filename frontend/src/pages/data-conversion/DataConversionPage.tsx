import React, { useState, useEffect, useMemo, useCallback } from 'react';
import axios from 'axios';
import { Download, Search, Maximize2, Minimize2, Database, FileSpreadsheet, Folder, RefreshCw, Layers } from 'lucide-react';
import { ChuyenDoiColumn, PgFolderOption } from '../../shared/types';

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

  // Thư mục kết quả PostgreSQL
  const [folderOptions, setFolderOptions] = useState<PgFolderOption[]>([]);
  const [selectedFolder, setSelectedFolder] = useState<string>('all');
  const [currentLoadedLabel, setCurrentLoadedLabel] = useState<string>(
    initialRows && initialRows.length > 0 ? `Đã nạp ${initialRows.length} hồ sơ từ đợt quét` : ''
  );

  // Nạp danh sách 129 cột
  useEffect(() => {
    axios.get('/api/v1/exports/columns-129')
      .then(res => setColumns(res.data.columns || []))
      .catch(err => console.error('Lỗi nạp cột:', err));
  }, []);

  // Nạp danh sách thư mục từ PostgreSQL
  const fetchFolders = useCallback(async () => {
    try {
      const res = await axios.get('/api/v1/pg/filters');
      setFolderOptions(res.data?.folders || []);
    } catch (err) {
      console.error('Lỗi nạp danh mục thư mục:', err);
    }
  }, []);

  useEffect(() => {
    fetchFolders();
  }, [fetchFolders]);

  useEffect(() => {
    if (initialRows && initialRows.length > 0) {
      setRows(initialRows);
      setCurrentLoadedLabel(`Đã nạp ${initialRows.length} hồ sơ từ đợt quét vừa thực hiện`);
    }
  }, [initialRows]);

  // Nạp dữ liệu từ PostgreSQL theo Thư Mục Kết Quả (Folder)
  const loadFromPostgres = async (folderToLoad: string = selectedFolder) => {
    setLoading(true);
    try {
      const params: any = { limit: 5000 };
      if (folderToLoad !== 'all') {
        params.folder_result = folderToLoad;
      }
      const res = await axios.get('/api/v1/pg/129-rows', { params });
      const loadedRows = res.data?.rows || [];
      setRows(loadedRows);
      if (folderToLoad !== 'all') {
        setCurrentLoadedLabel(`Thư mục: ${folderToLoad} (${loadedRows.length} dòng)`);
      } else {
        setCurrentLoadedLabel(`Toàn bộ kho dữ liệu PostgreSQL (${loadedRows.length} dòng)`);
      }
    } catch (err: any) {
      alert('Không thể nạp dữ liệu từ PostgreSQL: ' + (err.response?.data?.detail || err.message));
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
      const filename = selectedFolder !== 'all' 
        ? `KetQua_129Cot_${selectedFolder}.xlsx` 
        : 'KetQua_ChuyenDoi_129Cot.xlsx';

      const res = await axios.post(
        '/api/v1/exports/excel-129',
        { rows, filename },
        { responseType: 'blob' }
      );
      const url = window.URL.createObjectURL(new Blob([res.data]));
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', filename);
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

  return (
    <div className={`space-y-4 ${fullscreen ? 'fixed inset-0 z-50 bg-white p-6 overflow-hidden flex flex-col' : ''}`}>
      {/* Header Panel */}
      <div className="bg-white rounded-2xl p-5 shadow-sm border border-slate-200 flex flex-col lg:flex-row lg:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <h2 className="text-lg font-bold text-slate-900 flex items-center gap-2">
              <FileSpreadsheet className="text-emerald-600" />
              <span>Bảng Kết Quả Chuyển Đổi Địa Chính (129 Cột Chuẩn Mẫu Excel)</span>
            </h2>
            <span className="bg-emerald-50 text-emerald-700 text-xs px-2.5 py-0.5 rounded-full font-bold border border-emerald-200">
              Chuẩn KeKhaiDangKy
            </span>
          </div>
          <p className="text-xs text-slate-500 mt-0.5">
            Ánh xạ toàn bộ thông tin Giấy chứng nhận, Chủ sử dụng, Vợ/Chồng, Thửa đất, Tài sản gắn liền với đất
          </p>
        </div>

        {/* Action Buttons */}
        <div className="flex flex-wrap items-center gap-2">
          <button
            onClick={handleExportExcel}
            disabled={rows.length === 0}
            className="px-4 py-2 bg-emerald-600 hover:bg-emerald-700 disabled:bg-slate-200 text-white disabled:text-slate-400 text-xs font-bold rounded-xl shadow-sm transition flex items-center gap-1.5"
          >
            <Download size={15} />
            <span>Xuất File Excel (129 Cột)</span>
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

      {/* ── BỘ CHỌN THƯ MỤC KẾT QUẢ POSTGRESQL & TÌM KIẾM ── */}
      <div className="bg-white rounded-2xl p-4 shadow-sm border border-slate-200 space-y-3">
        <div className="grid grid-cols-1 md:grid-cols-12 gap-3 items-center">
          
          {/* Chọn Thư Mục Kết Quả (Folder Selector) */}
          <div className="md:col-span-6 flex items-center gap-2">
            <div className="flex items-center gap-1 text-xs font-bold text-slate-700 shrink-0">
              <Folder size={15} className="text-indigo-600" />
              <span>Thư mục kết quả:</span>
            </div>
            <select
              value={selectedFolder}
              onChange={e => {
                const val = e.target.value;
                setSelectedFolder(val);
                loadFromPostgres(val);
              }}
              className="flex-1 bg-slate-50 border border-slate-200 rounded-xl px-3 py-2 text-xs font-bold text-slate-800 focus:outline-indigo-500 focus:bg-white truncate"
            >
              <option value="all">🌟 Toàn bộ kho PostgreSQL</option>
              {folderOptions.map(f => (
                <option key={f.name} value={f.name}>
                  📁 {f.name} ({f.count} hồ sơ) - {f.date}
                </option>
              ))}
            </select>
            <button
              onClick={() => loadFromPostgres(selectedFolder)}
              disabled={loading}
              className="px-3 py-2 bg-indigo-50 hover:bg-indigo-100 text-indigo-700 text-xs font-semibold rounded-xl border border-indigo-200 transition flex items-center gap-1 shrink-0"
              title="Tải lại dữ liệu từ PostgreSQL"
            >
              <RefreshCw size={13} className={loading ? 'animate-spin' : ''} />
              <span>Nạp</span>
            </button>
          </div>

          {/* Ô Tìm kiếm nhanh */}
          <div className="md:col-span-4">
            <div className="relative">
              <Search size={14} className="absolute left-3 top-2.5 text-slate-400" />
              <input
                type="text"
                value={search}
                onChange={e => setSearch(e.target.value)}
                placeholder="Tìm tên chủ, số seri, thửa, tờ, CCCD..."
                className="w-full text-xs pl-8 pr-3 py-2 bg-slate-50 border border-slate-200 rounded-xl focus:outline-indigo-500 focus:bg-white"
              />
            </div>
          </div>

          {/* Đếm số dòng */}
          <div className="md:col-span-2 text-right">
            <span className="text-xs font-bold text-indigo-700 bg-indigo-50 px-3 py-1.5 rounded-xl border border-indigo-100 inline-block">
              {filteredRows.length} hồ sơ ({filteredColumns.length} cột)
            </span>
          </div>
        </div>

        {/* Thông báo trạng thái folder đang nạp */}
        {currentLoadedLabel && (
          <div className="pt-2 border-t border-slate-100 flex items-center justify-between text-xs text-slate-500">
            <div className="flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-emerald-500"></span>
              <span>Đang hiển thị: <b className="text-slate-800">{currentLoadedLabel}</b></span>
            </div>
            {folderOptions.length > 0 && (
              <span className="text-slate-400 text-[11px]">
                Tổng cộng có {folderOptions.length} thư mục kết quả đã lưu trong PostgreSQL
              </span>
            )}
          </div>
        )}

        {/* Section Pills */}
        <div className="flex flex-wrap gap-1.5 pt-2 border-t border-slate-100">
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
              {loading ? (
                <tr>
                  <td colSpan={filteredColumns.length + 2} className="text-center py-20 text-slate-400">
                    <RefreshCw size={24} className="animate-spin mx-auto mb-2 text-indigo-500" />
                    <span>Đang nạp dữ liệu từ PostgreSQL...</span>
                  </td>
                </tr>
              ) : filteredRows.length === 0 ? (
                <tr>
                  <td colSpan={filteredColumns.length + 2} className="text-center py-20 text-slate-400">
                    <FileSpreadsheet size={32} className="mx-auto mb-2 text-slate-300" />
                    <p className="text-sm font-semibold text-slate-600">Chưa có dữ liệu hiển thị</p>
                    <p className="text-xs text-slate-400 mt-1">
                      Hãy chọn Thư mục kết quả ở trên hoặc bấm "Nạp" để tải dữ liệu từ PostgreSQL.
                    </p>
                  </td>
                </tr>
              ) : (
                filteredRows.map((row, idx) => (
                  <tr key={idx} className="hover:bg-indigo-50/40 transition">
                    <td className="p-2 border-r border-slate-100 font-medium text-slate-600 sticky left-0 bg-white">
                      {idx + 1}
                    </td>
                    <td className="p-2 border-r border-slate-100 font-mono text-xs font-semibold text-slate-800 sticky left-12 bg-white max-w-[160px] truncate" title={row.file_name || row.HS_duongDanHSQ}>
                      {row.file_name || row.HS_duongDanHSQ || row.GCN_soPhatHanh || '-'}
                    </td>
                    {filteredColumns.map(c => {
                      const rawVal = row[c.code];
                      return (
                        <td key={c.code} className="p-2 border-r border-slate-100 whitespace-nowrap">
                          {rawVal !== undefined && rawVal !== null && rawVal !== '' ? String(rawVal) : '-'}
                        </td>
                      );
                    })}
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
