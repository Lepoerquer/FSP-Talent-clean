import React, { useState } from 'react';
import { Alert, Anchor, Badge, Box, Button, Divider, Group, PasswordInput, Stack, Text, TextInput, UnstyledButton } from '@mantine/core';
import { IconAlertCircle, IconKey, IconMail, IconShieldCheck } from '@tabler/icons-react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { homePathForRole, useAuth } from '../../auth/AuthContext';
import { toApiError } from '../../api/http';
import { AuthCard } from '../../components/common/AuthCard';
import { FspIdLoginModal } from '../../components/auth/FspIdLoginModal';
import { FspStarIcon } from '../../components/common/FspStarIcon';

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;

const DEMO_ACCOUNTS = [
  { email: 'anna@fsp-talent.ru', who: 'Анна Смирнова', note: 'Кандидат · Middle, есть история ФСП' },
  { email: 'boris@fsp-talent.ru', who: 'Борис Кузнецов', note: 'Кандидат · Middle, без истории ФСП' },
  { email: 'recruiter@techprom.ru', who: 'Работодатель', note: 'Кабинет работодателя с активной потребностью' },
];
const DEMO_PASSWORD = 'demo123';

import { usePageTitle } from '../../hooks/usePageTitle';

export const LoginPage: React.FC = () => {
  usePageTitle('Вход');
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const from = (location.state as { from?: string } | null)?.from;

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [touched, setTouched] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fspOpen, setFspOpen] = useState(false);

  const submit = async (e: string, p: string) => {
    setBusy(true);
    setError(null);
    try {
      const session = await login(e, p);
      if (!session.user.email_verified) navigate('/verify-email', { replace: true });
      else navigate(from ?? homePathForRole(session.user.role), { replace: true });
    } catch (err) {
      setError(toApiError(err).message);
    } finally {
      setBusy(false);
    }
  };

  const emailError = touched && !EMAIL_RE.test(email) ? 'Введите адрес электронной почты в формате name@example.com' : null;
  const passwordError = touched && !password ? 'Введите пароль' : null;

  return (
    <Stack gap="lg">
      <AuthCard title="Вход в личный кабинет" description="Войдите, чтобы пройти тестирование или найти специалистов.">
        <form
          noValidate
          onSubmit={(ev) => {
            ev.preventDefault();
            setTouched(true);
            if (EMAIL_RE.test(email) && password) void submit(email, password);
          }}
        >
          <Stack gap="md">
            {error && (
              <Alert color="red" variant="light" icon={<IconAlertCircle size={18} />} role="alert">
                {error}
              </Alert>
            )}
            <TextInput
              label="Электронная почта"
              placeholder="name@example.com"
              type="email"
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.currentTarget.value)}
              leftSection={<IconMail size={16} />}
              error={emailError}
              required
            />
            <PasswordInput
              label="Пароль"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.currentTarget.value)}
              leftSection={<IconKey size={16} />}
              error={passwordError}
              required
            />
            <Button type="submit" fullWidth loading={busy}>
              Войти
            </Button>
            <Divider label="или" labelPosition="center" />
            <Button
              variant="default"
              fullWidth
              leftSection={<FspStarIcon size={18} />}
              onClick={() => setFspOpen(true)}
              style={{ borderColor: 'var(--fsp-blue)', fontWeight: 600 }}
            >
              Войти через ФСП ID
            </Button>
            <Text size="sm" ta="center" c="dimmed">
              Нет аккаунта?{' '}
              <Anchor component={Link} to="/register" fw={600}>
                Зарегистрироваться
              </Anchor>
            </Text>
          </Stack>
        </form>
      </AuthCard>

      <Box maw={460} mx="auto" w="100%">
        <Divider label="Демонстрационные аккаунты" labelPosition="center" mb="sm" />
        <Stack gap="xs">
          {DEMO_ACCOUNTS.map((acc) => (
            <UnstyledButton
              key={acc.email}
              className="choice-card"
              style={{ borderRadius: 6, padding: '10px 12px' }}
              disabled={busy}
              onClick={() => {
                setEmail(acc.email);
                setPassword(DEMO_PASSWORD);
                void submit(acc.email, DEMO_PASSWORD);
              }}
            >
              <Group justify="space-between" wrap="nowrap">
                <Box>
                  <Text size="sm" fw={600}>
                    {acc.who}
                  </Text>
                  <Text size="xs" c="dimmed">
                    {acc.note}
                  </Text>
                </Box>
                <Badge variant="light" color="gray" style={{ flexShrink: 0 }}>
                  Войти
                </Badge>
              </Group>
            </UnstyledButton>
          ))}
        </Stack>
        <Text size="xs" c="dimmed" ta="center" mt="sm">
          Пароль демонстрационных аккаунтов: {DEMO_PASSWORD}. Экспресс-тест доступен{' '}
          <Anchor component={Link} to="/express" size="xs">
            без регистрации
          </Anchor>
          .
        </Text>
      </Box>
      <FspIdLoginModal opened={fspOpen} onClose={() => setFspOpen(false)} />
    </Stack>
  );
};
