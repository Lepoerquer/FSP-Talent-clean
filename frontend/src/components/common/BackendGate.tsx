import React, { useCallback, useEffect, useState } from 'react';
import { Box, Button, Center, Code, List, Loader, Paper, Stack, Text, Title } from '@mantine/core';
import { api } from '../../api/api';

/** Проверяет доступность сервера. Если сервер не отвечает, показывает понятную инструкцию вместо пустых экранов. */
export const BackendGate: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [state, setState] = useState<'checking' | 'up' | 'down'>('checking');

  const check = useCallback(async () => {
    setState('checking');
    setState((await api.health()) ? 'up' : 'down');
  }, []);

  useEffect(() => {
    void check();
  }, [check]);

  if (state === 'up') return <>{children}</>;

  if (state === 'checking') {
    return (
      <Center h="100vh">
        <Loader color="fspPink" size="sm" />
      </Center>
    );
  }

  return (
    <Center mih="100vh" p="md" style={{ background: 'var(--fsp-bg)' }}>
      <Paper withBorder p="xl" maw={560} w="100%">
        <Box className="page-head" mb="md">
          <Title order={1} size="h3">Сервер платформы недоступен</Title>
          <Text size="sm" c="dimmed" mt={4}>
            Интерфейс не смог связаться с API. Запустите серверную часть и повторите попытку.
          </Text>
        </Box>
        <Stack gap="sm">
          <List size="sm" spacing="xs">
            <List.Item>
              В Docker: <Code>docker compose -f infra/docker-compose.yml up -d</Code>
            </List.Item>
            <List.Item>
              Без Docker: <Code>uvicorn backend.app.main:app --port 8000</Code>
            </List.Item>
          </List>
          <Text size="xs" c="dimmed">
            Адрес API задаётся переменной VITE_API_URL (по умолчанию /api/v1 через прокси).
          </Text>
          <Button onClick={check} mt="xs">
            Повторить проверку
          </Button>
        </Stack>
      </Paper>
    </Center>
  );
};
