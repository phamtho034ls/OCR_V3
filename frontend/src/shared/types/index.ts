export interface CropItem {
  url: string;
  paddle_text?: string;
  paddle_conf?: number;
  viet_text?: string;
  viet_conf?: number;
  final_text?: string;
  final_conf?: number;
  raw_text?: string;
  pruned_text?: string;
  removed_border_tokens?: string[];
  crop_size?: [number, number];
  bbox?: number[][];
}

export interface PageResult {
  page_index: number;
  file_name?: string;
  preview_url: string;
  mau?: string;
  so_phat_hanh?: string;
  diagram_url?: string;
  crops?: CropItem[];
  ocr_results?: any[];
  raw_fields?: Record<string, any>;
}

export interface ParcelItem {
  stt?: number;
  so_thua?: string;
  to_ban_do?: string;
  dia_chi?: string;
  dien_tich?: number | string;
  dien_tich_rieng?: number | string;
  dien_tich_chung?: number | string;
  dien_tich_tong?: number | string;
  muc_dich_su_dung?: string;
  ma_muc_dich?: string;
  thoi_han?: string;
  thoi_han_su_dung?: string;
  nguon_goc?: string;
  nguon_goc_su_dung?: string;
  nguon_goc_ky_hieu?: string;
  [key: string]: any;
}

export interface DocumentResult {
  document_id: string;
  file_name: string;
  mau?: string;
  template?: string;
  so_phat_hanh?: string;
  ma_vach?: string;
  so_vao_so?: string;
  loai_cap?: string;
  dot_cap_gcn?: string;
  dong_su_dung?: string;
  tong_thoi_gian_sec?: number;
  preview_url?: string;
  pages?: PageResult[];
  crops?: CropItem[];
  attachments?: {
    so_do_thua_dat?: string;
    [key: string]: any;
  };
  nguoi_su_dung?: {
    ho_ten_chu_1?: string;
    cmnd_chu_1?: string;
    ngay_sinh_chu_1?: string;
    ho_ten_chu_2?: string;
    cmnd_chu_2?: string;
    ngay_sinh_chu_2?: string;
    ho_ten_goc?: string;
    loai_chu?: string;
    dia_chi_thuong_tru?: string;
    [key: string]: any;
  };
  thua_dat?: {
    so_thua?: string;
    to_ban_do?: string;
    ty_le?: string;
    dien_tich_cap?: string;
    dien_tich_rieng?: string;
    dien_tich_chung?: string;
    dien_tich_chu?: string;
    dien_tich_validated?: boolean;
    dia_chi?: string;
    muc_dich_su_dung?: string;
    ma_muc_dich?: string;
    thoi_han_su_dung?: string;
    thoi_han?: string;
    nguon_goc_su_dung?: string;
    nguon_goc?: string;
    nguon_goc_ky_hieu?: string;
    danh_sach_thua?: ParcelItem[];
    [key: string]: any;
  };
  tai_san?: {
    nha_o?: string;
    cong_trinh_khac?: string;
    rung_cay?: string;
    ghi_chu?: string;
    [key: string]: any;
  };
  cap_gcn?: {
    noi_cap?: string;
    ngay_cap?: string;
    nguoi_ky_qd?: string;
    chuc_vu_nguoi_ky?: string;
    so_quyet_dinh?: string;
    ngay_vao_so?: string;
    so_ho_so_goc?: string;
    [key: string]: any;
  };
  bien_dong?: {
    thong_tin_bien_dong?: string;
    ten_chuyen_nhuong_1?: string;
    cmnd_chuyen_nhuong_1?: string;
    ten_chuyen_nhuong_2?: string;
    cmnd_chuyen_nhuong_2?: string;
    ngay_chuyen_nhuong?: string;
    nguoi_ky_xac_nhan?: string;
    so_ho_so_bien_dong?: string;
    [key: string]: any;
  };
  confidence?: Record<string, number>;
  can_review?: string[];
  chuyen_doi_rows?: Record<string, any>[];
  [key: string]: any;
}

export interface ChuyenDoiColumn {
  index: number;
  code: string;
  label: string;
  section: string;
  section_title: string;
}

export interface JobProgress {
  job_id: string;
  status: 'queued' | 'running' | 'completed' | 'failed' | 'cancelled';
  total_files: number;
  processed_files: number;
  current_file?: string;
  progress_percentage: number;
}

export interface BatchItemSummary {
  stt: number;
  file_name: string;
  status: 'success' | 'error' | 'processing' | 'waiting';
  elapsed_seconds?: number;
  mau?: string;
  so_phat_hanh?: string;
  so_vao_so?: string;
  ma_vach?: string;
  ten_chu?: string;
  cmnd?: string;
  so_thua?: string;
  to_ban_do?: string;
  dien_tich?: string;
  dia_chi_thua?: string;
  document_id?: string;
  raw_ocr_markdown?: string;
  error?: string;
  data?: DocumentResult;
}

export interface BatchProgressResponse {
  batch_id: string;
  status: 'processing' | 'done' | 'error' | 'cancelled' | 'unknown';
  total_files: number;
  processed_count: number;
  progress_percent: number;
  current_file?: string;
  elapsed_seconds: number;
  speed_files_per_min: number;
  results: BatchItemSummary[];
  chuyen_doi_rows: Record<string, any>[];
  last_checkpoint_idx?: number;
  last_checkpoint_time?: string;
  checkpoint_excel_url?: string;
  checkpoint_excel_name?: string;
  last_checkpoint_message?: string;
  error?: string;
}

