import React, { useMemo, useRef, useState } from 'react';
import {
  Alert,
  Badge,
  Box,
  Button,
  Card,
  Container,
  Group,
  LoadingOverlay,
  NumberInput,
  Paper,
  Select,
  SimpleGrid,
  Stack,
  Switch,
  TagsInput,
  Text,
  Textarea,
  TextInput,
  Title,
  UnstyledButton,
} from '@mantine/core';
import { IconHistory, IconInfoCircle, IconSparkles } from '@tabler/icons-react';
import { notifications } from '@mantine/notifications';
import { useMutation } from '@tanstack/react-query';
import { api, CandidateCard, NeedParse, Recommendations } from '../api/api';
import { toApiError } from '../api/http';
import { useDictionaries, useInvitedMap } from '../hooks/queries';
import { StoredNeed, useStoredNeeds } from '../hooks/useStoredNeeds';
import { usePageTitle } from '../hooks/usePageTitle';
import { PageHeader } from '../components/common/PageHeader';
import { CandidateCard as CandidateCardView } from '../components/employer/CandidateCard';
import { InviteModal } from '../components/employer/InviteModal';
import { formatDate, formatMoney } from '../utils/format';
import { GRADE_LABELS, gradeLabel, specCode, specLabel, WORK_FORMAT_LABELS } from '../utils/labels';

const DEFAULT_NEED =
  'Ищем Middle Backend-разработчика на Python (FastAPI, PostgreSQL) в команду платформы процессинга. Нужен опыт с очередями (Kafka) и кэшированием (Redis), коммерческий опыт от 3 лет. Вилка 250 000 – 360 000 ₽ на руки, гибрид в Москве или удалённо.';

const EXAMPLES = [
  { label: 'Frontend React', text: 'Ищем Middle Frontend-разработчика на React и TypeScript. Опыт с TanStack Query, Vite или Next.js, адаптивная вёрстка, тесты на Jest. Опыт от 2 лет, вилка 180 000 – 240 000 ₽ на руки, удалённо.' },
  { label: 'ML-инженер', text: 'Ищем Senior Data Scientist / ML Engineer для рекомендательных систем. Стек: Python, PyTorch, SQL, Pandas, вывод моделей в прод через Docker и FastAPI. Вилка 280 000 – 380 000 ₽ на руки, гибрид.' },
  { label: 'QA-инженер', text: 'Ищем Middle QA-инженера по автоматизации: Python, Pytest, Playwright, Postman, SQL. Опыт от 2 лет, вилка 160 000 – 220 000 ₽ на руки, удалённо.' },
];

const GRADES = ['INTERN', 'JUNIOR', 'MIDDLE', 'SENIOR'].map((value) => ({ value, label: GRADE_LABELS[value] }));
const ALL = 'ALL';

interface NeedForm {
  title: string;
  specialization: string;
  grade: string;
  skills: string[];
  salaryFrom: number | string;
  salaryTo: number | string;
  salaryType: 'NET' | 'GROSS';
  workFormat: string;
  raw: string;
}

/** Одна выдача подбора: предыдущие сохраняются, чтобы уточнение запроса не стирало ранее полученный результат. */
interface Run {
  id: string;
  at: Date;
  need: StoredNeed;
  data: Recommendations;
}

const formFromParse = (p: NeedParse, raw: string): NeedForm => ({
  title: [p.specialization.value && specLabel(p.specialization.value), p.grade.value && gradeLabel(p.grade.value)].filter(Boolean).join(' · '),
  specialization: p.specialization.value ?? 'BACKEND',
  grade: p.grade.value ?? 'MIDDLE',
  skills: p.skills.map((s) => s.name),
  salaryFrom: p.salary_from ?? '',
  salaryTo: p.salary_to ?? '',
  salaryType: p.salary_type === 'GROSS' ? 'GROSS' : 'NET',
  workFormat: p.work_format.value ?? 'REMOTE',
  raw,
});

const confidenceColor = (c: number) => (c >= 0.75 ? 'teal' : c >= 0.5 ? 'orange' : 'gray');
const time = (d: Date) => d.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' });

/** Совпадает ли название категории из выдачи с запрошенной специализацией и грейдом. */
const isRequestedCategory = (category: string, need: StoredNeed) => {
  const [spec, grade] = category.split('·').map((s) => s.trim());
  return Boolean(spec && grade) && specCode(spec).startsWith(specCode(need.specialization)) && grade.toLowerCase() === gradeLabel(need.grade).toLowerCase();
};

export const EmployerMatchingPage: React.FC = () => {
  usePageTitle('Подбор по потребности');
  const { data: dict } = useDictionaries();
  const invited = useInvitedMap();
  const [storedNeeds, addStoredNeed] = useStoredNeeds();

  const [text, setText] = useState(DEFAULT_NEED);
  const [parseProvider, setParseProvider] = useState<'auto' | 'rules'>('auto');
  const [parsed, setParsed] = useState<NeedParse | null>(null);
  const [form, setForm] = useState<NeedForm | null>(null);
  const [runs, setRuns] = useState<Run[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [inviteTarget, setInviteTarget] = useState<CandidateCard | null>(null);

  // Уточнение выдачи без повторного запроса к серверу
  const [confirmedOnly, setConfirmedOnly] = useState(false);
  const [fspOnly, setFspOnly] = useState(false);
  const [category, setCategory] = useState<string | null>(null);
  const [city, setCity] = useState('');
  const [format, setFormat] = useState(ALL);
  const [inBudget, setInBudget] = useState(false);

  // Потребность создаётся один раз для набора параметров: повторное нажатие лишь обновляет выдачу.
  const lastNeed = useRef<{ key: string; need: StoredNeed } | null>(null);

  const specOptions = useMemo(() => (dict?.specializations ?? []).map((s) => ({ value: s.code, label: s.name })), [dict]);
  const active = runs.find((r) => r.id === activeId) ?? null;

  const pushRun = (need: StoredNeed, data: Recommendations) => {
    const run: Run = { id: `${need.id}-${Date.now()}`, at: new Date(), need, data };
    setRuns((prev) => [run, ...prev].slice(0, 6));
    setActiveId(run.id);
    setCategory(null);
  };

  const parse = useMutation({
    mutationFn: ({ t, provider }: { t: string; provider?: 'auto' | 'rules' }) =>
      api.parseNeed(t, undefined, provider),
    onSuccess: (p, { t }) => {
      setParsed(p);
      setForm(formFromParse(p, t));
    },
    onError: (e) => notifications.show({ title: 'Не удалось разобрать текст', message: toApiError(e).message, color: 'red' }),
  });

  const match = useMutation({
    mutationFn: async (f: NeedForm) => {
      const key = JSON.stringify([f.title, f.specialization, f.grade, f.skills, f.salaryFrom, f.salaryTo, f.salaryType, f.workFormat, f.raw]);
      let need = lastNeed.current?.key === key ? lastNeed.current.need : null;
      if (!need) {
        const created = await api.createNeed({
          title: f.title.trim() || 'Потребность',
          target_specialization: f.specialization,
          target_grade: f.grade,
          required_skills: f.skills,
          raw_description: f.raw,
          salary_budget_min: f.salaryFrom === '' ? null : Number(f.salaryFrom),
          salary_budget_max: f.salaryTo === '' ? null : Number(f.salaryTo),
          salary_type: f.salaryType,
          is_gross: f.salaryType === 'GROSS',
          work_format: f.workFormat,
        });
        need = {
          id: created.id,
          title: created.title,
          specialization: f.specialization,
          grade: f.grade,
          skills: f.skills,
          salaryFrom: created.salary_budget_min,
          salaryTo: created.salary_budget_max,
          salaryType: f.salaryType,
          workFormat: f.workFormat,
          source: 'TEXT',
          createdAt: created.created_at,
        };
        lastNeed.current = { key, need };
        addStoredNeed(need);
      }
      const data = await api.recommendations(need.id, { limit: 30, save_snapshot: true });
      return { need, data };
    },
    onSuccess: ({ need, data }) => pushRun(need, data),
    onError: (e) => notifications.show({ title: 'Не удалось выполнить подбор', message: toApiError(e).message, color: 'red' }),
  });

  const rerun = useMutation({
    mutationFn: async (need: StoredNeed) => ({ need, data: await api.recommendations(need.id, { limit: 30, save_snapshot: true }) }),
    onSuccess: ({ need, data }) => pushRun(need, data),
    onError: (e) => notifications.show({ title: 'Не удалось выполнить подбор', message: toApiError(e).message, color: 'red' }),
  });

  const set = <K extends keyof NeedForm>(k: K, v: NeedForm[K]) => setForm((f) => (f ? { ...f, [k]: v } : f));

  const items = active?.data.items ?? [];

  // Рекомендованные категории: связка специализации и грейда с числом кандидатов в выдаче.
  const categories = useMemo(() => {
    const map = new Map<string, number>();
    for (const i of items) map.set(i.candidate_card.confirmed_category ?? 'Категория не присвоена', (map.get(i.candidate_card.confirmed_category ?? 'Категория не присвоена') ?? 0) + 1);
    return [...map.entries()].map(([name, count]) => ({ name, count })).sort((a, b) => b.count - a.count);
  }, [items]);

  const budgetMax = active?.need.salaryTo ?? undefined;
  const visible = useMemo(() => {
    const c = city.trim().toLowerCase();
    return items.filter((i) => {
      const card = i.candidate_card;
      if (confirmedOnly && !(card.is_grade_confirmed ?? Boolean(card.confirmed_grade))) return false;
      if (fspOnly && !card.is_fsp_verified) return false;
      if (category && (card.confirmed_category ?? 'Категория не присвоена') !== category) return false;
      if (c && !(card.city ?? '').toLowerCase().includes(c)) return false;
      if (format !== ALL && card.work_format !== format) return false;
      if (inBudget && budgetMax && card.desired_salary_min != null && card.desired_salary_min > budgetMax) return false;
      return true;
    });
  }, [items, confirmedOnly, fspOnly, category, city, format, inBudget, budgetMax]);

  const filtersOn = confirmedOnly || fspOnly || Boolean(category) || Boolean(city.trim()) || format !== ALL || inBudget;
  const resetFilters = () => {
    setConfirmedOnly(false);
    setFspOnly(false);
    setCategory(null);
    setCity('');
    setFormat(ALL);
    setInBudget(false);
  };

  return (
    <Container size="xl" p={0}>
      <Stack gap="lg">
        <PageHeader
          eyebrow="Кабинет работодателя"
          title="Подбор по описанию потребности"
          description="Опишите задачу своими словами. Система выделит специализацию, грейд, стек и бюджет, вы проверите параметры и получите ранжированную подборку с объяснением."
        />

        <Paper withBorder p="lg">
          <Textarea
            label="Описание потребности"
            description="Свободный текст: роль, чем занимается команда, стек, опыт, формат работы, зарплатная вилка"
            value={text}
            onChange={(e) => setText(e.currentTarget.value)}
            minRows={4}
            autosize
            maxRows={10}
            mb="md"
          />
          <Group justify="space-between" align="center" gap="sm" wrap="wrap">
            <Group gap="xs">
              <Text size="xs" c="dimmed">
                Примеры:
              </Text>
              {EXAMPLES.map((ex) => (
                <Button
                  key={ex.label}
                  variant="default"
                  size="compact-xs"
                  onClick={() => {
                    setText(ex.text);
                    parse.mutate({ t: ex.text, provider: parseProvider });
                  }}
                >
                  {ex.label}
                </Button>
              ))}
            </Group>
            <Group gap="xs" align="center">
              <Select
                size="xs"
                w={210}
                data={[
                  { value: 'auto', label: 'AI: GigaChat (152-ФЗ)' },
                  { value: 'rules', label: 'Локальный NLP (правила)' },
                ]}
                value={parseProvider}
                onChange={(v) => setParseProvider((v as 'auto' | 'rules') || 'auto')}
                allowDeselect={false}
              />
              <Button
                loading={parse.isPending}
                disabled={text.trim().length < 10}
                leftSection={<IconSparkles size={16} />}
                onClick={() => parse.mutate({ t: text, provider: parseProvider })}
              >
                Разобрать текст
              </Button>
            </Group>
          </Group>
        </Paper>

        {storedNeeds.length > 0 && (
          <Paper withBorder p="lg">
            <Group gap="xs" mb={4}>
              <IconHistory size={18} color="var(--fsp-purple)" />
              <Title order={2} size="h4">
                Мои потребности
              </Title>
            </Group>
            <Text size="sm" c="dimmed" mb="md">
              Ранее созданные потребности и вакансии с этого устройства. Подбор можно повторить: выдача обновится по текущей базе кандидатов, прежние результаты останутся в списке подборок.
            </Text>
            <SimpleGrid cols={{ base: 1, sm: 2, lg: 3 }} spacing="sm">
              {storedNeeds.slice(0, 6).map((n) => (
                <Card key={n.id} padding="sm">
                  <Group justify="space-between" wrap="wrap" gap="xs" mb={4}>
                    <Text size="sm" fw={600} lineClamp={1} style={{ minWidth: 0, flex: 1 }}>
                      {n.title}
                    </Text>
                    <Badge size="xs" variant="light" color={n.source === 'ATS' ? 'blue' : 'gray'} style={{ flexShrink: 0 }}>
                      {n.source === 'ATS' ? 'ATS' : 'Текст'}
                    </Badge>
                  </Group>
                  <Text size="xs" c="dimmed">
                    {specLabel(n.specialization)} · {gradeLabel(n.grade)}
                    {n.salaryTo ? ` · до ${formatMoney(n.salaryTo)}` : ''} · {formatDate(n.createdAt)}
                  </Text>
                  <Button mt="xs" size="compact-sm" variant="default" loading={rerun.isPending && rerun.variables?.id === n.id} onClick={() => rerun.mutate(n)}>
                    Подобрать снова
                  </Button>
                </Card>
              ))}
            </SimpleGrid>
          </Paper>
        )}

        {form && parsed && (
          <Paper withBorder p="lg">
            <Group justify="space-between" mb="md" align="flex-start" wrap="wrap" gap="sm">
              <Box>
                <Title order={2} size="h3">
                  Параметры потребности
                </Title>
                <Text size="sm" c="dimmed">
                  Значения извлечены автоматически ({parsed.parser_source === 'gigachat' ? 'нейросеть GigaChat AI' : 'внутренний NLP-парсер'}). Исправьте их при необходимости и запустите подбор.
                </Text>
              </Box>
              <Group gap={6} wrap="wrap">
                {parsed.parser_source === 'gigachat' ? (
                  <Badge
                    variant="filled"
                    color="violet"
                    leftSection={<IconSparkles size={12} />}
                    title="Распознано нейросетью GigaChat (ПАО Сбербанк, 152-ФЗ) со структурированным извлечением сущностей"
                  >
                    GigaChat AI (152-ФЗ)
                  </Badge>
                ) : (
                  <Badge
                    variant="light"
                    color="teal"
                    title={parsed.ai_available === false ? 'GigaChat временно недоступен — применён внутренний NLP-парсер' : 'Распознано детерминированным алгоритмическим NLP-парсером'}
                  >
                    {parsed.engine_badge || 'Внутренний NLP-парсер'}
                  </Badge>
                )}
                <Badge variant="light" color={confidenceColor(parsed.specialization.confidence ?? 0)} title={(parsed.specialization.evidence ?? []).join(', ')}>
                  Специализация: {Math.round((parsed.specialization.confidence ?? 0) * 100)}%
                </Badge>
                <Badge variant="light" color={confidenceColor(parsed.grade.confidence ?? 0)} title={(parsed.grade.evidence ?? []).join(', ')}>
                  Грейд: {Math.round((parsed.grade.confidence ?? 0) * 100)}%
                </Badge>
              </Group>
            </Group>

            <SimpleGrid cols={{ base: 1, sm: 2, lg: 4 }} spacing="md">
              <TextInput label="Название позиции" value={form.title} onChange={(e) => set('title', e.currentTarget.value)} />
              <Select label="Специализация" data={specOptions} value={form.specialization} onChange={(v) => v && set('specialization', v)} allowDeselect={false} />
              <Select label="Грейд" data={GRADES} value={form.grade} onChange={(v) => v && set('grade', v)} allowDeselect={false} />
              <Select
                label="Формат работы"
                data={Object.entries(WORK_FORMAT_LABELS).map(([value, label]) => ({ value, label }))}
                value={form.workFormat}
                onChange={(v) => v && set('workFormat', v)}
                allowDeselect={false}
              />
              <NumberInput label="Бюджет от, ₽" thousandSeparator=" " suffix=" ₽" min={0} step={10000} value={form.salaryFrom} onChange={(v) => set('salaryFrom', v)} />
              <NumberInput label="Бюджет до, ₽" thousandSeparator=" " suffix=" ₽" min={0} step={10000} value={form.salaryTo} onChange={(v) => set('salaryTo', v)} />
              <Select
                label="Бюджет указан"
                data={[
                  { value: 'NET', label: 'На руки' },
                  { value: 'GROSS', label: 'До вычета НДФЛ' },
                ]}
                value={form.salaryType}
                onChange={(v) => set('salaryType', v === 'GROSS' ? 'GROSS' : 'NET')}
                allowDeselect={false}
              />
            </SimpleGrid>
            <TagsInput mt="md" label="Обязательный стек" value={form.skills} onChange={(v) => set('skills', v)} placeholder="Добавьте навык и нажмите Enter" />
            {parsed.experience_years != null && (
              <Text size="xs" c="dimmed" mt="xs">
                Из текста извлечён требуемый опыт: от {parsed.experience_years} лет{parsed.city.value ? `, город: ${parsed.city.value}` : ''}.
              </Text>
            )}
            <Group justify="flex-end" mt="md">
              <Button loading={match.isPending} leftSection={<IconSparkles size={16} />} onClick={() => match.mutate(form)}>
                {runs.length > 0 ? 'Обновить подборку' : 'Подобрать кандидатов'}
              </Button>
            </Group>
          </Paper>
        )}

        {runs.length > 1 && (
          <Paper withBorder p="md">
            <Group gap="xs" align="center">
              <Text size="xs" fw={600} c="dimmed">
                Подборки:
              </Text>
              {runs.map((r, i) => (
                <Button key={r.id} size="compact-xs" variant={r.id === activeId ? 'filled' : 'default'} onClick={() => { setActiveId(r.id); setCategory(null); }}>
                  {runs.length - i}. {r.need.title} · {time(r.at)}
                </Button>
              ))}
            </Group>
          </Paper>
        )}

        <Box pos="relative" mih={active ? 120 : 0}>
          <LoadingOverlay visible={(match.isPending || rerun.isPending) && Boolean(active)} zIndex={20} overlayProps={{ blur: 1, backgroundOpacity: 0.5 }} loaderProps={{ size: 'sm', color: 'fspPink' }} />
          {active && (
            <Stack gap="lg">
              <Paper withBorder p="lg">
                <Title order={2} size="h3" mb={4}>
                  Рекомендованные категории
                </Title>
                <Text size="sm" c="dimmed" mb="md">
                  Категория — связка специализации и подтверждённого грейда. Выберите категорию, чтобы сузить выдачу; подборка при этом не теряется.
                </Text>
                {categories.length === 0 ? (
                  <Text size="sm" c="dimmed">
                    В выдаче нет кандидатов с присвоенной категорией.
                  </Text>
                ) : (
                  <SimpleGrid cols={{ base: 1, sm: 2, lg: 4 }} spacing="sm">
                    {categories.map((c) => {
                      const selected = category === c.name;
                      return (
                        <UnstyledButton
                          key={c.name}
                          className="choice-card"
                          data-selected={selected}
                          aria-pressed={selected}
                          style={{ borderRadius: 6, padding: 12 }}
                          onClick={() => setCategory(selected ? null : c.name)}
                        >
                          <Group justify="space-between" wrap="wrap" gap="xs" align="flex-start">
                            <Text size="sm" fw={600} style={{ minWidth: 0, flex: 1 }}>
                              {c.name}
                            </Text>
                            <Badge variant="light" color="fspPurple" style={{ flexShrink: 0 }}>
                              {c.count}
                            </Badge>
                          </Group>
                          {isRequestedCategory(c.name, active.need) && (
                            <Text size="xs" c="teal" fw={600} mt={4}>
                              Запрошенная категория
                            </Text>
                          )}
                        </UnstyledButton>
                      );
                    })}
                  </SimpleGrid>
                )}
              </Paper>

              <Paper withBorder p="lg">
                <Group justify="space-between" align="flex-start" mb="md" gap="md">
                  <Box>
                    <Title order={2} size="h3">
                      Ранжированные кандидаты
                    </Title>
                    <Text size="sm" c="dimmed" maw={680}>
                      Найдено: {active.data.total_found}. Порядок определяют подтверждённая категория, стек и результат теста; достижения ФСП дают бонус. Контакты скрыты до принятия приглашения.
                    </Text>
                  </Box>
                  {filtersOn && (
                    <Button variant="subtle" size="compact-sm" onClick={resetFilters}>
                      Сбросить фильтры
                    </Button>
                  )}
                </Group>

                <SimpleGrid cols={{ base: 1, sm: 2, lg: 4 }} spacing="md" mb="md">
                  <TextInput label="Город" placeholder="Москва" value={city} onChange={(e) => setCity(e.currentTarget.value)} />
                  <Select
                    label="Формат работы"
                    data={[{ value: ALL, label: 'Любой' }, ...Object.entries(WORK_FORMAT_LABELS).map(([value, label]) => ({ value, label }))]}
                    value={format}
                    onChange={(v) => setFormat(v ?? ALL)}
                    allowDeselect={false}
                  />
                  <Stack gap={6} justify="flex-end">
                    <Switch size="sm" checked={confirmedOnly} onChange={(e) => setConfirmedOnly(e.currentTarget.checked)} label="Только с подтверждённым грейдом" />
                    <Switch size="sm" checked={fspOnly} onChange={(e) => setFspOnly(e.currentTarget.checked)} label="Только с достижениями ФСП" />
                  </Stack>
                  <Stack gap={6} justify="flex-end">
                    <Switch size="sm" checked={inBudget} disabled={!budgetMax} onChange={(e) => setInBudget(e.currentTarget.checked)} label={budgetMax ? `Ожидания в бюджете (до ${formatMoney(budgetMax)})` : 'Бюджет не указан'} />
                  </Stack>
                </SimpleGrid>

                {visible.length === 0 ? (
                  <Alert variant="light" color="gray" icon={<IconInfoCircle size={18} />} title="Подходящих кандидатов не найдено">
                    {items.length > 0
                      ? 'Фильтры скрыли всю подборку — ослабьте условия выше.'
                      : 'Для выбранной специализации и грейда в базе пока нет кандидатов с подтверждённой категорией. Попробуйте смежный грейд или другую специализацию.'}
                  </Alert>
                ) : (
                  <Stack gap="sm">
                    {visible.map((item, i) => (
                      <CandidateCardView
                        key={item.candidate_id}
                        card={item.candidate_card}
                        rank={i + 1}
                        scorePercent={item.score_percent}
                        reasons={item.bullet_points}
                        components={item.components}
                        fspBadge={item.fsp_badge}
                        needId={active?.need.id}
                        invitation={invited.get(item.candidate_id)}
                        onInvite={setInviteTarget}
                      />
                    ))}
                  </Stack>
                )}
              </Paper>
            </Stack>
          )}
        </Box>
      </Stack>

      <InviteModal
        candidate={inviteTarget}
        onClose={() => setInviteTarget(null)}
        needId={active?.need.id}
        defaultSalary={active ? { from: active.need.salaryFrom, to: active.need.salaryTo, type: active.need.salaryType } : undefined}
      />
    </Container>
  );
};
