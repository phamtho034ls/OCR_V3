import axios from 'axios';
import Keycloak from 'keycloak-js';
import React, { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react';

export interface AuthUser {
  id: string;
  username: string;
  display_name: string;
  email?: string | null;
  roles: string[];
  permissions: string[];
  region?: string;
}

interface KeycloakPublicConfig {
  enabled: boolean;
  url: string;
  realm: string;
  client_id: string;
}

interface AuthContextValue {
  user: AuthUser | null;
  loading: boolean;
  error: string | null;
  can: (permission: string) => boolean;
  logout: () => Promise<void>;
  retry: () => void;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

const localDevelopmentUser: AuthUser = {
  id: 'local-development',
  username: 'local-development',
  display_name: 'Local development',
  roles: ['ocr-admin'],
  permissions: ['*'],
};

// Biến toàn cục module để tránh khởi tạo Keycloak nhiều lần khi React 18 StrictMode mount/unmount kép
let keycloakInstance: Keycloak | null = null;
let initPromise: Promise<{ user: AuthUser | null; keycloak: Keycloak | null }> | null = null;
let interceptorId: number | null = null;
let responseInterceptorId: number | null = null;

function setupAxiosInterceptor(keycloak: Keycloak) {
  if (interceptorId !== null) {
    axios.interceptors.request.eject(interceptorId);
    interceptorId = null;
  }
  if (responseInterceptorId !== null) {
    axios.interceptors.response.eject(responseInterceptorId);
    responseInterceptorId = null;
  }
  interceptorId = axios.interceptors.request.use(async (request) => {
    if (keycloak.authenticated) {
      try {
        await keycloak.updateToken(30);
        if (keycloak.token) {
          request.headers = request.headers || {};
          request.headers.Authorization = `Bearer ${keycloak.token}`;
        }
      } catch (err) {
        console.warn('Không thể tự động làm mới token Keycloak:', err);
      }
    }
    return request;
  });

  responseInterceptorId = axios.interceptors.response.use(
    (response) => response,
    async (error) => {
      if (error.response?.status === 401 && keycloak.authenticated) {
        try {
          const refreshed = await keycloak.updateToken(-1);
          if (refreshed && error.config) {
            error.config.headers = error.config.headers || {};
            error.config.headers.Authorization = `Bearer ${keycloak.token}`;
            return axios.request(error.config);
          }
        } catch {
          console.warn('Phiên đăng nhập Keycloak đã kết thúc, yêu cầu đăng nhập lại.');
          void keycloak.login();
        }
      }
      return Promise.reject(error);
    }
  );
}

async function doInitializeAuth(): Promise<{ user: AuthUser | null; keycloak: Keycloak | null }> {
  let configResponse: Response;
  try {
    configResponse = await fetch('/api/v1/auth/config');
  } catch (err) {
    throw new Error('Không thể kết nối đến máy chủ API Backend (cổng 8000). Vui lòng kiểm tra backend đã khởi động chưa.');
  }

  if (!configResponse.ok) {
    throw new Error(`Máy chủ trả về lỗi khi lấy cấu hình đăng nhập (HTTP ${configResponse.status}). Hãy kiểm tra Backend.`);
  }

  const config = (await configResponse.json()) as KeycloakPublicConfig;
  if (!config.enabled) {
    return { user: localDevelopmentUser, keycloak: null };
  }

  if (!keycloakInstance) {
    keycloakInstance = new Keycloak({
      url: config.url,
      realm: config.realm,
      clientId: config.client_id,
    });
  }

  const keycloak = keycloakInstance;
  setupAxiosInterceptor(keycloak);

  if (!keycloak.didInitialize) {
    const authenticated = await keycloak.init({
      onLoad: 'login-required',
      pkceMethod: 'S256',
      checkLoginIframe: false,
    });

    if (!authenticated) {
      throw new Error('Chưa đăng nhập Keycloak hoặc phiên đăng nhập đã hết hạn.');
    }
  }

  const headers: Record<string, string> = {};
  if (keycloak.token) {
    headers.Authorization = `Bearer ${keycloak.token}`;
  }

  const me = await axios.get<AuthUser>('/api/v1/auth/me', { headers });
  return { user: me.data, keycloak };
}

export const AuthProvider: React.FC<React.PropsWithChildren> = ({ children }) => {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [retryTrigger, setRetryTrigger] = useState(0);

  useEffect(() => {
    let alive = true;

    if (!initPromise) {
      initPromise = doInitializeAuth();
    }

    initPromise
      .then((result) => {
        if (alive) {
          setUser(result.user);
          setError(null);
        }
      })
      .catch((cause) => {
        if (alive) {
          // Xóa promise lỗi để lần retry sau có thể chạy lại
          initPromise = null;
          setError(cause instanceof Error ? cause.message : 'Không thể khởi tạo đăng nhập Keycloak.');
        }
      })
      .finally(() => {
        if (alive) {
          setLoading(false);
        }
      });

    return () => {
      alive = false;
    };
  }, [retryTrigger]);

  const logout = useCallback(async () => {
    if (keycloakInstance?.authenticated) {
      initPromise = null;
      await keycloakInstance.logout({ redirectUri: window.location.origin });
    }
  }, []);

  const retry = useCallback(() => {
    initPromise = null;
    setError(null);
    setLoading(true);
    setRetryTrigger((prev) => prev + 1);
  }, []);

  const value = useMemo<AuthContextValue>(() => ({
    user,
    loading,
    error,
    can: (permission) => Boolean(user?.permissions.includes('*') || user?.permissions.includes(permission)),
    logout,
    retry,
  }), [error, loading, logout, retry, user]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};

export const useAuth = (): AuthContextValue => {
  const context = useContext(AuthContext);
  if (!context) throw new Error('useAuth phải được đặt bên trong AuthProvider.');
  return context;
};

export const Can: React.FC<React.PropsWithChildren<{ permission: string }>> = ({ permission, children }) => {
  const { can } = useAuth();
  return can(permission) ? <>{children}</> : null;
};
