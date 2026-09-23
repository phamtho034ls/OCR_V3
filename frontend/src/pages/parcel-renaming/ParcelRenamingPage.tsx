import React, { useEffect, useRef, useState } from 'react';
import axios from 'axios';
import { AlertTriangle, CheckCircle2, Download, FileText, FolderUp, Loader2, Tags } from 'lucide-react';
import { ProjectSelector } from '../../shared/components/ProjectSelector';
import { extractErrorMessage } from '../../shared/lib/errorHelper';

interface ParcelRenamingPageProps {
  onNavigateToProjects?: () => void;
}

interface RenameResult {
  original_name: string;
  original_path: string;
  map_sheet: string | null;
  parcel_number: string | null;
  renamed_path: string | null;
  page_number: number | null;
  confidence: number | null;
  status: 'renamed' | 'review';
  reason: string | null;
}

interface RenameResponse {
  job_id: string;
  total: number;
  renamed: number;
  review: number;
  results: RenameResult[];
  download_url: string;
}

export const ParcelRenamingPage: React.FC<ParcelRenamingPageProps> = ({ onNavigateToProjects }) => {
  const [projectId, setProjectId] = useState('');
  const [files, setFiles] = useState<File[]>([]);
  const [folderName, setFolderName] = useState('');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<RenameResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    inputRef.current?.setAttribute('webkitdirectory', '');
    inputRef.current?.setAttribute('directory', '');
  }, []);

  const selectFolder = (event: React.ChangeEvent<HTMLInputElement>) => {
    const selected = Array.from(event.target.files || []);
    const pdfs = selected.filter((file) => file.name.toLowerCase().endsWith('.pdf'));
    if (!pdfs.length) {
      setFiles([]);
      setFolderName('');
      setError('Không tìm thấy file PDF trong thư mục đã chọn.');
      return;
    }
    const relative = pdfs[0].webkitRelativePath || '';
    setFolderName(relative.split('/')[0] || 'Thư mục PDF');
    setFiles(pdfs);
    setError(null);
    setResult(null);
  };

  const processFolder = async () => {
    if (!projectId) {
      setError('Vui lòng chọn dự án trước khi xử lý.');
      return;
    }
    if (!files.length) {
      setError('Vui lòng chọn thư mục có file PDF.');
      return;
    }
    setLoading(true);
    setError(null);
    const form = new FormData();
    form.append('project_id', projectId);
    files.forEach((file) => {
      form.append('files', file);
      form.append('relative_paths', file.webkitRelativePath || file.name);
    });
    try {
      const response = await axios.post<RenameResponse>('/api/v1/parcel-renaming', form);
      setResult(response.data);
    } catch (err: unknown) {
      setError(await extractErrorMessage(err, 'Không thể xử lý thư mục PDF.'));
    } finally {
      setLoading(false);
    }
  };

  const downloadZip = async () => {
    if (!result) return;
    try {
      const response = await axios.get(result.download_url, { responseType: 'blob' });
      const url = URL.createObjectURL(new Blob([response.data], { type: 'application/zip' }));
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = 'ket-qua-doi-ten.zip';
      anchor.click();
      URL.revokeObjectURL(url);
    } catch (err: unknown) {
      setError(await extractErrorMessage(err, 'Không thể tải tệp ZIP kết quả.'));
    }
  };

  return (
    <div className="mx-auto max-w-6xl space-y-6 pb-12">
      <section className="rounded-2xl border border-gov-200 bg-gradient-to-br from-gov-50 via-white to-emerald-50 p-6 shadow-sm">
        <div className="flex items-start gap-4">
          <div className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-gov-900 text-amber-300 shadow-sm">
            <Tags size={21} />
          </div>
          <div>
            <h2 className="text-lg font-bold text-slate-950">Đổi tên PDF theo số tờ - số thửa</h2>
            <p className="mt-1 max-w-3xl text-sm leading-6 text-slate-600">
              Hệ thống đọc bảng <b>“Thông tin theo hồ sơ đăng ký đất đai”</b>, tạo tên <code className="rounded bg-slate-100 px-1.5 py-0.5">{'{số_tờ}-{số_thửa}.pdf'}</code> theo dạng <code className="rounded bg-slate-100 px-1.5 py-0.5">38-109.pdf</code> và không dùng bảng “bản đồ 299”.
            </p>
          </div>
        </div>
      </section>

      <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
        <div className="grid gap-5 md:grid-cols-[minmax(0,1fr)_minmax(0,1.2fr)] md:items-end">
          <ProjectSelector
            value={projectId}
            onChange={(id) => setProjectId(id)}
            disabled={loading}
            required
            label="Dự án xử lý"
            onNavigateToProjects={onNavigateToProjects}
          />
          <div>
            <input ref={inputRef} type="file" className="hidden" multiple accept="application/pdf,.pdf" onChange={selectFolder} />
            <button type="button" onClick={() => inputRef.current?.click()} disabled={loading} className="flex w-full items-center justify-center gap-2 rounded-xl border-2 border-dashed border-gov-300 bg-gov-50 px-4 py-3 text-sm font-bold text-gov-900 transition hover:border-gov-600 hover:bg-gov-100 disabled:cursor-not-allowed disabled:opacity-60">
              <FolderUp size={18} />
              Chọn thư mục PDF
            </button>
            <p className="mt-2 text-center text-xs text-slate-500">
              {files.length ? `${folderName}: ${files.length} file PDF đã chọn` : 'Có thể gồm các thư mục con; chỉ PDF được tải lên.'}
            </p>
          </div>
        </div>
        <div className="mt-5 flex flex-wrap items-center justify-between gap-3 border-t border-slate-100 pt-5">
          <p className="text-xs leading-5 text-slate-500">File không xác định chắc chắn sẽ được giữ nguyên trong thư mục <b>can-kiem-tra</b> của ZIP, không bị đổi tên tự động.</p>
          <button type="button" onClick={() => void processFolder()} disabled={loading || !files.length || !projectId} className="inline-flex items-center gap-2 rounded-xl bg-gov-800 px-5 py-2.5 text-sm font-bold text-white shadow-sm transition hover:bg-gov-950 disabled:cursor-not-allowed disabled:bg-slate-300">
            {loading ? <Loader2 size={16} className="animate-spin" /> : <FileText size={16} />}
            {loading ? 'Đang OCR và đổi tên...' : 'Xử lý thư mục'}
          </button>
        </div>
      </section>

      {error && <div className="flex items-start gap-2 rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-800"><AlertTriangle size={18} className="mt-0.5 shrink-0" />{error}</div>}

      {result && (
        <section className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
          <div className="flex flex-wrap items-center justify-between gap-4 border-b border-slate-100 p-5">
            <div>
              <h3 className="flex items-center gap-2 text-base font-bold text-slate-900"><CheckCircle2 size={18} className="text-emerald-600" /> Đã xử lý {result.total} file</h3>
              <p className="mt-1 text-xs text-slate-500">Đổi tên: <b className="text-emerald-700">{result.renamed}</b> · Cần kiểm tra: <b className="text-amber-700">{result.review}</b></p>
            </div>
            <button type="button" onClick={() => void downloadZip()} className="inline-flex items-center gap-2 rounded-xl bg-emerald-600 px-4 py-2.5 text-sm font-bold text-white shadow-sm transition hover:bg-emerald-700"><Download size={16} />Tải ZIP kết quả</button>
          </div>
          <div className="max-h-[480px] overflow-auto">
            <table className="w-full text-left text-xs text-slate-700">
              <thead className="sticky top-0 bg-slate-50 text-[11px] font-bold uppercase tracking-wide text-slate-600"><tr><th className="px-4 py-3">File gốc</th><th className="px-4 py-3 text-center">Số tờ</th><th className="px-4 py-3 text-center">Số thửa</th><th className="px-4 py-3">Tên/đường dẫn đầu ra</th><th className="px-4 py-3">Trạng thái</th></tr></thead>
              <tbody className="divide-y divide-slate-100">
                {result.results.map((item) => <tr key={item.original_path} className="hover:bg-slate-50"><td className="max-w-64 truncate px-4 py-3 font-medium" title={item.original_path}>{item.original_path}</td><td className="px-4 py-3 text-center font-mono font-bold">{item.map_sheet || '-'}</td><td className="px-4 py-3 text-center font-mono font-bold">{item.parcel_number || '-'}</td><td className="max-w-72 truncate px-4 py-3 font-mono text-gov-800" title={item.renamed_path || item.reason || ''}>{item.renamed_path || item.reason}</td><td className="px-4 py-3">{item.status === 'renamed' ? <span className="rounded-full bg-emerald-100 px-2 py-1 font-bold text-emerald-800">Đã đổi tên</span> : <span className="rounded-full bg-amber-100 px-2 py-1 font-bold text-amber-800">Cần kiểm tra</span>}</td></tr>)}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </div>
  );
};
