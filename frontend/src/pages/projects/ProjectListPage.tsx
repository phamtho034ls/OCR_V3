/**
 * Trang quản lý dự án OCR.
 * - admin/truong_phong: tạo dự án, thêm thành viên
 * - member: xem danh sách dự án được giao
 */
import axios from 'axios';
import {
  AlertCircle,
  CheckCircle2,
  FolderPlus,
  Loader2,
  Plus,
  RefreshCw,
  Trash2,
  UserPlus,
  Users,
  X,
} from 'lucide-react';
import React, { FormEvent, useCallback, useEffect, useState } from 'react';
import { useAuth } from '../../shared/auth/AuthProvider';
import { extractErrorMessage } from '../../shared/lib/errorHelper';

interface Project {
  project_id: string;
  project_name: string;
  description?: string;
  created_by: string;
  status: string;
  created_at: string;
}

interface Member {
  user_id: string;
  username: string;
  display_name?: string;
  role_in_project: string;
  added_at: string;
}

export const ProjectListPage: React.FC = () => {
  const { can, user } = useAuth();
  const canCreate = can('project.create');
  const canManage = can('project.manage');

  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  // Create project form
  const [showCreate, setShowCreate] = useState(false);
  const [createName, setCreateName] = useState('');
  const [createDesc, setCreateDesc] = useState('');
  const [creating, setCreating] = useState(false);

  // Member management
  const [selectedProject, setSelectedProject] = useState<Project | null>(null);
  const [members, setMembers] = useState<Member[]>([]);
  const [loadingMembers, setLoadingMembers] = useState(false);
  const [allUsers, setAllUsers] = useState<any[]>([]);
  const [addUserId, setAddUserId] = useState('');
  const [addRole, setAddRole] = useState<'member' | 'truong_phong'>('member');
  const [addingMember, setAddingMember] = useState(false);

  const loadProjects = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await axios.get('/api/v1/projects?limit=200');
      setProjects(res.data?.projects ?? []);
    } catch (e: any) {
      setError(await extractErrorMessage(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void loadProjects(); }, [loadProjects]);

  const handleCreateProject = async (e: FormEvent) => {
    e.preventDefault();
    if (!createName.trim()) return;
    setCreating(true);
    try {
      await axios.post('/api/v1/projects', {
        project_name: createName.trim(),
        description: createDesc.trim() || null,
      });
      setNotice(`Dự án '${createName.trim()}' đã được tạo.`);
      setCreateName('');
      setCreateDesc('');
      setShowCreate(false);
      await loadProjects();
    } catch (e: any) {
      setError(await extractErrorMessage(e));
    } finally {
      setCreating(false);
    }
  };

  const handleDeleteProject = async (p: Project) => {
    if (!window.confirm(`Xóa dự án '${p.project_name}'? Dữ liệu liên quan sẽ bị xóa.`)) return;
    try {
      await axios.delete(`/api/v1/projects/${p.project_id}`);
      setNotice(`Đã xóa dự án '${p.project_name}'.`);
      await loadProjects();
    } catch (e: any) {
      setError(await extractErrorMessage(e));
    }
  };

  const openMemberPanel = async (p: Project) => {
    setSelectedProject(p);
    setLoadingMembers(true);
    try {
      const [memRes, usrRes] = await Promise.all([
        axios.get(`/api/v1/projects/${p.project_id}/members`),
        can('user.manage') ? axios.get('/api/v1/admin/users') : Promise.resolve({ data: { users: [] } }),
      ]);
      setMembers(memRes.data?.members ?? []);
      setAllUsers(usrRes.data?.users ?? []);
    } catch (e: any) {
      setError(await extractErrorMessage(e));
    } finally {
      setLoadingMembers(false);
    }
  };

  const handleAddMember = async (e: FormEvent) => {
    e.preventDefault();
    if (!selectedProject || !addUserId) return;
    setAddingMember(true);
    try {
      const selectedUser = allUsers.find((u) => u.id === addUserId);
      await axios.post(`/api/v1/projects/${selectedProject.project_id}/members`, {
        user_id: addUserId,
        username: selectedUser?.username ?? addUserId,
        display_name: selectedUser
          ? `${selectedUser.first_name || ''} ${selectedUser.last_name || ''}`.trim() || selectedUser.username
          : addUserId,
        role_in_project: addRole,
      });
      setNotice('Thêm thành viên thành công.');
      const memRes = await axios.get(`/api/v1/projects/${selectedProject.project_id}/members`);
      setMembers(memRes.data?.members ?? []);
      setAddUserId('');
    } catch (e: any) {
      setError(await extractErrorMessage(e));
    } finally {
      setAddingMember(false);
    }
  };

  const handleRemoveMember = async (userId: string) => {
    if (!selectedProject) return;
    if (!window.confirm('Xóa thành viên này khỏi dự án?')) return;
    try {
      await axios.delete(`/api/v1/projects/${selectedProject.project_id}/members/${userId}`);
      const memRes = await axios.get(`/api/v1/projects/${selectedProject.project_id}/members`);
      setMembers(memRes.data?.members ?? []);
    } catch (e: any) {
      setError(await extractErrorMessage(e));
    }
  };


  const ROLE_LABEL: Record<string, string> = {
    truong_phong: 'Trưởng phòng',
    member: 'Nhân viên',
  };

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-base font-bold text-slate-800">Quản lý Dự án OCR</h2>
          <p className="text-xs text-slate-500 mt-0.5">
            {canCreate ? 'Tạo dự án và thêm thành viên' : 'Danh sách dự án bạn được giao'}
          </p>
        </div>
        <div className="flex gap-2">
          <button
            type="button"
            onClick={() => void loadProjects()}
            className="rounded-lg p-2 text-slate-400 hover:bg-slate-100 hover:text-slate-700 transition"
            title="Tải lại"
          >
            <RefreshCw size={15} />
          </button>
          {canCreate && (
            <button
              type="button"
              onClick={() => setShowCreate(true)}
              className="flex items-center gap-1.5 rounded-lg bg-indigo-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-indigo-700 transition"
            >
              <Plus size={13} /> Tạo dự án
            </button>
          )}
        </div>
      </div>

      {/* Notice */}
      {notice && (
        <div className="flex items-center gap-2 rounded-lg bg-emerald-50 border border-emerald-200 p-3 text-sm text-emerald-800">
          <CheckCircle2 size={15} />
          <span>{notice}</span>
          <button type="button" onClick={() => setNotice(null)} className="ml-auto text-emerald-600 hover:text-emerald-800">
            <X size={13} />
          </button>
        </div>
      )}
      {error && (
        <div className="flex items-center gap-2 rounded-lg bg-red-50 border border-red-200 p-3 text-sm text-red-800">
          <AlertCircle size={15} />
          <span>{error}</span>
          <button type="button" onClick={() => setError(null)} className="ml-auto"><X size={13} /></button>
        </div>
      )}

      {/* Create form */}
      {showCreate && canCreate && (
        <form onSubmit={(e) => void handleCreateProject(e)} className="rounded-xl border border-slate-200 bg-white p-4 space-y-3 shadow-sm">
          <h3 className="text-sm font-semibold text-slate-700 flex items-center gap-1.5">
            <FolderPlus size={15} /> Tạo dự án mới
          </h3>
          <div>
            <label className="block text-xs font-medium text-slate-600 mb-1">Tên dự án *</label>
            <input
              type="text" value={createName} onChange={(e) => setCreateName(e.target.value)}
              required maxLength={255} placeholder="Ví dụ: Dự án Số Hóa Tân An Q1"
              className="block w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-slate-600 mb-1">Mô tả (tùy chọn)</label>
            <textarea
              value={createDesc} onChange={(e) => setCreateDesc(e.target.value)}
              rows={2} maxLength={1000}
              className="block w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none"
            />
          </div>
          <div className="flex gap-2 justify-end">
            <button type="button" onClick={() => setShowCreate(false)} className="rounded-lg px-3 py-1.5 text-xs border text-slate-600 hover:bg-slate-50">
              Hủy
            </button>
            <button type="submit" disabled={creating || !createName.trim()}
              className="flex items-center gap-1.5 rounded-lg bg-indigo-600 px-3 py-1.5 text-xs text-white disabled:opacity-50 hover:bg-indigo-700">
              {creating ? <Loader2 size={12} className="animate-spin" /> : <Plus size={12} />} Tạo
            </button>
          </div>
        </form>
      )}

      {/* Projects table */}
      {loading ? (
        <div className="flex items-center justify-center py-12 text-slate-400">
          <Loader2 size={20} className="animate-spin mr-2" /> Đang tải...
        </div>
      ) : projects.length === 0 ? (
        <div className="text-center py-12 text-slate-400 text-sm">
          Chưa có dự án nào. {canCreate && 'Nhấn "Tạo dự án" để bắt đầu.'}
        </div>
      ) : (
        <div className="overflow-x-auto rounded-xl border border-slate-200 shadow-sm">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-xs text-slate-600">
              <tr>
                <th className="text-left px-4 py-3 font-semibold">Tên dự án</th>
                <th className="text-left px-4 py-3 font-semibold hidden sm:table-cell">Mô tả</th>
                <th className="text-left px-4 py-3 font-semibold hidden md:table-cell">Ngày tạo</th>
                <th className="text-center px-4 py-3 font-semibold">Thành viên</th>
                {canManage && <th className="text-right px-4 py-3 font-semibold">Thao tác</th>}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {projects.map((p) => (
                <tr key={p.project_id} className="hover:bg-slate-50 transition">
                  <td className="px-4 py-3">
                    <div className="font-medium text-slate-800">{p.project_name}</div>
                    <div className="text-[11px] text-slate-400 font-mono">{p.project_id}</div>
                  </td>
                  <td className="px-4 py-3 text-slate-500 hidden sm:table-cell max-w-[200px] truncate">
                    {p.description || '—'}
                  </td>
                  <td className="px-4 py-3 text-slate-500 hidden md:table-cell text-xs">
                    {p.created_at ? new Date(p.created_at).toLocaleDateString('vi-VN') : '—'}
                  </td>
                  <td className="px-4 py-3 text-center">
                    <button
                      type="button"
                      onClick={() => void openMemberPanel(p)}
                      className="inline-flex items-center gap-1 rounded-lg px-2.5 py-1 text-xs bg-slate-100 text-slate-700 hover:bg-indigo-50 hover:text-indigo-700 transition"
                    >
                      <Users size={12} /> Xem
                    </button>
                  </td>
                  {canManage && (
                    <td className="px-4 py-3 text-right">
                      <button
                        type="button"
                        onClick={() => void handleDeleteProject(p)}
                        className="rounded-lg p-1.5 text-slate-400 hover:bg-red-50 hover:text-red-600 transition"
                        title="Xóa dự án"
                      >
                        <Trash2 size={14} />
                      </button>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Member panel */}
      {selectedProject && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm p-4">
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-lg max-h-[90vh] flex flex-col">
            <div className="flex items-center justify-between px-5 py-4 border-b border-slate-100">
              <div>
                <h3 className="text-sm font-bold text-slate-800">{selectedProject.project_name}</h3>
                <p className="text-xs text-slate-400">Danh sách thành viên</p>
              </div>
              <button type="button" onClick={() => setSelectedProject(null)} className="rounded-lg p-1.5 text-slate-400 hover:text-slate-700 hover:bg-slate-100 transition">
                <X size={16} />
              </button>
            </div>

            <div className="flex-1 overflow-y-auto p-5 space-y-4">
              {loadingMembers ? (
                <div className="flex justify-center py-8"><Loader2 className="animate-spin text-slate-400" /></div>
              ) : (
                <div className="space-y-2">
                  {members.map((m) => (
                    <div key={m.user_id} className="flex items-center justify-between rounded-lg bg-slate-50 px-3 py-2">
                      <div>
                        <div className="text-xs font-medium text-slate-800">{m.display_name || m.username}</div>
                        <div className="text-[11px] text-slate-400">
                          {ROLE_LABEL[m.role_in_project] || m.role_in_project}
                        </div>
                      </div>
                      {canManage && user?.id !== m.user_id && (
                        <button
                          type="button"
                          onClick={() => void handleRemoveMember(m.user_id)}
                          className="rounded p-1 text-slate-400 hover:bg-red-50 hover:text-red-500 transition"
                        >
                          <X size={13} />
                        </button>
                      )}
                    </div>
                  ))}
                  {members.length === 0 && (
                    <p className="text-center text-xs text-slate-400 py-4">Chưa có thành viên.</p>
                  )}
                </div>
              )}

              {/* Add member form */}
              {canManage && allUsers.length > 0 && (
                <form onSubmit={(e) => void handleAddMember(e)} className="border-t border-slate-100 pt-4 space-y-3">
                  <h4 className="text-xs font-semibold text-slate-600 flex items-center gap-1"><UserPlus size={13} /> Thêm thành viên</h4>
                  <div>
                    <label className="block text-xs text-slate-500 mb-1">Tài khoản</label>
                    <select
                      value={addUserId}
                      onChange={(e) => setAddUserId(e.target.value)}
                      required
                      className="block w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none"
                    >
                      <option value="">-- Chọn người dùng --</option>
                      {allUsers
                        .filter((u) => !members.some((m) => m.user_id === u.id))
                        .map((u) => (
                          <option key={u.id} value={u.id}>
                            {u.username} {(u.first_name || u.last_name) ? `(${[u.first_name, u.last_name].filter(Boolean).join(' ')})` : ''}
                          </option>
                        ))}
                    </select>
                  </div>
                  <div>
                    <label className="block text-xs text-slate-500 mb-1">Vai trò</label>
                    <select
                      value={addRole}
                      onChange={(e) => setAddRole(e.target.value as 'member' | 'truong_phong')}
                      className="block w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none"
                    >
                      <option value="member">Nhân viên</option>
                      <option value="truong_phong">Trưởng phòng</option>
                    </select>
                  </div>
                  <button
                    type="submit" disabled={addingMember || !addUserId}
                    className="flex items-center gap-1.5 rounded-lg bg-indigo-600 px-3 py-1.5 text-xs text-white disabled:opacity-50 hover:bg-indigo-700"
                  >
                    {addingMember ? <Loader2 size={12} className="animate-spin" /> : <Plus size={12} />} Thêm
                  </button>
                </form>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
