import React, { useState } from 'react';
import { Badge, Box, Button, Card, Collapse, Group, List, Progress, SimpleGrid, Stack, Text, ThemeIcon, Title, Tooltip } from '@mantine/core';
import { IconBrain, IconCheck, IconChevronDown, IconChevronUp, IconLock, IconSend, IconSparkles, IconTrophy, IconChartDots } from '@tabler/icons-react';
import { notifications } from '@mantine/notifications';
import { api, CandidateCard as CardData, ScoreComponents } from '../../api/api';
import { CompetenceRadarChart, RadarDimension } from '../common/CompetenceRadarChart';
import { FspStarIcon } from '../common/FspStarIcon';
import { SalaryRange } from '../common/SalaryRange';
import { InvitationStatusBadge } from '../common/StatusBadge';
import { candidateDisplayName, formatDecimal } from '../../utils/format';
import { gradeLabel, SCORE_COMPONENT_LABELS, workFormatLabel } from '../../utils/labels';

const DEFAULT_WEIGHTS: Record<string, number> = { C: 0.3, S: 0.25, E: 0.1, T: 0.25, F: 0.07, A: 0.03 };

interface CandidateCardProps {
  card: CardData;
  rank?: number;
  /** Итоговое соответствие запросу, 0–100: показывается только в подборке по потребности. */
  scorePercent?: number;
  reasons?: string[];
  components?: ScoreComponents;
  weights?: Record<string, number>;
  fspBadge?: string;
  needId?: string;
  /** Уже отправленное приглашение этому кандидату (новое не отправляется, пока прежнее не закрыто). */
  invitation?: { status: string; expired?: boolean };
  /** Предпросмотр для самого кандидата (настройки приватности): без кнопки приглашения. */
  preview?: boolean;
  onInvite: (card: CardData) => void;
}

/** Карточка кандидата для работодателя. Контакты скрыты до принятия приглашения. */
export const CandidateCard: React.FC<CandidateCardProps> = ({ card: c, rank, scorePercent, reasons, components, weights, fspBadge, needId, invitation, preview, onInvite }) => {
  const [open, setOpen] = useState(false);
  const [pitch, setPitch] = useState<string | null>(null);
  const [pitchLoading, setPitchLoading] = useState(false);
  const [pitchOpen, setPitchOpen] = useState(false);

  const [questions, setQuestions] = useState<Array<{ topic: string; question: string; expected_answer: string }> | null>(null);
  const [questionsLoading, setQuestionsLoading] = useState(false);
  const [questionsOpen, setQuestionsOpen] = useState(false);

  const [radarOpen, setRadarOpen] = useState(false);

  const confirmed = c.is_grade_confirmed ?? Boolean(c.confirmed_grade);
  const name = c.full_name || 'Неизвестный кандидат';

  const candidateRadarDimensions: RadarDimension[] = [
    {
      key: 'test',
      label: 'Тест ФСП (Hard skills)',
      value: components?.T !== undefined
        ? Math.round((components.T ?? 0) * 100)
        : (c.category_percentile != null
          ? c.category_percentile
          : (c.confirmed_grade === 'SENIOR' ? 85 : c.confirmed_grade === 'MIDDLE' ? 65 : 45)),
      targetValue: 80,
    },
    {
      key: 'stack',
      label: 'Стек технологий',
      value: components?.S !== undefined
        ? Math.round((components.S ?? 0) * 100)
        : (c.confirmed_grade === 'SENIOR' ? 85 : c.confirmed_grade === 'MIDDLE' ? 70 : 55),
      targetValue: 75,
    },
    {
      key: 'exp',
      label: 'Опыт и грейд',
      value: components?.E !== undefined
        ? Math.round((components.E ?? 0) * 100)
        : (c.confirmed_grade === 'SENIOR' ? 90 : c.confirmed_grade === 'MIDDLE' ? 70 : 50),
      targetValue: 70,
    },
    {
      key: 'fsp',
      label: 'Олимпиадный опыт ФСП',
      value: components?.F !== undefined
        ? Math.round((components.F ?? 0) * 100)
        : (c.is_fsp_verified
            ? Math.min(100, Math.max(35, Math.round(
                (c.fsp_score ?? 0) > 0 ? (c.fsp_score ?? 0) * 100 : 35
              )))
            : 20),
      targetValue: 60,
    },
    {
      key: 'verified',
      label: 'Подтверждённость 152-ФЗ',
      value: confirmed ? 95 : 40,
      targetValue: 85,
    },
  ];

  const handleFetchPitch = async () => {
    if (pitch) {
      setPitchOpen((v) => !v);
      return;
    }
    setPitchLoading(true);
    setPitchOpen(true);
    try {
      const res = await api.aiPitch({
        candidate_id: c.id,
        need_id: needId || null,
        score_percent: scorePercent ?? 85,
      });
      setPitch(res.pitch);
    } catch {
      notifications.show({
        title: 'Ошибка генерации AI-питча',
        message: 'Не удалось получить ответ GigaChat. Попробуйте еще раз.',
        color: 'red',
      });
    } finally {
      setPitchLoading(false);
    }
  };

  const handleFetchQuestions = async () => {
    if (questions) {
      setQuestionsOpen((v) => !v);
      return;
    }
    setQuestionsLoading(true);
    setQuestionsOpen(true);
    try {
      const res = await api.aiInterviewQuestions({
        specialization: c.confirmed_specialization || 'BACKEND',
        grade: c.confirmed_grade || 'MIDDLE',
        skills: ['Python', 'SQL', 'FastAPI', 'PostgreSQL', 'Docker'],
        count: 3,
      });
      setQuestions(res.questions);
    } catch {
      notifications.show({
        title: 'Ошибка генерации вопросов',
        message: 'Не удалось сгенерировать вопросы от GigaChat.',
        color: 'red',
      });
    } finally {
      setQuestionsLoading(false);
    }
  };

  return (
    <Card
      padding="md"
      style={{ borderLeft: `4px solid ${confirmed ? (rank === 1 ? 'var(--fsp-primary)' : 'var(--fsp-border-strong)') : 'var(--mantine-color-orange-5)'}` }}
    >
      <div className="split-grid">
        <Box className="span-8">
          <Group justify="space-between" align="flex-start" gap="xs" mb={6} wrap="wrap">
            <Group gap="xs" align="center" style={{ minWidth: 0, flex: 1 }}>
              {rank !== undefined && (
                <Badge variant="filled" color="dark" size="lg" radius="sm" aria-label={`Место ${rank}`} style={{ flexShrink: 0 }}>
                  {rank}
                </Badge>
              )}
              <Title order={3} size="h4" style={{ minWidth: 0 }}>{name}</Title>
            </Group>
            {scorePercent !== undefined && (
              <Badge size="lg" variant="light" color={scorePercent >= 75 ? 'teal' : 'orange'} aria-label={`Соответствие запросу ${scorePercent} из 100`} style={{ flexShrink: 0 }}>
                Соответствие {scorePercent}
              </Badge>
            )}
          </Group>

          <Group gap="xs" mb="xs">
            <Badge variant="light" color="fspPink">
              {c.confirmed_category ?? 'Категория не присвоена'}
            </Badge>
            {confirmed ? (
              <Badge variant="light" color="teal" leftSection={<IconCheck size={12} />}>
                Грейд подтверждён
              </Badge>
            ) : (
              <Tooltip label="Штраф 0.6 на категорию" withArrow>
                <Badge variant="filled" color="orange" style={{ cursor: 'help' }}>
                  Грейд не подтверждён
                </Badge>
              </Tooltip>
            )}
            {c.category_percentile != null && confirmed && (
              <Badge variant="light" color="gray">
                Тест: {c.category_percentile}-й процентиль
              </Badge>
            )}
            {c.is_fsp_verified ? (
              <Badge variant="light" color="fspBlue" leftSection={<FspStarIcon size={13} />}>
                {fspBadge ?? 'ФСП'} · {formatDecimal(c.fsp_score ?? 0)}
              </Badge>
            ) : (
              <Badge variant="outline" color="gray">
                Без истории ФСП
              </Badge>
            )}
          </Group>

          <Text size="xs" c="dimmed" mb={reasons?.length ? 'sm' : 0}>
            {[c.city, workFormatLabel(c.work_format), confirmed && c.confirmed_grade ? gradeLabel(c.confirmed_grade) : null].filter((v) => v && v !== '—').join(' · ')}
          </Text>

          {reasons && reasons.length > 0 && (
            <Box p="sm" style={{ background: 'var(--fsp-tint-neutral)', borderRadius: 6 }}>
              <Text className="section-eyebrow" mb={6}>
                Почему в подборке
              </Text>
              <List
                spacing={4}
                size="xs"
                icon={
                  <ThemeIcon size={16} radius="xl" variant="light" color={confirmed ? 'teal' : 'orange'}>
                    <IconCheck size={10} />
                  </ThemeIcon>
                }
              >
                {reasons.map((r) => (
                  <List.Item key={r}>{r}</List.Item>
                ))}
              </List>

              {components && (
                <>
                  <Button
                    variant="subtle"
                    size="compact-xs"
                    mt={6}
                    onClick={() => setOpen((v) => !v)}
                    rightSection={open ? <IconChevronUp size={12} /> : <IconChevronDown size={12} />}
                    aria-expanded={open}
                  >
                    {open ? 'Скрыть расчёт' : 'Показать расчёт'}
                  </Button>
                  <Collapse in={open}>
                    <SimpleGrid cols={{ base: 2, sm: 3 }} spacing="xs" mt={6}>
                      {(Object.keys(SCORE_COMPONENT_LABELS) as Array<keyof ScoreComponents>).map((k) => (
                        <Box key={k}>
                          <Group justify="space-between" gap={4}>
                            <Text size="xs" c="dimmed">
                              {SCORE_COMPONENT_LABELS[k]} ({k})
                            </Text>
                            <Text size="xs" fw={600}>
                              {Math.round((components[k] ?? 0) * 100)}%
                            </Text>
                          </Group>
                          <Progress value={(components[k] ?? 0) * 100} size="xs" color="fspPurple" aria-label={SCORE_COMPONENT_LABELS[k]} />
                          <Text size="xs" c="dimmed">
                            вес {Math.round(((weights ?? DEFAULT_WEIGHTS)[k] ?? 0) * 100)}%
                          </Text>
                        </Box>
                      ))}
                    </SimpleGrid>
                  </Collapse>
                </>
              )}

              <Group gap="xs" mt="xs" wrap="wrap">
                <Button
                  size="compact-xs"
                  variant="light"
                  color="fspPurple"
                  loading={pitchLoading}
                  leftSection={<IconSparkles size={12} />}
                  onClick={handleFetchPitch}
                  style={{ flex: '0 1 auto' }}
                >
                  {pitchOpen && pitch ? 'Скрыть AI-резюме' : '✨ AI-питч GigaChat'}
                </Button>
                <Button
                  size="compact-xs"
                  variant="subtle"
                  color="blue"
                  loading={questionsLoading}
                  leftSection={<IconBrain size={12} />}
                  onClick={handleFetchQuestions}
                  style={{ flex: '0 1 auto' }}
                >
                  {questionsOpen && questions ? 'Скрыть вопросы' : '🎯 Вопросы к интервью'}
                </Button>
                <Button
                  size="compact-xs"
                  variant="subtle"
                  color="teal"
                  leftSection={<IconChartDots size={12} />}
                  onClick={() => setRadarOpen((v) => !v)}
                  style={{ flex: '0 1 auto' }}
                >
                  {radarOpen ? 'Скрыть радар' : '📊 Радар компетенций'}
                </Button>
              </Group>

              <Collapse in={pitchOpen}>
                <Box
                  mt="xs"
                  p="xs"
                  style={{
                    background: 'rgba(121, 80, 242, 0.07)',
                    border: '1px solid rgba(121, 80, 242, 0.25)',
                    borderRadius: 6,
                  }}
                >
                  <Group justify="space-between" mb={4}>
                    <Group gap="xs">
                      <ThemeIcon size={18} radius="xl" color="fspPurple" variant="light">
                        <IconSparkles size={10} />
                      </ThemeIcon>
                      <Text size="xs" fw={600} c="fspPurple">
                        AI-резюме GigaChat (Сбер 152-ФЗ) для рекрутера:
                      </Text>
                    </Group>
                    <Badge size="xs" variant="outline" color="fspPurple">GigaChat</Badge>
                  </Group>
                  {pitchLoading ? (
                    <Text size="xs" c="dimmed" fs="italic">Генерация ответа нейросетью...</Text>
                  ) : (
                    <Text size="xs" style={{ lineHeight: 1.4, color: 'inherit' }}>
                      {pitch}
                    </Text>
                  )}
                </Box>
              </Collapse>

              <Collapse in={questionsOpen}>
                <Box
                  mt="xs"
                  p="xs"
                  style={{
                    background: 'rgba(34, 139, 230, 0.07)',
                    border: '1px solid rgba(34, 139, 230, 0.25)',
                    borderRadius: 6,
                  }}
                >
                  <Group justify="space-between" mb="xs">
                    <Group gap="xs">
                      <ThemeIcon size={18} radius="xl" color="blue" variant="light">
                        <IconBrain size={10} />
                      </ThemeIcon>
                      <Text size="xs" fw={600} c="blue">
                        Практические вопросы для технического собеседования:
                      </Text>
                    </Group>
                    <Badge size="xs" variant="outline" color="blue">GigaChat</Badge>
                  </Group>
                  {questionsLoading ? (
                    <Text size="xs" c="dimmed" fs="italic">Формирование вопросов под стек соискателя...</Text>
                  ) : questions && questions.length > 0 ? (
                    <Stack gap="xs">
                      {questions.map((q, qIdx) => (
                        <Box key={qIdx} p="xs" style={{ background: 'var(--fsp-card-bg)', borderRadius: 6, border: '1px solid var(--fsp-border)' }}>
                          <Text size="xs" fw={600} c="dimmed">{qIdx + 1}. Тема: {q.topic}</Text>
                          <Text size="xs" fw={500} mt={2}>{q.question}</Text>
                          <Text size="xs" c="dimmed" mt={4}>
                            💡 <b>Критерии ответа:</b> {q.expected_answer}
                          </Text>
                        </Box>
                      ))}
                    </Stack>
                  ) : null}
                </Box>
              </Collapse>
              <Collapse in={radarOpen}>
                <Box
                  mt="xs"
                  p="xs"
                  style={{
                    background: 'var(--fsp-card-bg)',
                    border: '1px solid var(--fsp-border)',
                    borderRadius: 6,
                  }}
                >
                  <Group justify="space-between" mb="xs">
                    <Group gap="xs">
                      <ThemeIcon size={18} radius="xl" color="teal" variant="light">
                        <IconChartDots size={10} />
                      </ThemeIcon>
                      <Text size="xs" fw={600} c="teal">
                        Многомерный радар компетенций ФСП:
                      </Text>
                    </Group>
                    <Badge size="xs" variant="outline" color="teal">Соответствие требованиям</Badge>
                  </Group>
                  <Box style={{ display: 'flex', justifyContent: 'center' }}>
                    <CompetenceRadarChart
                      dimensions={candidateRadarDimensions}
                      size={280}
                      candidateLabel="Кандидат"
                      targetLabel="Требования"
                    />
                  </Box>
                </Box>
              </Collapse>
            </Box>
          )}

          {(!reasons || reasons.length === 0) && (
            <Box mt="xs">
              <Button
                size="compact-xs"
                variant="subtle"
                color="teal"
                leftSection={<IconChartDots size={12} />}
                onClick={() => setRadarOpen((v) => !v)}
              >
                {radarOpen ? 'Скрыть радар' : '📊 Радар компетенций ФСП'}
              </Button>
              <Collapse in={radarOpen}>
                <Box
                  mt="xs"
                  p="xs"
                  style={{
                    background: 'var(--fsp-card-bg)',
                    border: '1px solid var(--fsp-border)',
                    borderRadius: 6,
                  }}
                >
                  <Group justify="space-between" mb="xs">
                    <Group gap="xs">
                      <ThemeIcon size={18} radius="xl" color="teal" variant="light">
                        <IconChartDots size={10} />
                      </ThemeIcon>
                      <Text size="xs" fw={600} c="teal">
                        Многомерный радар компетенций ФСП:
                      </Text>
                    </Group>
                    <Badge size="xs" variant="outline" color="teal">Профиль кандидата</Badge>
                  </Group>
                  <Box style={{ display: 'flex', justifyContent: 'center' }}>
                    <CompetenceRadarChart
                      dimensions={candidateRadarDimensions}
                      size={280}
                      candidateLabel="Кандидат"
                      targetLabel="Эталон"
                    />
                  </Box>
                </Box>
              </Collapse>
            </Box>
          )}
        </Box>

        <Box className="span-4">
          <Box style={{ display: 'flex', flexDirection: 'column', gap: 12, height: '100%', justifyContent: 'space-between' }}>
            <Box>
              <Text size="xs" c="dimmed" mb={2}>
                Ожидания кандидата
              </Text>
              {c.desired_salary_min ? (
                <SalaryRange from={c.desired_salary_min} prefix="от " type={c.salary_type} />
              ) : (
                <Text size="sm" c="dimmed">
                  не указаны
                </Text>
              )}
              <Group gap={4} mt={8} wrap="nowrap" align="flex-start">
                <IconLock size={12} color="var(--fsp-text-muted)" style={{ marginTop: 2, flexShrink: 0 }} />
                <Text size="xs" c="dimmed">
                  Контакты откроются после принятия приглашения
                </Text>
              </Group>
            </Box>
            {preview ? (
              <Text size="xs" c="dimmed">
                Так карточка выглядит для работодателя в подборке и поиске.
              </Text>
            ) : invitation ? (
              <Stack gap={6} align="stretch">
                <InvitationStatusBadge status={invitation.status} expired={invitation.expired} />
                <Button variant="default" leftSection={<IconSend size={16} />} disabled fullWidth>
                  Уже приглашён
                </Button>
              </Stack>
            ) : (
              <Button leftSection={<IconSend size={16} />} onClick={() => onInvite(c)} fullWidth>
                Пригласить
              </Button>
            )}
          </Box>
        </Box>
      </div>
    </Card>
  );
};
