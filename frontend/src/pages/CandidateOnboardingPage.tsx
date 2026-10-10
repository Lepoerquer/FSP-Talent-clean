import React, { useEffect, useRef, useState } from 'react';
import {
  Alert,
  Badge,
  Box,
  Button,
  Card,
  Container,
  FileButton,
  Group,
  List,
  Loader,
  NumberInput,
  Paper,
  Select,
  SimpleGrid,
  Stack,
  Stepper,
  TagsInput,
  Text,
  Textarea,
  TextInput,
  ThemeIcon,
  Title,
} from '@mantine/core';
import {
  IconArrowLeft,
  IconArrowRight,
  IconBrain,
  IconCheck,
  IconCode,
  IconFileUpload,
  IconInfoCircle,
  IconServer,
  IconSparkles,
  IconTestPipe,
} from '@tabler/icons-react';
import { notifications } from '@mantine/notifications';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { api, CandidateProfileUpdate } from '../api/api';
import { toApiError } from '../api/http';
import { keys, useDictionaries, useProfile } from '../hooks/queries';
import { useExtras } from '../hooks/useExtras';
import { PageHeader } from '../components/common/PageHeader';
import { extractPdfText, MAX_RESUME_BYTES, parseResumeText, recognizedCount, RecognizedResume } from '../utils/resumeParser';
import { gradeLabel, WORK_FORMAT_LABELS } from '../utils/labels';

const DIRECTION_INFO: Record<string, { icon: React.ElementType; text: string }> = {
  DEVELOPMENT: { icon: IconCode, text: 'Проектирование и создание веб-сервисов, распределённых систем и клиентских приложений.' },
  DATA_ML: { icon: IconBrain, text: 'Анализ данных, обучение моделей машинного обучения, инженерия данных.' },
  QA: { icon: IconTestPipe, text: 'Автоматизация тестирования, обеспечение качества и надёжности.' },
  INFRASTRUCTURE: { icon: IconServer, text: 'DevOps, SRE, облачная инфраструктура, контейнеризация и оркестрация.' },
};

const GRADE_ORDER = ['INTERN', 'JUNIOR', 'MIDDLE', 'SENIOR'];

interface FormState {
  first_name: string;
  last_name: string;
  phone: string;
  telegram: string;
  city: string;
  work_format: string;
  desired_salary_min: number | string;
  salary_type: 'NET' | 'GROSS';
  experience_years: number | string;
}

const EMPTY_FORM: FormState = {
  first_name: '',
  last_name: '',
  phone: '',
  telegram: '',
  city: '',
  work_format: 'REMOTE',
  desired_salary_min: '',
  salary_type: 'NET',
  experience_years: '',
};

import { usePageTitle } from '../hooks/usePageTitle';

export const CandidateOnboardingPage: React.FC = () => {
  usePageTitle('Анкета и резюме');
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { data: profile } = useProfile();
  const { data: dict } = useDictionaries();
  const [extras, setExtras] = useExtras();

  const [step, setStep] = useState(0);
  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  const [stack, setStack] = useState<string[]>([]);
  const [softSkills, setSoftSkills] = useState<string[]>([]);
  const [roles, setRoles] = useState<string[]>([]);
  const [about, setAbout] = useState('');
  const [directionId, setDirectionId] = useState<string | null>(null);
  const [specCode, setSpecCode] = useState<string>('BACKEND');
  const [gradeCode, setGradeCode] = useState<string>('MIDDLE');
  const [recognizing, setRecognizing] = useState(false);
  const [recognized, setRecognized] = useState<RecognizedResume | null>(null);
  const [resumeName, setResumeName] = useState<string | undefined>(extras.resume_file);
  const [skillQuery, setSkillQuery] = useState('');
  const initialised = useRef(false);

  // Подставляем данные профиля один раз, когда он загружен.
  useEffect(() => {
    if (initialised.current || !profile) return;
    initialised.current = true;
    setForm({
      first_name: profile.first_name ?? '',
      last_name: profile.last_name ?? '',
      phone: profile.phone ?? '',
      telegram: profile.telegram ?? '',
      city: profile.city ?? '',
      work_format: profile.work_format ?? 'REMOTE',
      desired_salary_min: profile.desired_salary_min ?? '',
      salary_type: profile.salary_type === 'GROSS' ? 'GROSS' : 'NET',
      experience_years: extras.experience_years ?? '',
    });
    setStack(extras.stack);
    setSoftSkills(extras.soft_skills);
    setRoles(extras.roles);
    setAbout(extras.about);
    if (profile.declared_grade) setGradeCode(profile.declared_grade);
    else if (profile.confirmed_grade) setGradeCode(profile.confirmed_grade);
  }, [profile, extras]);

  // Направление и специализация из справочника
  useEffect(() => {
    if (!dict || directionId) return;
    const wanted = (profile?.confirmed_specialization ?? 'BACKEND').toUpperCase();
    const spec = dict.specializations.find((s) => s.code === wanted) ?? dict.specializations[0];
    if (spec) {
      setSpecCode(spec.code);
      setDirectionId(spec.direction_id);
    }
  }, [dict, profile, directionId]);

  const { data: skillOptions = [] } = useQuery({
    queryKey: ['skills', skillQuery],
    queryFn: () => api.skills(skillQuery, 15),
    enabled: skillQuery.length >= 1,
    staleTime: 60_000,
  });

  const set = <K extends keyof FormState>(k: K, v: FormState[K]) => setForm((f) => ({ ...f, [k]: v }));

  const currentSpec = dict?.specializations.find((s) => s.code === specCode);
  const hasTest = currentSpec ? currentSpec.has_active_assessment === 1 : true;
  const specs = (dict?.specializations ?? []).filter((s) => !directionId || s.direction_id === directionId);

  const onFile = async (file: File | null) => {
    if (!file) return;
    if (file.type !== 'application/pdf' && !file.name.toLowerCase().endsWith('.pdf')) {
      notifications.show({ title: 'Неверный формат', message: 'Загрузите резюме в формате PDF.', color: 'red' });
      return;
    }
    if (file.size > MAX_RESUME_BYTES) {
      notifications.show({ title: 'Файл слишком большой', message: 'Максимальный размер — 8 МБ.', color: 'red' });
      return;
    }
    setRecognizing(true);
    try {
      const text = await extractPdfText(file);
      if (text.trim().length < 20) {
        notifications.show({
          title: 'Текст не найден',
          message: 'В файле нет текстового слоя (возможно, это скан). Заполните форму вручную.',
          color: 'orange',
        });
        return;
      }
      const r = parseResumeText(text);
      setRecognized(r);
      setResumeName(file.name);
      setExtras({
        resume_file: file.name,
        about: r.about_me ?? extras.about,
        experience_years: r.experience_years ?? extras.experience_years,
        stack: r.stack.length ? Array.from(new Set([...stack, ...r.stack])) : extras.stack,
        soft_skills: r.soft_skills.length ? Array.from(new Set([...softSkills, ...r.soft_skills])) : extras.soft_skills,
        roles: r.roles.length ? Array.from(new Set([...roles, ...r.roles])) : extras.roles,
      });
      setForm((f) => ({
        ...f,
        first_name: r.first_name ?? f.first_name,
        last_name: r.last_name ?? f.last_name,
        phone: r.phone ?? f.phone,
        telegram: r.telegram ?? f.telegram,
        city: r.city ?? f.city,
        work_format: r.work_format ?? f.work_format,
        desired_salary_min: r.desired_salary_min ?? f.desired_salary_min,
        experience_years: r.experience_years ?? f.experience_years,
      }));
      if (r.about_me) setAbout(r.about_me);
      if (r.stack.length) setStack(Array.from(new Set([...stack, ...r.stack])));
      if (r.soft_skills.length) setSoftSkills(Array.from(new Set([...softSkills, ...r.soft_skills])));
      if (r.roles.length) setRoles(Array.from(new Set([...roles, ...r.roles])));
      if (r.grade_hint) setGradeCode(r.grade_hint);
    } catch (err) {
      console.error('PDF parsing error:', err);
      notifications.show({ title: 'Не удалось прочитать файл', message: 'Проверьте, что PDF не повреждён и не защищён паролем.', color: 'red' });
    } finally {
      setRecognizing(false);
    }
  };

  const save = useMutation({
    mutationFn: async () => {
      const body: CandidateProfileUpdate = {
        first_name: form.first_name.trim() || null,
        last_name: form.last_name.trim() || null,
        phone: form.phone.trim() || null,
        telegram: form.telegram.trim() || null,
        city: form.city.trim() || null,
        work_format: form.work_format,
        desired_salary_min: form.desired_salary_min === '' ? null : Number(form.desired_salary_min),
        salary_type: form.salary_type,
        is_gross: form.salary_type === 'GROSS',
        // анкета хранится в профиле: её видит работодатель и PDF-профиль, стек участвует в подборе
        experience_years: form.experience_years === '' ? null : Number(form.experience_years),
        stack: stack.join(', '),
        soft_skills: softSkills.join(', '),
        roles: roles.join(', '),
        about_me: about.trim(),
      };
      return api.updateProfile(body);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: keys.profile });
    },
    onError: (e) => notifications.show({ title: 'Не удалось сохранить анкету', message: toApiError(e).message, color: 'red' }),
  });

  const finish = async () => {
    try {
      await save.mutateAsync();
    } catch {
      return;
    }
    if (hasTest) navigate(`/candidate/assessment?grade=${gradeCode}&spec=${specCode}`);
    else {
      notifications.show({
        title: 'Анкета сохранена',
        message: 'Для выбранной специализации тест пока недоступен. Выберите другое направление или вернитесь позже.',
        color: 'orange',
      });
      navigate('/candidate');
    }
  };

  const chooseSpec = (code: string) => setSpecCode(code);
  const chooseDirection = (id: string) => {
    setDirectionId(id);
    const first = dict?.specializations.find((s) => s.direction_id === id);
    if (first) chooseSpec(first.code);
  };

  const choiceProps = (selected: boolean, onSelect: () => void) => ({
    className: 'choice-card',
    'data-selected': selected,
    role: 'radio' as const,
    'aria-checked': selected,
    tabIndex: 0,
    onClick: onSelect,
    onKeyDown: (e: React.KeyboardEvent) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        onSelect();
      }
    },
  });

  const resumeValid = form.first_name.trim() && form.last_name.trim();

  return (
    <Container size="lg" p={0}>
      <Stack gap="lg">
        <PageHeader
          eyebrow="Кабинет кандидата"
          title="Анкета и резюме"
          description="Заполните профиль вручную или загрузите резюме в PDF — поля распознаются автоматически. Затем выберите специализацию и грейд, на который претендуете. Категорию присваивает тест, а не анкета."
        />

        <Paper withBorder p={{ base: 'md', sm: 'lg' }}>
          <Stepper active={step} onStepClick={setStep} color="fspPink" size="sm" mb="xl" allowNextStepsSelect={false} wrap>
            <Stepper.Step label="Резюме" />
            <Stepper.Step label="Специализация" />
            <Stepper.Step label="Технологии" />
            <Stepper.Step label="Грейд" />
          </Stepper>

          {step === 0 && (
            <Stack gap="md">
              <Card padding="md" style={{ background: 'var(--fsp-tint-violet)' }}>
                <Group justify="space-between" align="center" gap="md" wrap="wrap">
                  <Box maw={520}>
                    <Text fw={600}>Загрузить резюме (PDF)</Text>
                    <Text size="sm" c="dimmed">
                      Распознаём ФИО, контакты, город, опыт, стек и soft-skills прямо в браузере — файл не отправляется на сервер. Результат можно исправить.
                    </Text>
                    {resumeName && (
                      <Text size="xs" c="teal" fw={600} mt={4}>
                        Загружено: {resumeName}
                      </Text>
                    )}
                  </Box>
                  <FileButton onChange={onFile} accept="application/pdf">
                    {(props) => (
                      <Button {...props} variant="default" loading={recognizing} leftSection={recognizing ? <Loader size={14} /> : <IconFileUpload size={16} />}>
                        {resumeName ? 'Загрузить другой файл' : 'Выбрать файл'}
                      </Button>
                    )}
                  </FileButton>
                </Group>
              </Card>

              {recognized && (
                <Alert color="teal" variant="light" icon={<IconSparkles size={18} />} title={`Распознано полей: ${recognizedCount(recognized)}`}>
                  Проверьте значения ниже: автоматическое распознавание может ошибаться. Данные сохранятся в профиле на последнем шаге анкеты.
                </Alert>
              )}

              <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="md">
                <TextInput label="Имя" required value={form.first_name} onChange={(e) => set('first_name', e.currentTarget.value)} error={!form.first_name.trim() && step === 0 && recognized ? 'Укажите имя' : null} />
                <TextInput label="Фамилия" required value={form.last_name} onChange={(e) => set('last_name', e.currentTarget.value)} />
                <TextInput label="Телефон" placeholder="+7 (900) 000-00-00" value={form.phone} onChange={(e) => set('phone', e.currentTarget.value)} autoComplete="tel" />
                <TextInput label="Telegram" placeholder="@username" value={form.telegram} onChange={(e) => set('telegram', e.currentTarget.value)} />
                <TextInput label="Город" value={form.city} onChange={(e) => set('city', e.currentTarget.value)} autoComplete="address-level2" />
                <Select
                  label="Формат работы"
                  data={Object.entries(WORK_FORMAT_LABELS).map(([value, label]) => ({ value, label }))}
                  value={form.work_format}
                  onChange={(v) => set('work_format', v ?? 'REMOTE')}
                  allowDeselect={false}
                />
                <NumberInput label="Ожидаемая зарплата от, ₽" thousandSeparator=" " suffix=" ₽" min={0} step={10000} value={form.desired_salary_min} onChange={(v) => set('desired_salary_min', v)} />
                <Select
                  label="Зарплата указана"
                  data={[
                    { value: 'NET', label: 'На руки' },
                    { value: 'GROSS', label: 'До вычета НДФЛ' },
                  ]}
                  value={form.salary_type}
                  onChange={(v) => set('salary_type', v === 'GROSS' ? 'GROSS' : 'NET')}
                  allowDeselect={false}
                />
                <NumberInput label="Опыт работы, лет" min={0} max={50} decimalScale={1} step={0.5} value={form.experience_years} onChange={(v) => set('experience_years', v)} />
              </SimpleGrid>
              <TagsInput
                label="Роли и должности"
                placeholder="Например: Backend-разработчик"
                value={roles}
                onChange={setRoles}
                data={['Backend-разработчик', 'Frontend-разработчик', 'Fullstack-разработчик', 'Продуктовый дизайнер', 'UX/UI-дизайнер', 'Дизайнер', 'Data Scientist', 'ML-инженер', 'DevOps-инженер', 'QA-инженер', 'Тимлид', 'Архитектор']}
              />
              <TagsInput
                label="Soft-skills"
                placeholder="Например: работа в команде"
                value={softSkills}
                onChange={setSoftSkills}
                data={['Коммуникабельность', 'Работа в команде', 'Лидерство', 'Наставничество', 'Самообучаемость', 'Ответственность', 'Тайм-менеджмент', 'Аналитическое мышление', 'Дизайн-мышление']}
              />
              <Textarea label="О себе" description="Роли, проекты, чем гордитесь" value={about} onChange={(e) => setAbout(e.currentTarget.value)} minRows={3} autosize maxLength={2000} />
            </Stack>
          )}

          {step === 1 && (
            <Stack gap="lg">
              <Box>
                <Title order={2} size="h4" mb="sm">
                  Направление
                </Title>
                <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="md" role="radiogroup" aria-label="Направление">
                  {(dict?.directions ?? []).map((dir) => {
                    const info = DIRECTION_INFO[dir.code] ?? DIRECTION_INFO.DEVELOPMENT;
                    const sel = directionId === dir.id;
                    return (
                      <Card key={dir.id} padding="md" {...choiceProps(sel, () => chooseDirection(dir.id))}>
                        <Group justify="space-between" mb="xs">
                          <ThemeIcon variant="light" color="fspPurple" size="lg">
                            <info.icon size={20} />
                          </ThemeIcon>
                          {sel && (
                            <Badge variant="filled" color="fspPink" size="sm">
                              Выбрано
                            </Badge>
                          )}
                        </Group>
                        <Text fw={700} mb={2}>
                          {dir.name}
                        </Text>
                        <Text size="xs" c="dimmed">
                          {info.text}
                        </Text>
                      </Card>
                    );
                  })}
                </SimpleGrid>
              </Box>
              <Box>
                <Title order={2} size="h4" mb="sm">
                  Специализация
                </Title>
                <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="md" role="radiogroup" aria-label="Специализация">
                  {specs.map((spec) => {
                    const sel = specCode === spec.code;
                    const tested = spec.has_active_assessment === 1;
                    return (
                      <Card key={spec.id} padding="md" {...choiceProps(sel, () => chooseSpec(spec.code))}>
                        <Group justify="space-between" mb={4} wrap="wrap" gap="xs">
                          <Text fw={700} style={{ minWidth: 0, flex: 1 }}>{spec.name}</Text>
                          <Badge variant="light" color={tested ? 'teal' : 'gray'} size="sm" style={{ flexShrink: 0 }}>
                            {tested ? 'Есть тест' : 'Теста пока нет'}
                          </Badge>
                        </Group>
                        <Text size="xs" c="dimmed">
                          {tested ? 'Доступен банк параметризованных заданий и адаптивный тест.' : 'Анкета сохраняется, тест для этой специализации появится позже.'}
                        </Text>
                      </Card>
                    );
                  })}
                </SimpleGrid>
              </Box>
            </Stack>
          )}

          {step === 2 && (
            <Stack gap="md">
              <Box>
                <Title order={2} size="h4" mb={4}>
                  Технологии и инструменты
                </Title>
                <Text size="sm" c="dimmed">
                  Начните вводить название — подсказки приходят из справочника навыков платформы.
                </Text>
              </Box>
              <TagsInput
                label="Ваш стек"
                placeholder="Python, FastAPI, PostgreSQL…"
                value={stack}
                onChange={setStack}
                data={skillOptions.map((s) => s.name)}
                onSearchChange={setSkillQuery}
                maxTags={30}
              />
              <Alert variant="light" color="gray" icon={<IconInfoCircle size={18} />} p="sm">
                Стек сохраняется в профиле с пометкой «заявлено кандидатом»: работодатель его видит, в подборке такие навыки весят меньше подтверждённых тестом. Навыки из справочника учитываются при ранжировании.
              </Alert>
            </Stack>
          )}

          {step === 3 && (
            <Stack gap="md">
              <Box>
                <Title order={2} size="h4" mb={4}>
                  Самооценка грейда
                </Title>
                <Alert variant="light" color="gray" icon={<IconInfoCircle size={18} />} p="sm">
                  Выбранный грейд задаёт стартовую сложность адаптивного теста. Подтвердить его можно только прохождением теста.
                </Alert>
              </Box>
              <SimpleGrid cols={{ base: 1, md: 2 }} spacing="md" role="radiogroup" aria-label="Грейд">
                {(dict?.grades ?? [])
                  .slice()
                  .sort((a, b) => a.rank - b.rank)
                  .filter((g) => GRADE_ORDER.includes(g.code))
                  .map((g) => (
                    <Card key={g.id} padding="md" {...choiceProps(gradeCode === g.code, () => setGradeCode(g.code))}>
                      <Group justify="space-between" mb="xs">
                        <Text fw={700}>{gradeLabel(g.code)}</Text>
                        <Text size="xs" c="dimmed">
                          Уровень {g.rank} из 4
                        </Text>
                      </Group>
                      <List
                        spacing={4}
                        size="xs"
                        icon={
                          <ThemeIcon color="teal" variant="light" size={16} radius="xl">
                            <IconCheck size={10} />
                          </ThemeIcon>
                        }
                      >
                        {(g.behavioral_indicators ?? []).slice(0, 4).map((ind) => (
                          <List.Item key={ind}>{ind}</List.Item>
                        ))}
                      </List>
                    </Card>
                  ))}
              </SimpleGrid>
              {!hasTest && (
                <Alert variant="light" color="orange" p="sm">
                  Для специализации «{currentSpec?.name}» тест пока недоступен. Профиль будет сохранён со статусом «Грейд не подтверждён».
                </Alert>
              )}
            </Stack>
          )}

          <Group justify="space-between" mt="xl" pt="md" wrap="wrap" gap="sm" style={{ borderTop: '1px solid var(--fsp-border)' }}>
            <Button variant="default" disabled={step === 0} onClick={() => setStep((s) => Math.max(0, s - 1))} leftSection={<IconArrowLeft size={16} />}>
              Назад
            </Button>
            {step < 3 ? (
              <Button onClick={() => setStep((s) => Math.min(3, s + 1))} disabled={step === 0 && !resumeValid} rightSection={<IconArrowRight size={16} />}>
                Далее
              </Button>
            ) : (
              <Button loading={save.isPending} onClick={finish} rightSection={<IconArrowRight size={16} />}>
                {hasTest ? 'Сохранить и перейти к тесту' : 'Сохранить анкету'}
              </Button>
            )}
          </Group>
        </Paper>
      </Stack>
    </Container>
  );
};
