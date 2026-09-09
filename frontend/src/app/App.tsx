import React, { useState } from 'react';
import { FileSpreadsheet, Upload, FolderUp, Layers, FileCode } from 'lucide-react';
import { DataConversionPage } from '../pages/data-conversion/DataConversionPage';
import { DocumentUploadPage } from '../pages/document-upload/DocumentUploadPage';
import { BatchScanPage } from '../pages/batch-scan/BatchScanPage';
import { RawMarkdownPage } from '../pages/raw-markdown/RawMarkdownPage';

export const App: React.FC = () => {
  const [currentTab, setCurrentTab] = useState<'conversion' | 'batch' | 'upload' | 'raw_markdown'>('batch');
  const [scannedRows, setScannedRows] = useState<Record<string, any>[]>([]);

  const handleView129Table = (rows: Record<string, any>[]) => {
    setScannedRows(rows);
    setCurrentTab('conversion');
  };

  return (
    <div className="min-h-screen flex flex-col bg-slate-50">
      {/* Top Header */}
      <header className="bg-white border-b border-slate-200 sticky top-0 z-40 shadow-sm">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 flex items-center justify-between h-16">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-emerald-600 to-emerald-800 flex items-center justify-center text-white shadow">
              <Layers size={22} />
            </div>
            <div>
              <h1 className="text-base font-bold text-slate-900 leading-tight">
                HỆ THỐNG OCR SỔ ĐỎ / SỔ HỒNG
              </h1>

            </div>
          </div>

          <div className="flex items-center gap-2">
            <span className="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
              <span className="w-2 h-2 rounded-full bg-emerald-500 mr-1.5 animate-pulse"></span>
              Backend v2.0 Active
            </span>
          </div>
        </div>

        {/* Navigation Tabs */}
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 flex space-x-6 border-t border-slate-100">
          <button
            onClick={() => setCurrentTab('batch')}
            className={`py-3 px-1 border-b-2 font-semibold text-xs flex items-center gap-2 transition ${currentTab === 'batch'
                ? 'border-indigo-600 text-indigo-700'
                : 'border-transparent text-slate-500 hover:text-slate-700'
              }`}
          >
            <FolderUp size={16} />
            <span>Quét Thư Mục Hàng Loạt</span>
            <span className="bg-indigo-100 text-indigo-800 text-[10px] px-2 py-0.5 rounded-full font-bold">Mới</span>
          </button>
          <button
            onClick={() => setCurrentTab('conversion')}
            className={`py-3 px-1 border-b-2 font-semibold text-xs flex items-center gap-2 transition ${currentTab === 'conversion'
                ? 'border-emerald-600 text-emerald-700'
                : 'border-transparent text-slate-500 hover:text-slate-700'
              }`}
          >
            <FileSpreadsheet size={16} />
            <span>Bảng Chuyển Đổi Địa Chính (129 Cột)</span>
            <span className="bg-emerald-100 text-emerald-800 text-[10px] px-2 py-0.5 rounded-full font-bold">Chuẩn Mẫu</span>
          </button>
          <button
            onClick={() => setCurrentTab('raw_markdown')}
            className={`py-3 px-1 border-b-2 font-semibold text-xs flex items-center gap-2 transition ${currentTab === 'raw_markdown'
                ? 'border-indigo-600 text-indigo-700'
                : 'border-transparent text-slate-500 hover:text-slate-700'
              }`}
          >
            <FileCode size={16} />
            <span>Bảng Dữ Liệu Thô (Markdown)</span>
            <span className="bg-indigo-100 text-indigo-800 text-[10px] px-2 py-0.5 rounded-full font-bold">SQLite</span>
          </button>
          <button
            onClick={() => setCurrentTab('upload')}
            className={`py-3 px-1 border-b-2 font-semibold text-xs flex items-center gap-2 transition ${currentTab === 'upload'
                ? 'border-emerald-600 text-emerald-700'
                : 'border-transparent text-slate-500 hover:text-slate-700'
              }`}
          >
            <Upload size={16} />
            <span>Nhận Dạng Đơn Lẻ</span>
          </button>
        </div>
      </header>

      {/* Main Content */}
      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-6">
        {currentTab === 'batch' && <BatchScanPage onView129Table={handleView129Table} />}
        {currentTab === 'conversion' && <DataConversionPage initialRows={scannedRows} />}
        {currentTab === 'raw_markdown' && <RawMarkdownPage />}
        {currentTab === 'upload' && <DocumentUploadPage />}
      </main>

      {/* Footer */}
      <footer className="bg-white border-t border-slate-200 py-3 text-center text-xs text-slate-400">
        Hệ thống OCR Giấy chứng nhận quyền sử dụng đất &copy; 2026 - Backend/Frontend Production Architecture
      </footer>
    </div>
  );
};
