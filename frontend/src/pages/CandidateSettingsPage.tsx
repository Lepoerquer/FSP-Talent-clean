import React from 'react';
import { Alert, Badge, Box, Container, Group, List, Paper, SegmentedControl, Select, SimpleGrid, Skeleton, Stack, Switch, Table, Text, ThemeIcon, Title, useMantineColorScheme } from '@mantine/core';
import { IconAlertTriangle, IconCheck, IconDeviceDesktop, IconEye, IconLock, IconMoon, IconSun } from '@tabler/icons-react';
import { notifications } from '@mantine/notifications';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { api, ConsentType } from '../api/api';
import { toApiError } from '../api/http';
import { fullName, keys, useConsents, useProfile } from '../hooks/queries';
import { PageHeader } from '../components/common/PageHeader';
import { CandidateCard } from '../components/employer/CandidateCard';
import { ScrollTable } from '../components/common/ScrollTable';
import { formatDateTime } from '../utils/format';
import { PROFILE_STATUS_LABELS } from '../utils/labels';

const CONSENT_TEXT: Record<ConsentType, { title: string; text: string }> = {
  PERSONAL_DATA: {
    title: 'Обработка персональных данных',
    text: 'Необходима для работы аккаунта, прохождения тестов и хранения подтверждённого грейда. Без этого согласия пользоваться платформой нельзя.',
  },
  PROFILE_DISTRIBUTION: {
    title: 'Распространение данных профиля работодателям',
    text: 'Работодатели видят категорию, результаты теста, достижения ФСП, город и формат работы. Контакты передаются только компаниям, чьи приглашения вы приняли.',
  },
};

import { usePageTitle } from '../hooks/usePageTitle';

export const CandidateSettingsPage: React.FC = () => {
  usePageTitle('Приватность и согласия');
  const queryClient = useQueryClient();
  const { data: profile } = useProfile();
  const { data: consents, isLoading } = useConsents();

  const toggle = useMutation({
    mutationFn: ({ type, on }: { type: ConsentType; on: boolean }) => (on ? api.giveConsent(type) : api.revokeConsent(type)),
    onSuccess: (_d, { on }) => {
      queryClient.invalidateQueries({ queryKey: keys.consents });
      notifications.show({
        title: on ? 'Согласие дано' : 'Согласие отозвано',
        message: 'Изменение зафиксировано в журнале согласий с отметкой времени.',
        color: on ? 'teal' : 'gray',
        icon: <IconCheck size={18} />,
      });
    },
    onError: (e) => notifications.show({ title: 'Не удалось изменить согласие', message: toApiError(e).message, color: 'red' }),
  });

  const setStatus = useMutation({
    mutationFn: (status: string) => api.updateProfile({ status }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: keys.profile });
      notifications.show({ title: 'Статус обновлён', message: 'Настройка видимости сохранена.', color: 'teal', icon: <IconCheck size={18} /> });
    },
    onError: (e) => notifications.show({ title: 'Не удалось сохранить', message: toApiError(e).message, color: 'red' }),
  });

  const { colorScheme, setColorScheme } = useMantineColorScheme();

  const active = (type: ConsentType) => (type === 'PERSONAL_DATA' ? consents?.personal_data_active : consents?.profile_distribution_active) ?? false;
  const hidden = Boolean(consents && profile) && (!consents!.personal_data_active || !consents!.profile_distribution_active || profile!.status === 'HIDDEN');

  return (
    <Container size="lg" p={0}>
      <Stack gap="lg">
        <PageHeader
          eyebrow="Кабинет кандидата"
          title="Настройки интерфейса и приватность"
          description="Управление темой оформления по брендбуку ФСП, настройка видимости профиля и управление согласиями на обработку персональных данных."
        />

        <Paper withBorder p="lg">
          <Title order={2} size="h4" mb={4}>
            Тема оформления интерфейса
          </Title>
          <Text size="sm" c="dimmed" mb="md">
            Переключение между светлой и тёмной темой платформы. Обе палитры строго выверены по официальному брендбуку Федерации спортивного программирования.
          </Text>
          <SegmentedControl
            value={colorScheme}
            onChange={(val) => setColorScheme(val as 'light' | 'dark' | 'auto')}
            data={[
              {
                value: 'light',
                label: (
                  <Group gap={6} justify="center" wrap="nowrap" py={2}>
                    <IconSun size={16} />
                    <Text size="sm" fw={600}>Светлая тема</Text>
                  </Group>
                ),
              },
              {
                value: 'dark',
                label: (
                  <Group gap={6} justify="center" wrap="nowrap" py={2}>
                    <IconMoon size={16} />
                    <Text size="sm" fw={600}>Тёмная тема (ФСП)</Text>
                  </Group>
                ),
              },
              {
                value: 'auto',
                label: (
                  <Group gap={6} justify="center" wrap="nowrap" py={2}>
                    <IconDeviceDesktop size={16} />
                    <Text size="sm" fw={600}>Системная</Text>
                  </Group>
                ),
              },
            ]}
            maw={520}
          />
        </Paper>

        <Paper withBorder p="lg">
          <Title order={2} size="h4" mb={4}>
            Согласия на обработку персональных данных
          </Title>
          <Text size="sm" c="dimmed" mb="md">
            В соответствии со ст. 10.1 Федерального закона № 152-ФЗ согласия оформляются раздельно.
          </Text>

          {isLoading || !consents ? (
            <Skeleton h={160} />
          ) : (
            <Stack gap={0}>
              {(Object.keys(CONSENT_TEXT) as ConsentType[]).map((type) => (
                <Group key={type} justify="space-between" align="flex-start" wrap="wrap" gap="sm" py="md" style={{ borderTop: '1px solid var(--fsp-border)' }}>
                  <Box style={{ minWidth: 0, flex: 1 }}>
                    <Text fw={600} size="sm">
                      {CONSENT_TEXT[type].title}
                    </Text>
                    <Text size="xs" c="dimmed" maw={560}>
                      {CONSENT_TEXT[type].text}
                    </Text>
                  </Box>
                  <Switch
                    checked={active(type)}
                    disabled={toggle.isPending}
                    onChange={(e) => toggle.mutate({ type, on: e.currentTarget.checked })}
                    color="fspPink"
                    aria-label={CONSENT_TEXT[type].title}
                    style={{ flexShrink: 0 }}
                  />
                </Group>
              ))}
            </Stack>
          )}

          {hidden && (
            <Alert variant="light" color="orange" icon={<IconAlertTriangle size={18} />} mt="sm" title="Профиль не показывается работодателям">
              При отозванных согласиях или скрытом статусе вы не попадаете в подборки и не получаете приглашения.
            </Alert>
          )}
        </Paper>

        <Paper withBorder p="lg">
          <Title order={2} size="h4" mb={4}>
            Видимость профиля
          </Title>
          <Text size="sm" c="dimmed" mb="md">
            Статус поиска виден работодателям. Если выбрать «Скрыт», вы исчезнете из подборок и поиска.
          </Text>
          <Select
            label="Статус"
            maw={360}
            value={profile?.status ?? 'ACTIVELY_SEARCHING'}
            data={Object.entries(PROFILE_STATUS_LABELS).map(([value, label]) => ({ value, label }))}
            onChange={(v) => v && setStatus.mutate(v)}
            allowDeselect={false}
            disabled={!profile || setStatus.isPending}
          />
          <Text size="xs" c="dimmed" mt="md">
            Контактные данные скрыты от всех работодателей по умолчанию и раскрываются только по вашему согласию при принятии приглашения. Передачу контактов можно отозвать в разделе «Приглашения».
          </Text>
        </Paper>

        <Paper withBorder p="lg">
          <Title order={2} size="h4" mb={4}>
            Что видит работодатель
          </Title>
          <Text size="sm" c="dimmed" mb="md">
            Так выглядит ваша карточка в подборках и поиске. Это решение по правилам видимости данных: сведения о квалификации открыты, контакты — только после принятия приглашения.
          </Text>
          {profile && (
            <Box mb="md">
              <CandidateCard
                preview
                onInvite={() => undefined}
                card={{
                  id: profile.id,
                  full_name: fullName(profile),
                  confirmed_category: profile.confirmed_category,
                  confirmed_grade: profile.confirmed_grade,
                  is_grade_confirmed: profile.is_grade_confirmed,
                  category_percentile: profile.category_percentile,
                  fsp_score: profile.fsp_score,
                  is_fsp_verified: profile.is_fsp_verified,
                  desired_salary_min: profile.desired_salary_min,
                  salary_type: profile.salary_type,
                  work_format: profile.work_format,
                  city: profile.city,
                }}
              />
            </Box>
          )}
          <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="md">
            <Box>
              <Group gap={6} mb={6}>
                <IconEye size={16} color="var(--mantine-color-teal-7)" />
                <Text size="sm" fw={600}>
                  Видно сразу
                </Text>
              </Group>
              <List size="sm" spacing={4} icon={<ThemeIcon size={14} radius="xl" color="teal" variant="light"><IconCheck size={9} /></ThemeIcon>}>
                <List.Item>Категория, грейд и процентиль по тесту</List.Item>
                <List.Item>Подтверждённые навыки и достижения ФСП</List.Item>
                <List.Item>Город, формат работы, ожидания по зарплате</List.Item>
              </List>
            </Box>
            <Box>
              <Group gap={6} mb={6}>
                <IconLock size={16} color="var(--mantine-color-orange-7)" />
                <Text size="sm" fw={600}>
                  Скрыто до принятия приглашения
                </Text>
              </Group>
              <List size="sm" spacing={4} icon={<ThemeIcon size={14} radius="xl" color="orange" variant="light"><IconLock size={9} /></ThemeIcon>}>
                <List.Item>Телефон</List.Item>
                <List.Item>Электронная почта</List.Item>
                <List.Item>Telegram</List.Item>
              </List>
            </Box>
          </SimpleGrid>
        </Paper>

        <Paper withBorder p="lg">
          <Title order={2} size="h4" mb="sm">
            Журнал согласий
          </Title>
          <ScrollTable minWidth={520} label="Журнал согласий">
            <Table verticalSpacing="sm">
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>Согласие</Table.Th>
                  <Table.Th>Версия</Table.Th>
                  <Table.Th>Дано</Table.Th>
                  <Table.Th>Отозвано</Table.Th>
                  <Table.Th>Статус</Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {(consents?.consents ?? []).map((c) => (
                  <Table.Tr key={c.id}>
                    <Table.Td>{c.title ?? c.consent_type}</Table.Td>
                    <Table.Td>{c.version}</Table.Td>
                    <Table.Td>{formatDateTime(c.given_at)}</Table.Td>
                    <Table.Td>{formatDateTime(c.revoked_at)}</Table.Td>
                    <Table.Td>
                      <Badge size="sm" variant="light" color={c.is_given ? 'teal' : 'gray'}>
                        {c.is_given ? 'Действует' : 'Отозвано'}
                      </Badge>
                    </Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          </ScrollTable>
        </Paper>
      </Stack>
    </Container>
  );
};
