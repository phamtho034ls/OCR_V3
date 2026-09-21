import axios from 'axios';
import {
  AlertCircle,
  AlertTriangle,
  CheckCircle2,
  Database,
  Edit3,
  Eye,
  EyeOff,
  FileSpreadsheet,
  FolderUp,
  Info,
  KeyRound,
  Loader2,
  Lock,
  MapPin,
  Plus,
  RefreshCw,
  Search,
  ShieldCheck,
  Trash2,
  Unlock,
  UserCheck,
  UserCog,
  Users,
  X,
} from 'lucide-react';
import React, { FormEvent, useCallback, useEffect, useMemo, useState } from 'react';
import { useAuth } from '../../shared/auth/AuthProvider';
import { extractErrorMessage } from '../../shared/lib/errorHelper';

interface AppRole {
  name: string;
  label: string;
  description: string;
}

interface ManagedUser {
  id: string;
  username: string;
  first_name: string;
  last_name: string;
  email: string;
  enabled: boolean;
  roles: string[];
  region?: string;
}

const initialForm = {
  username: '',
  first_name: '',
  last_name: '',
  email: '',
  temporary_password: '',
  roles: ['ocr-member'] as string[],
  region: 'Ninh Bình',
};

const USERNAME_REGEX = /^[a-zA-Z0-9._-]+$/;

const generateStrongPassword = () => {
  const chars = 'abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789';
  let rand = '';
  for (let i = 0; i < 6; i++) {
    rand += chars.charAt(Math.floor(Math.random() * chars.length));
  }
  return `Ocr@${rand}!`;
};

const ROLE_DISPLAY: Record<string, { label: string; badge: string; color: string; icon: typeof ShieldCheck }> = {
  'ocr-admin': {
    label: 'Quản trị viên',
    badge: 'bg-rose-50 text-rose-800 border-rose-200',
    color: 'text-rose-600',
    icon: ShieldCheck,
  },
  'ocr-truongphong': {
    label: 'Trưởng phòng',
    badge: 'bg-blue-50 text-blue-800 border-blue-200',
    color: 'text-blue-600',
    icon: UserCog,
  },
  'ocr-member': {
    label: 'Nhân viên',
    badge: 'bg-emerald-50 text-emerald-800 border-emerald-200',
    color: 'text-emerald-600',
    icon: Users,
  },
};

export const UserManagementPage: React.FC = () => {
  const { can, user: currentUser } = useAuth();
  const isCurrentUserRootAdmin = currentUser?.username === 'admin';
  const [roles, setRoles] = useState<AppRole[]>([]);
  const [users, setUsers] = useState<ManagedUser[]>([]);
  const [regions, setRegions] = useState<string[]>(['Ninh Bình', 'Hà Nam', 'Hà Nội', 'Nam Định']);
  const [form, setForm] = useState(initialForm);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [isLocalDev, setIsLocalDev] = useState(false);

  // Search & Filter
  const [searchQuery, setSearchQuery] = useState('');
  const [filterRole, setFilterRole] = useState('all');
  const [filterRegion, setFilterRegion] = useState('all');
  const [filterStatus, setFilterStatus] = useState<'all' | 'active' | 'locked'>('all');

  // Form toggles
  const [showCreatePassword, setShowCreatePassword] = useState(false);

  // Region modal
  const [showAddRegionModal, setShowAddRegionModal] = useState(false);
  const [newRegionName, setNewRegionName] = useState('');
  const [addingRegion, setAddingRegion] = useState(false);
  const [addRegionError, setAddRegionError] = useState<string | null>(null);

  // Modals state
  const [resetModalUser, setResetModalUser] = useState<ManagedUser | null>(null);
  const [newPassword, setNewPassword] = useState('');
  const [requirePasswordChange, setRequirePasswordChange] = useState(true);
  const [showNewPassword, setShowNewPassword] = useState(false);
  const [resetting, setResetting] = useState(false);
  const [resetError, setResetError] = useState<string | null>(null);

  const [editModalUser, setEditModalUser] = useState<ManagedUser | null>(null);
  const [editForm, setEditForm] = useState({ first_name: '', last_name: '', email: '', region: '' });
  const [editing, setEditing] = useState(false);
  const [editError, setEditError] = useState<string | null>(null);

  const [deleteModalUser, setDeleteModalUser] = useState<ManagedUser | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  const [lockModalUser, setLockModalUser] = useState<ManagedUser | null>(null);
  const [locking, setLocking] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [roleResponse, userResponse, regionResponse] = await Promise.all([
        axios.get<{ roles: AppRole[] }>('/api/v1/admin/roles'),
        axios.get<{ users: ManagedUser[]; is_local_dev?: boolean; message?: string }>('/api/v1/admin/users'),
        axios.get<{ regions: string[] }>('/api/v1/admin/regions').catch(() => ({ data: { regions: ['Ninh Bình', 'Hà Nam', 'Hà Nội', 'Nam Định'] } })),
      ]);
      setRoles(roleResponse.data.roles || []);
      setUsers(userResponse.data.users || []);
      if (regionResponse.data?.regions && regionResponse.data.regions.length > 0) {
        setRegions(regionResponse.data.regions);
        setForm((prev) => ({
          ...prev,
          region: currentUser?.username !== 'admin' && currentUser?.region
            ? currentUser.region
            : prev.region || regionResponse.data.regions[0],
        }));
      }
      if (userResponse.data.is_local_dev) {
        setIsLocalDev(true);
      }
    } catch (cause: any) {
      setError(await extractErrorMessage(cause));
    } finally {
      setLoading(false);
    }
  }, []);

  const silentRefresh = useCallback(async () => {
    try {
      const [roleResponse, userResponse, regionResponse] = await Promise.all([
        axios.get<{ roles: AppRole[] }>('/api/v1/admin/roles'),
        axios.get<{ users: ManagedUser[]; is_local_dev?: boolean; message?: string }>('/api/v1/admin/users'),
        axios.get<{ regions: string[] }>('/api/v1/admin/regions').catch(() => ({ data: { regions: [] } })),
      ]);
      if (roleResponse.data?.roles) {
        setRoles(roleResponse.data.roles);
      }
      if (userResponse.data?.users) {
        setUsers(userResponse.data.users);
      }
      if (regionResponse.data?.regions && regionResponse.data.regions.length > 0) {
        setRegions(regionResponse.data.regions);
      }
    } catch {
      // Giữ nguyên dữ liệu hiện tại
    }
  }, []);

  useEffect(() => {
    if (can('user.manage')) void load();
  }, [can, load]);

  const selectFormRole = (role: string) =>
    setForm((current) => ({
      ...current,
      roles: [role],
    }));

  const handleAddRegion = async (e: FormEvent) => {
    e.preventDefault();
    const name = newRegionName.trim();
    if (!name) return;
    setAddingRegion(true);
    setAddRegionError(null);
    try {
      await axios.post('/api/v1/admin/regions', { name });
      setRegions((prev) => (prev.includes(name) ? prev : [...prev, name]));
      setForm((prev) => ({ ...prev, region: name }));
      if (editModalUser) {
        setEditForm((prev) => ({ ...prev, region: name }));
      }
      setNewRegionName('');
      setShowAddRegionModal(false);
      setNotice(`Đã thêm khu vực "${name}" thành công.`);
    } catch (cause: any) {
      setAddRegionError(await extractErrorMessage(cause));
    } finally {
      setAddingRegion(false);
    }
  };

  // Create User
  const createEmployee = async (event: FormEvent) => {
    event.preventDefault();
    if (!USERNAME_REGEX.test(form.username)) {
      setError('Tên đăng nhập chỉ chấp nhận chữ cái, số, dấu chấm (.), gạch dưới (_) hoặc gạch ngang (-).');
      return;
    }
    if (!form.roles || form.roles.length !== 1) {
      setError('Vui lòng chọn 1 vai trò đảm nhiệm duy nhất cho tài khoản.');
      return;
    }
    setSaving(true);
    setError(null);
    setNotice(null);
    try {
      const res = await axios.post<{
        id: string;
        username: string;
        first_name?: string;
        last_name?: string;
        email?: string;
        roles?: string[];
        enabled?: boolean;
        region?: string;
      }>('/api/v1/admin/users', form);

      const created = res.data || {};
      const newUser: ManagedUser = {
        id: created.id || `user_${Date.now()}`,
        username: created.username || form.username,
        first_name: created.first_name !== undefined ? created.first_name : form.first_name,
        last_name: created.last_name !== undefined ? created.last_name : form.last_name,
        email: created.email !== undefined ? created.email : form.email,
        enabled: created.enabled ?? true,
        roles: created.roles && created.roles.length > 0 ? created.roles : form.roles,
        region: created.region !== undefined ? created.region : form.region,
      };

      // Cập nhật ngay lập tức xuống danh sách nhân viên phía dưới
      setUsers((current) => [newUser, ...current.filter((item) => item.id !== newUser.id)]);
      setForm((prev) => ({
        ...initialForm,
        region: prev.region, // Giữ lại khu vực vừa chọn cho thuận tiện
      }));
      setNotice(`Đã tạo tài khoản "${form.username}" thành công.`);

      // Đảm bảo tài khoản mới luôn hiển thị nếu đang lọc role khác
      if (filterRole !== 'all' && !newUser.roles.includes(filterRole)) {
        setFilterRole('all');
      }
      if (filterRegion !== 'all' && newUser.region !== filterRegion) {
        setFilterRegion('all');
      }
      if (searchQuery) {
        setSearchQuery('');
      }

      // Làm mới dữ liệu ngầm để đồng bộ với server mà không hiện spinner che bảng
      void silentRefresh();
    } catch (cause: any) {
      setError(await extractErrorMessage(cause));
    } finally {
      setSaving(false);
    }
  };

  // Replace roles for a user
  const replaceRoles = async (targetUser: ManagedUser, nextRoles: string[]) => {
    setError(null);
    setNotice(null);
    try {
      await axios.put(`/api/v1/admin/users/${encodeURIComponent(targetUser.id)}/roles`, {
        roles: nextRoles,
      });
      setUsers((current) =>
        current.map((item) => (item.id === targetUser.id ? { ...item, roles: nextRoles } : item))
      );
      setNotice(`Đã cập nhật vai trò cho @${targetUser.username}.`);
    } catch (cause: any) {
      setError(await extractErrorMessage(cause));
    }
  };

  // Toggle user enabled/disabled
  const handleToggleEnabled = async () => {
    if (!lockModalUser) return;
    setLocking(true);
    setError(null);
    setNotice(null);
    const targetState = !lockModalUser.enabled;
    try {
      await axios.put(`/api/v1/admin/users/${encodeURIComponent(lockModalUser.id)}/enabled`, {
        enabled: targetState,
      });
      setUsers((current) =>
        current.map((item) => (item.id === lockModalUser.id ? { ...item, enabled: targetState } : item))
      );
      setNotice(
        targetState
          ? `Đã mở khóa tài khoản @${lockModalUser.username}.`
          : `Đã khóa tài khoản @${lockModalUser.username}.`
      );
      setLockModalUser(null);
    } catch (cause: any) {
      setError(await extractErrorMessage(cause));
    } finally {
      setLocking(false);
    }
  };

  // Reset Password
  const handleResetPassword = async (e: FormEvent) => {
    e.preventDefault();
    if (!resetModalUser) return;
    if (newPassword.length < 6) {
      setResetError('Mật khẩu mới phải có tối thiểu 6 ký tự.');
      return;
    }
    setResetting(true);
    setResetError(null);
    try {
      await axios.put(
        `/api/v1/admin/users/${encodeURIComponent(resetModalUser.id)}/reset-password`,
        {
          temporary_password: newPassword,
          temporary: requirePasswordChange,
        }
      );
      setNotice(`Đã đặt lại mật khẩu cho tài khoản @${resetModalUser.username}.`);
      setResetModalUser(null);
      setNewPassword('');
    } catch (cause: any) {
      setResetError(await extractErrorMessage(cause));
    } finally {
      setResetting(false);
    }
  };

  // Edit User
  const handleEditUser = async (e: FormEvent) => {
    e.preventDefault();
    if (!editModalUser) return;
    setEditing(true);
    setEditError(null);
    try {
      await axios.put(`/api/v1/admin/users/${encodeURIComponent(editModalUser.id)}`, editForm);
      setUsers((current) =>
        current.map((item) =>
          item.id === editModalUser.id
            ? {
                ...item,
                first_name: editForm.first_name,
                last_name: editForm.last_name,
                email: editForm.email,
                region: editForm.region,
              }
            : item
        )
      );
      setNotice(`Đã cập nhật thông tin tài khoản @${editModalUser.username}.`);
      setEditModalUser(null);
    } catch (cause: any) {
      setEditError(await extractErrorMessage(cause));
    } finally {
      setEditing(false);
    }
  };

  // Delete User
  const handleDeleteUser = async () => {
    if (!deleteModalUser) return;
    setDeleting(true);
    setDeleteError(null);
    try {
      await axios.delete(`/api/v1/admin/users/${encodeURIComponent(deleteModalUser.id)}`);
      setUsers((current) => current.filter((item) => item.id !== deleteModalUser.id));
      setNotice(`Đã xóa tài khoản @${deleteModalUser.username}.`);
      setDeleteModalUser(null);
    } catch (cause: any) {
      setDeleteError(await extractErrorMessage(cause));
    } finally {
      setDeleting(false);
    }
  };

  // Filtered users
  const filteredUsers = useMemo(() => {
    return users.filter((u) => {
      // Role filter
      if (filterRole !== 'all' && !u.roles.includes(filterRole)) {
        return false;
      }
      // Region filter
      if (filterRegion !== 'all' && (u.region || '') !== filterRegion) {
        return false;
      }
      // Status filter
      if (filterStatus === 'active' && !u.enabled) {
        return false;
      }
      if (filterStatus === 'locked' && u.enabled) {
        return false;
      }
      // Query filter
      if (!searchQuery.trim()) return true;
      const query = searchQuery.toLowerCase().trim();
      const fullName = `${u.last_name} ${u.first_name}`.toLowerCase();
      return (
        u.username.toLowerCase().includes(query) ||
        fullName.includes(query) ||
        (u.email && u.email.toLowerCase().includes(query)) ||
        (u.region && u.region.toLowerCase().includes(query))
      );
    });
  }, [users, filterRole, filterRegion, filterStatus, searchQuery]);

  // Role counts
  const roleStats = useMemo(() => {
    const stats: Record<string, number> = {};
    for (const r of roles) {
      stats[r.name] = users.filter((u) => u.roles.includes(r.name)).length;
    }
    return stats;
  }, [roles, users]);

  if (!can('user.manage')) return null;

  return (
    <div className="space-y-6 pb-12">
      {/* 1. Header Card */}
      <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-center">
        <div className="flex items-center gap-3">
          <span className="grid h-10 w-10 place-items-center rounded-2xl bg-indigo-600 text-white shadow-md shadow-indigo-200">
            <UserCog size={20} />
          </span>
          <div>
            <h2 className="text-base font-bold tracking-tight text-slate-900">
              Quản lý tài khoản & Phân quyền
            </h2>
            <p className="text-xs text-slate-500">
              Cấp tài khoản, phân công vai trò và quản lý quyền truy cập.
            </p>
          </div>
        </div>

        <button
          type="button"
          onClick={() => void load()}
          disabled={loading}
          className="inline-flex items-center justify-center gap-2 rounded-xl border border-slate-200 bg-white px-3.5 py-2 text-xs font-semibold text-slate-700 shadow-sm transition hover:bg-slate-50 active:scale-[0.99] disabled:opacity-60 cursor-pointer"
        >
          <RefreshCw size={13} className={loading ? 'animate-spin' : ''} />
          Làm mới
        </button>
      </div>

      {/* 2. Interactive Role Filter Chips */}
      <div className="flex flex-wrap items-center gap-2">
        <button
          type="button"
          onClick={() => setFilterRole('all')}
          className={`inline-flex items-center gap-2 rounded-xl px-3.5 py-2 text-xs font-semibold transition cursor-pointer border ${
            filterRole === 'all'
              ? 'bg-slate-900 text-white border-slate-900 shadow-sm'
              : 'bg-white text-slate-600 border-slate-200 hover:bg-slate-50'
          }`}
        >
          <span>Tất cả</span>
          <span
            className={`rounded-full px-2 py-0.5 text-[10px] font-bold ${
              filterRole === 'all' ? 'bg-slate-800 text-slate-200' : 'bg-slate-100 text-slate-600'
            }`}
          >
            {users.length}
          </span>
        </button>

        {roles.map((r) => {
          const isSelected = filterRole === r.name;
          const display = ROLE_DISPLAY[r.name] || {
            label: r.label,
            color: 'text-indigo-600',
            icon: ShieldCheck,
          };
          const Icon = display.icon;
          const count = roleStats[r.name] || 0;

          return (
            <button
              key={r.name}
              type="button"
              onClick={() => setFilterRole(isSelected ? 'all' : r.name)}
              className={`inline-flex items-center gap-2 rounded-xl px-3.5 py-2 text-xs font-semibold transition cursor-pointer border ${
                isSelected
                  ? 'bg-indigo-600 text-white border-indigo-600 shadow-sm'
                  : 'bg-white text-slate-700 border-slate-200 hover:bg-slate-50'
              }`}
            >
              <Icon size={14} className={isSelected ? 'text-white' : display.color} />
              <span>{display.label}</span>
              <span
                className={`rounded-full px-2 py-0.5 text-[10px] font-bold ${
                  isSelected ? 'bg-indigo-700 text-indigo-100' : 'bg-slate-100 text-slate-600'
                }`}
              >
                {count}
              </span>
            </button>
          );
        })}
      </div>

      {/* 3. Alerts */}
      {isLocalDev && (
        <div className="flex items-center gap-3 rounded-2xl border border-amber-200 bg-amber-50/90 p-3.5 text-xs text-amber-900">
          <Info size={15} className="shrink-0 text-amber-600" />
          <span><span className="font-bold">Chế độ dev:</span> Đang dùng tài khoản giả lập nội bộ.</span>
        </div>
      )}

      {error && (
        <div className="flex items-start justify-between gap-3 rounded-2xl border border-rose-200 bg-rose-50/90 p-4 text-xs font-medium text-rose-800 shadow-sm">
          <div className="flex items-start gap-2.5">
            <AlertCircle size={17} className="mt-0.5 shrink-0 text-rose-600" />
            <span>{error}</span>
          </div>
          <button
            type="button"
            onClick={() => setError(null)}
            className="rounded-lg p-1 text-rose-500 hover:bg-rose-100 cursor-pointer"
          >
            <X size={14} />
          </button>
        </div>
      )}

      {notice && (
        <div className="flex items-start justify-between gap-3 rounded-2xl border border-emerald-200 bg-emerald-50/90 p-4 text-xs font-medium text-emerald-800 shadow-sm">
          <div className="flex items-start gap-2.5">
            <CheckCircle2 size={17} className="mt-0.5 shrink-0 text-emerald-600" />
            <span>{notice}</span>
          </div>
          <button
            type="button"
            onClick={() => setNotice(null)}
            className="rounded-lg p-1 text-emerald-600 hover:bg-emerald-100 cursor-pointer"
          >
            <X size={14} />
          </button>
        </div>
      )}

      {/* 4. Form Thêm nhân viên mới */}
      <section className="app-card p-5 sm:p-6">
        <div className="mb-4 flex items-center gap-2">
          <span className="grid h-7 w-7 place-items-center rounded-lg bg-emerald-100 text-emerald-700">
            <Plus size={15} />
          </span>
          <div>
            <h3 className="text-sm font-bold text-slate-900">Thêm tài khoản mới</h3>
          </div>
        </div>

        <form onSubmit={createEmployee} className="space-y-4">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                Tên đăng nhập <span className="text-rose-500">*</span>
              </label>
              <input
                required
                minLength={3}
                value={form.username}
                onChange={(e) => setForm({ ...form, username: e.target.value })}
                placeholder="nguyen.van.a"
                className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs outline-none ring-indigo-500 focus:ring-2"
              />
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">Họ & tên đệm</label>
              <input
                value={form.last_name}
                onChange={(e) => setForm({ ...form, last_name: e.target.value })}
                placeholder="Nguyễn Văn"
                className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs outline-none ring-indigo-500 focus:ring-2"
              />
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">Tên</label>
              <input
                value={form.first_name}
                onChange={(e) => setForm({ ...form, first_name: e.target.value })}
                placeholder="An"
                className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs outline-none ring-indigo-500 focus:ring-2"
              />
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">Email</label>
              <input
                type="email"
                value={form.email}
                onChange={(e) => setForm({ ...form, email: e.target.value })}
                placeholder="an.nv@donvi.gov.vn"
                className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs outline-none ring-indigo-500 focus:ring-2"
              />
            </div>

            <div>
              <div className="flex items-center justify-between mb-1">
                <label className="block text-xs font-semibold text-slate-700">
                  Mật khẩu khởi tạo <span className="text-rose-500">*</span>
                </label>
                <button
                  type="button"
                  onClick={() => setForm((prev) => ({ ...prev, temporary_password: generateStrongPassword() }))}
                  className="text-[10px] text-indigo-600 hover:text-indigo-800 font-medium cursor-pointer"
                  title="Tạo mật khẩu mạnh ngẫu nhiên"
                >
                  Tạo mật khẩu
                </button>
              </div>
              <div className="relative">
                <input
                  required
                  type={showCreatePassword ? 'text' : 'password'}
                  minLength={6}
                  autoComplete="new-password"
                  placeholder="Ví dụ: Ocr@Sodo2026!"
                  value={form.temporary_password}
                  onChange={(e) => setForm({ ...form, temporary_password: e.target.value })}
                  className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2 pr-9 text-xs outline-none ring-indigo-500 focus:ring-2 font-mono"
                />
                <button
                  type="button"
                  onClick={() => setShowCreatePassword(!showCreatePassword)}
                  className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600 cursor-pointer"
                  tabIndex={-1}
                >
                  {showCreatePassword ? <EyeOff size={14} /> : <Eye size={14} />}
                </button>
              </div>
            </div>

            <div>
              <div className="flex items-center justify-between mb-1">
                <label className="block text-xs font-semibold text-slate-700">
                  Khu vực <span className="text-rose-500">*</span>
                </label>
                {isCurrentUserRootAdmin && (
                  <button
                    type="button"
                    onClick={() => {
                      setAddRegionError(null);
                      setNewRegionName('');
                      setShowAddRegionModal(true);
                    }}
                    className="text-[11px] text-indigo-600 hover:text-indigo-800 font-medium cursor-pointer"
                  >
                    + Thêm mới
                  </button>
                )}
              </div>
              {isCurrentUserRootAdmin ? (
                <select
                  value={form.region}
                  onChange={(e) => setForm({ ...form, region: e.target.value })}
                  className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs outline-none ring-indigo-500 focus:ring-2"
                >
                  {regions.map((reg) => (
                    <option key={reg} value={reg}>
                      {reg}
                    </option>
                  ))}
                </select>
              ) : (
                <input
                  type="text"
                  readOnly
                  disabled
                  value={currentUser?.region || form.region || 'Chưa phân khu vực'}
                  className="w-full rounded-xl border border-slate-200 bg-slate-100 px-3 py-2 text-xs font-medium text-slate-700 cursor-not-allowed"
                />
              )}
            </div>
          </div>

          <div>
            <label className="block text-xs font-semibold text-slate-700 mb-2">
              Vai trò đảm nhiệm <span className="text-rose-500">*</span>
            </label>
            <div className="flex flex-wrap gap-2">
              {roles.map((r) => {
                const isSelected = form.roles[0] === r.name;
                const display = ROLE_DISPLAY[r.name] || { label: r.label, icon: ShieldCheck };
                const Icon = display.icon;
                return (
                  <label
                    key={r.name}
                    className={`inline-flex items-center gap-2 cursor-pointer rounded-xl border px-3.5 py-2 text-xs transition shadow-xs select-none ${
                      isSelected
                        ? 'border-indigo-500 bg-indigo-50/90 text-indigo-900 font-semibold ring-1 ring-indigo-500'
                        : 'border-slate-200 bg-white text-slate-600 hover:bg-slate-50'
                    }`}
                  >
                    <input
                      type="radio"
                      name="account_role"
                      checked={isSelected}
                      onChange={() => selectFormRole(r.name)}
                      className="accent-indigo-600"
                    />
                    <Icon size={14} className={isSelected ? 'text-indigo-600' : 'text-slate-400'} />
                    <span>{display.label}</span>
                  </label>
                );
              })}
            </div>
          </div>

          <div className="pt-2">
            <button
              type="submit"
              disabled={saving}
              className="inline-flex items-center gap-2 rounded-xl bg-slate-900 px-4 py-2.5 text-xs font-semibold text-white shadow-sm transition hover:bg-slate-800 active:scale-[0.99] disabled:opacity-60 cursor-pointer"
            >
              {saving ? <Loader2 size={15} className="animate-spin" /> : <Plus size={15} />}
              Tạo tài khoản
            </button>
          </div>
        </form>
      </section>

      {/* 5. Table Danh sách nhân viên */}
      <section className="app-card overflow-hidden">
        {/* Table Toolbar */}
        <div className="flex flex-col gap-3 border-b border-slate-100 bg-slate-50/60 p-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-2">
            <Users size={17} className="text-indigo-600" />
            <h3 className="text-sm font-bold text-slate-900">Danh sách nhân viên</h3>
            <span className="rounded-full bg-slate-200/80 px-2 py-0.5 text-[11px] font-semibold text-slate-600">
              {filteredUsers.length} tài khoản
            </span>
          </div>

          {/* Filters & Search box */}
          <div className="flex flex-wrap items-center gap-2.5">
            {/* Region Filter */}
            {isCurrentUserRootAdmin ? (
              <div className="flex items-center gap-1.5">
                <span className="text-[11px] text-slate-500 font-medium whitespace-nowrap">Khu vực:</span>
                <select
                  value={filterRegion}
                  onChange={(e) => setFilterRegion(e.target.value)}
                  className="rounded-xl border border-slate-200 bg-white py-1.5 px-2.5 text-xs outline-none ring-indigo-500 focus:ring-2 text-slate-700 font-medium cursor-pointer"
                >
                  <option value="all">Tất cả khu vực</option>
                  {regions.map((reg) => (
                    <option key={reg} value={reg}>
                      {reg}
                    </option>
                  ))}
                </select>
              </div>
            ) : (
              currentUser?.region ? (
                <span className="text-[11px] text-indigo-700 font-semibold bg-indigo-50 border border-indigo-100 px-2.5 py-1 rounded-xl">
                  Khu vực: {currentUser.region}
                </span>
              ) : null
            )}

            {/* Status Filter */}
            <div className="flex items-center gap-1.5">
              <span className="text-[11px] text-slate-500 font-medium whitespace-nowrap">Trạng thái:</span>
              <select
                value={filterStatus}
                onChange={(e) => setFilterStatus(e.target.value as 'all' | 'active' | 'locked')}
                className="rounded-xl border border-slate-200 bg-white py-1.5 px-2.5 text-xs outline-none ring-indigo-500 focus:ring-2 text-slate-700 font-medium cursor-pointer"
              >
                <option value="all">Tất cả trạng thái</option>
                <option value="active">Hoạt động</option>
                <option value="locked">Đã khóa</option>
              </select>
            </div>

            {/* Search box */}
            <div className="relative min-w-[220px]">
              <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
              <input
                type="text"
                placeholder="Tìm tên, tài khoản, email..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full rounded-xl border border-slate-200 bg-white py-1.5 pl-8 pr-3 text-xs outline-none ring-indigo-500 focus:ring-2"
              />
              {searchQuery && (
                <button
                  type="button"
                  onClick={() => setSearchQuery('')}
                  className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600 cursor-pointer"
                >
                  <X size={12} />
                </button>
              )}
            </div>
          </div>
        </div>

        {/* Content */}
        {loading ? (
          <div className="flex items-center justify-center gap-2 py-16 text-xs text-slate-400">
            <Loader2 size={16} className="animate-spin text-indigo-500" />
            Đang tải...
          </div>
        ) : filteredUsers.length === 0 ? (
          <div className="py-12 text-center text-xs text-slate-400">
            {searchQuery || filterRole !== 'all' || filterRegion !== 'all'
              ? 'Không tìm thấy tài khoản phù hợp.'
              : 'Chưa có tài khoản nào.'}
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full text-left text-xs">
              <thead className="bg-slate-50 text-slate-500 border-b border-slate-100">
                <tr>
                  <th className="px-5 py-3 font-semibold">Nhân viên</th>
                  <th className="px-5 py-3 font-semibold">Khu vực</th>
                  <th className="px-5 py-3 font-semibold">Vai trò đảm nhiệm</th>
                  <th className="px-5 py-3 font-semibold">Trạng thái</th>
                  <th className="px-5 py-3 text-right font-semibold">Thao tác</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {filteredUsers.map((user) => {
                  const isSelf =
                    currentUser?.id === user.id || currentUser?.username === user.username;
                  const fullName = [user.last_name, user.first_name].filter(Boolean).join(' ');
                  const initials = (fullName || user.username).slice(0, 2).toUpperCase();

                  const isCurrentUserRootAdmin = currentUser?.username === 'admin';
                  const isRowRootAdmin = user.username === 'admin';
                  const isRowAdmin = user.roles.includes('ocr-admin');

                  // 1. Root admin gốc không bao giờ bị xóa
                  // 2. Không được tự xóa tài khoản của chính mình
                  // 3. Tài khoản quản trị viên sau này không được xóa nhau, chỉ admin gốc mới xóa được
                  const canDelete = !isSelf && !isRowRootAdmin && (!isRowAdmin || isCurrentUserRootAdmin);
                  const deleteTooltip = isSelf
                    ? 'Không thể xóa tài khoản của chính mình'
                    : isRowRootAdmin
                    ? 'Không thể xóa tài khoản Quản trị viên gốc của hệ thống'
                    : isRowAdmin && !isCurrentUserRootAdmin
                    ? 'Chỉ tài khoản admin tổng mới có quyền xóa Quản trị viên'
                    : 'Xóa tài khoản';

                  return (
                    <tr
                      key={user.id}
                      className={`transition-colors ${
                        user.enabled
                          ? 'hover:bg-slate-50/60'
                          : 'bg-slate-50/40 opacity-75 hover:bg-slate-100/60'
                      }`}
                    >
                      {/* Name & User */}
                      <td className="px-5 py-3.5">
                        <div className="flex items-center gap-3">
                          <div className="grid h-8 w-8 shrink-0 place-items-center rounded-xl bg-slate-100 text-xs font-bold text-slate-700">
                            {initials}
                          </div>
                          <div>
                            <div className="flex items-center gap-1.5">
                              <span className="font-semibold text-slate-900">
                                {fullName || user.username}
                              </span>
                              {isSelf && (
                                <span className="rounded-md bg-indigo-50 px-1.5 py-0.5 text-[10px] font-bold text-indigo-700 border border-indigo-200">
                                  Bạn
                                </span>
                              )}
                            </div>
                            <p className="mt-0.5 text-[11px] text-slate-500 font-mono">
                              @{user.username}
                              {user.email ? ` · ${user.email}` : ''}
                            </p>
                          </div>
                        </div>
                      </td>

                      {/* Region */}
                      <td className="px-5 py-3.5">
                        {user.region ? (
                          <span className="inline-flex items-center gap-1 rounded-lg bg-indigo-50/70 border border-indigo-100/80 px-2.5 py-1 text-[11px] font-semibold text-indigo-800">
                            <MapPin size={12} className="text-indigo-600" />
                            {user.region}
                          </span>
                        ) : (
                          <span className="text-[11px] text-slate-400 italic">—</span>
                        )}
                      </td>

                      {/* Roles */}
                      <td className="px-5 py-3.5">
                        {user.roles.includes('ocr-admin') ? (
                          <div className="flex items-center">
                            <span className="inline-flex items-center gap-1.5 rounded-lg border border-rose-200 bg-rose-50 px-2.5 py-1 text-[11px] font-semibold text-rose-800">
                              <ShieldCheck size={13} className="text-rose-600" />
                              Quản trị viên
                            </span>
                          </div>
                        ) : (
                          <div className="flex min-w-[190px] flex-wrap gap-1.5">
                            {roles
                              .filter((r) => r.name !== 'ocr-admin')
                              .map((r) => {
                                const isAssigned = user.roles.includes(r.name);
                                const display = ROLE_DISPLAY[r.name] || {
                                  label: r.label,
                                  badge: 'bg-indigo-50 text-indigo-800 border-indigo-200',
                                };

                                return (
                                  <button
                                    key={r.name}
                                    type="button"
                                    onClick={() => {
                                      if (!isAssigned) {
                                        void replaceRoles(user, [r.name]);
                                      }
                                    }}
                                    className={`rounded-lg border px-2.5 py-1 text-[11px] transition select-none cursor-pointer ${
                                      isAssigned
                                        ? `${display.badge} font-semibold shadow-xs`
                                        : 'border-slate-200 bg-white text-slate-400 hover:border-slate-300 hover:text-slate-600 hover:bg-slate-50'
                                    }`}
                                  >
                                    {display.label}
                                  </button>
                                );
                              })}
                          </div>
                        )}
                      </td>

                      {/* Status */}
                      <td className="px-5 py-3.5">
                        {user.enabled ? (
                          <span className="inline-flex items-center gap-1.5 rounded-full bg-emerald-50 px-2.5 py-0.5 text-[11px] font-semibold text-emerald-700 border border-emerald-200">
                            <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
                            Hoạt động
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1.5 rounded-full bg-rose-50 px-2.5 py-0.5 text-[11px] font-semibold text-rose-700 border border-rose-200">
                            <span className="h-1.5 w-1.5 rounded-full bg-rose-500" />
                            Đã khóa
                          </span>
                        )}
                      </td>

                      {/* Actions */}
                      <td className="px-5 py-3.5 text-right">
                        <div className="inline-flex items-center gap-1">
                          <button
                            type="button"
                            title="Đặt lại mật khẩu"
                            onClick={() => {
                              setResetModalUser(user);
                              setNewPassword('');
                              setResetError(null);
                              setRequirePasswordChange(true);
                            }}
                            className="rounded-lg border border-slate-200 p-1.5 text-slate-600 hover:bg-slate-100 hover:text-slate-900 transition cursor-pointer"
                          >
                            <KeyRound size={14} />
                          </button>

                          <button
                            type="button"
                            title="Sửa thông tin"
                            onClick={() => {
                              setEditModalUser(user);
                              setEditForm({
                                first_name: user.first_name || '',
                                last_name: user.last_name || '',
                                email: user.email || '',
                                region: user.region || '',
                              });
                              setEditError(null);
                            }}
                            className="rounded-lg border border-slate-200 p-1.5 text-slate-600 hover:bg-slate-100 hover:text-slate-900 transition cursor-pointer"
                          >
                            <Edit3 size={14} />
                          </button>

                          {!isRowRootAdmin && (
                            <button
                              type="button"
                              title={
                                isSelf
                                  ? 'Không thể khóa tài khoản của chính mình'
                                  : user.enabled
                                  ? 'Khóa tài khoản'
                                  : 'Mở khóa tài khoản'
                              }
                              disabled={isSelf}
                              onClick={() => setLockModalUser(user)}
                              className={`rounded-lg border p-1.5 transition cursor-pointer ${
                                isSelf
                                  ? 'opacity-40 border-slate-200 text-slate-400 cursor-not-allowed'
                                  : user.enabled
                                  ? 'border-amber-200 text-amber-700 hover:bg-amber-50'
                                  : 'border-emerald-200 text-emerald-700 hover:bg-emerald-50'
                              }`}
                            >
                              {user.enabled ? <Lock size={14} /> : <Unlock size={14} />}
                            </button>
                          )}

                          <button
                            type="button"
                            title={deleteTooltip}
                            disabled={!canDelete}
                            onClick={() => {
                              if (!canDelete) return;
                              setDeleteModalUser(user);
                              setDeleteError(null);
                            }}
                            className={`rounded-lg border p-1.5 transition cursor-pointer ${
                              !canDelete
                                ? 'opacity-40 border-slate-200 text-slate-400 cursor-not-allowed'
                                : 'border-rose-200 text-rose-700 hover:bg-rose-50'
                            }`}
                          >
                            <Trash2 size={14} />
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {/* MODAL 1: Đặt lại mật khẩu */}
      {resetModalUser && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/60 p-4 backdrop-blur-sm animate-in fade-in duration-150">
          <div className="w-full max-w-md overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-2xl">
            <div className="flex items-center justify-between border-b border-slate-100 bg-slate-50/70 px-5 py-4">
              <div className="flex items-center gap-2">
                <span className="grid h-8 w-8 place-items-center rounded-lg bg-indigo-100 text-indigo-700">
                  <KeyRound size={16} />
                </span>
                <div>
                  <h4 className="text-sm font-bold text-slate-900">Đặt lại mật khẩu</h4>
                  <p className="text-[11px] text-slate-500 font-mono">@{resetModalUser.username}</p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setResetModalUser(null)}
                className="rounded-lg p-1 text-slate-400 hover:bg-slate-200/70 hover:text-slate-700 cursor-pointer"
              >
                <X size={16} />
              </button>
            </div>

            <form onSubmit={handleResetPassword} className="p-5 space-y-4">
              {resetError && (
                <div className="flex items-start gap-2 rounded-xl border border-rose-200 bg-rose-50 p-3 text-xs text-rose-700">
                  <AlertCircle size={15} className="mt-0.5 shrink-0" />
                  <span>{resetError}</span>
                </div>
              )}

              <div>
                <div className="flex items-center justify-between mb-1">
                  <label className="block text-xs font-semibold text-slate-700">
                    Mật khẩu mới <span className="text-rose-500">*</span>
                  </label>
                  <button
                    type="button"
                    onClick={() => setNewPassword(generateStrongPassword())}
                    className="text-[10px] text-indigo-600 hover:text-indigo-800 font-medium cursor-pointer"
                    title="Tạo mật khẩu mạnh ngẫu nhiên"
                  >
                    Tạo mật khẩu
                  </button>
                </div>
                <div className="relative">
                  <input
                    required
                    type={showNewPassword ? 'text' : 'password'}
                    minLength={6}
                    autoComplete="new-password"
                    placeholder="Ví dụ: Ocr@Sodo2026!"
                    value={newPassword}
                    onChange={(e) => setNewPassword(e.target.value)}
                    className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2 pr-9 text-xs outline-none ring-indigo-500 focus:ring-2 font-mono"
                  />
                  <button
                    type="button"
                    onClick={() => setShowNewPassword(!showNewPassword)}
                    className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600 cursor-pointer"
                    tabIndex={-1}
                  >
                    {showNewPassword ? <EyeOff size={14} /> : <Eye size={14} />}
                  </button>
                </div>
              </div>

              <label className="flex items-center gap-2 text-xs text-slate-700 cursor-pointer select-none">
                <input
                  type="checkbox"
                  checked={requirePasswordChange}
                  onChange={(e) => setRequirePasswordChange(e.target.checked)}
                  className="accent-indigo-600 rounded"
                />
                <span>Yêu cầu đổi mật khẩu ở lần đăng nhập tiếp theo</span>
              </label>

              <div className="flex justify-end gap-2.5 pt-2 border-t border-slate-100">
                <button
                  type="button"
                  onClick={() => setResetModalUser(null)}
                  disabled={resetting}
                  className="rounded-xl border border-slate-200 px-4 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-50 cursor-pointer"
                >
                  Hủy
                </button>
                <button
                  type="submit"
                  disabled={resetting}
                  className="inline-flex items-center gap-1.5 rounded-xl bg-indigo-600 px-4 py-2 text-xs font-semibold text-white shadow hover:bg-indigo-700 disabled:opacity-60 cursor-pointer"
                >
                  {resetting && <Loader2 size={14} className="animate-spin" />}
                  Lưu mật khẩu mới
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* MODAL 2: Sửa thông tin */}
      {editModalUser && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/60 p-4 backdrop-blur-sm animate-in fade-in duration-150">
          <div className="w-full max-w-md overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-2xl">
            <div className="flex items-center justify-between border-b border-slate-100 bg-slate-50/70 px-5 py-4">
              <div className="flex items-center gap-2">
                <span className="grid h-8 w-8 place-items-center rounded-lg bg-blue-100 text-blue-700">
                  <Edit3 size={16} />
                </span>
                <div>
                  <h4 className="text-sm font-bold text-slate-900">Sửa thông tin nhân viên</h4>
                  <p className="text-[11px] text-slate-500 font-mono">@{editModalUser.username}</p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setEditModalUser(null)}
                className="rounded-lg p-1 text-slate-400 hover:bg-slate-200/70 hover:text-slate-700 cursor-pointer"
              >
                <X size={16} />
              </button>
            </div>

            <form onSubmit={handleEditUser} className="p-5 space-y-3.5">
              {editError && (
                <div className="flex items-start gap-2 rounded-xl border border-rose-200 bg-rose-50 p-3 text-xs text-rose-700">
                  <AlertCircle size={15} className="mt-0.5 shrink-0" />
                  <span>{editError}</span>
                </div>
              )}

              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">Họ & tên đệm</label>
                <input
                  value={editForm.last_name}
                  onChange={(e) => setEditForm({ ...editForm, last_name: e.target.value })}
                  placeholder="Nguyễn Văn"
                  className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs outline-none ring-indigo-500 focus:ring-2"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">Tên</label>
                <input
                  value={editForm.first_name}
                  onChange={(e) => setEditForm({ ...editForm, first_name: e.target.value })}
                  placeholder="An"
                  className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs outline-none ring-indigo-500 focus:ring-2"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">Email</label>
                <input
                  type="email"
                  value={editForm.email}
                  onChange={(e) => setEditForm({ ...editForm, email: e.target.value })}
                  placeholder="an.nv@donvi.gov.vn"
                  className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs outline-none ring-indigo-500 focus:ring-2"
                />
              </div>

              <div>
                <div className="flex items-center justify-between mb-1">
                  <label className="block text-xs font-semibold text-slate-700">Khu vực</label>
                  <button
                    type="button"
                    onClick={() => {
                      setAddRegionError(null);
                      setNewRegionName('');
                      setShowAddRegionModal(true);
                    }}
                    className="text-[11px] text-indigo-600 hover:text-indigo-800 font-medium cursor-pointer"
                  >
                    + Thêm mới
                  </button>
                </div>
                <select
                  value={editForm.region}
                  onChange={(e) => setEditForm({ ...editForm, region: e.target.value })}
                  className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs outline-none ring-indigo-500 focus:ring-2"
                >
                  <option value="">-- Chưa phân khu vực --</option>
                  {regions.map((reg) => (
                    <option key={reg} value={reg}>
                      {reg}
                    </option>
                  ))}
                </select>
              </div>

              <div className="flex justify-end gap-2.5 pt-2 border-t border-slate-100">
                <button
                  type="button"
                  onClick={() => setEditModalUser(null)}
                  disabled={editing}
                  className="rounded-xl border border-slate-200 px-4 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-50 cursor-pointer"
                >
                  Hủy
                </button>
                <button
                  type="submit"
                  disabled={editing}
                  className="inline-flex items-center gap-1.5 rounded-xl bg-indigo-600 px-4 py-2 text-xs font-semibold text-white shadow hover:bg-indigo-700 disabled:opacity-60 cursor-pointer"
                >
                  {editing && <Loader2 size={14} className="animate-spin" />}
                  Cập nhật
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* MODAL 3: Khóa / Mở lại tài khoản */}
      {lockModalUser && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/60 p-4 backdrop-blur-sm animate-in fade-in duration-150">
          <div className="w-full max-w-md overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-2xl p-5 space-y-4">
            <div className="flex items-center gap-3">
              <span
                className={`grid h-10 w-10 place-items-center rounded-xl ${
                  lockModalUser.enabled ? 'bg-amber-100 text-amber-700' : 'bg-emerald-100 text-emerald-700'
                }`}
              >
                {lockModalUser.enabled ? <Lock size={20} /> : <Unlock size={20} />}
              </span>
              <div>
                <h4 className="text-sm font-bold text-slate-900">
                  {lockModalUser.enabled ? 'Khóa tài khoản' : 'Mở khóa tài khoản'}
                </h4>
                <p className="text-xs text-slate-500 font-mono">@{lockModalUser.username}</p>
              </div>
            </div>

            <p className="text-xs text-slate-600 leading-relaxed">
              {lockModalUser.enabled
                ? `Bạn có chắc chắn muốn khóa tài khoản @${lockModalUser.username}? Người dùng này sẽ tạm thời không thể đăng nhập vào hệ thống.`
                : `Bạn có muốn mở khóa tài khoản @${lockModalUser.username} để nhân viên tiếp tục sử dụng hệ thống?`}
            </p>

            <div className="flex justify-end gap-2.5 pt-2 border-t border-slate-100">
              <button
                type="button"
                onClick={() => setLockModalUser(null)}
                disabled={locking}
                className="rounded-xl border border-slate-200 px-4 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-50 cursor-pointer"
              >
                Hủy
              </button>
              <button
                type="button"
                onClick={() => void handleToggleEnabled()}
                disabled={locking}
                className={`inline-flex items-center gap-1.5 rounded-xl px-4 py-2 text-xs font-semibold text-white shadow cursor-pointer ${
                  lockModalUser.enabled
                    ? 'bg-amber-600 hover:bg-amber-700'
                    : 'bg-emerald-600 hover:bg-emerald-700'
                }`}
              >
                {locking && <Loader2 size={14} className="animate-spin" />}
                {lockModalUser.enabled ? 'Xác nhận khóa' : 'Xác nhận mở lại'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* MODAL 4: Xóa tài khoản */}
      {deleteModalUser && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/60 p-4 backdrop-blur-sm animate-in fade-in duration-150">
          <div className="w-full max-w-md overflow-hidden rounded-2xl border border-rose-200 bg-white shadow-2xl p-5 space-y-4">
            <div className="flex items-center gap-3">
              <span className="grid h-10 w-10 place-items-center rounded-xl bg-rose-100 text-rose-700">
                <AlertTriangle size={20} />
              </span>
              <div>
                <h4 className="text-sm font-bold text-slate-900">Xác nhận xóa tài khoản</h4>
                <p className="text-xs text-slate-500 font-mono">@{deleteModalUser.username}</p>
              </div>
            </div>

            {deleteError && (
              <div className="flex items-start gap-2 rounded-xl border border-rose-200 bg-rose-50 p-3 text-xs text-rose-700">
                <AlertCircle size={15} className="mt-0.5 shrink-0" />
                <span>{deleteError}</span>
              </div>
            )}

            <p className="text-xs text-slate-600 leading-relaxed">
              Bạn có chắc chắn muốn xóa tài khoản <strong className="text-slate-900">@{deleteModalUser.username}</strong>?
              Hành động này sẽ xóa hoàn toàn tài khoản khỏi hệ thống và <strong className="text-rose-700">không thể khôi phục</strong>.
            </p>

            <div className="flex justify-end gap-2.5 pt-2 border-t border-slate-100">
              <button
                type="button"
                onClick={() => setDeleteModalUser(null)}
                disabled={deleting}
                className="rounded-xl border border-slate-200 px-4 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-50 cursor-pointer"
              >
                Hủy
              </button>
              <button
                type="button"
                onClick={() => void handleDeleteUser()}
                disabled={deleting}
                className="inline-flex items-center gap-1.5 rounded-xl bg-rose-600 px-4 py-2 text-xs font-semibold text-white shadow hover:bg-rose-700 disabled:opacity-60 cursor-pointer"
              >
                {deleting && <Loader2 size={14} className="animate-spin" />}
                Xóa tài khoản
              </button>
            </div>
          </div>
        </div>
      )}

      {/* MODAL 5: Thêm khu vực mới */}
      {showAddRegionModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/60 p-4 backdrop-blur-sm animate-in fade-in duration-150">
          <div className="w-full max-w-md overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-2xl">
            <div className="flex items-center justify-between border-b border-slate-100 bg-slate-50/70 px-5 py-4">
              <div className="flex items-center gap-2">
                <span className="grid h-8 w-8 place-items-center rounded-lg bg-indigo-100 text-indigo-700">
                  <MapPin size={16} />
                </span>
                <h4 className="text-sm font-bold text-slate-900">Thêm khu vực mới</h4>
              </div>
              <button
                type="button"
                onClick={() => setShowAddRegionModal(false)}
                className="rounded-lg p-1 text-slate-400 hover:bg-slate-200/70 hover:text-slate-700 cursor-pointer"
              >
                <X size={16} />
              </button>
            </div>

            <form onSubmit={handleAddRegion} className="p-5 space-y-4">
              {addRegionError && (
                <div className="flex items-start gap-2 rounded-xl border border-rose-200 bg-rose-50 p-3 text-xs text-rose-700">
                  <AlertCircle size={15} className="mt-0.5 shrink-0" />
                  <span>{addRegionError}</span>
                </div>
              )}

              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">
                  Tên khu vực <span className="text-rose-500">*</span>
                </label>
                <input
                  required
                  placeholder="Ví dụ: Ninh Bình, Hà Nam, Thái Bình,..."
                  value={newRegionName}
                  onChange={(e) => setNewRegionName(e.target.value)}
                  className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs outline-none ring-indigo-500 focus:ring-2"
                  autoFocus
                />
              </div>

              <div className="flex justify-end gap-2.5 pt-2 border-t border-slate-100">
                <button
                  type="button"
                  onClick={() => setShowAddRegionModal(false)}
                  disabled={addingRegion}
                  className="rounded-xl border border-slate-200 px-4 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-50 cursor-pointer"
                >
                  Hủy
                </button>
                <button
                  type="submit"
                  disabled={addingRegion || !newRegionName.trim()}
                  className="inline-flex items-center gap-1.5 rounded-xl bg-indigo-600 px-4 py-2 text-xs font-semibold text-white shadow hover:bg-indigo-700 disabled:opacity-60 cursor-pointer"
                >
                  {addingRegion && <Loader2 size={14} className="animate-spin" />}
                  Thêm khu vực
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
