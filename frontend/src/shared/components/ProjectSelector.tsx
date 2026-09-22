import React, { useCallback, useEffect, useState } from 'react';
import axios from 'axios';
import { Folder, Loader2, AlertTriangle } from 'lucide-react';
import { useAuth } from '../auth/AuthProvider';

interface Project {
  project_id: string;
  project_name: string;
  description?: string;
  status: string;
  region?: string;
}

interface ProjectSelectorProps {
  value: string;
  onChange: (projectId: string, projectName: string) => void;
  required?: boolean;
  disabled?: boolean;
  label?: string;
  className?: string;
  onNavigateToProjects?: () => void;
}

export const ProjectSelector: React.FC<ProjectSelectorProps> = ({
  value,
  onChange,
  required = false,
  disabled = false,
  label = 'Dự án',
  className = '',
  onNavigateToProjects,
}) => {
  const { can } = useAuth();
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadProjects = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await axios.get('/api/v1/projects?limit=200');
      const list: Project[] = res.data?.projects ?? [];
      const activeList = list.filter((p) => p.status === 'active');
      setProjects(activeList);
      // Tự chọn dự án đầu tiên nếu chưa chọn
      if (!value && activeList.length > 0) {
        onChange(activeList[0].project_id, activeList[0].project_name);
      }
    } catch (e: any) {
      setError('Không thể tải danh sách dự án');
    } finally {
      setLoading(false);
    }
  }, [value, onChange]);

  useEffect(() => {
    void loadProjects();
    const handleProjectChanged = () => {
      void loadProjects();
    };
    window.addEventListener('project:changed', handleProjectChanged);
    return () => {
      window.removeEventListener('project:changed', handleProjectChanged);
    };
  }, [loadProjects]);

  if (loading) {
    return (
      <div className={`flex items-center gap-2 text-sm text-slate-400 ${className}`}>
        <Loader2 size={14} className="animate-spin text-gov-800" />
        <span>Đang tải danh mục dự án...</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className={`text-xs text-red-600 font-medium ${className}`}>{error}</div>
    );
  }

  if (projects.length === 0) {
    const handleNavigate = () => {
      if (onNavigateToProjects) {
        onNavigateToProjects();
      } else {
        window.dispatchEvent(new CustomEvent('app:navigate', { detail: 'projects' }));
      }
    };

    const canCreateProject = can('project.create');

    return (
      <div className={`p-3 bg-amber-50 border border-amber-200 rounded-xl text-amber-900 text-xs flex items-start gap-2.5 ${className}`}>
        <AlertTriangle size={16} className="text-amber-700 mt-0.5 shrink-0" />
        <div className="flex-1">
          <div className="font-bold text-amber-950 mb-0.5">Chưa có dự án nào khả dụng</div>
          {canCreateProject ? (
            <p className="text-amber-800 leading-relaxed">
              Bạn chưa có dự án nào để xử lý hồ sơ. Vui lòng{' '}
              <button
                type="button"
                onClick={handleNavigate}
                className="underline font-bold text-gov-800 hover:text-gov-950 cursor-pointer inline"
              >
                tạo dự án mới tại Quản lý dự án
              </button>{' '}
              trước khi tiếp tục.
            </p>
          ) : (
            <p className="text-amber-800 leading-relaxed">
              Tài khoản của bạn chưa được phân quyền vào bất kỳ dự án nào. Vui lòng liên hệ Trưởng phòng hoặc Quản trị viên để được thêm vào dự án trước khi xử lý hồ sơ.
            </p>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className={className}>
      {label && (
        <label className="block text-xs font-semibold text-slate-700 mb-1">
          <Folder size={13} className="inline mr-1 text-gov-800" />
          {label}{required && <span className="text-red-600 ml-0.5">*</span>}
        </label>
      )}
      <select
        value={value}
        onChange={(e) => {
          const selected = projects.find((p) => p.project_id === e.target.value);
          if (selected) onChange(selected.project_id, selected.project_name);
        }}
        disabled={disabled}
        required={required}
        className="block w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-medium
                   text-slate-800 shadow-xs focus:border-gov-800 focus:outline-none
                   focus:ring-1 focus:ring-gov-800 disabled:opacity-50 disabled:cursor-not-allowed"
      >
        {projects.map((p) => {
          const regionSuffix = p.region && p.region !== 'Chưa phân khu vực' ? ` [${p.region}]` : '';
          return (
            <option key={p.project_id} value={p.project_id}>
              📁 {p.project_name}{regionSuffix}
            </option>
          );
        })}
      </select>
    </div>
  );
};
