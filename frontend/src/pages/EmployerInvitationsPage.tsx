import React, { useState } from 'react';
import { Alert, Badge, Button, Container, Group, Paper, Select, SimpleGrid, Skeleton, Stack, Table, Text, Title } from '@mantine/core';
import { IconBrandTelegram, IconInfoCircle, IconLock, IconMail, IconPhone, IconMessageCircle } from '@tabler/icons-react';
import { notifications } from '@mantine/notifications';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '../api/api';
import { PlatformChatModal } from '../components/PlatformChatModal';
import { toApiError } from '../api/http';
import { keys, useCompanyInvitations } from '../hooks/queries';
import { PageHeader } from '../components/common/PageHeader';
import { ScrollTable } from '../components/common/ScrollTable';
import { InvitationStatusBadge } from '../components/common/StatusBadge';
import { SalaryRange } from '../components/common/SalaryRange';
import { candidateDisplayName, formatDate } from '../utils/format';
import { INVITATION_STATUS, InvitationStatusCode } from '../utils/labels';

const ALL = 'ALL';

import { usePageTitle } from '../hooks/usePageTitle';

export const EmployerInvitationsPage: React.FC = () => {
  usePageTitle('Приглашения работодателя');
  const queryClient = useQueryClient();
  const { data: invitations = [], isLoading, isError } = useCompanyInvitations();
  const [status, setStatus] = useState<string>(ALL);
  const [chatOpened, setChatOpened] = useState(false);
  const [chatUser, setChatUser] = useState({ id: '', name: '' });

  const withdraw = useMutation({
    mutationFn: (id: string) => api.withdrawInvitation(id),
    onSuccess: () => {
      notifications.show({ title: 'Приглашение отозвано', message: 'Кандидат больше не сможет его принять.', color: 'gray' });
      queryClient.invalidateQueries({ queryKey: keys.companyInvitations });
    },
    onError: (e) => notifications.show({ title: 'Не удалось отозвать', message: toApiError(e).message, color: 'red' }),
  });

  const count = (s: string) => invitations.filter((i) => i.status === s).length;
  const applications = count('APPLIED');
  const shown = status === ALL ? invitations : invitations.filter((i) => i.status === status);

  return (
    <Container size="xl" p={0}>
      <Stack gap="lg">
        <PageHeader
          eyebrow="Кабинет работодателя"
          title="Приглашения и отклики"
          description="Статусы ваших предложений: отправлено, просмотрено, принято, отклонено. Контакты кандидата открываются после принятия приглашения или его собственного отклика на вакансию."
        />

        <SimpleGrid cols={{ base: 2, md: 5 }} spacing="md">
          {[
            ['Отправлено', invitations.length - applications],
            ['Отклики кандидатов', applications],
            ['Просмотрено', count('VIEWED')],
            ['Принято', count('ACCEPTED')],
            ['Отклонено', count('DECLINED')],
          ].map(([label, value]) => (
            <Paper key={label} withBorder p="md">
              <Text size="xs" c="dimmed">
                {label}
              </Text>
              <Text fw={700} size="xl">
                {value}
              </Text>
            </Paper>
          ))}
        </SimpleGrid>

        <Paper withBorder p="lg">
          <Group justify="space-between" mb="md" align="flex-end" wrap="wrap" gap="sm">
            <Title order={2} size="h3">Все приглашения и отклики</Title>
            <Select
              aria-label="Фильтр по статусу"
              maw={220}
              value={status}
              onChange={(v) => setStatus(v ?? ALL)}
              allowDeselect={false}
              data={[{ value: ALL, label: 'Любой статус' }, ...Object.entries(INVITATION_STATUS).map(([value, c]) => ({ value, label: c.label }))]}
            />
          </Group>
          {isLoading ? (
            <Skeleton h={160} />
          ) : isError ? (
            <Alert color="red" variant="light">
              Не удалось загрузить приглашения.
            </Alert>
          ) : shown.length === 0 ? (
            <Alert variant="light" color="gray" icon={<IconInfoCircle size={18} />} title="Приглашений нет">
              Выберите кандидата в подборке или в банке кандидатов и отправьте предложение с зарплатной вилкой.
            </Alert>
          ) : (
            <ScrollTable minWidth={860} label="Список приглашений">
              <Table verticalSpacing="sm" highlightOnHover>
                <Table.Thead>
                  <Table.Tr>
                    <Table.Th>Кандидат</Table.Th>
                    <Table.Th>Предложение</Table.Th>
                    <Table.Th>Вилка</Table.Th>
                    <Table.Th>Дата</Table.Th>
                    <Table.Th>Статус</Table.Th>
                    <Table.Th>Контакты</Table.Th>
                  </Table.Tr>
                </Table.Thead>
                <Table.Tbody>
                  {shown.map((inv) => {
                    const card = inv.candidate_card;
                    const c = inv.candidate_contacts;
                    const open = (inv.status === 'SENT' || inv.status === 'VIEWED') && !inv.is_expired;
                    return (
                      <Table.Tr key={inv.id}>
                        <Table.Td>
                          <Text fw={600} size="sm">
                            {c && (c.first_name || c.last_name) ? [c.first_name, c.last_name].filter(Boolean).join(' ') : candidateDisplayName(inv.candidate_profile_id, card?.full_name)}
                          </Text>
                          {card?.confirmed_category && (
                            <Badge size="xs" variant="light" color="fspPink">
                              {card.confirmed_category}
                            </Badge>
                          )}
                        </Table.Td>
                        <Table.Td maw={260}>
                          <Text size="sm" lineClamp={2}>
                            {inv.message}
                          </Text>
                        </Table.Td>
                        <Table.Td>
                          <SalaryRange from={inv.salary_from} to={inv.salary_to} type={inv.salary_type} size="sm" />
                        </Table.Td>
                        <Table.Td>
                          <Text size="sm">{formatDate(inv.sent_at)}</Text>
                        </Table.Td>
                        <Table.Td>
                          <Stack gap={4} align="flex-start">
                            <Group gap="xs">
                              <InvitationStatusBadge status={inv.status} expired={inv.is_expired} />
                              {(inv.status === 'ACCEPTED' || inv.status === 'APPLIED') && (
                                <Button size="compact-xs" variant="light" leftSection={<IconMessageCircle size={14} />} onClick={() => { setChatUser({ id: inv.candidate_profile_id, name: inv.candidate_card?.full_name || 'Кандидат' }); setChatOpened(true); }}>Чат на платформе</Button>
                              )}
                            </Group>
                            {open && (
                              <Button size="compact-xs" variant="subtle" color="red" loading={withdraw.isPending && withdraw.variables === inv.id} onClick={() => withdraw.mutate(inv.id)}>
                                Отозвать
                              </Button>
                            )}
                          </Stack>
                        </Table.Td>
                        <Table.Td>
                          {inv.contacts_disclosed && c ? (
                            <Stack gap={2}>
                              {c.email && (
                                <Group gap={4} wrap="nowrap">
                                  <IconMail size={13} color="var(--fsp-text-muted)" />
                                  <Text size="xs">{c.email}</Text>
                                </Group>
                              )}
                              {c.phone && (
                                <Group gap={4} wrap="nowrap">
                                  <IconPhone size={13} color="var(--fsp-text-muted)" />
                                  <Text size="xs">{c.phone}</Text>
                                </Group>
                              )}
                              {c.telegram && (
                                <Group gap={4} wrap="nowrap">
                                  <IconBrandTelegram size={13} color="var(--fsp-text-muted)" />
                                  <Text size="xs">{c.telegram}</Text>
                                </Group>
                              )}
                            </Stack>
                          ) : (
                            <Group gap={4} wrap="nowrap">
                              <IconLock size={13} color="var(--fsp-text-muted)" />
                              <Text size="xs" c="dimmed">
                                {inv.status === 'CONTACTS_REVOKED' ? 'Кандидат скрыл контакты' : 'Скрыты до принятия'}
                              </Text>
                            </Group>
                          )}
                        </Table.Td>
                      </Table.Tr>
                    );
                  })}
                </Table.Tbody>
              </Table>
            </ScrollTable>
          )}
        </Paper>
      </Stack>
      <PlatformChatModal opened={chatOpened} onClose={() => setChatOpened(false)} receiverId={chatUser.id} receiverName={chatUser.name} />
    </Container>
  );
};

export type { InvitationStatusCode };
