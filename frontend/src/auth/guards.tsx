import React from 'react';
import { Center, Loader } from '@mantine/core';
import { Navigate, Outlet, useLocation } from 'react-router-dom';
import { homePathForRole, useAuth } from './AuthContext';

interface RequireAuthProps {
  role: 'CANDIDATE' | 'EMPLOYER';
}

/** Пускает только авторизованных пользователей нужной роли с подтверждённой почтой. */
export const RequireAuth: React.FC<RequireAuthProps> = ({ role }) => {
  const { session, loading } = useAuth();
  const location = useLocation();

  if (loading) {
    return (
      <Center h="100vh">
        <Loader color="fspPink" size="sm" />
      </Center>
    );
  }
  if (!session) return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  if (!session.user.email_verified) return <Navigate to="/verify-email" replace />;
  if (session.user.role !== role) return <Navigate to={homePathForRole(session.user.role)} replace />;
  return <Outlet />;
};

/** Страницы входа и регистрации: авторизованных отправляет в их кабинет. */
export const GuestOnly: React.FC = () => {
  const { session, loading } = useAuth();
  if (loading) return null;
  if (session?.user.email_verified) return <Navigate to={homePathForRole(session.user.role)} replace />;
  return <Outlet />;
};
