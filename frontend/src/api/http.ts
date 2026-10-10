import axios, { AxiosError, AxiosInstance } from 'axios';

/**
 * HTTP-клиент платформы. Адрес API берётся из VITE_API_URL, по умолчанию — относительный /api/v1
 * (в разработке проксируется Vite на :8000, в Docker — nginx на backend).
 */
export const API_BASE_URL: string = import.meta.env.VITE_API_URL || '/api/v1';

const SESSION_KEY = 'fsp_talent_session_v2';

export interface StoredSession {
  token: string;
  user: {
    id: string;
    email: string;
    role: 'CANDIDATE' | 'EMPLOYER' | 'ADMIN';
    email_verified: boolean;
    fsp_id: string | null;
  };
}

// Токен хранится в sessionStorage: живёт до закрытия вкладки и не попадает в долговременное хранилище.
export const sessionStore = {
  read(): StoredSession | null {
    try {
      const raw = sessionStorage.getItem(SESSION_KEY);
      return raw ? (JSON.parse(raw) as StoredSession) : null;
    } catch {
      return null;
    }
  },
  write(session: StoredSession | null) {
    try {
      if (session) sessionStorage.setItem(SESSION_KEY, JSON.stringify(session));
      else sessionStorage.removeItem(SESSION_KEY);
    } catch {
      /* хранилище недоступно — сессия живёт только до перезагрузки */
    }
  },
};

export const http: AxiosInstance = axios.create({
  baseURL: API_BASE_URL,
  headers: { 'Content-Type': 'application/json' },
  timeout: 15000,
});

http.interceptors.request.use((config) => {
  const session = sessionStore.read();
  if (session?.token) config.headers.set('Authorization', `Bearer ${session.token}`);
  return config;
});

type UnauthorizedHandler = () => void;
let onUnauthorized: UnauthorizedHandler | null = null;
export const setUnauthorizedHandler = (fn: UnauthorizedHandler | null) => {
  onUnauthorized = fn;
};

http.interceptors.response.use(
  (res) => res,
  (error: AxiosError) => {
    // истёкший или недействительный токен: только если запрос был авторизованным
    const hadToken = Boolean(error.config?.headers?.get?.('Authorization'));
    const url = error.config?.url ?? '';
    if (error.response?.status === 401 && hadToken && !url.includes('/auth/login')) onUnauthorized?.();
    return Promise.reject(error);
  }
);

/** Ошибка API с уже подготовленным для пользователя текстом. */
export class ApiError extends Error {
  status?: number;
  code?: string;
  constructor(message: string, status?: number, code?: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
  }
}

const FIELD_LABELS: Record<string, string> = {
  email: 'Электронная почта',
  password: 'Пароль',
  first_name: 'Имя',
  last_name: 'Фамилия',
  company_name: 'Название компании',
  message: 'Текст предложения',
  salary_from: 'Зарплата от',
  salary_to: 'Зарплата до',
  inn: 'ИНН',
  fsp_id: 'ФСП ID',
  solution_text: 'Решение',
};

/** Приводит ответ FastAPI (строка, объект с error_code или список ошибок валидации) к тексту для интерфейса. */
export const toApiError = (e: unknown): ApiError => {
  if (e instanceof ApiError) return e;
  if (axios.isAxiosError(e)) {
    if (!e.response) {
      return new ApiError('Сервер недоступен. Проверьте подключение и повторите попытку.', undefined, 'NETWORK');
    }
    const { status, data } = e.response;
    const detail = (data as { detail?: unknown } | undefined)?.detail;
    if (typeof detail === 'string') return new ApiError(detail, status);
    if (Array.isArray(detail)) {
      const parts = detail.map((d: { loc?: Array<string | number>; msg?: string }) => {
        const field = String(d.loc?.[d.loc.length - 1] ?? '');
        const label = FIELD_LABELS[field];
        return label ? `${label}: ${d.msg}` : d.msg;
      });
      return new ApiError(parts.filter(Boolean).join('; ') || 'Проверьте введённые данные.', status);
    }
    if (detail && typeof detail === 'object') {
      const obj = detail as { message?: string; error_code?: string };
      return new ApiError(obj.message ?? 'Запрос отклонён сервером.', status, obj.error_code);
    }
    if (status === 401) return new ApiError('Требуется вход в систему.', status);
    if (status === 403) return new ApiError('Недостаточно прав для этого действия.', status);
    if (status === 404) return new ApiError('Запрошенные данные не найдены.', status);
    if (status >= 500) return new ApiError('Ошибка на стороне сервера. Повторите попытку позже.', status);
    return new ApiError('Запрос отклонён сервером.', status);
  }
  return new ApiError(e instanceof Error ? e.message : 'Неизвестная ошибка.');
};
