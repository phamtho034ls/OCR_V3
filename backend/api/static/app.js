// app.js - Frontend logic cho Hệ thống OCR Sổ Đỏ / Sổ Hồng

let currentResult = null;
let currentBBoxes = [];
let batchResultsList = [];
let batchPollingTimer = null;
let currentRotation = 0;

// Khởi chạy khi load trang
document.addEventListener("DOMContentLoaded", () => {
  checkHealth();
  loadReviewQueue();
});

// ─── Tab Switching ──────────────────────────────────────────────────────────
function switchTab(tabId) {
  document.querySelectorAll(".tab-content").forEach(el => el.classList.add("hidden"));
  document.querySelectorAll(".tab-btn").forEach(btn => {
    btn.classList.remove("border-brand-600", "text-brand-700", "font-semibold");
    btn.classList.add("border-transparent", "text-slate-500", "font-medium");
  });

  const targetTab = document.getElementById(`tab-${tabId}`);
  const targetBtn = document.getElementById(`tab-btn-${tabId}`);

  if (targetTab) targetTab.classList.remove("hidden");
  if (targetBtn) {
    targetBtn.classList.remove("border-transparent", "text-slate-500", "font-medium");
    targetBtn.classList.add("border-brand-600", "text-brand-700", "font-semibold");
  }

  if (tabId === "review") {
    loadReviewQueue();
  }
  if (tabId === "batch") {
    // Tự động mở rộng giao diện ra Full Màn Hình (99vw) để hiển thị bảng 129 cột
    const mainCont = document.getElementById("main-container");
    if (mainCont) {
      mainCont.classList.remove("max-w-7xl");
      mainCont.classList.add("max-w-[99vw]", "px-2", "sm:px-4");
    }

    if (chuyenDoiColumns.length === 0) {
      loadChuyenDoiColumns().then(() => {
        if (chuyenDoiRows.length === 0) {
          autoMapLatestResults();
        } else {
          renderChuyenDoiGrid(chuyenDoiRows);
          updateChuyenDoiStatus(chuyenDoiRows.length);
        }
      });
    } else {
      if (chuyenDoiRows.length === 0) {
        autoMapLatestResults();
      } else {
        renderChuyenDoiGrid(chuyenDoiRows);
        updateChuyenDoiStatus(chuyenDoiRows.length);
      }
    }
  } else {
    // Thu gọn lại khổ chuẩn cho các tab khác (single, review)
    const mainCont = document.getElementById("main-container");
    if (mainCont) {
      mainCont.classList.add("max-w-7xl");
      mainCont.classList.remove("max-w-[99vw]", "px-2", "sm:px-4");
    }
  }
}

// ─── Health Check ────────────────────────────────────────────────────────────
async function checkHealth() {
  const dot = document.getElementById("status-dot");
  const text = document.getElementById("status-text");

  try {
    const res = await fetch("/health");
    if (!res.ok) throw new Error("Server error");
    const data = await res.json();
    
    dot.className = "w-2.5 h-2.5 rounded-full bg-emerald-500";
    text.innerText = `Hệ thống sẵn sàng (Pipeline: ${data.pipeline_loaded ? "Đã nạp" : "Sẵn sàng"})`;
    
    if (data.review_queue_size > 0) {
      const badge = document.getElementById("review-count-badge");
      badge.innerText = data.review_queue_size;
      badge.classList.remove("hidden");
    }
  } catch (err) {
    dot.className = "w-2.5 h-2.5 rounded-full bg-rose-500";
    text.innerText = "Mất kết nối API Server";
  }
}

// ─── Single File OCR ─────────────────────────────────────────────────────────
async function handleSingleFileSelect(event) {
  const file = event.target.files[0];
  if (!file) return;

  const uploadContainer = document.getElementById("upload-container");
  const loading = document.getElementById("single-loading");
  const resultView = document.getElementById("single-result-view");

  uploadContainer.classList.add("hidden");
  loading.classList.remove("hidden");
  resultView.classList.add("hidden");

  const formData = new FormData();
  formData.append("file", file);

  try {
    const startTime = performance.now();
    const res = await fetch("/ocr", {
      method: "POST",
      body: formData
    });

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "Lỗi xử lý OCR");
    }

    const data = await res.json();
    const duration = ((performance.now() - startTime) / 1000).toFixed(1);
    
    currentResult = data;
    renderSingleResult(data, duration, file.name);

    loading.classList.add("hidden");
    resultView.classList.remove("hidden");
  } catch (err) {
    alert(`Lỗi OCR: ${err.message}`);
    loading.classList.add("hidden");
    uploadContainer.classList.remove("hidden");
  }
}

let activePageIndex = 0;

function formatWebUrl(rawPath) {
  if (!rawPath) return "";
  let clean = String(rawPath).replace(/\\/g, "/");
  const outIdx = clean.indexOf("/output/");
  if (outIdx !== -1) {
    return clean.substring(outIdx);
  }
  const outIdx2 = clean.indexOf("output/");
  if (outIdx2 !== -1) {
    return "/" + clean.substring(outIdx2);
  }
  if (!clean.startsWith("/") && !clean.startsWith("http")) {
    clean = "/" + clean;
  }
  return clean;
}

function switchPreviewPage(pageIndex) {
  if (!currentResult || !currentResult.pages || !currentResult.pages[pageIndex]) return;
  activePageIndex = pageIndex;
  const page = currentResult.pages[pageIndex];
  
  // Cập nhật ảnh preview
  const img = document.getElementById("preview-image");
  if (page.preview_url) {
    const rawUrl = formatWebUrl(page.preview_url);
    img.src = rawUrl + (rawUrl.includes("?") ? "&" : "?") + "v=" + Date.now();
  }
  
  // Cập nhật tag trang
  document.getElementById("img-meta-tag").innerText = `Trang ${pageIndex + 1}/${currentResult.pages.length}`;
  
  // Cập nhật active button
  document.querySelectorAll(".page-switch-btn").forEach((btn, idx) => {
    if (idx === pageIndex) {
      btn.className = "page-switch-btn px-2.5 py-1 text-xs font-bold rounded-lg bg-brand-600 text-white shadow-sm";
    } else {
      btn.className = "page-switch-btn px-2.5 py-1 text-xs font-medium rounded-lg bg-slate-100 text-slate-700 hover:bg-slate-200";
    }
  });
  
  // Cập nhật Bounding Boxes
  currentBBoxes = page.ocr_results || [];
  drawBoundingBoxes();
}

function renderSingleResult(data, duration, filename) {
  document.getElementById("res-doc-id").innerText = filename || data.job_id || "GCN Thửa Đất";
  document.getElementById("res-time-tag").innerText = `Thời gian xử lý: ${duration}s (${data.processing_time_ms || 0}ms)`;

  // Mẫu template badge
  const tmplBadge = document.getElementById("res-template-badge");
  tmplBadge.innerText = data.mau === "mau_A" ? "Mẫu A (Sổ đỏ cũ)" : (data.mau === "mau_B" ? "Mẫu B (Sổ hồng)" : data.mau);
  tmplBadge.className = data.mau === "mau_B" ? "badge-high text-xs px-2.5 py-0.5 rounded-full font-bold" : "badge-med text-xs px-2.5 py-0.5 rounded-full font-bold";

  // Hiển thị Preview Ảnh & Page Switcher
  const pages = data.pages || [];
  const pageBar = document.getElementById("page-switcher-bar");
  pageBar.innerHTML = "";
  
  if (pages.length > 1) {
    pageBar.classList.remove("hidden");
    pages.forEach((p, idx) => {
      const btn = document.createElement("button");
      btn.innerText = `Trang ${idx + 1}`;
      btn.className = idx === (data.selected_page_index || 0) 
        ? "page-switch-btn px-2.5 py-1 text-xs font-bold rounded-lg bg-brand-600 text-white shadow-sm"
        : "page-switch-btn px-2.5 py-1 text-xs font-medium rounded-lg bg-slate-100 text-slate-700 hover:bg-slate-200";
      btn.onclick = () => switchPreviewPage(idx);
      pageBar.appendChild(btn);
    });
  } else {
    pageBar.classList.add("hidden");
  }

  activePageIndex = data.selected_page_index || 0;
  const initialPage = pages[activePageIndex] || {};
  const previewImg = document.getElementById("preview-image");
  
  previewImg.onload = () => {
    drawBoundingBoxes();
  };
  
  const initialPreviewUrl = data.preview_url || initialPage.preview_url || "";
  if (initialPreviewUrl) {
    const rawUrl = formatWebUrl(initialPreviewUrl);
    previewImg.src = rawUrl + (rawUrl.includes("?") ? "&" : "?") + "v=" + Date.now();
  }
  
  document.getElementById("img-meta-tag").innerText = `Trang ${activePageIndex + 1}/${pages.length || 1}`;

  // Định danh & Mã sổ
  document.getElementById("f-so-phat-hanh").value = data.so_phat_hanh || "";
  document.getElementById("f-so-vao-so").value = data.so_vao_so || "";
  document.getElementById("f-ma-vach").value = data.ma_vach || "";
  const loaiCapArr = [data.loai_cap, data.dot_cap_gcn].filter(Boolean);
  document.getElementById("f-loai-cap").value = loaiCapArr.join(" - ") || "";

  // Người sử dụng đất / Chủ sở hữu (Tách đôi Chồng & Vợ)
  const nguoi = data.nguoi_su_dung || {};
  const c1_ten = nguoi.ho_ten_chu_1 || (nguoi.ten ? nguoi.ten.split(/,\s*vợ\s*là\s*bà|,\s*chồng\s*là\s*ông|\s+và\s+/i)[0].trim() : "");
  const c1_cccd = nguoi.cmnd_chu_1 || (nguoi.cmnd ? String(nguoi.cmnd).split(/[,;]\s*/)[0].trim() : "");
  const c1_dob = nguoi.ngay_sinh_chu_1 || (nguoi.ngay_sinh ? String(nguoi.ngay_sinh).split(/[,;]\s*/)[0].trim() : "");

  let c2_ten = nguoi.ho_ten_chu_2 || "";
  if (!c2_ten && nguoi.ten && /(?:vợ\s*là\s*bà|chồng\s*là\s*ông|\s+và\s+bà)/i.test(nguoi.ten)) {
    const parts = nguoi.ten.split(/(?:,\s*vợ\s*là\s*bà|,\s*chồng\s*là\s*ông|\s+và\s+bà|\s+và\s+vợ\s+là\s+bà)/i);
    if (parts.length > 1) c2_ten = "Bà: " + parts[1].trim();
  }
  const c2_cccd = nguoi.cmnd_chu_2 || (nguoi.cmnd && String(nguoi.cmnd).includes(",") ? String(nguoi.cmnd).split(/[,;]\s*/)[1].trim() : "");
  const c2_dob = nguoi.ngay_sinh_chu_2 || (nguoi.ngay_sinh && String(nguoi.ngay_sinh).includes(",") ? String(nguoi.ngay_sinh).split(/[,;]\s*/)[1].trim() : "");

  if (document.getElementById("f-ho-ten-chu-1")) document.getElementById("f-ho-ten-chu-1").value = c1_ten;
  if (document.getElementById("f-cmnd-chu-1")) document.getElementById("f-cmnd-chu-1").value = c1_cccd;
  if (document.getElementById("f-ngay-sinh-chu-1")) document.getElementById("f-ngay-sinh-chu-1").value = c1_dob;

  if (document.getElementById("f-ho-ten-chu-2")) document.getElementById("f-ho-ten-chu-2").value = c2_ten;
  if (document.getElementById("f-cmnd-chu-2")) document.getElementById("f-cmnd-chu-2").value = c2_cccd;
  if (document.getElementById("f-ngay-sinh-chu-2")) document.getElementById("f-ngay-sinh-chu-2").value = c2_dob;

  if (document.getElementById("f-ho-ten")) document.getElementById("f-ho-ten").value = nguoi.ten || "";
  if (document.getElementById("f-cmnd")) document.getElementById("f-cmnd").value = nguoi.cmnd || "";
  if (document.getElementById("f-ngay-sinh")) document.getElementById("f-ngay-sinh").value = nguoi.ngay_sinh || "";
  if (document.getElementById("f-ho-ten-goc")) document.getElementById("f-ho-ten-goc").value = nguoi.ho_ten_goc || "";
  if (document.getElementById("f-loai-chu")) document.getElementById("f-loai-chu").value = nguoi.loai_chu || "";
  if (document.getElementById("f-dong-su-dung")) document.getElementById("f-dong-su-dung").value = data.dong_su_dung || "Không";
  if (document.getElementById("f-dia-chi-tt")) document.getElementById("f-dia-chi-tt").value = nguoi.dia_chi_thuong_tru || "";

  // Thửa đất
  const thua = data.thua_dat || {};
  document.getElementById("f-so-thua").value = thua.so_thua || "";
  document.getElementById("f-to-ban-do").value = thua.to_ban_do || "";
  document.getElementById("f-ty-le").value = thua.ty_le || "";
  document.getElementById("f-dien-tich").value = thua.dien_tich_cap || "";
  document.getElementById("f-dien-tich-rieng").value = thua.dien_tich_rieng || "";
  document.getElementById("f-dien-tich-chung").value = thua.dien_tich_chung || "0";
  document.getElementById("f-dien-tich-chu").value = thua.dien_tich_chu || "";
  document.getElementById("f-dia-chi-thua").value = thua.dia_chi || "";
  document.getElementById("f-muc-dich").value = thua.muc_dich_su_dung || "";
  document.getElementById("f-ma-muc-dich").value = thua.ma_muc_dich || "";
  document.getElementById("f-thoi-han").value = thua.thoi_han || "";
  document.getElementById("f-nguon-goc").value = thua.nguon_goc || "";
  document.getElementById("f-ma-nguon-goc").value = thua.nguon_goc_ky_hieu || "";

  // Diện tích validate tag
  const dtTag = document.getElementById("dt-validate-tag");
  if (thua.dien_tich_validated) {
    dtTag.className = "text-xs px-2 py-0.5 rounded font-semibold bg-emerald-100 text-emerald-800";
    dtTag.innerText = "✓ Khớp 100% Số & Chữ";
  } else if (thua.dien_tich_chu) {
    dtTag.className = "text-xs px-2 py-0.5 rounded font-semibold bg-amber-100 text-amber-800";
    dtTag.innerText = "Cần kiểm tra đối soát";
  } else {
    dtTag.className = "text-xs px-2 py-0.5 rounded font-semibold bg-slate-100 text-slate-600";
    dtTag.innerText = "Chưa đối soát";
  }

  // Tài sản gắn liền với đất & Ghi chú
  const taisan = data.tai_san || {};
  document.getElementById("f-nha-o").value = taisan.nha_o || "-";
  document.getElementById("f-cong-trinh").value = taisan.cong_trinh_khac || "-";
  document.getElementById("f-rung-cay").value = taisan.rung_cay || "-";
  document.getElementById("f-ghi-chu").value = taisan.ghi_chu || "";

  // Cấp GCN
  const cap = data.cap_gcn || {};
  document.getElementById("f-noi-cap").value = cap.noi_cap || "";
  document.getElementById("f-ngay-cap").value = cap.ngay_cap || "";
  const nguoiKyArr = [];
  if (cap.chuc_vu_nguoi_ky) nguoiKyArr.push(cap.chuc_vu_nguoi_ky);
  if (cap.nguoi_ky_qd) nguoiKyArr.push(cap.nguoi_ky_qd);
  document.getElementById("f-nguoi-ky").value = nguoiKyArr.join(" - ") || cap.nguoi_ky_qd || "";
  document.getElementById("f-so-quyet-dinh").value = cap.so_quyet_dinh || "";
  document.getElementById("f-ngay-vao-so").value = cap.ngay_vao_so || "";
  document.getElementById("f-so-ho-so-goc").value = cap.so_ho_so_goc || "";

  // Biến động / Chuyển nhượng sau cấp (Mục IV / Mục V - Tách đôi Chồng & Vợ)
  const bd = data.bien_dong || {};
  const bd_c1_t = bd.ten_chuyen_nhuong_1 || (bd.ten_chuyen_nhuong_moi ? bd.ten_chuyen_nhuong_moi.split(/,\s*vợ\s*là\s*bà|,\s*chồng\s*là\s*ông|\s+và\s+/i)[0].trim() : "");
  const bd_c1_c = bd.cmnd_chuyen_nhuong_1 || (bd.cmnd_chuyen_nhuong ? String(bd.cmnd_chuyen_nhuong).split(/[,;]\s*/)[0].trim() : "");
  
  let bd_c2_t = bd.ten_chuyen_nhuong_2 || "";
  if (!bd_c2_t && bd.ten_chuyen_nhuong_moi && /(?:vợ\s*là\s*bà|chồng\s*là\s*ông|\s+và\s+bà)/i.test(bd.ten_chuyen_nhuong_moi)) {
    const parts = bd.ten_chuyen_nhuong_moi.split(/(?:,\s*vợ\s*là\s*bà|,\s*chồng\s*là\s*ông|\s+và\s+bà|\s+và\s+vợ\s+là\s+bà)/i);
    if (parts.length > 1) bd_c2_t = "Bà: " + parts[1].trim();
  }
  const bd_c2_c = bd.cmnd_chuyen_nhuong_2 || (bd.cmnd_chuyen_nhuong && String(bd.cmnd_chuyen_nhuong).includes(",") ? String(bd.cmnd_chuyen_nhuong).split(/[,;]\s*/)[1].trim() : "");

  if (document.getElementById("f-bien-dong")) document.getElementById("f-bien-dong").value = bd.thong_tin_bien_dong || "";
  if (document.getElementById("f-bd-chu-1")) document.getElementById("f-bd-chu-1").value = bd_c1_t;
  if (document.getElementById("f-bd-cmnd-1")) document.getElementById("f-bd-cmnd-1").value = bd_c1_c;
  if (document.getElementById("f-bd-chu-2")) document.getElementById("f-bd-chu-2").value = bd_c2_t;
  if (document.getElementById("f-bd-cmnd-2")) document.getElementById("f-bd-cmnd-2").value = bd_c2_c;
  if (document.getElementById("f-bd-chu-moi")) document.getElementById("f-bd-chu-moi").value = bd.ten_chuyen_nhuong_moi || "";
  if (document.getElementById("f-bd-cmnd")) document.getElementById("f-bd-cmnd").value = bd.cmnd_chuyen_nhuong || "";
  if (document.getElementById("f-bd-ngay")) document.getElementById("f-bd-ngay").value = bd.ngay_chuyen_nhuong || "";
  
  const bdNguoiKyArr = [];
  if (bd.chuc_vu_xac_nhan) bdNguoiKyArr.push(bd.chuc_vu_xac_nhan);
  if (bd.nguoi_ky_xac_nhan) bdNguoiKyArr.push(bd.nguoi_ky_xac_nhan);
  if (bd.co_quan_xac_nhan) bdNguoiKyArr.push(bd.co_quan_xac_nhan);
  if (document.getElementById("f-bd-nguoi-ky")) {
    document.getElementById("f-bd-nguoi-ky").value = bdNguoiKyArr.join(" - ") || bd.nguoi_ky_xac_nhan || "";
  }
  if (document.getElementById("f-bd-so-hs")) document.getElementById("f-bd-so-hs").value = bd.so_ho_so_bien_dong || "";

  // Sơ đồ thửa đất đính kèm
  const diagramBox = document.getElementById("diagram-box");
  const diagramImg = document.getElementById("diagram-image");
  const diagramLink = document.getElementById("diagram-download-link");
  const diagramPath = data.attachments?.so_do_thua_dat;

  if (diagramPath && diagramPath.trim() !== "") {
    const fullWebPath = formatWebUrl(diagramPath);
    diagramBox.classList.remove("hidden");
    diagramImg.src = fullWebPath;
    diagramLink.href = fullWebPath;
  } else {
    diagramBox.classList.add("hidden");
  }

  // Draw Bounding Boxes
  currentBBoxes = initialPage.ocr_results || data.ocr_results || [];
  drawBoundingBoxes();

  // Bảng Tổng Hợp Kiểm Tra & Đối Soát Lỗi
  renderAuditTable(data);

  // Khung Hiển Thị Markdown Thông Tin OCR Gốc Chưa Qua Xử Lý Cuối
  renderRawMarkdown(data);

  // Hiển thị Crop Gallery (ảnh cắt trước VietOCR)
  renderCropGallery(data);
}

function renderAuditTable(data) {
  const tbody = document.getElementById("audit-table-body");
  if (!tbody) return;
  tbody.innerHTML = "";

  const confMap = data.confidence || {};
  const canReview = data.can_review || [];

  const nguoi = data.nguoi_su_dung || {};
  const thua = data.thua_dat || {};
  const taisan = data.tai_san || {};
  const cap = data.cap_gcn || {};
  const bd = data.bien_dong || {};

  const fieldsToCheck = [
    // Định danh
    { group: "Định danh", name: "Số phát hành (Serial)", key: "so_phat_hanh", val: data.so_phat_hanh, req: true },
    { group: "Định danh", name: "Số vào sổ cấp GCN", key: "so_vao_so", val: data.so_vao_so, req: true },
    { group: "Định danh", name: "Mã vạch (Barcode)", key: "ma_vach", val: data.ma_vach, req: false },
    { group: "Định danh", name: "Loại cấp / Đợt cấp", key: "loai_cap", val: [data.loai_cap, data.dot_cap_gcn].filter(Boolean).join(" - "), req: false },

    // Chủ sở hữu (Tách riêng Chủ 1 & Chủ 2)
    { group: "Chủ sở hữu", name: "Chủ 1 - Họ tên", key: "ho_ten_chu_1", val: nguoi.ho_ten_chu_1 || (nguoi.ten ? nguoi.ten.split(/,\s*vợ\s*là\s*bà|,\s*chồng\s*là\s*ông|\s+và\s+/i)[0].trim() : ""), req: true },
    { group: "Chủ sở hữu", name: "Chủ 1 - Số CCCD", key: "cmnd_chu_1", val: nguoi.cmnd_chu_1 || (nguoi.cmnd ? String(nguoi.cmnd).split(/[,;]\s*/)[0].trim() : ""), req: true },
    { group: "Chủ sở hữu", name: "Chủ 1 - Năm sinh", key: "ngay_sinh_chu_1", val: nguoi.ngay_sinh_chu_1 || (nguoi.ngay_sinh ? String(nguoi.ngay_sinh).split(/[,;]\s*/)[0].trim() : ""), req: false },
    { group: "Chủ sở hữu", name: "Chủ 2 (Vợ) - Họ tên", key: "ho_ten_chu_2", val: nguoi.ho_ten_chu_2 || "", req: false },
    { group: "Chủ sở hữu", name: "Chủ 2 (Vợ) - Số CCCD", key: "cmnd_chu_2", val: nguoi.cmnd_chu_2 || (nguoi.cmnd && String(nguoi.cmnd).includes(",") ? String(nguoi.cmnd).split(/[,;]\s*/)[1].trim() : ""), req: false },
    { group: "Chủ sở hữu", name: "Chủ 2 (Vợ) - Năm sinh", key: "ngay_sinh_chu_2", val: nguoi.ngay_sinh_chu_2 || (nguoi.ngay_sinh && String(nguoi.ngay_sinh).includes(",") ? String(nguoi.ngay_sinh).split(/[,;]\s*/)[1].trim() : ""), req: false },
    { group: "Chủ sở hữu", name: "Chủ sở hữu gốc bìa", key: "ho_ten_goc", val: nguoi.ho_ten_goc, req: false },
    { group: "Chủ sở hữu", name: "Loại đối tượng chủ", key: "loai_chu", val: nguoi.loai_chu, req: false },
    { group: "Chủ sở hữu", name: "Đồng sở hữu", key: "dong_su_dung", val: data.dong_su_dung || "Không", req: false },
    { group: "Chủ sở hữu", name: "Địa chỉ thường trú", key: "dia_chi_thuong_tru", val: nguoi.dia_chi_thuong_tru, req: false },

    // Thửa đất
    { group: "Thửa đất", name: "Số thửa", key: "so_thua", val: thua.so_thua, req: true },
    { group: "Thửa đất", name: "Tờ bản đồ số", key: "to_ban_do", val: thua.to_ban_do, req: true },
    { group: "Thửa đất", name: "Tỷ lệ bản đồ", key: "ty_le", val: thua.ty_le, req: false },
    { group: "Thửa đất", name: "Địa chỉ thửa đất", key: "dia_chi_thua", val: thua.dia_chi, req: true },
    { group: "Thửa đất", name: "Diện tích cấp (m²)", key: "dien_tich_cap", val: thua.dien_tich_cap, req: true },
    { group: "Thửa đất", name: "Diện tích riêng / chung", key: "dien_tich_rieng", val: (thua.dien_tich_rieng || thua.dien_tich_chung) ? `Riêng: ${thua.dien_tich_rieng || "-"} | Chung: ${thua.dien_tich_chung || "0"}` : "", req: false },
    { group: "Thửa đất", name: "Diện tích bằng chữ", key: "dien_tich_chu", val: thua.dien_tich_chu, req: true },
    { group: "Thửa đất", name: "Mục đích sử dụng", key: "muc_dich_su_dung", val: thua.muc_dich_su_dung ? `${thua.muc_dich_su_dung} (${thua.ma_muc_dich || ""})` : "", req: true },
    { group: "Thửa đất", name: "Thời hạn sử dụng", key: "thoi_han", val: thua.thoi_han, req: false },
    { group: "Thửa đất", name: "Nguồn gốc sử dụng", key: "nguon_goc", val: thua.nguon_goc ? `${thua.nguon_goc} (${thua.nguon_goc_ky_hieu || ""})` : "", req: false },

    // Tài sản & Ghi chú
    { group: "Tài sản & Ghi chú", name: "Nhà ở", key: "nha_o", val: taisan.nha_o, req: false },
    { group: "Tài sản & Ghi chú", name: "Công trình xây dựng khác", key: "cong_trinh_khac", val: taisan.cong_trinh_khac, req: false },
    { group: "Tài sản & Ghi chú", name: "Rừng SX / Cây lâu năm", key: "rung_cay", val: taisan.rung_cay, req: false },
    { group: "Tài sản & Ghi chú", name: "Ghi chú cấp đổi / Hạn chế", key: "ghi_chu", val: taisan.ghi_chu, req: false },

    // Cấp GCN
    { group: "Cấp GCN", name: "Cơ quan cấp ban đầu", key: "noi_cap", val: cap.noi_cap, req: true },
    { group: "Cấp GCN", name: "Ngày cấp GCN", key: "ngay_cap", val: cap.ngay_cap, req: true },
    { group: "Cấp GCN", name: "Người ký / Chức vụ", key: "nguoi_ky_qd", val: [cap.chuc_vu_nguoi_ky, cap.nguoi_ky_qd].filter(Boolean).join(" - "), req: false },
    { group: "Cấp GCN", name: "Số QĐ / Số vào sổ / Hồ sơ gốc", key: "so_quyet_dinh", val: [cap.so_quyet_dinh, cap.ngay_vao_so, cap.so_ho_so_goc].filter(Boolean).join(" | "), req: false },

    // Biến động
    { group: "Biến động", name: "Nội dung biến động (Mục IV)", key: "bien_dong", val: bd.thong_tin_bien_dong, req: false },
    { group: "Biến động", name: "Người nhận CN 1 - Họ tên", key: "ten_chuyen_nhuong_1", val: bd.ten_chuyen_nhuong_1 || (bd.ten_chuyen_nhuong_moi ? bd.ten_chuyen_nhuong_moi.split(/,\s*vợ\s*là\s*bà|,\s*chồng\s*là\s*ông|\s+và\s+/i)[0].trim() : ""), req: false },
    { group: "Biến động", name: "Người nhận CN 1 - Số CCCD", key: "cmnd_chuyen_nhuong_1", val: bd.cmnd_chuyen_nhuong_1 || (bd.cmnd_chuyen_nhuong ? String(bd.cmnd_chuyen_nhuong).split(/[,;]\s*/)[0].trim() : ""), req: false },
    { group: "Biến động", name: "Người nhận CN 2 (Vợ) - Họ tên", key: "ten_chuyen_nhuong_2", val: bd.ten_chuyen_nhuong_2 || (/(?:vợ\s*là\s*bà|chồng\s*là\s*ông|\s+và\s+bà)/i.test(bd.ten_chuyen_nhuong_moi || "") ? ("Bà: " + bd.ten_chuyen_nhuong_moi.split(/(?:,\s*vợ\s*là\s*bà|,\s*chồng\s*là\s*ông|\s+và\s+bà|\s+và\s+vợ\s+là\s+bà)/i)[1].trim()) : ""), req: false },
    { group: "Biến động", name: "Người nhận CN 2 (Vợ) - Số CCCD", key: "cmnd_chuyen_nhuong_2", val: bd.cmnd_chuyen_nhuong_2 || (bd.cmnd_chuyen_nhuong && String(bd.cmnd_chuyen_nhuong).includes(",") ? String(bd.cmnd_chuyen_nhuong).split(/[,;]\s*/)[1].trim() : ""), req: false },
    { group: "Biến động", name: "Ngày & Người ký xác nhận BĐ", key: "ngay_chuyen_nhuong", val: [bd.ngay_chuyen_nhuong, bd.nguoi_ky_xac_nhan].filter(Boolean).join(" | "), req: false },
    { group: "Biến động", name: "Số hồ sơ biến động", key: "so_ho_so_bien_dong", val: bd.so_ho_so_bien_dong, req: false },
  ];

  let warnCount = 0;

  fieldsToCheck.forEach(f => {
    const tr = document.createElement("tr");
    tr.className = "hover:bg-slate-50 transition";

    let conf = confMap[f.key];
    if (conf === undefined) {
      conf = (f.val && f.val !== "-") ? 0.95 : 0.0;
    }
    const confPct = Math.round(conf * 100);

    let statusHtml = "";
    if (f.val && f.val !== "-") {
      if (canReview.includes(f.key) || conf < 0.70) {
        statusHtml = '<span class="inline-flex items-center px-2 py-0.5 rounded text-xs font-semibold bg-amber-100 text-amber-800">⚠️ Cần rà soát</span>';
        warnCount++;
      } else {
        statusHtml = '<span class="inline-flex items-center px-2 py-0.5 rounded text-xs font-semibold bg-emerald-100 text-emerald-800">✓ Hợp lệ</span>';
      }
    } else if (f.req) {
      statusHtml = '<span class="inline-flex items-center px-2 py-0.5 rounded text-xs font-semibold bg-rose-100 text-rose-800">✗ Thiếu</span>';
      warnCount++;
    } else {
      statusHtml = '<span class="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-slate-100 text-slate-500">- Trống</span>';
    }

    let confBadgeClass = "bg-slate-100 text-slate-600";
    if (confPct >= 90) confBadgeClass = "bg-emerald-50 text-emerald-700 font-bold";
    else if (confPct >= 70) confBadgeClass = "bg-amber-50 text-amber-700 font-bold";
    else if (confPct > 0) confBadgeClass = "bg-rose-50 text-rose-700 font-bold";

    tr.innerHTML = `
      <td class="px-3 py-2 text-slate-500 font-medium whitespace-nowrap">${f.group}</td>
      <td class="px-3 py-2 font-semibold text-slate-900 whitespace-nowrap">${f.name}</td>
      <td class="px-3 py-2 text-slate-800 break-words max-w-xs font-mono text-xs">${f.val || '<span class="text-slate-300 italic">(chưa có)</span>'}</td>
      <td class="px-3 py-2 text-center whitespace-nowrap"><span class="px-2 py-0.5 rounded text-xs ${confBadgeClass}">${confPct > 0 ? confPct + '%' : '-'}</span></td>
      <td class="px-3 py-2 text-center whitespace-nowrap">${statusHtml}</td>
    `;
    tbody.appendChild(tr);
  });

  const sumTag = document.getElementById("audit-summary-tag");
  if (sumTag) {
    if (warnCount === 0) {
      sumTag.className = "text-xs font-semibold px-2 py-0.5 bg-emerald-100 text-emerald-800 rounded-full";
      sumTag.innerText = "✓ 100% Hoàn chỉnh";
    } else {
      sumTag.className = "text-xs font-semibold px-2 py-0.5 bg-amber-100 text-amber-800 rounded-full";
      sumTag.innerText = `⚠️ ${warnCount} trường cần rà soát`;
    }
  }
}

function renderRawMarkdown(data) {
  const md = data.raw_ocr_markdown || "";
  const rawTextArea = document.getElementById("raw-ocr-markdown-text");
  if (rawTextArea) {
    rawTextArea.value = md;
  }
  const renderedContent = document.getElementById("md-rendered-content");
  if (renderedContent) {
    if (md) {
      if (typeof marked !== "undefined" && marked.parse) {
        renderedContent.innerHTML = marked.parse(md);
      } else {
        const esc = md.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
        renderedContent.innerHTML = `<pre class="whitespace-pre-wrap font-mono text-xs text-slate-800">${esc}</pre>`;
      }
    } else {
      renderedContent.innerHTML = `<p class="text-slate-400 italic">Không có dữ liệu Markdown thông tin gốc.</p>`;
    }
  }
}

let isMarkdownSourceView = false;
function toggleMarkdownView() {
  isMarkdownSourceView = !isMarkdownSourceView;
  const renderedView = document.getElementById("md-rendered-view");
  const sourceView = document.getElementById("md-source-view");
  const toggleBtn = document.getElementById("btn-toggle-md");

  if (isMarkdownSourceView) {
    renderedView.classList.add("hidden");
    sourceView.classList.remove("hidden");
    if (toggleBtn) toggleBtn.innerHTML = '<i class="fa-solid fa-eye mr-1.5 text-slate-500"></i> Xem Định Dạng';
  } else {
    sourceView.classList.add("hidden");
    renderedView.classList.remove("hidden");
    if (toggleBtn) toggleBtn.innerHTML = '<i class="fa-solid fa-code mr-1.5 text-slate-500"></i> Xem Mã Nguồn .MD';
  }
}

function copyRawMarkdown() {
  const rawTextArea = document.getElementById("raw-ocr-markdown-text");
  if (!rawTextArea || !rawTextArea.value) {
    alert("Chưa có dữ liệu thô OCR để sao chép!");
    return;
  }
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(rawTextArea.value).then(() => {
      alert("✓ Đã sao chép toàn bộ dữ liệu thô OCR vào Clipboard!");
    }).catch(() => {
      rawTextArea.select();
      document.execCommand("copy");
      alert("✓ Đã sao chép dữ liệu thô OCR vào Clipboard!");
    });
  } else {
    rawTextArea.select();
    document.execCommand("copy");
    alert("✓ Đã sao chép dữ liệu thô OCR vào Clipboard!");
  }
}

function downloadRawMarkdown() {
  const rawTextArea = document.getElementById("raw-ocr-markdown-text");
  if (!rawTextArea || !rawTextArea.value) {
    alert("Chưa có dữ liệu thô OCR để tải xuống!");
    return;
  }
  const jobDocId = document.getElementById("res-doc-id")?.innerText || "GCN_RAW_OCR";
  const cleanDocId = jobDocId.replace(/[^a-zA-Z0-9_\-]/g, "_");
  const blob = new Blob([rawTextArea.value], { type: "text/markdown;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${cleanDocId}_du_lieu_tho_ocr.md`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

function drawBoundingBoxes() {
  const canvas = document.getElementById("bbox-canvas");
  const img = document.getElementById("preview-image");
  if (!canvas || !img || !img.complete) return;

  canvas.width = img.clientWidth;
  canvas.height = img.clientHeight;
  const ctx = canvas.getContext("2d");
  ctx.clearRect(0, 0, canvas.width, canvas.height);

  const scaleX = img.clientWidth / (img.naturalWidth || img.clientWidth);
  const scaleY = img.clientHeight / (img.naturalHeight || img.clientHeight);

  ctx.strokeStyle = "rgba(34, 197, 94, 0.75)";
  ctx.lineWidth = 1.5;
  ctx.fillStyle = "rgba(34, 197, 94, 0.1)";

  currentBBoxes.forEach(item => {
    const bbox = item.bbox;
    if (bbox && bbox.length === 4) {
      ctx.beginPath();
      ctx.moveTo(bbox[0][0] * scaleX, bbox[0][1] * scaleY);
      for (let i = 1; i < 4; i++) {
        ctx.lineTo(bbox[i][0] * scaleX, bbox[i][1] * scaleY);
      }
      ctx.closePath();
      ctx.stroke();
      ctx.fill();
    }
  });
}

function rotatePreview(deg) {
  currentRotation = (currentRotation + deg) % 360;
  const img = document.getElementById("preview-image");
  img.style.transform = `rotate(${currentRotation}deg)`;
  setTimeout(drawBoundingBoxes, 250);
}

function zoomPreview(factor) {
  const img = document.getElementById("preview-image");
  const curScale = parseFloat(img.getAttribute("data-scale") || "1");
  const newScale = Math.max(0.5, Math.min(3.0, curScale * factor));
  img.setAttribute("data-scale", newScale);
  img.style.transform = `scale(${newScale}) rotate(${currentRotation}deg)`;
  setTimeout(drawBoundingBoxes, 200);
}

function resetZoom() {
  currentRotation = 0;
  const img = document.getElementById("preview-image");
  img.style.transform = "none";
  drawBoundingBoxes();
}

function exportSingleJSON() {
  if (!currentResult) return;
  const dataStr = "data:text/json;charset=utf-8," + encodeURIComponent(JSON.stringify(currentResult, null, 2));
  const a = document.createElement("a");
  a.setAttribute("href", dataStr);
  a.setAttribute("download", `${currentResult.job_id || "gcn"}_result.json`);
  a.click();
}

function exportSingleExcel() {
  if (!currentResult) return;
  const nguoi = currentResult.nguoi_su_dung || {};
  const thua = currentResult.thua_dat || {};
  const taisan = currentResult.tai_san || {};
  const cap = currentResult.cap_gcn || {};
  const bd = currentResult.bien_dong || {};

  const rows = [
    ["Nhóm", "Trường Dữ Liệu", "Giá Trị Trích Xuất"],
    // Định danh
    ["Định danh", "Mã Hồ Sơ", currentResult.job_id || currentResult.bo_gcn || ""],
    ["Định danh", "Mẫu Sổ", currentResult.mau || ""],
    ["Định danh", "Mã Số Phát Hành (Serial)", currentResult.so_phat_hanh || ""],
    ["Định danh", "Số Vào Sổ Cấp GCN", currentResult.so_vao_so || ""],
    ["Định danh", "Mã Vạch (Barcode)", currentResult.ma_vach || ""],
    ["Định danh", "Loại Cấp / Đợt Cấp", [currentResult.loai_cap, currentResult.dot_cap_gcn].filter(Boolean).join(" - ")],

    // Chủ sở hữu (Tách riêng Chủ 1 & Chủ 2)
    ["Chủ sở hữu", "Chủ 1 (Chồng/Đại diện) - Họ Tên", nguoi.ho_ten_chu_1 || (nguoi.ten ? nguoi.ten.split(/,\s*vợ\s*là\s*bà|,\s*chồng\s*là\s*ông|\s+và\s+/i)[0].trim() : "")],
    ["Chủ sở hữu", "Chủ 1 - Số CMND / CCCD", nguoi.cmnd_chu_1 || (nguoi.cmnd ? String(nguoi.cmnd).split(/[,;]\s*/)[0].trim() : "")],
    ["Chủ sở hữu", "Chủ 1 - Năm Sinh", nguoi.ngay_sinh_chu_1 || (nguoi.ngay_sinh ? String(nguoi.ngay_sinh).split(/[,;]\s*/)[0].trim() : "")],
    ["Chủ sở hữu", "Chủ 2 (Vợ/Đồng sở hữu) - Họ Tên", nguoi.ho_ten_chu_2 || ""],
    ["Chủ sở hữu", "Chủ 2 - Số CMND / CCCD", nguoi.cmnd_chu_2 || (nguoi.cmnd && String(nguoi.cmnd).includes(",") ? String(nguoi.cmnd).split(/[,;]\s*/)[1].trim() : "")],
    ["Chủ sở hữu", "Chủ 2 - Năm Sinh", nguoi.ngay_sinh_chu_2 || (nguoi.ngay_sinh && String(nguoi.ngay_sinh).includes(",") ? String(nguoi.ngay_sinh).split(/[,;]\s*/)[1].trim() : "")],
    ["Chủ sở hữu", "Chủ Sở Hữu Gốc (Bìa)", nguoi.ho_ten_goc || ""],
    ["Chủ sở hữu", "Loại Đối Tượng Chủ", nguoi.loai_chu || ""],
    ["Chủ sở hữu", "Đồng Sở Hữu", currentResult.dong_su_dung || "Không"],
    ["Chủ sở hữu", "Địa Chỉ Thường Trú", nguoi.dia_chi_thuong_tru || ""],

    // Thửa đất
    ["Thửa đất", "Thửa Đất Số", thua.so_thua || ""],
    ["Thửa đất", "Tờ Bản Đồ Số", thua.to_ban_do || ""],
    ["Thửa đất", "Tỷ Lệ Bản Đồ", thua.ty_le || ""],
    ["Thửa đất", "Địa Chỉ Thửa Đất", thua.dia_chi || ""],
    ["Thửa đất", "Diện Tích Cấp (m2)", thua.dien_tich_cap || ""],
    ["Thửa đất", "Diện Tích Riêng (m2)", thua.dien_tich_rieng || ""],
    ["Thửa đất", "Diện Tích Chung (m2)", thua.dien_tich_chung || "0"],
    ["Thửa đất", "Diện Tích Bằng Chữ", thua.dien_tich_chu || ""],
    ["Thửa đất", "Mục Đích Sử Dụng", thua.muc_dich_su_dung || ""],
    ["Thửa đất", "Mã Mục Đích", thua.ma_muc_dich || ""],
    ["Thửa đất", "Thời Hạn Sử Dụng", thua.thoi_han || ""],
    ["Thửa đất", "Nguồn Gốc Sử Dụng", thua.nguon_goc || ""],
    ["Thửa đất", "Mã Nguồn Gốc", thua.nguon_goc_ky_hieu || ""],

    // Tài sản & Ghi chú
    ["Tài sản & Ghi chú", "Nhà Ở", taisan.nha_o || "-"],
    ["Tài sản & Ghi chú", "Công Trình Xây Dựng Khác", taisan.cong_trinh_khac || "-"],
    ["Tài sản & Ghi chú", "Rừng SX / Cây Lâu Năm", taisan.rung_cay || "-"],
    ["Tài sản & Ghi chú", "Ghi Chú / Hạn Chế Quyền", taisan.ghi_chu || ""],

    // Cấp GCN
    ["Cấp GCN", "Nơi Cấp (Cơ Quan)", cap.noi_cap || ""],
    ["Cấp GCN", "Ngày Cấp GCN", cap.ngay_cap || ""],
    ["Cấp GCN", "Người Ký / Chức Vụ", [cap.chuc_vu_nguoi_ky, cap.nguoi_ky_qd].filter(Boolean).join(" - ")],
    ["Cấp GCN", "Số Quyết Định Cấp", cap.so_quyet_dinh || ""],
    ["Cấp GCN", "Ngày Vào Sổ", cap.ngay_vao_so || ""],
    ["Cấp GCN", "Số Hồ Sơ Gốc", cap.so_ho_so_goc || ""],

    // Biến động (Tách riêng Người nhận 1 & 2)
    ["Biến động (Mục IV)", "Nội Dung Biến Động", bd.thong_tin_bien_dong || ""],
    ["Biến động (Mục IV)", "Người Nhận CN 1 - Họ Tên", bd.ten_chuyen_nhuong_1 || (bd.ten_chuyen_nhuong_moi ? bd.ten_chuyen_nhuong_moi.split(/,\s*vợ\s*là\s*bà|,\s*chồng\s*là\s*ông|\s+và\s+/i)[0].trim() : "")],
    ["Biến động (Mục IV)", "Người Nhận CN 1 - Số CMND / CCCD", bd.cmnd_chuyen_nhuong_1 || (bd.cmnd_chuyen_nhuong ? String(bd.cmnd_chuyen_nhuong).split(/[,;]\s*/)[0].trim() : "")],
    ["Biến động (Mục IV)", "Người Nhận CN 2 (Vợ) - Họ Tên", bd.ten_chuyen_nhuong_2 || (/(?:vợ\s*là\s*bà|chồng\s*là\s*ông|\s+và\s+bà)/i.test(bd.ten_chuyen_nhuong_moi || "") ? ("Bà: " + bd.ten_chuyen_nhuong_moi.split(/(?:,\s*vợ\s*là\s*bà|,\s*chồng\s*là\s*ông|\s+và\s+bà|\s+và\s+vợ\s+là\s+bà)/i)[1].trim()) : "")],
    ["Biến động (Mục IV)", "Người Nhận CN 2 (Vợ) - Số CMND / CCCD", bd.cmnd_chuyen_nhuong_2 || (bd.cmnd_chuyen_nhuong && String(bd.cmnd_chuyen_nhuong).includes(",") ? String(bd.cmnd_chuyen_nhuong).split(/[,;]\s*/)[1].trim() : "")],
    ["Biến động (Mục IV)", "Ngày Xác Nhận Biến Động", bd.ngay_chuyen_nhuong || ""],
    ["Biến động (Mục IV)", "Người Ký / CQ Xác Nhận BĐ", bd.nguoi_ky_xac_nhan || ""],
    ["Biến động (Mục IV)", "Số Hồ Sơ Biến Động", bd.so_ho_so_bien_dong || ""]
  ];

  let csvContent = "\uFEFF" + rows.map(e => e.map(cell => `"${(cell || "").toString().replace(/"/g, '""')}"`).join(",")).join("\n");
  const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${currentResult.job_id || "gcn"}_result.csv`;
  a.click();
}

// ─── Batch Directory Scanning ────────────────────────────────────────────────
async function startDirectoryScan() {
  const dirPath = document.getElementById("batch-dir-path").value.trim();
  const sampleCount = parseInt(document.getElementById("batch-sample-count").value, 10);

  if (!dirPath) {
    alert("Vui lòng nhập đường dẫn thư mục trên máy chủ!");
    return;
  }

  const btn = document.getElementById("btn-start-scan");
  const progressBox = document.getElementById("batch-progress-box");
  const progressBar = document.getElementById("batch-progress-bar");
  const progressTitle = document.getElementById("batch-progress-title");
  const progressPct = document.getElementById("batch-progress-pct");

  btn.disabled = true;
  btn.classList.add("opacity-50");
  progressBox.classList.remove("hidden");
  progressBar.style.width = "0%";
  progressTitle.innerText = "Đang quét danh sách file trong thư mục...";
  progressPct.innerText = "0%";

  try {
    const res = await fetch("/ocr/scan-directory", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        directory_path: dirPath,
        sample_count: sampleCount
      })
    });

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "Lỗi khi khởi chạy quét thư mục");
    }

    const data = await res.json();
    const batchId = data.batch_id;
    pollBatchProgress(batchId);
  } catch (err) {
    alert(`Lỗi: ${err.message}`);
    btn.disabled = false;
    btn.classList.remove("opacity-50");
    progressBox.classList.add("hidden");
  }
}

function pollBatchProgress(batchId) {
  if (batchPollingTimer) clearInterval(batchPollingTimer);

  batchPollingTimer = setInterval(async () => {
    try {
      const res = await fetch(`/batch/${batchId}`);
      if (!res.ok) return;
      const data = await res.json();

      const total = data.files_count || 1;
      const doneCount = (data.results || []).length;
      const pct = Math.min(100, Math.round((doneCount / total) * 100));

      document.getElementById("batch-progress-bar").style.width = `${pct}%`;
      document.getElementById("batch-progress-pct").innerText = `${pct}%`;
      document.getElementById("batch-progress-title").innerText = `Đang xử lý: ${doneCount}/${total} file`;
      
      if (data.current_file) {
        document.getElementById("batch-current-file").innerText = `Đang xử lý: ${data.current_file}`;
      }

      if (data.results && data.results.length > 0) {
        batchResultsList = data.results;
        updateBatchStats(data.results);

        if (data.chuyen_doi_rows && data.chuyen_doi_rows.length > 0) {
          chuyenDoiRows = data.chuyen_doi_rows;
          if (chuyenDoiColumns.length === 0) {
            loadChuyenDoiColumns().then(() => {
              renderChuyenDoiGrid(chuyenDoiRows);
              updateChuyenDoiStatus(chuyenDoiRows.length);
            });
          } else {
            renderChuyenDoiGrid(chuyenDoiRows);
            updateChuyenDoiStatus(chuyenDoiRows.length);
          }
        }
      }

      if (data.status === "done" || data.status === "error") {
        clearInterval(batchPollingTimer);
        document.getElementById("btn-start-scan").disabled = false;
        document.getElementById("btn-start-scan").classList.remove("opacity-50");
        document.getElementById("batch-progress-title").innerText = `Hoàn tất xử lý ${doneCount}/${total} file!`;
        document.getElementById("batch-progress-pct").innerText = "100%";
        document.getElementById("batch-progress-bar").style.width = "100%";
      }
    } catch (err) {
      console.error("Poll error:", err);
    }
  }, 1000);
}

function updateBatchStats(results) {
  document.getElementById("stat-total").innerText = results.length;
  const successCount = results.filter(r => r.thua_dat?.so_thua || r.thua_dat?.dien_tich_cap).length;
  const reviewCount = results.filter(r => (r.can_review && r.can_review.length > 0) || r.error).length;
  
  document.getElementById("stat-success").innerText = successCount;
  document.getElementById("stat-review").innerText = reviewCount;

  const totalTime = results.reduce((acc, r) => acc + (r.tong_thoi_gian_sec || r.processing_time_ms / 1000 || 0), 0);
  const avgTime = results.length > 0 ? (totalTime / results.length).toFixed(1) : "0.0";
  document.getElementById("stat-avg-time").innerText = `${avgTime}s`;
}

function renderBatchTable(results) {
  const tbody = document.getElementById("batch-table-body");
  document.getElementById("table-count-tag").innerText = `${results.length} dòng`;

  if (!results || results.length === 0) {
    tbody.innerHTML = `<tr><td colspan="11" class="text-center py-8 text-slate-400">Không có kết quả.</td></tr>`;
    return;
  }

  tbody.innerHTML = results.map((r, idx) => {
    const chu = r.nguoi_su_dung?.ten || r.folder_meta?.ten_chu_thu_muc || "-";
    const thua = r.thua_dat?.so_thua || r.folder_meta?.so_thua || "-";
    const to = r.thua_dat?.to_ban_do || r.folder_meta?.to_ban_do || "-";
    const dt = r.thua_dat?.dien_tich_cap || "-";
    const serial = r.so_phat_hanh || "-";
    const tg = r.tong_thoi_gian_sec ? `${r.tong_thoi_gian_sec}s` : (r.processing_time_ms ? `${(r.processing_time_ms / 1000).toFixed(1)}s` : "-");

    let statusBadge = `<span class="inline-flex items-center px-2 py-0.5 rounded text-xs font-semibold bg-emerald-100 text-emerald-800">✓ Đạt</span>`;
    if (r.error) {
      statusBadge = `<span class="inline-flex items-center px-2 py-0.5 rounded text-xs font-semibold bg-rose-100 text-rose-800">✗ Lỗi</span>`;
    } else if (r.can_review && r.can_review.length > 0) {
      statusBadge = `<span class="inline-flex items-center px-2 py-0.5 rounded text-xs font-semibold bg-amber-100 text-amber-800">⚠️ Soát (${r.can_review.length})</span>`;
    }

    return `
      <tr class="hover:bg-slate-50 transition cursor-pointer" onclick="viewBatchDetail(${idx})">
        <td class="px-3 py-2 font-mono text-slate-500">${idx + 1}</td>
        <td class="px-3 py-2 font-semibold text-slate-800 break-words max-w-[180px]" title="${r.bo_gcn || r.job_id || ''}">
          <i class="fa-regular fa-file-pdf text-rose-500 mr-1"></i> ${r.bo_gcn || r.job_id || "-"}
        </td>
        <td class="px-3 py-2"><span class="badge-med text-xs px-2 py-0.5 rounded-full font-semibold">${r.mau || "-"}</span></td>
        <td class="px-3 py-2 font-bold text-slate-900">${chu}</td>
        <td class="px-3 py-2 font-mono">${thua}</td>
        <td class="px-3 py-2 font-mono">${to}</td>
        <td class="px-3 py-2 font-bold text-brand-700">${dt}</td>
        <td class="px-3 py-2 font-mono text-xs text-slate-700">${serial}</td>
        <td class="px-3 py-2 text-slate-500 text-xs">${tg}</td>
        <td class="px-3 py-2 text-center">${statusBadge}</td>
        <td class="px-3 py-2 text-center">
          <button class="text-brand-600 hover:text-brand-800 font-semibold text-xs inline-flex items-center">
            Chi tiết <i class="fa-solid fa-chevron-right ml-1 text-[10px]"></i>
          </button>
        </td>
      </tr>
    `;
  }).join("");
}

function filterBatchTable() {
  const query = document.getElementById("batch-search").value.toLowerCase().trim();
  if (!query) {
    renderBatchTable(batchResultsList);
    return;
  }

  const filtered = batchResultsList.filter(r => {
    const text = [
      r.bo_gcn, r.job_id, r.nguoi_su_dung?.ten, r.thua_dat?.so_thua, r.thua_dat?.to_ban_do,
      r.so_phat_hanh, r.so_vao_so, r.thua_dat?.dia_chi
    ].filter(Boolean).join(" ").toLowerCase();
    return text.includes(query);
  });
  renderBatchTable(filtered);
}

function viewBatchDetail(idx) {
  const item = batchResultsList[idx];
  if (!item) return;
  currentResult = item;
  switchTab("single");
  renderSingleResult(item, item.tong_thoi_gian_sec || "1.0", item.bo_gcn || item.job_id);
  document.getElementById("upload-container").classList.add("hidden");
  document.getElementById("single-result-view").classList.remove("hidden");
}

function exportBatchExcel() {
  if (!batchResultsList || batchResultsList.length === 0) {
    alert("Chưa có kết quả để xuất!");
    return;
  }

  const headers = [
    "STT", "Mã Hồ Sơ", "Mẫu Sổ", 
    "Chủ 1 - Họ Tên", "Chủ 1 - CCCD/CMND", "Chủ 1 - Năm Sinh",
    "Chủ 2 (Vợ/Đồng Sở Hữu) - Họ Tên", "Chủ 2 - CCCD/CMND", "Chủ 2 - Năm Sinh",
    "Chủ Bìa Gốc", "Loại Chủ", "Đồng Sở Hữu", "Địa Chỉ Thường Trú",
    "Thửa Đất Số", "Tờ Bản Đồ Số", "Tỷ Lệ", "Diện Tích Cấp (m2)", "Diện Tích Riêng", "Diện Tích Chung", "Diện Tích Bằng Chữ",
    "Mục Đích Sử Dụng", "Mã Mục Đích", "Thời Hạn", "Nguồn Gốc", "Mã Nguồn Gốc", "Địa Chỉ Thửa Đất",
    "Nhà Ở", "Công Trình Khác", "Rừng/Cây Lâu Năm", "Ghi Chú",
    "Số Phát Hành (Serial)", "Số Vào Sổ", "Mã Vạch", "Nơi Cấp", "Ngày Cấp", "Người Ký / Chức Vụ", "Số QĐ", "Ngày Vào Sổ", "Số HS Gốc",
    "Nội Dung Biến Động (Mục IV)", 
    "Người Nhận CN 1 - Họ Tên", "Người Nhận CN 1 - CCCD",
    "Người Nhận CN 2 (Vợ) - Họ Tên", "Người Nhận CN 2 (Vợ) - CCCD",
    "Ngày Xác Nhận BĐ", "Người Ký Xác Nhận BĐ", "Số HS Biến Động",
    "Thời Gian (s)", "Trạng Thái"
  ];

  const rows = batchResultsList.map((r, i) => {
    const ng = r.nguoi_su_dung || {};
    const c1_t = ng.ho_ten_chu_1 || (ng.ten ? ng.ten.split(/,\s*vợ\s*là\s*bà|,\s*chồng\s*là\s*ông|\s+và\s+/i)[0].trim() : (r.folder_meta?.ten_chu_thu_muc || ""));
    const c1_c = ng.cmnd_chu_1 || (ng.cmnd ? String(ng.cmnd).split(/[,;]\s*/)[0].trim() : "");
    const c1_d = ng.ngay_sinh_chu_1 || (ng.ngay_sinh ? String(ng.ngay_sinh).split(/[,;]\s*/)[0].trim() : "");

    let c2_t = ng.ho_ten_chu_2 || "";
    if (!c2_t && ng.ten && /(?:vợ\s*là\s*bà|chồng\s*là\s*ông|\s+và\s+bà)/i.test(ng.ten)) {
      const parts = ng.ten.split(/(?:,\s*vợ\s*là\s*bà|,\s*chồng\s*là\s*ông|\s+và\s+bà|\s+và\s+vợ\s*là\s+bà)/i);
      if (parts.length > 1) c2_t = "Bà: " + parts[1].trim();
    }
    const c2_c = ng.cmnd_chu_2 || (ng.cmnd && String(ng.cmnd).includes(",") ? String(ng.cmnd).split(/[,;]\s*/)[1].trim() : "");
    const c2_d = ng.ngay_sinh_chu_2 || (ng.ngay_sinh && String(ng.ngay_sinh).includes(",") ? String(ng.ngay_sinh).split(/[,;]\s*/)[1].trim() : "");

    const b = r.bien_dong || {};
    const b_c1_t = b.ten_chuyen_nhuong_1 || (b.ten_chuyen_nhuong_moi ? b.ten_chuyen_nhuong_moi.split(/,\s*vợ\s*là\s*bà|,\s*chồng\s*là\s*ông|\s+và\s+/i)[0].trim() : "");
    const b_c1_c = b.cmnd_chuyen_nhuong_1 || (b.cmnd_chuyen_nhuong ? String(b.cmnd_chuyen_nhuong).split(/[,;]\s*/)[0].trim() : "");
    let b_c2_t = b.ten_chuyen_nhuong_2 || "";
    if (!b_c2_t && b.ten_chuyen_nhuong_moi && /(?:vợ\s*là\s*bà|chồng\s*là\s*ông|\s+và\s+bà)/i.test(b.ten_chuyen_nhuong_moi)) {
      const parts = b.ten_chuyen_nhuong_moi.split(/(?:,\s*vợ\s*là\s*bà|,\s*chồng\s*là\s*ông|\s+và\s+bà|\s+và\s+vợ\s+là\s+bà)/i);
      if (parts.length > 1) b_c2_t = "Bà: " + parts[1].trim();
    }
    const b_c2_c = b.cmnd_chuyen_nhuong_2 || (b.cmnd_chuyen_nhuong && String(b.cmnd_chuyen_nhuong).includes(",") ? String(b.cmnd_chuyen_nhuong).split(/[,;]\s*/)[1].trim() : "");

    return [
      i + 1,
      r.bo_gcn || r.job_id || "",
      r.mau || "",
      c1_t,
      c1_c,
      c1_d,
      c2_t,
      c2_c,
      c2_d,
      ng.ho_ten_goc || "",
      ng.loai_chu || "",
      r.dong_su_dung || "Không",
      ng.dia_chi_thuong_tru || "",
      r.thua_dat?.so_thua || r.folder_meta?.so_thua || "",
      r.thua_dat?.to_ban_do || r.folder_meta?.to_ban_do || "",
      r.thua_dat?.ty_le || "",
      r.thua_dat?.dien_tich_cap || "",
      r.thua_dat?.dien_tich_rieng || "",
      r.thua_dat?.dien_tich_chung || "0",
    r.thua_dat?.dien_tich_chu || "",
    r.thua_dat?.muc_dich_su_dung || "",
    r.thua_dat?.ma_muc_dich || "",
    r.thua_dat?.thoi_han || "",
    r.thua_dat?.nguon_goc || "",
    r.thua_dat?.nguon_goc_ky_hieu || "",
    r.thua_dat?.dia_chi || "",
    r.tai_san?.nha_o || "-",
    r.tai_san?.cong_trinh_khac || "-",
    r.tai_san?.rung_cay || "-",
    r.tai_san?.ghi_chu || "",
    r.so_phat_hanh || "",
    r.so_vao_so || "",
    r.ma_vach || "",
    r.cap_gcn?.noi_cap || "",
    r.cap_gcn?.ngay_cap || "",
    [r.cap_gcn?.chuc_vu_nguoi_ky, r.cap_gcn?.nguoi_ky_qd].filter(Boolean).join(" - "),
    r.cap_gcn?.so_quyet_dinh || "",
    r.cap_gcn?.ngay_vao_so || "",
    r.cap_gcn?.so_ho_so_goc || "",
    r.bien_dong?.thong_tin_bien_dong || "",
    r.bien_dong?.ten_chuyen_nhuong_moi || "",
    r.bien_dong?.cmnd_chuyen_nhuong || "",
    r.bien_dong?.ngay_chuyen_nhuong || "",
    r.bien_dong?.nguoi_ky_xac_nhan || "",
    r.bien_dong?.so_ho_so_bien_dong || "",
    r.tong_thoi_gian_sec || "",
    r.error ? "Lỗi" : (r.can_review && r.can_review.length > 0 ? "Cần Review" : "Hợp lệ")
  ];
});

  let csvContent = "\uFEFF" + [headers, ...rows].map(row => row.map(cell => `"${(cell || "").toString().replace(/"/g, '""')}"`).join(",")).join("\n");
  const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `ket_qua_ocr_batch_${Date.now()}.csv`;
  a.click();
}

function exportBatchJSON() {
  const dataToExport = (chuyenDoiRows && chuyenDoiRows.length > 0) ? chuyenDoiRows : batchResultsList;
  if (!dataToExport || dataToExport.length === 0) {
    alert("Chưa có dữ liệu để xuất JSON!");
    return;
  }
  const dataStr = "data:text/json;charset=utf-8," + encodeURIComponent(JSON.stringify(dataToExport, null, 2));
  const a = document.createElement("a");
  a.setAttribute("href", dataStr);
  a.setAttribute("download", `ket_qua_chuyen_doi_129cot_${Date.now()}.json`);
  a.click();
}

// ─── Review Queue ───────────────────────────────────────────────────────────
async function loadReviewQueue() {
  const container = document.getElementById("review-list-container");
  try {
    const res = await fetch("/review");
    if (!res.ok) return;
    const data = await res.json();
    const items = data.items || [];

    const badge = document.getElementById("review-count-badge");
    if (items.length > 0) {
      badge.innerText = items.length;
      badge.classList.remove("hidden");
    } else {
      badge.classList.add("hidden");
    }

    if (items.length === 0) {
      container.innerHTML = `
        <div class="text-center py-12 text-slate-400">
          <i class="fa-solid fa-circle-check text-3xl text-emerald-500 mb-2"></i>
          <p class="text-sm font-semibold text-slate-700">Tuyệt vời! Không có hồ sơ nào cần soát lỗi.</p>
        </div>
      `;
      return;
    }

    container.innerHTML = items.map(item => `
      <div class="p-4 bg-slate-50 hover:bg-slate-100 rounded-xl border border-slate-200 flex items-center justify-between transition">
        <div>
          <div class="flex items-center space-x-2">
            <h5 class="text-sm font-bold text-slate-800">${item.job_id}</h5>
            <span class="badge-med text-xs px-2 py-0.5 rounded-full font-semibold">${item.mau}</span>
          </div>
          <p class="text-xs text-amber-700 mt-1 font-medium">
            <i class="fa-solid fa-triangle-exclamation mr-1"></i> Các trường cần xem lại: ${(item.can_review || []).join(", ")}
          </p>
        </div>
        <div class="flex items-center space-x-2">
          <button onclick="approveReview('${item.job_id}')" class="px-3 py-1.5 bg-brand-600 hover:bg-brand-700 text-white text-xs font-semibold rounded-lg shadow-sm">
            ✓ Phê duyệt
          </button>
        </div>
      </div>
    `).join("");
  } catch (err) {
    console.error("Load review error:", err);
  }
}

async function approveReview(jobId) {
  try {
    await fetch(`/review/${jobId}`, { method: "DELETE" });
    loadReviewQueue();
  } catch (err) {
    console.error(err);
  }
}


// ─── Crop Gallery ─────────────────────────────────────────────────────────────

let _allCrops = [];          // lưu toàn bộ crops của lần OCR hiện tại
let _cropGalleryVisible = true;

/**
 * Render lưới ảnh crops (trước VietOCR) từ response.
 * Mỗi card hiển thị: thumbnail ảnh, PaddleOCR text, VietOCR text, confidence badge.
 * Cards có text khác nhau giữa Paddle vs Viet được highlight vàng.
 */
function renderCropGallery(data) {
  const box = document.getElementById("crop-gallery-box");
  const grid = document.getElementById("crop-gallery-grid");
  const badge = document.getElementById("crop-count-badge");
  if (!box || !grid) return;

  // Thu thập crops: ưu tiên top-level crops, fallback lấy từng trang trong pages
  let crops = [];
  if (Array.isArray(data.crops) && data.crops.length > 0) {
    crops = data.crops;
  } else if (Array.isArray(data.pages) && data.pages.length > 0) {
    for (const p of data.pages) {
      if (Array.isArray(p.crops) && p.crops.length > 0) {
        crops = crops.concat(p.crops);
      }
    }
  }

  console.log(`[CropGallery] Tìm thấy ${crops.length} crops trong response.`);

  _allCrops = crops;

  if (crops.length === 0) {
    box.classList.add("hidden");
    console.warn("[CropGallery] Không có crops để hiển thị.");
    return;
  }

  badge.textContent = crops.length;
  box.classList.remove("hidden");
  _cropGalleryVisible = true;
  document.getElementById("crop-toggle-btn").textContent = "Thu gọn";

  _renderCropCards(crops);
}

function _renderCropCards(crops) {
  const grid = document.getElementById("crop-gallery-grid");
  if (!grid) return;
  grid.innerHTML = "";

  crops.forEach((crop, i) => {
    const isDiff = crop.paddle_text && crop.viet_text &&
      crop.paddle_text.trim().toLowerCase() !== crop.viet_text.trim().toLowerCase();

    const confVal = crop.final_conf ?? crop.viet_conf ?? 0;
    const confClass = confVal >= 0.75 ? "bg-emerald-100 text-emerald-700"
      : confVal >= 0.5  ? "bg-amber-100 text-amber-700"
      : "bg-rose-100 text-rose-700";
    const confPct = Math.round(confVal * 100);

    const card = document.createElement("div");
    card.className = "crop-card" + (isDiff ? " diff-highlight" : "");
    card.title = isDiff
      ? `⚠ Paddle: "${crop.paddle_text}" | VietOCR: "${crop.viet_text}"`
      : `✓ ${crop.final_text || crop.viet_text || crop.paddle_text}`;
    card.onclick = () => openCropModal(crop);

    const ts = Date.now(); // cache-bust
    card.innerHTML = `
      <img src="${crop.url}?v=${ts}" alt="crop" loading="lazy"
           onerror="this.src='data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 width=%22100%22 height=%2240%22><rect fill=%22%23f1f5f9%22 width=%22100%25%22 height=%22100%25%22/><text x=%2250%25%22 y=%2255%25%22 dominant-baseline=%22middle%22 text-anchor=%22middle%22 font-size=%2210%22 fill=%22%2394a3b8%22>Hết hạn</text></svg>'">
      <div class="crop-text">
        <div class="flex items-center justify-between mb-0.5">
          <span class="crop-conf-badge ${confClass}">${confPct}%</span>
          ${isDiff ? '<span class="text-[9px] text-amber-600 font-bold">⚠ Khác</span>' : ''}
        </div>
        <div class="text-slate-700 truncate font-medium" style="max-width:100%">
          ${escHtml(crop.final_text || crop.viet_text || crop.paddle_text || "(trống)")}
        </div>
      </div>
    `;
    grid.appendChild(card);
  });
}

/** Lọc: chỉ hiện các crops mà Paddle và VietOCR cho kết quả khác nhau */
function filterCropGallery() {
  const showDiffOnly = document.getElementById("crop-show-diff-only")?.checked;
  if (!_allCrops.length) return;
  const filtered = showDiffOnly
    ? _allCrops.filter(c => c.paddle_text && c.viet_text &&
        c.paddle_text.trim().toLowerCase() !== c.viet_text.trim().toLowerCase())
    : _allCrops;
  document.getElementById("crop-count-badge").textContent = filtered.length;
  _renderCropCards(filtered);
}

/** Mở modal zoom chi tiết crop */
function openCropModal(crop) {
  const modal = document.getElementById("crop-zoom-modal");
  if (!modal) return;

  const ts = Date.now();
  document.getElementById("crop-zoom-img").src = `${crop.url}?v=${ts}`;
  document.getElementById("crop-zoom-paddle-text").textContent = crop.paddle_text || "(trống)";
  document.getElementById("crop-zoom-paddle-conf").textContent = `Confidence: ${Math.round((crop.paddle_conf ?? 0) * 100)}%`;
  document.getElementById("crop-zoom-viet-text").textContent = crop.viet_text || "(trống)";
  document.getElementById("crop-zoom-viet-conf").textContent = `Confidence: ${Math.round((crop.viet_conf ?? 0) * 100)}%`;
  document.getElementById("crop-zoom-final").textContent = crop.final_text || crop.viet_text || crop.paddle_text || "(trống)";

  modal.classList.add("active");
  document.addEventListener("keydown", _modalEscClose);
}

function closeCropModal(e) {
  if (e && e.target !== document.getElementById("crop-zoom-modal")) return;
  document.getElementById("crop-zoom-modal")?.classList.remove("active");
  document.removeEventListener("keydown", _modalEscClose);
}

function _modalEscClose(e) {
  if (e.key === "Escape") {
    document.getElementById("crop-zoom-modal")?.classList.remove("active");
    document.removeEventListener("keydown", _modalEscClose);
  }
}

/** Thu gọn / mở rộng crop gallery */
function toggleCropGallery() {
  const grid = document.getElementById("crop-gallery-grid");
  const btn = document.getElementById("crop-toggle-btn");
  if (!grid || !btn) return;
  _cropGalleryVisible = !_cropGalleryVisible;
  grid.style.display = _cropGalleryVisible ? "" : "none";
  btn.textContent = _cropGalleryVisible ? "Thu gọn" : "Mở rộng";
}

/** Helper escape HTML */
function escHtml(str) {
  return String(str ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

// ─── Module Chuyển Đổi Dữ Liệu Địa Chính (129 Cột Theo Mẫu Excel) ────────────

let chuyenDoiColumns = [];
let chuyenDoiSections = [];
let activeSections = new Set();
let chuyenDoiRows = [];
let currentModalRow = null;
let isAllColumnsMode = true;
let isCoreColumnsMode = false;
let isChuyenDoiFullscreen = false;

// Các cột nhận diện cốt lõi luôn luôn hiển thị để cố định bên trái khi lọc
const ALWAYS_VISIBLE_CODES = new Set(["STT", "GCN_soPhatHanh", "GCN_soVaoSo", "CHU_hoTen"]);

// 30 cột bóc tách trọng tâm có dữ liệu phổ biến nhất
const CORE_EXTRACTED_CODES = new Set([
  "STT", "GCN_soPhatHanh", "GCN_soVaoSo", "GCN_ngayCap", "GCN_tenNguoiKy", "GCN_donViCap",
  "CHU_hoTen", "CHU_ngaySinh", "CHU_gioiTinh", "CHU_diaChiChiTiet", "CHU_tenXa", "CHU_tenHuyen", "CHU_tenTinh",
  "GT_loaiGiayTo", "GT_soGiayTo",
  "VC_hoTen", "VC_ngaySinh", "VC_gioiTinh", "GT_VC_loaiGiayTo", "GT_VC_soGiayTo",
  "TD_soThuTuThua", "TD_soHieuToBanDo", "TD_dienTich", "TD_maMucDichSuDung", "TD_thoiHanSuDung", "TD_nguonGoc", "TD_diaChiChiTiet",
  "NHA_tenNha", "NHA_soTang", "NHA_dienTichXayDung"
]);

function getVisibleColumns() {
  if (isAllColumnsMode) {
    return chuyenDoiColumns;
  }
  if (isCoreColumnsMode) {
    return chuyenDoiColumns.filter(c => CORE_EXTRACTED_CODES.has(c.code));
  }
  // Khi lọc theo nhóm cụ thể: luôn giữ 4 cột nhận diện bên trái + các cột thuộc nhóm đó
  return chuyenDoiColumns.filter(c => ALWAYS_VISIBLE_CODES.has(c.code) || activeSections.has(c.section_key));
}

async function loadChuyenDoiColumns() {
  try {
    const res = await fetch("/chuyen-doi/columns");
    if (!res.ok) throw new Error("Không thể tải cấu hình cột");
    const data = await res.json();
    chuyenDoiColumns = data.columns || [];
    chuyenDoiSections = data.sections || [];

    // Mặc định bật toàn bộ các nhóm section
    activeSections = new Set(chuyenDoiSections.map(s => s.key));
    isAllColumnsMode = true;
    isCoreColumnsMode = false;

    renderSectionPills();
    renderChuyenDoiHeaders();
  } catch (err) {
    console.error("Lỗi nạp danh mục cột:", err);
  }
}

function showAllColumnsMode() {
  isAllColumnsMode = true;
  isCoreColumnsMode = false;
  activeSections = new Set(chuyenDoiSections.map(s => s.key));

  updateModeButtons();
  renderSectionPills();
  renderChuyenDoiHeaders();
  filterChuyenDoiGrid();
}

function showCoreColumnsMode() {
  isAllColumnsMode = false;
  isCoreColumnsMode = true;
  activeSections = new Set(["chung", "gcn", "chu", "gt_chu", "vc", "gt_vc", "thua_dat", "nha_rieng"]);

  updateModeButtons();
  renderSectionPills();
  renderChuyenDoiHeaders();
  filterChuyenDoiGrid();
}

function selectSectionFilter(secKey) {
  isAllColumnsMode = false;
  isCoreColumnsMode = false;
  activeSections = new Set([secKey]);

  updateModeButtons();
  renderSectionPills();
  renderChuyenDoiHeaders();
  filterChuyenDoiGrid();
}

function updateModeButtons() {
  const btnAll = document.getElementById("btn-mode-all");
  const btnCore = document.getElementById("btn-mode-core");

  if (btnAll) {
    if (isAllColumnsMode) {
      btnAll.className = "px-2.5 py-1 rounded-md text-xs font-bold bg-indigo-600 text-white shadow-sm transition";
    } else {
      btnAll.className = "px-2.5 py-1 rounded-md text-xs font-medium bg-slate-100 hover:bg-slate-200 text-slate-700 transition";
    }
  }

  if (btnCore) {
    if (isCoreColumnsMode) {
      btnCore.className = "px-2.5 py-1 rounded-md text-xs font-bold bg-indigo-600 text-white shadow-sm transition";
    } else {
      btnCore.className = "px-2.5 py-1 rounded-md text-xs font-medium bg-slate-100 hover:bg-slate-200 text-slate-700 transition";
    }
  }
}

function renderSectionPills() {
  const container = document.getElementById("chuyen-doi-section-pills");
  if (!container) return;

  container.innerHTML = chuyenDoiSections.map(sec => {
    const isSingleActive = !isAllColumnsMode && !isCoreColumnsMode && activeSections.has(sec.key);
    const isIncluded = activeSections.has(sec.key);

    let style = "background-color: #f8fafc; color: #475569; border: 1px solid #e2e8f0;";
    if (isSingleActive) {
      style = "background-color: #4f46e5; color: #ffffff; font-weight: 700; border: 1px solid #4338ca; box-shadow: 0 1px 4px rgba(79,70,229,0.3);";
    } else if (isIncluded && isAllColumnsMode) {
      style = "background-color: #eef2ff; color: #3730a3; font-weight: 600; border: 1px solid #c7d2fe;";
    } else if (isIncluded && isCoreColumnsMode) {
      style = "background-color: #ecfdf5; color: #065f46; font-weight: 600; border: 1px solid #a7f3d0;";
    }

    return `
      <button onclick="selectSectionFilter('${sec.key}')" style="${style}" class="text-xs px-2.5 py-1 rounded-lg transition flex items-center space-x-1.5 hover:opacity-90" title="Bấm để lọc xem riêng nhóm ${sec.title}">
        <span>${sec.title}</span>
        <span class="text-[10px] opacity-80 font-mono">(${sec.count})</span>
      </button>
    `;
  }).join("");
}

function toggleChuyenDoiFullscreen() {
  const card = document.getElementById("chuyen-doi-table-card");
  const fsBar = document.getElementById("chuyen-doi-fs-bar");
  const icon = document.getElementById("icon-fullscreen");
  const text = document.getElementById("text-fullscreen");
  const wrapper = document.getElementById("chuyen-doi-table-wrapper");

  isChuyenDoiFullscreen = !isChuyenDoiFullscreen;

  if (isChuyenDoiFullscreen) {
    card.classList.add("fixed", "inset-0", "z-50", "rounded-none", "border-0", "p-0", "h-screen", "w-screen");
    if (fsBar) fsBar.classList.remove("hidden");
    if (wrapper) {
      wrapper.classList.remove("max-h-[660px]");
      wrapper.classList.add("flex-1", "h-[calc(100vh-90px)]");
    }
    if (icon) icon.className = "fa-solid fa-compress mr-1.5 text-indigo-600";
    if (text) text.innerText = "Thu Nhỏ";
    document.addEventListener("keydown", handleFullscreenEsc);
    updateChuyenDoiStatus(chuyenDoiRows.length);
  } else {
    card.classList.remove("fixed", "inset-0", "z-50", "rounded-none", "border-0", "p-0", "h-screen", "w-screen");
    if (fsBar) fsBar.classList.add("hidden");
    if (wrapper) {
      wrapper.classList.add("max-h-[660px]");
      wrapper.classList.remove("flex-1", "h-[calc(100vh-90px)]");
    }
    if (icon) icon.className = "fa-solid fa-expand mr-1.5 text-indigo-600";
    if (text) text.innerText = "Toàn Màn Hình";
    document.removeEventListener("keydown", handleFullscreenEsc);
    updateChuyenDoiStatus(chuyenDoiRows.length);
  }
}

function handleFullscreenEsc(e) {
  if (e.key === "Escape" && isChuyenDoiFullscreen) {
    toggleChuyenDoiFullscreen();
  }
}

function renderChuyenDoiHeaders() {
  const theadSection = document.getElementById("thead-section-row");
  const theadCol = document.getElementById("thead-column-row");
  if (!theadSection || !theadCol) return;

  const visibleCols = getVisibleColumns();

  // Nhóm các cột liên tiếp theo section để tạo merged header Row 1
  const groupedSections = [];
  let currentSec = null;

  visibleCols.forEach(col => {
    if (!currentSec || currentSec.key !== col.section_key) {
      currentSec = {
        key: col.section_key,
        title: col.section,
        count: 1
      };
      groupedSections.push(currentSec);
    } else {
      currentSec.count++;
    }
  });

  // Row 1: Section Header
  theadSection.innerHTML = groupedSections.map(gs => {
    return `
      <th colspan="${gs.count}" class="p-2 text-center border-r border-slate-300 bg-slate-200 text-slate-800 font-bold">
        ${gs.title}
      </th>
    `;
  }).join("");

  // Row 2: Columns Header (Label + Code)
  theadCol.innerHTML = visibleCols.map(col => {
    let stickyClass = "";
    if (col.code === "STT") stickyClass = "cd-sticky-stt bg-slate-100";
    else if (col.code === "GCN_soPhatHanh") stickyClass = "cd-sticky-file bg-slate-100";
    else if (col.code === "GCN_soVaoSo") stickyClass = "cd-sticky-serial bg-slate-100";
    else if (col.code === "CHU_hoTen") stickyClass = "cd-sticky-owner bg-slate-100";

    return `
      <th class="p-2 border-r border-b border-slate-200 text-left font-semibold text-slate-700 whitespace-nowrap ${stickyClass}" title="${escHtml(col.label)} (${col.code})">
        <div class="truncate max-w-[150px] text-[11px]">${escHtml(col.label)}</div>
        <div class="text-[9px] font-mono text-slate-400 font-normal">${col.code}</div>
      </th>
    `;
  }).join("");
}

async function autoMapLatestResults() {
  if (batchResultsList && batchResultsList.length > 0) {
    loadCurrentBatchToChuyenDoi();
  } else {
    await loadVinhYen50ChuyenDoi();
  }
}

async function loadVinhYen50ChuyenDoi() {
  const btn = document.getElementById("btn-load-vinhyen-50");
  if (btn) {
    btn.disabled = true;
    btn.innerHTML = '<i class="fa-solid fa-spinner animate-spin mr-1.5 text-indigo-600"></i> Đang nạp từ DB...';
  }

  try {
    if (chuyenDoiColumns.length === 0) {
      await loadChuyenDoiColumns();
    }
    const res = await fetch("/chuyen-doi/load-from-markdown-db");
    if (!res.ok) throw new Error("Không thể tải dữ liệu Markdown từ DB");
    const data = await res.json();
    chuyenDoiRows = data.rows || [];

    // Reset về chế độ xem toàn bộ
    isAllColumnsMode = true;
    isCoreColumnsMode = false;
    activeSections = new Set(chuyenDoiSections.map(s => s.key));
    updateModeButtons();
    renderSectionPills();
    renderChuyenDoiHeaders();

    renderChuyenDoiGrid(chuyenDoiRows);
    updateChuyenDoiStatus(chuyenDoiRows.length);
  } catch (err) {
    alert(`Lỗi nạp mẫu Vĩnh Yên: ${err.message}`);
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = '<i class="fa-solid fa-database mr-1.5 text-indigo-600"></i> Nạp 50 Mẫu Vĩnh Yên';
    }
  }
}

function loadCurrentBatchToChuyenDoi() {
  if (!batchResultsList || batchResultsList.length === 0) {
    alert("Chưa có lượt quét thư mục nào trong phiên làm việc hiện tại!");
    return;
  }

  const rows = [];
  batchResultsList.forEach((r, idx) => {
    if (r.chuyen_doi_row) {
      rows.push(r.chuyen_doi_row);
    }
  });

  if (rows.length === 0) {
    alert("Các kết quả batch hiện tại chưa có dữ liệu chuyển đổi!");
    return;
  }

  chuyenDoiRows = rows;
  if (chuyenDoiColumns.length === 0) {
    loadChuyenDoiColumns().then(() => {
      renderChuyenDoiGrid(chuyenDoiRows);
      updateChuyenDoiStatus(chuyenDoiRows.length);
    });
  } else {
    renderChuyenDoiGrid(chuyenDoiRows);
    updateChuyenDoiStatus(chuyenDoiRows.length);
  }
}

function renderChuyenDoiGrid(rows) {
  const tbody = document.getElementById("tbody-chuyen-doi");
  if (!tbody) return;

  const visibleCols = getVisibleColumns();

  if (!rows || rows.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="${visibleCols.length || 20}" class="text-center py-12 text-slate-400">
          <i class="fa-solid fa-folder-open text-3xl mb-2 text-slate-300 block"></i>
          Không tìm thấy hồ sơ nào phù hợp với bộ lọc tìm kiếm.
        </td>
      </tr>
    `;
    return;
  }

  tbody.innerHTML = rows.map((row, rIdx) => {
    const isEven = rIdx % 2 === 0;
    const bgClass = isEven ? "bg-white" : "bg-slate-50/70";

    const cellsHtml = visibleCols.map(col => {
      const code = col.code;
      const rawVal = row[code];
      const val = rawVal !== undefined && rawVal !== null ? String(rawVal) : "";

      let stickyClass = "";
      if (code === "STT") stickyClass = `cd-sticky-stt ${bgClass}`;
      else if (code === "GCN_soPhatHanh") stickyClass = `cd-sticky-file ${bgClass}`;
      else if (code === "GCN_soVaoSo") stickyClass = `cd-sticky-serial ${bgClass}`;
      else if (code === "CHU_hoTen") stickyClass = `cd-sticky-owner ${bgClass}`;

      let align = "text-left";
      if (code === "STT" || code.includes("ma") || code.includes("ngay") || code.includes("gioiTinh")) {
        align = "text-center";
      } else if (code.includes("dienTich") || code.includes("soTang")) {
        align = "text-right font-mono font-semibold";
      }

      let cellContent = val ? escHtml(val) : '<span class="text-slate-300">-</span>';

      if (code === "CHU_hoTen" && val) {
        cellContent = `<span class="font-bold text-slate-900">${escHtml(val)}</span>`;
      } else if (code === "GCN_soPhatHanh" && val) {
        cellContent = `<span class="font-bold text-indigo-700 font-mono">${escHtml(val)}</span>`;
      } else if (code === "TD_dienTich" && val) {
        cellContent = `<span class="font-bold text-emerald-700 font-mono">${escHtml(val)} m²</span>`;
      } else if (code === "TD_maMucDichSuDung" && val) {
        cellContent = `<span class="px-1.5 py-0.5 rounded text-[11px] font-bold bg-blue-100 text-blue-800">${escHtml(val)}</span>`;
      } else if (code === "CHU_gioiTinh") {
        cellContent = val === "1" ? '<span class="text-blue-700 font-medium">Nam</span>' : (val === "0" ? '<span class="text-rose-700 font-medium">Nữ</span>' : '<span class="text-slate-300">-</span>');
      } else if (code === "VC_gioiTinh") {
        cellContent = val === "1" ? '<span class="text-blue-700 font-medium">Nam</span>' : (val === "0" ? '<span class="text-rose-700 font-medium">Nữ</span>' : '<span class="text-slate-300">-</span>');
      }

      return `
        <td class="p-2 border-r border-b border-slate-200 text-xs ${align} ${stickyClass} cell-truncate" title="${escHtml(val)}">
          ${cellContent}
        </td>
      `;
    }).join("");

    return `
      <tr class="hover:bg-indigo-50/50 transition cursor-pointer" onclick="openChuyenDoiModal(${rIdx})" title="Kích để xem chi tiết toàn bộ 129 trường">
        ${cellsHtml}
      </tr>
    `;
  }).join("");
}

function filterChuyenDoiGrid() {
  const query = (document.getElementById("chuyen-doi-search")?.value || "").toLowerCase().trim();
  if (!query) {
    renderChuyenDoiGrid(chuyenDoiRows);
    updateChuyenDoiStatus(chuyenDoiRows.length);
    return;
  }

  const filtered = chuyenDoiRows.filter(row => {
    return Object.values(row).some(v => v !== null && v !== undefined && String(v).toLowerCase().includes(query));
  });

  renderChuyenDoiGrid(filtered);
  updateChuyenDoiStatus(filtered.length);
}

function updateChuyenDoiStatus(count) {
  const visibleCols = getVisibleColumns();

  const countBadge = document.getElementById("chuyen-doi-row-count");
  if (countBadge) countBadge.innerText = `${count} hồ sơ`;

  const info = document.getElementById("grid-status-info");
  if (info) {
    info.innerText = `Hiển thị ${count} hồ sơ • ${visibleCols.length}/129 cột đang hiển thị`;
  }

  const fsInfo = document.getElementById("fs-status-info");
  if (fsInfo) {
    fsInfo.innerText = `${count} HỒ SƠ • ${visibleCols.length}/129 CỘT`;
  }
}

async function exportChuyenDoiExcel() {
  if (!chuyenDoiRows || chuyenDoiRows.length === 0) {
    alert("Chưa có dữ liệu để xuất! Vui lòng nạp 50 mẫu hoặc quét thư mục trước.");
    return;
  }

  const btn = document.getElementById("btn-export-chuyen-doi");
  if (btn) {
    btn.disabled = true;
    btn.innerHTML = '<i class="fa-solid fa-spinner animate-spin mr-1.5"></i> Đang kết xuất Excel...';
  }

  try {
    const query = (document.getElementById("chuyen-doi-search")?.value || "").toLowerCase().trim();
    let rowsToExport = chuyenDoiRows;
    if (query) {
      rowsToExport = chuyenDoiRows.filter(row => {
        return Object.values(row).some(v => v !== null && v !== undefined && String(v).toLowerCase().includes(query));
      });
    }

    const res = await fetch("/chuyen-doi/export", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        rows: rowsToExport,
        filename: `ChuyenDoiDuLieu_129Cot_${Date.now()}.xlsx`
      })
    });

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "Lỗi khi xuất file Excel");
    }

    const blob = await res.blob();
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `KetQua_ChuyenDoiDuLieu_129Cot_${rowsToExport.length}_HoSo.xlsx`;
    document.body.appendChild(a);
    a.click();
    window.URL.revokeObjectURL(url);
    a.remove();
  } catch (err) {
    alert(`Lỗi xuất Excel: ${err.message}`);
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = '<i class="fa-solid fa-file-arrow-down mr-1.5 text-sm"></i> Xuất File Excel (129 Cột)';
    }
  }
}

// ─── Modal Chi Tiết Hồ Sơ 129 Cột ──────────────────────────────────────────

let activeModalSectionKey = "gcn";

function openChuyenDoiModal(rowIndex) {
  const row = chuyenDoiRows[rowIndex];
  if (!row) return;
  currentModalRow = row;

  const modal = document.getElementById("chuyen-doi-detail-modal");
  const title = document.getElementById("modal-cd-title");
  const subtitle = document.getElementById("modal-cd-subtitle");

  title.innerText = `Hồ Sơ: ${row.GCN_soPhatHanh || "Chưa có seri"} - ${row.CHU_hoTen || "Chưa rõ chủ"}`;
  subtitle.innerText = `File: ${row.DDK_maDon || row.GCN_soPhatHanh || "Hồ sơ"} | Thửa: ${row.TD_soThuTuThua || "-"} | Tờ: ${row.TD_soHieuToBanDo || "-"}`;

  renderModalSectionTabs();
  renderModalSectionFields(activeModalSectionKey);

  modal.classList.remove("hidden");
}

function closeChuyenDoiModal() {
  const modal = document.getElementById("chuyen-doi-detail-modal");
  if (modal) modal.classList.add("hidden");
  currentModalRow = null;
}

function renderModalSectionTabs() {
  const container = document.getElementById("modal-cd-section-tabs");
  if (!container) return;

  container.innerHTML = chuyenDoiSections.map(sec => {
    const isActive = sec.key === activeModalSectionKey;
    const activeClass = isActive
      ? "bg-indigo-600 text-white shadow-sm font-bold"
      : "bg-white hover:bg-slate-200 text-slate-600 border border-slate-200";

    return `
      <button onclick="switchModalSection('${sec.key}')" class="text-xs px-3 py-1.5 rounded-lg transition ${activeClass}">
        ${sec.title} (${sec.count})
      </button>
    `;
  }).join("");
}

function switchModalSection(secKey) {
  activeModalSectionKey = secKey;
  renderModalSectionTabs();
  renderModalSectionFields(secKey);
}

function renderModalSectionFields(secKey) {
  const container = document.getElementById("modal-cd-fields-container");
  if (!container || !currentModalRow) return;

  const cols = chuyenDoiColumns.filter(c => c.section_key === secKey);

  container.innerHTML = `
    <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
      ${cols.map(col => {
        const val = currentModalRow[col.code] !== undefined && currentModalRow[col.code] !== null
          ? String(currentModalRow[col.code])
          : "";
        return `
          <div class="bg-slate-50 p-3 rounded-xl border border-slate-200 hover:border-indigo-300 transition">
            <div class="flex items-center justify-between mb-1">
              <span class="text-[11px] font-semibold text-slate-700">${escHtml(col.label)}</span>
              <span class="text-[9px] font-mono text-indigo-600 bg-indigo-50 px-1.5 py-0.5 rounded">${col.code}</span>
            </div>
            <div class="text-xs font-medium text-slate-900 break-words ${val ? '' : 'text-slate-300 italic'}">
              ${val ? escHtml(val) : '(Trống)'}
            </div>
            ${col.sample ? `<div class="text-[10px] text-slate-400 mt-1 truncate" title="Mẫu: ${escHtml(col.sample)}">Mẫu: ${escHtml(col.sample)}</div>` : ''}
          </div>
        `;
      }).join("")}
    </div>
  `;
}

