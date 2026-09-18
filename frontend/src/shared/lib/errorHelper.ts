/**
 * Trích xuất thông báo lỗi chính xác từ Axios error,
 * đặc biệt xử lý trường hợp responseType là 'blob' khi backend trả về JSON lỗi.
 */
export async function extractErrorMessage(error: any, fallbackMessage: string = 'Đã xảy ra lỗi khi thực hiện thao tác.'): Promise<string> {
  if (!error) return fallbackMessage;

  // Trường hợp response data là Blob (do request dùng responseType: 'blob')
  if (error.response?.data instanceof Blob) {
    try {
      const text = await error.response.data.text();
      if (text) {
        try {
          const parsed = JSON.parse(text);
          if (parsed && typeof parsed.detail === 'string') {
            return parsed.detail;
          }
          if (parsed && typeof parsed.message === 'string') {
            return parsed.message;
          }
        } catch {
          if (text.length < 300) return text;
        }
      }
    } catch {
      // Bỏ qua lỗi đọc blob
    }
  }

  // Trường hợp response data đã được parse JSON
  if (error.response?.data?.detail) {
    const detail = error.response.data.detail;
    if (typeof detail === 'string') return detail;
    if (Array.isArray(detail) && detail.length > 0) {
      return detail.map((d: any) => d.msg || JSON.stringify(d)).join('; ');
    }
  }

  if (error.response?.data?.message && typeof error.response.data.message === 'string') {
    return error.response.data.message;
  }

  // Mã lỗi HTTP phổ biến
  if (error.response?.status === 403) {
    return 'Tài khoản không có quyền thực hiện thao tác này.';
  }
  if (error.response?.status === 401) {
    return 'Phiên đăng nhập đã hết hạn. Vui lòng làm mới trang hoặc đăng nhập lại.';
  }
  if (error.response?.status === 404) {
    return 'Không tìm thấy dữ liệu yêu cầu trên máy chủ.';
  }
  if (error.response?.status >= 500) {
    return 'Máy chủ gặp lỗi trong quá trình xử lý (HTTP 500). Vui lòng kiểm tra lại dịch vụ.';
  }

  if (error.message && typeof error.message === 'string') {
    return error.message;
  }

  return fallbackMessage;
}
