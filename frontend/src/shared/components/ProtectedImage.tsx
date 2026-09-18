import axios from 'axios';
import React, { useEffect, useState } from 'react';

type ProtectedImageProps = Omit<React.ImgHTMLAttributes<HTMLImageElement>, 'src'> & {
  src?: string;
};

/** Tải artifact OCR qua axios để interceptor gắn Bearer token Keycloak.
 * Trình duyệt không thể tự thêm Authorization header cho thẻ img thông thường. */
export const ProtectedImage: React.FC<ProtectedImageProps> = ({ src, alt = '', ...props }) => {
  const [objectUrl, setObjectUrl] = useState<string | undefined>();

  useEffect(() => {
    let active = true;
    let nextObjectUrl: string | undefined;
    if (!src) {
      setObjectUrl(undefined);
      return undefined;
    }
    if (src.startsWith('blob:') || src.startsWith('data:')) {
      setObjectUrl(src);
      return undefined;
    }
    void axios.get(src, { responseType: 'blob' })
      .then((response) => {
        nextObjectUrl = URL.createObjectURL(response.data);
        if (active) setObjectUrl(nextObjectUrl);
      })
      .catch(() => { if (active) setObjectUrl(undefined); });
    return () => {
      active = false;
      if (nextObjectUrl) URL.revokeObjectURL(nextObjectUrl);
    };
  }, [src]);

  return <img src={objectUrl} alt={alt} {...props} />;
};
