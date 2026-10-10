import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { MantineProvider } from '@mantine/core';
import { Notifications } from '@mantine/notifications';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import { theme } from './theme/theme';
import { AuthProvider, useAuth, homePathForRole } from './auth/AuthContext';
import { GuestOnly, RequireAuth } from './auth/guards';
import { BackendGate } from './components/common/BackendGate';

// Layouts
import { CandidateLayout } from './components/layout/CandidateLayout';
import { EmployerLayout } from './components/layout/EmployerLayout';
import { PublicLayout } from './components/layout/PublicLayout';

// Pages
import { LoginPage } from './pages/auth/LoginPage';
import { RegisterPage } from './pages/auth/RegisterPage';
import { VerifyEmailPage } from './pages/auth/VerifyEmailPage';
import { CandidateCabinetPage } from './pages/CandidateCabinetPage';
import { CandidateVacanciesPage } from './pages/CandidateVacanciesPage';
import { CandidateOnboardingPage } from './pages/CandidateOnboardingPage';
import { AssessmentPlayerPage } from './pages/AssessmentPlayerPage';
import { CandidateFSPPage } from './pages/CandidateFSPPage';
import { CandidateSettingsPage } from './pages/CandidateSettingsPage';
import { EmployerMatchingPage } from './pages/EmployerMatchingPage';
import { EmployerBankPage } from './pages/EmployerBankPage';
import { EmployerInvitationsPage } from './pages/EmployerInvitationsPage';
import { EmployerCompanyPage } from './pages/EmployerCompanyPage';
import { DemoShowcasePage } from './pages/DemoShowcasePage';
import { CandidateVerificationPage } from './pages/CandidateVerificationPage';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      retry: 1,
    },
  },
});

/** Корень и неизвестные адреса: в кабинет своей роли или на страницу входа. */
const HomeRedirect: React.FC = () => {
  const { session, loading } = useAuth();
  if (loading) return null;
  return <Navigate to={session ? homePathForRole(session.user.role) : '/login'} replace />;
};

export const App: React.FC = () => {
  return (
    <QueryClientProvider client={queryClient}>
      <MantineProvider theme={theme} defaultColorScheme="light">
        <Notifications position="bottom-right" zIndex={1000} />
        <BackendGate>
          <AuthProvider>
            <BrowserRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
              <Routes>
                {/* Публичные страницы */}
                <Route element={<PublicLayout />}>
                  <Route path="/demo" element={<DemoShowcasePage />} />
                  <Route path="/express" element={<AssessmentPlayerPage publicMode />} />
                  <Route path="/verify/candidates/:id" element={<CandidateVerificationPage />} />
                  <Route path="/verify/:id" element={<CandidateVerificationPage />} />
                  <Route element={<GuestOnly />}>
                    <Route path="/login" element={<LoginPage />} />
                    <Route path="/register" element={<RegisterPage />} />
                  </Route>
                  <Route path="/verify-email" element={<VerifyEmailPage />} />
                </Route>

                {/* Кабинет кандидата */}
                <Route element={<RequireAuth role="CANDIDATE" />}>
                  <Route path="/candidate" element={<CandidateLayout />}>
                    <Route index element={<CandidateCabinetPage view="dashboard" />} />
                    <Route path="onboarding" element={<CandidateOnboardingPage />} />
                    <Route path="assessment" element={<AssessmentPlayerPage />} />
                    <Route path="invitations" element={<CandidateCabinetPage view="invitations" />} />
                    <Route path="fsp" element={<CandidateFSPPage />} />
                    <Route path="settings" element={<CandidateSettingsPage />} />
                    <Route path="vacancies" element={<CandidateVacanciesPage />} />
                  </Route>
                </Route>

                {/* Кабинет работодателя */}
                <Route element={<RequireAuth role="EMPLOYER" />}>
                  <Route path="/employer" element={<EmployerLayout />}>
                    <Route index element={<Navigate to="/employer/matching" replace />} />
                    <Route path="matching" element={<EmployerMatchingPage />} />
                    <Route path="bank" element={<EmployerBankPage />} />
                    <Route path="invitations" element={<EmployerInvitationsPage />} />
                    <Route path="company" element={<EmployerCompanyPage />} />
                  </Route>
                </Route>

                <Route path="*" element={<HomeRedirect />} />
              </Routes>
            </BrowserRouter>
          </AuthProvider>
        </BackendGate>
      </MantineProvider>
    </QueryClientProvider>
  );
};
