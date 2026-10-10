import React, { useEffect, useState } from 'react';
import { Alert, Box, Button, Group, NumberInput, Select, SegmentedControl, SimpleGrid, Stack, Text, Textarea } from '@mantine/core';
import { IconCheck, IconInfoCircle } from '@tabler/icons-react';
import { notifications } from '@mantine/notifications';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { api, CandidateCard } from '../../api/api';
import { toApiError } from '../../api/http';
import { keys } from '../../hooks/queries';
import { AppModal } from '../common/AppModal';
import { formatMoney, grossToNet, netToGross } from '../../utils/format';
import { CONTACT_METHOD_LABELS } from '../../utils/labels';

interface InviteModalProps {
  candidate: CandidateCard | null;
  onClose: () => void;
  /** Потребность, по которой составлена подборка (необязательно: приглашение возможно и без вакансии). */
  needId?: string;
  /** Бюджет из потребности подставляется в вилку. */
  defaultSalary?: { from?: number | null; to?: number | null; type?: string | null };
}

const MIN_MESSAGE = 10;

/** Приглашение кандидату. Зарплатная вилка в рублях обязательна (п. 2.2 ТЗ). */
export const InviteModal: React.FC<InviteModalProps> = ({ candidate, onClose, needId, defaultSalary }) => {
  const queryClient = useQueryClient();
  const [type, setType] = useState<'NET' | 'GROSS'>('NET');
  const [from, setFrom] = useState<number | string>('');
  const [to, setTo] = useState<number | string>('');
  const [contact, setContact] = useState('TELEGRAM');
  const [message, setMessage] = useState('');
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!candidate) return;
    const base = candidate.desired_salary_min ?? undefined;
    setType(defaultSalary?.type === 'GROSS' ? 'GROSS' : 'NET');
    setFrom(defaultSalary?.from ?? base ?? '');
    setTo(defaultSalary?.to ?? (base ? base + 50000 : ''));
    setContact('TELEGRAM');
    setMessage('Здравствуйте! Нам подошёл ваш подтверждённый профиль. Приглашаем обсудить задачи команды и условия сотрудничества.');
    setError(null);
     
  }, [candidate?.id]);

  const send = useMutation({
    mutationFn: () =>
      api.createInvitation({
        candidate_profile_id: candidate!.id,
        need_id: needId ?? null,
        salary_from: Number(from),
        salary_to: Number(to),
        salary_type: type,
        is_gross: type === 'GROSS',
        message: message.trim(),
        contact_method: contact,
      }),
    onSuccess: () => {
      notifications.show({
        title: 'Приглашение отправлено',
        message: `Кандидат увидит вилку ${formatMoney(Number(from))} – ${formatMoney(Number(to))} (${type === 'NET' ? 'на руки' : 'до вычета НДФЛ'}). Контакты откроются после принятия.`,
        color: 'teal',
        icon: <IconCheck size={18} />,
      });
      queryClient.invalidateQueries({ queryKey: keys.companyInvitations });
      onClose();
    },
    onError: (e) => setError(toApiError(e).message),
  });

  const submit = () => {
    const f = Number(from);
    const t = Number(to);
    if (!f || f <= 0) return setError('Укажите нижнюю границу зарплатной вилки в рублях — поле обязательно.');
    if (!t || t <= 0) return setError('Укажите верхнюю границу зарплатной вилки в рублях — поле обязательно.');
    if (t < f) return setError('Верхняя граница вилки не может быть меньше нижней.');
    if (message.trim().length < MIN_MESSAGE) return setError(`Текст предложения — не менее ${MIN_MESSAGE} символов.`);
    setError(null);
    send.mutate();
  };

  const f = Number(from) || 0;
  const t = Number(to) || 0;
  const alt = type === 'NET' ? [netToGross(f), netToGross(t)] : [grossToNet(f), grossToNet(t)];

  return (
    <AppModal opened={!!candidate} onClose={onClose} title="Приглашение кандидата" size="lg">
      <Stack gap="md">
        <Alert variant="light" color="gray" icon={<IconInfoCircle size={18} />} p="sm">
          Зарплатная вилка в рублях обязательна: кандидат видит условия до начала общения. Контакты кандидата откроются только после того, как он примет приглашение.
        </Alert>

        {error && (
          <Alert color="red" variant="light" role="alert">
            {error}
          </Alert>
        )}

        <Box>
          <Text size="sm" fw={500} mb={4}>
            Формат зарплаты
          </Text>
          <SegmentedControl
            fullWidth
            value={type}
            onChange={(v) => setType(v as 'NET' | 'GROSS')}
            data={[
              { label: 'На руки', value: 'NET' },
              { label: 'До вычета НДФЛ', value: 'GROSS' },
            ]}
          />
        </Box>

        <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="md">
          <NumberInput
            label="Зарплата от, ₽"
            required
            thousandSeparator=" "
            suffix=" ₽"
            min={0}
            step={10000}
            value={from}
            onChange={(v) => {
              setFrom(v);
              setError(null);
            }}
          />
          <NumberInput
            label="Зарплата до, ₽"
            required
            thousandSeparator=" "
            suffix=" ₽"
            min={0}
            step={10000}
            value={to}
            onChange={(v) => {
              setTo(v);
              setError(null);
            }}
          />
        </SimpleGrid>
        <Text size="xs" c="dimmed" ta="right" mt={-8}>
          ≈ {formatMoney(alt[0])} – {formatMoney(alt[1])} {type === 'NET' ? 'до вычета НДФЛ' : 'на руки'}
        </Text>

        <Select
          label="Способ связи после принятия"
          data={Object.entries(CONTACT_METHOD_LABELS).map(([value, label]) => ({ value, label }))}
          value={contact}
          onChange={(v) => setContact(v ?? 'TELEGRAM')}
          allowDeselect={false}
        />

        <Textarea
          label="Текст предложения"
          description="Опишите задачи и почему приглашаете именно этого кандидата"
          required
          value={message}
          onChange={(e) => setMessage(e.currentTarget.value)}
          minRows={3}
          autosize
          maxLength={5000}
        />

        <Group justify="flex-end">
          <Button variant="default" onClick={onClose}>
            Отмена
          </Button>
          <Button loading={send.isPending} onClick={submit}>
            Отправить приглашение
          </Button>
        </Group>
      </Stack>
    </AppModal>
  );
};
