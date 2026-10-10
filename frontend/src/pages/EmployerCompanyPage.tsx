import React, { useEffect, useState } from 'react';
import { Alert, Badge, Box, Button, Card, Container, Group, NumberInput, Paper, Select, SimpleGrid, Skeleton, Stack, TagsInput, Text, Textarea, TextInput, Title } from '@mantine/core';
import { IconCheck, IconCode, IconInfoCircle, IconPlugConnected, IconPlus, IconShieldCheck, IconShieldX } from '@tabler/icons-react';
import { notifications } from '@mantine/notifications';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api, AtsSyncResult, Challenge, VerifyInn } from '../api/api';
import { toApiError } from '../api/http';
import { keys, useCompany, useCompanyInvitations, useDictionaries } from '../hooks/queries';
import { PageHeader } from '../components/common/PageHeader';
import { QueryError } from '../components/common/QueryError';
import { AppModal } from '../components/common/AppModal';
import { formatDate, isValidInn } from '../utils/format';
import { gradeLabel, specLabel } from '../utils/labels';

interface FormState {
  name: string;
  inn: string;
  website: string;
  description: string;
}

import { usePageTitle } from '../hooks/usePageTitle';

export const EmployerCompanyPage: React.FC = () => {
  usePageTitle('Профиль компании');
  const queryClient = useQueryClient();
  const { data: company, isLoading, isError, error, refetch } = useCompany();
  const { data: invitations = [] } = useCompanyInvitations();

  const [form, setForm] = useState<FormState | null>(null);
  const [touched, setTouched] = useState(false);
  const [verifyResult, setVerifyResult] = useState<VerifyInn | null>(null);
  const { data: dict } = useDictionaries();

  // Синхронизация вакансии из внешней ATS
  const [ats, setAts] = useState({
    system: 'HUNTFLOW',
    externalId: '',
    title: '',
    specialization: 'BACKEND',
    grade: 'MIDDLE',
    salaryMin: '' as number | string,
    salaryMax: '' as number | string,
    salaryType: 'NET',
    skills: [] as string[],
    description: '',
  });
  const [atsResult, setAtsResult] = useState<AtsSyncResult | null>(null);
  const [atsTouched, setAtsTouched] = useState(false);
  const atsErrors = {
    externalId: !ats.externalId.trim() ? 'Укажите идентификатор вакансии в ATS' : null,
    title: !ats.title.trim() ? 'Укажите название должности' : null,
    salary: !(Number(ats.salaryMin) > 0 && Number(ats.salaryMax) >= Number(ats.salaryMin)) ? 'Укажите вилку в рублях: «до» не меньше «от»' : null,
  };
  const atsSync = useMutation({
    mutationFn: () =>
      api.atsSyncVacancy({
        ats_system: ats.system,
        external_vacancy_id: ats.externalId.trim(),
        title: ats.title.trim(),
        specialization: ats.specialization,
        target_grade: ats.grade,
        salary_min: Number(ats.salaryMin),
        salary_max: Number(ats.salaryMax),
        salary_type: ats.salaryType,
        required_skills: ats.skills,
        description: ats.description.trim() || null,
      }),
    onSuccess: (r) => {
      setAtsResult(r);
      notifications.show({ title: 'Вакансия синхронизирована', message: r.message, color: 'teal', icon: <IconCheck size={18} /> });
    },
    onError: (e) => notifications.show({ title: 'Не удалось синхронизировать', message: toApiError(e).message, color: 'red' }),
  });

  // Практические регулярные задания компании (ТЗ 2.1 & Q&A Row 2)
  const [challengeOpen, setChallengeOpen] = useState(false);
  const [challengeForm, setChallengeForm] = useState({
    title: '',
    task_description: '',
    specialization: 'BACKEND',
    target_grade: 'MIDDLE',
    task_type: 'CODE_REVIEW',
    time_limit_minutes: 30,
  });
  const [challengeTouched, setChallengeTouched] = useState(false);
  // Ответы кандидатов на выбранное задание: работодатель оценивает открытые задания сам (Q&A Row 2)
  const [answersFor, setAnswersFor] = useState<Challenge | null>(null);
  const { data: answers = [], isLoading: answersLoading } = useQuery({
    queryKey: ['challenge-submissions', answersFor?.id],
    queryFn: () => api.challengeSubmissions(answersFor!.id),
    enabled: Boolean(answersFor),
  });

  const { data: employerChallenges = [], refetch: refetchChallenges } = useQuery({
    queryKey: ['employer-challenges'],
    queryFn: () => api.employerChallenges(),
  });

  const createChallenge = useMutation({
    mutationFn: () => api.createEmployerChallenge(challengeForm),
    onSuccess: () => {
      notifications.show({
        title: 'Задание опубликовано',
        message: 'Задание появилось в кабинетах кандидатов: сначала его видят кандидаты этой специализации.',
        color: 'teal',
        icon: <IconCheck size={18} />,
      });
      setChallengeForm({
        title: '',
        task_description: '',
        specialization: 'BACKEND',
        target_grade: 'MIDDLE',
        task_type: 'CODE_REVIEW',
        time_limit_minutes: 30,
      });
      setChallengeOpen(false);
      setChallengeTouched(false);
      refetchChallenges();
    },
    onError: (e) => notifications.show({ title: 'Не удалось создать задание', message: toApiError(e).message, color: 'red' }),
  });

  useEffect(() => {
    if (company && !form) setForm({ name: company.name, inn: company.inn ?? '', website: company.website ?? '', description: company.description ?? '' });
  }, [company, form]);

  const save = useMutation({
    mutationFn: (f: FormState) =>
      api.updateCompany({ name: f.name.trim(), inn: f.inn.trim() || null, website: f.website.trim() || null, description: f.description.trim() || null }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: keys.company });
      notifications.show({ title: 'Профиль компании сохранён', message: 'Данные обновлены.', color: 'teal', icon: <IconCheck size={18} /> });
    },
    onError: (e) => notifications.show({ title: 'Не удалось сохранить', message: toApiError(e).message, color: 'red' }),
  });

  const verify = useMutation({
    mutationFn: () => api.verifyInn(company!.id, form!.inn.trim()),
    onSuccess: (r) => {
      setVerifyResult(r);
      queryClient.invalidateQueries({ queryKey: keys.company });
    },
    onError: (e) => notifications.show({ title: 'Проверка не выполнена', message: toApiError(e).message, color: 'red' }),
  });

  if (isError) {
    return (
      <Container size="lg" p={0}>
        <QueryError error={error} onRetry={() => refetch()} title="Не удалось загрузить профиль компании" />
      </Container>
    );
  }

  if (isLoading || !form || !company) {
    return (
      <Container size="lg" p={0}>
        <Skeleton h={320} />
      </Container>
    );
  }

  const set = <K extends keyof FormState>(key: K, value: FormState[K]) => setForm({ ...form, [key]: value });
  const innFilled = form.inn.trim().length > 0;
  const innValid = isValidInn(form.inn.trim());
  const errors = {
    name: !form.name.trim() ? 'Укажите название организации' : null,
    inn: innFilled && !innValid ? 'ИНН не прошёл проверку контрольной суммы (10 цифр для организации, 12 — для ИП)' : null,
  };
  const accepted = invitations.filter((i) => i.status === 'ACCEPTED').length;
  const answered = invitations.filter((i) => i.status === 'ACCEPTED' || i.status === 'DECLINED').length;

  return (
    <Container size="lg" p={0}>
      <Stack gap="lg">
        <PageHeader
          eyebrow="Кабинет работодателя"
          title="Профиль компании"
          description="Эти сведения видят кандидаты в ваших приглашениях. Проверка ИНН помогает кандидатам доверять предложениям и защищает платформу от фиктивных вакансий."
        />

        <SimpleGrid cols={{ base: 1, sm: 3 }} spacing="md">
          <Paper withBorder p="md">
            <Text size="xs" c="dimmed">
              Приглашений отправлено
            </Text>
            <Text fw={700} size="xl">
              {invitations.length}
            </Text>
          </Paper>
          <Paper withBorder p="md">
            <Text size="xs" c="dimmed">
              Приняли предложение
            </Text>
            <Text fw={700} size="xl">
              {answered > 0 ? `${Math.round((accepted / answered) * 100)}%` : '—'}
            </Text>
            <Text size="xs" c="dimmed">
              {answered > 0 ? `${accepted} из ${answered} ответов` : 'Ответов пока нет'}
            </Text>
          </Paper>
          <Paper withBorder p="md">
            <Text size="xs" c="dimmed">
              Верификация организации
            </Text>
            <Badge mt={6} size="lg" variant="light" color={company.is_verified ? 'teal' : 'orange'} leftSection={company.is_verified ? <IconShieldCheck size={14} /> : <IconShieldX size={14} />}>
              {company.is_verified ? 'Пройдена' : 'Не пройдена'}
            </Badge>
          </Paper>
        </SimpleGrid>

        <Paper withBorder p="lg">
          <form
            noValidate
            onSubmit={(e) => {
              e.preventDefault();
              setTouched(true);
              if (!errors.name && !errors.inn) save.mutate(form);
            }}
          >
            <Stack gap="md">
              <Title order={2} size="h4">Об организации</Title>
              <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="md">
                <TextInput label="Название" required value={form.name} onChange={(e) => set('name', e.currentTarget.value)} error={touched ? errors.name : null} autoComplete="organization" />
                <TextInput
                  label="ИНН"
                  inputMode="numeric"
                  maxLength={12}
                  value={form.inn}
                  onChange={(e) => set('inn', e.currentTarget.value.replace(/\D/g, ''))}
                  error={touched || form.inn.length >= 10 ? errors.inn : null}
                  rightSection={innValid ? <IconCheck size={16} color="var(--mantine-color-teal-6)" aria-label="Контрольная сумма верна" /> : undefined}
                />
                <TextInput label="Сайт" placeholder="https://example.com" value={form.website} onChange={(e) => set('website', e.currentTarget.value)} />
              </SimpleGrid>
              <Textarea label="Описание" description="Направление деятельности, чем занимается организация и команда, контакты для связи" value={form.description} onChange={(e) => set('description', e.currentTarget.value)} minRows={3} autosize />

              <Group justify="space-between" gap="sm">
                <Button
                  variant="default"
                  leftSection={<IconShieldCheck size={16} />}
                  disabled={!innValid}
                  loading={verify.isPending}
                  onClick={() => verify.mutate()}
                >
                  Проверить организацию по ИНН
                </Button>
                <Button type="submit" loading={save.isPending}>
                  Сохранить
                </Button>
              </Group>

              {verifyResult && (
                <Alert
                  variant="light"
                  color={verifyResult.success ? 'teal' : 'orange'}
                  icon={verifyResult.success ? <IconShieldCheck size={18} /> : <IconInfoCircle size={18} />}
                  title={verifyResult.success ? 'Организация проверена' : 'Проверка не пройдена'}
                >
                  <Text size="sm">{verifyResult.message}</Text>
                  <Box mt={6}>
                    <Text size="xs" c="dimmed">
                      Статус: {verifyResult.organization_status} · уровень доверия: {verifyResult.verification_tier} · индекс доверия: {verifyResult.trust_score}
                    </Text>
                    {(verifyResult.is_disqualified || verifyResult.in_unscrupulous_suppliers_registry) && (
                      <Text size="xs" c="red" fw={600}>
                        Организация найдена в реестрах риска.
                      </Text>
                    )}
                  </Box>
                </Alert>
              )}
              <Alert variant="light" color="gray" icon={<IconInfoCircle size={18} />} p="sm">
                Проверяется формат и контрольная сумма ИНН. Запрос статуса организации в ЕГРЮЛ — часть концепции защиты от фиктивных вакансий (см. документацию).
              </Alert>
            </Stack>
          </form>
        </Paper>

        <Paper withBorder p="lg">
          <Group gap="xs" mb={4}>
            <IconPlugConnected size={20} color="var(--fsp-purple)" />
            <Title order={2} size="h4">
              Интеграция с ATS
            </Title>
          </Group>
          <Text size="sm" c="dimmed" mb="md" maw={760}>
            Платформа встраивается в существующий процесс найма: вакансия из внутренней ATS (Huntflow, Potok, E-Staff или собственной системы) передаётся через API и сразу участвует в подборе, без ручного дублирования.
          </Text>
          <form
            noValidate
            onSubmit={(e) => {
              e.preventDefault();
              setAtsTouched(true);
              if (!atsErrors.externalId && !atsErrors.title && !atsErrors.salary) atsSync.mutate();
            }}
          >
            <Stack gap="md">
              <SimpleGrid cols={{ base: 1, sm: 2, lg: 3 }} spacing="md">
                <Select
                  label="Система ATS"
                  data={[
                    { value: 'HUNTFLOW', label: 'Huntflow' },
                    { value: 'POTOK', label: 'Potok' },
                    { value: 'E_STAFF', label: 'E-Staff' },
                    { value: 'CUSTOM', label: 'Другая (собственная)' },
                  ]}
                  value={ats.system}
                  onChange={(v) => v && setAts({ ...ats, system: v })}
                  allowDeselect={false}
                />
                <TextInput label="Идентификатор вакансии в ATS" required value={ats.externalId} onChange={(e) => setAts({ ...ats, externalId: e.currentTarget.value })} error={atsTouched ? atsErrors.externalId : null} />
                <TextInput label="Должность" required value={ats.title} onChange={(e) => setAts({ ...ats, title: e.currentTarget.value })} error={atsTouched ? atsErrors.title : null} />
                <Select
                  label="Специализация"
                  data={(dict?.specializations ?? []).map((s) => ({ value: s.code, label: s.name }))}
                  value={ats.specialization}
                  onChange={(v) => v && setAts({ ...ats, specialization: v })}
                  allowDeselect={false}
                />
                <Select
                  label="Грейд"
                  data={[
                    { value: 'INTERN', label: 'Стажёр' },
                    { value: 'JUNIOR', label: 'Junior' },
                    { value: 'MIDDLE', label: 'Middle' },
                    { value: 'SENIOR', label: 'Senior' },
                  ]}
                  value={ats.grade}
                  onChange={(v) => v && setAts({ ...ats, grade: v })}
                  allowDeselect={false}
                />
                <Select
                  label="Зарплата указана"
                  data={[
                    { value: 'NET', label: 'На руки' },
                    { value: 'GROSS', label: 'До вычета НДФЛ' },
                  ]}
                  value={ats.salaryType}
                  onChange={(v) => v && setAts({ ...ats, salaryType: v })}
                  allowDeselect={false}
                />
                <NumberInput label="Зарплата от, ₽" required thousandSeparator=" " suffix=" ₽" min={0} step={10000} value={ats.salaryMin} onChange={(v) => setAts({ ...ats, salaryMin: v })} error={atsTouched ? atsErrors.salary : null} />
                <NumberInput label="Зарплата до, ₽" required thousandSeparator=" " suffix=" ₽" min={0} step={10000} value={ats.salaryMax} onChange={(v) => setAts({ ...ats, salaryMax: v })} />
              </SimpleGrid>
              <TagsInput label="Обязательные навыки" placeholder="Python, FastAPI…" value={ats.skills} onChange={(v) => setAts({ ...ats, skills: v })} />
              <Textarea label="Описание вакансии" value={ats.description} onChange={(e) => setAts({ ...ats, description: e.currentTarget.value })} minRows={2} autosize />
              <Group justify="flex-end">
                <Button type="submit" loading={atsSync.isPending} leftSection={<IconPlugConnected size={16} />}>
                  Синхронизировать вакансию
                </Button>
              </Group>
              {atsResult && (
                <Alert variant="light" color={atsResult.success ? 'teal' : 'orange'} icon={<IconCheck size={18} />} title={`Статус: ${atsResult.sync_status}`}>
                  <Text size="sm">{atsResult.message}</Text>
                  <Text size="xs" c="dimmed" mt={4}>
                    Идентификатор в платформе: {atsResult.need_id} · в ATS ({atsResult.ats_system}): {atsResult.external_vacancy_id}.
                  </Text>
                </Alert>
              )}
            </Stack>
          </form>
        </Paper>

        <Paper withBorder p="lg">
          <Group justify="space-between" mb="xs">
            <Group gap="xs">
              <IconCode size={20} color="var(--fsp-purple)" />
              <Title order={2} size="h4">
                Регулярные задания для кандидатов
              </Title>
            </Group>
            <Button
              size="xs"
              variant={challengeOpen ? 'default' : 'filled'}
              leftSection={challengeOpen ? undefined : <IconPlus size={14} />}
              onClick={() => setChallengeOpen((v) => !v)}
            >
              {challengeOpen ? 'Скрыть форму' : 'Создать задание'}
            </Button>
          </Group>
          <Text size="sm" c="dimmed" mb="md" maw={760}>
            Короткие практические микро-задачи от вашей компании (п. 2.1 ТЗ и Q&A Row 2). Система предлагает их подходящим кандидатам, что поддерживает их профиль в актуальном состоянии и даёт вам свежий сигнал об их навыках.
          </Text>

          {challengeOpen && (
            <Box mb="lg" p="md" style={{ background: 'var(--fsp-tint-neutral)', borderRadius: 8 }}>
              <Title order={3} size="h5" mb="sm">
                Новое практическое задание
              </Title>
              <Stack gap="sm">
                <TextInput
                  label="Название задания"
                  placeholder="Например: Оптимизация составного B-Tree индекса"
                  required
                  value={challengeForm.title}
                  onChange={(e) => setChallengeForm({ ...challengeForm, title: e.currentTarget.value })}
                  error={challengeTouched && !challengeForm.title.trim() ? 'Укажите название' : null}
                />
                <Textarea
                  label="Формулировка задачи или архитектурного кейса"
                  placeholder="Опишите контекст проблемы, код или вопрос, на который кандидат должен предложить подход к решению..."
                  required
                  minRows={3}
                  autosize
                  value={challengeForm.task_description}
                  onChange={(e) => setChallengeForm({ ...challengeForm, task_description: e.currentTarget.value })}
                  error={challengeTouched && !challengeForm.task_description.trim() ? 'Опишите задачу' : null}
                />
                <SimpleGrid cols={{ base: 1, sm: 3 }} spacing="sm">
                  <Select
                    label="Специализация"
                    data={(dict?.specializations ?? []).map((s) => ({ value: s.code, label: s.name }))}
                    value={challengeForm.specialization}
                    onChange={(v) => v && setChallengeForm({ ...challengeForm, specialization: v })}
                    allowDeselect={false}
                  />
                  <Select
                    label="Целевой грейд"
                    data={[
                      { value: 'INTERN', label: 'Стажёр' },
                      { value: 'JUNIOR', label: 'Junior' },
                      { value: 'MIDDLE', label: 'Middle' },
                      { value: 'SENIOR', label: 'Senior' },
                    ]}
                    value={challengeForm.target_grade}
                    onChange={(v) => v && setChallengeForm({ ...challengeForm, target_grade: v })}
                    allowDeselect={false}
                  />
                  <Select
                    label="Тип задания"
                    data={[
                      { value: 'CODE_REVIEW', label: 'Code Review' },
                      { value: 'ARCHITECTURE', label: 'Архитектурный кейс' },
                      { value: 'ALGORITHM', label: 'Алгоритмическая задача' },
                      { value: 'OPEN_ENDED', label: 'Открытый подход' },
                    ]}
                    value={challengeForm.task_type}
                    onChange={(v) => v && setChallengeForm({ ...challengeForm, task_type: v })}
                    allowDeselect={false}
                  />
                </SimpleGrid>
                <Group justify="flex-end" mt="xs">
                  <Button
                    loading={createChallenge.isPending}
                    onClick={() => {
                      setChallengeTouched(true);
                      if (challengeForm.title.trim() && challengeForm.task_description.trim()) {
                        createChallenge.mutate();
                      }
                    }}
                  >
                    Опубликовать задание
                  </Button>
                </Group>
              </Stack>
            </Box>
          )}

          {employerChallenges.length === 0 ? (
            <Alert variant="light" color="gray" icon={<IconInfoCircle size={18} />}>
              У вашей компании пока нет опубликованных регулярных заданий. Нажмите «Создать задание», чтобы направить задачу кандидатам.
            </Alert>
          ) : (
            <SimpleGrid cols={{ base: 1, md: 2 }} spacing="md">
              {employerChallenges.map((ch) => (
                <Card key={ch.id} padding="md" withBorder>
                  <Group justify="space-between" mb="xs" wrap="wrap" gap="xs">
                    <Badge variant="light" color="fspPurple" size="sm">
                      {specLabel(ch.specialization)} · {gradeLabel(ch.target_grade)}
                    </Badge>
                    <Badge variant="outline" color="gray" size="xs">
                      {ch.task_type} · {ch.time_limit_minutes} мин
                    </Badge>
                  </Group>
                  <Text fw={600} size="sm" mb={4}>
                    {ch.title}
                  </Text>
                  <Text size="xs" c="dimmed" lineClamp={3}>
                    {ch.task_description}
                  </Text>
                  <Group justify="space-between" mt="md" wrap="wrap" gap="xs">
                    <Badge size="xs" color="teal" variant="dot">
                      Активно · {new Date(ch.created_at).toLocaleDateString('ru-RU')}
                    </Badge>
                    <Button size="compact-xs" variant="light" disabled={!ch.submissions_count} onClick={() => setAnswersFor(ch)}>
                      Ответы: {ch.submissions_count ?? 0}
                    </Button>
                  </Group>
                </Card>
              ))}
            </SimpleGrid>
          )}
        </Paper>
      </Stack>

      <AppModal opened={!!answersFor} onClose={() => setAnswersFor(null)} title={`Ответы: ${answersFor?.title ?? ''}`} size="lg">
        {answersLoading ? (
          <Skeleton h={120} />
        ) : (
          <Stack gap="sm">
            {answers.map((a) => (
              <Card key={a.id} withBorder padding="sm">
                <Group justify="space-between" mb={4}>
                  <Text fw={600} size="sm">
                    {a.candidate_name}
                  </Text>
                  <Text size="xs" c="dimmed">
                    {formatDate(a.submitted_at)}
                  </Text>
                </Group>
                <Badge size="xs" variant="light" color={a.is_grade_confirmed ? 'fspPink' : 'gray'} mb={6}>
                  {a.confirmed_category ?? 'Грейд не подтверждён'}
                </Badge>
                <Text size="sm" style={{ whiteSpace: 'pre-line' }}>
                  {a.answer_text}
                </Text>
              </Card>
            ))}
            <Text size="xs" c="dimmed">
              Контакты кандидата откроются, когда он примет ваше приглашение: пригласить можно из подборки или банка кандидатов.
            </Text>
          </Stack>
        )}
      </AppModal>
    </Container>
  );
};
