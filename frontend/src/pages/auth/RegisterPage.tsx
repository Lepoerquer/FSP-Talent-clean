import React, { useState } from 'react';
import { Alert, Anchor, Button, Checkbox, PasswordInput, SegmentedControl, Stack, Text, TextInput } from '@mantine/core';
import { IconAlertCircle, IconBuildingSkyscraper, IconMail, IconUser } from '@tabler/icons-react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../../auth/AuthContext';
import { toApiError } from '../../api/http';
import { AuthCard } from '../../components/common/AuthCard';

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;

type Role = 'CANDIDATE' | 'EMPLOYER';

import { usePageTitle } from '../../hooks/usePageTitle';

export const RegisterPage: React.FC = () => {
  usePageTitle('Регистрация');
  const { register } = useAuth();
  const navigate = useNavigate();

  const [role, setRole] = useState<Role>('CANDIDATE');
  const [firstName, setFirstName] = useState('');
  const [lastName, setLastName] = useState('');
  const [companyName, setCompanyName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [repeat, setRepeat] = useState('');
  const [consentData, setConsentData] = useState(false);
  const [consentProfile, setConsentProfile] = useState(true);
  const [touched, setTouched] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const errors = {
    firstName: role === 'CANDIDATE' && !firstName.trim() ? 'Укажите имя' : null,
    lastName: role === 'CANDIDATE' && !lastName.trim() ? 'Укажите фамилию' : null,
    companyName: role === 'EMPLOYER' && !companyName.trim() ? 'Укажите название организации' : null,
    email: !EMAIL_RE.test(email) ? 'Введите адрес электронной почты в формате name@example.com' : null,
    password:
      password.length < 8 || !/[A-Za-zА-Яа-я]/.test(password) || !/\d/.test(password)
        ? 'Не менее 8 символов, с буквами и цифрами'
        : null,
    repeat: repeat !== password ? 'Пароли не совпадают' : null,
    consent: !consentData ? 'Без согласия на обработку персональных данных регистрация невозможна' : null,
  };
  const valid = Object.values(errors).every((e) => !e);
  const show = <K extends keyof typeof errors>(k: K) => (touched ? errors[k] : null);

  const submit = async (ev: React.FormEvent) => {
    ev.preventDefault();
    setTouched(true);
    if (!valid) return;
    setBusy(true);
    setError(null);
    try {
      await register({
        email: email.trim(),
        password,
        role,
        first_name: role === 'CANDIDATE' ? firstName.trim() : null,
        last_name: role === 'CANDIDATE' ? lastName.trim() : null,
        company_name: role === 'EMPLOYER' ? companyName.trim() : null,
        consent_personal_data: consentData,
        consent_profile_distribution: role === 'CANDIDATE' ? consentProfile : false,
      });
      navigate('/verify-email', { replace: true });
    } catch (err) {
      setError(toApiError(err).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <AuthCard title="Регистрация" description="Создайте кабинет кандидата или работодателя. Адрес электронной почты потребуется подтвердить." width={520}>
      <form onSubmit={submit} noValidate>
        <Stack gap="md">
          {error && (
            <Alert color="red" variant="light" icon={<IconAlertCircle size={18} />} role="alert">
              {error}
            </Alert>
          )}

          <SegmentedControl
            fullWidth
            value={role}
            onChange={(v) => setRole(v as Role)}
            data={[
              { value: 'CANDIDATE', label: <span>Я соискатель</span> },
              { value: 'EMPLOYER', label: <span>Я работодатель</span> },
            ]}
            aria-label="Тип аккаунта"
          />

          {role === 'CANDIDATE' ? (
            <Stack gap="md">
              <TextInput label="Имя" required leftSection={<IconUser size={16} />} value={firstName} onChange={(e) => setFirstName(e.currentTarget.value)} error={show('firstName')} autoComplete="given-name" />
              <TextInput label="Фамилия" required value={lastName} onChange={(e) => setLastName(e.currentTarget.value)} error={show('lastName')} autoComplete="family-name" />
            </Stack>
          ) : (
            <TextInput
              label="Название организации"
              required
              leftSection={<IconBuildingSkyscraper size={16} />}
              value={companyName}
              onChange={(e) => setCompanyName(e.currentTarget.value)}
              error={show('companyName')}
              autoComplete="organization"
            />
          )}

          <TextInput
            label="Электронная почта"
            type="email"
            required
            placeholder="name@example.com"
            leftSection={<IconMail size={16} />}
            value={email}
            onChange={(e) => setEmail(e.currentTarget.value)}
            error={show('email')}
            autoComplete="email"
          />
          <PasswordInput label="Пароль" required value={password} onChange={(e) => setPassword(e.currentTarget.value)} error={show('password')} autoComplete="new-password" description="Не менее 8 символов, буквы и цифры" />
          <PasswordInput label="Повторите пароль" required value={repeat} onChange={(e) => setRepeat(e.currentTarget.value)} error={show('repeat')} autoComplete="new-password" />

          <Stack gap="xs">
            <Checkbox
              checked={consentData}
              onChange={(e) => setConsentData(e.currentTarget.checked)}
              error={show('consent')}
              label="Даю согласие на обработку персональных данных в соответствии с 152-ФЗ"
            />
            {role === 'CANDIDATE' && (
              <Checkbox
                checked={consentProfile}
                onChange={(e) => setConsentProfile(e.currentTarget.checked)}
                label="Разрешаю показывать мою карточку работодателям (ст. 10.1 152-ФЗ). Контакты передаются только после принятия приглашения"
              />
            )}
          </Stack>

          <Button type="submit" fullWidth loading={busy}>
            Создать аккаунт
          </Button>
          <Text size="sm" ta="center" c="dimmed">
            Уже зарегистрированы?{' '}
            <Anchor component={Link} to="/login" fw={600}>
              Войти
            </Anchor>
          </Text>
        </Stack>
      </form>
    </AuthCard>
  );
};
