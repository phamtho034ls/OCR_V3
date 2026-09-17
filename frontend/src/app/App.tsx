import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { Database, FileSpreadsheet, FolderUp, Layers, Upload } from 'lucide-react';
import { DataConversionPage } from '../pages/data-conversion/DataConversionPage';
import { DocumentUploadPage } from '../pages/document-upload/DocumentUploadPage';
import { BatchScanPage } from '../pages/batch-scan/BatchScanPage';
import { RawMarkdownPage } from '../pages/raw-markdown/RawMarkdownPage';

type AppTab = 'batch' | 'conversion' | 'records' | 'upload';

const navigation: Array<{
  id: AppTab;
  label: string;
  shortLabel: string;
  Icon: typeof FolderUp;
}> = [
  { id: 'batch', label: 'Xử lý hàng loạt', shortLabel: 'Hàng loạt', Icon: FolderUp },
  { id: 'upload', label: 'Kiểm tra hồ sơ', shortLabel: 'Hồ sơ', Icon: Upload },
  { id: 'conversion', label: 'Bảng dữ liệu 129 cột', shortLabel: 'Bảng dữ liệu', Icon: FileSpreadsheet },
  { id: 'records', label: 'Kho hồ sơ', shortLabel: 'Kho hồ sơ', Icon: Database },
];

export const App: React.FC = () => {
  const [currentTab, setCurrentTab] = useState<AppTab>('batch');
  const [scannedRows, setScannedRows] = useState<Record<string, any>[]>([]);
  const [storageAvailable, setStorageAvailable] = useState<boolean | null>(null);
  const [isBatchRunning, setIsBatchRunning] = useState<boolean>(false);

  useEffect(() => {
    let cancelled = false;
    const checkStorage = async () => {
      try {
        const response = await axios.get('/api/v1/pg/health');
        if (!cancelled) setStorageAvailable(Boolean(response.data?.connected));
      } catch {
        if (!cancelled) setStorageAvailable(false);
      }
    };

    checkStorage();
    // Chỉ retry 1 lần sau 10s nếu lần đầu thất bại, không polling liên tục
    const retryTimer = window.setTimeout(() => {
      if (!cancelled) checkStorage();
    }, 10000);
    return () => {
      cancelled = true;
      window.clearTimeout(retryTimer);
    };
  }, []);

  const handleView129Table = (rows: Record<string, any>[]) => {
    setScannedRows(rows);
    setCurrentTab('conversion');
  };

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900">
      <header className="sticky top-0 z-40 border-b border-slate-200/80 bg-white/95 backdrop-blur">
        <div className="mx-auto flex h-16 max-w-[1440px] items-center justify-between gap-4 px-4 sm:px-6 lg:px-8">
          <div className="flex min-w-0 items-center gap-3">
            <div className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-slate-900 text-white shadow-sm">
              <Layers size={19} strokeWidth={2.25} />
            </div>
            <div className="min-w-0">
              <h1 className="truncate text-sm font-semibold tracking-tight text-slate-950 sm:text-base">
                Số hóa hồ sơ địa chính
              </h1>
              <p className="hidden text-xs text-slate-500 sm:block">
                Trích xuất, đối soát và xuất dữ liệu chuẩn
              </p>
            </div>
          </div>

          <div
            className={`hidden items-center gap-2 rounded-full px-3 py-1.5 text-xs font-medium sm:flex ${
              storageAvailable === false
                ? 'bg-red-50 text-red-800'
                : storageAvailable === null
                  ? 'bg-slate-50 text-slate-500'
                  : 'bg-emerald-50 text-emerald-800'
            }`}
            title={storageAvailable === false ? 'PostgreSQL chưa kết nối — hệ thống cần PostgreSQL để hoạt động' : storageAvailable === null ? 'Đang kiểm tra kết nối...' : 'Kho dữ liệu sẵn sàng'}
          >
            <span className={`h-1.5 w-1.5 rounded-full ${storageAvailable === false ? 'bg-red-500' : storageAvailable === null ? 'bg-slate-400' : 'bg-emerald-500'}`} />
            {storageAvailable === false ? 'PostgreSQL chưa kết nối' : storageAvailable === null ? 'Đang kiểm tra...' : 'Dữ liệu sẵn sàng'}
          </div>
        </div>

        <nav className="mx-auto flex max-w-[1440px] gap-1 overflow-x-auto px-3 sm:px-5 lg:px-7" aria-label="Chức năng chính">
          {navigation.map(({ id, label, shortLabel, Icon }) => {
            const active = currentTab === id;
            return (
              <button
                key={id}
                type="button"
                onClick={() => setCurrentTab(id)}
                aria-current={active ? 'page' : undefined}
                className={`flex shrink-0 items-center gap-2 border-b-2 px-3 py-3 text-xs font-medium transition sm:px-4 ${
                  active
                    ? 'border-slate-900 text-slate-950'
                    : 'border-transparent text-slate-500 hover:border-slate-300 hover:text-slate-800'
                }`}
              >
                <Icon size={15} strokeWidth={active ? 2.4 : 2} />
                <span className="sm:hidden">{shortLabel}</span>
                <span className="hidden sm:inline">{label}</span>
                {id === 'batch' && isBatchRunning && (
                  <span className="relative flex h-2 w-2 ml-0.5" title="Đang xử lý trong nền...">
                    <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                    <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
                  </span>
                )}
              </button>
            );
          })}
        </nav>
      </header>

      <main className="mx-auto w-full max-w-[1440px] px-4 py-6 sm:px-6 lg:px-8 lg:py-8">
        <div className={currentTab === 'batch' ? 'block' : 'hidden'}>
          <BatchScanPage
            onView129Table={handleView129Table}
            onOpenPgStorage={() => setCurrentTab('records')}
            onRunningChange={setIsBatchRunning}
          />
        </div>
        <div className={currentTab === 'conversion' ? 'block' : 'hidden'}>
          <DataConversionPage initialRows={scannedRows} />
        </div>
        <div className={currentTab === 'records' ? 'block' : 'hidden'}>
          <RawMarkdownPage
            onView129Table={handleView129Table}
            isActive={currentTab === 'records'}
          />
        </div>
        <div className={currentTab === 'upload' ? 'block' : 'hidden'}>
          <DocumentUploadPage />
        </div>
      </main>
    </div>
  );
};
