import React, { useRef, useState } from 'react';
import { Alert, Anchor, Button, Center, PinInput, Stack, Text } from '@mantine/core';
import { IconAlertCircle, IconMailCheck } from '@tabler/icons-react';
import { Navigate, useNavigate } from 'react-router-dom';
import { notifications } from '@mantine/notifications';
import { useAuth } from '../../auth/AuthContext';
import { toApiError } from '../../api/http';
import { AuthCard } from '../../components/common/AuthCard';

/** Подтверждение адреса электронной почты после регистрации (п. 2.2 ТЗ). */
import { usePageTitle } from '../../hooks/usePageTitle';

export const VerifyEmailPage: React.FC = () => {
  usePageTitle('Подтверждение почты');
  const { session, verifyEmail, logout, loading } = useAuth();
  const navigate = useNavigate();
  const [code, setCode] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Уже подтверждённых пользователей уводим отсюда сразу; после успешного ввода кода переход выполняет сам обработчик.
  const verifiedOnEntry = useRef(Boolean(session?.user.email_verified));

  if (loading) return null;
  if (!session) return <Navigate to="/login" replace />;

  const done = async (value: string) => {
    if (value.length !== 6) return;
    setBusy(true);
    setError(null);
    try {
      await verifyEmail(value);
      notifications.show({ title: 'Почта подтверждена', message: 'Аккаунт активирован.', color: 'teal' });
      navigate(session.user.role === 'EMPLOYER' ? '/employer/company' : '/candidate/onboarding', { replace: true });
    } catch (err) {
      setError(toApiError(err).message);
    } finally {
      setBusy(false);
    }
  };

  if (verifiedOnEntry.current) return <Navigate to="/" replace />;

  return (
    <AuthCard title="Подтверждение почты" description={<>Мы отправили шестизначный код на адрес <b>{session.user.email}</b>.</>}>
      <Stack gap="md" align="stretch">
        {error && (
          <Alert color="red" variant="light" icon={<IconAlertCircle size={18} />} role="alert">
            {error}
          </Alert>
        )}
        <Center>
          <PinInput
            length={6}
            type="number"
            oneTimeCode
            value={code}
            onChange={setCode}
            onComplete={done}
            disabled={busy}
            aria-label="Код подтверждения"
            size="md"
          />
        </Center>
        <Alert variant="light" color="gray" icon={<IconMailCheck size={18} />} p="sm">
          Демонстрационный стенд: письмо не отправляется, введите код <b>123456</b>.
        </Alert>
        <Button loading={busy} disabled={code.length !== 6} onClick={() => done(code)}>
          Подтвердить
        </Button>
        <Text size="sm" ta="center" c="dimmed">
          Ошиблись адресом?{' '}
          <Anchor component="button" type="button" onClick={logout} fw={600}>
            Выйти и зарегистрироваться заново
          </Anchor>
        </Text>
      </Stack>
    </AuthCard>
  );
};
