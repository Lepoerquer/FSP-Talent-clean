import React, { useEffect, useState } from 'react';
import { Accordion, Alert, Badge, Box, Button, Code, Group, List, PasswordInput, Stack, Text, TextInput, ThemeIcon } from '@mantine/core';
import { IconAlertCircle, IconCheck, IconKey, IconLoader, IconMail, IconShieldCheck } from '@tabler/icons-react';
import { useNavigate } from 'react-router-dom';
import { homePathForRole, useAuth } from '../../auth/AuthContext';
import { toApiError } from '../../api/http';
import { createPkce, PkcePair, randomUrlSafe } from '../../utils/pkce';
import { AppModal } from '../common/AppModal';
import { FspStarIcon } from '../common/FspStarIcon';

interface FspIdLoginModalProps {
  opened: boolean;
  onClose: () => void;
}

const REALM = 'fsp-talent';
const CLIENT_ID = 'fsp-talent-web';
const SCOPE = 'openid profile email fsp:achievements';

type Step = 'form' | 'redirect' | 'exchange' | 'done';

/**
 * Имитация входа через ФСП ID (Keycloak, OpenID Connect, Authorization Code + PKCE).
 * Боевых доступов к Keycloak ФСП командам не выдают (решение Q&A), поэтому воспроизведены шаги протокола:
 * параметры запроса авторизации с PKCE, ввод учётных данных ФСП ID и обмен кода на токен.
 * Учётные данные проверяет внутренний провайдер платформы (AUTH_PROVIDER=internal); при подключении
 * реального Keycloak заменяется только шаг обмена кода на токен.
 */
export const FspIdLoginModal: React.FC<FspIdLoginModalProps> = ({ opened, onClose }) => {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [step, setStep] = useState<Step>('form');
  const [error, setError] = useState<string | null>(null);
  const [pkce, setPkce] = useState<PkcePair | null>(null);
  const [state, setState] = useState('');

  // Параметры запроса авторизации формируются при открытии окна, как это делал бы клиент OIDC.
  useEffect(() => {
    if (!opened) return;
    setStep('form');
    setError(null);
    setState(randomUrlSafe(12));
    createPkce().then(setPkce);
  }, [opened]);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email || !password) {
      setError('Введите адрес электронной почты и пароль аккаунта ФСП ID.');
      return;
    }
    setError(null);
    try {
      setStep('redirect');
      await new Promise((r) => setTimeout(r, 450));
      setStep('exchange');
      const session = await login(email.trim(), password);
      setStep('done');
      await new Promise((r) => setTimeout(r, 350));
      onClose();
      navigate(session.user.email_verified ? homePathForRole(session.user.role) : '/verify-email', { replace: true });
    } catch (err) {
      setStep('form');
      setError(toApiError(err).message);
    }
  };

  const busy = step !== 'form';
  const steps: Array<[Step, string]> = [
    ['redirect', 'Перенаправление на сервер авторизации ФСП ID'],
    ['exchange', 'Обмен кода авторизации на токен (PKCE)'],
    ['done', 'Токен получен, сессия открыта'],
  ];
  const order: Step[] = ['form', 'redirect', 'exchange', 'done'];

  return (
    <AppModal
      opened={opened}
      onClose={busy ? () => undefined : onClose}
      title={
        <Group gap="xs">
          <FspStarIcon size={20} />
          <Text fw={700}>Вход через ФСП ID</Text>
        </Group>
      }
      closeOnClickOutside={!busy}
    >
      <Stack gap="md">
        <Alert variant="light" color="fspBlue" icon={<FspStarIcon size={18} />} p="sm">
          Единый вход участников Федерации спортивного программирования. На стенде подключение имитируется: протокол воспроизведён, но боевой сервер
          Keycloak не используется.
        </Alert>

        <form onSubmit={submit} noValidate>
          <Stack gap="sm">
            {error && (
              <Alert color="red" variant="light" icon={<IconAlertCircle size={18} />} role="alert">
                {error}
              </Alert>
            )}
            <TextInput
              label="Электронная почта ФСП ID"
              type="email"
              autoComplete="email"
              leftSection={<IconMail size={16} />}
              value={email}
              onChange={(e) => setEmail(e.currentTarget.value)}
              disabled={busy}
              required
            />
            <PasswordInput
              label="Пароль"
              autoComplete="current-password"
              leftSection={<IconKey size={16} />}
              value={password}
              onChange={(e) => setPassword(e.currentTarget.value)}
              disabled={busy}
              required
            />
            <Button type="submit" loading={busy} leftSection={<IconShieldCheck size={16} />} fullWidth>
              Войти через ФСП ID
            </Button>
          </Stack>
        </form>

        {busy && (
          <List spacing={6} size="sm" center aria-live="polite">
            {steps.map(([key, label]) => {
              const reached = order.indexOf(step) >= order.indexOf(key);
              const finished = order.indexOf(step) > order.indexOf(key) || step === 'done';
              return (
                <List.Item
                  key={key}
                  icon={
                    <ThemeIcon size={18} radius="xl" variant={reached ? 'filled' : 'light'} color={finished ? 'teal' : reached ? 'fspPink' : 'gray'}>
                      {finished ? <IconCheck size={11} /> : <IconLoader size={11} />}
                    </ThemeIcon>
                  }
                >
                  <Text span c={reached ? undefined : 'dimmed'}>
                    {label}
                  </Text>
                </List.Item>
              );
            })}
          </List>
        )}

        <Accordion variant="contained" radius="sm">
          <Accordion.Item value="tech">
            <Accordion.Control>
              <Text size="sm" fw={600}>
                Технические параметры запроса (имитация OIDC)
              </Text>
            </Accordion.Control>
            <Accordion.Panel>
              <Stack gap={6}>
                {[
                  ['realm', REALM],
                  ['client_id', CLIENT_ID],
                  ['response_type', 'code'],
                  ['scope', SCOPE],
                  ['redirect_uri', `${window.location.origin}/login`],
                  ['state', state],
                  ['code_challenge_method', pkce?.method ?? '…'],
                  ['code_challenge', pkce?.challenge ?? '…'],
                ].map(([k, v]) => (
                  <Box key={k}>
                    <Group gap={6} align="baseline" wrap="nowrap">
                      <Badge variant="light" color="gray" size="sm" style={{ flexShrink: 0 }}>
                        {k}
                      </Badge>
                      <Code style={{ overflowWrap: 'anywhere' }}>{v}</Code>
                    </Group>
                  </Box>
                ))}
                <Text size="xs" c="dimmed" mt={4}>
                  code_verifier хранится только в памяти страницы и отправляется при обмене кода на токен; в рабочей схеме обмен выполняет конечная точка /token Keycloak.
                </Text>
              </Stack>
            </Accordion.Panel>
          </Accordion.Item>
        </Accordion>
      </Stack>
    </AppModal>
  );
};
