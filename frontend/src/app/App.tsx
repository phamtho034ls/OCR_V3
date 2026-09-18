import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { Database, FileSpreadsheet, FolderUp, Layers, LogOut, Upload, UserCog } from 'lucide-react';
import { DataConversionPage } from '../pages/data-conversion/DataConversionPage';
import { DocumentUploadPage } from '../pages/document-upload/DocumentUploadPage';
import { BatchScanPage } from '../pages/batch-scan/BatchScanPage';
import { RawMarkdownPage } from '../pages/raw-markdown/RawMarkdownPage';
import { UserManagementPage } from '../pages/admin/UserManagementPage';
import { LoginPage } from '../pages/login/LoginPage';
import { useAuth } from '../shared/auth/AuthProvider';
import { UserProfileModal } from '../shared/components/UserProfileModal';

type AppTab = 'batch' | 'conversion' | 'records' | 'upload' | 'admin';

const navigation: Array<{
  id: AppTab;
  label: string;
  shortLabel: string;
  Icon: typeof FolderUp;
  permission?: string;
}> = [
  { id: 'batch', label: 'Xử lý hàng loạt', shortLabel: 'Hàng loạt', Icon: FolderUp, permission: 'batch.create' },
  { id: 'upload', label: 'Kiểm tra hồ sơ', shortLabel: 'Hồ sơ', Icon: Upload, permission: 'document.create' },
  { id: 'conversion', label: 'Bảng dữ liệu 129 cột', shortLabel: 'Bảng dữ liệu', Icon: FileSpreadsheet, permission: 'record.read' },
  { id: 'records', label: 'Kho hồ sơ', shortLabel: 'Kho hồ sơ', Icon: Database, permission: 'record.read' },
  { id: 'admin', label: 'Tài khoản & quyền', shortLabel: 'Quyền', Icon: UserCog, permission: 'user.manage' },
];

export const App: React.FC = () => {
  const { user, loading: authLoading, error: authError, can, logout, retry } = useAuth();
  const [currentTab, setCurrentTab] = useState<AppTab>('batch');
  const [scannedRows, setScannedRows] = useState<Record<string, any>[]>([]);
  const [storageAvailable, setStorageAvailable] = useState<boolean | null>(null);
  const [isBatchRunning, setIsBatchRunning] = useState<boolean>(false);
  const [profileModalOpen, setProfileModalOpen] = useState<boolean>(false);

  const visibleNavigation = navigation.filter((item) => !item.permission || can(item.permission));

  useEffect(() => {
    if (!visibleNavigation.some((item) => item.id === currentTab)) {
      setCurrentTab(visibleNavigation[0]?.id || 'records');
    }
  }, [currentTab, visibleNavigation]);

  useEffect(() => {
    // App được mount trong khi AuthProvider còn đang đổi code OIDC lấy token.
    // Không gọi API bảo vệ trước thời điểm đó, nếu không health check sẽ bị 401
    // dù phiên Keycloak sau đó hợp lệ.
    if (authLoading || !user) return;

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
  }, [authLoading, user]);

  const handleView129Table = (rows: Record<string, any>[]) => {
    setScannedRows(rows);
    setCurrentTab('conversion');
  };

  if (authLoading) {
    return (
      <div className="grid min-h-screen place-items-center bg-slate-950 text-slate-100">
        <div className="flex flex-col items-center gap-3 p-6 text-center">
          <div className="grid h-11 w-11 place-items-center rounded-2xl bg-indigo-600 text-white shadow-xl shadow-indigo-600/30 animate-pulse">
            <Layers size={22} />
          </div>
          <div className="text-sm font-bold text-white tracking-tight">Số hóa hồ sơ địa chính</div>
          <p className="text-xs text-slate-500">Đang xác thực...</p>
        </div>
      </div>
    );
  }

  if (authError || !user) {
    return <LoginPage error={authError} onRetry={retry} />;
  }

  const userInitials = (user.display_name || user.username || 'U')
    .split(' ')
    .map((w: string) => w[0])
    .filter(Boolean)
    .slice(-2)
    .join('')
    .toUpperCase();

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900">
      <header className="sticky top-0 z-40 border-b border-slate-200/80 bg-white/95 backdrop-blur">
        <div className="mx-auto flex h-14 max-w-[1440px] items-center justify-between gap-4 px-4 sm:px-6 lg:px-8">
          <div className="flex min-w-0 items-center gap-3">
            <div className="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-slate-900 text-white shadow-sm">
              <Layers size={17} strokeWidth={2.25} />
            </div>
            <div className="min-w-0">
              <h1 className="truncate text-sm font-bold tracking-tight text-slate-950">
                Số hóa hồ sơ địa chính
              </h1>
              <p className="hidden text-[11px] text-slate-400 sm:block">OCR Sổ Đỏ / Sổ Hồng</p>
            </div>
          </div>

          <div className="flex items-center gap-1.5">
            {/* Storage Status Dot */}
            <div
              className={`hidden items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-medium lg:flex ${
                storageAvailable === false
                  ? 'bg-red-50 text-red-700'
                  : storageAvailable === null
                    ? 'bg-slate-100 text-slate-400'
                    : 'bg-emerald-50 text-emerald-700'
              }`}
              title={
                storageAvailable === false
                  ? 'PostgreSQL chưa kết nối'
                  : storageAvailable === null
                    ? 'Đang kiểm tra kết nối...'
                    : 'Kho dữ liệu sẵn sàng'
              }
            >
              <span
                className={`h-1.5 w-1.5 rounded-full ${
                  storageAvailable === false
                    ? 'bg-red-500'
                    : storageAvailable === null
                      ? 'bg-slate-300 animate-pulse'
                      : 'bg-emerald-500'
                }`}
              />
              {storageAvailable === false ? 'Mất kết nối' : storageAvailable === null ? 'Đang kiểm tra...' : 'Trực tuyến'}
            </div>

            {/* User Avatar Button */}
            <button
              type="button"
              onClick={() => setProfileModalOpen(true)}
              className="flex items-center gap-2 rounded-xl px-2 py-1.5 hover:bg-slate-100 transition cursor-pointer"
              title="Thông tin tài khoản"
            >
              <div className="grid h-7 w-7 shrink-0 place-items-center rounded-lg bg-indigo-600 text-white text-[11px] font-bold shadow-sm">
                {userInitials}
              </div>
              <div className="hidden text-left sm:block min-w-0">
                <p className="max-w-36 truncate text-xs font-semibold text-slate-800 leading-tight">{user.display_name || user.username}</p>
                <p className="max-w-36 truncate text-[10px] text-slate-400 leading-tight capitalize">{user.roles[0]?.replace('ocr-', '') ?? ''}</p>
              </div>
            </button>

            <button
              type="button"
              onClick={() => void logout()}
              className="rounded-lg p-2 text-slate-400 transition hover:bg-slate-100 hover:text-slate-700"
              title="Đăng xuất"
              aria-label="Đăng xuất"
            >
              <LogOut size={15} />
            </button>
          </div>
        </div>

        <nav className="mx-auto flex max-w-[1440px] gap-0.5 overflow-x-auto px-3 sm:px-5 lg:px-7" aria-label="Chức năng chính">
          {visibleNavigation.map(({ id, label, shortLabel, Icon }) => {
            const active = currentTab === id;
            return (
              <button
                key={id}
                type="button"
                onClick={() => setCurrentTab(id)}
                aria-current={active ? 'page' : undefined}
                className={`flex shrink-0 items-center gap-2 border-b-2 px-3 py-2.5 text-xs font-medium transition sm:px-4 ${
                  active
                    ? 'border-indigo-600 text-indigo-700'
                    : 'border-transparent text-slate-500 hover:border-slate-200 hover:text-slate-700'
                }`}
              >
                <Icon size={14} strokeWidth={active ? 2.5 : 2} />
                <span className="sm:hidden">{shortLabel}</span>
                <span className="hidden sm:inline">{label}</span>
                {id === 'batch' && isBatchRunning && (
                  <span className="relative flex h-1.5 w-1.5 ml-0.5">
                    <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
                    <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-emerald-500" />
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
        <div className={currentTab === 'admin' ? 'block' : 'hidden'}>
          <UserManagementPage />
        </div>
      </main>

      <UserProfileModal
        isOpen={profileModalOpen}
        onClose={() => setProfileModalOpen(false)}
      />
    </div>
  );
};
