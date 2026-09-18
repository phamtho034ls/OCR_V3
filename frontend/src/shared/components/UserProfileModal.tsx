import React, { useState } from 'react';
import {
  KeyRound,
  LogOut,
  Mail,
  ShieldCheck,
  User,
  X,
} from 'lucide-react';
import { useAuth } from '../auth/AuthProvider';
import { ChangePasswordModal } from './ChangePasswordModal';

interface UserProfileModalProps {
  isOpen: boolean;
  onClose: () => void;
}

const ROLE_INFO: Record<string, { label: string; desc: string; badgeClass: string }> = {
  'ocr-admin': {
    label: 'Quản trị đơn vị',
    desc: 'Toàn quyền quản lý hệ thống, nhân viên và dữ liệu',
    badgeClass: 'bg-rose-50 text-rose-800 border-rose-200',
  },
  'ocr-operator': {
    label: 'Nhập liệu & Quét lô',
    desc: 'Tải lên hồ sơ, khởi tạo và theo dõi tiến trình quét lô',
    badgeClass: 'bg-blue-50 text-blue-800 border-blue-200',
  },
  'ocr-reviewer': {
    label: 'Tra soát dữ liệu',
    desc: 'Kiểm tra đối chiếu bằng chứng ảnh OCR và chỉnh sửa',
    badgeClass: 'bg-amber-50 text-amber-800 border-amber-200',
  },
  'ocr-exporter': {
    label: 'Khai thác dữ liệu',
    desc: 'Xem và xuất bảng tính Excel 129 cột chuẩn địa chính',
    badgeClass: 'bg-emerald-50 text-emerald-800 border-emerald-200',
  },
  'ocr-viewer': {
    label: 'Chỉ xem',
    desc: 'Tra cứu hồ sơ lưu trữ mà không chỉnh sửa',
    badgeClass: 'bg-slate-50 text-slate-700 border-slate-200',
  },
};

export const UserProfileModal: React.FC<UserProfileModalProps> = ({ isOpen, onClose }) => {
  const { user, logout } = useAuth();
  const [isChangePasswordOpen, setIsChangePasswordOpen] = useState(false);

  if (!isOpen || !user) return null;

  const initials = (user.display_name || user.username || 'U')
    .split(' ')
    .map((w) => w[0])
    .filter(Boolean)
    .slice(-2)
    .join('')
    .toUpperCase();

  return (
    <>
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/60 p-4 backdrop-blur-sm animate-in fade-in duration-150">
        <div
          className="w-full max-w-md overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-2xl flex flex-col"
          role="dialog"
          aria-modal="true"
          aria-labelledby="user-profile-title"
        >
          {/* Header */}
          <div className="flex items-center justify-between border-b border-slate-100 px-5 py-4">
            <h2 id="user-profile-title" className="text-sm font-bold text-slate-900">
              Tài khoản của tôi
            </h2>
            <button
              type="button"
              onClick={onClose}
              className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-700 transition cursor-pointer"
              aria-label="Đóng"
            >
              <X size={16} />
            </button>
          </div>

          {/* Body */}
          <div className="p-6 space-y-5">
            {/* User Info Avatar + Details */}
            <div className="flex items-center gap-4">
              <div className="grid h-14 w-14 shrink-0 place-items-center rounded-2xl bg-gradient-to-br from-indigo-600 to-indigo-800 text-lg font-bold text-white shadow-md shadow-indigo-200">
                {initials}
              </div>
              <div className="min-w-0 flex-1">
                <h3 className="text-base font-bold text-slate-900 truncate">
                  {user.display_name || user.username}
                </h3>
                <p className="text-xs font-mono text-slate-500 truncate">
                  @{user.username}
                </p>
                {user.email && (
                  <p className="mt-1 text-xs text-slate-600 flex items-center gap-1.5 truncate">
                    <Mail size={13} className="shrink-0 text-slate-400" />
                    {user.email}
                  </p>
                )}
              </div>
            </div>

            {/* Roles Section */}
            <div>
              <div className="flex items-center gap-1.5 text-xs font-semibold text-slate-600 mb-2">
                <ShieldCheck size={14} className="text-indigo-500" />
                <span>Vai trò</span>
              </div>
              <div className="space-y-1.5">
                {user.roles.map((roleName) => {
                  const info = ROLE_INFO[roleName] || {
                    label: roleName.replace('ocr-', ''),
                    desc: 'Vai trò phân quyền',
                    badgeClass: 'bg-indigo-50 text-indigo-800 border-indigo-200',
                  };
                  return (
                    <div
                      key={roleName}
                      className={`rounded-xl border px-3 py-2.5 ${info.badgeClass}`}
                    >
                      <span className="font-semibold text-xs">{info.label}</span>
                      <p className="mt-0.5 text-[11px] opacity-80 leading-relaxed">{info.desc}</p>
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Quick Actions */}
            <div className="pt-2 border-t border-slate-100 flex flex-col gap-2">
              <button
                type="button"
                onClick={() => setIsChangePasswordOpen(true)}
                className="w-full inline-flex items-center justify-center gap-2 rounded-xl border border-slate-200 bg-white py-2.5 px-4 text-xs font-semibold text-slate-700 shadow-sm hover:bg-slate-50 transition cursor-pointer"
              >
                <KeyRound size={14} className="text-indigo-600" />
                Đổi mật khẩu
              </button>
            </div>
          </div>

          {/* Footer */}
          <div className="flex items-center justify-between border-t border-slate-100 bg-slate-50/70 px-5 py-3.5">
            <button
              type="button"
              onClick={() => void logout()}
              className="inline-flex items-center gap-1.5 rounded-xl px-3 py-1.5 text-xs font-semibold text-rose-600 hover:bg-rose-50 transition cursor-pointer"
            >
              <LogOut size={14} />
              Đăng xuất
            </button>
            <button
              type="button"
              onClick={onClose}
              className="rounded-xl bg-slate-900 px-4 py-2 text-xs font-semibold text-white hover:bg-slate-800 transition cursor-pointer"
            >
              Đóng
            </button>
          </div>
        </div>
      </div>

      {/* Change Password Modal */}
      <ChangePasswordModal
        isOpen={isChangePasswordOpen}
        onClose={() => setIsChangePasswordOpen(false)}
        username={user.username}
      />
    </>
  );
};

