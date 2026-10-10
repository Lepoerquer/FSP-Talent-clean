import React, { useState } from 'react';
import {
  Alert,
  Avatar,
  Badge,
  Box,
  Button,
  Container,
  Divider,
  Group,
  Paper,
  Select,
  SimpleGrid,
  Skeleton,
  Stack,
  Text,
  ThemeIcon,
  Timeline,
  Title,
} from '@mantine/core';
import {
  IconAward,
  IconCheck,
  IconClock,
  IconCompass,
  IconDownload,
  IconInfoCircle,
  IconPlus,
  IconQrcode,
  IconRefresh,
  IconRoute,
  IconSparkles,
  IconTarget,
  IconTrophy,
  IconChartDots,
} from '@tabler/icons-react';
import { notifications } from '@mantine/notifications';
import { useMutation, useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { api, CandidateSpecialization, AICareerAdviceResult } from '../api/api';
import { CompetenceRadarChart, RadarDimension } from '../components/common/CompetenceRadarChart';
import { FspStarIcon } from '../components/common/FspStarIcon';
import { PlatformChatModal } from '../components/PlatformChatModal';
import { toApiError } from '../api/http';
import { fullName, useDictionaries, useGradeStatus, useProfile } from '../hooks/queries';
import { useExtras } from '../hooks/useExtras';
import { PageHeader } from '../components/common/PageHeader';
import { QueryError } from '../components/common/QueryError';
import { usePageTitle } from '../hooks/usePageTitle';
import { SalaryRange } from '../components/common/SalaryRange';
import { InvitationsPanel } from '../components/candidate/InvitationsPanel';
import { ChallengesPanel } from '../components/candidate/ChallengesPanel';
import { AssessmentHistory } from '../components/candidate/AssessmentHistory';
import { daysUntil, formatCount, formatDate, formatDecimal, formatTheta, initials } from '../utils/format';
import { fspLevelLabel, fspResultLabel, gradeLabel, specCode, specLabel, TOPIC_LEVEL_LABELS, workFormatLabel } from '../utils/labels';

const SKILL_SOURCE: Record<string, { label: string; color: string }> = {
  ASSESSMENT: { label: 'подтверждён тестом', color: 'teal' },
  FSP: { label: 'подтверждён ФСП', color: 'fspPurple' },
  RESUME: { label: 'из резюме', color: 'blue' },
  CLAIMED: { label: 'заявлен', color: 'gray' },
};

interface CandidateCabinetPageProps {
  view: 'dashboard' | 'invitations';
}

export const CandidateCabinetPage: React.FC<CandidateCabinetPageProps> = ({ view }) => {
  usePageTitle(view === 'invitations' ? 'Приглашения' : 'Профиль и обзор');
  const { data: profile, isLoading, isError, error, refetch } = useProfile();
  const { data: grade } = useGradeStatus();
  const { data: dict } = useDictionaries();
  const [extras] = useExtras();

  const pdf = useMutation({
    mutationFn: api.profilePdf,
    onSuccess: (blob) => {
      const url = URL.createObjectURL(blob);
      window.open(url, '_blank', 'noopener');
      window.setTimeout(() => URL.revokeObjectURL(url), 60000);
    },
    onError: (e) => notifications.show({ title: 'PDF-профиль недоступен', message: toApiError(e).message, color: 'red' }),
  });

  // Дополнительные специализации кандидата (Q&A Row 6)
  const [newSpec, setNewSpec] = useState('FRONTEND');
  const [newGrade, setNewGrade] = useState('MIDDLE');
  const [showAddSpec, setShowAddSpec] = useState(false);
  const [advice, setAdvice] = useState<AICareerAdviceResult | null>(null);
  const [adviceLoading, setAdviceLoading] = useState(false);

  const { data: extraSpecs = [], refetch: refetchSpecs } = useQuery<CandidateSpecialization[]>({
    queryKey: ['candidate-specializations'],
    queryFn: () => api.getSpecializations(),
  });

  const addSpec = useMutation({
    mutationFn: () => api.addSpecialization({ specialization: newSpec, grade: newGrade }),
    onSuccess: () => {
      notifications.show({
        title: 'Специализация добавлена',
        message: 'Она видна в профиле как заявленная. Категорию и грейд присваивает только тест.',
        color: 'teal',
        icon: <IconCheck size={18} />,
      });
      setShowAddSpec(false);
      refetchSpecs();
    },
    onError: (e) => notifications.show({ title: 'Ошибка добавления', message: toApiError(e).message, color: 'red' }),
  });

  if (view === 'invitations') {
    return (
      <Container size="xl" p={0}>
        <Stack gap="lg">
          <PageHeader eyebrow="Кабинет кандидата" title="Приглашения" description="Предложения работодателей, выбравших вас по подтверждённой категории." />
          <InvitationsPanel />
        </Stack>
      </Container>
    );
  }

  if (isError) {
    return (
      <Container size="xl" p={0}>
        <QueryError error={error} onRetry={() => refetch()} title="Не удалось загрузить профиль" />
      </Container>
    );
  }
  if (isLoading || !profile) {
    return (
      <Container size="xl" p={0}>
        <Skeleton h={360} />
      </Container>
    );
  }

  const confirmed = profile.is_grade_confirmed;
  const days = daysUntil(grade?.next_grade_change_available_at);
  const attempt = grade?.regular_attempt;
  const lastAttempt = grade?.attempts?.[0];
  const specRecord = dict?.specializations.find((s) => specCode(s.code) === specCode(profile.confirmed_specialization));
  const direction = specRecord?.direction_name;
  const topics = grade?.topic_profile ?? [];

  const handleFetchAdvice = async () => {
    setAdviceLoading(true);
    try {
      const res = await api.aiCareerAdvice({
        specialization: profile.confirmed_specialization ?? undefined,
        grade: profile.confirmed_grade ?? undefined,
        skills: profile.skills.map((s) => s.name),
        experience_years: profile.experience_years ?? undefined,
        fsp_verified: profile.is_fsp_verified,
        percentile: profile.category_percentile ?? undefined,
      });
      setAdvice(res);
      notifications.show({
        title: 'AI-план сформирован',
        message: 'Рекомендации GigaChat подготовлены на основе вашего профиля ФСП.',
        color: 'teal',
        icon: <IconCheck size={18} />,
      });
    } catch (e) {
      notifications.show({
        title: 'Ошибка AI-консультанта',
        message: toApiError(e).message,
        color: 'red',
      });
    } finally {
      setAdviceLoading(false);
    }
  };

  const radarDimensions: RadarDimension[] = [
    {
      key: 'test',
      label: 'Тест ФСП (Hard skills)',
      value: profile.category_percentile != null
        ? profile.category_percentile
        : (profile.last_theta != null
          ? Math.min(100, Math.max(25, Math.round(((profile.last_theta + 3) / 6) * 100)))
          : (profile.confirmed_grade === 'SENIOR' ? 85 : profile.confirmed_grade === 'MIDDLE' ? 65 : 45)),
      targetValue: profile.confirmed_grade === 'SENIOR' ? 90 : profile.confirmed_grade === 'MIDDLE' ? 80 : 65,
      hint: profile.category_percentile != null
        ? `${profile.category_percentile}-й процентиль`
        : (profile.last_theta != null ? `Theta: ${formatTheta(profile.last_theta)}` : 'По результатам IRT-теста'),
    },
    {
      key: 'stack',
      label: 'Стек технологий',
      value: Math.min(100, Math.max(30, 40 + (profile.skills?.length ?? 0) * 8)),
      targetValue: 80,
      hint: `Подтверждённых навыков: ${profile.skills?.length ?? 0}`,
    },
    {
      key: 'exp',
      label: 'Опыт и грейд',
      value: profile.confirmed_grade === 'SENIOR' ? 90 : profile.confirmed_grade === 'MIDDLE' ? 70 : 50,
      targetValue: profile.confirmed_grade === 'SENIOR' ? 95 : profile.confirmed_grade === 'MIDDLE' ? 80 : 65,
      hint: `Грейд: ${gradeLabel(profile.confirmed_grade)}`,
    },
    {
      key: 'fsp',
      label: 'Олимпиадный опыт ФСП',
      value: profile.is_fsp_verified
        ? Math.min(100, Math.max(35, Math.round(
            (profile.fsp_score ?? 0) > 0
              ? (profile.fsp_score ?? 0) * 100
              : 35 + (profile.fsp_achievements?.length ?? 0) * 20
          )))
        : 20,
      targetValue: 60,
      hint: profile.is_fsp_verified
        ? `Балл ФСП: ${profile.fsp_score ?? 0}, турниров: ${profile.fsp_achievements?.length ?? 0}`
        : 'Участие в соревнованиях ФСП не привязано',
    },
    {
      key: 'verified',
      label: 'Подтверждённость 152-ФЗ',
      value: confirmed ? 95 : 40,
      targetValue: 85,
      hint: confirmed ? 'Категория подтверждена (152-ФЗ)' : 'Самозаявлен',
    },
  ];

  return (
    <Container size="xl" p={0}>
      <Stack gap="lg">
        <PageHeader
          eyebrow="Кабинет кандидата"
          title="Профиль и обзор"
          description="Ваша категория, результат квалификационного теста, достижения ФСП и входящие предложения."
          actions={
            <Group gap="xs" wrap="wrap">
              <Button
                component={Link}
                to={`/verify/candidates/${profile.id}`}
                variant="light"
                color="teal"
                leftSection={<IconQrcode size={16} />}
              >
                QR-сертификат
              </Button>
              <Button variant="default" leftSection={<IconDownload size={16} />} loading={pdf.isPending} onClick={() => pdf.mutate()}>
                Скачать PDF-профиль
              </Button>
            </Group>
          }
        />

        <Paper withBorder p={{ base: 'md', sm: 'lg' }} style={{ overflow: 'hidden' }}>
          <SimpleGrid cols={{ base: 1, md: 3 }} spacing="lg">
            <Group align="flex-start" gap="md" wrap="wrap">
              <Avatar size={64} radius="xl" color="fspPurple" variant="filled" style={{ flexShrink: 0 }}>
                {initials(fullName(profile))}
              </Avatar>
              <Box style={{ minWidth: 0, flex: 1 }}>
                <Title order={2} size="h3">{fullName(profile)}</Title>
                <Text size="sm" c="dimmed" mb={8}>
                  {[profile.city, workFormatLabel(profile.work_format)].filter((v) => v && v !== '—').join(' · ')}
                </Text>
                {confirmed ? (
                  <Stack gap={4} align="flex-start">
                    <Group gap="xs" wrap="wrap">
                      <Badge size="lg" color="fspPink" variant="light">
                        {profile.confirmed_category}
                      </Badge>
                      {profile.is_fsp_verified && (
                        <Badge size="lg" color="fspBlue" variant="light" leftSection={<FspStarIcon size={14} />}>
                          ФСП ID {profile.fsp_id}
                        </Badge>
                      )}
                    </Group>
                    {direction && (
                      <Text size="xs" c="dimmed">
                        Отрасль: {direction} · специализация: {specLabel(profile.confirmed_specialization)} · грейд: {gradeLabel(profile.confirmed_grade)}
                      </Text>
                    )}
                  </Stack>
                ) : profile.declared_grade ? (
                  <Badge size="lg" color="orange" variant="light">
                    Заявлен {gradeLabel(profile.declared_grade)} · не подтверждён
                  </Badge>
                ) : (
                  <Badge size="lg" color="gray" variant="light">
                    Категория не присвоена
                  </Badge>
                )}
              </Box>
            </Group>

            <Box>
              <Text className="section-eyebrow" mb={6}>
                Квалификационный тест
              </Text>
              {confirmed ? (
                <>
                  <Group gap="sm" align="baseline">
                    <Text fw={700} size="xl">
                      {formatTheta(profile.last_theta ?? 0)}
                    </Text>
                    {profile.category_percentile != null && (
                      <Badge variant="light" color="fspPurple">
                        {profile.category_percentile}-й процентиль
                      </Badge>
                    )}
                  </Group>
                  <Text size="sm" c="dimmed">
                    Погрешность оценки ±{formatDecimal(profile.last_se ?? 0)}. Результат относительно участников той же категории.
                  </Text>
                </>
              ) : (
                <>
                  <Text fw={700}>Тест не пройден</Text>
                  <Text size="sm" c="dimmed" mb="sm">
                    Без теста профиль виден работодателям со статусом «Не подтверждён», а в подборке стоит ниже.
                  </Text>
                  <Button component={Link} to="/candidate/assessment" size="xs">
                    Пройти тест
                  </Button>
                </>
              )}
            </Box>

            <Box>
              <Group gap={6} mb={6}>
                <IconClock size={15} color="var(--fsp-text-muted)" />
                <Text className="section-eyebrow">Смена грейда</Text>
              </Group>
              {days > 0 ? (
                <>
                  <Text fw={700}>{formatCount(days, ['день', 'дня', 'дней'])} до следующей попытки</Text>
                  <Text size="sm" c="dimmed">
                    {attempt?.message ?? 'Тест на другой грейд можно пройти не чаще одного раза в 90 дней.'}
                  </Text>
                </>
              ) : (
                <>
                  <Text fw={700}>{attempt?.allowed === false ? 'Пока недоступна' : 'Доступна'}</Text>
                  <Text size="sm" c="dimmed">
                    {attempt?.message ?? 'Можно пройти тест на грейд выше или ниже текущего.'}
                  </Text>
                </>
              )}
            </Box>
          </SimpleGrid>

          <Divider my="md" />

          <Group justify="space-between" align="flex-start" gap="md">
            <Group gap="xs">
              <Text size="xs" fw={600} c="dimmed">
                Навыки:
              </Text>
              {profile.skills.length === 0 && (
                <Text size="xs" c="dimmed">
                  появятся после теста
                </Text>
              )}
              {profile.skills.map((s) => {
                const src = SKILL_SOURCE[s.confirmation_source] ?? SKILL_SOURCE.CLAIMED;
                return (
                  <Badge key={s.id} color={src.color} variant={s.confirmation_source === 'CLAIMED' ? 'outline' : 'light'} size="sm" title={src.label}>
                    {s.name}
                  </Badge>
                );
              })}
            </Group>
            {extras.roles.length > 0 && (
              <Group gap="xs" w="100%">
                <Text size="xs" fw={600} c="dimmed">
                  Роли:
                </Text>
                {extras.roles.map((r) => (
                  <Badge key={r} variant="light" color="fspPurple" size="sm">
                    {r}
                  </Badge>
                ))}
              </Group>
            )}
            {extras.soft_skills.length > 0 && (
              <Group gap="xs" w="100%">
                <Text size="xs" fw={600} c="dimmed">
                  Soft skills:
                </Text>
                {extras.soft_skills.map((s) => (
                  <Badge key={s} variant="outline" color="gray" size="sm">
                    {s}
                  </Badge>
                ))}
              </Group>
            )}
            {extras.about && (
              <Box w="100%" mt="xs">
                <Text size="xs" fw={600} c="dimmed" mb={4}>
                  О себе:
                </Text>
                <Text size="sm">{extras.about}</Text>
              </Box>
            )}
            {profile.desired_salary_min ? (
              <Box ta="right">
                <Text size="xs" c="dimmed">
                  Ожидания по зарплате
                </Text>
                <SalaryRange from={profile.desired_salary_min} prefix="от " type={profile.salary_type} />
              </Box>
            ) : (
              <Text size="xs" c="dimmed">
                Ожидания по зарплате не указаны —{' '}
                <Text component={Link} to="/candidate/onboarding" span c="fspPink" fw={600} td="underline" inherit>
                  заполнить
                </Text>
              </Text>
            )}
          </Group>
        </Paper>

        <Paper withBorder p="lg">
          <Group justify="space-between" mb="xs">
            <Group gap="xs">
              <IconAward size={20} color="var(--fsp-pink)" />
              <Title order={3} size="h4">
                Категории и специализации кандидата
              </Title>
            </Group>
            <Button
              size="xs"
              variant={showAddSpec ? 'default' : 'subtle'}
              leftSection={showAddSpec ? undefined : <IconPlus size={14} />}
              onClick={() => setShowAddSpec((v) => !v)}
            >
              {showAddSpec ? 'Отмена' : 'Добавить специализацию'}
            </Button>
          </Group>
          <Text size="sm" c="dimmed" mb="md">
            Основная категория присвоена тестом и участвует в подборе. Дополнительные специализации заявлены вами без теста: работодатель видит их в профиле с этой пометкой.
          </Text>

          {showAddSpec && (
            <Box mb="md" p="md" style={{ background: 'var(--fsp-tint-neutral)', borderRadius: 8 }}>
              <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="sm" mb="sm">
                <Select
                  label="Дополнительная специализация"
                  data={(dict?.specializations ?? []).map((s) => ({ value: s.code, label: s.name }))}
                  value={newSpec}
                  onChange={(v) => v && setNewSpec(v)}
                  allowDeselect={false}
                />
                <Select
                  label="Заявленный грейд"
                  data={[
                    { value: 'INTERN', label: 'Стажёр' },
                    { value: 'JUNIOR', label: 'Junior' },
                    { value: 'MIDDLE', label: 'Middle' },
                    { value: 'SENIOR', label: 'Senior' },
                  ]}
                  value={newGrade}
                  onChange={(v) => v && setNewGrade(v)}
                  allowDeselect={false}
                />
              </SimpleGrid>
              <Group justify="flex-end">
                <Button size="xs" loading={addSpec.isPending} onClick={() => addSpec.mutate()}>
                  Добавить как заявленную
                </Button>
              </Group>
            </Box>
          )}

          <Group gap="xs">
            <Badge size="lg" color="fspPink" variant="filled">
              {profile.confirmed_category ? `${profile.confirmed_category} · подтверждена тестом` : 'Категория не присвоена: пройдите тест'}
            </Badge>
            {extraSpecs.map((s: CandidateSpecialization) => (
              <Badge key={s.id} size="lg" color="fspPurple" variant="light">
                {specLabel(s.specialization)} · {gradeLabel(s.grade)} · заявлена, не подтверждена
              </Badge>
            ))}
          </Group>
        </Paper>

        {/* Интерактивный радар компетенций и AI-Карьерный консультант ФСП */}
        <SimpleGrid cols={{ base: 1, md: 2 }} spacing="lg">
          <Paper withBorder p={{ base: 'md', sm: 'lg' }} style={{ overflow: 'hidden' }}>
            <Group justify="space-between" mb="xs" wrap="wrap" gap="xs">
              <Group gap="xs">
                <ThemeIcon size={24} radius="md" variant="light" color="fspPurple">
                  <IconChartDots size={16} />
                </ThemeIcon>
                <Title order={3} size="h4">Радар компетенций ФСП</Title>
              </Group>
              <Badge variant="light" color="fspPurple">Интерактивный</Badge>
            </Group>
            <Text size="xs" c="dimmed" mb="md">
              Сравнение вашего текущего профиля по 5 ключевым осям с целевым эталоном следующего грейда.
            </Text>
            <Box style={{ display: 'flex', justifyContent: 'center' }}>
              <CompetenceRadarChart
                dimensions={radarDimensions}
                size={320}
                candidateLabel="Текущий уровень"
                targetLabel="Целевой эталон"
              />
            </Box>
          </Paper>

          <Paper withBorder p={{ base: 'md', sm: 'lg' }} style={{ background: 'linear-gradient(135deg, var(--fsp-tint-accent) 0%, var(--fsp-tint-violet) 100%)', overflow: 'hidden' }}>
            <Group justify="space-between" mb="xs" align="flex-start" wrap="wrap" gap="xs">
              <Group gap="xs" wrap="nowrap" align="flex-start" style={{ minWidth: 0, flex: 1 }}>
                <ThemeIcon size={28} radius="md" variant="gradient" gradient={{ from: 'fspBlue', to: 'fspNavy' }} style={{ flexShrink: 0, marginTop: 2 }}>
                  <IconCompass size={18} />
                </ThemeIcon>
                <Box style={{ minWidth: 0, flex: 1 }}>
                  <Title order={3} size="h4">AI-Карьерный консультант ФСП</Title>
                  <Text size="xs" c="dimmed">Персональный карьерный трек на базе GigaChat и регламентов ФСП</Text>
                </Box>
              </Group>
              <Badge variant="filled" color="fspBlue" size="sm" style={{ flexShrink: 0 }}>GigaChat 152-ФЗ</Badge>
            </Group>

            {!advice && !adviceLoading && (
              <Box mt="md" p="md" style={{ background: 'var(--fsp-card-bg)', borderRadius: 8, border: '1px dashed var(--fsp-border)' }}>
                <Text size="sm" mb="xs">
                  Нейросеть проанализирует ваши баллы IRT-теста, участие в турнирах Федерации спортивного программирования и стек технологий, чтобы составить пошаговый план роста.
                </Text>
                <Button
                  variant="gradient"
                  gradient={{ from: 'fspBlue', to: 'fspNavy' }}
                  leftSection={<IconSparkles size={16} />}
                  onClick={handleFetchAdvice}
                >
                  Сформировать карьерный план AI
                </Button>
              </Box>
            )}

            {adviceLoading && (
              <Box mt="md" p="xl" ta="center">
                <Skeleton height={20} radius="xl" mb="sm" />
                <Skeleton height={14} radius="xl" width="85%" mb="xs" />
                <Skeleton height={14} radius="xl" width="65%" mb="md" />
                <Text size="xs" c="dimmed" fs="italic">
                  GigaChat анализирует ваш профиль, регламенты ФСП и формирует персональный план...
                </Text>
              </Box>
            )}

            {advice && !adviceLoading && (
              <Stack gap="md" mt="md">
                <Box p="sm" style={{ background: 'var(--fsp-card-bg)', borderRadius: 8, border: '1px solid var(--fsp-border)' }}>
                  <Text size="xs" fw={700} c="var(--fsp-primary)" mb={4}>ОБЩИЙ АНАЛИЗ ГОТОВНОСТИ:</Text>
                  <Text size="sm">{advice.overall_summary}</Text>
                </Box>

                {advice.recommended_fsp_discipline && (
                  <Box p="xs" style={{ background: 'var(--fsp-tint-accent)', borderRadius: 6, border: '1px solid var(--fsp-border)' }}>
                    <Group gap="xs" mb={4}>
                      <Badge color="fspBlue" variant="filled" size="sm" leftSection={<IconTrophy size={12} />}>
                        {advice.recommended_fsp_discipline}
                      </Badge>
                      <Text size="xs" fw={700} c="var(--fsp-primary)">РЕКОМЕНДОВАННАЯ ДИСЦИПЛИНА ФСП</Text>
                    </Group>
                    {advice.fsp_boost_tip && (
                      <Text size="xs" c="dimmed">
                        💡 {advice.fsp_boost_tip}
                      </Text>
                    )}
                  </Box>
                )}

                <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="sm">
                  <Box p="xs" style={{ background: 'var(--fsp-tint-success)', borderRadius: 6, border: '1px solid var(--fsp-border)' }}>
                    <Group gap={6} mb={4}>
                      <IconCheck size={14} color="#20c997" />
                      <Text size="xs" fw={700} c="teal">СИЛЬНЫЕ СТОРОНЫ</Text>
                    </Group>
                    <Stack gap={4}>
                      {advice.strengths.map((s, i) => (
                        <Text key={i} size="xs">• {s}</Text>
                      ))}
                    </Stack>
                  </Box>

                  <Box p="xs" style={{ background: 'var(--fsp-tint-warn)', borderRadius: 6, border: '1px solid var(--fsp-border)' }}>
                    <Group gap={6} mb={4}>
                      <IconTarget size={14} color="#fd7e14" />
                      <Text size="xs" fw={700} c="orange">ТОЧКИ РОСТА</Text>
                    </Group>
                    <Stack gap={4}>
                      {advice.growth_points.map((g, i) => (
                        <Text key={i} size="xs">• {g}</Text>
                      ))}
                    </Stack>
                  </Box>
                </SimpleGrid>

                {Boolean(advice.career_roadmap && advice.career_roadmap.length > 0) && (
                  <Box p="sm" style={{ background: 'var(--fsp-card-bg)', borderRadius: 8, border: '1px solid var(--fsp-border)' }}>
                    <Group gap={6} mb="xs">
                      <IconRoute size={16} color="var(--fsp-primary)" />
                      <Text size="xs" fw={700} c="var(--fsp-primary)">ПОШАГОВЫЙ КАРЬЕРНЫЙ ПЛАН</Text>
                    </Group>
                    <Stack gap="xs">
                      {advice.career_roadmap!.map((step, idx) => (
                        <Group key={idx} align="flex-start" wrap="nowrap" gap="xs">
                          <Badge size="xs" color="fspBlue" variant="filled" circle>{idx + 1}</Badge>
                          <Box>
                            <Text size="xs" fw={600}>{step.step} {step.timeframe ? `(${step.timeframe})` : ''}</Text>
                            <Text size="xs" c="dimmed">{step.action}</Text>
                          </Box>
                        </Group>
                      ))}
                    </Stack>
                  </Box>
                )}

                <Group justify="space-between" align="center">
                  <Text size="xs" c="dimmed">
                    Рекомендации сформированы AI ({advice.provider}) на основе регламентов ФСП и 152-ФЗ.
                  </Text>
                  <Button
                    variant="subtle"
                    size="xs"
                    leftSection={<IconRefresh size={14} />}
                    onClick={handleFetchAdvice}
                    loading={adviceLoading}
                  >
                    Обновить анализ
                  </Button>
                </Group>
              </Stack>
            )}
          </Paper>
        </SimpleGrid>

        {topics.length > 0 && (
          <Paper withBorder p="lg">
            <Title order={3} size="h4" mb={4}>
              Профиль по темам
            </Title>
            <Text size="sm" c="dimmed" mb="md">
              По результату последнего прохождения{lastAttempt ? ` (${formatDate(lastAttempt.started_at)})` : ''}.
            </Text>
            <SimpleGrid cols={{ base: 1, sm: 2, lg: 3 }} spacing="sm">
              {topics.map((t) => {
                const lvl = TOPIC_LEVEL_LABELS[t.level] ?? { label: t.level, color: 'gray' };
                return (
                  <Group key={t.topic} justify="space-between" wrap="wrap" gap="xs" p="xs" style={{ border: '1px solid var(--fsp-border)', borderRadius: 6 }}>
                    <Box style={{ minWidth: 0, flex: 1 }}>
                      <Text size="sm" fw={600}>
                        {t.topic}
                      </Text>
                      <Text size="xs" c="dimmed">
                        верно {t.correct} из {t.items}
                      </Text>
                    </Box>
                    <Badge variant="light" color={lvl.color} size="sm" style={{ flexShrink: 0 }}>
                      {lvl.label}
                    </Badge>
                  </Group>
                );
              })}
            </SimpleGrid>
          </Paper>
        )}

        {profile.is_fsp_verified && profile.fsp_achievements.length > 0 ? (
          <Paper withBorder p="lg">
            <Group justify="space-between" mb="md" align="flex-start">
              <Group gap="sm" wrap="nowrap" align="flex-start">
                <FspStarIcon size={26} style={{ marginTop: 2 }} />
                <Box>
                  <Title order={2} size="h3">Достижения ФСП</Title>
                  <Text size="sm" c="dimmed">
                    ФСП ID {profile.fsp_id} · данные из реестра Федерации спортивного программирования
                  </Text>
                </Box>
              </Group>
              <Badge variant="light" color="fspBlue" size="lg">
                Балл ФСП: {formatDecimal(profile.fsp_score ?? 0)}
              </Badge>
            </Group>
            <Timeline active={profile.fsp_achievements.length} bulletSize={22} lineWidth={2} color="fspPurple">
              {profile.fsp_achievements.map((ach) => (
                <Timeline.Item
                  key={ach.id}
                  bullet={<IconAward size={12} />}
                  title={
                    <Group gap="xs">
                      <Text fw={600} size="sm">
                        {ach.event_name}
                      </Text>
                      <Badge color="fspPink" variant="light" size="sm">
                        {fspResultLabel(ach.result)}
                      </Badge>
                      {ach.sport_category && (
                        <Badge color="gray" variant="outline" size="sm">
                          {ach.sport_category}
                        </Badge>
                      )}
                    </Group>
                  }
                >
                  <Text size="xs" c="dimmed">
                    {ach.discipline} · {fspLevelLabel(ach.level)} уровень{ach.event_date ? ` · ${formatDate(ach.event_date)}` : ''}
                  </Text>
                </Timeline.Item>
              ))}
            </Timeline>
            <Text size="xs" c="dimmed" mt="sm">
              Достижения влияют только на позицию внутри категории и не заменяют результат квалификационного теста.
            </Text>
          </Paper>
        ) : (
          <Alert variant="light" color="gray" icon={<IconInfoCircle size={18} />} title="История ФСП не привязана">
            Это не влияет на подтверждённую категорию и не снижает позицию в подборках: ранжирование опирается на результат теста. Если вы участвовали в соревнованиях ФСП,{' '}
            <Text component={Link} to="/candidate/fsp" span c="fspPink" fw={600} td="underline" inherit>
              привяжите ФСП ID
            </Text>
            .
          </Alert>
        )}

        <InvitationsPanel limit={2} />
        <AssessmentHistory />
        <ChallengesPanel />
      </Stack>
    </Container>
  );
};
