import React, { useState } from 'react';
import {
  AlertCircle,
  ArrowRight,
  Database,
  FileSpreadsheet,
  FolderUp,
  KeyRound,
  Layers,
  Loader2,
  Lock,
  RefreshCw,
  ShieldCheck,
  UserCheck,
} from 'lucide-react';
import { AuthUser, useAuth } from '../../shared/auth/AuthProvider';

interface LoginPageProps {
  onLocalLogin?: (role: string) => void;
  error?: string | null;
  onRetry?: () => void;
}

const DEMO_ROLES = [
  {
    role: 'ocr-admin',
    name: 'Quản trị viên',
    desc: 'Toàn quyền quản lý hệ thống, nhân viên và phân quyền',
    icon: ShieldCheck,
    color: 'border-rose-200 bg-rose-50/70 text-rose-800 hover:bg-rose-100/80',
    iconColor: 'text-rose-600',
  },
  {
    role: 'ocr-operator',
    name: 'Nhập liệu & Quét lô',
    desc: 'Tải lên hồ sơ, khởi chạy và theo dõi tiến trình xử lý',
    icon: FolderUp,
    color: 'border-blue-200 bg-blue-50/70 text-blue-800 hover:bg-blue-100/80',
    iconColor: 'text-blue-600',
  },
  {
    role: 'ocr-reviewer',
    name: 'Tra soát & Sửa lỗi',
    desc: 'Kiểm tra đối chiếu bằng chứng ảnh OCR và xác nhận',
    icon: UserCheck,
    color: 'border-amber-200 bg-amber-50/70 text-amber-800 hover:bg-amber-100/80',
    iconColor: 'text-amber-600',
  },
  {
    role: 'ocr-exporter',
    name: 'Khai thác dữ liệu',
    desc: 'Xem báo cáo và xuất bảng tính Excel 129 cột chuẩn địa chính',
    icon: FileSpreadsheet,
    color: 'border-emerald-200 bg-emerald-50/70 text-emerald-800 hover:bg-emerald-100/80',
    iconColor: 'text-emerald-600',
  },
  {
    role: 'ocr-viewer',
    name: 'Chỉ xem',
    desc: 'Tra cứu hồ sơ đã lưu trữ mà không chỉnh sửa',
    icon: Database,
    color: 'border-slate-200 bg-slate-50/70 text-slate-800 hover:bg-slate-100/80',
    iconColor: 'text-slate-600',
  },
];

export const LoginPage: React.FC<LoginPageProps> = ({ error, onRetry }) => {
  const { retry } = useAuth();
  const [loggingIn, setLoggingIn] = useState(false);

  const handleKeycloakLogin = () => {
    setLoggingIn(true);
    if (onRetry) {
      onRetry();
    } else {
      retry();
    }
  };

  return (
    <div className="min-h-screen w-full flex flex-col lg:flex-row bg-slate-900 text-slate-100">
      {/* Cột trái: Thương hiệu & Giới thiệu hệ thống */}
      <div className="lg:w-7/12 p-8 sm:p-12 lg:p-16 flex flex-col justify-between relative overflow-hidden bg-gradient-to-br from-slate-950 via-indigo-950 to-slate-900 border-b lg:border-b-0 lg:border-r border-slate-800">
        {/* Họa tiết nền bản đồ / địa chính */}
        <div className="absolute inset-0 opacity-10 pointer-events-none bg-[radial-gradient(#818cf8_1px,transparent_1px)] [background-size:24px_24px]" />

        {/* Brand Top */}
        <div className="relative z-10">
          <div className="inline-flex items-center gap-2.5 px-3 py-1.5 rounded-full bg-indigo-500/10 border border-indigo-500/20 text-indigo-300 text-xs font-semibold">
            <Layers size={14} className="text-indigo-400" />
            <span>Hệ Thống Trí Tuệ Nhân Tạo Địa Chính</span>
          </div>

          <h1 className="mt-6 text-2xl sm:text-3xl lg:text-4xl font-extrabold text-white tracking-tight leading-tight">
            Số Hóa & Nhận Dạng <br />
            <span className="bg-gradient-to-r from-indigo-400 via-sky-300 to-emerald-400 bg-clip-text text-transparent">
              Giấy Chứng Nhận Quyền Sử Dụng Đất
            </span>
          </h1>

          <p className="mt-4 text-sm sm:text-base text-slate-400 max-w-xl leading-relaxed">
            Nền tảng tự động nhận dạng 4 mặt sổ đỏ / sổ hồng, bóc tách bảng tọa độ ranh giới thửa đất
            và chuẩn hóa xuất bảng dữ liệu 129 cột tiêu chuẩn.
          </p>
        </div>

        {/* 3 Trụ cột nghiệp vụ */}
        <div className="my-8 lg:my-12 grid sm:grid-cols-3 gap-4 relative z-10">
          <div className="rounded-2xl border border-slate-800/80 bg-slate-900/40 p-4 backdrop-blur-sm">
            <div className="grid h-9 w-9 place-items-center rounded-xl bg-indigo-500/10 text-indigo-400 mb-3">
              <FolderUp size={18} />
            </div>
            <h3 className="text-xs font-bold text-slate-200">Xử lý hàng loạt</h3>
            <p className="mt-1 text-[11px] text-slate-400 leading-relaxed">
              Quét theo thư mục, đối soát tự động mặt trước / mặt sau.
            </p>
          </div>

          <div className="rounded-2xl border border-slate-800/80 bg-slate-900/40 p-4 backdrop-blur-sm">
            <div className="grid h-9 w-9 place-items-center rounded-xl bg-emerald-500/10 text-emerald-400 mb-3">
              <FileSpreadsheet size={18} />
            </div>
            <h3 className="text-xs font-bold text-slate-200">Chuẩn hóa 129 cột</h3>
            <p className="mt-1 text-[11px] text-slate-400 leading-relaxed">
              Xuất bảng tính tích hợp cơ sở dữ liệu đất đai.
            </p>
          </div>

          <div className="rounded-2xl border border-slate-800/80 bg-slate-900/40 p-4 backdrop-blur-sm">
            <div className="grid h-9 w-9 place-items-center rounded-xl bg-sky-500/10 text-sky-400 mb-3">
              <ShieldCheck size={18} />
            </div>
            <h3 className="text-xs font-bold text-slate-200">Bảo mật & Phân quyền</h3>
            <p className="mt-1 text-[11px] text-slate-400 leading-relaxed">
              Xác thực OIDC, phân quyền theo vai trò nghiệp vụ.
            </p>
          </div>
        </div>

        {/* Footer info */}
        <div className="relative z-10 text-[11px] text-slate-600">
          v2.0 · Tiêu chuẩn lưu trữ địa chính số
        </div>
      </div>

      {/* Cột phải: Khối Đăng nhập */}
      <div className="lg:w-5/12 bg-white text-slate-900 p-8 sm:p-12 flex flex-col justify-center">
        <div className="max-w-md w-full mx-auto space-y-6">
          {/* Header */}
          <div>
            <div className="inline-grid h-11 w-11 place-items-center rounded-2xl bg-indigo-600 text-white shadow-md shadow-indigo-200 mb-3">
              <Lock size={20} />
            </div>
            <h2 className="text-xl font-bold text-slate-900 tracking-tight">Đăng nhập</h2>
            <p className="mt-1 text-xs text-slate-500">
              Dùng tài khoản cán bộ được cấp để tiếp tục.
            </p>
          </div>

          {/* Lỗi nếu có */}
          {error && (
            <div className="flex items-start gap-2.5 rounded-2xl border border-rose-200 bg-rose-50 p-4 text-xs font-medium text-rose-800">
              <AlertCircle size={17} className="mt-0.5 shrink-0 text-rose-600" />
              <div className="flex-1">
                <span className="font-bold">Lỗi xác thực:</span> {error}
              </div>
            </div>
          )}

          {/* Nút Đăng nhập chính */}
          <div className="space-y-3">
            <button
              type="button"
              onClick={handleKeycloakLogin}
              disabled={loggingIn}
              className="w-full inline-flex items-center justify-center gap-2 rounded-2xl bg-slate-900 px-5 py-3.5 text-sm font-semibold text-white shadow-lg shadow-slate-900/10 hover:bg-slate-800 transition active:scale-[0.99] disabled:opacity-60 cursor-pointer"
            >
              {loggingIn ? (
                <>
                  <Loader2 size={16} className="animate-spin" />
                  Đang chuyển hướng xác thực...
                </>
              ) : (
                <>
                  <KeyRound size={16} />
                  Đăng nhập với tài khoản hệ thống
                  <ArrowRight size={15} />
                </>
              )}
            </button>

            {error && (
              <button
                type="button"
                onClick={() => (onRetry ? onRetry() : retry())}
                className="w-full inline-flex items-center justify-center gap-1.5 rounded-2xl border border-slate-200 bg-white px-4 py-2.5 text-xs font-semibold text-slate-700 hover:bg-slate-50 transition cursor-pointer"
              >
                <RefreshCw size={13} />
                Thử kết nối lại máy chủ
              </button>
            )}
          </div>

          {/* Footer */}
          <div className="pt-5 border-t border-slate-100 text-center">
            <p className="text-[11px] text-slate-400">
              Mọi hoạt động được ghi nhật ký và kiểm soát truy cập.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
};

