import React from 'react';
import { Alert, Badge, Button, Card, Container, Group, Skeleton, Stack, Text } from '@mantine/core';
import { notifications } from '@mantine/notifications';
import { IconBriefcase, IconBuildingSkyscraper, IconCheck, IconInfoCircle, IconShieldCheck } from '@tabler/icons-react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '../api/api';
import { toApiError } from '../api/http';
import { keys, useCandidateInvitations } from '../hooks/queries';
import { usePageTitle } from '../hooks/usePageTitle';
import { PageHeader } from '../components/common/PageHeader';
import { QueryError } from '../components/common/QueryError';
import { SalaryRange } from '../components/common/SalaryRange';
import { gradeLabel, specLabel, workFormatLabel } from '../utils/labels';

/** Открытые вакансии и самостоятельный отклик (дополнительный сценарий п. 2.1 ТЗ). */
export const CandidateVacanciesPage: React.FC = () => {
  usePageTitle('Вакансии');
  const queryClient = useQueryClient();
  const { data: vacancies = [], isLoading, isError, error, refetch } = useQuery({ queryKey: ['vacancies'], queryFn: () => api.needs() });
  const { data: invitations = [] } = useCandidateInvitations();

  // Отклик или приглашение по вакансии уже есть: повторно откликнуться нельзя, статус виден в «Приглашениях»
  const answered = new Map(invitations.filter((i) => i.need_id).map((i) => [i.need_id as string, i.status]));

  const apply = useMutation({
    mutationFn: (id: string) => api.applyToNeed(id),
    onSuccess: (res) => {
      notifications.show({ title: 'Отклик отправлен', message: res.message, color: 'teal', icon: <IconCheck size={18} /> });
      queryClient.invalidateQueries({ queryKey: keys.candidateInvitations });
    },
    onError: (e) => notifications.show({ title: 'Не удалось откликнуться', message: toApiError(e).message, color: 'red' }),
  });

  return (
    <Container size="lg" p={0}>
      <Stack gap="lg">
        <PageHeader
          eyebrow="Кабинет кандидата"
          title="Открытые вакансии"
          description="Основной сценарий — приглашения от работодателей по вашей подтверждённой категории. Здесь можно проявить инициативу и откликнуться самому: компания сразу увидит ваш профиль и контакты."
        />

        {isLoading ? (
          <Stack gap="sm">
            <Skeleton h={140} />
            <Skeleton h={140} />
          </Stack>
        ) : isError ? (
          <QueryError error={error} onRetry={() => refetch()} title="Не удалось загрузить вакансии" />
        ) : vacancies.length === 0 ? (
          <Alert variant="light" color="gray" icon={<IconInfoCircle size={18} />} title="Открытых вакансий пока нет">
            Пройдите тест и заполните профиль: работодатели находят кандидатов по подтверждённой категории и приглашают сами.
          </Alert>
        ) : (
          <Stack gap="md">
            {vacancies.map((v) => {
              const status = answered.get(v.id);
              return (
                <Card key={v.id} withBorder padding="md">
                  <Group justify="space-between" align="flex-start" mb={6} wrap="wrap" gap="xs">
                    <Text fw={700} size="lg" style={{ minWidth: 0, flex: 1 }}>
                      {v.title}
                    </Text>
                    <Badge variant="light" color="fspPurple" style={{ flexShrink: 0 }}>
                      {workFormatLabel(v.work_format)}
                    </Badge>
                  </Group>
                  <Group gap="xs" mb="sm">
                    <IconBuildingSkyscraper size={16} color="var(--fsp-text-muted)" />
                    <Text size="sm" c="dimmed">
                      {v.company_name ?? 'Компания'}
                    </Text>
                    {v.company_is_verified && (
                      <Badge size="xs" variant="light" color="teal" leftSection={<IconShieldCheck size={11} />}>
                        ИНН проверен
                      </Badge>
                    )}
                    <Text size="sm" c="dimmed">
                      · {specLabel(v.target_specialization)} · {gradeLabel(v.target_grade)}
                    </Text>
                  </Group>
                  {v.salary_budget_min && v.salary_budget_max ? (
                    <SalaryRange from={v.salary_budget_min} to={v.salary_budget_max} type={v.salary_type} />
                  ) : v.salary_budget_min || v.salary_budget_max ? (
                    <SalaryRange
                      from={(v.salary_budget_min || v.salary_budget_max) as number}
                      prefix={v.salary_budget_min ? 'от ' : 'до '}
                      type={v.salary_type}
                    />
                  ) : (
                    <Text size="sm" c="dimmed">
                      Зарплата не указана
                    </Text>
                  )}
                  {(v.required_skills ?? []).length > 0 && (
                    <Group gap="xs" mt="sm">
                      {(v.required_skills ?? []).map((s) => (
                        <Badge key={s} variant="light" color="gray">
                          {s}
                        </Badge>
                      ))}
                    </Group>
                  )}
                  <Group justify="flex-end" mt="md">
                    {status ? (
                      <Badge color="teal" variant="light" size="lg" leftSection={<IconCheck size={14} />}>
                        {status === 'APPLIED' ? 'Вы откликнулись' : 'Есть приглашение по вакансии'}
                      </Badge>
                    ) : (
                      <Button
                        leftSection={<IconBriefcase size={16} />}
                        loading={apply.isPending && apply.variables === v.id}
                        onClick={() => apply.mutate(v.id)}
                      >
                        Откликнуться
                      </Button>
                    )}
                  </Group>
                </Card>
              );
            })}
          </Stack>
        )}
      </Stack>
    </Container>
  );
};
