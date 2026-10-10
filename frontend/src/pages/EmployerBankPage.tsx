import React, { useEffect, useMemo, useState } from 'react';
import { Alert, Button, Container, Group, NumberInput, Paper, Select, SimpleGrid, Skeleton, Stack, Switch, TagsInput, Text, TextInput, Title } from '@mantine/core';
import { IconInfoCircle } from '@tabler/icons-react';
import { useQuery } from '@tanstack/react-query';
import { api, CandidateCard } from '../api/api';
import { toApiError } from '../api/http';
import { useDictionaries, useInvitedMap } from '../hooks/queries';
import { PageHeader } from '../components/common/PageHeader';
import { CandidateCard as CandidateCardView } from '../components/employer/CandidateCard';
import { InviteModal } from '../components/employer/InviteModal';
import { formatCount } from '../utils/format';
import { GRADE_LABELS, specCode, WORK_FORMAT_LABELS } from '../utils/labels';

const ALL = 'ALL';

/** Значение поля с задержкой: запрос к серверу уходит после паузы в наборе. */
const useDebounced = <T,>(value: T, ms = 400): T => {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = window.setTimeout(() => setV(value), ms);
    return () => window.clearTimeout(t);
  }, [value, ms]);
  return v;
};

import { usePageTitle } from '../hooks/usePageTitle';

export const EmployerBankPage: React.FC = () => {
  usePageTitle('Банк кандидатов');
  const { data: dict } = useDictionaries();
  const invited = useInvitedMap();
  const [spec, setSpec] = useState<string>(ALL);
  const [grade, setGrade] = useState<string>(ALL);
  const [format, setFormat] = useState<string>(ALL);
  const [skills, setSkills] = useState<string[]>([]);
  const [city, setCity] = useState('');
  const [salaryMax, setSalaryMax] = useState<number | string>('');
  const [fspOnly, setFspOnly] = useState(false);
  const [inviteTarget, setInviteTarget] = useState<CandidateCard | null>(null);

  // Отбор выполняет сервер по всему банку (специализация, подтверждённый грейд, формат, зарплата, стек, ФСП),
  // иначе фильтр видел бы только первые 100 кандидатов. Город сверяется здесь по подстроке.
  const debouncedSalary = useDebounced(salaryMax === '' ? undefined : Number(salaryMax));
  const serverFilters = useDebounced({
    specialization: spec !== ALL ? spec : undefined,
    grade: grade !== ALL ? grade : undefined,
    work_format: format !== ALL ? format : undefined,
    salary_max: debouncedSalary,
    skills: skills.length ? skills.join(',') : undefined,
    has_fsp: fspOnly ? true : undefined,
    limit: 100, // максимум, который принимает API
  });
  const debouncedCity = useDebounced(city.trim().toLowerCase());

  const { data, isLoading, isError, error, isFetching } = useQuery({
    queryKey: ['candidate-bank', serverFilters],
    queryFn: () => api.searchCandidates(serverFilters),
    placeholderData: (prev) => prev,
  });

  const items = useMemo(
    () =>
      (data?.items ?? []).filter((i) => {
        const c = i.candidate_card;
        const confirmed = c.is_grade_confirmed ?? false;
        if (spec !== ALL && specCode(c.confirmed_specialization) !== spec) return false;
        if (grade !== ALL && !(confirmed && (c.confirmed_grade ?? '').toUpperCase() === grade)) return false;
        if (format !== ALL && c.work_format !== format) return false;
        if (debouncedCity && !(c.city ?? '').toLowerCase().includes(debouncedCity)) return false;
        if (debouncedSalary !== undefined && c.desired_salary_min != null && c.desired_salary_min > debouncedSalary) return false;
        return true;
      }),
    [data, spec, grade, format, debouncedCity, debouncedSalary]
  );

  const specOptions = useMemo(
    () => [{ value: ALL, label: 'Все специализации' }, ...(dict?.specializations ?? []).map((s) => ({ value: s.code, label: s.name }))],
    [dict]
  );

  const reset = () => {
    setSpec(ALL);
    setGrade(ALL);
    setFormat(ALL);
    setSkills([]);
    setCity('');
    setSalaryMax('');
    setFspOnly(false);
  };

  return (
    <Container size="xl" p={0}>
      <Stack gap="lg">
        <PageHeader
          eyebrow="Кабинет работодателя"
          title="Банк кандидатов"
          description="Все кандидаты платформы с фильтрами по специализации, грейду, стеку и подтверждённым достижениям ФСП. Порядок — по силе подтверждённого профиля."
        />

        <Paper withBorder p="lg">
          <SimpleGrid cols={{ base: 1, sm: 2, lg: 4 }} spacing="md">
            <Select label="Специализация" data={specOptions} value={spec} onChange={(v) => setSpec(v ?? ALL)} allowDeselect={false} />
            <Select
              label="Грейд"
              data={[{ value: ALL, label: 'Все грейды' }, ...['INTERN', 'JUNIOR', 'MIDDLE', 'SENIOR'].map((value) => ({ value, label: GRADE_LABELS[value] }))]}
              value={grade}
              onChange={(v) => setGrade(v ?? ALL)}
              allowDeselect={false}
            />
            <Select
              label="Формат работы"
              data={[{ value: ALL, label: 'Любой' }, ...Object.entries(WORK_FORMAT_LABELS).map(([value, label]) => ({ value, label }))]}
              value={format}
              onChange={(v) => setFormat(v ?? ALL)}
              allowDeselect={false}
            />
            <TextInput label="Город" placeholder="Москва" value={city} onChange={(e) => setCity(e.currentTarget.value)} />
            <TagsInput label="Стек" description="Кандидат должен владеть всеми навыками" placeholder="Python, FastAPI…" value={skills} onChange={setSkills} style={{ gridColumn: 'span 1' }} />
            <NumberInput label="Ожидания не выше, ₽" thousandSeparator=" " suffix=" ₽" min={0} step={10000} value={salaryMax} onChange={setSalaryMax} />
          </SimpleGrid>
          <Group justify="space-between" mt="md" wrap="wrap" gap="sm">
            <Switch label="Только с подтверждёнными достижениями ФСП" checked={fspOnly} onChange={(e) => setFspOnly(e.currentTarget.checked)} />
            <Button variant="default" size="xs" onClick={reset}>
              Сбросить фильтры
            </Button>
          </Group>
        </Paper>

        <Paper withBorder p="lg">
          <Group justify="space-between" mb="md" wrap="wrap" gap="sm">
            <Title order={2} size="h3">Найдено: {formatCount(items.length, ['кандидат', 'кандидата', 'кандидатов'])}</Title>
            <Text size="xs" c="dimmed">
              {isFetching
                ? 'Обновляем…'
                : (data?.items.length ?? 0) >= 100
                ? 'Показаны первые 100 по силе профиля — уточните условия поиска'
                : 'Сначала кандидаты с сильнейшим подтверждённым профилем'}
            </Text>
          </Group>

          {isLoading ? (
            <Stack gap="sm">
              <Skeleton h={130} />
              <Skeleton h={130} />
            </Stack>
          ) : isError ? (
            <Alert color="red" variant="light">
              {toApiError(error).message}
            </Alert>
          ) : items.length === 0 ? (
            <Alert variant="light" color="gray" icon={<IconInfoCircle size={18} />} title="Никого не нашли">
              Измените условия поиска или сбросьте фильтры.
            </Alert>
          ) : (
            <Stack gap="sm">
              {items.map((item) => (
                <CandidateCardView key={item.candidate_id} card={item.candidate_card} fspBadge={item.fsp_badge} invitation={invited.get(item.candidate_id)} onInvite={setInviteTarget} />
              ))}
            </Stack>
          )}
        </Paper>
      </Stack>

      <InviteModal candidate={inviteTarget} onClose={() => setInviteTarget(null)} />
    </Container>
  );
};
