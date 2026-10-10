import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  Alert,
  Badge,
  Box,
  Button,
  Card,
  Container,
  Group,
  List,
  Paper,
  Progress,
  Radio,
  SegmentedControl,
  Select,
  SimpleGrid,
  Skeleton,
  Stack,
  Text,
  ThemeIcon,
  Title,
} from '@mantine/core';
import { IconAlertTriangle, IconArrowRight, IconCheck, IconClock, IconInfoCircle, IconPlayerPlay, IconShieldLock } from '@tabler/icons-react';
import { useQueryClient } from '@tanstack/react-query';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { api, AssessmentFinish, AssessmentItem } from '../api/api';
import { toApiError } from '../api/http';
import { keys, useDictionaries, useGradeStatus, useProfile } from '../hooks/queries';
import { PageHeader } from '../components/common/PageHeader';
import { AppModal } from '../components/common/AppModal';
import { usePageTitle } from '../hooks/usePageTitle';
import { useExtras } from '../hooks/useExtras';
import { daysUntil, formatCount, formatDate, formatDecimal, formatTheta } from '../utils/format';
import { gradeLabel, RECOMMENDATION_LABELS, specLabel, TOPIC_LEVEL_LABELS } from '../utils/labels';

const GRADE_CARDS = [
  { code: 'INTERN', range: '−1,5 ≤ θ < −0,5', desc: 'Осваивает базовый синтаксис, выполняет типовые учебные задачи с наставником.' },
  { code: 'JUNIOR', range: '−0,5 ≤ θ < 0,5', desc: 'Решает изолированные задачи по подробному ТЗ, пишет модульные тесты.' },
  { code: 'MIDDLE', range: '0,5 ≤ θ < 1,5', desc: 'Проектирует и реализует модуль целиком, работает с БД, кэшем и транзакциями.' },
  { code: 'SENIOR', range: 'θ ≥ 1,5', desc: 'Определяет архитектуру сервисов, отвечает за масштабируемость и технический долг.' },
];

const GRADE_ORDER = ['INTERN', 'JUNIOR', 'MIDDLE', 'SENIOR'];

const recommendGrade = (years?: number): string => {
  if (years === undefined) return 'MIDDLE';
  if (years < 1) return 'INTERN';
  if (years < 2.5) return 'JUNIOR';
  if (years < 5) return 'MIDDLE';
  return 'SENIOR';
};

const formatElapsed = (seconds: number) =>
  `${Math.floor(seconds / 60).toString().padStart(2, '0')}:${(seconds % 60).toString().padStart(2, '0')}`;

const OPEN_SESSION_KEY = 'fsp_talent_open_assessment';

interface AssessmentPlayerPageProps {
  /** Экспресс-тест без регистрации для экспертов (маршрут /express). */
  publicMode?: boolean;
}

interface RunningSession {
  id: string;
  maxItems: number;
  express: boolean;
  specialization: string;
  targetGrade: string;
}

export const AssessmentPlayerPage: React.FC<AssessmentPlayerPageProps> = ({ publicMode = false }) => {
  usePageTitle(publicMode ? 'Экспресс-тест' : 'Квалификационный тест');
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [searchParams] = useSearchParams();
  const { data: dict } = useDictionaries();
  const { data: profile } = useProfile();
  const { data: gradeStatus } = useGradeStatus();
  const [extras] = useExtras();

  const urlGrade = searchParams.get('grade')?.toUpperCase();
  const urlSpec = searchParams.get('spec')?.toUpperCase();

  const [phase, setPhase] = useState<'config' | 'running' | 'result'>('config');
  const [grade, setGrade] = useState<string>(urlGrade && GRADE_ORDER.includes(urlGrade) ? urlGrade : 'MIDDLE');
  const [spec, setSpec] = useState<string>(urlSpec ?? 'BACKEND');
  const [express, setExpress] = useState<boolean>(publicMode || searchParams.get('mode') === 'express');
  const touched = useRef(Boolean(urlGrade || urlSpec));

  const [session, setSession] = useState<RunningSession | null>(null);
  const [item, setItem] = useState<AssessmentItem | null>(null);
  const [answered, setAnswered] = useState(0);
  const [selected, setSelected] = useState('');
  const [result, setResult] = useState<AssessmentFinish | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [elapsed, setElapsed] = useState(0);
  const [abortOpen, setAbortOpen] = useState(false);
  const itemShownAt = useRef(Date.now());

  const specs = useMemo(
    () => (dict?.specializations ?? []).filter((s) => s.has_active_assessment === 1).map((s) => ({ value: s.code, label: s.name })),
    [dict]
  );

  // Значения по умолчанию берутся из профиля, как только он загрузится (если пользователь ничего не менял).
  useEffect(() => {
    if (publicMode || !profile || touched.current) return;
    touched.current = true;
    if (profile.declared_grade && GRADE_ORDER.includes(profile.declared_grade)) setGrade(profile.declared_grade);
    else if (profile.confirmed_grade && GRADE_ORDER.includes(profile.confirmed_grade)) setGrade(profile.confirmed_grade);
    const code = (profile.confirmed_specialization ?? '').toUpperCase();
    if (code) setSpec(code);
  }, [profile, publicMode]);

  useEffect(() => {
    if (specs.length > 0 && !specs.some((s) => s.value === spec)) setSpec(specs[0].value);
  }, [specs, spec]);

  // Таймер прохождения (справочно: сервер не ограничивает общее время)
  useEffect(() => {
    if (phase !== 'running') return;
    setElapsed(0);
    const t = window.setInterval(() => setElapsed((v) => v + 1), 1000);
    return () => window.clearInterval(t);
  }, [phase]);

  const loadNext = async (s: RunningSession): Promise<boolean> => {
    const next = await api.nextItem(s.id);
    if (next.is_finished) return false;
    setItem(next);
    setSelected('');
    itemShownAt.current = Date.now();
    return true;
  };

  const finish = async (s: RunningSession) => {
    const done = await api.finishAssessment(s.id);
    sessionStorage.removeItem(OPEN_SESSION_KEY);
    setResult(done);
    setPhase('result');
    if (!publicMode) {
      queryClient.invalidateQueries({ queryKey: keys.profile });
      queryClient.invalidateQueries({ queryKey: keys.grade });
    }
  };

  const begin = async (s: RunningSession, alreadyAnswered = 0) => {
    setSession(s);
    setAnswered(alreadyAnswered);
    setResult(null);
    if (await loadNext(s)) setPhase('running');
    else await finish(s);
  };

  const start = async () => {
    setBusy(true);
    setError(null);
    try {
      const started = publicMode
        ? await api.startDemoAssessment({ specialization: spec, target_grade: grade })
        : await api.startAssessment({ candidate_profile_id: profile?.id, specialization: spec, target_grade: grade, is_express: express });
      const s: RunningSession = {
        id: started.session_id,
        maxItems: started.max_items ?? (express ? 5 : 25),
        express: express || Boolean(started.is_demo),
        specialization: started.specialization,
        targetGrade: started.target_grade,
      };
      if (!publicMode) sessionStorage.setItem(OPEN_SESSION_KEY, JSON.stringify(s));
      await begin(s);
    } catch (e) {
      setError(toApiError(e).message);
    } finally {
      setBusy(false);
    }
  };

  const resume = async () => {
    if (!gradeStatus?.open_session_id) return;
    setBusy(true);
    setError(null);
    try {
      let stored: RunningSession | null = null;
      try {
        const raw = sessionStorage.getItem(OPEN_SESSION_KEY);
        stored = raw ? (JSON.parse(raw) as RunningSession) : null;
      } catch {
        stored = null;
      }
      const s: RunningSession =
        stored && stored.id === gradeStatus.open_session_id
          ? stored
          : { id: gradeStatus.open_session_id, maxItems: 25, express: false, specialization: spec, targetGrade: grade };
      await begin(s);
    } catch (e) {
      setError(toApiError(e).message);
    } finally {
      setBusy(false);
    }
  };

  const submitAnswer = async () => {
    if (!session || !item || !selected) return;
    setBusy(true);
    setError(null);
    try {
      const res = await api.answer(session.id, {
        session_item_id: item.session_item_id,
        response: selected,
        response_time_seconds: Math.max(1, Math.round((Date.now() - itemShownAt.current) / 1000)),
      });
      setAnswered(res.items_count);
      if (res.is_finished || !(await loadNext(session))) await finish(session);
    } catch (e) {
      setError(toApiError(e).message);
    } finally {
      setBusy(false);
    }
  };

  const abort = () => {
    sessionStorage.removeItem(OPEN_SESSION_KEY);
    setAbortOpen(false);
    setPhase('config');
    setSession(null);
    setItem(null);
  };

  // ---------------------------------------------------------------- Настройка
  if (phase === 'config') {
    const attempt = gradeStatus?.regular_attempt;
    const blocked = !publicMode && attempt && attempt.allowed === false;
    const recommended = recommendGrade(extras.experience_years);
    const waitDays = daysUntil(attempt?.available_at ?? gradeStatus?.next_grade_change_available_at);

    return (
      <Container size="lg" p={0}>
        <Stack gap="lg">
          <PageHeader
            eyebrow={publicMode ? 'Для экспертов' : 'Кабинет кандидата'}
            title={publicMode ? 'Экспресс-тест без регистрации' : 'Квалификационный тест'}
            description={
              publicMode
                ? 'Пять заданий, около пяти минут. Результат не сохраняется и не влияет на ограничения по времени. Демонстрирует адаптивную механику и защиту заданий от распространения.'
                : 'Тест подтверждает заявленный грейд и определяет категорию, которую видят работодатели. Грейд выбираете вы; при неудаче профиль не скрывается, а получает статус «Не подтверждён».'
            }
          />

          {!publicMode && gradeStatus?.open_session_id && (
            <Alert color="blue" variant="light" icon={<IconInfoCircle size={18} />} title="Есть незавершённый тест">
              <Group justify="space-between" align="center">
                <Text size="sm">Вы можете продолжить прохождение с того же места.</Text>
                <Button size="xs" loading={busy} onClick={resume}>
                  Продолжить тест
                </Button>
              </Group>
            </Alert>
          )}

          <Paper withBorder p="lg">
            <Title order={2} size="h4" mb={4}>
              1. Грейд, на который вы претендуете
            </Title>
            <Alert variant="light" color="gray" icon={<IconInfoCircle size={18} />} mb="md" p="sm">
              Выбор грейда задаёт стартовую сложность адаптивного теста.{' '}
              {extras.experience_years !== undefined
                ? `По указанному опыту (${extras.experience_years} лет) ориентир — ${gradeLabel(recommended)}. Это только подсказка: выбор остаётся за вами.`
                : 'Выбор остаётся за вами; опыт можно указать в анкете.'}
            </Alert>
            <SimpleGrid cols={{ base: 1, xs: 2, lg: 4 }} spacing="sm" role="radiogroup" aria-label="Целевой грейд">
              {GRADE_CARDS.map((g) => {
                const sel = grade === g.code;
                const choose = () => {
                  touched.current = true;
                  setGrade(g.code);
                };
                return (
                  <Card
                    key={g.code}
                    padding="md"
                    className="choice-card"
                    data-selected={sel}
                    role="radio"
                    aria-checked={sel}
                    tabIndex={0}
                    onClick={choose}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault();
                        choose();
                      }
                    }}
                  >
                    <Group justify="space-between" mb={6}>
                      <Text fw={700}>{gradeLabel(g.code)}</Text>
                      {sel && (
                        <ThemeIcon size="sm" radius="xl" color="fspPink">
                          <IconCheck size={12} />
                        </ThemeIcon>
                      )}
                    </Group>
                    <Text size="xs" fw={600} c="fspPurple" mb={6}>
                      {g.range}
                    </Text>
                    <Text size="xs" c="dimmed">
                      {g.desc}
                    </Text>
                  </Card>
                );
              })}
            </SimpleGrid>
          </Paper>

          <Paper withBorder p="lg">
            <Title order={2} size="h4" mb="sm">
              2. Специализация
            </Title>
            {specs.length === 0 ? (
              <Skeleton h={36} maw={420} />
            ) : (
              <Select
                data={specs}
                value={spec}
                onChange={(v) => {
                  if (v) {
                    touched.current = true;
                    setSpec(v);
                  }
                }}
                allowDeselect={false}
                aria-label="Специализация"
                maw={420}
              />
            )}
            <Text size="xs" c="dimmed" mt={6}>
              Тесты доступны для специализаций с готовым банком заданий.
            </Text>
          </Paper>

          {!publicMode && (
            <Paper withBorder p="lg">
              <Title order={2} size="h4" mb="sm">
                3. Режим прохождения
              </Title>
              <SegmentedControl
                value={express ? 'express' : 'standard'}
                onChange={(v) => setExpress(v === 'express')}
                data={[
                  { value: 'standard', label: 'Стандартный' },
                  { value: 'express', label: 'Экспресс' },
                ]}
                mb="sm"
              />
              <Text size="sm" c="dimmed">
                {express
                  ? 'Экспресс: 5 заданий, около 5 минут. Тренировка и проверка механики: результат не меняет грейд и не тратит попытки.'
                  : 'Стандартный: от 12 до 25 заданий. Тест завершается досрочно, когда точность оценки достаточна (стандартная ошибка ниже 0,30).'}
              </Text>
            </Paper>
          )}

          <Paper withBorder p="lg">
            <Text className="section-eyebrow" mb="xs">
              Правила
            </Text>
            <List spacing={6} size="sm" icon={<ThemeIcon size={16} radius="xl" color="teal" variant="light"><IconCheck size={10} /></ThemeIcon>}>
              <List.Item>Задания собираются из параметризованных семейств: у разных кандидатов отличаются данные и порядок вариантов ответа.</List.Item>
              <List.Item>Следующее задание подбирается по вашим ответам; вернуться к пройденному нельзя.</List.Item>
              <List.Item>Неудачная попытка на более высокий грейд не отменяет и не понижает текущую категорию.</List.Item>
              <List.Item>После подтверждения грейда повторный тест на смену грейда доступен через 90 дней.</List.Item>
            </List>
          </Paper>

          {blocked && (
            <Alert color="orange" variant="light" icon={<IconAlertTriangle size={18} />} title="Тест пока недоступен">
              {attempt?.message}
              {waitDays > 0 && ` Следующая попытка — через ${formatCount(waitDays, ['день', 'дня', 'дней'])}.`}
            </Alert>
          )}
          {!publicMode && !blocked && attempt?.initial_attempts_left != null && attempt.initial_attempts_left > 0 && attempt.kind === 'INITIAL' && (
            <Text size="sm" c="dimmed">
              Идёт первичное определение грейда: осталось попыток — {attempt.initial_attempts_left}.
            </Text>
          )}
          {error && (
            <Alert color="red" variant="light" icon={<IconAlertTriangle size={18} />} role="alert">
              {error}
            </Alert>
          )}

          <Group justify="space-between" align="center">
            <Button variant="default" onClick={() => navigate(publicMode ? '/demo' : '/candidate')}>
              {publicMode ? 'К материалам для экспертов' : 'В профиль'}
            </Button>
            <Button size="md" loading={busy} disabled={Boolean(blocked) || specs.length === 0} leftSection={<IconPlayerPlay size={18} />} onClick={start}>
              {express ? 'Начать экспресс-тест' : 'Начать тест'} · {gradeLabel(grade)}
            </Button>
          </Group>
        </Stack>
      </Container>
    );
  }

  // ---------------------------------------------------------------- Результат
  if (phase === 'result' && result) {
    // экспресс-тест только показывает оценку: грейд и категорию присваивает квалификационный тест
    const demo = Boolean(result.is_demo);
    const confirmed = result.is_confirmed && !demo;
    const waitDays = daysUntil(result.next_grade_change_available_at);
    return (
      <Container size="md" p={0}>
        <Stack gap="lg">
          <PageHeader
            eyebrow="Результат"
            title={demo ? 'Результат экспресс-теста' : confirmed ? 'Грейд подтверждён' : 'Грейд не подтверждён'}
            description={
              demo
                ? `Оценка по 5 заданиям: ${result.is_confirmed ? 'уровень заявленного грейда достигнут' : 'уровень заявленного грейда не достигнут'}. Результат не сохраняется в профиле.`
                : RECOMMENDATION_LABELS[result.recommendation] ?? undefined
            }
          />

          <Paper withBorder p="lg" style={{ borderLeft: `4px solid ${confirmed ? 'var(--mantine-color-teal-6)' : 'var(--mantine-color-orange-6)'}` }}>
            <Group justify="space-between" align="flex-start" gap="lg">
              <Box>
                <Text className="section-eyebrow">{confirmed ? 'Присвоенная категория' : demo ? 'Проверенный грейд' : 'Заявленный грейд'}</Text>
                <Title order={2} mt={2}>
                  {confirmed ? result.confirmed_category ?? `${specLabel(session?.specialization)} · ${gradeLabel(result.confirmed_grade)}` : `${specLabel(session?.specialization)} · ${gradeLabel(result.target_grade)}`}
                </Title>
                <Badge mt="xs" color={confirmed ? 'teal' : demo ? 'gray' : 'orange'} variant="light">
                  {confirmed ? 'Подтверждено тестом' : demo ? 'Не сохраняется в профиле' : 'Не подтверждено'}
                </Badge>
              </Box>
              <Group gap="xl">
                <Box>
                  <Text size="xs" c="dimmed">
                    Оценка способности
                  </Text>
                  <Text fw={700} size="xl">
                    {formatTheta(result.final_theta)}
                  </Text>
                  <Text size="xs" c="dimmed">
                    погрешность ±{formatDecimal(result.final_se)}
                  </Text>
                </Box>
                {result.category_percentile != null && (
                  <Box>
                    <Text size="xs" c="dimmed">
                      Процентиль
                    </Text>
                    <Text fw={700} size="xl">
                      {result.category_percentile}
                    </Text>
                    <Text size="xs" c="dimmed">
                      по специализации
                    </Text>
                  </Box>
                )}
                <Box>
                  <Text size="xs" c="dimmed">
                    Заданий
                  </Text>
                  <Text fw={700} size="xl">
                    {result.items_count}
                  </Text>
                </Box>
              </Group>
            </Group>
            <Text size="sm" c="dimmed" mt="md">
              {result.explanation}
            </Text>
          </Paper>

          {(result.topic_profile ?? []).length > 0 && (
            <Paper withBorder p="lg">
              <Title order={2} size="h4" mb="md">
                Результаты по темам
              </Title>
              <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="md">
                {(result.topic_profile ?? []).map((t) => {
                  const lvl = TOPIC_LEVEL_LABELS[t.level] ?? { label: t.level, color: 'gray' };
                  const pct = t.items > 0 ? Math.round((t.correct / t.items) * 100) : 0;
                  return (
                    <Box key={t.topic}>
                      <Group justify="space-between" mb={4}>
                        <Text size="sm" fw={500}>
                          {t.topic}
                        </Text>
                        <Badge size="sm" variant="light" color={lvl.color}>
                          {lvl.label}
                        </Badge>
                      </Group>
                      <Progress value={pct} color={lvl.color} size="sm" aria-label={t.topic} />
                      <Text size="xs" c="dimmed" mt={2}>
                        верно {t.correct} из {t.items}
                      </Text>
                    </Box>
                  );
                })}
              </SimpleGrid>
            </Paper>
          )}

          {confirmed && !publicMode && (
            <Alert variant="light" color="blue" icon={<IconInfoCircle size={18} />} title={waitDays > 0 ? `Следующая смена грейда — через ${formatCount(waitDays, ['день', 'дня', 'дней'])}` : 'Категория закреплена'}>
              {result.next_grade_change_available_at
                ? `Ограничение действует до ${formatDate(result.next_grade_change_available_at)}. Оно защищает работодателей от случайных скачков оценки.`
                : 'Ограничение защищает работодателей от случайных скачков оценки и поддерживает доверие к категории.'}
            </Alert>
          )}
          {!confirmed && !demo && (
            <Alert variant="light" color="orange" icon={<IconInfoCircle size={18} />} title="Что можно сделать">
              {result.suggested_grade
                ? `Пройдите тест на грейд ${gradeLabel(result.suggested_grade)}: принудительного понижения не происходит, выбор за вами.`
                : 'Повторите попытку позже после подготовки.'}
              {result.follow_up && ` Предложение действует до ${formatDate(result.follow_up.available_until)}.`}
            </Alert>
          )}

          <Group justify="flex-end" gap="sm">
            {!confirmed && !demo && result.suggested_grade && (
              <Button
                variant="light"
                onClick={() => {
                  setGrade(result.suggested_grade!);
                  touched.current = true;
                  setPhase('config');
                }}
              >
                Тест на грейд {gradeLabel(result.suggested_grade)}
              </Button>
            )}
            <Button variant="default" onClick={() => setPhase('config')}>
              Пройти заново
            </Button>
            <Button rightSection={<IconArrowRight size={16} />} onClick={() => navigate(publicMode ? '/register' : '/candidate')}>
              {publicMode ? 'Зарегистрироваться' : 'В профиль'}
            </Button>
          </Group>
        </Stack>
      </Container>
    );
  }

  // ---------------------------------------------------------------- Вопросы
  if (!session || !item) {
    return (
      <Container size="md" p={0}>
        <Paper withBorder p="lg">
          <Text>Загрузка задания…</Text>
        </Paper>
      </Container>
    );
  }

  const optionEntries = Object.entries(item.options).sort(([a], [b]) => a.localeCompare(b));
  const index = item.item_index || answered + 1;

  return (
    <Container size="md" p={0}>
      <Paper withBorder p="lg">
        <Group justify="space-between" align="center" mb="sm" wrap="wrap" gap="xs">
          <Group gap="xs">
            <Badge variant="light" color="fspPink" size="lg">
              Задание {index}{session.express ? ` из ${session.maxItems}` : ''}
            </Badge>
            <Badge variant="outline" color="gray">
              {gradeLabel(session.targetGrade)}
            </Badge>
            {session.express && (
              <Badge variant="light" color="orange">
                Экспресс
              </Badge>
            )}
          </Group>
          <Group gap={6} role="timer" aria-label={`Прошло времени: ${formatElapsed(elapsed)}`}>
            <IconClock size={16} color="var(--fsp-text-muted)" />
            <Text fw={700} size="sm" style={{ fontVariantNumeric: 'tabular-nums' }}>
              {formatElapsed(elapsed)}
            </Text>
          </Group>
        </Group>

        <Progress value={Math.min(100, (answered / session.maxItems) * 100)} size="sm" color={session.express ? 'orange' : 'fspPink'} mb="md" aria-label="Прогресс теста" />

        <Group gap="xs" mb="md">
          <Badge size="sm" variant="light" color="violet" leftSection={<IconShieldLock size={11} />}>
            Вариант задания № {item.seed}
          </Badge>
          <Badge size="sm" variant="light" color="gray">
            {item.topic}
          </Badge>
        </Group>

        <Text size="lg" fw={600} mb="md" style={{ whiteSpace: 'pre-line' }}>
          {item.question_text}
        </Text>

        {item.code_snippet && (
          <Box
            component="pre"
            p="md"
            style={{ background: 'var(--fsp-ink)', color: '#f3f4f7', borderRadius: 6, overflowX: 'auto', fontSize: 13, lineHeight: 1.55, margin: 0, marginBottom: 16 }}
          >
            <code>{item.code_snippet}</code>
          </Box>
        )}

        <Radio.Group value={selected} onChange={setSelected} label="Выберите один вариант" mb="lg">
          <Stack gap="xs" mt="xs">
            {optionEntries.map(([key, text]) => (
              <Radio.Card key={key} value={key} className="choice-card" data-selected={selected === key} p="sm" radius="md">
                <Group wrap="nowrap" align="flex-start">
                  <Radio.Indicator color="fspPink" mt={2} />
                  <Text size="sm" style={{ minWidth: 0, flex: 1, whiteSpace: 'pre-line', overflowWrap: 'break-word' }}>
                    {text}
                  </Text>
                </Group>
              </Radio.Card>
            ))}
          </Stack>
        </Radio.Group>

        {error && (
          <Alert color="red" variant="light" mb="md" role="alert">
            {error}
          </Alert>
        )}

        <Group justify="space-between" pt="md" style={{ borderTop: '1px solid var(--fsp-border)' }}>
          <Button variant="default" onClick={() => setAbortOpen(true)}>
            Прервать тест
          </Button>
          <Button disabled={!selected} loading={busy} rightSection={<IconArrowRight size={16} />} onClick={submitAnswer}>
            Ответить
          </Button>
        </Group>
      </Paper>

      <AppModal opened={abortOpen} onClose={() => setAbortOpen(false)} title="Прервать тест?" size="sm">
        <Stack gap="md">
          <Text size="sm" c="dimmed">
            Сессия останется открытой, и вы сможете продолжить её позже со страницы теста. Результат пока не будет засчитан.
          </Text>
          <Group justify="flex-end">
            <Button variant="default" onClick={() => setAbortOpen(false)}>
              Продолжить тест
            </Button>
            <Button color="red" onClick={abort}>
              Прервать
            </Button>
          </Group>
        </Stack>
      </AppModal>
    </Container>
  );
};
