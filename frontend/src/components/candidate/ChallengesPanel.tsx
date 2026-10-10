import React, { useState } from 'react';
import { Alert, Badge, Box, Button, Card, Group, Paper, SimpleGrid, Skeleton, Stack, Text, Textarea, Title } from '@mantine/core';
import { IconCheck, IconCode } from '@tabler/icons-react';
import { notifications } from '@mantine/notifications';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { api, Challenge } from '../../api/api';
import { toApiError } from '../../api/http';
import { keys, useChallenges } from '../../hooks/queries';
import { AppModal } from '../common/AppModal';
import { gradeLabel, specLabel } from '../../utils/labels';

const MIN_LENGTH = 30;

/** Регулярные короткие задания от работодателей (необязательная часть MVP, п. 2.1 ТЗ). */
export const ChallengesPanel: React.FC = () => {
  const queryClient = useQueryClient();
  const { data: challenges = [], isLoading, isError } = useChallenges();
  const [target, setTarget] = useState<Challenge | null>(null);
  const [text, setText] = useState('');

  const submit = useMutation({
    mutationFn: ({ id, body }: { id: string; body: string }) => api.submitChallenge(id, body),
    onSuccess: (res) => {
      // ответ хранится на сервере: работодатель его читает, а профиль получает свежую отметку активности
      queryClient.invalidateQueries({ queryKey: keys.challenges });
      notifications.show({
        title: 'Решение отправлено',
        message: res.message,
        color: 'teal',
        icon: <IconCheck size={18} />,
      });
      setTarget(null);
      setText('');
    },
    onError: (e) => notifications.show({ title: 'Не удалось отправить', message: toApiError(e).message, color: 'red' }),
  });

  const tooShort = text.trim().length < MIN_LENGTH;

  return (
    <Paper withBorder p="lg">
      <Group gap="sm" mb="md" align="flex-start" wrap="nowrap">
        <IconCode size={22} color="var(--fsp-purple)" style={{ marginTop: 4, flexShrink: 0 }} />
        <Box>
          <Title order={2} size="h3">Задания от работодателей</Title>
          <Text size="sm" c="dimmed">
            Короткие практические задачи: решите или предложите подход. Ответы поддерживают профиль в актуальном состоянии и дают работодателю свежий сигнал.
          </Text>
        </Box>
      </Group>

      {isLoading ? (
        <Skeleton h={140} />
      ) : isError ? (
        <Alert color="red" variant="light">
          Не удалось загрузить задания.
        </Alert>
      ) : challenges.length === 0 ? (
        <Alert color="gray" variant="light">
          Сейчас активных заданий нет.
        </Alert>
      ) : (
        <SimpleGrid cols={{ base: 1, md: 2 }} spacing="md">
          {challenges.map((ch) => {
            const sent = ch.my_answer ?? undefined;
            return (
              <Card key={ch.id} padding="md">
                <Group justify="space-between" mb="xs" wrap="nowrap">
                  <Text size="xs" fw={600} c="dimmed" truncate>
                    {ch.company_name}
                  </Text>
                  <Badge variant="outline" color="gray" size="sm">
                    ≈ {ch.time_limit_minutes} мин · {gradeLabel(ch.target_grade)}
                  </Badge>
                </Group>
                <Text fw={600} size="sm" mb={4}>
                  {ch.title}
                </Text>
                <Text size="xs" c="dimmed" mb="md">
                  {ch.task_description}
                </Text>
                <Group justify="space-between" align="center">
                  <Badge variant="light" color="fspPurple" size="sm">
                    {specLabel(ch.specialization)}
                  </Badge>
                  <Button
                    size="xs"
                    variant={sent ? 'default' : 'light'}
                    onClick={() => {
                      setTarget(ch);
                      setText(sent ?? '');
                    }}
                  >
                    {sent ? 'Изменить ответ' : 'Предложить подход'}
                  </Button>
                </Group>
                {sent && (
                  <Text size="xs" c="teal" fw={600} mt={6}>
                    Ответ отправлен
                  </Text>
                )}
              </Card>
            );
          })}
        </SimpleGrid>
      )}

      <AppModal opened={!!target} onClose={() => setTarget(null)} title={target?.title ?? ''} size="lg">
        <Stack gap="md">
          <Text size="sm" c="dimmed">
            {target?.task_description}
          </Text>
          <Textarea
            label="Ваше решение или подход"
            description={`Текст решения или ссылка на репозиторий, не менее ${MIN_LENGTH} символов`}
            value={text}
            onChange={(e) => setText(e.currentTarget.value)}
            minRows={6}
            autosize
            maxRows={14}
            error={text.length > 0 && tooShort ? `Добавьте деталей: сейчас ${text.trim().length} из ${MIN_LENGTH} символов` : undefined}
          />
          <Group justify="flex-end">
            <Button variant="default" onClick={() => setTarget(null)}>
              Отмена
            </Button>
            <Button disabled={tooShort} loading={submit.isPending} onClick={() => target && submit.mutate({ id: target.id, body: text.trim() })}>
              Отправить
            </Button>
          </Group>
        </Stack>
      </AppModal>
    </Paper>
  );
};
