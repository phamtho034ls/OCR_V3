import axios from 'axios';
import { AlertCircle, CheckCircle2, Eye, EyeOff, KeyRound, Loader2, X } from 'lucide-react';
import React, { FormEvent, useMemo, useState } from 'react';
import { extractErrorMessage } from '../lib/errorHelper';

interface ChangePasswordModalProps {
  isOpen: boolean;
  onClose: () => void;
  username?: string;
}

export const ChangePasswordModal: React.FC<ChangePasswordModalProps> = ({
  isOpen,
  onClose,
  username,
}) => {
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  // Strength calculation
  const strength = useMemo(() => {
    if (!newPassword) return 0;
    let score = 0;
    if (newPassword.length >= 6) score += 1;
    if (newPassword.length >= 8) score += 1;
    if (/[A-Z]/.test(newPassword) || /[0-9]/.test(newPassword)) score += 1;
    if (/[^A-Za-z0-9]/.test(newPassword)) score += 1;
    return score;
  }, [newPassword]);

  const strengthLabel = useMemo(() => {
    if (strength === 0) return '';
    if (strength <= 1) return 'Yếu';
    if (strength <= 2) return 'Trung bình';
    return 'Mạnh';
  }, [strength]);

  const strengthColor = useMemo(() => {
    if (strength <= 1) return 'bg-rose-500';
    if (strength <= 2) return 'bg-amber-500';
    return 'bg-emerald-500';
  }, [strength]);

  const passwordsMatch = newPassword.length > 0 && newPassword === confirmPassword;

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (newPassword.length < 6) {
      setError('Mật khẩu mới phải có tối thiểu 6 ký tự.');
      return;
    }
    if (newPassword !== confirmPassword) {
      setError('Mật khẩu xác nhận không trùng khớp.');
      return;
    }

    setSaving(true);
    setError(null);

    try {
      await axios.post('/api/v1/auth/change-password', {
        new_password: newPassword,
      });
      setSuccess(true);
      setTimeout(() => {
        handleClose();
      }, 1400);
    } catch (cause: any) {
      setError(await extractErrorMessage(cause));
    } finally {
      setSaving(false);
    }
  };

  const handleClose = () => {
    setNewPassword('');
    setConfirmPassword('');
    setError(null);
    setSuccess(false);
    onClose();
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center bg-slate-950/60 p-4 backdrop-blur-sm animate-in fade-in duration-150">
      <div
        className="w-full max-w-md overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-2xl"
        role="dialog"
        aria-modal="true"
        aria-labelledby="change-password-title"
      >
        {/* Header */}
        <div className="flex items-center justify-between border-b border-slate-100 bg-slate-50/70 px-5 py-4">
          <div className="flex items-center gap-2.5">
            <span className="grid h-9 w-9 place-items-center rounded-xl bg-indigo-600 text-white shadow-sm">
              <KeyRound size={17} />
            </span>
            <div>
              <h3 id="change-password-title" className="text-sm font-bold text-slate-900">
                Đổi mật khẩu
              </h3>
              {username && <p className="text-[11px] text-slate-500 font-mono">@{username}</p>}
            </div>
          </div>
          <button
            type="button"
            onClick={handleClose}
            className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-200/70 hover:text-slate-700 transition cursor-pointer"
          >
            <X size={16} />
          </button>
        </div>

        {/* Content */}
        {success ? (
          <div className="p-8 text-center space-y-2">
            <div className="mx-auto grid h-12 w-12 place-items-center rounded-full bg-emerald-100 text-emerald-600">
              <CheckCircle2 size={26} />
            </div>
            <h4 className="text-sm font-bold text-slate-900">Đổi mật khẩu thành công!</h4>
            <p className="text-xs text-slate-500">Mật khẩu mới đã được cập nhật an toàn.</p>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="p-5 space-y-4">
            {error && (
              <div className="flex items-start gap-2 rounded-xl border border-rose-200 bg-rose-50 p-3 text-xs text-rose-700">
                <AlertCircle size={15} className="mt-0.5 shrink-0 text-rose-600" />
                <span>{error}</span>
              </div>
            )}

            {/* Mật khẩu mới */}
            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                Mật khẩu mới <span className="text-rose-500">*</span>
              </label>
              <div className="relative">
                <input
                  required
                  type={showPassword ? 'text' : 'password'}
                  minLength={6}
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                  placeholder="Tối thiểu 6 ký tự"
                  className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2 pr-9 text-xs outline-none ring-indigo-500 focus:ring-2"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600 cursor-pointer"
                  tabIndex={-1}
                >
                  {showPassword ? <EyeOff size={14} /> : <Eye size={14} />}
                </button>
              </div>

              {/* Password strength bar */}
              {newPassword.length > 0 && (
                <div className="mt-2 flex items-center gap-2">
                  <div className="flex-1 h-1.5 rounded-full bg-slate-100 overflow-hidden flex gap-1">
                    <div className={`h-full flex-1 ${strength >= 1 ? strengthColor : 'bg-slate-200'}`} />
                    <div className={`h-full flex-1 ${strength >= 2 ? strengthColor : 'bg-slate-200'}`} />
                    <div className={`h-full flex-1 ${strength >= 3 ? strengthColor : 'bg-slate-200'}`} />
                  </div>
                  <span className="text-[10px] font-semibold text-slate-500">{strengthLabel}</span>
                </div>
              )}
            </div>

            {/* Xác nhận mật khẩu */}
            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                Nhập lại mật khẩu mới <span className="text-rose-500">*</span>
              </label>
              <div className="relative">
                <input
                  required
                  type={showConfirm ? 'text' : 'password'}
                  minLength={6}
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  placeholder="Nhập lại chính xác mật khẩu"
                  className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2 pr-9 text-xs outline-none ring-indigo-500 focus:ring-2"
                />
                <button
                  type="button"
                  onClick={() => setShowConfirm(!showConfirm)}
                  className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600 cursor-pointer"
                  tabIndex={-1}
                >
                  {showConfirm ? <EyeOff size={14} /> : <Eye size={14} />}
                </button>
              </div>
              {confirmPassword.length > 0 && (
                <p
                  className={`mt-1 text-[11px] font-medium ${
                    passwordsMatch ? 'text-emerald-600' : 'text-rose-600'
                  }`}
                >
                  {passwordsMatch ? '✓ Mật khẩu trùng khớp' : '✕ Mật khẩu chưa trùng khớp'}
                </p>
              )}
            </div>

            {/* Footer buttons */}
            <div className="flex justify-end gap-2.5 pt-3 border-t border-slate-100">
              <button
                type="button"
                onClick={handleClose}
                disabled={saving}
                className="rounded-xl border border-slate-200 px-4 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-50 transition cursor-pointer"
              >
                Hủy
              </button>
              <button
                type="submit"
                disabled={saving || !passwordsMatch}
                className="inline-flex items-center gap-1.5 rounded-xl bg-indigo-600 px-4 py-2 text-xs font-semibold text-white shadow-sm hover:bg-indigo-700 transition disabled:opacity-50 cursor-pointer"
              >
                {saving && <Loader2 size={14} className="animate-spin" />}
                Lưu mật khẩu mới
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
};
