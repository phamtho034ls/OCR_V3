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
import React, { FormEvent, useCallback, useEffect, useState, useMemo } from 'react';
import { useAuth } from '../../shared/auth/AuthProvider';
import { extractErrorMessage } from '../../shared/lib/errorHelper';

interface Project {
  project_id: string;
  project_name: string;
  description?: string;
  created_by: string;
  status: string;
  created_at: string;
  region?: string;
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
  const isAdmin = user?.roles.includes('ocr-admin') || false;

  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  // Region filtering (cho Admin tổng)
  const [selectedRegionFilter, setSelectedRegionFilter] = useState<string>('all');

  // Create project form
  const [showCreate, setShowCreate] = useState(false);
  const [createName, setCreateName] = useState('');
  const [createDesc, setCreateDesc] = useState('');
  const [createRegion, setCreateRegion] = useState<string>('TP. Hải Phòng');
  const [creating, setCreating] = useState(false);
  const [creationCandidates, setCreationCandidates] = useState<any[]>([]);
  const [selectedCandidateIds, setSelectedCandidateIds] = useState<string[]>([]);
  const [loadingCandidates, setLoadingCandidates] = useState(false);
  const [createNameError, setCreateNameError] = useState<string | null>(null);
  const [candidateSearch, setCandidateSearch] = useState('');

  // Member management
  const [selectedProject, setSelectedProject] = useState<Project | null>(null);
  const [members, setMembers] = useState<Member[]>([]);
  const [loadingMembers, setLoadingMembers] = useState(false);
  const [canManageSelectedProject, setCanManageSelectedProject] = useState(false);
  const [allUsers, setAllUsers] = useState<any[]>([]);
  const [managerRegion, setManagerRegion] = useState<string>('');
  const [addUserId, setAddUserId] = useState('');
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

  const availableRegions = useMemo(() => {
    const setReg = new Set<string>();
    projects.forEach((p) => {
      if (p.region && p.region.trim() && p.region !== 'Chưa phân khu vực') {
        setReg.add(p.region.trim());
      }
    });
    return Array.from(setReg);
  }, [projects]);

  const filteredProjects = useMemo(() => {
    if (selectedRegionFilter === 'all') return projects;
    return projects.filter((p) => (p.region || 'Chưa phân khu vực') === selectedRegionFilter);
  }, [projects, selectedRegionFilter]);

  const openCreateModal = async () => {
    setShowCreate(true);
    setCreateName('');
    setCreateDesc('');
    setCreateRegion(user?.region || 'TP. Hải Phòng');
    setSelectedCandidateIds([]);
    setCreateNameError(null);
    setCandidateSearch('');
    setLoadingCandidates(true);
    try {
      const res = await axios.get('/api/v1/projects/candidates');
      setCreationCandidates(res.data?.users ?? []);
    } catch {
      setCreationCandidates([]);
    } finally {
      setLoadingCandidates(false);
    }
  };

  const handleCreateProject = async (e: FormEvent) => {
    e.preventDefault();
    const trimmedName = createName.trim();
    if (!trimmedName) {
      setCreateNameError('Vui lòng nhập tên dự án.');
      return;
    }
    setCreateNameError(null);
    setCreating(true);
    try {
      await axios.post('/api/v1/projects', {
        project_name: trimmedName,
        description: createDesc.trim() || null,
        region: createRegion.trim() || undefined,
        member_ids: selectedCandidateIds,
      });
      const memberCountMsg = selectedCandidateIds.length > 0 ? ` cùng ${selectedCandidateIds.length} thành viên` : '';
      setNotice(`Dự án '${trimmedName}' đã được tạo${memberCountMsg}.`);
      setCreateName('');
      setCreateDesc('');
      setSelectedCandidateIds([]);
      setShowCreate(false);
      window.dispatchEvent(new CustomEvent('project:changed'));
      await loadProjects();
    } catch (e: any) {
      setError(await extractErrorMessage(e));
    } finally {
      setCreating(false);
    }
  };

  const toggleCandidate = (uid: string) => {
    setSelectedCandidateIds((prev) =>
      prev.includes(uid) ? prev.filter((id) => id !== uid) : [...prev, uid]
    );
  };

  const toggleSelectAllCandidates = () => {
    const visibleUids = filteredCandidates.map((c) => c.id);
    const allSelected = visibleUids.every((uid) => selectedCandidateIds.includes(uid));
    if (allSelected) {
      setSelectedCandidateIds((prev) => prev.filter((id) => !visibleUids.includes(id)));
    } else {
      setSelectedCandidateIds((prev) => Array.from(new Set([...prev, ...visibleUids])));
    }
  };

  const filteredCandidates = creationCandidates.filter((c) => {
    if (!candidateSearch.trim()) return true;
    const q = candidateSearch.toLowerCase();
    const uName = (c.username || '').toLowerCase();
    const dName = (c.display_name || '').toLowerCase();
    const reg = (c.region || '').toLowerCase();
    return uName.includes(q) || dName.includes(q) || reg.includes(q);
  });

  const handleDeleteProject = async (p: Project) => {
    const confirmMsg = `XÁC NHẬN XÓA TOÀN BỘ DỰ ÁN '${p.project_name}'?\n\nCẢNH BÁO NGUY HIỂM:\nHệ thống sẽ xóa vĩnh viễn dữ liệu dự án trong CSDL và XÓA SẠCH TOÀN BỘ ẢNH CROP, PREVIEWS, VÀ THƯ MỤC DỮ LIỆU LIÊN QUAN TRÊN Ổ ĐĨA.\n\nThao tác này không thể phục hồi. Bạn có chắc chắn muốn xóa?`;
    if (!window.confirm(confirmMsg)) return;
    try {
      await axios.delete(`/api/v1/projects/${p.project_id}`);
      setNotice(`Đã xóa vĩnh viễn dự án '${p.project_name}' cùng toàn bộ dữ liệu CSDL và ảnh crop trên đĩa.`);
      window.dispatchEvent(new CustomEvent('project:changed'));
      await loadProjects();
    } catch (e: any) {
      setError(await extractErrorMessage(e));
    }
  };

  const openMemberPanel = async (p: Project, focusAdd = false) => {
    setSelectedProject(p);
    setLoadingMembers(true);
    setCanManageSelectedProject(false);
    setAllUsers([]);
    setManagerRegion('');
    try {
      const memRes = await axios.get(`/api/v1/projects/${p.project_id}/members`);
      const memberList: Member[] = memRes.data?.members ?? [];
      const canManageHere = !isStaffMember && (
        canManage || memberList.some(
          (member) => member.user_id === user?.id && member.role_in_project === 'truong_phong'
        )
      );
      setMembers(memberList);
      setCanManageSelectedProject(canManageHere);
      if (canManageHere) {
        const usersRes = await axios.get(`/api/v1/projects/${p.project_id}/available-users`);
        setAllUsers(usersRes.data?.users ?? []);
        setManagerRegion(usersRes.data?.caller_region || '');
      }
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
        display_name: selectedUser?.display_name || selectedUser?.username || addUserId,
        role_in_project: 'member',
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

  const isStaffMember = !user?.roles.includes('ocr-admin') && !user?.roles.includes('ocr-truongphong');

  const canDeleteProject = (project: Project) => {
    if (isStaffMember) return false;
    return user?.roles.includes('ocr-admin') || project.created_by === user?.id;
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
              onClick={() => void openCreateModal()}
              className="flex items-center gap-1.5 rounded-lg bg-gov-800 px-3 py-1.5 text-xs font-medium text-white hover:bg-gov-900 transition cursor-pointer shadow-xs"
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
        <form onSubmit={(e) => void handleCreateProject(e)} className="rounded-xl border border-slate-200 bg-white p-5 space-y-4 shadow-sm">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-semibold text-slate-800 flex items-center gap-1.5">
              <FolderPlus size={16} className="text-gov-800" /> Tạo dự án mới
            </h3>
            <button type="button" onClick={() => setShowCreate(false)} className="text-slate-400 hover:text-slate-600">
              <X size={15} />
            </button>
          </div>

          <div>
            <label className="block text-xs font-semibold text-slate-700 mb-1">
              Tên dự án <span className="text-rose-500">*</span>
            </label>
            <input
              type="text"
              value={createName}
              onChange={(e) => {
                setCreateName(e.target.value);
                if (createNameError) setCreateNameError(null);
              }}
              onInvalid={(e) => (e.target as HTMLInputElement).setCustomValidity('Vui lòng nhập tên dự án')}
              onInput={(e) => (e.target as HTMLInputElement).setCustomValidity('')}
              required
              maxLength={255}
              placeholder="Ví dụ: Dự án Số Hóa Tân An Q1"
              className={`block w-full rounded-lg border ${
                createNameError ? 'border-rose-400 ring-1 ring-rose-400' : 'border-slate-300'
              } px-3 py-2 text-sm focus:border-gov-800 focus:outline-none focus:ring-1 focus:ring-gov-800`}
            />
            {createNameError && (
              <p className="mt-1 text-xs text-rose-600 font-medium">{createNameError}</p>
            )}
          </div>

          {/* Chọn khu vực áp dụng cho dự án */}
          <div>
            <label className="block text-xs font-semibold text-slate-700 mb-1">
              Khu vực địa bàn {isAdmin && <span className="text-gov-800 font-bold">(Admin tổng chỉ định)</span>}
            </label>
            {isAdmin ? (
              <div className="space-y-1.5">
                <input
                  type="text"
                  value={createRegion}
                  onChange={(e) => setCreateRegion(e.target.value)}
                  placeholder="Ví dụ: TP. Hải Phòng, Tỉnh Lạng Sơn, Tỉnh Ninh Bình..."
                  className="block w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-gov-800 focus:outline-none focus:ring-1 focus:ring-gov-800"
                />
                <div className="flex flex-wrap gap-1.5 text-[11px]">
                  <span className="text-slate-400">Gợi ý nhanh:</span>
                  {['TP. Hải Phòng', 'Tỉnh Lạng Sơn', 'Tỉnh Ninh Bình', 'TP. Hà Nội'].map((r) => (
                    <button
                      key={r}
                      type="button"
                      onClick={() => setCreateRegion(r)}
                      className="px-2 py-0.5 rounded bg-slate-100 hover:bg-gov-100 hover:text-gov-900 text-slate-600 transition cursor-pointer"
                    >
                      {r}
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              <div className="px-3 py-2 bg-slate-50 border border-slate-200 rounded-lg text-xs font-semibold text-slate-700">
                📍 {user?.region || 'Khu vực quản lý của tài khoản'}
              </div>
            )}
          </div>

          <div>
            <label className="block text-xs font-semibold text-slate-700 mb-1">Mô tả (tùy chọn)</label>
            <textarea
              value={createDesc}
              onChange={(e) => setCreateDesc(e.target.value)}
              rows={2}
              maxLength={1000}
              placeholder="Ghi chú ngắn về mục tiêu hoặc phạm vi của dự án..."
              className="block w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-gov-800 focus:outline-none"
            />
          </div>

          {/* Thêm thành viên ngay khi tạo dự án */}
          <div className="border-t border-slate-100 pt-3">
            <div className="flex items-center justify-between mb-2">
              <label className="block text-xs font-semibold text-slate-700">
                Thêm thành viên vào dự án ngay ({selectedCandidateIds.length} đã chọn)
              </label>
              {filteredCandidates.length > 0 && (
                <button
                  type="button"
                  onClick={toggleSelectAllCandidates}
                  className="text-[11px] text-gov-800 hover:text-gov-950 font-medium cursor-pointer"
                >
                  {filteredCandidates.every((c) => selectedCandidateIds.includes(c.id))
                    ? 'Bỏ chọn tất cả'
                    : 'Chọn tất cả'}
                </button>
              )}
            </div>

            {loadingCandidates ? (
              <div className="flex items-center justify-center py-4 text-xs text-slate-400">
                <Loader2 size={14} className="animate-spin mr-1.5" /> Đang tải danh sách nhân sự...
              </div>
            ) : creationCandidates.length === 0 ? (
              <p className="text-xs text-slate-400 italic py-1">
                Không có nhân sự khả dụng để thêm. Bạn có thể thêm sau khi tạo xong.
              </p>
            ) : (
              <div className="space-y-2">
                {creationCandidates.length > 4 && (
                  <input
                    type="text"
                    placeholder="Tìm tên, tài khoản..."
                    value={candidateSearch}
                    onChange={(e) => setCandidateSearch(e.target.value)}
                    className="w-full rounded-lg border border-slate-200 bg-slate-50 px-2.5 py-1.5 text-xs outline-none focus:border-gov-800 focus:bg-white"
                  />
                )}
                <div className="max-h-40 overflow-y-auto divide-y divide-slate-100 rounded-lg border border-slate-200 bg-slate-50/50 p-1">
                  {filteredCandidates.map((cand) => {
                    const isChecked = selectedCandidateIds.includes(cand.id);
                    return (
                      <label
                        key={cand.id}
                        className="flex items-center justify-between px-2.5 py-1.5 hover:bg-white rounded cursor-pointer transition text-xs select-none"
                      >
                        <div className="flex items-center gap-2">
                          <input
                            type="checkbox"
                            checked={isChecked}
                            onChange={() => toggleCandidate(cand.id)}
                            className="rounded border-slate-300 text-gov-800 focus:ring-gov-800 h-3.5 w-3.5"
                          />
                          <span className="font-medium text-slate-700">
                            {cand.display_name || cand.username}
                          </span>
                          <span className="text-[11px] text-slate-400 font-mono">
                            @{cand.username}
                          </span>
                        </div>
                        {cand.region && (
                          <span className="text-[10px] bg-slate-200/70 text-slate-600 px-1.5 py-0.5 rounded font-medium">
                            {cand.region}
                          </span>
                        )}
                      </label>
                    );
                  })}
                </div>
              </div>
            )}
          </div>

          <div className="flex gap-2 justify-end pt-2 border-t border-slate-100">
            <button
              type="button"
              onClick={() => setShowCreate(false)}
              className="rounded-lg px-3 py-1.5 text-xs border text-slate-600 hover:bg-slate-50 cursor-pointer"
            >
              Hủy
            </button>
            <button
              type="submit"
              disabled={creating || !createName.trim()}
              className="flex items-center gap-1.5 rounded-lg bg-gov-800 px-4 py-1.5 text-xs font-medium text-white disabled:opacity-50 hover:bg-gov-900 cursor-pointer shadow-xs"
            >
              {creating ? <Loader2 size={12} className="animate-spin" /> : <Plus size={12} />} Tạo dự án
            </button>
          </div>
        </form>
      )}

      {/* Admin Tổng: Thanh Lọc & Phân Vùng Khu Vực */}
      {isAdmin && (
        <div className="bg-white rounded-xl border border-slate-200 p-4 shadow-2xs space-y-2.5">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              <span className="w-2.5 h-2.5 rounded-full bg-gov-800 animate-pulse"></span>
              <span className="text-xs font-bold uppercase tracking-wider text-slate-800">
                Phân vùng khu vực toàn quốc
              </span>
              <span className="text-[10px] font-bold text-gov-900 bg-gov-50 border border-gov-200 px-2 py-0.5 rounded">
                Admin Tổng
              </span>
            </div>
            <div className="text-xs text-slate-500">
              Tổng số: <strong className="text-slate-800">{projects.length}</strong> dự án trên <strong className="text-slate-800">{availableRegions.length}</strong> khu vực
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2 pt-1 border-t border-slate-100">
            <button
              type="button"
              onClick={() => setSelectedRegionFilter('all')}
              className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition cursor-pointer flex items-center gap-1.5 ${
                selectedRegionFilter === 'all'
                  ? 'bg-gov-800 text-white shadow-2xs font-bold'
                  : 'bg-slate-100 text-slate-600 hover:bg-slate-200 hover:text-slate-900'
              }`}
            >
              <span>🏢 Tất cả khu vực</span>
              <span className={`px-1.5 py-0.2 text-[10px] rounded-full ${selectedRegionFilter === 'all' ? 'bg-gov-950 text-white' : 'bg-slate-200 text-slate-700'}`}>
                {projects.length}
              </span>
            </button>

            {availableRegions.map((reg) => {
              const count = projects.filter((p) => (p.region || 'Chưa phân khu vực') === reg).length;
              const isSelected = selectedRegionFilter === reg;
              return (
                <button
                  key={reg}
                  type="button"
                  onClick={() => setSelectedRegionFilter(reg)}
                  className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition cursor-pointer flex items-center gap-1.5 ${
                    isSelected
                      ? 'bg-gov-800 text-white shadow-2xs font-bold'
                      : 'bg-slate-100 text-slate-600 hover:bg-slate-200 hover:text-slate-900'
                  }`}
                >
                  <span>📍 {reg}</span>
                  <span className={`px-1.5 py-0.2 text-[10px] rounded-full ${isSelected ? 'bg-gov-950 text-white' : 'bg-slate-200 text-slate-700'}`}>
                    {count}
                  </span>
                </button>
              );
            })}
          </div>
        </div>
      )}

      {/* Projects table */}
      {loading ? (
        <div className="flex items-center justify-center py-12 text-slate-400">
          <Loader2 size={20} className="animate-spin mr-2" /> Đang tải...
        </div>
      ) : filteredProjects.length === 0 ? (
        <div className="text-center py-12 text-slate-400 text-sm">
          Chưa có dự án nào{selectedRegionFilter !== 'all' ? ` thuộc khu vực "${selectedRegionFilter}"` : ''}. {canCreate && 'Nhấn "Tạo dự án" để bắt đầu.'}
        </div>
      ) : (
        <div className="overflow-x-auto rounded-xl border border-slate-200 shadow-sm bg-white">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-xs text-slate-600 border-b border-slate-200">
              <tr>
                <th className="text-left px-4 py-3 font-semibold">Tên dự án</th>
                <th className="text-left px-4 py-3 font-semibold">Khu vực</th>
                <th className="text-left px-4 py-3 font-semibold hidden sm:table-cell">Mô tả</th>
                <th className="text-left px-4 py-3 font-semibold hidden md:table-cell">Ngày tạo</th>
                <th className="text-center px-4 py-3 font-semibold">Thành viên</th>
                {filteredProjects.some(canDeleteProject) && <th className="text-right px-4 py-3 font-semibold">Thao tác</th>}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {filteredProjects.map((p) => (
                <tr key={p.project_id} className="hover:bg-gov-50/40 transition">
                  <td className="px-4 py-3">
                    <div className="font-bold text-slate-900">{p.project_name}</div>
                    <div className="text-[11px] text-slate-400 font-mono">{p.project_id}</div>
                  </td>
                  <td className="px-4 py-3 whitespace-nowrap">
                    <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-gov-50 text-gov-900 border border-gov-200">
                      📍 {p.region || 'Chưa phân khu vực'}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-slate-500 hidden sm:table-cell max-w-[200px] truncate">
                    {p.description || '—'}
                  </td>
                  <td className="px-4 py-3 text-slate-500 hidden md:table-cell text-xs">
                    {p.created_at ? new Date(p.created_at).toLocaleDateString('vi-VN') : '—'}
                  </td>
                  <td className="px-4 py-3 text-center">
                    <div className="inline-flex items-center gap-1.5 justify-center">
                      <button
                        type="button"
                        onClick={() => void openMemberPanel(p, false)}
                        className="inline-flex items-center gap-1 rounded-lg px-2.5 py-1 text-xs bg-slate-100 text-slate-700 hover:bg-gov-50 hover:text-gov-800 transition cursor-pointer"
                        title="Xem danh sách thành viên"
                      >
                        <Users size={12} /> Xem
                      </button>
                      {!isStaffMember && (canManage || user?.roles.includes('ocr-admin') || p.created_by === user?.id) && (
                        <button
                          type="button"
                          onClick={() => void openMemberPanel(p, true)}
                          className="inline-flex items-center gap-1 rounded-lg px-2.5 py-1 text-xs bg-gov-50 text-gov-800 hover:bg-gov-100 transition font-medium cursor-pointer"
                          title="Thêm thành viên vào dự án"
                        >
                          <UserPlus size={12} /> + Thêm
                        </button>
                      )}
                    </div>
                  </td>
                  {canDeleteProject(p) && (
                    <td className="px-4 py-3 text-right">
                      <button
                        type="button"
                        onClick={() => void handleDeleteProject(p)}
                        className="rounded-lg p-1.5 text-slate-400 hover:bg-red-50 hover:text-red-600 transition cursor-pointer"
                        title="Xóa vĩnh viễn dự án và toàn bộ ảnh crop trên đĩa"
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
                      {canManageSelectedProject && user?.id !== m.user_id && (
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
              {canManageSelectedProject && (
                <>
                  {allUsers.length > 0 ? (
                    <form onSubmit={(e) => void handleAddMember(e)} className="border-t border-slate-100 pt-4 space-y-3">
                      <div className="flex items-center justify-between">
                        <h4 className="text-xs font-semibold text-slate-600 flex items-center gap-1">
                          <UserPlus size={13} /> Thêm thành viên
                        </h4>
                        {managerRegion && (
                          <span className="text-[11px] font-medium text-slate-500 bg-slate-100 px-2 py-0.5 rounded-md">
                            Khu vực: <strong className="text-gov-800">{managerRegion}</strong>
                          </span>
                        )}
                      </div>
                      <div>
                        <label className="block text-xs text-slate-500 mb-1">Tài khoản</label>
                        <select
                          value={addUserId}
                          onChange={(e) => setAddUserId(e.target.value)}
                          required
                          className="block w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-gov-800 focus:outline-none"
                        >
                          <option value="">-- Chọn người dùng --</option>
                          {allUsers
                            .filter((u) => !members.some((m) => m.user_id === u.id))
                            .map((u) => {
                              const nameStr = [u.first_name, u.last_name].filter(Boolean).join(' ') || u.display_name;
                              return (
                                <option key={u.id} value={u.id}>
                                  {u.username} {nameStr && nameStr !== u.username ? `(${nameStr})` : ''} {u.region ? `[${u.region}]` : ''}
                                </option>
                              );
                            })}
                        </select>
                      </div>
                      <button
                        type="submit" disabled={addingMember || !addUserId}
                        className="flex items-center gap-1.5 rounded-lg bg-gov-800 px-3 py-1.5 text-xs text-white disabled:opacity-50 hover:bg-gov-900 cursor-pointer shadow-xs"
                      >
                        {addingMember ? <Loader2 size={12} className="animate-spin" /> : <Plus size={12} />} Thêm
                      </button>
                    </form>
                  ) : (
                    <div className="border-t border-slate-100 pt-4 text-center">
                      <p className="text-xs text-slate-500">
                        {managerRegion
                          ? `Không có nhân viên khả dụng thuộc khu vực "${managerRegion}".`
                          : 'Không có nhân viên khả dụng để thêm vào dự án.'}
                      </p>
                    </div>
                  )}
                </>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
