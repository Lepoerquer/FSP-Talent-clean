import React from 'react';
import { Alert, Badge, Box, Group, Paper, Skeleton, Table, Text, Title } from '@mantine/core';
import { IconInfoCircle } from '@tabler/icons-react';
import { useGradeStatus } from '../../hooks/queries';
import { ScrollTable } from '../common/ScrollTable';
import { formatDateTime, formatDecimal, formatTheta } from '../../utils/format';
import { gradeLabel, RECOMMENDATION_LABELS, specLabel } from '../../utils/labels';

const KIND_LABELS: Record<string, string> = {
  INITIAL: 'Первичное определение',
  CHANGE: 'Смена грейда',
  FOLLOW_UP: 'Тест на соседний грейд',
  REGULAR: 'Плановая пересдача',
};
const STATUS_LABELS: Record<string, string> = { COMPLETED: 'Завершён', IN_PROGRESS: 'Не завершён', ABANDONED: 'Прерван' };
const REASON_LABELS: Record<string, string> = { ASSESSMENT: 'По результату теста', INITIAL: 'Первичное присвоение', MANUAL: 'Решение модератора' };

/** История опроса и тестирования, смены грейда (п. 2.1 ТЗ, «Категория и грейд»). */
export const AssessmentHistory: React.FC = () => {
  const { data: grade, isLoading } = useGradeStatus();

  if (isLoading) return <Skeleton h={160} />;
  const attempts = grade?.attempts ?? [];
  const history = grade?.grade_history ?? [];

  return (
    <Paper withBorder p="lg">
      <Title order={2} size="h3" mb={4}>
        История тестирования
      </Title>
      <Text size="sm" c="dimmed" mb="md">
        Все попытки и смены грейда. Неудачная попытка на более высокий грейд не отменяет текущую категорию.
      </Text>

      {attempts.length === 0 && history.length === 0 ? (
        <Alert variant="light" color="gray" icon={<IconInfoCircle size={18} />}>
          Попыток пока не было. После первого теста здесь появятся результат и дата.
        </Alert>
      ) : (
        <>
          {attempts.length > 0 && (
            <ScrollTable minWidth={720} label="Попытки тестирования">
              <Table verticalSpacing="xs" highlightOnHover>
                <Table.Thead>
                  <Table.Tr>
                    <Table.Th>Дата</Table.Th>
                    <Table.Th>Тип</Table.Th>
                    <Table.Th>Специализация · грейд</Table.Th>
                    <Table.Th>Заданий</Table.Th>
                    <Table.Th>Оценка θ</Table.Th>
                    <Table.Th>Результат</Table.Th>
                  </Table.Tr>
                </Table.Thead>
                <Table.Tbody>
                  {attempts.map((a) => (
                    <Table.Tr key={a.session_id}>
                      <Table.Td>{formatDateTime(a.started_at)}</Table.Td>
                      <Table.Td>{KIND_LABELS[a.kind] ?? a.kind}</Table.Td>
                      <Table.Td>
                        {specLabel(a.specialization)} · {gradeLabel(a.target_grade)}
                      </Table.Td>
                      <Table.Td>{a.items_count}</Table.Td>
                      <Table.Td>
                        {a.theta != null ? (
                          <>
                            {formatTheta(a.theta)}
                            {a.se != null && (
                              <Text span size="xs" c="dimmed">
                                {' '}
                                ±{formatDecimal(a.se)}
                              </Text>
                            )}
                          </>
                        ) : (
                          '—'
                        )}
                      </Table.Td>
                      <Table.Td>
                        {a.status !== 'COMPLETED' ? (
                          <Badge variant="light" color="gray">
                            {STATUS_LABELS[a.status] ?? a.status}
                          </Badge>
                        ) : (
                          <Group gap={6} wrap="nowrap">
                            <Badge variant="light" color={a.is_confirmed ? 'teal' : 'orange'}>
                              {a.is_confirmed ? 'Подтверждён' : 'Не подтверждён'}
                            </Badge>
                            {a.recommendation && !a.is_confirmed && (
                              <Text size="xs" c="dimmed">
                                {RECOMMENDATION_LABELS[a.recommendation] ?? ''}
                              </Text>
                            )}
                          </Group>
                        )}
                      </Table.Td>
                    </Table.Tr>
                  ))}
                </Table.Tbody>
              </Table>
            </ScrollTable>
          )}

          {history.length > 0 && (
            <Box mt="lg">
              <Text className="section-eyebrow" mb={6}>
                Смены грейда
              </Text>
              <ScrollTable minWidth={520} label="Смены грейда">
                <Table verticalSpacing="xs">
                  <Table.Thead>
                    <Table.Tr>
                      <Table.Th>Дата</Table.Th>
                      <Table.Th>Специализация</Table.Th>
                      <Table.Th>Было</Table.Th>
                      <Table.Th>Стало</Table.Th>
                      <Table.Th>Основание</Table.Th>
                    </Table.Tr>
                  </Table.Thead>
                  <Table.Tbody>
                    {history.map((h) => (
                      <Table.Tr key={`${h.changed_at}-${h.new_grade}`}>
                        <Table.Td>{formatDateTime(h.changed_at)}</Table.Td>
                        <Table.Td>{specLabel(h.specialization)}</Table.Td>
                        <Table.Td>{h.previous_grade ? gradeLabel(h.previous_grade) : '—'}</Table.Td>
                        <Table.Td fw={600}>{gradeLabel(h.new_grade)}</Table.Td>
                        <Table.Td>{REASON_LABELS[h.reason] ?? h.reason}</Table.Td>
                      </Table.Tr>
                    ))}
                  </Table.Tbody>
                </Table>
              </ScrollTable>
            </Box>
          )}
        </>
      )}
    </Paper>
  );
};
