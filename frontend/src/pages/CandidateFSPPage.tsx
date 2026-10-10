import React, { useState } from 'react';
import { Alert, Badge, Box, Button, Card, Checkbox, Container, Group, Paper, SimpleGrid, Stack, Text, TextInput, Timeline, Title } from '@mantine/core';
import { IconAward, IconCheck, IconInfoCircle, IconShieldCheck } from '@tabler/icons-react';
import { notifications } from '@mantine/notifications';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '../api/api';
import { toApiError } from '../api/http';
import { keys, useProfile } from '../hooks/queries';
import { PageHeader } from '../components/common/PageHeader';
import { formatCount, formatDate, formatDecimal } from '../utils/format';
import { fspLevelLabel, fspResultLabel } from '../utils/labels';

const FSP_ID_RE = /^FSP-[A-Z0-9-]{3,20}$/i;

import { usePageTitle } from '../hooks/usePageTitle';
import { FspStarIcon } from '../components/common/FspStarIcon';

export const CandidateFSPPage: React.FC = () => {
  usePageTitle('ФСП ID и достижения');
  const queryClient = useQueryClient();
  const { data: profile } = useProfile();
  const [fspId, setFspId] = useState('');
  const [consent, setConsent] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const linked = Boolean(profile?.is_fsp_verified);

  const link = useMutation({
    mutationFn: () => api.linkFsp(fspId.trim().toUpperCase(), consent),
    onSuccess: (res) => {
      setFspId('');
      setConsent(false);
      queryClient.invalidateQueries({ queryKey: keys.profile });
      notifications.show({
        title: 'ФСП ID привязан',
        message: res.description,
        color: 'teal',
        icon: <IconCheck size={18} />,
      });
    },
    onError: (e) => setError(toApiError(e).message),
  });

  const submit = (ev: React.FormEvent) => {
    ev.preventDefault();
    if (!FSP_ID_RE.test(fspId.trim())) {
      setError('Неверный формат. Идентификатор выглядит так: FSP-1001');
      return;
    }
    if (!consent) {
      setError('Для проверки в реестре нужно согласие на интеграцию и верификацию достижений (152-ФЗ).');
      return;
    }
    setError(null);
    link.mutate();
  };

  return (
    <Container size="lg" p={0}>
      <Stack gap="lg">
        <PageHeader
          eyebrow="Кабинет кандидата"
          title="ФСП ID и достижения"
          description="Связь профиля с идентификатором участника Федерации спортивного программирования. Достижения подтверждаются реестром и учитываются при ранжировании внутри вашей категории."
        />

        <Paper withBorder p="lg">
          <Group justify="space-between" align="center" mb="sm" gap="xs">
            <Group gap="sm" wrap="nowrap">
              <FspStarIcon size={24} />
              <Title order={2} size="h4">Привязка идентификатора ФСП ID</Title>
            </Group>
            <Badge variant="light" color={linked ? 'teal' : 'gray'}>
              {linked ? `Привязан: ${profile?.fsp_id}` : 'Не привязан'}
            </Badge>
          </Group>
          <form onSubmit={submit} noValidate>
            <Stack gap="sm" maw={480}>
              <TextInput
                label="ФСП ID"
                placeholder="FSP-1001"
                value={fspId}
                onChange={(e) => {
                  setFspId(e.currentTarget.value);
                  setError(null);
                }}
                error={error}
                description="Номер участника в реестре ФСП"
              />
              <Checkbox
                checked={consent}
                onChange={(e) => setConsent(e.currentTarget.checked)}
                label="Согласен на передачу ФСП ID в реестр и получение сведений о моих достижениях (152-ФЗ)"
              />
              <Group>
                <Button type="submit" loading={link.isPending} leftSection={<IconShieldCheck size={16} />}>
                  {linked ? 'Привязать другой ID' : 'Проверить и привязать'}
                </Button>
              </Group>
            </Stack>
          </form>
          <Text size="xs" c="dimmed" mt="sm">
            Стенд подключён к имитации реестра ФСП: известны идентификаторы FSP-1001, FSP-1002 и другие. Неизвестный номер вернёт ответ «не найден».
          </Text>
        </Paper>

        {linked && profile ? (
          <Paper withBorder p="lg">
            <Group justify="space-between" align="flex-start" mb="md" gap="md">
              <Group gap="sm" align="flex-start" wrap="nowrap">
                <FspStarIcon size={26} style={{ marginTop: 2 }} />
                <Box>
                  <Title order={2} size="h4">Подтверждённые достижения ФСП</Title>
                  <Text size="sm" c="dimmed">
                    Из реестра Федерации спортивного программирования: {formatCount(profile.fsp_achievements.length, ['запись', 'записи', 'записей'])}
                  </Text>
                </Box>
              </Group>
              <Card padding="sm">
                <Text size="xs" c="dimmed">
                  Балл ФСП
                </Text>
                <Text fw={700} size="xl">
                  {formatDecimal(profile.fsp_score ?? 0)}{' '}
                  <Text span size="sm" c="dimmed">
                    / 1,00
                  </Text>
                </Text>
              </Card>
            </Group>

            <Timeline active={profile.fsp_achievements.length} bulletSize={24} lineWidth={2} color="fspPurple">
              {profile.fsp_achievements.map((ach) => (
                <Timeline.Item
                  key={ach.id}
                  bullet={<IconAward size={13} />}
                  title={
                    <Group gap="xs">
                      <Text fw={600}>{ach.event_name}</Text>
                      <Badge color="fspPink" variant="light" size="sm">
                        {fspResultLabel(ach.result)}
                      </Badge>
                      {ach.sport_category && (
                        <Badge color="gray" variant="outline" size="sm">
                          {ach.sport_category}
                        </Badge>
                      )}
                    </Group>
                  }
                >
                  <Text size="sm">{ach.discipline}</Text>
                  <Text size="xs" c="dimmed">
                    {fspLevelLabel(ach.level)} уровень{ach.event_date ? ` · ${formatDate(ach.event_date)}` : ''}
                  </Text>
                </Timeline.Item>
              ))}
            </Timeline>
          </Paper>
        ) : (
          <Alert variant="light" color="gray" icon={<IconInfoCircle size={20} />} title="История ФСП не привязана">
            Отсутствие ФСП ID не накладывает штрафов: ранжирование строится на результате квалификационного теста.
          </Alert>
        )}

        <Paper withBorder p="lg">
          <Title order={2} size="h4" mb="sm">
            Как достижения учитываются в подборе
          </Title>
          <SimpleGrid cols={{ base: 1, sm: 3 }} spacing="md">
            {[
              ['Не определяют грейд', 'Грейд присваивается только по результату квалификационного теста.'],
              ['Усиливают позицию в категории', 'Подтверждённые результаты — бонус к ранжированию внутри вашей категории (вес 7%).'],
              ['Дисциплины равноценны', 'Все направления ФСП имеют одинаковый базовый вес; значение имеют результат и уровень соревнования.'],
            ].map(([title, text]) => (
              <Box key={title}>
                <Text fw={600} size="sm" mb={2}>
                  {title}
                </Text>
                <Text size="xs" c="dimmed">
                  {text}
                </Text>
              </Box>
            ))}
          </SimpleGrid>
        </Paper>
      </Stack>
    </Container>
  );
};
