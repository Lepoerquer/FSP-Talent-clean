import React, { useEffect, useRef, useState } from 'react';
import {
  Alert,
  Badge,
  Box,
  Button,
  Card,
  Group,
  Paper,
  Radio,
  Skeleton,
  Stack,
  Text,
  Textarea,
  Title,
} from '@mantine/core';
import { IconBrandTelegram, IconBuildingSkyscraper, IconCheck, IconEyeOff, IconMail, IconMailOpened, IconPhone, IconShieldCheck, IconX, IconMessageCircle } from '@tabler/icons-react';
import { notifications } from '@mantine/notifications';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { PlatformChatModal } from '../PlatformChatModal';
import { api, DeclineReason, Invitation } from '../../api/api';
import { toApiError } from '../../api/http';
import { fullName, isOpenInvitation, keys, useCandidateInvitations, useProfile } from '../../hooks/queries';
import { InvitationStatusBadge } from '../common/StatusBadge';
import { AppModal } from '../common/AppModal';
import { SalaryRange } from '../common/SalaryRange';
import { formatDate } from '../../utils/format';
import { CONTACT_METHOD_LABELS, DECLINE_REASON_LABELS } from '../../utils/labels';

interface InvitationsPanelProps {
  /** Сколько приглашений показать (остальные доступны на отдельной странице). */
  limit?: number;
}

export const InvitationsPanel: React.FC<InvitationsPanelProps> = ({ limit }) => {
  const { data: profile } = useProfile();
  const queryClient = useQueryClient();
  const { data: invitations = [], isLoading, isError } = useCandidateInvitations();

  const [acceptTarget, setAcceptTarget] = useState<Invitation | null>(null);
  const [declineTarget, setDeclineTarget] = useState<Invitation | null>(null);
  const [declineReason, setDeclineReason] = useState<DeclineReason>('SALARY');
  const [declineComment, setDeclineComment] = useState('');
  
  const [chatOpened, setChatOpened] = useState(false);
  const [chatUser, setChatUser] = useState({ id: '', name: '' });

  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: keys.candidateInvitations });
    queryClient.invalidateQueries({ queryKey: keys.companyInvitations });
  };
  const onError = (e: unknown) => notifications.show({ title: 'Не удалось выполнить действие', message: toApiError(e).message, color: 'red' });

  const shown = limit ? invitations.slice(0, limit) : invitations;

  // Помечаем просмотренными только приглашения, которые кандидат видит на экране: работодатель получает статус «Просмотрено».
  const viewed = useRef(new Set<string>());
  useEffect(() => {
    const fresh = shown.filter((i) => i.status === 'SENT' && !i.is_expired && !viewed.current.has(i.id));
    if (fresh.length === 0) return;
    fresh.forEach((i) => viewed.current.add(i.id));
    Promise.allSettled(fresh.map((i) => api.viewInvitation(i.id))).then(refresh);
     
  }, [invitations, limit]);

  const accept = useMutation({
    mutationFn: (id: string) => api.acceptInvitation(id),
    onSuccess: (inv) => {
      notifications.show({
        title: 'Приглашение принято',
        message: `Контакты переданы компании «${inv.company?.name ?? ''}». Дальнейшее общение — напрямую.`,
        color: 'teal',
        icon: <IconCheck size={18} />,
      });
      setAcceptTarget(null);
      refresh();
    },
    onError,
  });

  const decline = useMutation({
    mutationFn: ({ id, reason, feedback }: { id: string; reason: DeclineReason; feedback?: string }) =>
      api.declineInvitation(id, reason, feedback),
    onSuccess: () => {
      notifications.show({ title: 'Приглашение отклонено', message: 'Причина передана работодателю.', color: 'gray', icon: <IconX size={18} /> });
      setDeclineTarget(null);
      setDeclineComment('');
      setDeclineReason('SALARY');
      refresh();
    },
    onError,
  });

  const revoke = useMutation({
    mutationFn: (id: string) => api.revokeContacts(id),
    onSuccess: () => {
      notifications.show({ title: 'Контакты скрыты', message: 'Работодатель больше не видит ваши контактные данные.', color: 'teal' });
      refresh();
    },
    onError,
  });

  const openCount = invitations.filter(isOpenInvitation).length;

  return (
    <Paper withBorder p="lg">
      <Group justify="space-between" align="flex-start" mb="md">
        <Box>
          <Group gap="xs">
            <Title order={2} size="h3">Приглашения и отклики</Title>
            {openCount > 0 && (
              <Badge color="fspPink" variant="filled">
                {openCount} {openCount === 1 ? 'ждёт ответа' : 'ждут ответа'}
              </Badge>
            )}
          </Group>
          <Text size="sm" c="dimmed" mt={4}>
            В каждом приглашении указана зарплатная вилка в рублях. Контакты передаются компании только после вашего согласия или вашего отклика на вакансию.
          </Text>
        </Box>
        {limit && invitations.length > limit && (
          <Button component={Link} to="/candidate/invitations" variant="default" size="xs">
            Все приглашения ({invitations.length})
          </Button>
        )}
      </Group>

      {isLoading ? (
        <Stack gap="sm">
          <Skeleton h={120} />
          <Skeleton h={120} />
        </Stack>
      ) : isError ? (
        <Alert color="red" variant="light">
          Не удалось загрузить приглашения. Обновите страницу.
        </Alert>
      ) : shown.length === 0 ? (
        <Alert variant="light" color="gray" icon={<IconMail size={18} />} title="Приглашений пока нет">
          Компании находят кандидатов по подтверждённой категории. Пройдите квалификационный тест и заполните профиль, чтобы появиться в подборках.
        </Alert>
      ) : (
        <Stack gap="sm">
          {shown.map((inv) => {
            const open = isOpenInvitation(inv);
            return (
              <Card
                key={inv.id}
                padding="md"
                style={{
                  borderLeft: `4px solid ${open ? 'var(--fsp-primary)' : inv.status === 'ACCEPTED' ? 'var(--mantine-color-teal-6)' : 'var(--fsp-border-strong)'}`,
                  background: open || inv.status === 'ACCEPTED' ? undefined : 'var(--fsp-tint-neutral)',
                }}
              >
                <div className="split-grid">
                  <Box className="span-7">
                    <Group gap="xs" mb={4}>
                      <IconBuildingSkyscraper size={16} color="var(--fsp-text-muted)" />
                      <Text fw={700} size="sm">
                        {inv.company?.name ?? 'Компания'}
                      </Text>
                      {inv.company?.is_verified && (
                        <Badge size="xs" variant="light" color="teal" leftSection={<IconShieldCheck size={11} />}>
                          ИНН проверен
                        </Badge>
                      )}
                      <Text size="xs" c="dimmed">
                        · {formatDate(inv.sent_at)}
                      </Text>
                      <Group gap="xs">
                        <InvitationStatusBadge status={inv.status} expired={inv.is_expired} />
                      </Group>
                    </Group>
                    {inv.status !== 'APPLIED' && (
                      <Text size="sm" mb="sm" style={{ whiteSpace: 'pre-line' }}>
                        {inv.message}
                      </Text>
                    )}
                    <Group gap="sm" align="flex-start">
                      <SalaryRange from={inv.salary_from} to={inv.salary_to} type={inv.salary_type} />
                    </Group>
                    {inv.status === 'APPLIED' ? (
                      <Text size="xs" c="dimmed" mt={6}>
                        Ваш отклик на вакансию: компания видит профиль и контакты и может написать в чат на платформе.
                      </Text>
                    ) : (
                      <Text size="xs" c="dimmed" mt={6}>
                        Связь после принятия: {CONTACT_METHOD_LABELS[inv.contact_method] ?? inv.contact_method}
                        {open && ` · предложение действует до ${formatDate(inv.expires_at)}`}
                      </Text>
                    )}
                  </Box>

                  <Box className="span-5">
                    {open && (
                      <Group justify="flex-end" gap="sm">
                        <Button variant="default" size="sm" leftSection={<IconX size={16} />} onClick={() => setDeclineTarget(inv)}>
                          Отклонить
                        </Button>
                        <Button size="sm" leftSection={<IconCheck size={16} />} onClick={() => setAcceptTarget(inv)}>
                          Принять
                        </Button>
                      </Group>
                    )}
                    {inv.status === 'APPLIED' && (
                      <Group justify="flex-end">
                        <Button
                          size="xs"
                          variant="light"
                          leftSection={<IconMessageCircle size={14} />}
                          onClick={() => {
                            setChatUser({ id: inv.company_id, name: inv.company?.name || 'Работодатель' });
                            setChatOpened(true);
                          }}
                        >
                          Чат на платформе
                        </Button>
                      </Group>
                    )}
                    {(inv.status === 'ACCEPTED' || inv.status === 'CONTACTS_REVOKED') && (
                      <Stack gap={6} align="flex-end">
                        <Text size="xs" fw={600} c={inv.contacts_disclosed ? 'teal' : 'dimmed'}>
                          {inv.contacts_disclosed ? 'Контакты переданы компании' : 'Доступ к контактам отозван'}
                        </Text>
                        <Group gap="xs" justify="flex-end">
                          {inv.contacts_disclosed && (
                            <Button
                              variant="default"
                              size="xs"
                              leftSection={<IconEyeOff size={14} />}
                              loading={revoke.isPending && revoke.variables === inv.id}
                              onClick={() => revoke.mutate(inv.id)}
                            >
                              Скрыть контакты
                            </Button>
                          )}
                          <Button
                            size="xs"
                            variant="light"
                            leftSection={<IconMessageCircle size={14} />}
                            onClick={() => {
                              setChatUser({ id: inv.company_id, name: inv.company?.name || 'Работодатель' });
                              setChatOpened(true);
                            }}
                          >
                            Чат на платформе
                          </Button>
                        </Group>
                      </Stack>
                    )}
                    {inv.status === 'DECLINED' && inv.decline_reason && (
                      <Text size="xs" c="dimmed" ta="right">
                        Причина: {DECLINE_REASON_LABELS[inv.decline_reason] ?? inv.decline_reason}
                      </Text>
                    )}
                  </Box>
                </div>
              </Card>
            );
          })}
        </Stack>
      )}

      <AppModal opened={!!acceptTarget} onClose={() => setAcceptTarget(null)} title="Передача контактных данных">
        <Stack gap="md">
          <Alert color="blue" variant="light" title="Согласие на передачу контактов">
            Принимая приглашение компании «{acceptTarget?.company?.name}», вы разрешаете передать ей контактные данные из профиля (ст. 10.1 152-ФЗ). До этого момента компания видит только категорию, результаты и опыт.
          </Alert>
          <Card padding="sm">
            <Text className="section-eyebrow" mb={6}>
              Будет передано
            </Text>
            <Stack gap={6}>
              <Text size="sm" fw={600}>
                {fullName(profile)}
              </Text>
              <Group gap="xs">
                <IconMail size={16} color="var(--fsp-text-muted)" />
                <Text size="sm">{profile?.email || '—'}</Text>
              </Group>
              <Group gap="xs">
                <IconPhone size={16} color="var(--fsp-text-muted)" />
                <Text size="sm">{profile?.phone || 'не указан'}</Text>
              </Group>
              <Group gap="xs">
                <IconBrandTelegram size={16} color="var(--fsp-text-muted)" />
                <Text size="sm">{profile?.telegram || 'не указан'}</Text>
              </Group>
            </Stack>
          </Card>
          <Group justify="flex-end">
            <Button variant="default" onClick={() => setAcceptTarget(null)}>
              Отмена
            </Button>
            <Button loading={accept.isPending} leftSection={<IconMailOpened size={16} />} onClick={() => acceptTarget && accept.mutate(acceptTarget.id)}>
              Принять и передать контакты
            </Button>
          </Group>
        </Stack>
      </AppModal>

      <AppModal opened={!!declineTarget} onClose={() => setDeclineTarget(null)} title="Причина отклонения">
        <Stack gap="md">
          <Text size="sm" c="dimmed">
            Причина передаётся работодателю и помогает ему корректировать предложения.
          </Text>
          <Radio.Group value={declineReason} onChange={(v) => setDeclineReason(v as DeclineReason)}>
            <Stack gap="xs">
              {Object.entries(DECLINE_REASON_LABELS).map(([value, label]) => (
                <Radio key={value} value={value} label={label} />
              ))}
            </Stack>
          </Radio.Group>
          <Textarea placeholder="Комментарий (необязательно)" value={declineComment} onChange={(e) => setDeclineComment(e.currentTarget.value)} minRows={2} autosize />
          <Group justify="flex-end">
            <Button variant="default" onClick={() => setDeclineTarget(null)}>
              Назад
            </Button>
            <Button
              color="red"
              loading={decline.isPending}
              onClick={() => declineTarget && decline.mutate({ id: declineTarget.id, reason: declineReason, feedback: declineComment.trim() || undefined })}
            >
              Отклонить приглашение
            </Button>
          </Group>
        </Stack>
      </AppModal>
      <PlatformChatModal opened={chatOpened} onClose={() => setChatOpened(false)} receiverId={chatUser.id} receiverName={chatUser.name} />
    </Paper>
  );
};
