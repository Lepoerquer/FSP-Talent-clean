import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { notifications } from '@mantine/notifications';
import { api, RegisterRequest } from '../api/api';
import { sessionStore, setUnauthorizedHandler, StoredSession } from '../api/http';

type Role = StoredSession['user']['role'];

interface AuthContextType {
  session: StoredSession | null;
  role: Role | null;
  /** Идёт первичная проверка сохранённой сессии. */
  loading: boolean;
  login: (email: string, password: string) => Promise<StoredSession>;
  register: (body: RegisterRequest) => Promise<StoredSession>;
  verifyEmail: (code: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

/** Домашняя страница роли: используется для редиректов после входа. */
export const homePathForRole = (role: Role | null | undefined): string =>
  role === 'EMPLOYER' ? '/employer/matching' : role === 'CANDIDATE' ? '/candidate' : role === 'ADMIN' ? '/demo' : '/login';

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const queryClient = useQueryClient();
  const [session, setSession] = useState<StoredSession | null>(() => sessionStore.read());
  const [loading, setLoading] = useState<boolean>(() => sessionStore.read() !== null);

  const apply = useCallback((next: StoredSession | null) => {
    sessionStore.write(next);
    setSession(next);
  }, []);

  const logout = useCallback(() => {
    apply(null);
    queryClient.clear();
  }, [apply, queryClient]);

  // Сохранённая сессия проверяется на сервере: токен мог истечь.
  useEffect(() => {
    const stored = sessionStore.read();
    if (!stored) return;
    api
      .me()
      .then((user) =>
        apply({
          token: stored.token,
          user: { id: user.id, email: user.email, role: user.role as Role, email_verified: user.email_verified, fsp_id: user.fsp_id ?? null },
        })
      )
      .catch(() => apply(null))
      .finally(() => setLoading(false));
  }, [apply]);

  // 401 на авторизованном запросе завершает сессию с пояснением.
  useEffect(() => {
    setUnauthorizedHandler(() => {
      notifications.show({ title: 'Сессия завершена', message: 'Срок действия входа истёк. Войдите снова.', color: 'orange' });
      logout();
    });
    return () => setUnauthorizedHandler(null);
  }, [logout]);

  const fromToken = (t: Awaited<ReturnType<typeof api.login>>): StoredSession => ({
    token: t.access_token,
    user: { id: t.user_id, email: t.email, role: t.role as Role, email_verified: t.email_verified, fsp_id: t.fsp_id ?? null },
  });

  const login = useCallback(
    async (email: string, password: string) => {
      const next = fromToken(await api.login(email, password));
      queryClient.clear();
      apply(next);
      return next;
    },
    [apply, queryClient]
  );

  const register = useCallback(
    async (body: RegisterRequest) => {
      const next = fromToken(await api.register(body));
      queryClient.clear();
      apply(next);
      return next;
    },
    [apply, queryClient]
  );

  const verifyEmail = useCallback(
    async (code: string) => {
      const user = await api.verifyEmail(code);
      const stored = sessionStore.read();
      if (stored) apply({ ...stored, user: { ...stored.user, email_verified: user.email_verified } });
    },
    [apply]
  );

  const value = useMemo(
    () => ({ session, role: session?.user.role ?? null, loading, login, register, verifyEmail, logout }),
    [session, loading, login, register, verifyEmail, logout]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};

export const useAuth = () => {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within an AuthProvider');
  return ctx;
};
