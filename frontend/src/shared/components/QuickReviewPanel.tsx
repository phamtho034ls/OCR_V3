import React, { useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import {
  AlertTriangle,
  Check,
  CheckCheck,
  Edit3,
  Eye,
  Image as ImageIcon,
  Loader2,
  Pencil,
  RotateCw,
  Save,
  X,
  ZoomIn,
  ZoomOut,
} from 'lucide-react';
import { OcrDocumentReview, OcrFieldReview, OcrReviewField, OcrReviewStatus } from '../types';
import { ProtectedImage } from './ProtectedImage';
import { useAuth } from '../auth/AuthProvider';

interface QuickReviewPanelProps {
  documentId: string;
  onClose: () => void;
}

const STATUS_CONFIG: Record<OcrReviewStatus, { label: string; className: string }> = {
  ready: { label: 'Có bằng chứng', className: 'bg-emerald-100 text-emerald-800' },
  needs_review: { label: 'Cần xem', className: 'bg-amber-100 text-amber-800' },
  missing: { label: 'Thiếu dữ liệu', className: 'bg-rose-100 text-rose-800' },
  no_evidence: { label: 'Chưa có box', className: 'bg-slate-200 text-slate-700' },
  confirmed: { label: 'Đã xác nhận', className: 'bg-emerald-100 text-emerald-800' },
  corrected: { label: 'Đã chỉnh', className: 'bg-indigo-100 text-indigo-800' },
};

const effectiveStatus = (field: OcrReviewField): OcrReviewStatus =>
  field.review?.review_status || field.status;

const correctedOrOriginal = (field: OcrReviewField): string =>
  field.review?.review_status === 'corrected' && field.review.corrected_value
    ? field.review.corrected_value
    : field.value || '—';

const getPoints = (bbox?: number[][] | null): string =>
  Array.isArray(bbox) ? bbox.map(([x, y]) => `${x},${y}`).join(' ') : '';

const getBounds = (bbox?: number[][] | null) => {
  if (!Array.isArray(bbox) || bbox.length !== 4) return null;
  const xs = bbox.map(([x]) => Number(x));
  const ys = bbox.map(([, y]) => Number(y));
  if (![...xs, ...ys].every(Number.isFinite)) return null;
  return {
    left: Math.min(...xs),
    top: Math.min(...ys),
    right: Math.max(...xs),
    bottom: Math.max(...ys),
  };
};

interface BboxEvidenceCropProps {
  imageUrl: string;
  bbox: number[][];
  label: string;
}

/** Cắt trực tiếp từ preview gốc theo box OCR đã được xác thực.
 * Không phụ thuộc vào crop thô có thể đã bao lẫn barcode/footer trong DB. */
const BboxEvidenceCrop: React.FC<BboxEvidenceCropProps> = ({ imageUrl, bbox, label }) => {
  const [sourceSize, setSourceSize] = useState<{ width: number; height: number } | null>(null);
  const bounds = useMemo(() => getBounds(bbox), [bbox]);

  useEffect(() => setSourceSize(null), [imageUrl]);

  if (!bounds) return null;

  const padding = Math.min(56, Math.max(18, Math.round(Math.max(bounds.right - bounds.left, bounds.bottom - bounds.top) * 0.18)));
  const cropLeft = Math.max(0, bounds.left - padding);
  const cropTop = Math.max(0, bounds.top - padding);
  const cropRight = Math.min(sourceSize?.width ?? bounds.right + padding, bounds.right + padding);
  const cropBottom = Math.min(sourceSize?.height ?? bounds.bottom + padding, bounds.bottom + padding);
  const cropWidth = Math.max(1, cropRight - cropLeft);
  const cropHeight = Math.max(1, cropBottom - cropTop);
  const scale = sourceSize ? Math.min(320 / cropWidth, 148 / cropHeight) : 1;
  const boxPoints = bbox.map(([x, y]) => `${Number(x) - cropLeft},${Number(y) - cropTop}`).join(' ');

  return (
    <div className="relative flex min-h-24 items-center justify-center overflow-hidden rounded-lg border border-slate-200 bg-white p-2">
      <ProtectedImage
        src={imageUrl}
        alt=""
        aria-hidden="true"
        className="absolute h-px w-px opacity-0"
        onLoad={(event) => setSourceSize({
          width: event.currentTarget.naturalWidth,
          height: event.currentTarget.naturalHeight,
        })}
      />
      {sourceSize ? (
        <div
          className="relative overflow-hidden rounded border border-slate-100 bg-slate-100"
          title="Ảnh được cắt trực tiếp từ preview theo box OCR"
          style={{ width: cropWidth * scale, height: cropHeight * scale }}
        >
          <ProtectedImage
            src={imageUrl}
            alt={`Ảnh vùng OCR của ${label}`}
            className="absolute max-w-none"
            style={{
              width: sourceSize.width * scale,
              height: sourceSize.height * scale,
              left: -cropLeft * scale,
              top: -cropTop * scale,
            }}
          />
          <svg
            className="absolute inset-0 h-full w-full"
            viewBox={`0 0 ${cropWidth} ${cropHeight}`}
            preserveAspectRatio="none"
            aria-label={`Box OCR của ${label}`}
          >
            <polygon
              points={boxPoints}
              fill="rgb(16 185 129)"
              fillOpacity="0.18"
              stroke="rgb(5 150 105)"
              strokeWidth="3"
              vectorEffect="non-scaling-stroke"
            />
          </svg>
        </div>
      ) : (
        <span className="flex items-center gap-1.5 text-[11px] text-slate-500">
          <Loader2 size={14} className="animate-spin text-indigo-600" /> Đang cắt vùng OCR...
        </span>
      )}
    </div>
  );
};

export const QuickReviewPanel: React.FC<QuickReviewPanelProps> = ({ documentId, onClose }) => {
  const { can } = useAuth();
  const [data, setData] = useState<OcrDocumentReview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedFieldKey, setSelectedFieldKey] = useState<string | null>(null);
  const [activePageIndex, setActivePageIndex] = useState<number>(0);
  const [zoom, setZoom] = useState(0.48);
  const [imageSize, setImageSize] = useState<{ width: number; height: number } | null>(null);
  const [editing, setEditing] = useState(false);
  const [correctedValue, setCorrectedValue] = useState('');
  const [note, setNote] = useState('');
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    let active = true;
    const load = async () => {
      setLoading(true);
      setError(null);
      try {
        const response = await axios.get<OcrDocumentReview>(
          `/api/v1/pg/records/${encodeURIComponent(documentId)}/review`,
        );
        if (!active) return;
        const nextData = response.data;
        setData(nextData);
        const first = nextData.fields.find((field) =>
          ['needs_review', 'missing', 'no_evidence'].includes(effectiveStatus(field)),
        ) || nextData.fields[0];
        if (first) {
          setSelectedFieldKey(first.key);
          if (first.page_index !== null && first.page_index !== undefined) {
            setActivePageIndex(first.page_index);
          }
        } else if (nextData.pages[0]) {
          setActivePageIndex(nextData.pages[0].page_index);
        }
      } catch (requestError: any) {
        if (active) {
          setError(requestError.response?.data?.detail || 'Không thể tải dữ liệu tra soát.');
        }
      } finally {
        if (active) setLoading(false);
      }
    };
    load();
    return () => {
      active = false;
    };
  }, [documentId]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [onClose]);

  const selectedField = data?.fields.find((field) => field.key === selectedFieldKey) || null;
  const activePage = data?.pages.find((page) => page.page_index === activePageIndex) || data?.pages[0];
  const selectedFieldPage = data?.pages.find((page) => page.page_index === selectedField?.page_index) || activePage;
  const pageFields = useMemo(
    () => (data?.fields || []).filter((field) => field.page_index === activePage?.page_index && field.bbox),
    [data?.fields, activePage?.page_index],
  );
  const groupedFields = useMemo(() => {
    const groups = new Map<string, OcrReviewField[]>();
    (data?.fields || []).forEach((field) => {
      groups.set(field.group, [...(groups.get(field.group) || []), field]);
    });
    return [...groups.entries()];
  }, [data?.fields]);

  const selectField = (field: OcrReviewField) => {
    setSelectedFieldKey(field.key);
    if (field.page_index !== null && field.page_index !== undefined) {
      setActivePageIndex(field.page_index);
    }
    setEditing(false);
    setCorrectedValue(field.review?.corrected_value || field.value || '');
    setNote(field.review?.note || '');
  };

  const updateReview = async (reviewStatus: OcrFieldReview['review_status'], value?: string) => {
    if (!selectedField || saving || !can('record.review')) return;
    setSaving(true);
    try {
      const response = await axios.post(
        `/api/v1/pg/records/${encodeURIComponent(documentId)}/review`,
        {
          field_key: selectedField.key,
          review_status: reviewStatus,
          corrected_value: value,
          note: note.trim() || undefined,
        },
      );
      const review: OcrFieldReview = response.data.review;
      setData((previous) => previous && {
        ...previous,
        fields: previous.fields.map((field) =>
          field.key === selectedField.key ? { ...field, review } : field,
        ),
      });
      setEditing(false);
    } catch (requestError: any) {
      setError(requestError.response?.data?.detail || 'Không thể lưu kết quả tra soát.');
    } finally {
      setSaving(false);
    }
  };

  // Trạng thái Chế độ sửa tất cả (Bulk Edit Mode)
  const [isBulkMode, setIsBulkMode] = useState<boolean>(false);
  const [bulkValues, setBulkValues] = useState<Record<string, string>>({});
  const [bulkNotes, setBulkNotes] = useState<Record<string, string>>({});
  const [bulkSaving, setBulkSaving] = useState<boolean>(false);
  const [bulkSuccessMsg, setBulkSuccessMsg] = useState<string | null>(null);

  const handleToggleBulkMode = () => {
    if (!isBulkMode) {
      const initialVals: Record<string, string> = {};
      const initialNotes: Record<string, string> = {};
      data?.fields.forEach((f) => {
        initialVals[f.key] = f.review?.corrected_value ?? f.value ?? '';
        initialNotes[f.key] = f.review?.note ?? '';
      });
      setBulkValues(initialVals);
      setBulkNotes(initialNotes);
      setIsBulkMode(true);
    } else {
      setIsBulkMode(false);
    }
  };

  const modifiedCount = useMemo(() => {
    if (!isBulkMode || !data) return 0;
    let count = 0;
    data.fields.forEach((f) => {
      const cur = (bulkValues[f.key] ?? '').trim();
      const orig = (f.review?.corrected_value ?? f.value ?? '').trim();
      if (cur !== orig) count++;
    });
    return count;
  }, [isBulkMode, data, bulkValues]);

  const handleSaveBulkChanges = async (alsoConfirmUnedited: boolean = false) => {
    if (!data || bulkSaving || !can('record.review')) return;
    setBulkSaving(true);
    setError(null);
    try {
      const items: any[] = [];
      data.fields.forEach((field) => {
        const cur = (bulkValues[field.key] ?? '').trim();
        const orig = (field.review?.corrected_value ?? field.value ?? '').trim();
        const isModified = cur !== orig;

        if (isModified) {
          items.push({
            field_key: field.key,
            review_status: 'corrected',
            corrected_value: bulkValues[field.key],
            note: bulkNotes[field.key]?.trim() || undefined,
          });
        } else if (alsoConfirmUnedited && effectiveStatus(field) !== 'confirmed') {
          items.push({
            field_key: field.key,
            review_status: 'confirmed',
            corrected_value: field.review?.corrected_value || field.value || undefined,
            note: bulkNotes[field.key]?.trim() || field.review?.note || undefined,
          });
        }
      });

      if (items.length === 0) {
        setBulkSuccessMsg('Không có trường nào thay đổi để lưu.');
        setTimeout(() => setBulkSuccessMsg(null), 3000);
        setBulkSaving(false);
        return;
      }

      const res = await axios.post(
        `/api/v1/pg/records/${encodeURIComponent(documentId)}/reviews/bulk`,
        { items },
      );

      const returnedReviews: OcrFieldReview[] = res.data?.reviews || [];
      const reviewMap = new Map(returnedReviews.map((r) => [r.field_key, r]));

      setData((prev) => {
        if (!prev) return prev;
        return {
          ...prev,
          fields: prev.fields.map((field) => {
            const updated = reviewMap.get(field.key);
            return updated ? { ...field, review: updated } : field;
          }),
        };
      });

      setBulkSuccessMsg(`Đã lưu thành công ${returnedReviews.length} trường!`);
      setTimeout(() => setBulkSuccessMsg(null), 4000);
      setIsBulkMode(false);
    } catch (requestError: any) {
      setError(requestError.response?.data?.detail || 'Không thể lưu danh sách tra soát.');
    } finally {
      setBulkSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center bg-slate-950/65 p-3 backdrop-blur-sm sm:p-6">
      <section
        className="flex h-[94vh] w-full max-w-[1560px] flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-2xl"
        role="dialog"
        aria-modal="true"
        aria-labelledby="quick-review-title"
      >
        <header className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 bg-slate-50 px-4 py-3 sm:px-6">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <h2 id="quick-review-title" className="truncate text-base font-bold text-slate-900">
                {data ? `Tra soát nhanh · ${data.document.file_name}` : 'Tra soát nhanh hồ sơ'}
              </h2>
              {data?.document.template && (
                <span className="rounded-md bg-slate-200 px-2 py-0.5 text-[11px] font-semibold text-slate-700">
                  {data.document.template}
                </span>
              )}
            </div>
            {data && (
              <p className="mt-0.5 text-xs text-slate-500">
                {data.summary.total_fields} trường thiết yếu · {data.summary.needs_review} trường cần xem · không hiển thị 129 cột
              </p>
            )}
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg p-2 text-slate-500 transition hover:bg-slate-200 hover:text-slate-900"
            aria-label="Đóng tra soát nhanh"
          >
            <X size={19} />
          </button>
        </header>

        {loading ? (
          <div className="flex flex-1 items-center justify-center gap-2 text-sm text-slate-500">
            <Loader2 size={18} className="animate-spin text-indigo-600" /> Đang tải bằng chứng OCR...
          </div>
        ) : error && !data ? (
          <div className="flex flex-1 flex-col items-center justify-center gap-3 px-6 text-center">
            <AlertTriangle size={30} className="text-rose-600" />
            <p className="max-w-lg text-sm text-rose-700">{error}</p>
            <button type="button" onClick={onClose} className="rounded-lg bg-slate-900 px-4 py-2 text-xs font-semibold text-white">
              Đóng
            </button>
          </div>
        ) : (
          <div className="grid min-h-0 flex-1 grid-cols-1 lg:grid-cols-[minmax(0,1.45fr)_minmax(350px,.85fr)]">
            <div className="flex min-h-0 flex-col bg-slate-100">
              <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-200 bg-white px-3 py-2 sm:px-4">
                <div className="flex flex-wrap items-center gap-1.5" aria-label="Chọn trang tài liệu">
                  {(data?.pages || []).map((page) => (
                    <button
                      key={page.page_index}
                      type="button"
                      onClick={() => {
                        setActivePageIndex(page.page_index);
                        setImageSize(null);
                      }}
                      className={`rounded-lg px-2.5 py-1.5 text-xs font-semibold transition ${
                        activePage?.page_index === page.page_index
                          ? 'bg-emerald-600 text-white'
                          : 'bg-slate-100 text-slate-700 hover:bg-slate-200'
                      }`}
                    >
                      {page.label}
                    </button>
                  ))}
                </div>
                <div className="flex items-center gap-1 rounded-lg border border-slate-200 bg-slate-50 p-0.5">
                  <button
                    type="button"
                    onClick={() => setZoom((current) => Math.max(0.25, Number((current - 0.1).toFixed(2))))}
                    className="rounded p-1.5 text-slate-600 hover:bg-white"
                    title="Thu nhỏ ảnh"
                    aria-label="Thu nhỏ ảnh"
                  >
                    <ZoomOut size={15} />
                  </button>
                  <span className="min-w-12 text-center text-[11px] font-mono text-slate-600">{Math.round(zoom * 100)}%</span>
                  <button
                    type="button"
                    onClick={() => setZoom((current) => Math.min(1.25, Number((current + 0.1).toFixed(2))))}
                    className="rounded p-1.5 text-slate-600 hover:bg-white"
                    title="Phóng to ảnh"
                    aria-label="Phóng to ảnh"
                  >
                    <ZoomIn size={15} />
                  </button>
                  <button
                    type="button"
                    onClick={() => setZoom(0.48)}
                    className="rounded p-1.5 text-slate-600 hover:bg-white"
                    title="Đặt lại tỷ lệ"
                    aria-label="Đặt lại tỷ lệ"
                  >
                    <RotateCw size={15} />
                  </button>
                </div>
              </div>

              <div className="min-h-0 flex-1 overflow-auto p-4">
                {activePage?.image_url ? (
                  <div
                    className="relative mx-auto w-fit rounded-sm bg-white shadow-md"
                    style={imageSize ? { width: imageSize.width * zoom } : undefined}
                  >
                    <ProtectedImage
                      src={activePage.image_url}
                      alt={`Ảnh gốc ${activePage.label} của hồ sơ`}
                      className={imageSize ? 'block h-auto w-full' : 'block max-w-full'}
                      onLoad={(event) => {
                        setImageSize({
                          width: event.currentTarget.naturalWidth,
                          height: event.currentTarget.naturalHeight,
                        });
                      }}
                    />
                    {imageSize && (
                      <svg
                        className="absolute inset-0 h-full w-full"
                        viewBox={`0 0 ${imageSize.width} ${imageSize.height}`}
                        preserveAspectRatio="none"
                        aria-label="Các vùng OCR được phát hiện"
                      >
                        {pageFields.map((field) => {
                          const selected = field.key === selectedFieldKey;
                          const warning = ['needs_review', 'missing', 'no_evidence'].includes(effectiveStatus(field));
                          return (
                            <g
                              key={field.key}
                              role="button"
                              tabIndex={0}
                              className={selected ? 'cursor-pointer text-emerald-500' : warning ? 'cursor-pointer text-amber-500' : 'cursor-pointer text-sky-500'}
                              aria-label={`Chọn trường ${field.label}`}
                              onClick={() => selectField(field)}
                              onKeyDown={(event) => {
                                if (event.key === 'Enter' || event.key === ' ') {
                                  event.preventDefault();
                                  selectField(field);
                                }
                              }}
                            >
                              <polygon
                                points={getPoints(field.bbox)}
                                fill="currentColor"
                                fillOpacity={selected ? 0.28 : 0.12}
                                stroke="currentColor"
                                strokeWidth={selected ? 5 : 3}
                                vectorEffect="non-scaling-stroke"
                              />
                            </g>
                          );
                        })}
                      </svg>
                    )}
                  </div>
                ) : (
                  <div className="flex h-full min-h-72 flex-col items-center justify-center gap-2 text-center text-slate-500">
                    <ImageIcon size={30} className="text-slate-400" />
                    <p className="text-sm font-semibold text-slate-700">Chưa có ảnh preview cho {activePage?.label || 'trang này'}</p>
                    <p className="max-w-sm text-xs">Dữ liệu trường vẫn có thể được tra soát, nhưng không thể vẽ box trên ảnh.</p>
                  </div>
                )}
              </div>
            </div>

            <aside className="min-h-0 flex flex-col overflow-hidden border-t border-slate-200 bg-white lg:border-l lg:border-t-0">
              {/* Toolbar tiêu đề của bảng tra soát */}
              <div className="flex items-center justify-between border-b border-slate-200 bg-slate-50/80 px-4 py-2.5 shrink-0">
                <div className="flex items-center gap-2">
                  <span className="text-xs font-bold text-slate-800">
                    {isBulkMode ? '✏️ Chế độ sửa tất cả' : '📋 Danh sách trường OCR'}
                  </span>
                  {isBulkMode && (
                    <span className="rounded-full bg-indigo-100 px-2 py-0.5 text-[10px] font-bold text-indigo-800">
                      Đã sửa {modifiedCount} trường
                    </span>
                  )}
                </div>
                {can('record.review') && (
                  <button
                    type="button"
                    onClick={handleToggleBulkMode}
                    className={`inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs font-semibold transition cursor-pointer ${
                      isBulkMode
                        ? 'bg-amber-100 text-amber-900 hover:bg-amber-200'
                        : 'bg-indigo-50 text-indigo-700 hover:bg-indigo-100 border border-indigo-200'
                    }`}
                  >
                    <Edit3 size={13} />
                    {isBulkMode ? 'Thoát sửa tất cả' : 'Sửa tất cả & lưu 1 lần'}
                  </button>
                )}
              </div>

              {/* Danh sách trường có thể scroll */}
              <div className="min-h-0 flex-1 overflow-y-auto space-y-4 p-4">
                {bulkSuccessMsg && (
                  <div className="rounded-xl border border-emerald-200 bg-emerald-50 px-3.5 py-2.5 text-xs font-bold text-emerald-800 shadow-2xs">
                    {bulkSuccessMsg}
                  </div>
                )}
                {groupedFields.map(([group, fields]) => (
                  <section key={group} aria-label={group}>
                    <h3 className="mb-1.5 text-[11px] font-bold uppercase tracking-wider text-slate-500">{group}</h3>
                    <div className="overflow-hidden rounded-xl border border-slate-200">
                      {fields.map((field) => {
                        const isSelected = field.key === selectedFieldKey;
                        const status = effectiveStatus(field);
                        const config = STATUS_CONFIG[status];
                        const isFieldModified = isBulkMode && (bulkValues[field.key] ?? '').trim() !== (field.review?.corrected_value ?? field.value ?? '').trim();

                        return (
                          <div
                            key={field.key}
                            onClick={() => selectField(field)}
                            className={`block w-full border-b border-slate-100 px-3 py-2.5 text-left transition cursor-pointer last:border-b-0 ${
                              isSelected ? 'bg-emerald-50/70 ring-1 ring-inset ring-emerald-300' : isFieldModified ? 'bg-indigo-50/40' : 'hover:bg-slate-50'
                            }`}
                          >
                            <div className="flex items-start justify-between gap-2">
                              <span className="text-[11px] font-semibold text-slate-600">{field.label}</span>
                              <div className="flex items-center gap-1">
                                {isFieldModified && (
                                  <span className="shrink-0 rounded-full bg-indigo-100 px-1.5 py-0.5 text-[9px] font-bold text-indigo-800">
                                    Đã sửa
                                  </span>
                                )}
                                <span className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] font-bold ${config.className}`}>
                                  {config.label}
                                </span>
                              </div>
                            </div>

                            {isBulkMode ? (
                              <div className="mt-1.5 space-y-1" onClick={(e) => e.stopPropagation()}>
                                <input
                                  type="text"
                                  value={bulkValues[field.key] ?? ''}
                                  onChange={(e) => {
                                    setBulkValues((prev) => ({ ...prev, [field.key]: e.target.value }));
                                  }}
                                  onFocus={() => {
                                    if (selectedFieldKey !== field.key) selectField(field);
                                  }}
                                  placeholder="Nhập giá trị chuẩn..."
                                  className={`w-full rounded-lg border px-2.5 py-1.5 text-xs font-bold outline-none transition ${
                                    isFieldModified
                                      ? 'border-indigo-500 bg-white text-indigo-950 ring-2 ring-indigo-500/20 shadow-2xs'
                                      : 'border-slate-300 bg-white text-slate-900 focus:border-indigo-500'
                                  }`}
                                />
                                <div className="flex items-center justify-between text-[10px] text-slate-400">
                                  <span className="truncate max-w-[200px]" title={field.value || ''}>OCR: {field.value || '—'}</span>
                                  {field.confidence !== null && field.confidence !== undefined && (
                                    <span className="font-mono shrink-0">{Math.round(field.confidence * 100)}%</span>
                                  )}
                                </div>
                              </div>
                            ) : (
                              <>
                                <div className="mt-0.5 flex items-center justify-between gap-2">
                                  <span className="truncate text-sm font-bold text-slate-900">{correctedOrOriginal(field)}</span>
                                  {field.confidence !== null && field.confidence !== undefined && (
                                    <span className="shrink-0 font-mono text-[10px] text-slate-500">{Math.round(field.confidence * 100)}%</span>
                                  )}
                                </div>
                                {field.review?.review_status === 'corrected' && (
                                  <span className="mt-0.5 block truncate text-[10px] text-slate-500">OCR: {field.value || '—'}</span>
                                )}
                              </>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  </section>
                ))}

                {selectedField && (
                  <section className="rounded-xl border border-slate-200 bg-slate-50 p-3" aria-label="Bằng chứng OCR của trường đang chọn">
                    <div className="mb-2 flex items-center justify-between gap-2">
                      <span className="flex items-center gap-1.5 text-xs font-bold text-slate-800">
                        <Eye size={14} className="text-indigo-600" /> Bằng chứng OCR
                      </span>
                      {selectedField.page_index !== null && selectedField.page_index !== undefined && (
                        <span className="text-[10px] font-medium text-slate-500">Trang {selectedField.page_index + 1}</span>
                      )}
                    </div>
                    {selectedField.bbox && selectedFieldPage?.image_url ? (
                      <BboxEvidenceCrop
                        imageUrl={selectedFieldPage.image_url}
                        bbox={selectedField.bbox}
                        label={selectedField.label}
                      />
                    ) : selectedField.crop_url ? (
                      <div className="flex min-h-20 items-center justify-center overflow-hidden rounded-lg border border-slate-200 bg-white p-2">
                        <ProtectedImage src={selectedField.crop_url} alt={`Ảnh crop của ${selectedField.label}`} className="max-h-28 max-w-full object-contain" />
                      </div>
                    ) : (
                      <div className="rounded-lg border border-dashed border-slate-300 bg-white px-3 py-4 text-center text-[11px] text-slate-500">
                        {selectedField.bbox ? 'Có box trên trang nhưng chưa có ảnh crop.' : 'Chưa tìm được crop hoặc box tương ứng.'}
                      </div>
                    )}
                    {selectedField.bbox && selectedFieldPage?.image_url && (
                      <p className="mt-1.5 text-[10px] text-slate-500">Cắt trực tiếp từ trang gốc theo box OCR đã chọn.</p>
                    )}
                    <p className="mt-2 break-words text-[11px] leading-relaxed text-slate-600">
                      OCR: <span className="font-medium text-slate-800">{selectedField.source_text || '—'}</span>
                    </p>
                    {selectedField.selection_reason && (
                      <p className="mt-1 text-[10px] text-slate-500">Nguồn: {selectedField.selection_reason}</p>
                    )}

                    <div className="mt-3 border-t border-slate-200 pt-3">
                      {!can('record.review') && <p className="text-[11px] text-slate-500">Bạn chỉ có quyền xem bằng chứng OCR của hồ sơ này.</p>}
                      {can('record.review') && !isBulkMode && (
                        <>
                      {!editing ? (
                        <div className="flex flex-wrap gap-2">
                          <button
                            type="button"
                            onClick={() => updateReview('confirmed')}
                            disabled={saving}
                            className="inline-flex items-center gap-1.5 rounded-lg bg-emerald-600 px-3 py-2 text-xs font-bold text-white transition hover:bg-emerald-700 disabled:opacity-50"
                          >
                            {saving ? <Loader2 size={13} className="animate-spin" /> : <Check size={13} />}
                            Xác nhận đúng
                          </button>
                          <button
                            type="button"
                            onClick={() => {
                              setCorrectedValue(selectedField.review?.corrected_value || selectedField.value || '');
                              setNote(selectedField.review?.note || '');
                              setEditing(true);
                            }}
                            className="inline-flex items-center gap-1.5 rounded-lg border border-indigo-300 bg-white px-3 py-2 text-xs font-bold text-indigo-700 transition hover:bg-indigo-50"
                          >
                            <Pencil size={13} /> Sai / chỉnh lại
                          </button>
                        </div>
                      ) : (
                        <div className="space-y-2">
                          <label className="block text-[11px] font-semibold text-slate-700">
                            Giá trị đã chỉnh
                            <input
                              autoFocus
                              value={correctedValue}
                              onChange={(event) => setCorrectedValue(event.target.value)}
                              className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-2.5 py-2 text-sm text-slate-900 outline-none ring-indigo-500 focus:ring-2"
                            />
                          </label>
                          <label className="block text-[11px] font-semibold text-slate-700">
                            Ghi chú (không bắt buộc)
                            <input
                              value={note}
                              onChange={(event) => setNote(event.target.value)}
                              className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-2.5 py-2 text-sm text-slate-900 outline-none ring-indigo-500 focus:ring-2"
                            />
                          </label>
                          <div className="flex gap-2">
                            <button
                              type="button"
                              onClick={() => updateReview('corrected', correctedValue)}
                              disabled={saving || !correctedValue.trim()}
                              className="inline-flex items-center gap-1.5 rounded-lg bg-indigo-600 px-3 py-2 text-xs font-bold text-white transition hover:bg-indigo-700 disabled:opacity-50"
                            >
                              {saving ? <Loader2 size={13} className="animate-spin" /> : <Save size={13} />} Lưu chỉnh sửa
                            </button>
                            <button
                              type="button"
                              onClick={() => setEditing(false)}
                              disabled={saving}
                              className="rounded-lg px-3 py-2 text-xs font-semibold text-slate-600 hover:bg-slate-200"
                            >
                              Hủy
                            </button>
                          </div>
                        </div>
                      )}
                        </>
                      )}
                    </div>
                  </section>
                )}
                {error && <p role="alert" className="text-xs font-medium text-rose-700">{error}</p>}
              </div>

              {/* Sticky footer action bar for bulk editing */}
              {isBulkMode && can('record.review') && (
                <div className="border-t border-slate-200 bg-white/95 p-3.5 backdrop-blur-sm shadow-xl shrink-0 space-y-2.5">
                  <div className="flex items-center justify-between text-xs">
                    <span className="text-slate-600 font-medium">
                      Đã sửa: <strong className="text-indigo-600 font-bold">{modifiedCount}</strong> trường
                    </span>
                    <span className="text-[11px] text-slate-400">
                      Lưu tất cả thay đổi cùng lúc
                    </span>
                  </div>
                  <div className="flex gap-2">
                    <button
                      type="button"
                      onClick={() => handleSaveBulkChanges(false)}
                      disabled={bulkSaving || modifiedCount === 0}
                      className="flex-1 inline-flex items-center justify-center gap-1.5 rounded-xl bg-indigo-600 py-2.5 text-xs font-bold text-white shadow-sm hover:bg-indigo-700 disabled:opacity-40 transition cursor-pointer disabled:cursor-not-allowed"
                    >
                      {bulkSaving ? <Loader2 size={14} className="animate-spin" /> : <Save size={14} />}
                      <span>Lưu tất cả ({modifiedCount})</span>
                    </button>
                    <button
                      type="button"
                      onClick={() => handleSaveBulkChanges(true)}
                      disabled={bulkSaving}
                      title="Lưu tất cả trường đã sửa và xác nhận đúng các trường còn lại"
                      className="inline-flex items-center justify-center gap-1.5 rounded-xl bg-emerald-600 px-3 py-2.5 text-xs font-bold text-white shadow-sm hover:bg-emerald-700 disabled:opacity-40 transition cursor-pointer"
                    >
                      <CheckCheck size={14} />
                      <span>Xác nhận tất cả</span>
                    </button>
                    <button
                      type="button"
                      onClick={() => setIsBulkMode(false)}
                      disabled={bulkSaving}
                      className="rounded-xl border border-slate-200 bg-slate-100 px-3 py-2.5 text-xs font-semibold text-slate-600 hover:bg-slate-200 transition cursor-pointer"
                    >
                      Hủy
                    </button>
                  </div>
                </div>
              )}
            </aside>
          </div>
        )}
      </section>
    </div>
  );
};
